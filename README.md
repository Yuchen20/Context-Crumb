# ContextCrumb

ContextCrumb is a token-level context compressor for LLM and agent workflows. It uses a 32M parameter token-classification model to mark which words and punctuation can be deleted while preserving as much useful context as possible.

The first release is Python-first, with optional MCP support for local agent workflows. JavaScript, hosted APIs, and public deployment are intentionally deferred until the Python UX and model packaging are stable.

## Install

For local development:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e ".[dev]"
```

For private Hugging Face model access, authenticate first:

```powershell
.\.venv\Scripts\hf.exe auth login
```

The default model id is private for now:

```text
ymao20/contextcrumb-32m
```

ContextCrumb uses the ONNX backend by default, so normal users do not need PyTorch or Transformers installed. Model files are cached locally after the first download, so the model is not downloaded on every run.

## Python API

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()

result = compressor.compress(
    "ContextCrumb deletes low-value words while preserving useful context.",
    return_tokens=True,
)

print(result.text)
print(result.stats)
```

Golden mode is the default. It chooses a natural cutoff for each input:

```python
result = compressor.compress(text)
print(result.stats["golden_cutoff"])
print(result.stats["golden_keep_ratio"])
```

Golden mode finds the largest gap in word-token keep probabilities and uses the midpoint as the cutoff. This often lands near the model's natural split between high-value and low-value tokens.
It keeps at least one third of word-like tokens by default, so an extreme probability gap does not delete almost everything. Use `target_keep_ratio` when you intentionally want a lower fixed budget.

For a local model folder:

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor(
    "models/runs/YYYYMMDD-HHMMSS-name/onnx",
    device="cpu",
)
print(compressor.compress("A short example sentence for compression.").text)
```

Read and compress a file from Python:

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()
result = compressor.compress_file("notes.txt")

print(result.text)
print(result.stats["source_path"])
print(result.stats["token_keep_ratio"])
```

Use the Torch backend only when you need parity debugging or custom Transformers workflows:

```python
compressor = ContextCompressor(
    "models/runs/YYYYMMDD-HHMMSS-name",
    backend="torch",
    device="cpu",
)
```

## CLI

Agent-oriented file loading:

```powershell
contextcrumb load .\notes.txt
```

`contextcrumb load` is designed for coding agents, MCP tools, and prompt pipelines that need to read a large local text file before sending it to an LLM. It prints only the compressed text by default, so an agent can capture stdout and use it as shortened context. It uses capped golden mode by default, so callers do not need to tune a ratio.

Use a fixed compression budget:

```powershell
contextcrumb load .\notes.txt --target-keep-ratio 0.35
```

Use threshold mode when you want a fixed probability cutoff instead of golden mode:

```powershell
contextcrumb load .\notes.txt --no-golden --threshold 0.6
```

Golden mode keeps at least one third of word-like tokens unless you override `--golden-min-keep-ratio`. Use `--target-keep-ratio` for intentionally lower fixed budgets.

Emit metadata for tool callers:

```powershell
contextcrumb load .\notes.txt --json
```

Best fit: docs, notes, transcripts, issue threads, logs, research context, and other natural-language files. For source code where exact syntax matters, prefer raw file loading or use a conservative keep ratio.

Compress inline text:

```powershell
contextcrumb compress --text "ContextCrumb removes expendable wording from long prompts."
```

Compress a file:

```powershell
contextcrumb compress .\article.txt
```

Emit structured JSON:

```powershell
contextcrumb compress --input .\article.txt --json --return-tokens
```

Inspect compression stats without dumping the compressed text:

```powershell
contextcrumb inspect .\article.txt
```

Show an inline keep/delete diff for trust-building and demos:

```powershell
contextcrumb diff .\article.txt
```

Deleted tokens are marked like this:

```text
kept words [-deleted words-] kept words
```

Batch-compress a folder while preserving relative paths:

```powershell
contextcrumb batch .\docs --glob "*.md" --out .\compressed-docs
```

Show how many tokens ContextCrumb has saved:

```powershell
contextcrumb stats
contextcrumb stats --since 7d
contextcrumb stats --json
```

Compression commands write one local JSONL stats event per result by default. The ledger stores token counts and metadata, not original or compressed text. Disable logging for one command with `--no-stats`, or globally with:

```powershell
$env:CONTEXTCRUMB_STATS = "0"
```

By default, source paths are stored as basenames. Set `CONTEXTCRUMB_STATS_PATH_MODE` to `full`, `basename`, `hash`, or `none` to change that.

Golden mode is the default; use `--no-golden` for threshold mode:

```powershell
contextcrumb compress --input .\article.txt --no-golden --threshold 0.6 --json
```

Use a local model folder instead of the private Hub model:

```powershell
contextcrumb compress --model .\models\runs\YYYYMMDD-HHMMSS-name\onnx --text "A local smoke test."
```

By default, inference uses `max_length=1024` with `stride=64` for overlapping long-text windows. All windows for one document are batched together by default; set `--window-batch-size 16` to cap memory use for very long documents.

Torch backend CLI:

```powershell
contextcrumb compress --backend torch --model .\models\runs\YYYYMMDD-HHMMSS-name --device cpu --text "A local smoke test."
```

## Local Service

Use `contextcrumb serve` when an agent, MCP server, hook, or local script will call ContextCrumb repeatedly. The service loads the model once and keeps it warm, avoiding repeated model startup cost.

Install the optional service dependencies:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e ".[serve]"
```

Start the service:

```powershell
contextcrumb serve --host 127.0.0.1 --port 8765 --idle-timeout 900
```

Or start it in the background:

```powershell
contextcrumb service start --idle-timeout 3600
contextcrumb service status
```

Use the warm service from CLI commands:

```powershell
contextcrumb compress .\article.txt --use-service
contextcrumb inspect .\article.txt --use-service
contextcrumb diff .\article.txt --use-service
contextcrumb batch .\docs --glob "*.md" --out .\compressed-docs --use-service
```

Stop it explicitly:

```powershell
contextcrumb service stop
```

Endpoints:

```text
GET  /health
POST /compress
POST /compress_file
POST /shutdown
```

Example request:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8765/compress `
  -ContentType "application/json" `
  -Body '{"text":"ContextCrumb keeps the model warm for agent calls."}'
```

By default, the service loads the model before accepting requests. Use `--lazy-load` when you want the HTTP server to start first and load the model on the first compression call.

## MCP Server

ContextCrumb includes an optional MCP stdio adapter for agent clients that can run Python tools through `uvx`. Install MCP support only when you need it:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e ".[mcp]"
```

Published-package MCP config:

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

Local development config:

```json
{
  "mcpServers": {
    "contextcrumb-dev": {
      "command": "uv",
      "args": [
        "run",
        "--extra",
        "mcp",
        "contextcrumb-mcp"
      ],
      "cwd": "C:\\Users\\yuche\\OneDrive\\Documents\\Brain in a vat\\Personal Life\\ContextCrumb"
    }
  }
}
```

The MCP server exposes two tools:

```text
compress_text
compress_file
```

Both tools return the same structured payload as `CompressionResult.to_dict()`, including `text`, `original_text`, and `stats`. Token decisions are omitted by default; pass `return_tokens=true` when a client needs them.

## MCP Catalog Shrink Proxy

`contextcrumb-shrink` is a separate MCP stdio proxy for wrapping other MCP servers. It compresses upstream catalog prose before the agent sees it, while forwarding requests, tool calls, tool results, resource contents, tool names, and schemas unchanged.

```json
{
  "mcpServers": {
    "filesystem-shrunk": {
      "command": "uvx",
      "args": [
        "--from",
        "contextcrumb[mcp]",
        "contextcrumb-shrink",
        "--mode",
        "service",
        "--service-url",
        "http://127.0.0.1:8765",
        "npx",
        "@modelcontextprotocol/server-filesystem",
        "C:/Users/me/project"
      ]
    }
  }
}
```

By default it compresses top-level `description` fields in `tools`, `prompts`, `resources`, and `resourceTemplates` list responses. Use `--fields description,title` or `CONTEXTCRUMB_SHRINK_FIELDS=description,title` to opt into additional fields. `--mode model` loads ContextCrumb in the proxy process; `--mode service` uses a warm `contextcrumb service start` process.

For lower repeated-call latency, start the warm local service first:

```powershell
contextcrumb service start --idle-timeout 3600
```

Then run the MCP adapter in service mode:

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

## Model

Current private Hugging Face repo:

```text
ymao20/contextcrumb-32m
```

Training summary for the current checkpoint:

| Metric | Value |
| --- | ---: |
| Accuracy | 0.8398 |
| Macro F1 | 0.8339 |
| Delete F1 | 0.8651 |
| Keep F1 | 0.8027 |

The model is based on `jhu-clsp/ettin-encoder-32m` and is fine-tuned as a two-label token classifier:

- `DELETE`
- `KEEP`

## Repository Layout

```text
src/contextcrumb/                  # installable public Python package
tests/                             # public package tests
agent/                             # repo-owned agent skill and command templates
```

## Planned Later

These are intentionally out of scope for the first public Python release:

- JavaScript or TypeScript client.
- Local browser or Node inference.
- Modal or hosted production API.
- npm publishing.
- Monetization.

## Changelog

Release notes are tracked in [CHANGELOG.md](CHANGELOG.md).

## Development Checks

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e ".[dev,mcp]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m build
```
