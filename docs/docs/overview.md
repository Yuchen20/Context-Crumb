---
sidebar_position: 1
---

# Overview

ContextCrumb compresses prose-heavy context before it reaches an LLM or agent. It scores the input token by token, deletes low-value tokens, and keeps the surviving text in the original order. For supported source files, it can preserve executable code exactly while compressing only comments/docstrings.

It is useful when natural-language context is too verbose for a model context window: docs, notes, issue threads, transcripts, logs, research dumps, prompts, conversation history, subagent output, or natural-language tool results.

## Choose Your Path

ContextCrumb serves two common workflows:

| If you are... | Use ContextCrumb to... | Start with |
| --- | --- | --- |
| Building an app, pipeline, evaluation, or internal tool | Add local context compression as middleware before an LLM call, agent handoff, or prompt assembly step | [Python API](api/python.md) and [Local Service](api/service.md) |
| Working with coding agents or assistant tools | Compress prose-heavy context before it enters the agent context | [Getting Started](getting-started.md) and [Agent Skills / MCP](skills/overview.md) |

Both paths use the same model and output shape. The difference is integration style: application developers usually call Python or HTTP APIs; assistant workflows usually call the CLI, a skill, or MCP.

## What Makes It Different

ContextCrumb is not a summarizer. It does not rewrite the source into a new paragraph. It keeps the source sequence and removes padding.

That makes it a good fit for agent workflows where the model still needs names, steps, constraints, and ordering, but does not need every filler phrase.

## Best Fit

- Long Markdown files and documentation
- Meeting notes and research dumps
- Issue threads and long discussions
- Logs with narrative text
- User prompts and prompt templates
- Conversation history before replaying it into another model call
- Subagent reports, planner output, and research-agent notes
- Natural-language tool results
- Tool, resource, and prompt descriptions in MCP catalogs
- Agent skills that load large local files
- Supported source files when comment/docstring compression is useful

## Context Surfaces

ContextCrumb can sit anywhere a system turns natural language into model input:

| Context surface | Example |
| --- | --- |
| Retrieved documents | Compress long docs before adding them to a RAG prompt |
| User prompt | Compress an oversized free-form request before routing or planning |
| Conversation history | Compress older turns before replaying them into another model call |
| Subagent output | Compress research or planning reports before handing them to a main agent |
| Tool output | Compress prose fields in search results, issue threads, or logs |
| Tool catalogs | Compress verbose MCP descriptions before an agent sees the catalog |

## Avoid Or Use Carefully

Do not use compressed output as the only source of truth when exact text matters:

- Unsupported source code, or source code when exact comments/docstrings matter
- Config files
- Diffs and patches
- JSON, YAML, TOML, XML, or schemas
- Shell commands people may copy exactly
- Legal, compliance, policy, or contract text

For supported Python, JavaScript, TypeScript, JSX, TSX, Go, and Rust files, `auto` mode preserves executable source exactly and compresses only comments/docstrings. For structured data and unsupported code, load the raw file or use `raw`/`refuse` file modes.

For structured tool output, preserve the structure and compress only natural-language values. Do not compress raw JSON as one string if keys, ids, numbers, or schema shape matter.

## Main Workflows

| Workflow | Start with |
| --- | --- |
| Try it from the terminal | [Getting Started](getting-started.md) |
| Use it as middleware in an app | [Python API](api/python.md) |
| Compress many files | [Batch API](api/batch.md) |
| Compress prompts, history, or tool results | [App Integration Examples](examples/developer.md) |
| Add it to agent-assisted workflows | [Agent Skills / MCP](skills/overview.md) |
| Expose MCP tools | [MCP Server](skills/mcp-server.md) |
| Shrink verbose MCP catalogs | [MCP Shrink Proxy](skills/mcp-shrink.md) |
| Keep one warm model process | [Local Service](api/service.md) |
