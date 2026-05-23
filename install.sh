#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORBBEC_VERSION="v2.8.6"
ORBBEC_TARBALL="OrbbecSDK_v2.8.6_202604271452_6399409_linux_arm64.tar.gz"
ORBBEC_URL="https://github.com/orbbec/OrbbecSDK_v2/releases/download/${ORBBEC_VERSION}/${ORBBEC_TARBALL}"
VENDOR_DIR="${ROOT}/vendor/orbbec"
ORBBEC_EXTRACT="${VENDOR_DIR}/OrbbecSDK_v2.8.6_202604271452_6399409_linux_arm64"
VENV="${ROOT}/.venv"

echo "==> Orbbec Gemini 2 + Device Connect setup"
echo "    Project root: ${ROOT}"

find_python() {
  local candidate resolved
  for candidate in \
    "${PYTHON:-}" \
    "${VENV}/bin/python" \
    python3.13 python3.12 python3.11 python3; do
    [[ -n "${candidate}" ]] || continue
    resolved="$(command -v "${candidate}" 2>/dev/null || true)"
    [[ -n "${resolved}" && -x "${resolved}" ]] || continue
    if "${resolved}" -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
      echo "${resolved}"
      return 0
    fi
  done
  return 1
}

PYTHON_BIN="$(find_python || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "Python 3.11+ is required. Install it, or set PYTHON= to a 3.11+ interpreter." >&2
  echo "On Jetson/Ubuntu 20.04 you can use Miniforge:" >&2
  echo "  curl -fsSL -o /tmp/miniforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh" >&2
  echo "  bash /tmp/miniforge.sh -b -p \"\${HOME}/miniforge3\"" >&2
  echo "  PYTHON=\"\${HOME}/miniforge3/bin/python\" ./install.sh" >&2
  exit 1
fi

echo "==> Using Python: ${PYTHON_BIN} ($("${PYTHON_BIN}" --version))"

if [[ ! -d "${VENV}" ]]; then
  echo "==> Creating virtualenv at ${VENV}"
  "${PYTHON_BIN}" -m venv "${VENV}"
fi

echo "==> Installing Python dependencies"
"${VENV}/bin/pip" install -U pip
"${VENV}/bin/pip" install -r "${ROOT}/requirements.txt"
"${VENV}/bin/pip" install -e "${ROOT}"

if [[ ! -d "${ORBBEC_EXTRACT}" ]]; then
  echo "==> Downloading Orbbec SDK ${ORBBEC_VERSION} to vendor/orbbec/"
  mkdir -p "${VENDOR_DIR}"
  curl -fsSL -o "/tmp/${ORBBEC_TARBALL}" "${ORBBEC_URL}"
  tar -xzf "/tmp/${ORBBEC_TARBALL}" -C "${VENDOR_DIR}"
fi

# Migrate legacy sibling install if present
LEGACY_ORBBEC="${ROOT}/../orbbec/${ORBBEC_EXTRACT##*/}"
if [[ -d "${LEGACY_ORBBEC}" && ! -d "${ORBBEC_EXTRACT}" ]]; then
  echo "==> Migrating Orbbec SDK from ../orbbec/ to vendor/orbbec/"
  mkdir -p "${VENDOR_DIR}"
  mv "${LEGACY_ORBBEC}" "${ORBBEC_EXTRACT}"
fi

echo "==> Installing udev rules (requires sudo for USB access)"
if sudo -n true 2>/dev/null; then
  sudo cp "${ORBBEC_EXTRACT}/shared/99-obsensor-libusb.rules" /etc/udev/rules.d/
  sudo udevadm control --reload-rules
  sudo udevadm trigger
  echo "udev rules installed"
else
  echo "Run once with sudo to grant USB access:"
  echo "  sudo cp ${ORBBEC_EXTRACT}/shared/99-obsensor-libusb.rules /etc/udev/rules.d/"
  echo "  sudo udevadm control --reload-rules && sudo udevadm trigger"
  echo "Then unplug and replug the Gemini 2."
fi

if [[ ! -f "${ROOT}/.env" ]]; then
  cat > "${ROOT}/.env.example" <<'EOF'
# Copy to .env and adjust if needed.
# ORBBEC_SDK_DIR=vendor/orbbec/OrbbecSDK_v2.8.6_202604271452_6399409_linux_arm64
# GEMINI2_VENV=.venv
# DEVICE_CONNECT_ALLOW_INSECURE=true
# DEVICE_ID=gemini2-001
EOF
fi

chmod +x "${ROOT}/run_driver.sh"

echo
echo "Setup complete."
echo "Start the driver:"
echo "  cd \"${ROOT}\" && ./run_driver.sh --device-id gemini2-001"
