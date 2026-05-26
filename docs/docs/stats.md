---
sidebar_position: 9
---

# Stats

ContextCrumb logs local token-savings events by default.

View stats:

```bash
contextcrumb stats
```

JSON:

```bash
contextcrumb stats --json
```

Recent window:

```bash
contextcrumb stats --since 24h
contextcrumb stats --since 7d
contextcrumb stats --since 4w
```

Shareable one-liner:

```bash
contextcrumb stats --share
```

Reset the ledger:

```bash
contextcrumb stats reset
```

## Privacy Controls

Disable stats for one command:

```bash
contextcrumb load notes.md --no-stats
```

Disable stats globally:

```bash
CONTEXTCRUMB_STATS=0 contextcrumb load notes.md
```

Choose how paths are recorded:

```bash
CONTEXTCRUMB_STATS_PATH_MODE=basename contextcrumb load notes.md
CONTEXTCRUMB_STATS_PATH_MODE=full contextcrumb load notes.md
CONTEXTCRUMB_STATS_PATH_MODE=hash contextcrumb load notes.md
CONTEXTCRUMB_STATS_PATH_MODE=none contextcrumb load notes.md
```

Default path mode is `basename`.

Use a custom stats file:

```bash
CONTEXTCRUMB_STATS_FILE=/tmp/contextcrumb-stats.jsonl contextcrumb load notes.md
```

## Recorded Fields

Each event includes:

- timestamp
- run id
- source
- command
- redacted source path
- input tokens
- kept tokens
- deleted tokens
- token keep ratio
- mode
- model id
- backend
