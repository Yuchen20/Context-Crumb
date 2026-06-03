---
sidebar_position: 1
---

# Python API

Use the Python API when ContextCrumb is part of an application, script, evaluation pipeline, or local agent tool. The common pattern is to compress natural-language context before adding it to an LLM request.

ContextCrumb is not limited to files. Use it on any prose-heavy model input: user prompts, retrieved chunks, older chat turns, subagent reports, planner output, and natural-language tool results.

## Middleware Pattern

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()

def prepare_context(raw_context: str) -> str:
    result = compressor.compress(raw_context, target_keep_ratio=0.6)
    return result.text

context = prepare_context(open("notes.md", encoding="utf-8").read())
```

Create the compressor once, then reuse it. This avoids loading the model for every request.

## Compress Prompt Text

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()

def compress_user_prompt(prompt: str) -> str:
    result = compressor.compress(prompt, target_keep_ratio=0.75)
    return result.text
```

Use a conservative keep ratio for user prompts. Prompts often contain constraints that should survive.

## Compress Conversation History

```python
def compress_history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    compressed = []
    for message in messages:
        if message["role"] in {"user", "assistant"} and len(message["content"]) > 2000:
            result = compressor.compress(message["content"], target_keep_ratio=0.6)
            compressed.append({**message, "content": result.text})
        else:
            compressed.append(message)
    return compressed
```

Keep system messages and short instruction turns raw unless you have a reason to compress them.

## Compress Structured Tool Output

Do not compress raw JSON as one string when structure matters. Walk the object and compress only natural-language values.

```python
PROSE_KEYS = {"summary", "body", "description", "comment", "notes"}

def compress_tool_output(value):
    if isinstance(value, dict):
        return {
            key: (
                compressor.compress(text, target_keep_ratio=0.6).text
                if key in PROSE_KEYS and isinstance(text, str) and len(text) > 500
                else compress_tool_output(text)
            )
            for key, text in value.items()
        }
    if isinstance(value, list):
        return [compress_tool_output(item) for item in value]
    return value
```

This preserves keys, ids, numbers, URLs, and schema shape while shrinking long prose fields.

## One-Off Compression

```python
from contextcrumb import compress

text = "Agents spend context on long notes, docs, tickets, and logs."
result = compress(text)

print(result.text)
print(result.stats)
```

`compress()` loads a compressor for the call. For repeated calls, create a `ContextCompressor` once and reuse it.

## Reuse A Warm Compressor

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()

first = compressor.compress("First long input.")
second = compressor.compress("Second long input.")

print(first.text)
print(second.stats["token_keep_ratio"])
```

## Compress A File

```python
from contextcrumb import compress_file

result = compress_file("notes.md")
print(result.text)
```

Or reuse a compressor:

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()
result = compressor.compress_file("notes.md", encoding="utf-8")
```

## Explicit Keep Ratio

```python
result = compressor.compress(
    text,
    target_keep_ratio=0.5,
)
```

`target_keep_ratio` overrides threshold mode and keeps the top-scoring tokens near the requested ratio.

## Threshold Mode

```python
result = compressor.compress(
    text,
    threshold=0.6,
)
```

Threshold mode keeps tokens with keep probability greater than or equal to the threshold.

## Token Decisions

```python
result = compressor.compress(
    text,
    return_tokens=True,
)

for token in result.tokens:
    print(token.text, token.keep_prob, token.keep)
```

Each `TokenDecision` has:

| Field | Meaning |
| --- | --- |
| `text` | Token text |
| `start` | Character start offset |
| `end` | Character end offset |
| `keep_prob` | Model probability that the token should be kept |
| `keep` | Final keep/delete decision |

## Result Object

`CompressionResult` contains:

| Field | Meaning |
| --- | --- |
| `text` | Compressed output |
| `original_text` | Original input |
| `stats` | Compression and runtime metadata |
| `tokens` | Optional token decisions |

Convert to a dict:

```python
payload = result.to_dict()
payload_with_tokens = result.to_dict(include_tokens=True)
```

## Constructor Options

```python
compressor = ContextCompressor(
    model_id="ymao20/contextcrumb-32m",
    backend="onnx",
    device="auto",
    revision=None,
    cache_dir=None,
    max_length=1024,
    stride=64,
    window_batch_size=None,
)
```

Use `backend="torch"` only after installing:

```bash
pip install "contextcrumb[torch]"
```

## API Reference

### `compress(text, ...)`

Loads a compressor, compresses one string, and returns `CompressionResult`.

Important keyword arguments:

| Argument | Default | Meaning |
| --- | --- | --- |
| `model_id` | `ymao20/contextcrumb-32m` | Hugging Face model id or local model path |
| `backend` | `onnx` | Inference backend: `onnx` or `torch` |
| `device` | `auto` | Inference device |
| `target_keep_ratio` | `None` | Fixed token budget; overrides threshold mode |
| `golden` | `True` | Deprecated compatibility flag; threshold mode is used by default |
| `threshold` | `0.5` | Probability cutoff used when `target_keep_ratio` is not set |
| `return_tokens` | `False` | Include token-level decisions |

### `compress_file(path, ...)`

Reads a text file and compresses it. It accepts the same compression options plus `encoding`.

### `ContextCompressor`

Use this class for repeated calls. It exposes:

| Method | Use |
| --- | --- |
| `compress(text, ...)` | Compress one string |
| `compress_file(path, ...)` | Read and compress one text file |
| `score_keep_probabilities(text)` | Inspect raw token scores |

### `CompressionResult`

| Field | Use |
| --- | --- |
| `text` | Compressed context |
| `original_text` | Original input |
| `stats` | Counts, mode, backend, model window metadata |
| `tokens` | Optional token decisions when `return_tokens=True` |
