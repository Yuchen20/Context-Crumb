---
sidebar_position: 4
---

# MCP Shrink Proxy

`contextcrumb-shrink` wraps another MCP stdio server and compresses verbose catalog descriptions before the agent sees them.

It is for a different problem than `contextcrumb-mcp`:

- `contextcrumb-mcp` gives the agent compression tools.
- `contextcrumb-shrink` compresses another server's tool, prompt, resource, and resource-template descriptions.

Tool calls, tool results, names, schemas, and resource contents are forwarded unchanged.

## Basic Usage

```bash
contextcrumb-shrink -- upstream-mcp-server --flag value
```

The upstream command is everything after `--`.

## Service Mode

For a lighter proxy, start a warm service and use it from the shrink proxy:

```bash
contextcrumb service start
contextcrumb-shrink --mode service -- upstream-mcp-server
```

## Fields

By default, the proxy compresses only `description` fields.

Compress extra catalog fields:

```bash
contextcrumb-shrink --fields description,title -- upstream-mcp-server
```

Environment variable equivalent:

```bash
CONTEXTCRUMB_SHRINK_FIELDS=description,title contextcrumb-shrink -- upstream-mcp-server
```

## Compression Budget

The default shrink proxy target keep ratio is `0.5`.

Tune it:

```bash
contextcrumb-shrink --target-keep-ratio 0.4 -- upstream-mcp-server
```

Environment variable:

```bash
CONTEXTCRUMB_SHRINK_TARGET_KEEP_RATIO=0.4 contextcrumb-shrink -- upstream-mcp-server
```

## Debugging

```bash
contextcrumb-shrink --debug -- upstream-mcp-server
```

Or:

```bash
CONTEXTCRUMB_SHRINK_DEBUG=1 contextcrumb-shrink -- upstream-mcp-server
```

## Protected Text

The proxy preserves protected spans outside model input, including:

- Fenced code blocks
- Inline code
- URLs
- Windows and Unix-like paths
- Function calls
- Dotted identifiers
- Snake case and uppercase identifiers
- Version strings
- Small JSON-like objects

This keeps catalog descriptions shorter without breaking important handles or names.
