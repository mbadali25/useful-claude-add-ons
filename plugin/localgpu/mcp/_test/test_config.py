"""Where the install root resolves to, and how the two config layers merge."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import config


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_explicit_home_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALGPU_HOME", str(tmp_path / "elsewhere"))
    assert config.localgpu_home() == tmp_path / "elsewhere"


def test_windows_default_is_localappdata(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALGPU_HOME", raising=False)
    monkeypatch.setattr(config.os, "name", "nt")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    assert config.localgpu_home() == tmp_path / "AppData" / "Local" / "localgpu"


def test_posix_default_is_local_share(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALGPU_HOME", raising=False)
    monkeypatch.setattr(config.os, "name", "posix")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert config.localgpu_home() == tmp_path / "home" / ".local" / "share" / "localgpu"


def test_artifact_paths_hang_off_the_home(home):
    assert config.index_dir(home) == home / "index"
    assert config.vectors_path(home) == home / "index" / "vectors.f16"
    assert config.meta_path(home) == home / "index" / "meta.sqlite"
    assert config.manifest_path(home) == home / "index" / "manifest.json"
    assert config.venv_dir(home) == home / "venv"
    assert config.venv_python(home).parent.name in {"Scripts", "bin"}


def test_defaults_when_nothing_is_configured(home, tmp_path):
    settings = config.load_config(cwd=tmp_path, home=home)
    assert settings["roots"] == [str(tmp_path.resolve())]
    assert settings["embed_model"] == "nomic-embed-text"
    assert settings["chat_model"] == "qwen2.5-coder:7b-instruct-q4_K_M"
    assert settings["ollama_url"] == "http://127.0.0.1:11434"
    assert settings["embed_dim"] == 768
    assert ".git" in settings["ignore"]


def test_repo_layer_beats_the_home_layer(home, tmp_path):
    write_json(
        config.global_config_path(home),
        {"embed_model": "home-model", "chat_model": "home-chat"},
    )
    write_json(
        config.repo_config_path(tmp_path),
        {"embed_model": "repo-model", "ollama_url": "http://127.0.0.1:9999/"},
    )
    settings = config.load_config(cwd=tmp_path, home=home)
    assert settings["embed_model"] == "repo-model"
    assert settings["chat_model"] == "home-chat"
    assert settings["ollama_url"] == "http://127.0.0.1:9999"


def test_ignore_lists_union_rather_than_replace(home, tmp_path):
    write_json(config.global_config_path(home), {"ignore": ["*.tmp"]})
    write_json(config.repo_config_path(tmp_path), {"ignore": ["fixtures", "*.tmp"]})
    settings = config.load_config(cwd=tmp_path, home=home)
    assert ".git" in settings["ignore"], "the built-ins are not droppable"
    assert "*.tmp" in settings["ignore"]
    assert "fixtures" in settings["ignore"]
    assert settings["ignore"].count("*.tmp") == 1


def test_roots_are_resolved_absolute(home, tmp_path):
    target = tmp_path / "code"
    target.mkdir()
    write_json(config.repo_config_path(tmp_path), {"roots": [str(target)]})
    settings = config.load_config(cwd=tmp_path, home=home)
    assert settings["roots"] == [str(target.resolve())]
    assert all(os.path.isabs(r) for r in settings["roots"])


def test_unknown_keys_are_ignored(home, tmp_path):
    write_json(config.repo_config_path(tmp_path), {"nonsense": 1, "roots": []})
    settings = config.load_config(cwd=tmp_path, home=home)
    assert "nonsense" not in settings
    assert settings["roots"] == [str(tmp_path.resolve())]


def test_broken_json_is_reported_not_swallowed(home, tmp_path):
    path = config.repo_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(config.ConfigError) as caught:
        config.load_config(cwd=tmp_path, home=home)
    assert str(path) in str(caught.value)


def test_a_json_array_is_not_a_config(home, tmp_path):
    write_json(config.global_config_path(home), {})
    config.global_config_path(home).write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load_config(cwd=tmp_path, home=home)
