"""File-type safety policy for agent-facing compression."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


SAFE_PROSE_EXTENSIONS = {
    ".adoc",
    ".log",
    ".markdown",
    ".md",
    ".mdx",
    ".org",
    ".rst",
    ".srt",
    ".text",
    ".txt",
    ".vtt",
}

UNSAFE_EXACT_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".conf",
    ".config",
    ".cs",
    ".css",
    ".csv",
    ".diff",
    ".env",
    ".go",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsonl",
    ".jsx",
    ".lock",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".svelte",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

UNSAFE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "dockerfile",
    "gemfile",
    "makefile",
    "package-lock.json",
    "pipfile",
    "poetry.lock",
    "requirements.txt",
    "uv.lock",
    "yarn.lock",
}


@dataclass(frozen=True)
class FilePolicyDecision:
    status: str
    reason: str
    raw_read_required: bool
    force_required: bool

    def to_dict(self) -> dict[str, bool | str]:
        return asdict(self)


def classify_file_for_compression(path: str | Path) -> FilePolicyDecision:
    source_path = Path(path)
    name = source_path.name.lower()
    suffix = source_path.suffix.lower()

    if name in UNSAFE_FILENAMES or suffix in UNSAFE_EXACT_EXTENSIONS:
        return FilePolicyDecision(
            status="unsafe",
            reason="Exact syntax, structure, or command text may matter for this file type.",
            raw_read_required=True,
            force_required=True,
        )
    if suffix in SAFE_PROSE_EXTENSIONS:
        return FilePolicyDecision(
            status="safe",
            reason="Prose-oriented file type.",
            raw_read_required=False,
            force_required=False,
        )
    return FilePolicyDecision(
        status="unknown",
        reason="Unknown file type; verify the compressed output before relying on it.",
        raw_read_required=True,
        force_required=False,
    )

