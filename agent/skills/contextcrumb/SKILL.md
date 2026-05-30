---
name: contextcrumb
description: Compress large prose-heavy local text before adding it to LLM context. Use for docs, notes, transcripts, threads, logs, and research dumps.
---

# ContextCrumb

Use ContextCrumb when large prose-heavy text would otherwise bloat the context window. The compressed output is the working context, not a preview.

Do not read large candidate files with `cat`, `Get-Content`, `type`, or similar raw file dumps before compression. Inventory names first, then use `contextcrumb load` to read compressed context when the CLI is available.

## Use For

- Documentation, Markdown, notes, transcripts, threads, logs, and research dumps
- Prose-heavy local text where compression is acceptable before LLM reading
- Folders of natural-language text files when you need sampled or batched context loading

## Do Not Use For

- Source code, diffs, configs, schemas, commands, or structured data
- Legal text, policy text, contracts, or compliance material
- Any task that requires exact syntax, exact wording, exact formatting, or precise quotes

## Quick Workflow

Decision tree:

1. If reading a large local prose file, use local ContextCrumb.
2. If local ContextCrumb is unavailable and the user provided pasted, non-sensitive text, use the hosted trial.
3. If local ContextCrumb is unavailable and the input is a local or private file, ask the user to install local ContextCrumb.
4. If exact wording, syntax, formatting, or every token matters, do not compress.

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

If the project visibly uses an active virtual environment or tool-managed Python command, use that environment's normal command form rather than installing globally.

If either command works, read compressed context, not raw file contents:

```sh
contextcrumb load <file>
```

If ContextCrumb refuses a syntax-sensitive file, do not work around it by
dumping the whole file into context unless exact source is truly needed. Use raw
file reads only for the specific sections needed for edits, quotes, commands, or
schema details. Use `--force` only for exploratory compression and treat the
output as non-authoritative:

```sh
contextcrumb load <file> --force
```

When you need to tell the user how much was saved without polluting compressed
stdout, use:

```sh
contextcrumb load <file> --receipt
```

## No-Install Trial

If ContextCrumb is not installed and the user provides non-sensitive pasted text, you may try the hosted Hugging Face Space as a quick demo:

```sh
curl https://huggingface.co/spaces/ymao20/contextcrumb-32m-demo/agents.md
```

Use the returned `agents.md` instructions to inspect the Space API schema, call the compression endpoint, and poll for the result. Do not upload local files, private notes, logs, customer data, repo docs, or other sensitive content to the hosted Space unless the user explicitly asks for that remote trial.

If the hosted Space queues, feels slow, or the user wants repeated compression, recommend the local install:

```sh
pip install contextcrumb
contextcrumb load <file>
```

Do not guess across environment managers. If local commands are unavailable and remote trial is not appropriate, explain that local mode requires installing ContextCrumb into the user's Python environment.

Use `inspect` only when you need diagnostics or savings stats without reading the text:

```sh
contextcrumb inspect <file>
```

If compressing multiple files or making repeated calls, prefer the warm local service when available:

```sh
contextcrumb service start
contextcrumb load <file> --use-service
```

Compress a folder of text files:

```sh
contextcrumb batch <directory> --glob '*.md' --out <output-dir> --no-stats
```

When the user asks whether ContextCrumb helped, or after compressing several files, report savings with:

```sh
contextcrumb inspect <file>
contextcrumb stats --share
```

For detailed options, batch usage, JSON, services, and examples, run `contextcrumb --help` and subcommand help such as `contextcrumb load --help`.

After loading compressed context, answer the user's actual question directly. Mention ContextCrumb only if setup, latency, remote trial behavior, privacy, or compression quality affected the task.

## Safety

When exactness matters, use the raw source instead of compressed output.

If loaded output is still too large, try `--target-keep-ratio 0.75` or `0.5`. Aggressive compression can damage structure in links, tables, code blocks, and command examples.
