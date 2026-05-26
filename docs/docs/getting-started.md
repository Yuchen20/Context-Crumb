---
sidebar_position: 2
---

# Getting Started

Install ContextCrumb with Python 3.10 or newer:

```bash
pip install contextcrumb
```

The default backend is ONNX. You do not need PyTorch or Transformers for the default install.

## Pick An Integration

Start with the smallest path that matches what you are doing:

| Goal | Command or API |
| --- | --- |
| Compress one file from a terminal | `contextcrumb load notes.md` |
| Add compression before an LLM API call | `ContextCompressor().compress(text)` |
| Compress a prompt, history, or subagent report | `compressor.compress(text)` |
| Compress prose fields in tool output | Walk the structure and compress only text values |
| Compress many files | `contextcrumb batch docs --glob "*.md" --out compressed-docs` |
| Share one warm model across tools | `contextcrumb service start` |
| Let an agent call compression tools | `contextcrumb-mcp` |

## First Compression

Create a text file:

```text title="notes.txt"
Agents spend context on notes, logs, tickets, docs, and tool descriptions. Those files contain useful facts, but they also carry filler phrases and repeated wording.
```

Compress it:

```bash
contextcrumb load notes.txt
```

`load` prints compressed text only, so agents and shell scripts can capture it directly.

For application code, use the Python API:

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()
result = compressor.compress("Long prose-heavy context about project decisions and constraints.")

print(result.text)
```

## Inspect Before Trusting

Use `inspect` to see what happened without dumping the whole compressed file:

```bash
contextcrumb inspect notes.txt
```

Use `diff` to see deleted tokens inline:

```bash
contextcrumb diff notes.txt
```

Deleted tokens are marked like this:

```text
kept words [-deleted words-] kept words
```

## Tune Compression

By default, ContextCrumb uses golden mode, an adaptive cutoff that looks for a natural probability gap while keeping at least one third of word-like tokens.

Use a fixed budget when you need predictable output size:

```bash
contextcrumb load notes.txt --target-keep-ratio 0.5
contextcrumb load notes.txt --target-keep-ratio 0.75
```

Use threshold mode when you want direct control over the model probability cutoff:

```bash
contextcrumb load notes.txt --no-golden --threshold 0.6
```

## JSON Output

Use JSON when another tool needs stats or token counts:

```bash
contextcrumb load notes.txt --json
```

The compressed text is in `text`. Useful stats live under `stats`, including token counts, keep ratios, mode, backend, and model window count.

```json
{
  "text": "compressed output",
  "stats": {
    "input_tokens": 100,
    "kept_tokens": 58,
    "deleted_tokens": 42,
    "token_keep_ratio": 0.58,
    "mode": "golden"
  }
}
```

## Optional Extras

Install extras only when you need them:

```bash
pip install "contextcrumb[mcp]"
pip install "contextcrumb[serve]"
pip install "contextcrumb[torch]"
```

Use `[mcp]` for the MCP server, `[serve]` for the local HTTP service, and `[torch]` if you want the Torch backend.
