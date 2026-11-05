#!/usr/bin/env bash
# Validate and compile the ESPHome firmware.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -d .venv ]; then source .venv/bin/activate; fi

echo "== esphome version =="
esphome version

echo
echo "== config validate =="
esphome config iy-homelab.yaml

echo
echo "== compile =="
esphome compile iy-homelab.yaml
