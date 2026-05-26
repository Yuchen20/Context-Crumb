---
sidebar_position: 1
sidebar_label: Assistant Workflows
---

# Assistant Workflows

ContextCrumb is designed for agent context loading. The core habit is:

> Compress prose-heavy context before placing it into the model context.

The skill instructions focus on file loading because that is the easiest behavior to teach an assistant with a `SKILL.md`. Developers can also use ContextCrumb deeper in the stack: prompt compression, history compression, subagent output compression, and tool-output compression.

## Who This Is For

This section is for people using coding assistants, research agents, MCP clients, or editor-integrated tools. If you are adding ContextCrumb to an application or pipeline, start with the [Python API](../api/python.md) or [Local Service](../api/service.md).

## Recommended Agent Rule

Use ContextCrumb for large natural-language files:

```bash
contextcrumb load path/to/file.md
```

Do not use it as the only source for exact syntax:

- Source code
- Config files
- Diffs
- Schemas
- Commands
- Legal or policy text

For structured tool results, preserve the structure and compress only prose values. For example, compress a long `body` or `description` field, but keep ids, URLs, scores, timestamps, and schema fields raw.

## Common Prompts

Ask an agent:

```text
Use ContextCrumb to compress the project notes before you use them as context.
```

Or:

```text
Before reading the full transcript into context, run contextcrumb load on it and work from the compressed output.
```

For safer code-adjacent use:

```text
Use ContextCrumb only for the prose sections. Load code blocks and commands raw.
```

## Agent Integration Choices

| Integration | Use when |
| --- | --- |
| [Skill files](skills.md) | Your agent supports repo-owned or installed skills |
| [MCP server](mcp-server.md) | Your agent can call MCP tools |
| [MCP shrink proxy](mcp-shrink.md) | Tool catalogs are verbose before any tool call happens |
| [Local service](../api/service.md) | You want one warm model shared by multiple agent calls |

## Why This Helps Agents

- Reduces context spent on filler wording
- Keeps the original sequence of the document
- Avoids inventing summaries before the agent understands the task
- Lets agents process more source material before hitting context pressure
- Provides stats for how much context was saved
