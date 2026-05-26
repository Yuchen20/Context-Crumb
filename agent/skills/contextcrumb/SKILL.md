---
name: contextcrumb
description: Use when an agent needs to compress large prose-heavy files before sending them into LLM context. Best for Markdown docs, notes, issue threads, logs with narrative text, research dumps, and other natural-language files where useful information density matters more than every filler token.
---

# ContextCrumb

## Purpose

Use ContextCrumb to compress large local text files before they enter an LLM context window. It deletes lower-value words and punctuation while keeping the remaining text in original order.

ContextCrumb is for context compression, token savings, and context-bloat control. It is not a preview step. For prose-heavy inputs, the compressed output is the context you work from.

## When To Use

Use it for large natural-language files:

- Documentation and Markdown
- Notes and research dumps
- Issue threads and long discussions
- Logs with lots of prose
- Long comments or narrative text

## When Not To Use

Do not rely on compressed output for exact syntax or exact wording:

- Source code
- Config files
- Diffs and patches
- JSON, YAML, TOML, XML, or schemas
- Commands that may need to be copied exactly
- Legal, compliance, policy, or contract text

Only fall back to raw source when the task depends on exact syntax, exact wording, or exact formatting. If a natural-language file is simply large and prose-heavy, ContextCrumb output can be used directly as compressed context.

## Default Workflow

First, check whether the `contextcrumb` CLI is available:

```powershell
contextcrumb --help
```

If the command exists, use golden mode by default:

```powershell
contextcrumb load <file>
```

If the command is missing, install the Python package once:

```powershell
python -m pip install contextcrumb
```

Then compress the file:

```powershell
contextcrumb load <file>
```

If the environment has `uvx`, it can be used as an optional no-install path, but do not assume it is available:

```powershell
uvx --from contextcrumb contextcrumb load <file>
```

Golden mode chooses an adaptive cutoff for each file and is the preferred default because it is conservative. If the output is still too large, use a fixed keep ratio:

```powershell
contextcrumb load <file> --target-keep-ratio 0.75
contextcrumb load <file> --target-keep-ratio 0.5
```

Avoid aggressive ratios unless the user explicitly asks for heavy compression.

## Validation

Check compression savings without dumping the full output:

```powershell
contextcrumb inspect <file>
```

Check what was removed when you want to understand or tune the compression:

```powershell
contextcrumb diff <file>
```

Use JSON only when another tool needs stats:

```powershell
contextcrumb load <file> --json
```

Read the `text` field as compressed context. Use `stats.token_keep_ratio`, `stats.word_keep`, and `stats.model_windows` to decide whether to retry with a different setting.

## Practical Rules

- Use `contextcrumb load <file>` as the default.
- If `contextcrumb` is missing, install it with `python -m pip install contextcrumb`.
- Use `uvx --from contextcrumb contextcrumb load <file>` only when `uvx` is already available.
- Use `inspect` and `diff` when you want to understand or tune compressed text.
- Never edit code, copy commands, or quote exact wording based only on compressed output.
