#!/usr/bin/env bash
# Flash the firmware. First flash must be over USB; afterwards OTA by IP.
#
#   scripts/flash.sh                      # USB flash to default port
#   scripts/flash.sh /dev/cu.usbmodem1101 # USB flash to a specific port
#   scripts/flash.sh <DEVICE_IP>        # OTA flash over the network
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -d .venv ]; then source .venv/bin/activate; fi

TARGET="${1:-/dev/cu.usbmodem1101}"

if [ ! -f secrets.yaml ]; then
  echo "secrets.yaml missing. Copy secrets.example.yaml -> secrets.yaml and fill it in."
  exit 1
fi

echo "Flashing to: ${TARGET}"
esphome run iy-homelab.yaml --device "${TARGET}"
