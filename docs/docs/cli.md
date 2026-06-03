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
contextcrumb load notes.md --receipt
contextcrumb load notes.md --no-stats
```

`--receipt` keeps compressed text on stdout and writes a compact receipt to stderr:

```text
ContextCrumb receipt: notes.md tokens 12,400->4,100, saved 8,300 (66.9%), keep_ratio=0.331, mode=threshold, raw-read-before-exact-use=false
```

With `--json --receipt`, the receipt is included as a top-level JSON field.

## File Safety

ContextCrumb is meant for prose-heavy context. `load`, `inspect`, `diff`, and `batch`
refuse syntax-sensitive file types by default, including source code, diffs,
JSON/YAML/TOML/XML, lockfiles, shell scripts, SQL, `.env` files, and common package
manifests where exact structure matters.

For exploratory compression only, override the guard:

```bash
contextcrumb load script.py --force
```

When `--force` is used, read the raw source before editing, quoting, copying
commands, or relying on exact structure.

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
- `Threshold` when using threshold mode

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
