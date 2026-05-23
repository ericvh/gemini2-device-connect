# TODO

## Setup and verification

- [ ] Install udev rules with sudo and verify USB open succeeds (`usbEnumerator openUsbDevice`)
- [ ] Confirm all Gemini 2 streams start (color, depth, IR, IMU)
- [ ] End-to-end test with `device-connect-agent-tools` on a second host

## Driver improvements

- [x] Add `pyproject.toml` and editable install (`pip install -e .`)
- [x] Use relative paths / `vendor/orbbec` for portable packaging
- [x] Add `.gitignore` for `Log/`, `__pycache__`, `.venv`, and `vendor/`
- [ ] Expose raw uint16 depth arrays or point cloud RPC (`get_point_cloud`)
- [ ] Configurable stream profiles (resolution, FPS) via RPC or config file
- [ ] Stream start/stop RPCs for on-demand capture instead of always-on pipelines
- [ ] systemd unit file for running the driver at boot

## Packaging and CI

- [ ] Pin Orbbec SDK version in install script via env var or config
- [ ] Basic smoke test that mocks Orbbec SDK for CI

## Production deployment

- [ ] Document NATS commissioning flow with `device-connect-server`
- [x] Document portal connection via `gemini2.config.yaml` and `NATS_CREDENTIALS_FILE`
- [ ] Disable insecure mode and provision device credentials
- [ ] Rate-limit or downsample high-frequency IMU events
