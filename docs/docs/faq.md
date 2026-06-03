---
sidebar_position: 10
---

# FAQ

## Is ContextCrumb a summarizer?

No. It deletes lower-value tokens and keeps the remaining text in original order. It does not rewrite or paraphrase the document.

## When should I use it?

Use it before sending large prose-heavy context to an LLM or agent. Good inputs include docs, notes, issue threads, logs with narrative text, transcripts, research dumps, prompts, older conversation turns, subagent reports, and natural-language tool output.

## When should I avoid it?

Avoid using compressed output as the only source for exact syntax or exact wording. Use raw files for code, configs, schemas, diffs, commands, legal text, and direct quotes.

## What is the default threshold?

The default threshold is `0.5`. ContextCrumb is trained as a binary keep/delete classifier, so the default keeps tokens whose aggregated `KEEP` probability is at or above the classifier boundary.

The old `golden` options are kept for compatibility but no longer change default compression behavior.

## How do I make output smaller?

Use `--target-keep-ratio`:

```bash
contextcrumb load notes.md --target-keep-ratio 0.5
```

Lower values compress more aggressively.

## How do I make output safer?

Use a higher keep ratio:

```bash
contextcrumb load notes.md --target-keep-ratio 0.75
```

Or use raw loading when exact text matters.

## Does it need internet access?

The first run may download the model from Hugging Face. After that, model files are loaded from the local cache unless you change model, revision, or cache settings.

## Does it send my text to a hosted API?

The normal CLI and Python API run locally. The local service is also localhost-only by default. Your text is not sent to a ContextCrumb-hosted API by these paths.

## Why does first run feel slower?

The first run may download and initialize the model. For repeated calls, reuse `ContextCompressor` in Python or start `contextcrumb service start`.

## How do I use it with agents?

Use the skill instructions, MCP server, or direct CLI command:

```bash
contextcrumb load long-file.md
```

See [Assistant Workflows](skills/overview.md).

## Should developers use the CLI or Python API?

Use the Python API when ContextCrumb is part of an application or prompt pipeline. Use the CLI when a shell, editor task, hook, or agent needs a compact command.

For repeated calls from several processes, use the local service.

## Can I compress tool output?

Yes, when the output contains natural-language fields. Preserve the original structure and compress only prose values such as `summary`, `body`, `description`, `comment`, or `notes`.

Do not flatten an important JSON object into a string and compress the whole thing. Keep keys, ids, URLs, numeric values, timestamps, enums, and schemas unchanged.

## Can I compress prompts or conversation history?

Yes. Use conservative settings for prompts because instructions and constraints matter. For conversation history, older verbose turns are usually better candidates than system prompts or the latest user request.
