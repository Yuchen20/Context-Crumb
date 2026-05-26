---
sidebar_position: 4
---

# CLI

The `contextcrumb` command is the direct interface for shells, editor tasks, hooks, and agent tools.

Use `load` when a tool needs compressed context. Use `compress` when you are experimenting with inline text or stdin. Use `batch` when you want compressed files on disk.

## Load A File For Context

Use `load` when the next step is an LLM or agent context window:

```bash
contextcrumb load path/to/notes.md
```

It prints compressed text only, so another command or model prompt can consume it directly.

Useful options:

```bash
contextcrumb load notes.md --target-keep-ratio 0.5
contextcrumb load notes.md --json
contextcrumb load notes.md --json --return-tokens
contextcrumb load notes.md --no-stats
```

## Compress Inline Text Or Stdin

Compress inline text:

```bash
contextcrumb compress --text "A long prose-heavy paragraph about project decisions and constraints."
```

Compress a file through the general command:

```bash
contextcrumb compress notes.md
```

Pipe stdin on macOS or Linux:

```bash
cat notes.md | contextcrumb compress
```

On Windows PowerShell, the equivalent is:

```powershell
Get-Content notes.md | contextcrumb compress
```

## Inspect

Use `inspect` to see compression stats:

```bash
contextcrumb inspect notes.md
```

Example fields:

- `Mode`
- `Backend`
- `Model windows`
- `Chars`
- `Words`
- `Tokens`
- Golden cutoff details when using golden mode

## Diff

Use `diff` to build trust or tune settings:

```bash
contextcrumb diff notes.md
```

Deleted tokens are wrapped with `[-` and `-]`.

## Batch

Compress many files into another directory:

```bash
contextcrumb batch docs --glob "*.md" --out compressed-docs
```

The output directory mirrors the input directory structure.

Use `--json` when automation needs a summary of every output file:

```bash
contextcrumb batch docs --glob "*.md" --out compressed-docs --json
```

## Stats

ContextCrumb writes a local stats ledger by default. View it:

```bash
contextcrumb stats
contextcrumb stats --json
contextcrumb stats --since 7d
contextcrumb stats --share
```

Disable stats for a command:

```bash
contextcrumb load notes.md --no-stats
```

Disable stats globally:

```bash
CONTEXTCRUMB_STATS=0 contextcrumb load notes.md
```

On Windows PowerShell:

```powershell
$env:CONTEXTCRUMB_STATS = "0"
contextcrumb load notes.md
```
