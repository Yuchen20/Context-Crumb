"""Types shared by the ContextCrumb MCP adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from contextcrumb.compressor import (
    DEFAULT_BACKEND,
    DEFAULT_GOLDEN_MIN_KEEP_RATIO,
    DEFAULT_MAX_LENGTH,
    DEFAULT_MODEL_ID,
    DEFAULT_STRIDE,
    DEFAULT_THRESHOLD,
)


@dataclass(frozen=True)
class McpServerConfig:
    """Runtime configuration for the ContextCrumb MCP server."""

    model_id: str | Path = DEFAULT_MODEL_ID
    backend: str = DEFAULT_BACKEND
    device: str = "auto"
    revision: str | None = None
    cache_dir: str | Path | None = None
    max_length: int = DEFAULT_MAX_LENGTH
    stride: int = DEFAULT_STRIDE
    window_batch_size: int | None = None
    use_service: bool = False
    service_url: str = "http://127.0.0.1:8765"


@dataclass(frozen=True)
class CompressionOptions:
    """Per-call compression options exposed through MCP tools."""

    threshold: float = DEFAULT_THRESHOLD
    target_keep_ratio: float | None = None
    golden: bool = True
    golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO
    return_tokens: bool = False
