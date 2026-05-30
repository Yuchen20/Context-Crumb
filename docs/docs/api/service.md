---
sidebar_position: 3
---

# Local Service

The local service keeps one warm ContextCrumb model process running behind a localhost HTTP API. Use it when an application, agent, editor, MCP server, or batch job makes repeated compression calls.

Use the service when process startup or model loading would otherwise happen too often. For a single script that already stays alive, prefer `ContextCompressor` directly.

The service accepts text directly, so it works for prompts, conversation history chunks, subagent reports, and tool-output fields as well as files.

Install the service dependencies:

```bash
pip install "contextcrumb[serve]"
```

## Start

```bash
contextcrumb service start
```

By default it starts on:

```text
http://127.0.0.1:8765
```

Start lazily, so the HTTP server starts before the model is loaded:

```bash
contextcrumb service start --lazy-load
```

Allow local file reads under a specific root:

```bash
contextcrumb service start --allow-root docs
```

Disable file reads entirely:

```bash
contextcrumb service start --disable-file-reads
```

File reads are limited to allowed roots. This matters when an agent can call `/compress_file`; only expose directories that the agent should read.

## Use From The CLI

```bash
contextcrumb load notes.md --use-service
contextcrumb batch docs --glob "*.md" --out compressed-docs --use-service
```

Set a default service URL:

```bash
CONTEXTCRUMB_SERVICE_URL=http://127.0.0.1:8765 contextcrumb load notes.md --use-service
```

## Status And Stop

```bash
contextcrumb service status
contextcrumb service stop
```

## HTTP Endpoints

### `GET /health`

Returns service state:

```json
{
  "ok": true,
  "model_loaded": true,
  "backend": "onnx",
  "file_reads_enabled": true,
  "allowed_file_roots": ["C:/project/docs"]
}
```

### `POST /compress`

```bash
curl -X POST http://127.0.0.1:8765/compress \
  -H "Content-Type: application/json" \
  -d '{"text":"Long prose-heavy text.","target_keep_ratio":0.5}'
```

### `POST /compress_file`

```bash
curl -X POST http://127.0.0.1:8765/compress_file \
  -H "Content-Type: application/json" \
  -d '{"path":"docs/notes.md","target_keep_ratio":0.5}'
```

The file path must be under an allowed root unless file reads are disabled. The
endpoint refuses syntax-sensitive file types by default. Use `"force": true` only
for exploratory compression, and read the raw source before exact edits, quotes,
commands, or schema details.

### `POST /shutdown`

```bash
curl -X POST http://127.0.0.1:8765/shutdown
```

## Direct Serve Mode

Use `serve` when you want the foreground process instead of the service manager:

```bash
contextcrumb serve --host 127.0.0.1 --port 8765 --allow-root docs
```
