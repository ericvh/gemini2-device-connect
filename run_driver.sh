#!/usr/bin/env bash
# Portable launcher — all paths resolved relative to this script unless overridden.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Optional overrides (set in environment or .env) ---
# ORBBEC_SDK_DIR  — path to extracted OrbbecSDK_* directory
# PYTHON          — python interpreter (default: .venv/bin/python, then python3)
# GEMINI2_VENV    — path to virtualenv (default: ${ROOT}/.venv)

if [[ -f "${ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a && source "${ROOT}/.env" && set +a
fi

find_orbbec_sdk() {
  local dir candidate
  if [[ -n "${ORBBEC_SDK_DIR:-}" && -d "${ORBBEC_SDK_DIR}/lib" ]]; then
    echo "${ORBBEC_SDK_DIR}"
    return 0
  fi
  for dir in "${ROOT}/vendor/orbbec" "${ROOT}/../orbbec"; do
    [[ -d "${dir}" ]] || continue
    for candidate in "${dir}"/OrbbecSDK_*; do
      [[ -d "${candidate}/lib" ]] || continue
      echo "${candidate}"
      return 0
    done
  done
  return 1
}

ORBBEC_SDK="$(find_orbbec_sdk || true)"
if [[ -z "${ORBBEC_SDK}" ]]; then
  echo "Orbbec SDK not found. Run ./install.sh or set ORBBEC_SDK_DIR." >&2
  exit 1
fi

VENV="${GEMINI2_VENV:-${ROOT}/.venv}"
if [[ -x "${VENV}/bin/python" ]]; then
  PYTHON="${PYTHON:-${VENV}/bin/python}"
else
  PYTHON="${PYTHON:-python3}"
fi

export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"
export LD_LIBRARY_PATH="${ORBBEC_SDK}/lib:${LD_LIBRARY_PATH:-}"

# Do not force insecure mode — portal credentials in config/env take precedence.
if [[ -f "${ROOT}/gemini2.config.yaml" && -z "${DEVICE_CONNECT_ALLOW_INSECURE:-}" ]]; then
  unset DEVICE_CONNECT_ALLOW_INSECURE
fi

cd "${ROOT}"
exec "${PYTHON}" -m gemini2_device_connect "$@"
