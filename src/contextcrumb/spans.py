"""Text token spans and deletion-only reconstruction helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN_PATTERN = re.compile(r"\s+|[\w]+(?:['’][\w]+)*|[^\w\s]", re.UNICODE)
WORD_PATTERN = re.compile(r"[\w]+(?:['’][\w]+)*", re.UNICODE)


@dataclass(frozen=True)
class TextToken:
    """A non-whitespace token and its character span in the original text."""

    text: str
    start: int
    end: int


def tokenize_with_spans(text: str) -> list[TextToken]:
    """Split text into non-whitespace tokens with original character spans."""
    return [
        TextToken(match.group(0), match.start(), match.end())
        for match in TOKEN_PATTERN.finditer(text)
        if not match.group(0).isspace()
    ]


def needs_separator(previous: TextToken, current: TextToken) -> bool:
    current_is_word = bool(WORD_PATTERN.fullmatch(current.text))
    previous_is_word = bool(WORD_PATTERN.fullmatch(previous.text))
    return bool(
        current_is_word
        and (previous_is_word or previous.text in {".", ",", ";", ":", "?", "!", "\"", "'"})
    )


def minimal_original_separator(original: str, previous: TextToken, current: TextToken) -> str:
    """Return at most one original whitespace character needed between kept tokens."""
    if not needs_separator(previous, current):
        return ""

    gap = original[previous.end : current.start]
    match = re.search(r"\s+", gap)
    return match.group(0)[:1] if match else ""


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def compression_stats(original: str, shortened: str) -> dict[str, float | int]:
    """Character and whitespace-delimited word compression statistics."""
    original_chars = len(original)
    shortened_chars = len(shortened)
    original_words = count_words(original)
    shortened_words = count_words(shortened)

    char_keep = shortened_chars / original_chars if original_chars else 0.0
    word_keep = shortened_words / original_words if original_words else 0.0

    return {
        "original_chars": original_chars,
        "shortened_chars": shortened_chars,
        "char_keep": char_keep,
        "char_removed": 1.0 - char_keep,
        "original_words": original_words,
        "shortened_words": shortened_words,
        "word_keep": word_keep,
        "word_removed": 1.0 - word_keep,
    }
