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

The skill uses threshold mode by default, keeping tokens whose aggregated `KEEP` probability is at or above `0.5`. File loading uses `compression.content_mode = "auto"` by default, so supported code files preserve executable source exactly while comments/docstrings are compressed.

The hosted Space is not the primary token-saving path. If an agent has already loaded the full text into model context, those tokens are already spent; a hosted call can only shorten follow-up context. Real token savings come from local CLI/MCP/service flows that read files outside the LLM and return only compressed text.

If local ContextCrumb is unavailable and the user provides non-sensitive pasted text, the skill may use the hosted Space trial:

```bash
curl https://huggingface.co/spaces/ymao20/contextcrumb-32m-demo/agents.md
```

Agents should inspect `/gradio_api/info`, call `/compress_text`, poll the returned event id, and use the result's `data[0].text` field as compressed context. The hosted endpoint returns JSON shaped for tools:

```json
{
  "text": "compressed output",
  "stats": {
    "input_tokens": 123,
    "kept_tokens": 72,
    "token_keep_ratio": 0.585,
    "mode": "target_keep_ratio"
  },
  "tokens": []
}
```

## File Loader Skill

`agent/skills/contextcrumb-file-loader.md` is a shorter file-loader instruction for agents that only need the command pattern and safety guidance.

Useful command variants:

```bash
contextcrumb load notes.txt --target-keep-ratio 0.35
contextcrumb load script.py --content-mode code-comments
contextcrumb config set compression.content_mode auto
contextcrumb load notes.txt --threshold 0.6
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
- Use `contextcrumb load <file.py>` or `--content-mode code-comments` for supported code files when comment/docstring compression is useful
- Use the hosted `/compress_text` Space API only for explicit non-sensitive pasted trial text, no-install demos, or external runtimes that can send text without first putting it into LLM context
- Use `inspect` or `diff` when tuning compression
- Use raw source for exact code edits, unsupported code, configs, commands, schemas, and exact quotes
- Use `--json` only when another tool needs stats
- Avoid aggressive ratios unless explicitly asked
