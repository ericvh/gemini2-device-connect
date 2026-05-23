"""Tests for Orbbec camera helpers."""

from __future__ import annotations

from gemini2_device_connect.orbbec_camera import (
    FramePayload,
    ImuPayload,
    frame_to_dict,
    imu_to_dict,
)


def test_frame_to_dict_includes_image_by_default():
    payload = FramePayload(
        stream="color",
        width=640,
        height=480,
        timestamp_us=123,
        encoding="jpeg",
        data_b64="abc123",
        metadata={"foo": "bar"},
    )
    result = frame_to_dict(payload)
    assert result["stream"] == "color"
    assert result["data_b64"] == "abc123"
    assert result["metadata"] == {"foo": "bar"}


def test_frame_to_dict_can_omit_image():
    payload = FramePayload(
        stream="depth",
        width=640,
        height=480,
        timestamp_us=456,
        encoding="metadata_only",
        metadata={"center_mm": 1.5},
    )
    result = frame_to_dict(payload, include_image=False)
    assert "data_b64" not in result
    assert result["metadata"]["center_mm"] == 1.5


def test_imu_to_dict_returns_none_for_missing_payload():
    assert imu_to_dict(None) is None


def test_imu_to_dict_serializes_values():
    payload = ImuPayload(
        timestamp_us=789,
        temperature=25.0,
        x=0.1,
        y=0.2,
        z=9.8,
        unit="m/s^2",
    )
    result = imu_to_dict(payload)
    assert result == {
        "timestamp_us": 789,
        "temperature": 25.0,
        "x": 0.1,
        "y": 0.2,
        "z": 9.8,
        "unit": "m/s^2",
    }
