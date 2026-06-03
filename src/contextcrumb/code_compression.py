"""Code-aware compression helpers."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from contextcrumb.compressor import (
    DEFAULT_GOLDEN_MIN_KEEP_RATIO,
    DEFAULT_THRESHOLD,
    CompressionResult,
)
from contextcrumb.config import CodeConfig
from contextcrumb.spans import compression_stats


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
}


@dataclass(frozen=True)
class CompressibleCodeSpan:
    start: int
    end: int
    kind: str


def detect_code_language(path: str | Path) -> str | None:
    return LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower())


def is_supported_code_file(path: str | Path, config: CodeConfig) -> bool:
    language = detect_code_language(path)
    return language is not None and language in set(config.languages)


def parser_available_for_language(language: str) -> bool:
    """Return whether tree-sitter can parse this language in the current env."""
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        return False
    parser_language = "javascript" if language == "jsx" else language
    parser_language = "typescript" if language == "tsx" else parser_language
    try:
        parser = get_parser(parser_language)
        parser.parse(b"")
    except Exception:
        return False
    return True


def compress_code_comments(
    compressor: Any,
    text: str,
    *,
    path: str | Path,
    encoding: str = "utf-8",
    config: CodeConfig,
    threshold: float = DEFAULT_THRESHOLD,
    target_keep_ratio: float | None = None,
    golden: bool = True,
    golden_min_keep_ratio: float = DEFAULT_GOLDEN_MIN_KEEP_RATIO,
) -> CompressionResult:
    language = detect_code_language(path) or "unknown"
    spans = extract_compressible_spans(text, language)
    output = rebuild_with_compressed_spans(
        compressor,
        text,
        spans,
        config=config,
        threshold=threshold,
        fallback_target_keep_ratio=target_keep_ratio,
        golden=golden,
        golden_min_keep_ratio=golden_min_keep_ratio,
    )
    stats = compression_stats(text, output)
    stats.update(
        {
            "input_tokens": 0,
            "kept_tokens": 0,
            "deleted_tokens": 0,
            "token_keep_ratio": 1.0,
            "mode": "code-comments",
            "content_mode": "code-comments",
            "code_language": language,
            "compressed_span_count": len(spans),
            "preserved_code_exact": True,
            "tree_sitter_available": parser_available_for_language(language),
            "source_path": str(path),
            "source_encoding": encoding,
        }
    )
    return CompressionResult(text=output, original_text=text, stats=stats)


def raw_file_result(text: str, *, path: str | Path, encoding: str, content_mode: str = "raw") -> CompressionResult:
    stats = compression_stats(text, text)
    stats.update(
        {
            "input_tokens": 0,
            "kept_tokens": 0,
            "deleted_tokens": 0,
            "token_keep_ratio": 1.0,
            "mode": "raw",
            "content_mode": content_mode,
            "compressed_span_count": 0,
            "preserved_code_exact": True,
            "source_path": str(path),
            "source_encoding": encoding,
        }
    )
    return CompressionResult(text=text, original_text=text, stats=stats)


def rebuild_with_compressed_spans(
    compressor: Any,
    text: str,
    spans: list[CompressibleCodeSpan],
    *,
    config: CodeConfig,
    threshold: float,
    fallback_target_keep_ratio: float | None,
    golden: bool,
    golden_min_keep_ratio: float,
) -> str:
    if not spans:
        return text
    output: list[str] = []
    cursor = 0
    for span in merge_spans(spans):
        output.append(text[cursor : span.start])
        body = text[span.start : span.end]
        output.append(
            compress_span_body(
                compressor,
                body,
                span.kind,
                config=config,
                threshold=threshold,
                fallback_target_keep_ratio=fallback_target_keep_ratio,
                golden=golden,
                golden_min_keep_ratio=golden_min_keep_ratio,
            )
        )
        cursor = span.end
    output.append(text[cursor:])
    return "".join(output)


def compress_span_body(
    compressor: Any,
    body: str,
    kind: str,
    *,
    config: CodeConfig,
    threshold: float,
    fallback_target_keep_ratio: float | None,
    golden: bool,
    golden_min_keep_ratio: float,
) -> str:
    if not body.strip():
        return body
    match = re.match(r"^(\s*)(.*?)(\s*)$", body, re.DOTALL)
    if match is None:
        return body
    leading, core, trailing = match.groups()
    if not core.strip():
        return body
    target_keep_ratio = (
        config.docstring_target_keep_ratio
        if kind == "docstring"
        else config.comment_target_keep_ratio
    )
    if target_keep_ratio is None:
        target_keep_ratio = fallback_target_keep_ratio
    result = compressor.compress(
        core,
        threshold=threshold,
        target_keep_ratio=target_keep_ratio,
        golden=golden,
        golden_min_keep_ratio=golden_min_keep_ratio,
        return_tokens=False,
    )
    return leading + result.text + trailing


def merge_spans(spans: Iterable[CompressibleCodeSpan]) -> list[CompressibleCodeSpan]:
    ordered = sorted(spans, key=lambda item: (item.start, item.end))
    merged: list[CompressibleCodeSpan] = []
    for span in ordered:
        if span.start >= span.end:
            continue
        if merged and span.start < merged[-1].end:
            continue
        merged.append(span)
    return merged


def extract_compressible_spans(text: str, language: str) -> list[CompressibleCodeSpan]:
    if language == "python":
        return sorted(
            [*extract_python_comment_spans(text), *extract_python_docstring_spans(text)],
            key=lambda item: (item.start, item.end),
        )
    if language in {"javascript", "typescript", "jsx", "tsx", "go", "rust"}:
        return extract_c_family_comment_spans(text)
    return []


def extract_python_comment_spans(text: str) -> list[CompressibleCodeSpan]:
    line_offsets = compute_line_offsets(text)
    spans: list[CompressibleCodeSpan] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    except tokenize.TokenError:
        return spans
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        line, column = token.start
        start = line_offsets[line - 1] + column
        comment = token.string
        body_offset = 1
        if len(comment) > 1 and comment[1:2].isspace():
            body_offset = 2
        spans.append(CompressibleCodeSpan(start + body_offset, start + len(comment), "comment"))
    return spans


def extract_python_docstring_spans(text: str) -> list[CompressibleCodeSpan]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    line_offsets = compute_line_offsets(text)
    spans: list[CompressibleCodeSpan] = []
    for node in iter_docstring_expr_nodes(tree):
        if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
            continue
        start = line_offsets[node.lineno - 1] + node.col_offset
        end = line_offsets[node.end_lineno - 1] + node.end_col_offset
        literal = text[start:end]
        body = string_literal_body_span(literal)
        if body is None:
            continue
        body_start, body_end = body
        spans.append(CompressibleCodeSpan(start + body_start, start + body_end, "docstring"))
    return spans


def iter_docstring_expr_nodes(tree: ast.AST) -> Iterable[ast.Expr]:
    candidates: list[ast.AST] = [tree]
    candidates.extend(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    for owner in candidates:
        body = getattr(owner, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
            if isinstance(first.value.value, str):
                yield first


def string_literal_body_span(literal: str) -> tuple[int, int] | None:
    match = re.match(r"(?is)^[rubf]*('''|\"\"\"|'|\")", literal)
    if match is None:
        return None
    quote = match.group(1)
    start = match.end()
    if not literal.endswith(quote):
        return None
    return start, len(literal) - len(quote)


def extract_c_family_comment_spans(text: str) -> list[CompressibleCodeSpan]:
    spans: list[CompressibleCodeSpan] = []
    index = 0
    in_string: str | None = None
    escaped = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            in_string = char
            index += 1
            continue
        if char == "/" and next_char == "/":
            start = index + 2
            if start < len(text) and text[start : start + 1].isspace():
                start += 1
            end = text.find("\n", index)
            if end == -1:
                end = len(text)
            spans.append(CompressibleCodeSpan(start, end, "comment"))
            index = end
            continue
        if char == "/" and next_char == "*":
            start = index + 2
            if start < len(text) and text[start : start + 1].isspace():
                start += 1
            end_marker = text.find("*/", start)
            if end_marker == -1:
                break
            body_end = end_marker
            if body_end > start and text[body_end - 1 : body_end].isspace():
                body_end -= 1
            spans.append(CompressibleCodeSpan(start, body_end, "docstring"))
            index = end_marker + 2
            continue
        index += 1
    return spans


def compute_line_offsets(text: str) -> list[int]:
    offsets = [0]
    for match in re.finditer("\n", text):
        offsets.append(match.end())
    return offsets
