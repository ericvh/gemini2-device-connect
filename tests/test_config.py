"""Tests for configuration loading."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from gemini2_device_connect.config import (
    AppConfig,
    DeviceConnectSettings,
    apply_portal_env,
    discover_config_path,
    find_credentials_file,
    load_config,
    load_credentials_metadata,
)


def test_discover_config_path_prefers_explicit(project_root: Path, yaml_config: Path):
    assert discover_config_path(str(yaml_config), project_root) == yaml_config.resolve()


def test_load_yaml_config(project_root: Path, yaml_config: Path):
    app = load_config(config_path=str(yaml_config), project_root=project_root)
    assert app.config_path == yaml_config.resolve()
    assert app.device_connect.mode == "portal"
    assert app.driver.emit_interval == 2.0
    assert app.use_portal is True
    assert app.allow_insecure is False


def test_load_json_config(project_root: Path, sample_credentials: Path):
    config = {
        "device_connect": {
            "mode": "d2d",
            "allow_insecure": True,
        },
        "driver": {"emit_interval": 0.5},
    }
    path = project_root / "gemini2.config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    app = load_config(config_path=str(path), project_root=project_root)
    assert app.device_connect.mode == "d2d"
    assert app.use_portal is False
    assert app.allow_insecure is True
    assert app.driver.emit_interval == 0.5


def test_auto_mode_uses_portal_when_credentials_present(
    project_root: Path, sample_credentials: Path
):
    app = load_config(
        project_root=project_root,
        cli_overrides={"credentials_file": str(sample_credentials), "mode": "auto"},
    )
    assert app.use_portal is True
    assert app.resolved_credentials_file == sample_credentials.resolve()


def test_find_credentials_file_by_device_id(
    project_root: Path, sample_credentials: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HOME", str(project_root))
    found = find_credentials_file(None, device_id="tenant-camera-001")
    assert found == sample_credentials.resolve()


def test_apply_portal_env_sets_nats_variables(
    project_root: Path, sample_credentials: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("NATS_URL", raising=False)
    monkeypatch.delenv("DEVICE_ID", raising=False)
    monkeypatch.delenv("MESSAGING_BACKEND", raising=False)
    monkeypatch.delenv("DEVICE_CONNECT_ALLOW_INSECURE", raising=False)

    app = AppConfig(
        device_connect=DeviceConnectSettings(
            mode="portal",
            credentials_file=str(sample_credentials),
        )
    )
    apply_portal_env(app)

    assert os.environ["NATS_CREDENTIALS_FILE"] == str(sample_credentials.resolve())
    assert os.environ["NATS_URL"] == "nats://portal.deviceconnect.dev:4222"
    assert os.environ["MESSAGING_BACKEND"] == "nats"
    assert os.environ["DEVICE_ID"] == "tenant-camera-001"
    assert "DEVICE_CONNECT_ALLOW_INSECURE" not in os.environ


def test_load_credentials_metadata(sample_credentials: Path):
    metadata = load_credentials_metadata(sample_credentials)
    assert metadata["device_id"] == "tenant-camera-001"
    assert metadata["tenant"] == "tenant"
