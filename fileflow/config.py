from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any
import tomllib

import tomli_w


DEFAULT_TOP_LEVEL_CATEGORIES = [
    "文档",
    "代码项目",
    "图片与设计",
    "安装包",
    "压缩包",
    "视频音频",
    "其他",
]


@dataclass(slots=True)
class GeneralConfig:
    target_root: str = "D:/Organized"
    dry_run: bool = True
    create_shortcut: bool = True
    scan_interval_minutes: int = 30
    log_level: str = "INFO"


@dataclass(slots=True)
class SourcesConfig:
    paths: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(
        default_factory=lambda: [
            "*.tmp",
            "*.crdownload",
            "Thumbs.db",
            "desktop.ini",
            ".git/**",
            "node_modules/**",
            "__pycache__/**",
        ]
    )
    min_file_size_kb: int = 1
    max_file_size_mb: int = 5120


@dataclass(slots=True)
class LLMConfig:
    provider: str = "openclaw"
    ollama_model: str = "qwen3:8b"
    ollama_url: str = "http://localhost:11434"
    max_tokens: int = 500
    temperature: float = 0.1
    batch_size: int = 10


@dataclass(slots=True)
class CategoriesConfig:
    top_level: list[str] = field(default_factory=lambda: list(DEFAULT_TOP_LEVEL_CATEGORIES))
    max_depth: int = 3


@dataclass(slots=True)
class SafetyConfig:
    protected_paths: list[str] = field(
        default_factory=lambda: [
            "C:/Windows",
            "C:/Program Files",
        ]
    )
    log_retention_days: int = 90


@dataclass(slots=True)
class FileFlowConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    categories: CategoriesConfig = field(default_factory=CategoriesConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileFlowConfig":
        return cls(
            general=GeneralConfig(**data["general"]),
            sources=SourcesConfig(**data["sources"]),
            llm=LLMConfig(**data["llm"]),
            categories=CategoriesConfig(**data["categories"]),
            safety=SafetyConfig(**data["safety"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "general": {
                "target_root": self.general.target_root,
                "dry_run": self.general.dry_run,
                "create_shortcut": self.general.create_shortcut,
                "scan_interval_minutes": self.general.scan_interval_minutes,
                "log_level": self.general.log_level,
            },
            "sources": {
                "paths": self.sources.paths,
                "exclude_patterns": self.sources.exclude_patterns,
                "min_file_size_kb": self.sources.min_file_size_kb,
                "max_file_size_mb": self.sources.max_file_size_mb,
            },
            "llm": {
                "provider": self.llm.provider,
                "ollama_model": self.llm.ollama_model,
                "ollama_url": self.llm.ollama_url,
                "max_tokens": self.llm.max_tokens,
                "temperature": self.llm.temperature,
                "batch_size": self.llm.batch_size,
            },
            "categories": {
                "top_level": self.categories.top_level,
                "max_depth": self.categories.max_depth,
            },
            "safety": {
                "protected_paths": self.safety.protected_paths,
                "log_retention_days": self.safety.log_retention_days,
            },
        }


@dataclass(slots=True)
class AppPaths:
    home: Path
    config_file: Path
    database_file: Path


def get_app_home() -> Path:
    override = os.getenv("FILEFLOW_HOME")
    if override:
        return Path(override).expanduser()

    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "FileFlow"

    return Path.home() / ".fileflow"


def resolve_app_paths(home: Path | None = None) -> AppPaths:
    app_home = home or get_app_home()
    return AppPaths(
        home=app_home,
        config_file=app_home / "config.toml",
        database_file=app_home / "fileflow.db",
    )


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_template_path() -> Path:
    return project_root() / "config" / "default.toml"


def load_default_config_dict() -> dict[str, Any]:
    return tomllib.loads(default_template_path().read_text(encoding="utf-8"))


def build_runtime_default_config_dict() -> dict[str, Any]:
    config = load_default_config_dict()
    config["sources"]["paths"] = []
    return config


def initialize_app(home: Path | None = None, force: bool = False) -> AppPaths:
    paths = resolve_app_paths(home)
    paths.home.mkdir(parents=True, exist_ok=True)

    if force or not paths.config_file.exists():
        runtime_defaults = build_runtime_default_config_dict()
        paths.config_file.write_text(tomli_w.dumps(runtime_defaults), encoding="utf-8")

    from fileflow.db.operations import Database

    Database(paths.database_file).initialize()
    return paths


def is_initialized(home: Path | None = None) -> bool:
    paths = resolve_app_paths(home)
    return paths.config_file.exists() and paths.database_file.exists()


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(home: Path | None = None) -> FileFlowConfig:
    paths = resolve_app_paths(home)
    if not paths.config_file.exists():
        raise FileNotFoundError("FileFlow is not initialized. Run `fileflow init` first.")

    default_config = load_default_config_dict()
    user_config = tomllib.loads(paths.config_file.read_text(encoding="utf-8"))
    merged = _merge_dicts(default_config, user_config)
    return FileFlowConfig.from_dict(merged)


def save_config(config: FileFlowConfig, home: Path | None = None) -> Path:
    paths = resolve_app_paths(home)
    paths.home.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text(tomli_w.dumps(config.to_dict()), encoding="utf-8")
    return paths.config_file


def normalize_path(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def add_source_path(config: FileFlowConfig, value: str) -> bool:
    normalized = normalize_path(value)
    existing = {normalize_path(path).casefold(): path for path in config.sources.paths}
    if normalized.casefold() in existing:
        return False
    config.sources.paths.append(normalized)
    config.sources.paths.sort(key=str.casefold)
    return True


def remove_source_path(config: FileFlowConfig, value: str) -> bool:
    normalized = normalize_path(value).casefold()
    remaining = [path for path in config.sources.paths if normalize_path(path).casefold() != normalized]
    changed = len(remaining) != len(config.sources.paths)
    config.sources.paths = remaining
    return changed


def parse_scalar(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"none", "null"}:
        return None

    if value.startswith("[") or value.startswith("{"):
        return json.loads(value)

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        pass

    return value


def set_config_value(config: FileFlowConfig, dotted_key: str, raw_value: str) -> None:
    data = config.to_dict()
    parts = dotted_key.split(".")
    if len(parts) < 2:
        raise KeyError("Use a dotted key such as `general.dry_run`.")

    current: dict[str, Any] = data
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            raise KeyError(f"Unknown config section: {part}")
        current = next_value

    leaf = parts[-1]
    if leaf not in current:
        raise KeyError(f"Unknown config key: {dotted_key}")

    current[leaf] = parse_scalar(raw_value)

    updated = FileFlowConfig.from_dict(_merge_dicts(load_default_config_dict(), data))
    config.general = updated.general
    config.sources = updated.sources
    config.llm = updated.llm
    config.categories = updated.categories
    config.safety = updated.safety
