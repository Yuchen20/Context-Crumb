import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contextcrumb.compressor import CompressionResult
from contextcrumb.stats import (
    aggregate_events,
    append_event,
    build_event,
    default_stats_path,
    format_human_stats,
    parse_since,
    read_events,
    stats_enabled,
)


class StatsTests(unittest.TestCase):
    def test_default_path_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stats_file = Path(temp_dir) / "stats.jsonl"
            with patch.dict(os.environ, {"CONTEXTCRUMB_STATS_FILE": str(stats_file)}):
                self.assertEqual(default_stats_path(), stats_file)

    def test_append_read_and_skip_malformed_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stats_file = Path(temp_dir) / "stats.jsonl"
            append_event({"version": 1, "input_tokens": 10}, path=stats_file)
            with stats_file.open("a", encoding="utf-8") as handle:
                handle.write("{bad json\n")
                handle.write(json.dumps({"version": 1, "input_tokens": 20}) + "\n")

            events = read_events(path=stats_file)

        self.assertEqual([event["input_tokens"] for event in events], [10, 20])

    def test_aggregation_all_time_and_since(self):
        now = 2_000_000
        events = [
            {"ts": now - 8 * 24 * 60 * 60 * 1000, "input_tokens": 100, "kept_tokens": 40, "deleted_tokens": 60, "source_path": "old.md"},
            {"ts": now - 2 * 24 * 60 * 60 * 1000, "input_tokens": 50, "kept_tokens": 20, "deleted_tokens": 30, "source_path": "new.md"},
        ]

        all_time = aggregate_events(events)
        recent = aggregate_events(events, since_ms=parse_since("7d", now_ms=now))

        self.assertEqual(all_time.runs, 2)
        self.assertEqual(all_time.tokens_saved, 90)
        self.assertEqual(recent.runs, 1)
        self.assertEqual(recent.tokens_saved, 30)

    def test_aggregation_since_hours(self):
        now = 2_000_000
        events = [
            {"ts": now - 25 * 60 * 60 * 1000, "input_tokens": 100, "kept_tokens": 40, "deleted_tokens": 60},
            {"ts": now - 23 * 60 * 60 * 1000, "input_tokens": 50, "kept_tokens": 20, "deleted_tokens": 30},
        ]

        aggregate = aggregate_events(events, since_ms=parse_since("24h", now_ms=now))

        self.assertEqual(aggregate.runs, 1)
        self.assertEqual(aggregate.input_tokens, 50)

    def test_event_does_not_store_text_content(self):
        result = CompressionResult(
            text="compressed secret",
            original_text="original secret",
            stats={"input_tokens": 10, "kept_tokens": 4, "deleted_tokens": 6, "token_keep_ratio": 0.4},
        )

        event = build_event(result.stats, source="cli", command="compress")

        self.assertNotIn("text", event)
        self.assertNotIn("original_text", event)

    def test_env_disables_stats(self):
        with patch.dict(os.environ, {"CONTEXTCRUMB_STATS": "0"}):
            self.assertFalse(stats_enabled())

    def test_human_format_handles_empty_history(self):
        report = format_human_stats(aggregate_events([]))

        self.assertIn("Runs:", report)
        self.assertIn("Best source: <none>", report)


if __name__ == "__main__":
    unittest.main()
