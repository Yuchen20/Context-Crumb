---
sidebar_position: 2
sidebar_label: Assistant Workflows
---

# Assistant Workflow Examples

These examples are written as prompts or workflow snippets for people using coding assistants and agent tools.

## Read A Long Project Note

```text
Use ContextCrumb to compress docs/planning/roadmap.md before using it as context. Work from the compressed output unless you need exact wording.
```

Typical command:

```bash
contextcrumb load docs/planning/roadmap.md
```

## Compress A Research Folder

```text
Compress the Markdown research notes into a temporary folder with ContextCrumb, then use the compressed files to plan the implementation.
```

Typical command:

```bash
contextcrumb batch research --glob "*.md" --out .contextcrumb/research
```

## Inspect Before Acting

```text
Run contextcrumb inspect on the transcript first. If it keeps less than half the tokens, also run contextcrumb diff and check whether important names or constraints were deleted.
```

Typical commands:

```bash
contextcrumb inspect transcript.txt
contextcrumb diff transcript.txt
```

## Conservative Code-Adjacent Use

```text
This file mixes prose and code. Use ContextCrumb only for the prose sections. Load code blocks, config snippets, and commands exactly as written.
```

If the agent cannot split sections, use a conservative budget or raw loading:

```bash
contextcrumb load design.md --target-keep-ratio 0.75
```

## Use MCP

```text
Call the contextcrumb compress_file MCP tool on the long Markdown file, then use the returned text as compressed context.
```

Good MCP arguments:

```json
{
  "path": "docs/notes.md",
  "target_keep_ratio": 0.5
}
```

## Compress A Long Prompt Before Planning

```text
The request below is long and mostly prose. Compress it with ContextCrumb at a conservative keep ratio, then use the compressed version for planning. Keep exact commands, code, and acceptance criteria raw.
```

Typical command for a saved prompt:

```bash
contextcrumb load prompt.txt --target-keep-ratio 0.75
```

## Compress A Subagent Report

```text
Before handing the research report to the implementation agent, compress the narrative sections with ContextCrumb. Preserve code snippets, commands, URLs, and identifiers exactly.
```

Typical command:

```bash
contextcrumb load research-report.md --target-keep-ratio 0.55
```

## Compress Tool Output Carefully

```text
The tool output contains JSON. Do not compress the whole JSON blob. Compress only long prose fields such as description, body, summary, comment, or notes, and keep ids, URLs, statuses, timestamps, and numeric values unchanged.
```

For agents with direct MCP access, call `compress_text` on each safe prose field instead of on the full JSON object.
