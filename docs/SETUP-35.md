# Setup — 3.5" ILI9488 display on ESP32-S3 (human guide)

Step-by-step to build/rebuild the **single-screen KUBELAB dashboard** on the
3.5" ILI9488 TFT + ESP32-S3 board. For the hardware reference and full pin map
see [`hardware-35.md`](hardware-35.md). Firmware: [`iy-homelab-35.yaml`](../iy-homelab-35.yaml).

> This reuses the **same Home Assistant backend and the same
> `proxmox_bridge.py` entities** as the original build. You do **not** need a
> second bridge — just adopt this device into the same HA.

## Table of contents

- [What you need](#what-you-need)
- [1. Wire the display (USB UNPLUGGED)](#1-wire-the-display-usb-unplugged)
- [2. One-time environment](#2-one-time-environment)
- [3. Validate + compile](#3-validate--compile)
- [4. First flash (USB, at 115200)](#4-first-flash-usb-at-115200)
- [5. Check orientation](#5-check-orientation)
- [6. Join WiFi + adopt into Home Assistant](#6-join-wifi--adopt-into-home-assistant)
- [7. Future updates: over-the-air](#7-future-updates-over-the-air)
- [Dashboard layout (single screen, 480×320)](#dashboard-layout-single-screen-480320)
- [Troubleshooting quick hits](#troubleshooting-quick-hits)

---

## What you need

- ESP32-S3 board (sparkleIoT XH-S3E / N16R8, UNO form factor) + USB-C cable (data).
- 3.5" ILI9488 SPI TFT (Hongxun S219C35002A / "35002 V1.2").
- 8 jumper wires.
- The repo checked out with its `.venv` and a filled-in `secrets.yaml`
  (same `wifi_*`, `ota_password`, `api_encryption_key` as the other display —
  they can share the key).
- The metrics bridge already publishing `sensor.kubelab_*` + `sensor.homelab_kubernetes_*`
  into Home Assistant (same as the 1.47" build).

---

## 1. Wire the display (USB UNPLUGGED)

Connect exactly these 8 wires. Double-check **VCC→5V** and **GND→GND** (swapping
them can cook the module). Leave the touch (`T_*`) and SD pins unconnected.

| TFT pin | → ESP32-S3 pin |
|---------|----------------|
| VCC | **5V** |
| GND | **GND** |
| LED | **3V3** |
| SCK | **IO14** |
| SDI (MOSI) | **IO9** |
| DC | **IO11** |
| RESET | **IO13** |
| CS | **IO10** |

```
 5V ──VCC      GND ──GND      3V3 ──LED
IO14──SCK     IO9 ──SDI/MOSI
IO11──DC      IO13──RST       IO10──CS
             (SDO/MISO, T_*, SD_*  = leave empty)
```

A little warmth from the TFT's regulator at 5 V is normal; **hot** is not —
if it gets hot, unplug and recheck VCC/GND aren't swapped or shorted.

Then plug USB-C into the board.

---

## 2. One-time environment

```bash
cd ~/codesenju/repos/kubelab-display
# venv already exists in this repo; if starting fresh:
# python3 -m venv .venv && ./.venv/bin/pip install -U pip esphome esptool pyserial
ls /dev/cu.usbserial*          # expect /dev/cu.usbserial-10 (UART bridge)
```

> If no `usbserial` port appears: bad/charge-only cable, or a missing CH340/CP210x
> driver. This board is a **UART bridge**, so it shows as `usbserial-*`, not `usbmodem`.

---

## 3. Validate + compile

```bash
./.venv/bin/esphome config  iy-homelab-35.yaml   # must end "Configuration is valid!"
./.venv/bin/esphome compile iy-homelab-35.yaml   # must end "Successfully compiled program."
```

---

## 4. First flash (USB, at 115200)

The UART bridge is unreliable at the default 921600 baud — **flash at 115200.**

```bash
# simplest: esphome handles it
./.venv/bin/esphome upload iy-homelab-35.yaml --device /dev/cu.usbserial-10

# if that negotiates a too-fast baud and fails, flash the factory image directly:
esptool --chip esp32s3 --port /dev/cu.usbserial-10 --baud 115200 \
  --before default-reset --after hard-reset write-flash -z 0x0 \
  .esphome/build/iy-homelab-35/build/firmware.factory.bin
```

Expect `Hash of data verified.` and a hard reset. The display should light up
and show the KUBELAB dashboard within a few seconds.

---

## 5. Check orientation

The text should read left-to-right, right-side up, in **landscape**. If it's
mirrored or rotated, edit the `display: transform:` block in `iy-homelab-35.yaml`
and recompile/flash. Working value for this panel (ROT-3 / 270° landscape):

```yaml
transform:
  swap_xy: true
  mirror_x: false
  mirror_y: true
```

Other orientations: toggle `mirror_x`/`mirror_y`; for portrait set `swap_xy: false`.

---

## 6. Join WiFi + adopt into Home Assistant

On boot the footer shows `WiFi only - waiting for HA` once it joins your network.
Find its IP and adopt it:

```bash
ping -c1 iy-homelab-35.local            # resolves the IP (e.g. 192.168.0.232)
```

In Home Assistant: **Settings → Devices & Services → ESPHome** should
auto-discover `iy-homelab-35`. Add it; when prompted for the encryption key,
paste the value of `api_encryption_key` from `secrets.yaml`:

```bash
grep api_encryption_key secrets.yaml    # view it locally; don't paste into chat/logs
```

Headless alternative (needs your HA token):

```bash
KEY=$(grep api_encryption_key secrets.yaml | awk '{print $2}')
HA_TOKEN=<your-token> ./.venv/bin/python scripts/ha_adopt_esphome.py 192.168.0.232 6053 "$KEY"
```

When adopted, the footer flips to **HA connected** and the node/K8s values
populate (assuming the bridge is running).

---

## 7. Future updates: over-the-air

Once it's on WiFi and adopted, no USB needed:

```bash
./.venv/bin/esphome upload iy-homelab-35.yaml --device 192.168.0.232
```

---

## Dashboard layout (single screen, 480×320)

Each node is one row; the value sits on the node line and its bar sits just
**below** the value (not inline). The dot + `kubelab-N` label are vertically
centred on the value+bar pair.

```
┌──────────────────────────────────────────────────────────┐
│ KUBELAB                        04:08              HA       │
├──────────────────────────────────────────────────────────┤
│ NODE           CPU            MEM             TEMP         │
│                                                            │
│ ● kubelab-1    15%            80%             73C          │
│                ██░░░░░        ███████░        ██████░      │
│ ● kubelab-2    61%            79%             82C          │
│                █████░░        ██████░░        ███████░     │
│ ● kubelab-3    56%            80%             69C          │
│                █████░░        ███████░        █████░░      │
├──────────────────────────────────────────────────────────┤
│ ● K8S  Degraded   Ready 6/6   Pods bad 7                   │
├──────────────────────────────────────────────────────────┤
│ HA connected  -  updated 2s ago                           │
└──────────────────────────────────────────────────────────┘
```

Colour thresholds (same as the C6 build): CPU/MEM `<60 green, 60–85 amber,
≥85 red`; TEMP `<70 green, 70–85 amber, ≥85 red`; dots grey when stale/unknown;
missing values show `--`.

---

## Troubleshooting quick hits

| Symptom | Likely cause / fix |
|---------|--------------------|
| No `usbserial` port | charge-only cable, or missing CH340/CP210x driver |
| Upload fails "No serial data received" | a control wire is on a **strapping pin** (GPIO0/3/45/46) — move it; or flash at **115200** |
| Upload fails after "Changing baud rate to 921600" | baud too high — flash at **115200** |
| Backlight on, blank/white screen | wrong SPI wiring (SCK/MOSI/DC/CS/RST) or missing `invert_colors: true` |
| Dark text on white (inverted) | set `invert_colors: true` |
| Text mirrored/upside-down | adjust `display: transform:` (swap_xy / mirror_x / mirror_y) |
| `StoreProhibited` crash in `init()` (Arduino) | TFT_eSPI × core-3 bug — use ESPHome (this build) or LovyanGFX |
| Footer stuck "WiFi only - waiting for HA" | adopt device in HA; check `api_encryption_key` matches |
| All values `--` | bridge not running, or HA entities missing — start `integrations/run-bridge.sh` |
