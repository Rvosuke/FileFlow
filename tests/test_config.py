"""Tests for fileflow.config — dataclass defaults, loading, saving, and helpers."""

from pathlib import Path

import pytest

from fileflow.config import (
    FileFlowConfig,
    GeneralConfig,
    SourcesConfig,
    LLMConfig,
    CategoriesConfig,
    SafetyConfig,
    DEFAULT_TOP_LEVEL_CATEGORIES,
    add_source_path,
    default_target_root,
    initialize_app,
    load_config,
    remove_source_path,
    resolve_app_paths,
    save_config,
    set_config_value,
    parse_scalar,
    _merge_dicts,
)


# ── Dataclass default values ──────────────────────────────────────────

class TestGeneralConfigDefaults:

    def test_default_values(self) -> None:
        cfg = GeneralConfig()
        assert cfg.target_root == default_target_root()
        assert cfg.dry_run is True
        assert cfg.create_shortcut is True
        assert cfg.scan_interval_minutes == 30
        assert cfg.log_level == "INFO"


class TestSourcesConfigDefaults:

    def test_default_paths_empty(self) -> None:
        cfg = SourcesConfig()
        assert cfg.paths == []

    def test_default_scan_recursive_enabled(self) -> None:
        cfg = SourcesConfig()
        assert cfg.scan_recursive is True

    def test_default_exclude_patterns(self) -> None:
        cfg = SourcesConfig()
        assert "*.tmp" in cfg.exclude_patterns
        assert "__pycache__/**" in cfg.exclude_patterns

    def test_default_size_limits(self) -> None:
        cfg = SourcesConfig()
        assert cfg.min_file_size_kb == 1
        assert cfg.max_file_size_mb == 5120


class TestLLMConfigDefaults:

    def test_default_values(self) -> None:
        cfg = LLMConfig()
        assert cfg.provider == "openclaw"
        assert cfg.ollama_model == "qwen3:8b"
        assert cfg.openai_model == "gpt-6-astra"
        assert cfg.openai_base_url == "https://api.openai.com/v1"
        assert cfg.openai_reasoning_effort == "low"
        assert cfg.temperature == 0.1
        assert cfg.batch_size == 10


class TestCategoriesConfigDefaults:

    def test_default_top_level(self) -> None:
        cfg = CategoriesConfig()
        assert cfg.top_level == list(DEFAULT_TOP_LEVEL_CATEGORIES)
        assert cfg.max_depth == 3

    def test_default_top_level_is_independent_copy(self) -> None:
        a = CategoriesConfig()
        b = CategoriesConfig()
        a.top_level.append("extra")
        assert "extra" not in b.top_level


class TestSafetyConfigDefaults:

    def test_default_protected_paths(self) -> None:
        cfg = SafetyConfig()
        assert "C:/Windows" in cfg.protected_paths
        assert cfg.log_retention_days == 90


# ── FileFlowConfig from_dict / to_dict round-trip ─────────────────────

class TestFileFlowConfig:

    def _sample_dict(self) -> dict:
        return {
            "general": {
                "target_root": "E:/Sorted",
                "dry_run": False,
                "create_shortcut": False,
                "scan_interval_minutes": 15,
                "log_level": "DEBUG",
            },
            "sources": {
                "paths": ["/tmp/downloads"],
                "scan_recursive": False,
                "exclude_patterns": ["*.log"],
                "min_file_size_kb": 5,
                "max_file_size_mb": 1024,
            },
            "llm": {
                "provider": "ollama",
                "ollama_model": "llama3:8b",
                "ollama_url": "http://localhost:11434",
                "openclaw_agent": "main",
                "openai_model": "gpt-6-astra",
                "openai_base_url": "https://api.openai.com/v1",
                "openai_reasoning_effort": "low",
                "max_tokens": 300,
                "temperature": 0.5,
                "batch_size": 20,
            },
            "categories": {
                "top_level": ["A", "B"],
                "max_depth": 2,
            },
            "safety": {
                "protected_paths": ["/usr"],
                "log_retention_days": 30,
            },
        }

    def test_from_dict_populates_fields(self) -> None:
        cfg = FileFlowConfig.from_dict(self._sample_dict())
        assert cfg.general.target_root == "E:/Sorted"
        assert cfg.general.dry_run is False
        assert cfg.sources.paths == ["/tmp/downloads"]
        assert cfg.sources.scan_recursive is False
        assert cfg.llm.provider == "ollama"
        assert cfg.llm.openai_model == "gpt-6-astra"
        assert cfg.categories.top_level == ["A", "B"]
        assert cfg.safety.log_retention_days == 30

    def test_to_dict_round_trip(self) -> None:
        original = self._sample_dict()
        cfg = FileFlowConfig.from_dict(original)
        exported = cfg.to_dict()
        assert exported == original

    def test_default_construction(self) -> None:
        cfg = FileFlowConfig()
        assert isinstance(cfg.general, GeneralConfig)
        assert isinstance(cfg.sources, SourcesConfig)
        assert isinstance(cfg.llm, LLMConfig)
        assert isinstance(cfg.categories, CategoriesConfig)
        assert isinstance(cfg.safety, SafetyConfig)


# ── resolve_app_paths ─────────────────────────────────────────────────

class TestResolveAppPaths:

    def test_paths_are_under_home(self, tmp_path: Path) -> None:
        paths = resolve_app_paths(tmp_path)
        assert paths.home == tmp_path
        assert paths.config_file == tmp_path / "config.toml"
        assert paths.database_file == tmp_path / "fileflow.db"


# ── parse_scalar ──────────────────────────────────────────────────────

class TestParseScalar:

    @pytest.mark.parametrize("raw,expected", [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("False", False),
        ("none", None),
        ("null", None),
    ])
    def test_booleans_and_none(self, raw: str, expected) -> None:
        assert parse_scalar(raw) is expected

    def test_integer(self) -> None:
        assert parse_scalar("42") == 42

    def test_float(self) -> None:
        assert parse_scalar("3.14") == pytest.approx(3.14)

    def test_string_passthrough(self) -> None:
        assert parse_scalar("hello world") == "hello world"

    def test_json_list(self) -> None:
        assert parse_scalar('["a", "b"]') == ["a", "b"]

    def test_json_dict(self) -> None:
        assert parse_scalar('{"k": 1}') == {"k": 1}


# ── _merge_dicts ──────────────────────────────────────────────────────

class TestMergeDicts:

    def test_override_flat_key(self) -> None:
        base = {"a": 1, "b": 2}
        override = {"b": 99}
        assert _merge_dicts(base, override) == {"a": 1, "b": 99}

    def test_deep_merge(self) -> None:
        base = {"x": {"y": 1, "z": 2}}
        override = {"x": {"z": 3}}
        assert _merge_dicts(base, override) == {"x": {"y": 1, "z": 3}}

    def test_base_unmodified(self) -> None:
        base = {"a": {"b": 1}}
        _merge_dicts(base, {"a": {"b": 2}})
        assert base == {"a": {"b": 1}}


# ── initialize_app / load / save round-trip ───────────────────────────

class TestInitializeAndLoadConfig:

    def test_initialize_creates_config_and_database(self, tmp_path: Path) -> None:
        home = tmp_path / "app"
        paths = initialize_app(home=home)

        assert paths.config_file.exists()
        assert paths.database_file.exists()

        config = load_config(home=home)
        assert config.general.target_root == default_target_root()
        assert config.general.dry_run is True
        assert config.llm.provider == "openclaw"
        assert config.llm.openai_model == "gpt-6-astra"

    def test_load_config_without_init_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not initialized"):
            load_config(home=tmp_path / "nonexistent")

    def test_save_and_reload_preserves_values(self, tmp_path: Path) -> None:
        home = tmp_path / "app"
        initialize_app(home=home)

        config = load_config(home=home)
        config.general.dry_run = False
        config.general.log_level = "DEBUG"
        save_config(config, home=home)

        reloaded = load_config(home=home)
        assert reloaded.general.dry_run is False
        assert reloaded.general.log_level == "DEBUG"


# ── source path management ────────────────────────────────────────────

class TestSourcePathManagement:

    def test_add_and_remove(self, tmp_path: Path) -> None:
        home = tmp_path / "app"
        initialize_app(home=home)
        config = load_config(home=home)
        source_dir = tmp_path / "Downloads"
        source_dir.mkdir()

        assert add_source_path(config, str(source_dir)) is True
        assert add_source_path(config, str(source_dir)) is False  # duplicate

        assert remove_source_path(config, str(source_dir)) is True
        assert remove_source_path(config, str(source_dir)) is False  # already gone


# ── set_config_value ──────────────────────────────────────────────────

class TestSetConfigValue:

    def test_set_known_key(self, tmp_path: Path) -> None:
        home = tmp_path / "app"
        initialize_app(home=home)
        config = load_config(home=home)

        set_config_value(config, "general.dry_run", "false")
        assert config.general.dry_run is False

    def test_set_integer_key(self, tmp_path: Path) -> None:
        home = tmp_path / "app"
        initialize_app(home=home)
        config = load_config(home=home)

        set_config_value(config, "general.scan_interval_minutes", "10")
        assert config.general.scan_interval_minutes == 10

    def test_set_openai_model(self, tmp_path: Path) -> None:
        home = tmp_path / "app"
        initialize_app(home=home)
        config = load_config(home=home)

        set_config_value(config, "llm.openai_model", "gpt-6-astra")
        set_config_value(config, "llm.provider", "openai")

        assert config.llm.openai_model == "gpt-6-astra"
        assert config.llm.provider == "openai"

    def test_bad_section_raises(self, tmp_path: Path) -> None:
        home = tmp_path / "app"
        initialize_app(home=home)
        config = load_config(home=home)

        with pytest.raises(KeyError, match="Unknown config section"):
            set_config_value(config, "bogus.key", "value")

    def test_bad_key_raises(self, tmp_path: Path) -> None:
        home = tmp_path / "app"
        initialize_app(home=home)
        config = load_config(home=home)

        with pytest.raises(KeyError, match="Unknown config key"):
            set_config_value(config, "general.nonexistent", "value")

    def test_single_part_key_raises(self, tmp_path: Path) -> None:
        home = tmp_path / "app"
        initialize_app(home=home)
        config = load_config(home=home)

        with pytest.raises(KeyError, match="dotted key"):
            set_config_value(config, "noperiod", "value")
