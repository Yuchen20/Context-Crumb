---
sidebar_position: 2
---

# Batch API

Batch workflows are useful for precompressing docs, notes, research folders, or benchmark inputs before sending them to a model.

## CLI Batch

Compress every Markdown file under `docs` into `compressed-docs`:

```bash
contextcrumb batch docs --glob "*.md" --out compressed-docs
```

ContextCrumb recursively matches the glob and mirrors the input directory structure in the output directory.

Example:

```text
docs/
  guide.md
  api/
    python.md

compressed-docs/
  guide.md
  api/
    python.md
```

Use an explicit keep ratio:

```bash
contextcrumb batch docs --glob "*.md" --out compressed-docs --target-keep-ratio 0.5
```

Emit machine-readable summaries:

```bash
contextcrumb batch docs --glob "*.md" --out compressed-docs --json
```

## Python Batch

For custom behavior, reuse one compressor:

```python
from pathlib import Path
from contextcrumb import ContextCompressor

input_dir = Path("docs")
output_dir = Path("compressed-docs")
compressor = ContextCompressor()

for source in input_dir.rglob("*.md"):
    relative = source.relative_to(input_dir)
    target = output_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    result = compressor.compress_file(source, target_keep_ratio=0.5)
    target.write_text(result.text, encoding="utf-8")
```

## Service-Backed Batch

If you are compressing many files from multiple processes, start the warm service once:

```bash
contextcrumb service start --allow-root docs
contextcrumb batch docs --glob "*.md" --out compressed-docs --use-service
```

This avoids repeatedly loading the model.

## Practical Defaults

| Input type | Suggested setting |
| --- | --- |
| Internal docs | Golden mode |
| Research dumps | `--target-keep-ratio 0.5` |
| Meeting notes | `--target-keep-ratio 0.5` to `0.7` |
| Logs with prose | Golden mode first, then inspect |
| Code-heavy Markdown | `--target-keep-ratio 0.75` or raw file |

Skip empty files. The CLI does this during batch runs.
