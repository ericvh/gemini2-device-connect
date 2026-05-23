# Orbbec Gemini 2 — Device Connect Driver

A [Device Connect](https://deviceconnect.dev) edge driver that exposes depth, color, IR, and IMU streams from an Orbbec Gemini 2 over the Device Connect mesh. AI agents can discover the camera, invoke RPCs, and subscribe to frame events without knowing Orbbec SDK details.

Tested on **NVIDIA Jetson Xavier NX** (Ubuntu 20.04, aarch64) with the Gemini 2 Developer Kit over USB.

## Project layout

Clone or unpack anywhere — no hardcoded install paths:

```
gemini2-device-connect/
├── README.md
├── pyproject.toml
├── requirements.txt
├── install.sh              # Creates .venv, downloads SDK to vendor/
├── run_driver.sh           # Portable launcher (paths relative to repo)
├── gemini2.config.example.yaml  # Portal / D2D connection settings
├── .env.example            # Optional environment overrides
├── vendor/                 # Created by install.sh (gitignored)
│   └── orbbec/
│       └── OrbbecSDK_v2.8.6_.../
└── src/
    └── gemini2_device_connect/
        ├── driver.py
        └── orbbec_camera.py
```

## Prerequisites

- Orbbec Gemini 2 connected via USB 3.0
- Python 3.11+ on `PATH` (or set `PYTHON=` when running `install.sh`)
- USB udev rules (one-time, requires sudo)

## Quick start

```bash
git clone <repo-url> gemini2-device-connect
cd gemini2-device-connect
./install.sh

# Grant USB access (once, then replug the camera)
sudo cp vendor/orbbec/OrbbecSDK_v2.8.6_202604271452_6399409_linux_arm64/shared/99-obsensor-libusb.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

./run_driver.sh
```

If system Python is older than 3.11, point install at a newer interpreter:

```bash
PYTHON="$HOME/miniforge3/bin/python" ./install.sh
```

## Device Connect portal

To connect through the [Device Connect portal](https://portal.deviceconnect.dev) instead of local D2D mode, download your device credentials (a `*.creds.json` file) and configure the driver:

```bash
cp gemini2.config.example.yaml gemini2.config.yaml
# Edit credentials_file to point at your downloaded file, e.g.:
#   credentials_file: ~/your-tenant-orbbec-001.creds.json

./run_driver.sh
```

Or use environment variables:

```bash
export NATS_CREDENTIALS_FILE=~/your-device.creds.json
export DEVICE_CONNECT_MODE=portal
./run_driver.sh
```

### Connection modes

| Mode | Behavior |
|------|----------|
| `portal` | Connect to `portal.deviceconnect.dev` using JWT/NKey credentials (secure) |
| `d2d` | Local Zenoh multicast, no credentials (`DEVICE_CONNECT_ALLOW_INSECURE=true`) |
| `auto` | Use portal if a credentials file is found, otherwise fall back to D2D |

Credentials are discovered in this order:

1. `--credentials-file` CLI flag
2. `device_connect.credentials_file` in `gemini2.config.yaml`
3. `NATS_CREDENTIALS_FILE` environment variable
4. `~/your-device-id.creds.json`
5. `~/.device-connect/credentials/*.creds.json`
6. Any `*.creds.json` in `$HOME`

The `device_id` and NATS URL are read from the credentials file automatically. Your `--device-id` must match the identity in the file when using portal mode.

### Optional configuration

Copy `.env.example` to `.env` or create `gemini2.config.yaml`:

| Variable | Default |
|----------|---------|
| `ORBBEC_SDK_DIR` | First `OrbbecSDK_*` under `vendor/orbbec/` |
| `GEMINI2_VENV` | `.venv` in project root |
| `GEMINI2_CONFIG` | `gemini2.config.yaml` in project root |
| `NATS_CREDENTIALS_FILE` | From config or auto-discovered in `$HOME` |
| `DEVICE_CONNECT_MODE` | `auto` |
| `DEVICE_CONNECT_ALLOW_INSECURE` | `false` when portal credentials are used |

The driver starts in **D2D mode** by default (Zenoh multicast on the LAN, no broker). Set `NATS_URL` and `NATS_CREDENTIALS_FILE` for production infrastructure — see [Device Connect docs](https://github.com/arm/device-connect/tree/main/packages/device-connect-edge).

## Exposed API

### RPC functions

| Function | Description |
|----------|-------------|
| `get_device_info` | Camera name, serial, firmware, enabled streams |
| `list_streams` | Active sensor streams |
| `get_frame(stream, include_image=True)` | Latest frame as JPEG base64 + metadata |
| `get_depth_stats` | Depth min/max/center without image payload |
| `get_imu_reading` | Latest accelerometer and gyroscope samples |

Supported stream names: `color`, `depth`, `ir`, `left_ir`, `right_ir`, `confidence`.

### Events

| Event | Description |
|-------|-------------|
| `frame_available` | Metadata when a new frame arrives (default ~1 Hz) |
| `imu_available` | Accel/gyro updates when IMU is enabled |

## Agent usage

On another machine on the same LAN:

```bash
pip install device-connect-agent-tools
```

```python
from device_connect_agent_tools import connect, discover_devices, invoke_device

connect()
devices = discover_devices(device_type="depth_camera")
info = invoke_device("gemini2-001", "get_device_info")
frame = invoke_device("gemini2-001", "get_frame", stream="color")
```

## Development

From the project root (paths are relative):

```bash
source .venv/bin/activate
export LD_LIBRARY_PATH="$(echo vendor/orbbec/OrbbecSDK_*/lib):${LD_LIBRARY_PATH:-}"
python -m gemini2_device_connect --device-id gemini2-001
```

Or after `pip install -e .`:

```bash
gemini2-device-connect --device-id gemini2-001
```

## License

Apache-2.0
