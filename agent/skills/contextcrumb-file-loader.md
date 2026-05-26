# ContextCrumb File Loader

Use ContextCrumb when an agent needs to compress a large local text file before loading it into an LLM context window.

Do not raw-dump large candidate files with `cat`, `Get-Content`, `type`, or similar commands first. Inventory filenames, then use `contextcrumb load` to read compressed context.

## Command

```sh
contextcrumb load <file>
```

The command prints compressed text to stdout. It is intentionally quiet by default so tools and agents can capture the output and pass it directly into a prompt.

## Why Use It

- Reduces prompt tokens before a document is sent to an LLM.
- Keeps token order and deletes low-value wording instead of summarizing.
- Works locally after the model is cached, avoiding a hosted API dependency.
- Uses capped golden mode by default, so callers do not need to tune a ratio.

## When To Use

Good inputs:

- Documentation
- Notes
- Issue threads
- Logs
- Research context
- Long natural-language comments

Use raw file loading instead when exact syntax, indentation, or every token matters. For source code, either load the raw file or use a conservative budget such as:

```sh
contextcrumb load path/to/file.py --target-keep-ratio 0.75
```

## Useful Options

```sh
contextcrumb load notes.txt --target-keep-ratio 0.35
contextcrumb load notes.txt --no-golden --threshold 0.6
contextcrumb load notes.txt --json
contextcrumb load notes.txt --json --return-tokens
contextcrumb load notes.txt --model ./artifacts/onnx/contextcrumb-32m
```

Use `--json` when a caller needs compression stats such as `token_keep_ratio`, `source_path`, `model_windows`, or backend details.
Golden mode keeps at least one third of word-like tokens by default so a sharp probability gap does not erase too much context. Use `--target-keep-ratio` for an explicit fixed budget, or `--no-golden --threshold <value>` for threshold mode.
