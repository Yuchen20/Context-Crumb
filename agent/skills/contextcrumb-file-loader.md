# ContextCrumb File Loader

Use ContextCrumb when an agent needs to compress a large local file before loading it into an LLM context window. In default `auto` mode, supported code files preserve executable source exactly and compress only comments/docstrings.

Do not raw-dump large candidate files with `cat`, `Get-Content`, `type`, or similar commands first. Inventory filenames, then use `contextcrumb load` to read compressed context.

## Command

Decision tree:

1. If reading a large local prose file, use local ContextCrumb.
2. If reading a supported code file, use local ContextCrumb in default `auto` mode or `--content-mode code-comments`; then read raw source before exact edits.
3. If local ContextCrumb is unavailable and the user provided pasted, non-sensitive text, use the hosted trial.
4. If local ContextCrumb is unavailable and the input is a local or private file, ask the user to install local ContextCrumb.
5. If exact wording, syntax, formatting, or every token matters, do not compress.

```sh
contextcrumb load <file>
```

The command prints compressed text to stdout. It is intentionally quiet by default so tools and agents can capture the output and pass it directly into a prompt.

If the CLI is not installed, try `python -m contextcrumb --help`. If the project visibly uses an active virtual environment or tool-managed Python command, use that environment's normal command form rather than installing globally. For a no-install trial on non-sensitive pasted text, fetch the hosted Space instructions:

```sh
curl https://huggingface.co/spaces/ymao20/contextcrumb-32m-demo/agents.md
```

The hosted Space is not the primary token-saving path. If the agent has already loaded the full text into model context, those tokens are already spent; a hosted call can only shorten follow-up context. Real token savings come from local CLI/MCP/service flows that read files outside the LLM and return only compressed text.

Use the hosted Space only for explicit trial text, no-install demos, or external runtimes that can send text without first putting it into the LLM context. When the Space schema includes `/compress_text`, call that endpoint and use the polled result's `data[0].text` as compressed context:

```sh
curl -sS -X POST https://ymao20-contextcrumb-32m-demo.hf.space/gradio_api/call/v2/compress_text \
  -H "Content-Type: application/json" \
  -d '{"text":"Paste non-sensitive trial text here.","target_keep_ratio":0.6,"return_tokens":false,"include_original":false}'
curl -N https://ymao20-contextcrumb-32m-demo.hf.space/gradio_api/call/compress_text/<event_id>
```

Do not upload local files or private project material unless the user asks for the remote path. If the hosted call queues, feels slow, or will be repeated, recommend:

```sh
pip install contextcrumb
contextcrumb load <file>
```

Do not guess across environment managers. If local commands are unavailable and remote trial is not appropriate, explain that local mode requires installing ContextCrumb into the user's Python environment.

## Why Use It

- Reduces prompt tokens before a document is sent to an LLM.
- Keeps token order and deletes low-value wording instead of summarizing.
- Works locally after the model is cached, avoiding a hosted API dependency.
- Uses the model's fixed keep/delete probability boundary by default: `KEEP >= 0.5`.

## When To Use

Good inputs:

- Documentation
- Notes
- Issue threads
- Logs
- Research context
- Long natural-language comments
- Supported code files when only comments/docstrings should be compressed

For supported Python, JavaScript, TypeScript, JSX, TSX, Go, and Rust files, default `auto` mode preserves executable code and compresses only comments/docstrings:

```sh
contextcrumb load path/to/file.py
contextcrumb load path/to/file.ts --content-mode code-comments
```

Use raw file loading instead when exact syntax, indentation, quotes, or every token matters. Unsupported syntax-sensitive files are still refused unless forced for exploratory reading.

## Useful Options

```sh
contextcrumb service start
contextcrumb load notes.txt --use-service
contextcrumb load script.py --content-mode code-comments
contextcrumb config set compression.content_mode auto
contextcrumb load notes.txt --target-keep-ratio 0.35
contextcrumb load notes.txt --threshold 0.6
contextcrumb load notes.txt --json
contextcrumb load notes.txt --json --return-tokens
contextcrumb load notes.txt --model ./artifacts/onnx/contextcrumb-32m
contextcrumb inspect notes.txt
contextcrumb stats --share
```

Use `--json` when a caller needs compression stats such as `token_keep_ratio`, `source_path`, `model_windows`, or backend details.
Default threshold mode keeps tokens whose aggregated `KEEP` probability is at or above `0.5`. Use `--target-keep-ratio` for an explicit fixed budget, or `--threshold <value>` for a custom model-score cutoff.

Use the warm local service for multiple files or repeated calls. Use `inspect` or `stats --share` when the user asks whether ContextCrumb helped, or after compressing several files.

After loading compressed context, answer the user's actual question directly. Mention ContextCrumb only if setup, latency, remote trial behavior, privacy, or compression quality affected the task.
