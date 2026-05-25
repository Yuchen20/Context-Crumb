"""Model-backed MCP stdio proxy that shrinks catalog descriptions."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterable, Sequence

from contextcrumb.cli import result_from_payload, service_request
from contextcrumb.compressor import (
    DEFAULT_BACKEND,
    DEFAULT_GOLDEN_MIN_KEEP_RATIO,
    DEFAULT_MAX_LENGTH,
    DEFAULT_MODEL_ID,
    DEFAULT_STRIDE,
    DEFAULT_THRESHOLD,
    ContextCompressor,
)
from contextcrumb.stats import log_result

DEFAULT_SERVICE_URL = "http://127.0.0.1:8765"
DEFAULT_FIELDS = ("description",)
CATALOG_KEYS = ("tools", "prompts", "resources", "resourceTemplates")

PROTECTED_PATTERNS = [
    re.compile(r"```.*?```", re.DOTALL),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"https?://[^\s)\]}>,]+"),
    re.compile(r"\b[A-Za-z]:[\\/][^\s`\"')\]}>,]+"),
    re.compile(r"(?<!\w)/(?:[^\s`\"')\]}>,/]+/)+[^\s`\"')\]}>,]*"),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\([^()\n]*\)"),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b"),
    re.compile(r"\b[A-Za-z]+_[A-Za-z0-9_]+\b"),
    re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b"),
    re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b"),
    re.compile(r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9]*\b"),
    re.compile(r"\bv?\d+(?:\.\d+)+(?:[-+][A-Za-z0-9_.-]+)?\b"),
    re.compile(r"\{[^{}\n]*:[^{}\n]*\}"),
]


@dataclass(frozen=True)
class ShrinkProxyConfig:
    upstream_command: tuple[str, ...]
    fields: tuple[str, ...] = DEFAULT_FIELDS
    debug: bool = False
    use_service: bool = False
    service_url: str = DEFAULT_SERVICE_URL
    model_id: str | Path = DEFAULT_MODEL_ID
    backend: str = DEFAULT_BACKEND
    device: str = "auto"
    revision: str | None = None
    cache_dir: str | Path | None = None
    max_length: int = DEFAULT_MAX_LENGTH
    stride: int = DEFAULT_STRIDE
    window_batch_size: int | None = None
    threshold: float = DEFAULT_THRESHOLD
    target_keep_ratio: float | None = 0.5
    golden: bool = True
    golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO
    stats_enabled: bool = True


@dataclass
class CatalogShrinkStats:
    fields_seen: int = 0
    fields_compressed: int = 0
    input_chars: int = 0
    output_chars: int = 0
    input_tokens: int = 0
    kept_tokens: int = 0


class ContextCrumbShrinkRuntime:
    """Compress catalog text with a local model or warm ContextCrumb service."""

    def __init__(
        self,
        config: ShrinkProxyConfig | None = None,
        *,
        compressor_factory: Callable[..., ContextCompressor] = ContextCompressor,
        service_request_func: Callable[..., dict[str, Any]] = service_request,
        use_service: bool | None = None,
    ) -> None:
        if config is None:
            config = ShrinkProxyConfig(upstream_command=())
        if use_service is not None:
            config = ShrinkProxyConfig(**{**config.__dict__, "use_service": use_service})
        self.config = config
        self.compressor_factory = compressor_factory
        self.service_request = service_request_func
        self._compressor: ContextCompressor | None = None
        self._lock = threading.Lock()

    def shrink_text(self, text: str) -> str:
        if not text.strip():
            return text
        return "".join(self._shrink_segments(text))

    def _shrink_segments(self, text: str) -> Iterable[str]:
        cursor = 0
        for start, end in protected_spans(text):
            if start > cursor:
                yield self._shrink_unprotected_segment(text[cursor:start])
            yield text[start:end]
            cursor = end
        if cursor < len(text):
            yield self._shrink_unprotected_segment(text[cursor:])

    def _shrink_unprotected_segment(self, segment: str) -> str:
        if not segment.strip():
            return segment
        match = re.match(r"^(\s*)(.*?)(\s*)$", segment, re.DOTALL)
        if match is None:
            return segment
        leading, core, trailing = match.groups()
        if not core.strip():
            return segment
        compressed = self._compress_core(core)
        if not compressed.strip():
            return segment
        return leading + compressed.strip() + trailing

    def _compress_core(self, text: str) -> str:
        if self.config.use_service:
            payload = {
                "text": text,
                "threshold": self.config.threshold,
                "target_keep_ratio": self.config.target_keep_ratio,
                "golden": self.config.golden,
                "golden_min_keep_ratio": self.config.golden_min_keep_ratio,
                "return_tokens": False,
            }
            response = self.service_request(self.config.service_url, "/compress", payload)
            return result_from_payload(response).text

        compressor = self._get_compressor()
        return compressor.compress(
            text,
            threshold=self.config.threshold,
            target_keep_ratio=self.config.target_keep_ratio,
            golden=self.config.golden,
            golden_min_keep_ratio=self.config.golden_min_keep_ratio,
            return_tokens=False,
        ).text

    def compress_for_stats(self, text: str):
        if self.config.use_service:
            payload = {
                "text": text,
                "threshold": self.config.threshold,
                "target_keep_ratio": self.config.target_keep_ratio,
                "golden": self.config.golden,
                "golden_min_keep_ratio": self.config.golden_min_keep_ratio,
                "return_tokens": False,
            }
            return result_from_payload(self.service_request(self.config.service_url, "/compress", payload))
        compressor = self._get_compressor()
        return compressor.compress(
            text,
            threshold=self.config.threshold,
            target_keep_ratio=self.config.target_keep_ratio,
            golden=self.config.golden,
            golden_min_keep_ratio=self.config.golden_min_keep_ratio,
            return_tokens=False,
        )

    def _get_compressor(self) -> ContextCompressor:
        with self._lock:
            if self._compressor is None:
                self._compressor = self.compressor_factory(
                    model_id=self.config.model_id,
                    backend=self.config.backend,
                    device=self.config.device,
                    revision=self.config.revision,
                    cache_dir=self.config.cache_dir,
                    max_length=self.config.max_length,
                    stride=self.config.stride,
                    window_batch_size=self.config.window_batch_size,
                )
            return self._compressor


def protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in PROTECTED_PATTERNS:
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    if not spans:
        return []
    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def transform_message(
    message: dict[str, Any],
    runtime: ContextCrumbShrinkRuntime,
    *,
    fields: Sequence[str] = DEFAULT_FIELDS,
    stats: CatalogShrinkStats | None = None,
) -> dict[str, Any]:
    result = message.get("result")
    if not isinstance(result, dict):
        return message
    if not any(isinstance(result.get(key), list) for key in CATALOG_KEYS):
        return message

    transformed = copy.deepcopy(message)
    transformed_result = transformed["result"]
    for catalog_key in CATALOG_KEYS:
        items = transformed_result.get(catalog_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for field in fields:
                value = item.get(field)
                if not isinstance(value, str) or not value.strip():
                    continue
                if stats is not None:
                    stats.fields_seen += 1
                    stats.input_chars += len(value)
                compressed = runtime.shrink_text(value)
                if compressed and compressed != value:
                    item[field] = compressed
                    if stats is not None:
                        stats.fields_compressed += 1
                        stats.output_chars += len(compressed)
                elif stats is not None:
                    stats.output_chars += len(value)
    return transformed


def encode_content_length_message(message: dict[str, Any]) -> bytes:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def encode_newline_message(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def decode_message(raw: bytes) -> dict[str, Any]:
    if raw.startswith(b"Content-Length:"):
        header, body = raw.split(b"\r\n\r\n", 1) if b"\r\n\r\n" in raw else raw.split(b"\n\n", 1)
        length = None
        for line in header.decode("ascii", errors="replace").splitlines():
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise ValueError("Missing Content-Length header")
        return json.loads(body[:length].decode("utf-8"))
    return json.loads(raw.decode("utf-8"))


def _read_content_length_message(stream: BinaryIO, first_line: bytes) -> bytes:
    headers = [first_line]
    while True:
        line = stream.readline()
        if line == b"":
            return b"".join(headers)
        headers.append(line)
        if line in {b"\r\n", b"\n"}:
            break
    length = None
    for header in headers:
        if header.lower().startswith(b"content-length:"):
            length = int(header.split(b":", 1)[1].strip())
            break
    if length is None:
        return b"".join(headers)
    return b"".join(headers) + stream.read(length)


def iter_stdio_messages(stream: BinaryIO) -> Iterable[tuple[bytes, str]]:
    while True:
        line = stream.readline()
        if line == b"":
            break
        if line.lower().startswith(b"content-length:"):
            yield _read_content_length_message(stream, line), "content-length"
        else:
            yield line, "newline"


def transform_raw_message(
    raw: bytes,
    framing: str,
    runtime: ContextCrumbShrinkRuntime,
    config: ShrinkProxyConfig,
    stats: CatalogShrinkStats,
) -> bytes:
    try:
        message = decode_message(raw)
    except Exception as error:
        if config.debug:
            print(f"contextcrumb-shrink: passing through unparseable message: {error}", file=sys.stderr)
        return raw
    if not isinstance(message, dict):
        return raw
    transformed = transform_message(message, runtime, fields=config.fields, stats=stats)
    if transformed is message:
        return raw
    return encode_content_length_message(transformed) if framing == "content-length" else encode_newline_message(transformed)


def _copy_client_to_upstream(client_stdin: BinaryIO, upstream_stdin: BinaryIO) -> None:
    try:
        while True:
            read_chunk = getattr(client_stdin, "read1", client_stdin.read)
            chunk = read_chunk(8192)
            if not chunk:
                break
            upstream_stdin.write(chunk)
            upstream_stdin.flush()
    finally:
        try:
            upstream_stdin.close()
        except OSError:
            pass


def _copy_stderr(upstream_stderr: BinaryIO) -> None:
    for chunk in iter(lambda: upstream_stderr.read(8192), b""):
        sys.stderr.buffer.write(chunk)
        sys.stderr.buffer.flush()


def run_proxy(
    config: ShrinkProxyConfig,
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    compressor_factory: Callable[..., ContextCompressor] = ContextCompressor,
) -> int:
    if not config.upstream_command:
        raise ValueError("upstream command is required")
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    runtime = ContextCrumbShrinkRuntime(config, compressor_factory=compressor_factory)
    stats = CatalogShrinkStats()
    process = subprocess.Popen(
        list(config.upstream_command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    input_thread = threading.Thread(target=_copy_client_to_upstream, args=(stdin, process.stdin), daemon=True)
    stderr_thread = threading.Thread(target=_copy_stderr, args=(process.stderr,), daemon=True)
    input_thread.start()
    stderr_thread.start()
    for raw, framing in iter_stdio_messages(process.stdout):
        transformed = transform_raw_message(raw, framing, runtime, config, stats)
        stdout.write(transformed)
        stdout.flush()
    input_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    exit_code = process.wait()
    if config.debug:
        print(
            "contextcrumb-shrink: "
            f"compressed {stats.fields_compressed}/{stats.fields_seen} field(s), "
            f"chars {stats.input_chars}->{stats.output_chars}",
            file=sys.stderr,
        )
    if config.stats_enabled and stats.fields_seen:
        fake_result = type(
            "CatalogStatsResult",
            (),
            {
                "stats": {
                    "input_tokens": stats.input_tokens or max(stats.input_chars // 4, 0),
                    "kept_tokens": stats.kept_tokens or max(stats.output_chars // 4, 0),
                    "deleted_tokens": max((stats.input_chars - stats.output_chars) // 4, 0),
                    "token_keep_ratio": stats.output_chars / stats.input_chars if stats.input_chars else 0.0,
                    "mode": "service" if config.use_service else "model",
                    "model_id": str(config.model_id),
                    "backend": config.backend,
                }
            },
        )()
        log_result(fake_result, source="mcp-shrink", command="catalog", enabled=True)
    return int(exit_code or 0)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _fields_from_text(text: str | None) -> tuple[str, ...]:
    if not text:
        return DEFAULT_FIELDS
    fields = tuple(field.strip() for field in text.split(",") if field.strip())
    return fields or DEFAULT_FIELDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextcrumb-shrink",
        description="Wrap an upstream MCP stdio server and shrink catalog descriptions with ContextCrumb.",
    )
    parser.add_argument("--debug", action="store_true", default=_env_bool("CONTEXTCRUMB_SHRINK_DEBUG"))
    parser.add_argument(
        "--fields",
        default=os.environ.get("CONTEXTCRUMB_SHRINK_FIELDS", ",".join(DEFAULT_FIELDS)),
        help="Comma-separated top-level catalog fields to compress.",
    )
    parser.add_argument(
        "--mode",
        choices=["model", "service"],
        default=os.environ.get("CONTEXTCRUMB_SHRINK_MODE", "model"),
        help="Use an in-process model or a running ContextCrumb service.",
    )
    parser.add_argument(
        "--service-url",
        default=os.environ.get("CONTEXTCRUMB_SHRINK_SERVICE_URL", DEFAULT_SERVICE_URL),
        help="ContextCrumb service URL for --mode service.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL_ID, help="Hugging Face model id or local model path.")
    parser.add_argument("--backend", choices=["onnx", "torch"], default=DEFAULT_BACKEND, help="Inference backend.")
    parser.add_argument("--device", default="auto", help="Inference device: auto, cpu, cuda, etc.")
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH, help="Model max sequence length.")
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE, help="Sliding-window overlap.")
    parser.add_argument("--window-batch-size", type=int, default=None, help="Maximum sliding windows per model call.")
    parser.add_argument("--revision", default=None, help="Optional Hugging Face revision.")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Optional Hugging Face cache directory.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Keep probability threshold.")
    parser.add_argument(
        "--target-keep-ratio",
        type=float,
        default=float(os.environ.get("CONTEXTCRUMB_SHRINK_TARGET_KEEP_RATIO", "0.5")),
        help="Default model keep ratio for catalog prose.",
    )
    parser.add_argument("--no-golden", dest="golden", action="store_false", default=True)
    parser.add_argument("--golden-min-keep-ratio", type=float, default=DEFAULT_GOLDEN_MIN_KEEP_RATIO)
    parser.add_argument(
        "upstream_command",
        nargs=argparse.REMAINDER,
        metavar="upstream-command",
        help="Upstream MCP server command and arguments.",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> ShrinkProxyConfig:
    upstream_command = tuple(args.upstream_command)
    if upstream_command and upstream_command[0] == "--":
        upstream_command = upstream_command[1:]
    return ShrinkProxyConfig(
        upstream_command=upstream_command,
        fields=_fields_from_text(args.fields),
        debug=bool(args.debug),
        use_service=args.mode == "service",
        service_url=args.service_url,
        model_id=args.model,
        backend=args.backend,
        device=args.device,
        revision=args.revision,
        cache_dir=args.cache_dir,
        max_length=args.max_length,
        stride=args.stride,
        window_batch_size=args.window_batch_size,
        threshold=args.threshold,
        target_keep_ratio=args.target_keep_ratio,
        golden=args.golden,
        golden_min_keep_ratio=args.golden_min_keep_ratio,
        stats_enabled=_env_bool("CONTEXTCRUMB_SHRINK_STATS", True),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = config_from_args(args)
    if not config.upstream_command:
        parser.print_usage(sys.stderr)
        print("contextcrumb-shrink: error: upstream-command is required", file=sys.stderr)
        return 2
    try:
        return run_proxy(config)
    except FileNotFoundError as error:
        print(f"contextcrumb-shrink: upstream command not found: {error.filename}", file=sys.stderr)
        return 127
    except RuntimeError as error:
        print(f"contextcrumb-shrink: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
