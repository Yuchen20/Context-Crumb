---
sidebar_position: 2
---

# Skills

ContextCrumb ships repo-owned skill material under `agent/skills`.

Use these files as the source of truth for agent behavior:

```text
agent/
  skills/
    README.md
    contextcrumb-file-loader.md
    contextcrumb/
      SKILL.md
      agents/
        openai.yaml
```

## Main Skill

`agent/skills/contextcrumb/SKILL.md` tells an agent when and how to compress large local text files.

Core rule:

```bash
contextcrumb load <file>
```

The skill recommends golden mode by default, because it is conservative and does not require the agent to tune a ratio.

## File Loader Skill

`agent/skills/contextcrumb-file-loader.md` is a shorter file-loader instruction for agents that only need the command pattern and safety guidance.

Useful command variants:

```bash
contextcrumb load notes.txt --target-keep-ratio 0.35
contextcrumb load notes.txt --no-golden --threshold 0.6
contextcrumb load notes.txt --json
contextcrumb load notes.txt --json --return-tokens
contextcrumb load notes.txt --model ./artifacts/onnx/contextcrumb-32m
```

## OpenAI Agent Metadata

`agent/skills/contextcrumb/agents/openai.yaml` provides display metadata:

```yaml
interface:
  display_name: "ContextCrumb"
  short_description: "Compress large files for agent context"
  default_prompt: "Use $contextcrumb to compress a large local document before loading it into context."
```

## Installing The Skill Manually

If your agent supports local skill folders, copy or reference:

```text
agent/skills/contextcrumb/
```

If the agent accepts Markdown instructions only, paste the contents of:

```text
agent/skills/contextcrumb/SKILL.md
```

## Skill Safety Rules

Agents should:

- Use `contextcrumb load <file>` for large prose-heavy files
- Use `inspect` or `diff` when tuning compression
- Use raw source for code, configs, commands, schemas, and exact quotes
- Use `--json` only when another tool needs stats
- Avoid aggressive ratios unless explicitly asked
