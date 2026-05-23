"""Tests for the Device Connect driver."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gemini2_device_connect.config import AppConfig, DeviceConnectSettings, DriverSettings
from gemini2_device_connect.driver import (
    Gemini2Driver,
    build_device_runtime,
    describe_connection,
)
from gemini2_device_connect.orbbec_camera import FramePayload, ImuPayload


@pytest.fixture
def mock_camera():
    camera = MagicMock()
    camera.device_info = {
        "name": "Orbbec Gemini 2",
        "serial_number": "SN123",
        "firmware_version": "1.4.92",
    }
    camera.enabled_streams = ["color", "depth"]
    camera.support_imu = True
    return camera


@pytest.fixture
def driver(mock_camera):
    with patch("gemini2_device_connect.driver.OrbbecGemini2Camera", return_value=mock_camera):
        yield Gemini2Driver(emit_interval=1.0)


@pytest.mark.asyncio
async def test_get_device_info(driver, mock_camera):
    result = await driver.get_device_info()
    assert result["device_info"]["serial_number"] == "SN123"
    assert result["streams"] == ["color", "depth"]
    assert result["imu_supported"] is True
    assert "color" in result["supported_stream_names"]


@pytest.mark.asyncio
async def test_get_frame_unknown_stream_returns_error(driver):
    result = await driver.get_frame(stream="not-a-stream")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_frame_returns_latest_frame(driver, mock_camera):
    payload = FramePayload(
        stream="color",
        width=640,
        height=480,
        timestamp_us=100,
        encoding="jpeg",
        data_b64="Zm9v",
    )
    mock_camera.get_latest_frame.return_value = payload

    result = await driver.get_frame(stream="color")
    assert result["stream"] == "color"
    assert result["data_b64"] == "Zm9v"


@pytest.mark.asyncio
async def test_get_imu_reading(driver, mock_camera):
    mock_camera.get_imu.return_value = {
        "accel": ImuPayload(1, 25.0, 0.0, 0.0, 9.8, "m/s^2"),
        "gyro": ImuPayload(2, 25.0, 0.1, 0.0, 0.0, "rad/s"),
    }
    result = await driver.get_imu_reading()
    assert result["accel"]["unit"] == "m/s^2"
    assert result["gyro"]["unit"] == "rad/s"


def _make_runtime_mock_camera():
    camera = MagicMock()
    camera.device_info = {
        "name": "Orbbec Gemini 2",
        "serial_number": "SN123",
        "firmware_version": "1.4.92",
    }
    camera.enabled_streams = []
    camera.support_imu = False
    return camera


def test_build_device_runtime_d2d(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NATS_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("DEVICE_ID", raising=False)

    app = AppConfig(
        device_connect=DeviceConnectSettings(mode="d2d", allow_insecure=True),
        driver=DriverSettings(emit_interval=1.0),
    )

    with patch(
        "gemini2_device_connect.driver.OrbbecGemini2Camera",
        return_value=_make_runtime_mock_camera(),
    ):
        runtime = build_device_runtime(app)

    assert runtime.allow_insecure is True


def test_build_device_runtime_portal(sample_credentials, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEVICE_ID", raising=False)

    app = AppConfig(
        device_connect=DeviceConnectSettings(
            mode="portal",
            credentials_file=str(sample_credentials),
            messaging_backend="nats",
        )
    )

    with patch(
        "gemini2_device_connect.driver.OrbbecGemini2Camera",
        return_value=_make_runtime_mock_camera(),
    ):
        runtime = build_device_runtime(app)

    assert runtime.device_id == "tenant-camera-001"
    assert runtime.tenant == "tenant"


def test_build_device_runtime_portal_requires_credentials(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HOME", str(project_root))
    monkeypatch.delenv("NATS_CREDENTIALS_FILE", raising=False)

    app = AppConfig(device_connect=DeviceConnectSettings(mode="portal"))
    with patch(
        "gemini2_device_connect.driver.OrbbecGemini2Camera",
        return_value=_make_runtime_mock_camera(),
    ):
        with pytest.raises(FileNotFoundError):
            build_device_runtime(app)


def test_describe_connection_portal(sample_credentials):
    app = AppConfig(
        device_connect=DeviceConnectSettings(
            mode="portal",
            credentials_file=str(sample_credentials),
        )
    )
    description = describe_connection(app)
    assert description.startswith("Portal (")


def test_describe_connection_d2d(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NATS_URL", raising=False)
    app = AppConfig(device_connect=DeviceConnectSettings(mode="d2d"))
    assert describe_connection(app) == "D2D (Zenoh multicast)"
