"""Persistent configuration for ContextCrumb."""

from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from contextcrumb.compressor import DEFAULT_THRESHOLD


CONTENT_MODES = ("auto", "prose", "code-comments", "raw", "refuse")
UNSUPPORTED_CODE_POLICIES = ("refuse", "prose", "raw")
PROJECT_CONFIG_NAME = "contextcrumb.toml"
CONFIG_ENV_VAR = "CONTEXTCRUMB_CONFIG"


@dataclass(frozen=True)
class CompressionConfig:
    content_mode: str = "auto"
    threshold: float = DEFAULT_THRESHOLD
    target_keep_ratio: float | None = None


@dataclass(frozen=True)
class CodeConfig:
    comment_target_keep_ratio: float | None = 0.55
    docstring_target_keep_ratio: float | None = 0.65
    compress_string_literals: bool = False
    languages: list[str] = field(
        default_factory=lambda: ["python", "javascript", "typescript", "jsx", "tsx", "go", "rust"]
    )
    unsupported_code: str = "refuse"


@dataclass(frozen=True)
class ContextCrumbConfig:
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    code: CodeConfig = field(default_factory=CodeConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_user_config_path() -> Path:
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / "contextcrumb" / "config.toml"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "contextcrumb" / "config.toml"


def project_config_path(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        candidate = directory / PROJECT_CONFIG_NAME
        if candidate.exists():
            return candidate
    return None


def parse_config_text(text: str) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.10 fallback
        tomllib = None
    if tomllib is not None:
        return dict(tomllib.loads(text))
    return _parse_minimal_toml(text)


def _parse_minimal_toml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    section: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            section = data.setdefault(name, {})
            continue
        if "=" not in line:
            continue
        key, raw_value = (part.strip() for part in line.split("=", 1))
        target = section if section is not None else data
        target[key] = _parse_value(raw_value)
    return data


def _parse_value(raw_value: str) -> Any:
    value = raw_value.strip()
    if value == "null":
        return None
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(part.strip()) for part in inner.split(",")]
    try:
        if any(char in value for char in ".eE"):
            return float(value)
        return int(value)
    except ValueError:
        return value


def format_config(config: ContextCrumbConfig) -> str:
    data = config.to_dict()
    lines: list[str] = []
    for section_name in ("compression", "code"):
        lines.append(f"[{section_name}]")
        section = data[section_name]
        for key, value in section.items():
            lines.append(f"{key} = {_format_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    return str(value)


def load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return parse_config_text(path.read_text(encoding="utf-8"))


def merge_config(base: ContextCrumbConfig, data: dict[str, Any]) -> ContextCrumbConfig:
    compression_data = {**asdict(base.compression), **dict(data.get("compression") or {})}
    code_data = {**asdict(base.code), **dict(data.get("code") or {})}
    compression = CompressionConfig(
        content_mode=_validate_choice(
            "compression.content_mode",
            str(compression_data["content_mode"]),
            CONTENT_MODES,
        ),
        threshold=float(compression_data["threshold"]),
        target_keep_ratio=_optional_float(compression_data["target_keep_ratio"]),
    )
    code = CodeConfig(
        comment_target_keep_ratio=_optional_float(code_data["comment_target_keep_ratio"]),
        docstring_target_keep_ratio=_optional_float(code_data["docstring_target_keep_ratio"]),
        compress_string_literals=bool(code_data["compress_string_literals"]),
        languages=[str(language) for language in list(code_data["languages"])],
        unsupported_code=_validate_choice(
            "code.unsupported_code",
            str(code_data["unsupported_code"]),
            UNSUPPORTED_CODE_POLICIES,
        ),
    )
    return ContextCrumbConfig(compression=compression, code=code)


def resolve_config(*, start: Path | None = None, include_project: bool = True) -> ContextCrumbConfig:
    config = ContextCrumbConfig()
    config = merge_config(config, load_config_file(default_user_config_path()))
    if include_project:
        project_path = project_config_path(start)
        if project_path is not None:
            config = merge_config(config, load_config_file(project_path))
    return config


def set_config_value(config: ContextCrumbConfig, dotted_key: str, value: Any) -> ContextCrumbConfig:
    data = config.to_dict()
    section, key = split_dotted_key(dotted_key)
    if key not in data[section]:
        raise KeyError(f"Unknown config key: {dotted_key}")
    data[section][key] = _coerce_config_value(section, key, value)
    return merge_config(ContextCrumbConfig(), data)


def unset_config_value(config: ContextCrumbConfig, dotted_key: str) -> ContextCrumbConfig:
    section, key = split_dotted_key(dotted_key)
    default_data = ContextCrumbConfig().to_dict()
    return set_config_value(config, dotted_key, default_data[section][key])


def split_dotted_key(dotted_key: str) -> tuple[str, str]:
    if "." not in dotted_key:
        raise KeyError("Use dotted config keys such as compression.content_mode")
    section, key = dotted_key.split(".", 1)
    if section not in {"compression", "code"}:
        raise KeyError(f"Unknown config section: {section}")
    return section, key


def _coerce_config_value(section: str, key: str, value: Any) -> Any:
    if isinstance(value, str):
        value = _parse_value(value)
    if section == "compression" and key == "content_mode":
        return _validate_choice("compression.content_mode", str(value), CONTENT_MODES)
    if section == "compression" and key in {"threshold", "target_keep_ratio"}:
        return _optional_float(value)
    if section == "code" and key in {"comment_target_keep_ratio", "docstring_target_keep_ratio"}:
        return _optional_float(value)
    if section == "code" and key == "compress_string_literals":
        return bool(value)
    if section == "code" and key == "languages":
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item) for item in value]
    if section == "code" and key == "unsupported_code":
        return _validate_choice("code.unsupported_code", str(value), UNSUPPORTED_CODE_POLICIES)
    return value


def _optional_float(value: Any) -> float | None:
    if value is None or value == "null":
        return None
    return float(value)


def _validate_choice(name: str, value: str, choices: tuple[str, ...]) -> str:
    if value not in choices:
        raise ValueError(f"{name} must be one of: {', '.join(choices)}")
    return value
