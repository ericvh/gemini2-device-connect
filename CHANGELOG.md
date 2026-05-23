# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.3] - 2026-05-23

### Added

- Device Connect **portal mode** with credentials from `gemini2.config.yaml`, environment variables, or auto-discovery in `$HOME`
- `src/gemini2_device_connect/config.py` for config loading and credential resolution
- `gemini2.config.example.yaml` with portal connection template
- CLI flags: `--config`, `--credentials-file`, `--mode` (`auto` | `portal` | `d2d`)

### Changed

- Portal mode disables insecure D2D by default; device ID and NATS URL are inferred from the credentials file
- `run_driver.sh` no longer forces `DEVICE_CONNECT_ALLOW_INSECURE=true`

## [0.1.2] - 2026-05-23

### Changed

- `run_driver.sh` resolves all paths relative to the repo root (no hardcoded `/home/arm` or `/data/src` paths)
- Orbbec SDK now installs to `vendor/orbbec/` inside the project (self-contained, gitignored)
- `install.sh` creates a local `.venv` instead of requiring Miniforge in `$HOME`
- Added `pyproject.toml` for editable install and `gemini2-device-connect` console script
- Added `.gitignore`, `.env.example`, and optional `.env` overrides (`ORBBEC_SDK_DIR`, `GEMINI2_VENV`, `PYTHON`)

## [0.1.1] - 2026-05-23

### Changed

- Moved project from `~/gemini2-device-connect` to `~/src/gemini2-device-connect` (`/data/src/gemini2-device-connect`)
- Moved Orbbec SDK from `~/orbbec` to `~/src/orbbec` (`/data/src/orbbec`)
- Updated launcher and documentation paths accordingly

## [0.1.0] - 2026-05-23

### Added

- Initial Device Connect driver for Orbbec Gemini 2 (`depth_camera` device type)
- Orbbec SDK wrapper with multi-stream capture the camera exposes (color, depth, IR, confidence)
- Separate IMU pipeline for accelerometer and gyroscope data
- RPCs: `get_device_info`, `list_streams`, `get_frame`, `get_depth_stats`, `get_imu_reading`
- Events: `frame_available`, `imu_available` with configurable emit interval
- `install.sh` for Miniforge, Python dependencies, Orbbec SDK download, and udev guidance
- `run_driver.sh` launcher with correct `PYTHONPATH`, `LD_LIBRARY_PATH`, and D2D defaults
- Project documentation: `README.md`, `TODO.md`, `CHANGELOG.md`
- Source package under `src/gemini2_device_connect/`

### Notes

- Requires Python 3.11+ (`device-connect-edge` dependency)
- Orbbec SDK v2.8.6 arm64 tarball downloaded to `../orbbec/` by install script
- USB udev rules must be installed manually with sudo before the camera can be opened

[0.1.0]: https://github.com/arm/device-connect/compare/v0.1.0...HEAD
