# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Agent-facing file safety policy for `load`, `inspect`, `diff`, `batch`, service file compression, and MCP file compression.
- Optional `--receipt` output for compact compression savings summaries without changing plain compressed stdout.

## [0.1.0] - 2026-05-24

### Added

- Initial `contextcrumb` Python package for token-level context compression.
- Public Python API with `ContextCompressor`, `compress`, `compress_file`, and structured `CompressionResult` output.
- ONNX inference backend as the default runtime, with optional Torch backend support.
- CLI commands for `compress`, `load`, `inspect`, `diff`, and batch compression.
- Adaptive golden-mode compression with configurable threshold and keep-ratio controls.
- Warm local HTTP service for repeated agent, hook, and local script calls.
- Optional MCP stdio adapter via `contextcrumb[mcp]` and the `contextcrumb-mcp` console script.
- MCP tools for `compress_text` and `compress_file`, including optional warm-service mode for lower repeated-call latency.
- Test coverage for compression behavior, CLI workflows, service behavior, MCP adapter behavior, and research-helper utilities.

[Unreleased]: https://github.com/Yuchen20/Context-Crumb/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Yuchen20/Context-Crumb/releases/tag/v0.1.0
