"""Public compression API for ContextCrumb."""

from __future__ import annotations

import math
import json
import inspect
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from contextcrumb.backends import aggregate_word_keep_probabilities

DEFAULT_MODEL_ID = "ymao20/contextcrumb-32m"
DEFAULT_MAX_LENGTH = 1024
DEFAULT_STRIDE = 64
DEFAULT_THRESHOLD = 0.5
DEFAULT_BACKEND = "onnx"
DEFAULT_GOLDEN_MIN_KEEP_RATIO = 1.0 / 3.0


@dataclass(frozen=True)
class TokenDecision:
    """A token-level keep/delete decision."""

    text: str
    start: int
    end: int
    keep_prob: float
    keep: bool

    def to_dict(self) -> dict[str, bool | float | int | str]:
        return asdict(self)


@dataclass(frozen=True)
class CompressionResult:
    """Compressed text plus statistics and optional token decisions."""

    text: str
    original_text: str
    stats: dict[str, bool | float | int | str | None]
    tokens: list[TokenDecision] = field(default_factory=list)

    def to_dict(self, include_tokens: bool | None = None) -> dict[str, Any]:
        if include_tokens is None:
            include_tokens = bool(self.tokens)

        payload: dict[str, Any] = {
            "text": self.text,
            "original_text": self.original_text,
            "stats": self.stats,
        }
        if include_tokens:
            payload["tokens"] = [token.to_dict() for token in self.tokens]
        return payload


def validate_keep_ratio(target_keep_ratio: float | None) -> None:
    if target_keep_ratio is None:
        return
    if not 0.0 <= target_keep_ratio <= 1.0:
        raise ValueError("target_keep_ratio must be between 0.0 and 1.0")


@dataclass(frozen=True)
class GoldenCutoff:
    """Adaptive cutoff selected from the largest keep-probability gap."""

    cutoff: float
    gap: float
    keep_ratio: float
    keep_count: int
    basis_count: int
    min_keep_ratio: float
    capped: bool


def is_word_like_token(token_text: str) -> bool:
    return any(char.isalnum() for char in token_text)


def compute_golden_cutoff(
    tokens,
    keep_probabilities: Sequence[float],
    *,
    min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
) -> GoldenCutoff:
    """Find a natural cutoff from the largest adjacent gap among word-like tokens."""
    validate_keep_ratio(min_keep_ratio)
    basis_probabilities = [
        float(keep_prob)
        for token, keep_prob in zip(tokens, keep_probabilities)
        if is_word_like_token(token.text)
    ]
    if len(basis_probabilities) < 2:
        keep_count = sum(1 for keep_prob in basis_probabilities if keep_prob >= DEFAULT_THRESHOLD)
        min_keep_count = int(math.ceil(len(basis_probabilities) * min_keep_ratio))
        capped = keep_count < min_keep_count
        keep_count = max(keep_count, min_keep_count)
        cutoff = min(basis_probabilities) if capped and basis_probabilities else DEFAULT_THRESHOLD
        return GoldenCutoff(
            cutoff=float(cutoff),
            gap=0.0,
            keep_ratio=(keep_count / len(basis_probabilities)) if basis_probabilities else 0.0,
            keep_count=keep_count,
            basis_count=len(basis_probabilities),
            min_keep_ratio=float(min_keep_ratio),
            capped=capped,
        )

    ordered = sorted(basis_probabilities, reverse=True)
    gap_index = max(range(len(ordered) - 1), key=lambda index: ordered[index] - ordered[index + 1])
    gap = ordered[gap_index] - ordered[gap_index + 1]
    natural_keep_count = gap_index + 1
    min_keep_count = int(math.ceil(len(ordered) * min_keep_ratio))
    keep_count = max(natural_keep_count, min_keep_count)
    capped = keep_count != natural_keep_count
    if capped:
        cutoff = ordered[keep_count - 1]
    else:
        cutoff = (ordered[gap_index] + ordered[gap_index + 1]) / 2
    return GoldenCutoff(
        cutoff=float(cutoff),
        gap=float(gap),
        keep_ratio=keep_count / len(ordered),
        keep_count=keep_count,
        basis_count=len(ordered),
        min_keep_ratio=float(min_keep_ratio),
        capped=capped,
    )


def build_token_decisions(
    tokens,
    keep_probabilities: Sequence[float],
    threshold: float,
    target_keep_ratio: float | None,
) -> list[TokenDecision]:
    validate_keep_ratio(target_keep_ratio)

    keep_indexes: set[int] | None = None
    if target_keep_ratio is not None:
        keep_count = int(math.floor((len(tokens) * target_keep_ratio) + 0.5))
        keep_count = max(0, min(len(tokens), keep_count))
        keep_indexes = set(
            sorted(range(len(tokens)), key=lambda index: (-keep_probabilities[index], index))[:keep_count]
        )

    decisions: list[TokenDecision] = []
    for index, (token, keep_prob) in enumerate(zip(tokens, keep_probabilities)):
        keep = index in keep_indexes if keep_indexes is not None else keep_prob >= threshold
        decisions.append(
            TokenDecision(
                text=token.text,
                start=int(token.start),
                end=int(token.end),
                keep_prob=float(keep_prob),
                keep=bool(keep),
            )
        )
    return decisions


def build_compressed_text(original: str, decisions: Sequence[TokenDecision]) -> str:
    from contextcrumb.spans import TextToken, minimal_original_separator

    output_parts: list[str] = []
    previous_match: TextToken | None = None

    for decision in decisions:
        if not decision.keep:
            continue

        token = TextToken(decision.text, decision.start, decision.end)
        if previous_match is not None:
            output_parts.append(minimal_original_separator(original, previous_match, token))
        output_parts.append(original[token.start : token.end])
        previous_match = token

    return "".join(output_parts).strip()


class ContextCompressor:
    """Load ContextCrumb-32M and compress text by deleting low-value tokens.

    By default, this loads the private Hugging Face model
    ``ymao20/contextcrumb-32m`` into the local Hugging Face cache. Pass a local
    model folder or another Hub id as ``model_id`` to override it.

    Example:
        ```python
        from contextcrumb import ContextCompressor

        compressor = ContextCompressor()
        result = compressor.compress("Long context goes here.")
        print(result.text)
        ```
    """

    def __init__(
        self,
        model_id: str | Path = DEFAULT_MODEL_ID,
        *,
        device: str = "auto",
        backend: str = DEFAULT_BACKEND,
        revision: str | None = None,
        cache_dir: str | Path | None = None,
        max_length: int = DEFAULT_MAX_LENGTH,
        stride: int = DEFAULT_STRIDE,
        window_batch_size: int | None = None,
        trust_remote_code: bool = False,
        _tokenizer: Any | None = None,
        _model: Any | None = None,
        _device: Any | None = None,
    ) -> None:
        if max_length <= 0:
            raise ValueError("max_length must be positive")
        if stride < 0:
            raise ValueError("stride must be non-negative")
        if stride >= max_length:
            raise ValueError("stride must be smaller than max_length")
        if window_batch_size is not None and window_batch_size <= 0:
            raise ValueError("window_batch_size must be positive")

        from contextcrumb.backends import TorchBackend, load_backend

        if _tokenizer is None or _model is None:
            self._backend_runner = load_backend(
                backend_name=backend,
                model_id=model_id,
                device=device,
                revision=revision,
                cache_dir=cache_dir,
                trust_remote_code=trust_remote_code,
            )
        else:
            from contextcrumb.backends import choose_torch_device
            resolved_device = _device if _device is not None else choose_torch_device(device)
            component_model = _model
            if hasattr(component_model, "to"):
                component_model = component_model.to(resolved_device)
            if hasattr(component_model, "eval"):
                component_model.eval()
            self._backend_runner = TorchBackend(
                tokenizer=_tokenizer,
                model=component_model,
                device=resolved_device,
            )
            backend = "torch"

        self.model_id = str(model_id)
        self.backend = backend
        self.tokenizer = self._backend_runner.tokenizer
        self.model = self._backend_runner.model
        self.device = self._backend_runner.device
        self.max_length = int(max_length)
        self.stride = int(stride)
        self.window_batch_size = window_batch_size
        self.keep_label_id = self._backend_runner.keep_label_id

    @classmethod
    def from_pretrained(
        cls,
        model_id: str | Path = DEFAULT_MODEL_ID,
        *,
        device: str = "auto",
        backend: str = DEFAULT_BACKEND,
        revision: str | None = None,
        cache_dir: str | Path | None = None,
        max_length: int = DEFAULT_MAX_LENGTH,
        stride: int = DEFAULT_STRIDE,
        window_batch_size: int | None = None,
        trust_remote_code: bool = False,
    ) -> "ContextCompressor":
        """Compatibility constructor for users familiar with Hugging Face APIs."""
        return cls(
            model_id=model_id,
            device=device,
            backend=backend,
            revision=revision,
            cache_dir=cache_dir,
            max_length=max_length,
            stride=stride,
            window_batch_size=window_batch_size,
            trust_remote_code=trust_remote_code,
        )

    @classmethod
    def from_components(
        cls,
        tokenizer: Any,
        model: Any,
        *,
        device: str = "auto",
        max_length: int = DEFAULT_MAX_LENGTH,
        stride: int = DEFAULT_STRIDE,
        window_batch_size: int | None = None,
    ) -> "ContextCompressor":
        """Build a compressor from already-loaded tokenizer/model objects."""
        return cls(
            device=device,
            backend="torch",
            max_length=max_length,
            stride=stride,
            window_batch_size=window_batch_size,
            _tokenizer=tokenizer,
            _model=model,
        )

    def score_keep_probabilities(self, text: str) -> tuple[list[Any], list[float], int]:
        return self._backend_runner.score_keep_probabilities(
            text,
            max_length=self.max_length,
            stride=self.stride,
            window_batch_size=self.window_batch_size,
        )

    def compress(
        self,
        text: str,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        target_keep_ratio: float | None = None,
        golden: bool = True,
        golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
        return_tokens: bool = False,
    ) -> CompressionResult:
        """Compress text by keeping high-value tokens in their original order.

        Args:
            text: Input text to compress.
            threshold: Keep tokens with ``KEEP`` probability at or above this
                value when ``target_keep_ratio`` is not provided.
            target_keep_ratio: Optional token ratio. When set, ContextCrumb
                keeps the top-scoring tokens up to this ratio. This overrides
                threshold mode.
            golden: Deprecated compatibility flag. It is recorded in stats but
                no longer changes compression behavior.
            golden_min_keep_ratio: Deprecated compatibility value recorded in
                stats. The legacy adaptive golden cutoff is no longer used by
                default compression.
            return_tokens: Include token-level decisions in the result.

        Returns:
            A ``CompressionResult`` containing compressed text, statistics, and
            optional token decisions.
        """
        from contextcrumb.spans import compression_stats

        validate_keep_ratio(target_keep_ratio)
        validate_keep_ratio(golden_min_keep_ratio)
        tokens, keep_probabilities, window_count = self.score_keep_probabilities(text)
        mode = "target_keep_ratio" if target_keep_ratio is not None else "threshold"
        decision_threshold = float(threshold)

        decisions = build_token_decisions(tokens, keep_probabilities, decision_threshold, target_keep_ratio)
        compressed = build_compressed_text(text, decisions)
        stats = compression_stats(text, compressed)
        kept_tokens = sum(1 for decision in decisions if decision.keep)
        stats_update: dict[str, bool | float | int | str | None] = {
            "input_tokens": len(decisions),
            "kept_tokens": kept_tokens,
            "deleted_tokens": len(decisions) - kept_tokens,
            "token_keep_ratio": kept_tokens / len(decisions) if decisions else 0.0,
            "mode": mode,
            "threshold": decision_threshold,
            "requested_threshold": float(threshold),
            "target_keep_ratio": target_keep_ratio,
            "requested_golden": bool(golden),
            "requested_golden_min_keep_ratio": float(golden_min_keep_ratio),
            "max_length": self.max_length,
            "stride": self.stride,
            "model_windows": window_count,
            "model_id": getattr(self, "model_id", None),
            "backend": self.backend,
            "window_batch_size": self.window_batch_size,
        }
        stats.update(stats_update)
        return CompressionResult(
            text=compressed,
            original_text=text,
            stats=stats,
            tokens=decisions if return_tokens else [],
        )

    def compress_file(
        self,
        path: str | Path,
        *,
        encoding: str = "utf-8",
        threshold: float | None = DEFAULT_THRESHOLD,
        target_keep_ratio: float | None = None,
        golden: bool = True,
        golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
        return_tokens: bool = False,
        content_mode: str | None = None,
        config: Any | None = None,
    ) -> CompressionResult:
        """Read a text file and compress it for use as LLM or agent context.

        This is a convenience wrapper around :meth:`compress` for coding agents,
        MCP tools, and CLIs that want to load local text files without manually
        handling file I/O.
        """
        source_path = Path(path)
        text = source_path.read_text(encoding=encoding)
        if not text.strip():
            raise ValueError("Input file is empty.")
        from contextcrumb.code_compression import (
            compress_code_comments,
            detect_code_language,
            is_supported_code_file,
            raw_file_result,
        )
        from contextcrumb.config import CONTENT_MODES, resolve_config
        from contextcrumb.file_policy import classify_file_for_compression

        resolved_config = config or resolve_config(start=source_path)
        mode = content_mode or resolved_config.compression.content_mode
        if mode not in CONTENT_MODES:
            raise ValueError(f"content_mode must be one of: {', '.join(CONTENT_MODES)}")
        resolved_threshold = DEFAULT_THRESHOLD if threshold is None else float(threshold)
        resolved_target_keep_ratio = (
            target_keep_ratio
            if target_keep_ratio is not None
            else resolved_config.compression.target_keep_ratio
        )

        if mode == "raw":
            return raw_file_result(text, path=source_path, encoding=encoding, content_mode="raw")
        if mode == "refuse":
            raise ValueError(f"Refusing to compress file because content_mode=refuse: {source_path}")
        if mode == "code-comments":
            if not is_supported_code_file(source_path, resolved_config.code):
                raise ValueError(f"Code-aware compression does not support this file type: {source_path}")
            return compress_code_comments(
                self,
                text,
                path=source_path,
                encoding=encoding,
                config=resolved_config.code,
                threshold=resolved_threshold,
                target_keep_ratio=resolved_target_keep_ratio,
                golden=golden,
                golden_min_keep_ratio=golden_min_keep_ratio,
            )
        if mode == "auto":
            if is_supported_code_file(source_path, resolved_config.code):
                return compress_code_comments(
                    self,
                    text,
                    path=source_path,
                    encoding=encoding,
                    config=resolved_config.code,
                    threshold=resolved_threshold,
                    target_keep_ratio=resolved_target_keep_ratio,
                    golden=golden,
                    golden_min_keep_ratio=golden_min_keep_ratio,
                )
            policy = classify_file_for_compression(source_path)
            if policy.force_required:
                if resolved_config.code.unsupported_code == "raw":
                    return raw_file_result(text, path=source_path, encoding=encoding, content_mode="raw")
                if resolved_config.code.unsupported_code == "prose":
                    mode = "prose"
                else:
                    language = detect_code_language(source_path) or "unknown"
                    raise ValueError(f"Unsupported syntax-sensitive file for code-aware compression: {language}")
        result = self.compress(
            text,
            threshold=resolved_threshold,
            target_keep_ratio=resolved_target_keep_ratio,
            golden=golden,
            golden_min_keep_ratio=golden_min_keep_ratio,
            return_tokens=return_tokens,
        )
        result.stats.update(
            {
                "content_mode": "prose" if mode == "prose" else "auto",
                "compressed_span_count": 0,
                "preserved_code_exact": False,
                "source_path": str(source_path),
                "source_encoding": encoding,
            }
        )
        return result


def compress(
    text: str,
    *,
    model_id: str | Path = DEFAULT_MODEL_ID,
    device: str = "auto",
    backend: str = DEFAULT_BACKEND,
    revision: str | None = None,
    cache_dir: str | Path | None = None,
    max_length: int = DEFAULT_MAX_LENGTH,
    stride: int = DEFAULT_STRIDE,
    window_batch_size: int | None = None,
    trust_remote_code: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
    target_keep_ratio: float | None = None,
    golden: bool = True,
    golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
    return_tokens: bool = False,
) -> CompressionResult:
    """Load a compressor and compress one text string."""
    compressor = ContextCompressor(
        model_id=model_id,
        device=device,
        backend=backend,
        revision=revision,
        cache_dir=cache_dir,
        max_length=max_length,
        stride=stride,
        window_batch_size=window_batch_size,
        trust_remote_code=trust_remote_code,
    )
    return compressor.compress(
        text,
        threshold=threshold,
        target_keep_ratio=target_keep_ratio,
        golden=golden,
        golden_min_keep_ratio=golden_min_keep_ratio,
        return_tokens=return_tokens,
    )


def compress_file(
    path: str | Path,
    *,
    encoding: str = "utf-8",
    model_id: str | Path = DEFAULT_MODEL_ID,
    device: str = "auto",
    backend: str = DEFAULT_BACKEND,
    revision: str | None = None,
    cache_dir: str | Path | None = None,
    max_length: int = DEFAULT_MAX_LENGTH,
    stride: int = DEFAULT_STRIDE,
    window_batch_size: int | None = None,
    trust_remote_code: bool = False,
    threshold: float | None = DEFAULT_THRESHOLD,
    target_keep_ratio: float | None = None,
    golden: bool = True,
    golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
    return_tokens: bool = False,
    content_mode: str | None = None,
    config: Any | None = None,
) -> CompressionResult:
    """Load a compressor, read a file, and compress its text."""
    compressor = ContextCompressor(
        model_id=model_id,
        device=device,
        backend=backend,
        revision=revision,
        cache_dir=cache_dir,
        max_length=max_length,
        stride=stride,
        window_batch_size=window_batch_size,
        trust_remote_code=trust_remote_code,
    )
    return compressor.compress_file(
        path,
        encoding=encoding,
        threshold=threshold,
        target_keep_ratio=target_keep_ratio,
        golden=golden,
        golden_min_keep_ratio=golden_min_keep_ratio,
        return_tokens=return_tokens,
        content_mode=content_mode,
        config=config,
    )
