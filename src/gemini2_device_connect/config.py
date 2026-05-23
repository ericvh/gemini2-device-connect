"""Configuration loading for the Gemini 2 Device Connect driver."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - pyyaml is a declared dependency
    yaml = None


DEFAULT_CONFIG_NAMES = (
    "gemini2.config.yaml",
    "gemini2.config.yml",
    "gemini2.config.json",
    "config/gemini2.config.yaml",
)


@dataclass
class DriverSettings:
    """Resolved runtime settings for publishing camera streams."""

    emit_interval: float = 1.0


@dataclass
class DeviceConnectSettings:
    """Device Connect mesh / portal connection settings."""

    mode: str = "auto"  # auto | portal | d2d
    credentials_file: Optional[str] = None
    device_id: Optional[str] = None
    tenant: Optional[str] = None
    messaging_backend: Optional[str] = None
    nats_url: Optional[str] = None
    allow_insecure: Optional[bool] = None


@dataclass
class AppConfig:
    """Full application configuration."""

    device_connect: DeviceConnectSettings = field(default_factory=DeviceConnectSettings)
    driver: DriverSettings = field(default_factory=DriverSettings)
    config_path: Optional[Path] = None

    @property
    def resolved_credentials_file(self) -> Optional[Path]:
        return find_credentials_file(
            self.device_connect.credentials_file,
            self.device_connect.device_id,
        )

    @property
    def use_portal(self) -> bool:
        mode = self.device_connect.mode.lower()
        if mode == "portal":
            return True
        if mode == "d2d":
            return False
        return self.resolved_credentials_file is not None

    @property
    def allow_insecure(self) -> bool:
        if self.device_connect.allow_insecure is not None:
            return self.device_connect.allow_insecure
        return not self.use_portal


def expand_path(path: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(path))).resolve()


def _load_file_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
    else:
        if yaml is None:
            raise RuntimeError(
                f"PyYAML is required to read {path.name}. Install pyyaml or use JSON config."
            )
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return data


def discover_config_path(explicit: Optional[str] = None, project_root: Optional[Path] = None) -> Optional[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(expand_path(explicit))
    env_path = os.getenv("GEMINI2_CONFIG")
    if env_path:
        candidates.append(expand_path(env_path))

    root = project_root or Path.cwd()
    for name in DEFAULT_CONFIG_NAMES:
        candidates.append((root / name).resolve())

    for path in candidates:
        if path.is_file():
            return path
    return None


def find_credentials_file(
    explicit: Optional[str],
    device_id: Optional[str] = None,
) -> Optional[Path]:
    """Locate a Device Connect portal credentials file."""
    seen: set[Path] = set()
    candidates: list[Path] = []

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(resolved)

    if explicit:
        add(expand_path(explicit))

    env_file = os.getenv("NATS_CREDENTIALS_FILE")
    if env_file:
        add(expand_path(env_file))

    home = Path.home()
    if device_id:
        add(home / f"{device_id}.creds.json")
        add(home / ".device-connect" / "credentials" / f"{device_id}.creds.json")
        add(home / ".device-connect" / "credentials" / f"{device_id}.creds")

    creds_dir = home / ".device-connect" / "credentials"
    if creds_dir.is_dir():
        for path in sorted(creds_dir.glob("*.creds.json")):
            add(path)
        for path in sorted(creds_dir.glob("*.creds")):
            add(path)

    for path in sorted(home.glob("*.creds.json")):
        add(path)

    if device_id:
        for path in candidates:
            if path.is_file() and device_id in path.name:
                return path

    for path in candidates:
        if path.is_file():
            return path
    return None


def _merge_device_connect(raw: dict[str, Any]) -> DeviceConnectSettings:
    dc = DeviceConnectSettings()
    for key in (
        "mode",
        "credentials_file",
        "device_id",
        "tenant",
        "messaging_backend",
        "nats_url",
    ):
        if key in raw and raw[key] not in (None, ""):
            setattr(dc, key, raw[key])
    if "allow_insecure" in raw:
        dc.allow_insecure = bool(raw["allow_insecure"])
    return dc


def _merge_driver(raw: dict[str, Any]) -> DriverSettings:
    driver = DriverSettings()
    if "emit_interval" in raw and raw["emit_interval"] is not None:
        driver.emit_interval = float(raw["emit_interval"])
    return driver


def load_config(
    *,
    config_path: Optional[str] = None,
    project_root: Optional[Path] = None,
    cli_overrides: Optional[dict[str, Any]] = None,
) -> AppConfig:
    """Load config from file, then apply environment and CLI overrides."""
    path = discover_config_path(config_path, project_root)
    data: dict[str, Any] = {}
    if path:
        data = _load_file_config(path)

    app = AppConfig(
        device_connect=_merge_device_connect(data.get("device_connect", {})),
        driver=_merge_driver(data.get("driver", {})),
        config_path=path,
    )

    _apply_env_overrides(app)
    if cli_overrides:
        _apply_cli_overrides(app, cli_overrides)
    return app


def _apply_env_overrides(app: AppConfig) -> None:
    dc = app.device_connect

    if mode := os.getenv("DEVICE_CONNECT_MODE"):
        dc.mode = mode
    if creds := os.getenv("NATS_CREDENTIALS_FILE"):
        dc.credentials_file = creds
    if device_id := os.getenv("DEVICE_ID"):
        dc.device_id = device_id
    if tenant := os.getenv("DEVICE_CONNECT_TENANT"):
        dc.tenant = tenant
    if backend := os.getenv("MESSAGING_BACKEND"):
        dc.messaging_backend = backend
    if nats_url := os.getenv("NATS_URL"):
        dc.nats_url = nats_url
    if insecure := os.getenv("DEVICE_CONNECT_ALLOW_INSECURE"):
        dc.allow_insecure = insecure.lower() in ("1", "true", "yes")

    if emit := os.getenv("GEMINI2_EMIT_INTERVAL"):
        app.driver.emit_interval = float(emit)


def _apply_cli_overrides(app: AppConfig, overrides: dict[str, Any]) -> None:
    dc = app.device_connect
    if overrides.get("config"):
        # Reloading handled by caller when --config is passed explicitly
        pass
    if overrides.get("mode"):
        dc.mode = overrides["mode"]
    if overrides.get("credentials_file"):
        dc.credentials_file = overrides["credentials_file"]
    if overrides.get("device_id"):
        dc.device_id = overrides["device_id"]
    if overrides.get("allow_insecure") is not None:
        dc.allow_insecure = overrides["allow_insecure"]
    if overrides.get("emit_interval") is not None:
        app.driver.emit_interval = float(overrides["emit_interval"])


def load_credentials_metadata(credentials_file: Path) -> dict[str, Any]:
    with credentials_file.open(encoding="utf-8") as handle:
        return json.load(handle)


def apply_portal_env(app: AppConfig) -> None:
    """Set process environment variables expected by device-connect-edge."""
    creds_path = app.resolved_credentials_file
    if not app.use_portal or creds_path is None:
        return

    os.environ["NATS_CREDENTIALS_FILE"] = str(creds_path)

    metadata = load_credentials_metadata(creds_path)
    nats = metadata.get("nats", {})
    urls = nats.get("urls") or []
    if app.device_connect.nats_url:
        os.environ["NATS_URL"] = app.device_connect.nats_url
    elif urls:
        os.environ["NATS_URL"] = urls[0]
        if len(urls) > 1:
            os.environ["MESSAGING_URLS"] = ",".join(urls)

    if app.device_connect.messaging_backend:
        os.environ["MESSAGING_BACKEND"] = app.device_connect.messaging_backend
    elif not os.getenv("MESSAGING_BACKEND"):
        os.environ["MESSAGING_BACKEND"] = "nats"

    if app.device_connect.device_id:
        os.environ["DEVICE_ID"] = app.device_connect.device_id
    elif metadata.get("device_id") and not os.getenv("DEVICE_ID"):
        os.environ["DEVICE_ID"] = metadata["device_id"]

    if app.device_connect.tenant:
        os.environ["DEVICE_CONNECT_TENANT"] = app.device_connect.tenant
    elif metadata.get("tenant") and not os.getenv("DEVICE_CONNECT_TENANT"):
        os.environ["DEVICE_CONNECT_TENANT"] = metadata["tenant"]

    if app.allow_insecure:
        os.environ["DEVICE_CONNECT_ALLOW_INSECURE"] = "true"
    else:
        os.environ.pop("DEVICE_CONNECT_ALLOW_INSECURE", None)
