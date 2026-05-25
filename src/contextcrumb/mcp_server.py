"""MCP stdio server for ContextCrumb."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from contextcrumb.cli import result_from_payload, service_request
from contextcrumb.compressor import (
    DEFAULT_GOLDEN_MIN_KEEP_RATIO,
    DEFAULT_MAX_LENGTH,
    DEFAULT_MODEL_ID,
    DEFAULT_STRIDE,
    DEFAULT_THRESHOLD,
    ContextCompressor,
)
from contextcrumb.mcp_types import CompressionOptions, McpServerConfig
from contextcrumb.stats import log_result


class ContextCrumbMcpRuntime:
    """Lazy runtime behind the MCP tools."""

    def __init__(
        self,
        config: McpServerConfig,
        *,
        compressor_factory: Callable[..., ContextCompressor] = ContextCompressor,
        service_request_func: Callable[..., dict[str, Any]] = service_request,
    ) -> None:
        self.config = config
        self.compressor_factory = compressor_factory
        self.service_request = service_request_func
        self._compressor: ContextCompressor | None = None
        self._lock = threading.Lock()

    @property
    def model_loaded(self) -> bool:
        return self._compressor is not None

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

    def compress_text(
        self,
        text: str,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        target_keep_ratio: float | None = None,
        golden: bool = True,
        golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
        return_tokens: bool = False,
    ) -> dict[str, Any]:
        """Compress inline text and return a structured result."""
        if not text.strip():
            raise ValueError("No input text provided.")
        options = CompressionOptions(
            threshold=threshold,
            target_keep_ratio=target_keep_ratio,
            golden=golden,
            golden_min_keep_ratio=golden_min_keep_ratio,
            return_tokens=return_tokens,
        )
        if self.config.use_service:
            payload = self._service_payload(options, text=text)
            response = self._service_request("/compress", payload)
            return result_from_payload(response).to_dict(include_tokens=return_tokens)
        compressor = self._get_compressor()
        result = compressor.compress(
            text,
            threshold=options.threshold,
            target_keep_ratio=options.target_keep_ratio,
            golden=options.golden,
            golden_min_keep_ratio=options.golden_min_keep_ratio,
            return_tokens=options.return_tokens,
        )
        log_result(result, source="mcp", command="mcp.compress_text")
        return result.to_dict(include_tokens=return_tokens)

    def compress_file(
        self,
        path: str,
        *,
        encoding: str = "utf-8",
        threshold: float = DEFAULT_THRESHOLD,
        target_keep_ratio: float | None = None,
        golden: bool = True,
        golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
        return_tokens: bool = False,
    ) -> dict[str, Any]:
        """Read and compress a local text file on the MCP server machine."""
        source_path = Path(path)
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not source_path.is_file():
            raise ValueError(f"Not a file: {path}")
        options = CompressionOptions(
            threshold=threshold,
            target_keep_ratio=target_keep_ratio,
            golden=golden,
            golden_min_keep_ratio=golden_min_keep_ratio,
            return_tokens=return_tokens,
        )
        if self.config.use_service:
            payload = self._service_payload(options, path=source_path, encoding=encoding)
            response = self._service_request("/compress_file", payload)
            return result_from_payload(response).to_dict(include_tokens=return_tokens)
        compressor = self._get_compressor()
        result = compressor.compress_file(
            source_path,
            encoding=encoding,
            threshold=options.threshold,
            target_keep_ratio=options.target_keep_ratio,
            golden=options.golden,
            golden_min_keep_ratio=options.golden_min_keep_ratio,
            return_tokens=options.return_tokens,
        )
        log_result(result, source="mcp", command="mcp.compress_file", source_path=str(source_path))
        return result.to_dict(include_tokens=return_tokens)

    @staticmethod
    def _service_payload(
        options: CompressionOptions,
        *,
        text: str | None = None,
        path: Path | None = None,
        encoding: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "threshold": options.threshold,
            "target_keep_ratio": options.target_keep_ratio,
            "golden": options.golden,
            "golden_min_keep_ratio": options.golden_min_keep_ratio,
            "return_tokens": options.return_tokens,
        }
        if text is not None:
            payload["text"] = text
        if path is not None:
            payload["path"] = str(path)
        if encoding is not None:
            payload["encoding"] = encoding
        return payload

    def _service_request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.service_request(self.config.service_url, endpoint, payload)
        except SystemExit as error:
            raise RuntimeError(str(error)) from error


def _load_fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:  # pragma: no cover - exercised in environments without [mcp]
        raise RuntimeError(
            "contextcrumb-mcp requires the MCP optional dependencies. "
            "Install with `pip install contextcrumb[mcp]` or run with "
            "`uvx --from contextcrumb[mcp] contextcrumb-mcp`."
        ) from error
    return FastMCP


def build_mcp_server(
    config: McpServerConfig,
    *,
    runtime: ContextCrumbMcpRuntime | None = None,
):
    """Build the FastMCP server without loading the compression model."""
    FastMCP = _load_fastmcp()
    mcp = FastMCP("ContextCrumb", json_response=True)
    runtime = runtime or ContextCrumbMcpRuntime(config)

    @mcp.tool()
    def compress_text(
        text: str,
        threshold: float = DEFAULT_THRESHOLD,
        target_keep_ratio: float | None = None,
        golden: bool = True,
        golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
        return_tokens: bool = False,
    ) -> dict[str, Any]:
        """Compress inline text for LLM or agent context."""
        return runtime.compress_text(
            text,
            threshold=threshold,
            target_keep_ratio=target_keep_ratio,
            golden=golden,
            golden_min_keep_ratio=golden_min_keep_ratio,
            return_tokens=return_tokens,
        )

    @mcp.tool()
    def compress_file(
        path: str,
        encoding: str = "utf-8",
        threshold: float = DEFAULT_THRESHOLD,
        target_keep_ratio: float | None = None,
        golden: bool = True,
        golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
        return_tokens: bool = False,
    ) -> dict[str, Any]:
        """Read and compress a local text file for LLM or agent context."""
        return runtime.compress_file(
            path,
            encoding=encoding,
            threshold=threshold,
            target_keep_ratio=target_keep_ratio,
            golden=golden,
            golden_min_keep_ratio=golden_min_keep_ratio,
            return_tokens=return_tokens,
        )

    return mcp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextcrumb-mcp",
        description="Run the ContextCrumb MCP stdio server.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL_ID, help="Hugging Face model id or local model path.")
    parser.add_argument("--backend", choices=["onnx", "torch"], default="onnx", help="Inference backend.")
    parser.add_argument("--device", default="auto", help="Inference device: auto, cpu, cuda, etc.")
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH, help="Model max sequence length.")
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE, help="Sliding-window overlap.")
    parser.add_argument("--window-batch-size", type=int, default=None, help="Maximum number of sliding windows per model call.")
    parser.add_argument("--revision", default=None, help="Optional Hugging Face revision.")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Optional Hugging Face cache directory.")
    parser.add_argument("--use-service", action="store_true", help="Use a warm contextcrumb service instead of loading the model in this process.")
    parser.add_argument("--service-url", default="http://127.0.0.1:8765", help="ContextCrumb service URL.")
    return parser


def config_from_args(args: argparse.Namespace) -> McpServerConfig:
    return McpServerConfig(
        model_id=args.model,
        backend=args.backend,
        device=args.device,
        revision=args.revision,
        cache_dir=args.cache_dir,
        max_length=args.max_length,
        stride=args.stride,
        window_batch_size=args.window_batch_size,
        use_service=args.use_service,
        service_url=args.service_url,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        mcp = build_mcp_server(config_from_args(args))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    mcp.run()
    return 0


def benchmark_runtime(runtime: ContextCrumbMcpRuntime, text: str) -> dict[str, float]:
    """Measure adapter-level cold and warm tool-call latency."""
    start = time.perf_counter()
    runtime.compress_text(text)
    cold_seconds = time.perf_counter() - start
    start = time.perf_counter()
    runtime.compress_text(text)
    warm_seconds = time.perf_counter() - start
    return {"cold_seconds": cold_seconds, "warm_seconds": warm_seconds}


if __name__ == "__main__":
    raise SystemExit(main())
