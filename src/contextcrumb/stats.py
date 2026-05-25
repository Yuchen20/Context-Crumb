"""Append-only token savings ledger for ContextCrumb."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STATS_VERSION = 1


@dataclass(frozen=True)
class StatsAggregate:
    runs: int
    input_tokens: int
    kept_tokens: int
    tokens_saved: int
    files_compressed: int
    best_source: str | None
    best_saved_tokens: int

    @property
    def average_keep_ratio(self) -> float:
        if self.input_tokens <= 0:
            return 0.0
        return self.kept_tokens / self.input_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "input_tokens": self.input_tokens,
            "kept_tokens": self.kept_tokens,
            "tokens_saved": self.tokens_saved,
            "average_keep_ratio": self.average_keep_ratio,
            "files_compressed": self.files_compressed,
            "best_source": self.best_source,
            "best_saved_tokens": self.best_saved_tokens,
        }


def default_stats_path() -> Path:
    override = os.environ.get("CONTEXTCRUMB_STATS_FILE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "contextcrumb" / "stats.jsonl"


def stats_enabled() -> bool:
    return os.environ.get("CONTEXTCRUMB_STATS", "1").strip().lower() not in {"0", "false", "no", "off"}


def redact_source_path(source_path: str | None) -> str | None:
    if not source_path:
        return None
    mode = os.environ.get("CONTEXTCRUMB_STATS_PATH_MODE", "basename").strip().lower()
    if mode == "full":
        return source_path
    if mode == "none":
        return None
    if mode == "hash":
        return hashlib.sha256(source_path.encode("utf-8")).hexdigest()
    return Path(source_path).name


def parse_since(value: str | None, *, now_ms: int | None = None) -> int | None:
    if value is None:
        return None
    text = value.strip().lower()
    if not text:
        raise ValueError("--since must not be empty")
    multiplier_by_suffix = {
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
        "w": 7 * 24 * 60 * 60 * 1000,
    }
    suffix = text[-1]
    if suffix not in multiplier_by_suffix:
        raise ValueError("--since must use h, d, or w, for example 24h or 7d")
    try:
        amount = float(text[:-1])
    except ValueError as error:
        raise ValueError("--since must use a numeric value, for example 24h or 7d") from error
    if amount < 0:
        raise ValueError("--since must be non-negative")
    now = int(time.time() * 1000) if now_ms is None else now_ms
    return int(now - (amount * multiplier_by_suffix[suffix]))


def build_event(
    stats: dict[str, Any],
    *,
    source: str,
    command: str,
    source_path: str | None = None,
    agent: str | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
    ts: int | None = None,
) -> dict[str, Any]:
    input_tokens = int(stats.get("input_tokens") or 0)
    kept_tokens = int(stats.get("kept_tokens") or 0)
    deleted_tokens = int(stats.get("deleted_tokens") or max(input_tokens - kept_tokens, 0))
    event = {
        "version": STATS_VERSION,
        "ts": int(time.time() * 1000) if ts is None else int(ts),
        "run_id": run_id or str(uuid.uuid4()),
        "source": source,
        "command": command,
        "source_path": redact_source_path(source_path or stats.get("source_path")),
        "input_tokens": input_tokens,
        "kept_tokens": kept_tokens,
        "deleted_tokens": deleted_tokens,
        "token_keep_ratio": float(stats.get("token_keep_ratio") or (kept_tokens / input_tokens if input_tokens else 0.0)),
        "mode": stats.get("mode"),
        "model_id": stats.get("model_id"),
        "backend": stats.get("backend"),
        "agent": agent,
        "session_id": session_id,
    }
    return event


def append_event(event: dict[str, Any], *, path: Path | None = None) -> None:
    stats_path = path or default_stats_path()
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    with stats_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def log_result(
    result: Any,
    *,
    source: str,
    command: str,
    source_path: str | None = None,
    agent: str | None = None,
    session_id: str | None = None,
    enabled: bool = True,
) -> None:
    if not enabled or not stats_enabled():
        return
    stats = getattr(result, "stats", None)
    if not isinstance(stats, dict):
        return
    append_event(
        build_event(
            stats,
            source=source,
            command=command,
            source_path=source_path,
            agent=agent,
            session_id=session_id,
        )
    )


def read_events(*, path: Path | None = None) -> list[dict[str, Any]]:
    stats_path = path or default_stats_path()
    if not stats_path.exists():
        return []
    events: list[dict[str, Any]] = []
    with stats_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def aggregate_events(events: Iterable[dict[str, Any]], *, since_ms: int | None = None) -> StatsAggregate:
    filtered = [event for event in events if since_ms is None or int(event.get("ts") or 0) >= since_ms]
    input_tokens = sum(int(event.get("input_tokens") or 0) for event in filtered)
    kept_tokens = sum(int(event.get("kept_tokens") or 0) for event in filtered)
    tokens_saved = sum(int(event.get("deleted_tokens") or 0) for event in filtered)
    files_compressed = sum(1 for event in filtered if event.get("source_path"))
    best_source = None
    best_saved_tokens = 0
    for event in filtered:
        saved = int(event.get("deleted_tokens") or 0)
        if saved > best_saved_tokens:
            best_saved_tokens = saved
            best_source = event.get("source_path") or event.get("command")
    return StatsAggregate(
        runs=len(filtered),
        input_tokens=input_tokens,
        kept_tokens=kept_tokens,
        tokens_saved=tokens_saved,
        files_compressed=files_compressed,
        best_source=best_source,
        best_saved_tokens=best_saved_tokens,
    )


def format_count(value: int) -> str:
    return f"{value:,}"


def format_compact_count(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def format_human_stats(aggregate: StatsAggregate) -> str:
    lines = [
        "ContextCrumb Stats",
        "----------------------------------",
        f"Runs:                  {format_count(aggregate.runs)}",
        f"Input tokens:          {format_count(aggregate.input_tokens)}",
        f"Kept tokens:           {format_count(aggregate.kept_tokens)}",
        f"Tokens saved:          {format_count(aggregate.tokens_saved)}",
        f"Average keep ratio:    {aggregate.average_keep_ratio * 100:7.1f}%",
        f"Files compressed:      {format_count(aggregate.files_compressed)}",
        "----------------------------------",
    ]
    if aggregate.best_source:
        lines.append(
            f"Best source: {aggregate.best_source}, saved {format_compact_count(aggregate.best_saved_tokens)} tokens"
        )
    else:
        lines.append("Best source: <none>")
    return "\n".join(lines)


def format_share_stats(aggregate: StatsAggregate) -> str:
    return (
        "ContextCrumb saved "
        f"{format_count(aggregate.tokens_saved)} tokens across "
        f"{format_count(aggregate.runs)} compression run(s)."
    )


def reset_stats(*, path: Path | None = None) -> Path | None:
    stats_path = path or default_stats_path()
    if not stats_path.exists():
        return None
    backup_path = stats_path.with_suffix(stats_path.suffix + f".{int(time.time())}.bak")
    stats_path.replace(backup_path)
    return backup_path
