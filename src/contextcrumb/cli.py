"""Command line interface for ContextCrumb."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from contextcrumb.compressor import (
    DEFAULT_GOLDEN_MIN_KEEP_RATIO,
    DEFAULT_MAX_LENGTH,
    DEFAULT_BACKEND,
    DEFAULT_MODEL_ID,
    DEFAULT_STRIDE,
    DEFAULT_THRESHOLD,
    CompressionResult,
    ContextCompressor,
    TokenDecision,
)
from contextcrumb.stats import (
    aggregate_events,
    format_human_stats,
    format_share_stats,
    log_result,
    parse_since,
    read_events,
    reset_stats,
)

DEFAULT_SERVICE_URL = "http://127.0.0.1:8765"


def read_text(args: argparse.Namespace) -> str:
    source = getattr(args, "source", None)
    provided = [args.text is not None, args.input is not None, source is not None]
    if sum(provided) > 1:
        raise SystemExit("Provide only one input source: FILE, --text, --input, or stdin.")
    if args.text is not None:
        return args.text
    if args.input is not None:
        return args.input.read_text(encoding=args.encoding)
    if source is not None:
        return source.read_text(encoding=args.encoding)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("No input text provided. Use FILE, --text, --input, or pipe text on stdin.")


def add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=DEFAULT_MODEL_ID, help="Hugging Face model id or local model path.")
    parser.add_argument("--backend", choices=["onnx", "torch"], default=DEFAULT_BACKEND, help="Inference backend.")
    parser.add_argument("--device", default="auto", help="Inference device: auto, cpu, cuda, etc.")
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH, help="Model max sequence length.")
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE, help="Sliding-window overlap.")
    parser.add_argument("--window-batch-size", type=int, default=None, help="Maximum number of sliding windows per model call.")
    parser.add_argument("--revision", default=None, help="Optional Hugging Face revision.")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Optional Hugging Face cache directory.")


def add_compression_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Keep probability threshold.")
    parser.add_argument(
        "--target-keep-ratio",
        type=float,
        default=None,
        help="Keep the top-scoring tokens near this ratio. Overrides golden mode.",
    )
    parser.add_argument(
        "--golden",
        dest="golden",
        action="store_true",
        default=True,
        help="Use an adaptive cutoff from the largest word-token probability gap. This is the default.",
    )
    parser.add_argument(
        "--no-golden",
        dest="golden",
        action="store_false",
        help="Disable golden mode and use --threshold instead.",
    )
    parser.add_argument(
        "--golden-min-keep-ratio",
        type=float,
        default=DEFAULT_GOLDEN_MIN_KEEP_RATIO,
        help="Minimum word-like token ratio golden mode may keep.",
    )
    parser.add_argument("--return-tokens", action="store_true", help="Include token decisions in JSON output.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of plain compressed text.")
    parser.add_argument("--no-stats", action="store_true", help="Do not write a local token-savings stats event.")
    parser.add_argument("--stats-source", default="cli", help="Stats source label for local ledger events.")


def add_service_client_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--use-service",
        action="store_true",
        default=os.environ.get("CONTEXTCRUMB_USE_SERVICE") == "1",
        help="Use a running contextcrumb service instead of loading the model in this process.",
    )
    parser.add_argument(
        "--service-url",
        default=os.environ.get("CONTEXTCRUMB_SERVICE_URL", DEFAULT_SERVICE_URL),
        help="ContextCrumb service URL.",
    )


def add_service_file_read_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--allow-root",
        type=Path,
        action="append",
        default=None,
        help="Allow /compress_file to read files under this root. Repeat for multiple roots. Defaults to the service working directory.",
    )
    parser.add_argument(
        "--disable-file-reads",
        action="store_true",
        help="Disable the /compress_file endpoint for this local service.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextcrumb",
        description="Compress context with ContextCrumb-32M.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Agent workflow:\n"
            "  1. Inventory filenames/sizes first; do not cat/type/Get-Content large candidate\n"
            "     files into the conversation before compression.\n"
            "  2. Use `contextcrumb load FILE` to read large prose-heavy local text as compressed\n"
            "     LLM context. This is the default read path for agents.\n"
            "  3. Use `contextcrumb inspect FILE` only when you need token/word savings or other\n"
            "     diagnostics without reading the text.\n"
            "  4. Use `contextcrumb batch DIR --glob '*.md' --out OUT --no-stats` for many files;\n"
            "     sample or inspect outputs before relying on them.\n"
            "  5. Use `python -m contextcrumb ...` if the package is installed but the console\n"
            "     script is not on PATH.\n"
            "\n"
            "Safety:\n"
            "  Do not rely on compressed output for exact code, diffs, configs, commands, legal\n"
            "  text, policy text, quotes, or formatting. Use raw source when exactness matters.\n"
            "  If `--json` hits terminal Unicode errors, set PYTHONIOENCODING=utf-8.\n"
            "\n"
            "Examples:\n"
            "  contextcrumb load README.md\n"
            "  contextcrumb inspect notes.txt\n"
            "  contextcrumb load notes.txt --target-keep-ratio 0.5\n"
            "  contextcrumb batch docs --glob '*.md' --out /tmp/contextcrumb-docs --no-stats\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    compress_parser = subparsers.add_parser("compress", help="Compress a text string or file.")
    compress_parser.add_argument("source", type=Path, nargs="?", help="Input text file.")
    compress_parser.add_argument("--text", default=None, help="Text to compress.")
    compress_parser.add_argument("--input", type=Path, default=None, help="Input text file. Prefer positional FILE for new usage.")
    compress_parser.add_argument("--encoding", default="utf-8", help="Input file encoding.")
    add_runtime_arguments(compress_parser)
    add_compression_arguments(compress_parser)
    add_service_client_arguments(compress_parser)
    compress_parser.set_defaults(func=run_compress)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Show a stats-focused compression report for a text file.",
    )
    inspect_parser.add_argument("file", type=Path, help="Text file to inspect.")
    inspect_parser.add_argument("--encoding", default="utf-8", help="Input file encoding.")
    add_runtime_arguments(inspect_parser)
    add_compression_arguments(inspect_parser)
    add_service_client_arguments(inspect_parser)
    inspect_parser.set_defaults(func=run_inspect)

    diff_parser = subparsers.add_parser(
        "diff",
        help="Show kept text with deleted tokens marked inline for trust and demos.",
    )
    diff_parser.add_argument("file", type=Path, help="Text file to diff after compression.")
    diff_parser.add_argument("--encoding", default="utf-8", help="Input file encoding.")
    add_runtime_arguments(diff_parser)
    add_compression_arguments(diff_parser)
    add_service_client_arguments(diff_parser)
    diff_parser.set_defaults(func=run_diff)

    batch_parser = subparsers.add_parser(
        "batch",
        help="Compress many text files from a directory into an output directory.",
    )
    batch_parser.add_argument("directory", type=Path, help="Input directory.")
    batch_parser.add_argument("--glob", default="*.txt", help="Recursive glob pattern, for example *.md.")
    batch_parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    batch_parser.add_argument("--encoding", default="utf-8", help="Input and output file encoding.")
    add_runtime_arguments(batch_parser)
    add_compression_arguments(batch_parser)
    add_service_client_arguments(batch_parser)
    batch_parser.set_defaults(func=run_batch)

    load_parser = subparsers.add_parser(
        "load",
        help="Agent-oriented file loader: read a text file and return compressed context.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Read a UTF-8 text file, compress low-value tokens, and print the shortened text. "
            "This command is intended for coding agents, MCP tools, and prompt pipelines that "
            "need to load large files into limited LLM context windows."
        ),
        epilog=textwrap.dedent(
            """\
            Why agents use this:
              - It keeps the original token order while deleting low-value wording.
              - It reduces prompt/context size before the file is passed to an LLM.
              - It prints only compressed text by default, which is easy for tools to capture.
              - It uses capped golden mode by default, so callers do not need to tune a ratio.
              - Use --json when the caller needs compression stats or token decisions.

            Best fit:
              Natural-language files such as docs, notes, transcripts, issue threads, logs, and research context.
              For source code where exact syntax matters, prefer raw file loading or use a conservative keep ratio.
            """
        ),
    )
    load_parser.add_argument("file", type=Path, help="Text file to load and compress for agent context.")
    load_parser.add_argument("--encoding", default="utf-8", help="Input file encoding.")
    add_runtime_arguments(load_parser)
    add_compression_arguments(load_parser)
    add_service_client_arguments(load_parser)
    load_parser.set_defaults(func=run_load)

    stats_parser = subparsers.add_parser("stats", help="Show local token-savings stats.")
    stats_parser.add_argument("--all", action="store_true", help="Show all history. This is the default.")
    stats_parser.add_argument("--since", default=None, help="Only include events since a window such as 24h, 7d, or 4w.")
    stats_parser.add_argument("--share", action="store_true", help="Print a short shareable summary.")
    stats_parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text report.")
    stats_subparsers = stats_parser.add_subparsers(dest="stats_command")
    stats_reset = stats_subparsers.add_parser("reset", help="Move the stats history to a timestamped backup.")
    stats_reset.set_defaults(func=run_stats_reset)
    stats_parser.set_defaults(func=run_stats)

    service_parser = subparsers.add_parser(
        "service",
        help="Manage a warm background ContextCrumb service.",
        description="Start, inspect, or stop a local contextcrumb serve process.",
    )
    service_subparsers = service_parser.add_subparsers(dest="service_command", required=True)

    service_start = service_subparsers.add_parser("start", help="Start contextcrumb serve in the background.")
    service_start.add_argument("--host", default="127.0.0.1", help="Bind host. Defaults to localhost.")
    service_start.add_argument("--port", type=int, default=8765, help="Bind port.")
    service_start.add_argument("--idle-timeout", type=float, default=3600, help="Seconds of inactivity before exit. Use 0 to disable.")
    service_start.add_argument("--lazy-load", action="store_true", help="Start HTTP server before loading the model.")
    service_start.add_argument("--log-file", type=Path, default=None, help="Optional service log file.")
    service_start.add_argument("--wait-timeout", type=float, default=60, help="Seconds to wait for /health.")
    service_start.add_argument("--json", action="store_true", help="Emit JSON status.")
    add_service_file_read_arguments(service_start)
    add_runtime_arguments(service_start)
    service_start.set_defaults(func=run_service_start)

    service_status = service_subparsers.add_parser("status", help="Show service health.")
    service_status.add_argument("--service-url", default=os.environ.get("CONTEXTCRUMB_SERVICE_URL", DEFAULT_SERVICE_URL), help="ContextCrumb service URL.")
    service_status.add_argument("--json", action="store_true", help="Emit JSON status.")
    service_status.set_defaults(func=run_service_status)

    service_stop = service_subparsers.add_parser("stop", help="Ask the service to shut down.")
    service_stop.add_argument("--service-url", default=os.environ.get("CONTEXTCRUMB_SERVICE_URL", DEFAULT_SERVICE_URL), help="ContextCrumb service URL.")
    service_stop.add_argument("--json", action="store_true", help="Emit JSON status.")
    service_stop.set_defaults(func=run_service_stop)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run a local warm HTTP service for agents, MCP servers, and hooks.",
        description=(
            "Start a localhost HTTP service that loads ContextCrumb once and reuses the warm model "
            "across repeated compression calls."
        ),
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host. Defaults to localhost.")
    serve_parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    serve_parser.add_argument(
        "--idle-timeout",
        type=float,
        default=900,
        help="Seconds of inactivity before the service exits. Use 0 to disable.",
    )
    serve_parser.add_argument(
        "--lazy-load",
        action="store_true",
        help="Start the HTTP server before loading the model. By default the model is loaded at startup.",
    )
    add_service_file_read_arguments(serve_parser)
    add_runtime_arguments(serve_parser)
    serve_parser.set_defaults(func=run_serve)
    return parser


def make_compressor(args: argparse.Namespace) -> ContextCompressor:
    compressor = ContextCompressor(
        model_id=args.model,
        backend=args.backend,
        device=args.device,
        revision=args.revision,
        cache_dir=args.cache_dir,
        max_length=args.max_length,
        stride=args.stride,
        window_batch_size=args.window_batch_size,
    )
    return compressor


def print_result(args: argparse.Namespace, result) -> None:
    if args.json:
        print(json.dumps(result.to_dict(include_tokens=args.return_tokens), ensure_ascii=False, indent=2))
    else:
        print(result.text)


def should_log_stats(args: argparse.Namespace) -> bool:
    return not bool(getattr(args, "no_stats", False))


def log_cli_result(args: argparse.Namespace, result: CompressionResult, command: str, source_path: Path | None = None) -> None:
    log_result(
        result,
        source=str(getattr(args, "stats_source", "cli")),
        command=command,
        source_path=str(source_path) if source_path is not None else None,
        enabled=should_log_stats(args),
    )


def result_from_payload(payload: dict) -> CompressionResult:
    tokens = [
        TokenDecision(
            text=str(token["text"]),
            start=int(token["start"]),
            end=int(token["end"]),
            keep_prob=float(token["keep_prob"]),
            keep=bool(token["keep"]),
        )
        for token in payload.get("tokens", [])
    ]
    return CompressionResult(
        text=str(payload.get("text", "")),
        original_text=str(payload.get("original_text", "")),
        stats=dict(payload.get("stats", {})),
        tokens=tokens,
    )


def service_payload(args: argparse.Namespace, *, text: str | None = None, path: Path | None = None, return_tokens: bool | None = None) -> dict:
    payload: dict[str, object] = {
        "threshold": args.threshold,
        "target_keep_ratio": args.target_keep_ratio,
        "golden": args.golden,
        "golden_min_keep_ratio": args.golden_min_keep_ratio,
        "return_tokens": args.return_tokens if return_tokens is None else return_tokens,
        "no_stats": bool(getattr(args, "no_stats", False)),
    }
    if text is not None:
        payload["text"] = text
    if path is not None:
        payload["path"] = str(path)
        payload["encoding"] = args.encoding
    return payload


def service_request(service_url: str, endpoint: str, payload: dict | None = None, *, method: str = "POST", timeout: float = 30) -> dict:
    url = service_url.rstrip("/") + endpoint
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        if error.code == 400 and "Input file is empty." in body:
            raise SystemExit("Input file is empty.") from error
        raise SystemExit(f"ContextCrumb service returned HTTP {error.code}: {body}") from error
    except URLError as error:
        raise SystemExit(
            f"ContextCrumb service is not reachable at {service_url}. "
            "Run `contextcrumb service start` or omit --use-service."
        ) from error


def service_compress_text(text: str, args: argparse.Namespace, *, return_tokens: bool | None = None) -> CompressionResult:
    payload = service_request(
        args.service_url,
        "/compress",
        service_payload(args, text=text, return_tokens=return_tokens),
    )
    return result_from_payload(payload)


def service_compress_file(path: Path, args: argparse.Namespace, *, return_tokens: bool | None = None) -> CompressionResult:
    payload = service_request(
        args.service_url,
        "/compress_file",
        service_payload(args, path=path, return_tokens=return_tokens),
    )
    return result_from_payload(payload)


def input_file_from_args(args: argparse.Namespace) -> Path | None:
    source = getattr(args, "source", None)
    if source is not None:
        return source
    input_path = getattr(args, "input", None)
    if input_path is not None:
        return input_path
    return None


def compress_file_with_args(
    compressor: ContextCompressor,
    path: Path,
    args: argparse.Namespace,
    *,
    return_tokens: bool | None = None,
) -> CompressionResult:
    return compressor.compress_file(
        path,
        encoding=args.encoding,
        threshold=args.threshold,
        target_keep_ratio=args.target_keep_ratio,
        golden=args.golden,
        golden_min_keep_ratio=args.golden_min_keep_ratio,
        return_tokens=args.return_tokens if return_tokens is None else return_tokens,
    )


def format_inspection(result: CompressionResult) -> str:
    stats = result.stats
    lines = [
        f"Source: {stats.get('source_path', '<text>')}",
        f"Mode: {stats.get('mode')}",
        f"Backend: {stats.get('backend', '<unknown>')}",
        f"Model windows: {stats.get('model_windows', '<unknown>')}",
        f"Chars: {stats.get('original_chars', 0)} -> {stats.get('shortened_chars', 0)} kept ({stats.get('char_keep', 0):.3f})",
        f"Words: {stats.get('original_words', 0)} -> {stats.get('shortened_words', 0)} kept ({stats.get('word_keep', 0):.3f})",
        f"Tokens: {stats.get('input_tokens', 0)} -> {stats.get('kept_tokens', 0)} kept ({stats.get('token_keep_ratio', 0):.3f})",
    ]
    if stats.get("mode") == "golden":
        lines.extend(
            [
                f"Golden cutoff: {stats.get('golden_cutoff', 0):.4f}",
                f"Golden gap: {stats.get('golden_gap', 0):.4f}",
                f"Golden capped: {stats.get('golden_capped', False)}",
            ]
        )
    if stats.get("target_keep_ratio") is not None:
        lines.append(f"Target keep ratio: {stats['target_keep_ratio']}")
    return "\n".join(lines)


def inspection_payload(result: CompressionResult, *, include_tokens: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {"stats": result.stats}
    if include_tokens:
        payload["tokens"] = [token.to_dict() for token in result.tokens]
    return payload


def render_token_diff(original: str, decisions: Sequence[TokenDecision]) -> str:
    if not decisions:
        return original
    parts: list[str] = []
    cursor = 0
    for decision in decisions:
        parts.append(original[cursor : decision.start])
        text = original[decision.start : decision.end]
        parts.append(text if decision.keep else f"[-{text}-]")
        cursor = decision.end
    parts.append(original[cursor:])
    return "".join(parts)


def collect_batch_files(directory: Path, pattern: str, output_dir: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        raise SystemExit(f"Input directory does not exist: {directory}")
    resolved_output = output_dir.resolve()
    files = []
    for path in sorted(directory.rglob(pattern)):
        if not path.is_file():
            continue
        try:
            if path.resolve().is_relative_to(resolved_output):
                continue
        except ValueError:
            pass
        files.append(path)
    return files


def run_compress(args: argparse.Namespace) -> int:
    if args.use_service:
        input_path = input_file_from_args(args)
        if input_path is not None and args.text is None:
            result = service_compress_file(input_path, args)
            print_result(args, result)
            return 0

    text = read_text(args).strip()
    if not text:
        raise SystemExit("No input text provided.")

    if args.use_service:
        result = service_compress_text(text, args)
        print_result(args, result)
        return 0

    compressor = make_compressor(args)
    result = compressor.compress(
        text,
        threshold=args.threshold,
        target_keep_ratio=args.target_keep_ratio,
        golden=args.golden,
        golden_min_keep_ratio=args.golden_min_keep_ratio,
        return_tokens=args.return_tokens,
    )
    log_cli_result(args, result, "compress", input_file_from_args(args))
    print_result(args, result)
    return 0


def run_load(args: argparse.Namespace) -> int:
    if args.use_service:
        result = service_compress_file(args.file, args)
        print_result(args, result)
        return 0
    compressor = make_compressor(args)
    try:
        result = compressor.compress_file(
            args.file,
            encoding=args.encoding,
            threshold=args.threshold,
            target_keep_ratio=args.target_keep_ratio,
            golden=args.golden,
            golden_min_keep_ratio=args.golden_min_keep_ratio,
            return_tokens=args.return_tokens,
        )
    except ValueError as error:
        if str(error) == "Input file is empty.":
            raise SystemExit("Input file is empty.") from error
        raise
    log_cli_result(args, result, "load", args.file)
    print_result(args, result)
    return 0


def run_inspect(args: argparse.Namespace) -> int:
    if args.use_service:
        result = service_compress_file(args.file, args)
    else:
        compressor = make_compressor(args)
        try:
            result = compress_file_with_args(compressor, args.file, args)
        except ValueError as error:
            if str(error) == "Input file is empty.":
                raise SystemExit("Input file is empty.") from error
            raise
    if args.json:
        print(json.dumps(inspection_payload(result, include_tokens=args.return_tokens), ensure_ascii=False, indent=2))
    else:
        print(format_inspection(result))
    return 0


def run_diff(args: argparse.Namespace) -> int:
    if args.use_service:
        result = service_compress_file(args.file, args, return_tokens=True)
    else:
        compressor = make_compressor(args)
        try:
            result = compress_file_with_args(compressor, args.file, args, return_tokens=True)
        except ValueError as error:
            if str(error) == "Input file is empty.":
                raise SystemExit("Input file is empty.") from error
            raise
    if args.json:
        print(json.dumps(result.to_dict(include_tokens=True), ensure_ascii=False, indent=2))
    else:
        print(render_token_diff(result.original_text, result.tokens))
    return 0


def run_batch(args: argparse.Namespace) -> int:
    files = collect_batch_files(args.directory, args.glob, args.out)
    if not files:
        raise SystemExit(f"No files matched {args.glob!r} under {args.directory}.")
    compressor = None if args.use_service else make_compressor(args)
    args.out.mkdir(parents=True, exist_ok=True)
    summaries = []
    for source_path in files:
        try:
            result = service_compress_file(source_path, args) if args.use_service else compress_file_with_args(compressor, source_path, args)
        except (ValueError, SystemExit) as error:
            if isinstance(error, ValueError) and str(error) == "Input file is empty.":
                continue
            if isinstance(error, SystemExit) and str(error) == "Input file is empty.":
                continue
            raise
        relative_path = source_path.relative_to(args.directory)
        output_path = args.out / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.text, encoding=args.encoding)
        if not args.use_service:
            log_cli_result(args, result, "batch", source_path)
        summaries.append(
            {
                "source": str(source_path),
                "output": str(output_path),
                "stats": result.stats,
            }
        )
    if args.json:
        print(json.dumps({"files": summaries}, ensure_ascii=False, indent=2))
    else:
        for item in summaries:
            stats = item["stats"]
            print(
                f"{item['source']} -> {item['output']} "
                f"tokens {stats.get('input_tokens', 0)}->{stats.get('kept_tokens', 0)} "
                f"({stats.get('token_keep_ratio', 0):.3f})"
            )
        print(f"Compressed {len(summaries)} file(s).")
    return 0


def run_stats(args: argparse.Namespace) -> int:
    try:
        since_ms = parse_since(args.since)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    aggregate = aggregate_events(read_events(), since_ms=since_ms)
    if args.json:
        print(json.dumps(aggregate.to_dict(), ensure_ascii=False, indent=2))
    elif args.share:
        print(format_share_stats(aggregate))
    else:
        print(format_human_stats(aggregate))
    return 0


def run_stats_reset(args: argparse.Namespace) -> int:
    backup_path = reset_stats()
    if backup_path is None:
        print("No ContextCrumb stats history found.")
    else:
        print(f"Moved ContextCrumb stats history to {backup_path}.")
    return 0


def run_serve(args: argparse.Namespace) -> int:
    from contextcrumb.service import run_service

    idle_timeout = None if args.idle_timeout <= 0 else args.idle_timeout
    return run_service(
        host=args.host,
        port=args.port,
        idle_timeout=idle_timeout,
        lazy_load=args.lazy_load,
        model_id=args.model,
        backend=args.backend,
        device=args.device,
        revision=args.revision,
        cache_dir=args.cache_dir,
        max_length=args.max_length,
        stride=args.stride,
        window_batch_size=args.window_batch_size,
        file_reads_enabled=not args.disable_file_reads,
        allowed_file_roots=args.allow_root,
    )


def service_url_from_host_port(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def default_service_log_file() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "contextcrumb"
    root.mkdir(parents=True, exist_ok=True)
    return root / "service.log"


def wait_for_service(service_url: str, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return service_request(service_url, "/health", method="GET", timeout=2)
        except SystemExit as error:
            last_error = error
            time.sleep(0.5)
    raise SystemExit(f"ContextCrumb service did not become ready at {service_url}: {last_error}")


def run_service_start(args: argparse.Namespace) -> int:
    service_url = service_url_from_host_port(args.host, args.port)
    try:
        health = service_request(service_url, "/health", method="GET", timeout=2)
        if args.json:
            print(json.dumps({"already_running": True, "service_url": service_url, "health": health}, indent=2))
        else:
            print(f"ContextCrumb service is already running at {service_url}.")
        return 0
    except SystemExit:
        pass

    log_file = args.log_file or default_service_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "contextcrumb",
        "serve",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--idle-timeout",
        str(args.idle_timeout),
        "--model",
        str(args.model),
        "--backend",
        args.backend,
        "--device",
        args.device,
        "--max-length",
        str(args.max_length),
        "--stride",
        str(args.stride),
    ]
    if args.window_batch_size is not None:
        command.extend(["--window-batch-size", str(args.window_batch_size)])
    if args.revision is not None:
        command.extend(["--revision", args.revision])
    if args.cache_dir is not None:
        command.extend(["--cache-dir", str(args.cache_dir)])
    if args.lazy_load:
        command.append("--lazy-load")
    if args.disable_file_reads:
        command.append("--disable-file-reads")
    for allowed_root in args.allow_root or []:
        command.extend(["--allow-root", str(allowed_root)])

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    with log_file.open("ab") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    health = wait_for_service(service_url, args.wait_timeout)
    payload = {"started": True, "pid": process.pid, "service_url": service_url, "log_file": str(log_file), "health": health}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Started ContextCrumb service at {service_url} (pid {process.pid}).")
        print(f"Log: {log_file}")
    return 0


def run_service_status(args: argparse.Namespace) -> int:
    health = service_request(args.service_url, "/health", method="GET", timeout=5)
    if args.json:
        print(json.dumps(health, indent=2))
    else:
        print(f"ContextCrumb service: {args.service_url}")
        print(f"Model loaded: {health.get('model_loaded')}")
        print(f"Backend: {health.get('backend')}")
        print(f"File reads enabled: {health.get('file_reads_enabled')}")
        allowed_roots = health.get("allowed_file_roots") or []
        if allowed_roots:
            print(f"Allowed file roots: {', '.join(str(root) for root in allowed_roots)}")
        print(f"Idle seconds: {health.get('idle_seconds', 0):.1f}")
        print(f"Idle timeout: {health.get('idle_timeout')}")
    return 0


def run_service_stop(args: argparse.Namespace) -> int:
    payload = service_request(args.service_url, "/shutdown", payload={}, timeout=5)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Stopped ContextCrumb service at {args.service_url}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
