# Copyright (c) 2024-2026, Arm Limited and Contributors. All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Orbbec Gemini 2 Device Connect driver."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Optional

from device_connect_edge import DeviceRuntime
from device_connect_edge.drivers import DeviceDriver, emit, periodic, rpc
from device_connect_edge.types import DeviceIdentity, DeviceStatus

from gemini2_device_connect.config import AppConfig, apply_portal_env, load_config
from gemini2_device_connect.orbbec_camera import (
    OrbbecGemini2Camera,
    frame_to_dict,
    imu_to_dict,
)

log = logging.getLogger("gemini2-driver")

SUPPORTED_STREAMS = ("color", "depth", "ir", "left_ir", "right_ir", "confidence")


class Gemini2Driver(DeviceDriver):
    """Device Connect driver for the Orbbec Gemini 2 depth camera."""

    device_type = "depth_camera"

    def __init__(self, emit_interval: float = 1.0):
        super().__init__()
        self._camera = OrbbecGemini2Camera()
        self._emit_interval = emit_interval
        self._last_frame_ts: dict[str, int] = {}

    @property
    def identity(self) -> DeviceIdentity:
        info = self._camera.device_info
        return DeviceIdentity(
            device_type="depth_camera",
            manufacturer="Orbbec",
            model=info.get("name", "Gemini 2"),
            serial_number=info.get("serial_number"),
            firmware_version=info.get("firmware_version"),
            description="Orbbec Gemini 2 RGB-D camera with IMU",
        )

    @property
    def status(self) -> DeviceStatus:
        return DeviceStatus(
            availability="available" if self._camera.enabled_streams else "unavailable",
            metadata={
                "streams": self._camera.enabled_streams,
                "imu": self._camera.support_imu,
            },
        )

    @rpc()
    async def get_device_info(self) -> dict:
        """Return camera identity and enabled stream list."""
        return {
            "device_info": self._camera.device_info,
            "streams": self._camera.enabled_streams,
            "imu_supported": self._camera.support_imu,
            "supported_stream_names": list(SUPPORTED_STREAMS),
        }

    @rpc()
    async def list_streams(self) -> dict:
        """List currently active sensor streams."""
        return {
            "streams": self._camera.enabled_streams,
            "imu_supported": self._camera.support_imu,
        }

    @rpc()
    async def get_frame(
        self,
        stream: str = "color",
        include_image: bool = True,
        jpeg_quality: int = 80,
    ) -> dict:
        """Return the latest frame for a stream (color, depth, ir, left_ir, right_ir, confidence)."""
        if stream not in SUPPORTED_STREAMS:
            return {"error": f"Unknown stream '{stream}'. Supported: {list(SUPPORTED_STREAMS)}"}

        payload = await asyncio.to_thread(
            self._camera.get_latest_frame,
            stream,
            include_image=include_image,
            jpeg_quality=jpeg_quality,
        )
        if payload is None:
            return {"error": f"No frame available yet for stream '{stream}'"}
        return frame_to_dict(payload, include_image=include_image)

    @rpc()
    async def get_depth_stats(self) -> dict:
        """Return depth statistics without the preview image."""
        payload = await asyncio.to_thread(
            self._camera.get_latest_frame,
            "depth",
            include_image=False,
        )
        if payload is None:
            return {"error": "No depth frame available yet"}
        return {
            "timestamp_us": payload.timestamp_us,
            "width": payload.width,
            "height": payload.height,
            **payload.metadata,
        }

    @rpc()
    async def get_imu_reading(self) -> dict:
        """Return the latest accelerometer and gyroscope readings."""
        if not self._camera.support_imu:
            return {"error": "IMU not supported on this device"}
        imu = await asyncio.to_thread(self._camera.get_imu)
        return {
            "accel": imu_to_dict(imu["accel"]),
            "gyro": imu_to_dict(imu["gyro"]),
        }

    @emit()
    async def frame_available(
        self,
        stream: str,
        width: int,
        height: int,
        timestamp_us: int,
        encoding: str,
        metadata: dict,
        data_b64: Optional[str] = None,
    ):
        """A new camera frame is available."""
        pass

    @emit()
    async def imu_available(self, accel: Optional[dict], gyro: Optional[dict]):
        """New IMU samples are available."""
        pass

    @periodic(interval=1.0)
    async def publish_streams(self):
        """Emit events for newly received frames and IMU samples."""
        for stream in self._camera.enabled_streams:
            payload = await asyncio.to_thread(
                self._camera.get_latest_frame,
                stream,
                include_image=False,
            )
            if payload is None:
                continue
            last_ts = self._last_frame_ts.get(stream)
            if last_ts == payload.timestamp_us:
                continue
            self._last_frame_ts[stream] = payload.timestamp_us
            await self.frame_available(
                stream=payload.stream,
                width=payload.width,
                height=payload.height,
                timestamp_us=payload.timestamp_us,
                encoding=payload.encoding,
                metadata=payload.metadata,
            )

        if self._camera.support_imu:
            imu = await asyncio.to_thread(self._camera.get_imu)
            accel = imu_to_dict(imu["accel"])
            gyro = imu_to_dict(imu["gyro"])
            if accel or gyro:
                await self.imu_available(accel=accel, gyro=gyro)

    async def connect(self) -> None:
        await asyncio.to_thread(self._camera.start)
        self.publish_streams.__func__._routine_interval = self._emit_interval
        log.info(
            "Gemini 2 connected: %s streams=%s",
            self._camera.device_info.get("serial_number"),
            self._camera.enabled_streams,
        )

    async def disconnect(self) -> None:
        await asyncio.to_thread(self._camera.stop)
        log.info("Gemini 2 disconnected")


def build_device_runtime(app: AppConfig) -> DeviceRuntime:
    apply_portal_env(app)

    dc = app.device_connect
    creds_path = app.resolved_credentials_file
    device_id = dc.device_id or os.getenv("DEVICE_ID")
    messaging_urls = None
    if dc.nats_url:
        messaging_urls = [dc.nats_url]

    runtime_kwargs: dict = {
        "driver": Gemini2Driver(emit_interval=app.driver.emit_interval),
        "allow_insecure": app.allow_insecure,
    }

    if device_id:
        runtime_kwargs["device_id"] = device_id

    if app.use_portal:
        if creds_path is None:
            raise FileNotFoundError(
                "Portal mode requires a credentials file. Set device_connect.credentials_file "
                "in gemini2.config.yaml, NATS_CREDENTIALS_FILE, or place a *.creds.json in $HOME."
            )
        runtime_kwargs["credentials_file"] = str(creds_path)
        if dc.tenant:
            runtime_kwargs["tenant"] = dc.tenant
        if dc.messaging_backend:
            runtime_kwargs["messaging_backend"] = dc.messaging_backend
        if messaging_urls:
            runtime_kwargs["messaging_urls"] = messaging_urls
    elif messaging_urls:
        runtime_kwargs["messaging_urls"] = messaging_urls

    return DeviceRuntime(**runtime_kwargs)


def describe_connection(app: AppConfig) -> str:
    if app.use_portal:
        creds = app.resolved_credentials_file
        nats_url = app.device_connect.nats_url or os.getenv("NATS_URL", "from credentials file")
        return f"Portal ({nats_url}, creds={creds})"
    nats_url = os.getenv("NATS_URL")
    if nats_url:
        return f"NATS ({nats_url})"
    return "D2D (Zenoh multicast)"


async def run(app: AppConfig):
    device = build_device_runtime(app)
    device_id = device.device_id

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    log.info("=" * 56)
    log.info(" Orbbec Gemini 2 Device Connect Driver")
    if app.config_path:
        log.info(" Config file     : %s", app.config_path)
    log.info(" Device ID       : %s", device_id)
    log.info(" Emit interval   : %.1fs", app.driver.emit_interval)
    log.info(" Connection mode : %s", "portal" if app.use_portal else app.device_connect.mode)
    log.info(" Insecure mode   : %s", app.allow_insecure)
    log.info(" Messaging       : %s", describe_connection(app))
    log.info(" Press Ctrl+C to stop")
    log.info("=" * 56)

    device_task = asyncio.create_task(device.run())
    await stop_event.wait()
    await device.stop()

    if not device_task.done():
        device_task.cancel()
        try:
            await device_task
        except asyncio.CancelledError:
            pass


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-28s %(levelname)-7s %(message)s",
    )

    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config")
    pre_args, _ = pre_parser.parse_known_args()

    parser = argparse.ArgumentParser(description="Orbbec Gemini 2 Device Connect driver")
    parser.add_argument(
        "--config",
        default=pre_args.config,
        help="Path to gemini2.config.yaml (default: auto-discover in project root)",
    )
    parser.add_argument("--device-id", default=None, help="Override device ID from config/credentials")
    parser.add_argument("--credentials-file", default=None, help="Path to portal *.creds.json file")
    parser.add_argument(
        "--mode",
        choices=("auto", "portal", "d2d"),
        default=None,
        help="Connection mode: portal (Device Connect cloud), d2d (local Zenoh), or auto",
    )
    parser.add_argument("--emit-interval", type=float, default=None)
    parser.add_argument(
        "--allow-insecure",
        action="store_true",
        default=None,
        help="Allow unauthenticated D2D mode (development only)",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=None,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    app = load_config(
        config_path=args.config,
        project_root=project_root,
        cli_overrides={
            "device_id": args.device_id,
            "credentials_file": args.credentials_file,
            "mode": args.mode,
            "emit_interval": args.emit_interval,
            "allow_insecure": args.allow_insecure if args.allow_insecure is not None else args.insecure,
        },
    )

    asyncio.run(run(app))
