"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def sample_credentials(project_root: Path) -> Path:
    creds = {
        "device_id": "tenant-camera-001",
        "auth_type": "jwt",
        "tenant": "tenant",
        "nats": {
            "urls": ["nats://portal.deviceconnect.dev:4222"],
            "jwt": "test-jwt",
            "nkey_seed": "SUATESTSEED",
        },
    }
    path = project_root / "tenant-camera-001.creds.json"
    path.write_text(json.dumps(creds), encoding="utf-8")
    return path


@pytest.fixture
def yaml_config(project_root: Path, sample_credentials: Path) -> Path:
    config = f"""\
device_connect:
  mode: portal
  credentials_file: {sample_credentials}
  messaging_backend: nats

driver:
  emit_interval: 2.0
"""
    path = project_root / "gemini2.config.yaml"
    path.write_text(config, encoding="utf-8")
    return path
