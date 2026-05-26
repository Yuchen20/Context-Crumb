---
sidebar_position: 3
---

# Core Concepts

ContextCrumb turns text into token decisions. Each token receives a keep probability. The final output is built by preserving kept tokens in original order and using minimal separators from the original text.

## Input Boundary

ContextCrumb expects natural-language text. It can be used on many context surfaces, not only files:

- Prompt text
- Older conversation turns
- Retrieved document chunks
- Subagent reports
- Natural-language tool output
- MCP descriptions

Keep exact data outside the compression boundary. For JSON, YAML, tables, code, identifiers, commands, and schemas, preserve the structure and compress only the prose values that are safe to shorten.

For example, compress `summary`, `body`, `description`, or `comment` fields, but leave `id`, `url`, `status`, `score`, `created_at`, and schema fields unchanged.

## Compression Modes

### Golden Mode

Golden mode is the default.

It finds the largest adjacent probability gap among word-like tokens and uses that as an adaptive cutoff. It also keeps at least `golden_min_keep_ratio` of word-like tokens. The default minimum is `1 / 3`.

Use golden mode when you want a conservative automatic choice:

```bash
contextcrumb load notes.md
```

### Target Keep Ratio

`target_keep_ratio` keeps the top-scoring tokens near a fixed ratio. It overrides golden mode.

Use this when you have a budget:

```bash
contextcrumb load notes.md --target-keep-ratio 0.5
```

In Python:

```python
from contextcrumb import compress

result = compress(text, target_keep_ratio=0.5)
```

### Threshold Mode

Threshold mode keeps tokens whose keep probability is at or above the threshold.

Use it when you want direct model-score control:

```bash
contextcrumb load notes.md --no-golden --threshold 0.6
```

## Sliding Windows

The model processes long inputs with sliding windows.

Defaults:

| Setting | Default |
| --- | ---: |
| `max_length` | `1024` |
| `stride` | `64` |
| `backend` | `onnx` |
| `model_id` | `ymao20/contextcrumb-32m` |

`model_windows` in the result stats tells you how many windows were used.

## Result Shape

Every API path returns or can emit the same conceptual payload:

```json
{
  "text": "compressed text",
  "original_text": "original text",
  "stats": {
    "input_tokens": 100,
    "kept_tokens": 55,
    "deleted_tokens": 45,
    "token_keep_ratio": 0.55,
    "mode": "golden",
    "backend": "onnx"
  }
}
```

When `return_tokens=True`, token decisions are included as `tokens`.
