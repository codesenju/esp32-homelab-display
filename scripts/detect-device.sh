#!/usr/bin/env bash
# Identify the connected ESP32-C6 and its serial port. Read-only; no flashing.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Serial devices =="
ls /dev/cu.* 2>/dev/null || echo "  (none)"

echo
echo "== USB descriptor (Espressif) =="
ioreg -p IOUSB -l -w 0 2>/dev/null | grep -iE "idVendor|idProduct|USB Product Name|USB Vendor Name|USB Serial Number" | sed 's/^ *//' || true

PORT="${1:-/dev/cu.usbmodem1101}"
echo
echo "== esptool chip identity on ${PORT} =="
if [ -d .venv ]; then source .venv/bin/activate; fi
python -m esptool --port "${PORT}" chip-id 2>&1 | grep -iE "Chip type|Features|MAC|Crystal|USB mode" || {
  echo "Could not talk to ${PORT}. Check cable / port / bootloader."
  exit 1
}
echo
echo "== Flash size =="
python -m esptool --port "${PORT}" flash-id 2>&1 | grep -iE "Detected flash size" || true
