---
sidebar_position: 3
---

# MCP Server

ContextCrumb includes an MCP stdio server with two tools:

```text
compress_text
compress_file
```

Install MCP dependencies:

```bash
pip install "contextcrumb[mcp]"
```

Or run with `uvx`:

```bash
uvx --from "contextcrumb[mcp]" contextcrumb-mcp
```

## MCP Client Config

Use this pattern for clients that accept JSON MCP server config:

```json
{
  "mcpServers": {
    "contextcrumb": {
      "command": "uvx",
      "args": [
        "--from",
        "contextcrumb[mcp]",
        "contextcrumb-mcp"
      ]
    }
  }
}
```

## Tool: `compress_text`

Arguments:

| Argument | Default | Meaning |
| --- | --- | --- |
| `text` | required | Inline text to compress |
| `threshold` | `0.5` | Keep probability cutoff for threshold mode |
| `target_keep_ratio` | `null` | Fixed token budget; overrides threshold mode |
| `golden` | `true` | Deprecated compatibility flag; threshold mode is used by default |
| `golden_min_keep_ratio` | `0.333...` | Deprecated compatibility value |
| `return_tokens` | `false` | Include token decisions |

## Tool: `compress_file`

Arguments:

| Argument | Default | Meaning |
| --- | --- | --- |
| `path` | required | Local file path on the MCP server machine |
| `encoding` | `utf-8` | File encoding |
| `threshold` | `0.5` | Keep probability cutoff |
| `target_keep_ratio` | `null` | Fixed token budget |
| `golden` | `true` | Deprecated compatibility flag; threshold mode is used by default |
| `golden_min_keep_ratio` | `0.333...` | Deprecated compatibility value |
| `return_tokens` | `false` | Include token decisions |
| `force` | `false` | Allow syntax-sensitive file types for exploratory compression |
| `content_mode` | config default | `auto`, `prose`, `code-comments`, `raw`, or `refuse` |

`compress_file` uses configured `content_mode` by default. In `auto` mode,
supported source files preserve executable code exactly and compress only
comments/docstrings. Supported code-aware languages are Python, JavaScript,
TypeScript, JSX, TSX, Go, and Rust.

Unsupported syntax-sensitive file types such as diffs, structured configs,
lockfiles, SQL, and `.env` files are refused unless `force=true`. Forced output
should not be used for exact edits, quotes, commands, or schema details without
reading the raw source.

## Use A Warm Service

For repeated MCP calls, start the local service and run the MCP server in service mode:

```bash
contextcrumb service start --allow-root .
contextcrumb-mcp --use-service
```

Config:

```json
{
  "mcpServers": {
    "contextcrumb": {
      "command": "uvx",
      "args": [
        "--from",
        "contextcrumb[mcp]",
        "contextcrumb-mcp",
        "--use-service",
        "--service-url",
        "http://127.0.0.1:8765"
      ]
    }
  }
}
```

Service mode prevents every MCP server process from loading its own model.
