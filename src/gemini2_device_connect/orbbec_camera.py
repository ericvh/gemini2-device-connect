"""Orbbec Gemini 2 camera wrapper for Device Connect."""

from __future__ import annotations

import base64
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import cv2
import numpy as np
from pyorbbecsdk import (
    Config,
    Context,
    OBError,
    OBFormat,
    OBSensorType,
    Pipeline,
)

log = logging.getLogger("gemini2.orbbec")

STREAM_SENSOR_MAP = {
    "color": OBSensorType.COLOR_SENSOR,
    "depth": OBSensorType.DEPTH_SENSOR,
    "ir": OBSensorType.IR_SENSOR,
    "left_ir": OBSensorType.LEFT_IR_SENSOR,
    "right_ir": OBSensorType.RIGHT_IR_SENSOR,
    "confidence": OBSensorType.CONFIDENCE_SENSOR,
}

VIDEO_STREAMS = set(STREAM_SENSOR_MAP)


@dataclass
class FramePayload:
    stream: str
    width: int
    height: int
    timestamp_us: int
    encoding: str
    data_b64: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImuPayload:
    timestamp_us: int
    temperature: float
    x: float
    y: float
    z: float
    unit: str


class OrbbecGemini2Camera:
    """Thread-safe wrapper around pyorbbecsdk for Gemini 2 streams."""

    def __init__(self) -> None:
        self._video_pipeline: Optional[Pipeline] = None
        self._imu_pipeline: Optional[Pipeline] = None
        self._video_thread: Optional[threading.Thread] = None
        self._imu_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frames: Dict[str, FramePayload] = {}
        self._accel: Optional[ImuPayload] = None
        self._gyro: Optional[ImuPayload] = None
        self._enabled_streams: list[str] = []
        self._device_info: Dict[str, Any] = {}
        self._support_imu = False
        self._support_dual_ir = False

    @property
    def device_info(self) -> Dict[str, Any]:
        return dict(self._device_info)

    @property
    def enabled_streams(self) -> list[str]:
        return list(self._enabled_streams)

    @property
    def support_imu(self) -> bool:
        return self._support_imu

    def start(self) -> None:
        ctx = Context()
        device_list = ctx.query_devices()
        if device_list.get_count() == 0:
            raise RuntimeError("No Orbbec camera found on USB")

        pipeline = Pipeline()
        device = pipeline.get_device()
        info = device.get_device_info()
        self._device_info = {
            "name": info.get_name(),
            "serial_number": info.get_serial_number(),
            "firmware_version": info.get_firmware_version(),
            "vid": f"{info.get_vid():04x}",
            "pid": f"{info.get_pid():04x}",
            "connection_type": info.get_connection_type(),
        }

        config = Config()
        sensor_list = device.get_sensor_list()
        for index in range(len(sensor_list)):
            sensor_type = sensor_list[index].get_type()
            if sensor_type in (
                OBSensorType.LEFT_IR_SENSOR,
                OBSensorType.RIGHT_IR_SENSOR,
            ):
                self._support_dual_ir = True
            if sensor_type in (OBSensorType.ACCEL_SENSOR, OBSensorType.GYRO_SENSOR):
                self._support_imu = True
                continue
            if sensor_type not in STREAM_SENSOR_MAP.values():
                continue
            try:
                config.enable_stream(sensor_type)
                stream_name = self._sensor_to_stream(sensor_type)
                if stream_name and stream_name not in self._enabled_streams:
                    self._enabled_streams.append(stream_name)
            except OBError:
                continue

        if not self._enabled_streams:
            raise RuntimeError("No supported video streams could be enabled")

        self._video_pipeline = pipeline
        self._video_pipeline.start(config)
        self._stop.clear()
        self._video_thread = threading.Thread(
            target=self._video_loop, name="gemini2-video", daemon=True
        )
        self._video_thread.start()

        if self._support_imu:
            self._start_imu_pipeline()

        log.info(
            "Gemini 2 started: streams=%s imu=%s",
            self._enabled_streams,
            self._support_imu,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._video_thread:
            self._video_thread.join(timeout=3.0)
            self._video_thread = None
        if self._imu_thread:
            self._imu_thread.join(timeout=3.0)
            self._imu_thread = None
        if self._video_pipeline:
            self._video_pipeline.stop()
            self._video_pipeline = None
        if self._imu_pipeline:
            self._imu_pipeline.stop()
            self._imu_pipeline = None

    def get_latest_frame(
        self,
        stream: str,
        *,
        include_image: bool = True,
        jpeg_quality: int = 80,
    ) -> Optional[FramePayload]:
        with self._lock:
            payload = self._frames.get(stream)
            if payload is None:
                return None
            if not include_image:
                return FramePayload(
                    stream=payload.stream,
                    width=payload.width,
                    height=payload.height,
                    timestamp_us=payload.timestamp_us,
                    encoding="metadata_only",
                    metadata=dict(payload.metadata),
                )
            return payload

    def get_imu(self) -> Dict[str, Optional[ImuPayload]]:
        with self._lock:
            return {"accel": self._accel, "gyro": self._gyro}

    def _start_imu_pipeline(self) -> None:
        pipeline = Pipeline()
        config = Config()
        config.enable_accel_stream()
        config.enable_gyro_stream()
        self._imu_pipeline = pipeline
        self._imu_pipeline.start(config)
        self._imu_thread = threading.Thread(
            target=self._imu_loop, name="gemini2-imu", daemon=True
        )
        self._imu_thread.start()

    def _video_loop(self) -> None:
        assert self._video_pipeline is not None
        while not self._stop.is_set():
            try:
                frames = self._video_pipeline.wait_for_frames(500)
                if frames is None:
                    continue
                self._store_color(frames.get_color_frame())
                self._store_depth(frames.get_depth_frame())
                self._store_ir(frames.get_ir_frame(), "ir")
                self._store_ir(frames.get_left_ir_frame(), "left_ir")
                self._store_ir(frames.get_right_ir_frame(), "right_ir")
                self._store_confidence(frames.get_confidence_frame())
            except OBError as exc:
                log.warning("Video stream error: %s", exc)
                time.sleep(0.1)

    def _imu_loop(self) -> None:
        assert self._imu_pipeline is not None
        while not self._stop.is_set():
            try:
                frames = self._imu_pipeline.wait_for_frames(500)
                if frames is None:
                    continue
                accel = frames.get_accel_frame()
                if accel is not None:
                    with self._lock:
                        self._accel = ImuPayload(
                            timestamp_us=accel.get_timestamp_us(),
                            temperature=accel.get_temperature(),
                            x=accel.get_x(),
                            y=accel.get_y(),
                            z=accel.get_z(),
                            unit="m/s^2",
                        )
                gyro = frames.get_gyro_frame()
                if gyro is not None:
                    with self._lock:
                        self._gyro = ImuPayload(
                            timestamp_us=gyro.get_timestamp_us(),
                            temperature=gyro.get_temperature(),
                            x=gyro.get_x(),
                            y=gyro.get_y(),
                            z=gyro.get_z(),
                            unit="rad/s",
                        )
            except OBError as exc:
                log.warning("IMU stream error: %s", exc)
                time.sleep(0.1)

    def _store_color(self, frame) -> None:
        if frame is None:
            return
        image = self._color_to_bgr(frame)
        if image is None:
            return
        self._store_jpeg("color", frame, image)

    def _store_depth(self, frame) -> None:
        if frame is None:
            return
        width = frame.get_width()
        height = frame.get_height()
        scale = frame.get_depth_scale()
        depth = np.frombuffer(frame.get_data(), dtype=np.uint16).reshape(height, width)
        depth_mm = depth.astype(np.float32) * scale
        valid = depth_mm[(depth_mm > 20) & (depth_mm < 10000)]
        metadata = {
            "depth_scale": scale,
            "min_mm": float(valid.min()) if valid.size else 0.0,
            "max_mm": float(valid.max()) if valid.size else 0.0,
            "center_mm": float(depth_mm[height // 2, width // 2]),
            "valid_pixels": int(valid.size),
        }
        preview = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        preview = cv2.applyColorMap(preview, cv2.COLORMAP_JET)
        self._store_jpeg(
            "depth",
            frame,
            preview,
            metadata=metadata,
            encoding="jpeg_preview",
        )

    def _store_ir(self, frame, stream: str) -> None:
        if frame is None:
            return
        image = self._ir_to_bgr(frame)
        if image is None:
            return
        self._store_jpeg(stream, frame, image, encoding="jpeg")

    def _store_confidence(self, frame) -> None:
        if frame is None:
            return
        width = frame.get_width()
        height = frame.get_height()
        confidence = np.frombuffer(frame.get_data(), dtype=np.uint8).reshape(height, width)
        preview = cv2.normalize(confidence, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        preview = cv2.cvtColor(preview, cv2.COLOR_GRAY2BGR)
        self._store_jpeg("confidence", frame, preview, encoding="jpeg")

    def _store_jpeg(
        self,
        stream: str,
        frame,
        image: np.ndarray,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        encoding: str = "jpeg",
        quality: int = 80,
    ) -> None:
        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            return
        payload = FramePayload(
            stream=stream,
            width=frame.get_width(),
            height=frame.get_height(),
            timestamp_us=frame.get_timestamp_us(),
            encoding=encoding,
            data_b64=base64.b64encode(encoded.tobytes()).decode("ascii"),
            metadata=metadata or {},
        )
        with self._lock:
            self._frames[stream] = payload

    @staticmethod
    def _sensor_to_stream(sensor_type: OBSensorType) -> Optional[str]:
        for name, mapped in STREAM_SENSOR_MAP.items():
            if mapped == sensor_type:
                return name
        return None

    @staticmethod
    def _color_to_bgr(frame) -> Optional[np.ndarray]:
        width = frame.get_width()
        height = frame.get_height()
        fmt = frame.get_format()
        data = np.asanyarray(frame.get_data())
        if fmt == OBFormat.RGB:
            image = np.resize(data, (height, width, 3))
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if fmt == OBFormat.BGR:
            return np.resize(data, (height, width, 3))
        if fmt == OBFormat.MJPG:
            return cv2.imdecode(data, cv2.IMREAD_COLOR)
        if fmt == OBFormat.YUYV:
            image = np.resize(data, (height, width, 2))
            return cv2.cvtColor(image, cv2.COLOR_YUV2BGR_YUYV)
        if fmt == OBFormat.UYVY:
            image = np.resize(data, (height, width, 2))
            return cv2.cvtColor(image, cv2.COLOR_YUV2BGR_UYVY)
        return None

    @staticmethod
    def _ir_to_bgr(frame) -> Optional[np.ndarray]:
        width = frame.get_width()
        height = frame.get_height()
        fmt = frame.get_format()
        data = np.asanyarray(frame.get_data())
        if fmt == OBFormat.Y8:
            gray = np.resize(data, (height, width))
        elif fmt == OBFormat.MJPG:
            gray = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                return None
        else:
            gray = np.frombuffer(data, dtype=np.uint16).reshape(height, width)
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def frame_to_dict(payload: FramePayload, *, include_image: bool = True) -> dict:
    result = {
        "stream": payload.stream,
        "width": payload.width,
        "height": payload.height,
        "timestamp_us": payload.timestamp_us,
        "encoding": payload.encoding,
        "metadata": payload.metadata,
    }
    if include_image and payload.data_b64:
        result["data_b64"] = payload.data_b64
    return result


def imu_to_dict(payload: Optional[ImuPayload]) -> Optional[dict]:
    if payload is None:
        return None
    return {
        "timestamp_us": payload.timestamp_us,
        "temperature": payload.temperature,
        "x": payload.x,
        "y": payload.y,
        "z": payload.z,
        "unit": payload.unit,
    }
