#!/usr/bin/env bash
# Tail the device serial logs (USB) or network logs (by IP).
#   scripts/monitor.sh                      # USB
#   scripts/monitor.sh <DEVICE_IP>        # over network (encrypted API)
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -d .venv ]; then source .venv/bin/activate; fi
TARGET="${1:-/dev/cu.usbmodem1101}"
echo "Monitoring ${TARGET} (Ctrl-C to stop)"
esphome logs iy-homelab.yaml --device "${TARGET}"
