---
sidebar_position: 1
sidebar_label: App Integration
---

# App Integration Examples

These examples show ContextCrumb as a middleware layer: raw natural-language context goes in, compressed context goes into the next LLM call.

## Compress Before A Prompt Call

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()

raw_context = open("research-notes.md", encoding="utf-8").read()
compressed = compressor.compress(raw_context, target_keep_ratio=0.5)

prompt = f"""Use this compressed context to answer the question.

Context:
{compressed.text}

Question:
What are the main implementation risks?
"""
```

## Build A Reusable Context Loader

```python
from pathlib import Path
from contextcrumb import ContextCompressor

compressor = ContextCompressor()

def load_context(path: str, keep_ratio: float = 0.6) -> str:
    result = compressor.compress_file(
        Path(path),
        target_keep_ratio=keep_ratio,
    )
    return result.text

context = load_context("docs/architecture.md")
```

## Compress A Long User Prompt

Use a conservative ratio for prompts. A user prompt may contain constraints, preferences, or acceptance criteria.

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()

def prepare_user_prompt(prompt: str) -> str:
    if len(prompt) < 4000:
        return prompt
    return compressor.compress(prompt, target_keep_ratio=0.75).text

user_prompt = prepare_user_prompt(raw_user_prompt)
```

Do not compress short prompts or exact instructions unless you can tolerate losing wording.

## Compress Older Conversation History

Compress older verbose turns before replaying a conversation into another model call. Keep the latest user request raw.

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()

def prepare_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    prepared = []
    latest_index = len(messages) - 1

    for index, message in enumerate(messages):
        content = message["content"]
        should_compress = (
            index < latest_index
            and message["role"] in {"user", "assistant"}
            and len(content) > 2000
        )
        if should_compress:
            content = compressor.compress(content, target_keep_ratio=0.6).text
        prepared.append({**message, "content": content})

    return prepared
```

Keep system messages raw by default.

## Compress Subagent Output

Research agents and planning agents often return long narrative reports. Compress those reports before handing them to the next agent.

```python
def prepare_subagent_report(report: str) -> str:
    result = compressor.compress(
        report,
        target_keep_ratio=0.55,
    )
    return result.text

main_agent_context = prepare_subagent_report(research_agent_output)
```

Use `return_tokens=True` during evaluation if you want to inspect what is being removed.

## Compress Natural-Language Tool Results

Tool output often mixes exact fields with prose. Preserve the object shape and compress only long natural-language values.

```python
from typing import Any
from contextcrumb import ContextCompressor

compressor = ContextCompressor()
PROSE_KEYS = {"summary", "body", "description", "comment", "notes", "text"}

def compress_tool_result(value: Any) -> Any:
    if isinstance(value, dict):
        compressed = {}
        for key, item in value.items():
            if key in PROSE_KEYS and isinstance(item, str) and len(item) > 500:
                compressed[key] = compressor.compress(
                    item,
                    target_keep_ratio=0.6,
                ).text
            else:
                compressed[key] = compress_tool_result(item)
        return compressed

    if isinstance(value, list):
        return [compress_tool_result(item) for item in value]

    return value
```

This keeps ids, URLs, numbers, timestamps, statuses, and schema fields unchanged.

Avoid this pattern:

```python
import json

bad = compressor.compress(json.dumps(tool_result)).text
```

Compressing the whole JSON string can damage structure and make downstream parsing unreliable.

## Preserve Token Decisions For Review

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()
result = compressor.compress_file("notes.md", return_tokens=True)

deleted = [token.text for token in result.tokens if not token.keep]
print(result.text)
print(f"Deleted {len(deleted)} tokens")
```

## Compress Markdown But Keep Code Raw

For code-heavy Markdown, split your pipeline:

1. Send prose sections through ContextCrumb.
2. Preserve fenced code blocks exactly.
3. Reassemble the prompt with compressed prose and raw code.

Use this approach for READMEs, design docs, and notebooks where commands or snippets must remain exact.

## Reuse The Warm Service From Python

```python
import requests

response = requests.post(
    "http://127.0.0.1:8765/compress",
    json={
        "text": "Long prose-heavy input.",
        "target_keep_ratio": 0.5,
    },
    timeout=30,
)

payload = response.json()
print(payload["text"])
```

Start the service first:

```bash
contextcrumb service start
```
