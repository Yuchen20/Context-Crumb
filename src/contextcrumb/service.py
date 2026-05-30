"""Local warm HTTP service for ContextCrumb."""

import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from contextcrumb.compressor import (
    DEFAULT_BACKEND,
    DEFAULT_GOLDEN_MIN_KEEP_RATIO,
    DEFAULT_MAX_LENGTH,
    DEFAULT_MODEL_ID,
    DEFAULT_STRIDE,
    DEFAULT_THRESHOLD,
    ContextCompressor,
)
from contextcrumb.file_policy import classify_file_for_compression
from contextcrumb.stats import log_result


class ContextCrumbService:
    """Owns one warm compressor instance and optional idle shutdown timer."""

    def __init__(
        self,
        *,
        model_id: str | Path = DEFAULT_MODEL_ID,
        backend: str = DEFAULT_BACKEND,
        device: str = "auto",
        revision: str | None = None,
        cache_dir: str | Path | None = None,
        max_length: int = DEFAULT_MAX_LENGTH,
        stride: int = DEFAULT_STRIDE,
        window_batch_size: int | None = None,
        idle_timeout: float | None = 900,
        file_reads_enabled: bool = True,
        allowed_file_roots: Sequence[str | Path] | None = None,
        compressor_factory: Callable[..., ContextCompressor] = ContextCompressor,
    ) -> None:
        self.model_id = str(model_id)
        self.backend = backend
        self.device = device
        self.revision = revision
        self.cache_dir = cache_dir
        self.max_length = max_length
        self.stride = stride
        self.window_batch_size = window_batch_size
        self.idle_timeout = idle_timeout
        self.file_reads_enabled = bool(file_reads_enabled)
        self.allowed_file_roots = self._normalize_file_roots(allowed_file_roots)
        self.compressor_factory = compressor_factory
        self.created_at = time.time()
        self.last_activity_at = self.created_at
        self._compressor: ContextCompressor | None = None
        self._lock = threading.Lock()
        self._idle_timer: threading.Timer | None = None
        self._server: Any | None = None

    def attach_server(self, server: Any) -> None:
        self._server = server
        self.touch()

    def load(self) -> ContextCompressor:
        with self._lock:
            if self._compressor is None:
                self._compressor = self.compressor_factory(
                    model_id=self.model_id,
                    backend=self.backend,
                    device=self.device,
                    revision=self.revision,
                    cache_dir=self.cache_dir,
                    max_length=self.max_length,
                    stride=self.stride,
                    window_batch_size=self.window_batch_size,
                )
            self.last_activity_at = time.time()
            self._schedule_idle_shutdown_locked()
            return self._compressor

    def touch(self) -> None:
        with self._lock:
            self.last_activity_at = time.time()
            self._schedule_idle_shutdown_locked()

    def status(self) -> dict[str, Any]:
        now = time.time()
        return {
            "ok": True,
            "model_loaded": self._compressor is not None,
            "model_id": self.model_id,
            "backend": self.backend,
            "device": self.device,
            "max_length": self.max_length,
            "stride": self.stride,
            "window_batch_size": self.window_batch_size,
            "idle_timeout": self.idle_timeout,
            "file_reads_enabled": self.file_reads_enabled,
            "allowed_file_roots": [str(root) for root in self.allowed_file_roots],
            "uptime_seconds": now - self.created_at,
            "idle_seconds": now - self.last_activity_at,
        }

    def resolve_allowed_file_path(self, path: str | Path) -> Path:
        if not self.file_reads_enabled:
            raise PermissionError("Local file reads are disabled.")
        resolved_path = Path(path).expanduser().resolve()
        if not self._is_path_allowed(resolved_path):
            roots = ", ".join(str(root) for root in self.allowed_file_roots) or "<none>"
            raise PermissionError(f"File path is outside allowed roots: {roots}")
        return resolved_path

    def shutdown(self) -> None:
        with self._lock:
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None
            if self._server is not None:
                self._server.should_exit = True

    def _schedule_idle_shutdown_locked(self) -> None:
        if self.idle_timeout is None or self.idle_timeout <= 0 or self._server is None:
            return
        if self._idle_timer is not None:
            self._idle_timer.cancel()
        self._idle_timer = threading.Timer(self.idle_timeout, self._request_idle_shutdown)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _request_idle_shutdown(self) -> None:
        with self._lock:
            if self.idle_timeout is None or self._server is None:
                return
            if time.time() - self.last_activity_at >= self.idle_timeout:
                self._server.should_exit = True

    @staticmethod
    def _normalize_file_roots(allowed_file_roots: Sequence[str | Path] | None) -> tuple[Path, ...]:
        roots = allowed_file_roots if allowed_file_roots is not None else (Path.cwd(),)
        return tuple(Path(root).expanduser().resolve() for root in roots)

    def _is_path_allowed(self, path: Path) -> bool:
        return any(path == root or path.is_relative_to(root) for root in self.allowed_file_roots)


def create_app(service: ContextCrumbService):
    """Create the FastAPI app without importing FastAPI at package import time."""
    try:
        from fastapi import Body, FastAPI, HTTPException
        from pydantic import BaseModel, ConfigDict, Field
    except ImportError as error:  # pragma: no cover - exercised by users without [serve]
        raise RuntimeError(
            "contextcrumb serve requires FastAPI and Uvicorn. Install with `pip install contextcrumb[serve]`."
        ) from error

    class CompressRequest(BaseModel):
        model_config = ConfigDict(protected_namespaces=())

        text: str
        threshold: float = DEFAULT_THRESHOLD
        target_keep_ratio: float | None = None
        golden: bool = True
        golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO
        return_tokens: bool = False
        no_stats: bool = False

    class CompressFileRequest(BaseModel):
        model_config = ConfigDict(protected_namespaces=())

        path: str = Field(description="Local text file path on the machine running contextcrumb serve.")
        encoding: str = "utf-8"
        threshold: float = DEFAULT_THRESHOLD
        target_keep_ratio: float | None = None
        golden: bool = True
        golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO
        return_tokens: bool = False
        no_stats: bool = False
        force: bool = False

    app = FastAPI(
        title="ContextCrumb Local Service",
        version="0.1.0",
        description="Local warm ContextCrumb service for agents, MCP servers, hooks, and prompt pipelines.",
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return service.status()

    @app.post("/compress")
    def compress(request: CompressRequest = Body(...)) -> dict[str, Any]:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="No input text provided.")
        compressor = service.load()
        result = compressor.compress(
            request.text,
            threshold=request.threshold,
            target_keep_ratio=request.target_keep_ratio,
            golden=request.golden,
            golden_min_keep_ratio=request.golden_min_keep_ratio,
            return_tokens=request.return_tokens,
        )
        log_result(result, source="service", command="compress", enabled=not request.no_stats)
        return result.to_dict(include_tokens=request.return_tokens)

    @app.post("/compress_file")
    def compress_file(request: CompressFileRequest = Body(...)) -> dict[str, Any]:
        try:
            path = service.resolve_allowed_file_path(request.path)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {request.path}")
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {request.path}")
        policy = classify_file_for_compression(path)
        if policy.force_required and not request.force:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Refusing to compress syntax-sensitive file type. "
                    f"Reason: {policy.reason} Use force=true only for exploratory compression."
                ),
            )
        try:
            compressor = service.load()
            result = compressor.compress_file(
                path,
                encoding=request.encoding,
                threshold=request.threshold,
                target_keep_ratio=request.target_keep_ratio,
                golden=request.golden,
                golden_min_keep_ratio=request.golden_min_keep_ratio,
                return_tokens=request.return_tokens,
            )
            result.stats.update(
                {
                    "file_policy_status": policy.status,
                    "file_policy_reason": policy.reason,
                    "raw_read_required": policy.raw_read_required,
                }
            )
            log_result(
                result,
                source="service",
                command="compress_file",
                source_path=str(path),
                enabled=not request.no_stats,
            )
        except ValueError as error:
            if str(error) == "Input file is empty.":
                raise HTTPException(status_code=400, detail="Input file is empty.") from error
            raise
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=400, detail=f"Could not decode file with {request.encoding}.") from error
        return result.to_dict(include_tokens=request.return_tokens)

    @app.post("/shutdown")
    def shutdown() -> dict[str, Any]:
        service.shutdown()
        return {"ok": True, "shutting_down": True}

    return app


def run_service(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    idle_timeout: float | None = 900,
    lazy_load: bool = False,
    model_id: str | Path = DEFAULT_MODEL_ID,
    backend: str = DEFAULT_BACKEND,
    device: str = "auto",
    revision: str | None = None,
    cache_dir: str | Path | None = None,
    max_length: int = DEFAULT_MAX_LENGTH,
    stride: int = DEFAULT_STRIDE,
    window_batch_size: int | None = None,
    file_reads_enabled: bool = True,
    allowed_file_roots: Sequence[str | Path] | None = None,
) -> int:
    """Run the local service with Uvicorn."""
    try:
        import uvicorn
    except ImportError as error:  # pragma: no cover - exercised by users without [serve]
        raise RuntimeError(
            "contextcrumb serve requires Uvicorn. Install with `pip install contextcrumb[serve]`."
        ) from error

    service = ContextCrumbService(
        model_id=model_id,
        backend=backend,
        device=device,
        revision=revision,
        cache_dir=cache_dir,
        max_length=max_length,
        stride=stride,
        window_batch_size=window_batch_size,
        idle_timeout=idle_timeout,
        file_reads_enabled=file_reads_enabled,
        allowed_file_roots=allowed_file_roots,
    )
    if not lazy_load:
        service.load()
    app = create_app(service)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    service.attach_server(server)
    server.run()
    service.shutdown()
    return 0
