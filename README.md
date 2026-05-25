<p align="center">
  <img src="docs/assets/contextcrumb-banner.png" alt="ContextCrumb banner" width="100%" />
</p>

<h1 align="center">ContextCrumb</h1>

<p align="center">
  <strong>Shake the crumbs out of bloated context.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue?style=flat" alt="Python >=3.10">
  <a href="https://huggingface.co/ymao20/contextcrumb-32m"><img src="https://img.shields.io/badge/model-contextcrumb--32m-ffcc4d?style=flat" alt="Hugging Face model"></a>
  <a href="https://huggingface.co/ymao20/contextcrumb-32m"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fhuggingface.co%2Fapi%2Fmodels%2Fymao20%2Fcontextcrumb-32m&query=%24.downloads&label=model%20downloads&color=ffcc4d&style=flat" alt="Hugging Face model downloads"></a>
  <a href="https://huggingface.co/ymao20/contextcrumb-32m"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fhuggingface.co%2Fapi%2Fmodels%2Fymao20%2Fcontextcrumb-32m&query=%24.likes&label=model%20likes&color=ffcc4d&style=flat" alt="Hugging Face model likes"></a>
  <a href="https://github.com/Yuchen20/Context-Crumb/stargazers"><img src="https://img.shields.io/github/stars/Yuchen20/Context-Crumb?style=flat&color=yellow" alt="GitHub stars"></a>
  <a href="https://github.com/Yuchen20/Context-Crumb/commits/main"><img src="https://img.shields.io/github/last-commit/Yuchen20/Context-Crumb?style=flat" alt="Last commit"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Yuchen20/Context-Crumb?style=flat" alt="License"></a>
  <img src="https://visitor-badge.laobi.icu/badge?page_id=Yuchen20.Context-Crumb" alt="Visitors">
</p>

<p align="center">
  <a href="#before-after">Before / After</a> -
  <a href="https://huggingface.co/spaces/ymao20/contextcrumb-32m-demo">Playground</a> -
  <a href="#install">Install</a> -
  <a href="#quick-start">Quick Start</a> -
  <a href="#cli">CLI</a> -
  <a href="#agent-mcp">Agent + MCP</a> -
  <a href="#model">Model</a>
</p>

---

LLM context gets messy fast: meeting notes, logs, issue threads, docs, transcripts, and tool descriptions all pile up until the useful signal is buried under filler.

**ContextCrumb** is a token-level compressor for LLM and agent workflows. It looks at text word by word and removes low-signal tokens while keeping the surviving text in the original order.

That is the idea behind the name: the context is still there, but the loose crumbs are shaken off before they reach your model. Less bloat in the prompt. More room for the parts that matter.

<p align="center">
  <a href="https://huggingface.co/spaces/ymao20/contextcrumb-32m-demo">
    <img src="https://img.shields.io/badge/Try%20the%20playground-ContextCrumb--32M%20Demo-ffcc4d?style=for-the-badge" alt="Try the ContextCrumb-32M Demo">
  </a>
</p>

<p align="center">
  <sub>No install needed. Paste text, compare the kept context, and see what gets shaken off.</sub>
</p>

<h2 id="before-after">Before / After</h2>

ContextCrumb is not a summarizer. It does not rewrite your document into a new explanation. It keeps the source sequence and deletes expendable words.

**Original**

```text
ContextCrumb is designed for coding agents, MCP tools, and prompt pipelines that need to read a large local text file before sending it to an LLM. It prints only the compressed text by default, so an agent can capture stdout and use it as shortened context.
```

**Compressed**

```text
ContextCrumb designed coding agents, MCP tools, prompt pipelines need read large local text file before sending LLM. Prints compressed text default, agent capture stdout use shortened context.
```

Same order. Less padding. More room for the next file.

## Why ContextCrumb?

| Use case | What changes |
| --- | --- |
| Agent file loading | Read long notes, docs, transcripts, and logs before they hit the context window. |
| Prompt pipelines | Shrink natural-language inputs without hand-writing summarizers. |
| MCP catalogs | Compress verbose tool/resource descriptions while preserving names and schemas. |
| Local workflows | Run ONNX inference by default, with cached model files after first download. |
| Trust-building | Use `diff` and `inspect` to see what was kept, deleted, and saved. |

Best fit: docs, notes, transcripts, issue threads, logs, research context, and other natural-language files. For source code where exact syntax matters, prefer raw file loading or use a conservative keep ratio.

<h2 id="install">Install</h2>

```bash
pip install contextcrumb
```

Optional extras:

```bash
pip install "contextcrumb[mcp]"
pip install "contextcrumb[serve]"
pip install "contextcrumb[torch]"
```

ContextCrumb uses the ONNX backend by default, so normal users do not need PyTorch or Transformers installed. Model files are cached locally after the first download.

<h2 id="quick-start">Quick Start</h2>

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()

result = compressor.compress(
    "ContextCrumb deletes low-value words while preserving useful context.",
)

print(result.text)
print(result.stats)
```

Read and compress a file:

```python
from contextcrumb import ContextCompressor

compressor = ContextCompressor()
result = compressor.compress_file("notes.txt")

print(result.text)
print(result.stats["token_keep_ratio"])
```

<h2 id="cli">CLI</h2>

The main agent-friendly command is `load`:

```bash
contextcrumb load notes.txt
```

It prints only compressed text by default, which makes it easy for agents, hooks, shell scripts, and prompt pipelines to capture stdout and move on.

Useful commands:

```bash
contextcrumb load notes.txt --json
contextcrumb diff notes.txt
contextcrumb inspect notes.txt
contextcrumb stats
```

`diff` marks deleted tokens like this:

```text
kept words [-deleted words-] kept words
```

<h2 id="agent-mcp">Agent + MCP</h2>

ContextCrumb includes an optional MCP stdio adapter for agent clients that can run Python tools through `uvx`.

```bash
pip install "contextcrumb[mcp]"
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

The MCP server exposes:

```text
compress_text
compress_file
```

ContextCrumb also ships `contextcrumb-shrink`, an MCP proxy that compresses verbose catalog descriptions before an agent sees them while forwarding tool names, schemas, calls, results, and resource contents unchanged.

<h2 id="model">Model</h2>

Model weights and a hosted demo are public on Hugging Face:

- Model: [ymao20/contextcrumb-32m](https://huggingface.co/ymao20/contextcrumb-32m)
- Playground: [contextcrumb-32m-demo](https://huggingface.co/spaces/ymao20/contextcrumb-32m-demo)

## Roadmap

Planned for later:

- Public docs for advanced compression modes and service deployment.
- JavaScript or TypeScript client.
- Hosted API experiments.
- npm publishing.

## Development

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e ".[dev,mcp]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m build
```

Release notes are tracked in [CHANGELOG.md](CHANGELOG.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
