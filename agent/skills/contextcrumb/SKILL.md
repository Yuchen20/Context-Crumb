---
name: contextcrumb
description: Compress large prose-heavy local text before adding it to LLM context. Use for docs, notes, transcripts, threads, logs, and research dumps.
---

# ContextCrumb

Use ContextCrumb when a large local text file is mostly natural language and would otherwise bloat the context window. The compressed output is the working context, not a preview.

Do not read large candidate files with `cat`, `Get-Content`, `type`, or similar raw file dumps before compression. Inventory names first, then use `contextcrumb load` to read compressed context.

## Use For

- Documentation, Markdown, notes, transcripts, threads, logs, and research dumps
- Prose-heavy local text where compression is acceptable before LLM reading
- Folders of natural-language text files when you need sampled or batched context loading

## Do Not Use For

- Source code, diffs, configs, schemas, commands, or structured data
- Legal text, policy text, contracts, or compliance material
- Any task that requires exact syntax, exact wording, exact formatting, or precise quotes

## Quick Workflow

Inventory without reading file bodies:

```sh
rg --files <directory>
```

Check the CLI:

```sh
contextcrumb --help
```

If it is not on PATH, try the module form before installing:

```sh
python -m contextcrumb --help
```

Read compressed context, not raw file contents:

```sh
contextcrumb load <file>
```

Use `inspect` only when you need diagnostics or savings stats without reading the text:

```sh
contextcrumb inspect <file>
```

Compress a folder of text files:

```sh
contextcrumb batch <directory> --glob '*.md' --out <output-dir> --no-stats
```

For detailed options, batch usage, JSON, services, and examples, run `contextcrumb --help` and subcommand help such as `contextcrumb load --help`.

## Safety

When exactness matters, use the raw source instead of compressed output.

If loaded output is still too large, try `--target-keep-ratio 0.75` or `0.5`. Aggressive compression can damage structure in links, tables, code blocks, and command examples.
