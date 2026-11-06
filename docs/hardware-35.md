# Hardware — ESP32-S3 (sparkleIoT XH-S3E) + 3.5" ILI9488 SPI TFT

This is the **second** KUBELAB display build: a 3.5" 480×320 TFT driven by a
UNO-form-factor ESP32-S3 board. It renders the **same** Home Assistant entities
as the original 1.47" build, but as a **single always-on screen** (no pages, no
button) using the larger area. Firmware: [`iy-homelab-35.yaml`](../iy-homelab-35.yaml).

> If you are setting this up from scratch, see
> [`SETUP-35.md`](SETUP-35.md) (humans) and the ESP32-S3 section of
> [`AGENT_REPLICATION_GUIDE.md`](AGENT_REPLICATION_GUIDE.md) (agents).

## Table of contents

- [Verified identity (esptool)](#verified-identity-esptool)
- [Display](#display)
- [Connection mapping — ESP32-S3 ⟷ ILI9488 TFT](#connection-mapping--esp32-s3--ili9488-tft)
  - [Wiring table](#wiring-table)
  - [Simple layout diagram](#simple-layout-diagram)
  - [SPI bus summary](#spi-bus-summary-what-the-firmware-declares)
- [Pin-choice rationale](#pin-choice-rationale-avoid-the-traps-we-hit)
- [Flashing notes specific to this board](#flashing-notes-specific-to-this-board)
- [Backlight](#backlight)
- [Naming note](#naming-note)
- [Future development — capacitive touch (CTP)](#future-development--capacitive-touch-ctp)
  - [Proposed touch wiring (FT6236 over I²C)](#proposed-touch-wiring-ft6236-over-i2c)
    - [CTP connector layout (physical pin order)](#ctp-connector-layout-physical-pin-order-on-the-module)
  - [Updated layout diagram (display + touch)](#updated-layout-diagram-display--touch)
  - [ESPHome config sketch](#esphome-config-sketch-for-when-touch-is-wired)

---

## Verified identity (esptool)

```
Chip type:   ESP32-S3 (QFN56) (revision v0.2)
Features:    Wi-Fi, BT 5 (LE), Dual Core + LP Core, 240MHz, Embedded PSRAM 8MB (AP_3v3)
Module:      sparkleIoT XH-S3E, WiFi+BT, N16R8  (16 MB flash / 8 MB PSRAM)
Crystal:     40 MHz
Base MAC:    98:a3:16:e5:e9:30
USB:         USB-to-UART bridge ("USB Serial") — NOT native USB-Serial/JTAG
Serial port (macOS): /dev/cu.usbserial-10
Device IP:   192.168.0.232   (mDNS: iy-homelab-35.local, API port 6053)
```

> **Key difference from the C6 board:** this board enumerates as
> `/dev/cu.usbserial-*` (a CH340/CP210x-class UART bridge), **not** a native
> `usbmodem`. That bridge does classic DTR/RTS auto-reset, so flashing is
> reliable — but the default high upload baud (921600) is **not** reliable here.
> **Flash at 115200.** The firmware sets `flash_size: 16MB`, `psram: octal`.

---

## Display

| Property | Value |
|----------|-------|
| Product | 3.5" LCD Module With CTP — Hongxun **S219C35002A** ("35002 V1.2") |
| Controller | **ILI9488** (320×480 native portrait; shown 480×320 landscape) |
| Resolution | 480 × 320 **effective** (after `swap_xy` rotation) |
| Colour | 16-bit, `color_order: bgr`, `invert_colors: true` |
| Orientation | landscape via `transform: {swap_xy: true, mirror_x: false, mirror_y: true}` |
| Backlight | **always on** — LED pin tied to 3V3 (no PWM/GPIO control) |
| Touch (CTP) | present on the module, **not wired / not used** in this build |
| SD slot | present on the module, **not wired / not used** |
| SPI data rate | 20 MHz |

> **Invert colours:** this panel renders inverted; `invert_colors: true` is
> required or you get dark-on-white. Confirmed on the bench.

> **Declare NATIVE dimensions, not the rotated ones.** The YAML sets
> `dimensions: {width: 320, height: 480}` (the panel's real portrait geometry)
> and rotates to landscape with `transform: swap_xy: true`. Declaring the
> already-rotated `480×320` *and* swapping made LVGL map widget **width** onto
> the short physical axis — `bar`s rendered as tall vertical strips instead of
> short horizontal bars. Native `320×480` + `swap_xy` gives LVGL a consistent
> 480×320 landscape canvas, so bars render correctly. Confirmed on the bench.

---

## Connection mapping — ESP32-S3 ⟷ ILI9488 TFT

Only the **8 display wires** are connected. The module's touch (`T_*`) pins and
the SD-card header are intentionally left unconnected.

### Wiring table

| TFT pin (silkscreen) | Wire role | → ESP32-S3 pin | Notes |
|----------------------|-----------|----------------|-------|
| **VCC** | power in | **5V** | board's onboard regulator makes 3.3 V for logic |
| **GND** | ground | **GND** | common ground |
| **LED** | backlight | **3V3** | always on at full brightness |
| **SCK** | SPI clock | **IO14** | |
| **SDI (MOSI)** | SPI data in | **IO9** | ESP32 → TFT |
| **SDO (MISO)** | SPI data out | *(not connected)* | display-only; readback unused |
| **DC** | data/command | **IO11** | |
| **RESET (RST)** | reset | **IO13** | |
| **CS** | chip select | **IO10** | |
| **T_* (touch)** | touch SPI/I²C | *(not connected)* | CTP unused in this build |
| **SD_* (SD card)** | SD SPI | *(not connected)* | SD unused in this build |

### J1 header — physical pin order (14-pin, as silkscreened)

The display's main header is **J1**, a single 14-pin row. Pin **1 = VCC** (nearest
the board corner / mounting hole) and pin **14 = T_IRQ** at the far end. Read the
silkscreen on your board to confirm orientation before wiring.

```
J1 pin:  1    2    3    4     5    6    7    8   9         10   11    12    13    14
label:  VCC  GND  CS  RESET  DC  SDI  SCK  LED  SDO       T_CLK T_CS  T_SDI T_SDO T_IRQ
             (RESET=RST)    (MOSI)      (MISO)            └──── RTP resistive-touch pins ────┘
wired:  5V   GND IO10 IO13  IO11 IO9  IO14 3V3  n/c        n/c   n/c   n/c   n/c   n/c
```

- Pins **1–8 + SDO(9)** are the display SPI block; only pins 1–8 are wired (SDO/MISO
  left floating — the firmware never reads back).
- Pins **10–14** (`T_CLK/T_CS/T_SDI/T_SDO/T_IRQ`) are the **RTP** (resistive-touch)
  bus — **not** the capacitive touch. This build wires none of them. The capacitive
  touch (CTP) uses the separate 6-pin FPC connector, not J1 (see the touch section).
- **J4** (4-pin, opposite edge) is the micro-SD SPI header
  (`SD_CS / SD_MOSI / SD_MISO / SD_SCK`) — also unwired.

### Simple layout diagram

```
            ESP32-S3 (sparkleIoT XH-S3E)                 3.5" ILI9488 TFT
         ┌────────────────────────────────┐           ┌────────────────────┐
         │                              5V├───────────┤VCC                 │
         │                             GND├───────────┤GND                 │
         │                             3V3├───────────┤LED  (backlight)    │
         │                            IO14├───────────┤SCK  (clock)        │
         │                             IO9├───────────┤SDI  (MOSI)         │
         │                            IO11├───────────┤DC                  │
         │                            IO13├───────────┤RST                 │
         │                            IO10├───────────┤CS                  │
         │                                │    (n/c)  │SDO (MISO)          │
         │                                │    (n/c)  │T_* touch, SD_* card│
         └────────────────────────────────┘           └────────────────────┘
          USB-C ↔ /dev/cu.usbserial-10
          (UART bridge — flash @ 115200)
```

### SPI bus summary (what the firmware declares)

| ESPHome key | Value |
|-------------|-------|
| `spi: clk_pin` | GPIO14 |
| `spi: mosi_pin` | GPIO9 |
| `display: cs_pin` | GPIO10 |
| `display: dc_pin` | GPIO11 |
| `display: reset_pin` | GPIO13 |
| `display: data_rate` | 20MHz |

---

## Pin-choice rationale (avoid the traps we hit)

- **ESP32-S3 strapping pins are GPIO0, GPIO3, GPIO45, GPIO46.** Do **not** put a
  display control line (DC/RST/CS) on any of these — a wire holding a strapping
  pin at boot can block download mode and prevent reflashing. (We learned this
  the hard way: DC on GPIO3 made uploads fail with
  `Failed to connect ... No serial data received`.)
- **Avoid GPIO19/GPIO20** (USB D-/D+) and the excluded set the user reserved
  (IO35–42, 45, 16, 15, 47, 48).
- The chosen pins **IO9, IO10, IO11, IO13, IO14** are all plain GPIOs, broken
  out on the header, and safe for SPI.

---

## Flashing notes specific to this board

- **Upload speed: 115200.** The UART bridge drops data at 921600
  (`Changing baud rate to 921600... Changed.` then fail). Always pass a low baud.
- Auto-reset works (UART bridge drives DTR/RTS) — no BOOT/RESET button dance
  needed for normal flashing, unlike a native-USB board.
- First flash over USB; subsequent updates **over-the-air** once it's on WiFi
  (`esphome upload iy-homelab-35.yaml --device 192.168.0.232`).

```bash
# USB (esptool direct, reliable baud):
esptool --chip esp32s3 --port /dev/cu.usbserial-10 --baud 115200 \
  --before default-reset --after hard-reset write-flash -z 0x0 \
  .esphome/build/iy-homelab-35/build/firmware.factory.bin

# or via esphome (it will pick the bridge):
.venv/bin/esphome run iy-homelab-35.yaml --device /dev/cu.usbserial-10
```

---

## Backlight

The TFT **LED** pin is wired to **3V3**, so the backlight is permanently on at
full brightness (matches the "always-on" requirement). There is no PWM/GPIO
dimming for this build. To add brightness control later, move **LED** to a free
PWM-capable GPIO and add an `output: ledc` + `light: monochromatic` (see the C6
build's backlight section in [`hardware.md`](hardware.md)).

---

## Naming note

- ESPHome device `name:` is **`iy-homelab-35`** → Home Assistant entity IDs are
  prefixed `iy_homelab_35_*`. This is **separate** from the original
  `iy-homelab-display`; both devices can run at once.
- The on-screen title shows **KUBELAB** (changed from "KUBELAB HOMELAB").
  Renaming the title does not change the device name or HA entity IDs.

---

# Future development — capacitive touch (CTP)

The module has a built-in **FT6236 capacitive touch controller** (I²C) — the
`CTP Interface` on the board back exposes `INT / NC / SDA / RST / SCL`. It is
**not wired** in the current single-screen build. This section is the plan for
adding it later; nothing here is connected yet.

## Proposed touch wiring (FT6236 over I²C)

Four extra wires (plus the shared GND/3V3 the display already provides). Chosen
GPIOs avoid the SPI pins (9/10/11/13/14), the strapping pins (0/3/45/46), and
the reserved set (IO35–42, 45, 16, 15, 47, 48).

| CTP FPC pin | Role | → ESP32-S3 pin | Notes |
|-------------|------|----------------|-------|
| **1 VDD** | power | **3V3** (shared w/ display) | FT6236 runs at 3.3 V |
| **2 SDA** | I²C data | **IO4** | FT6236 is at I²C addr `0x38` |
| **3 SCL** | I²C clock | **IO5** | |
| **4 INT** | touch interrupt | **IO6** | active-low "touch ready"; lets ESPHome react on touch instead of polling |
| **5 RST** | touch reset | **IO7** | optional but recommended |
| **6 GND** | ground | **GND** (shared w/ display) | common ground |

### CTP connector layout (physical pin order on the module)

There are **two** capacitive-touch references silkscreened on this board — don't
confuse them:

1. **The on-board `CTP Interface` table** (printed next to the `RTP Interface`
   table) lists the logical signals: `INT · NC · SDA · RST · SCL`.
2. **The actual 6-pin FPC connector** (the small flat-flex socket near `Q1`,
   numbered `1`→`6`) is what you physically plug/solder to. Its silkscreen reads:

```
  3.5" 35002 V1.2 — CTP flat-flex connector (6-pin, near Q1)
  ┌─────┬─────┬─────┬─────┬─────┬─────┐
  │  1  │  2  │  3  │  4  │  5  │  6  │   <- FPC pin numbers
  │ VDD │ SDA │ SCL │ INT │ RST │ GND │   <- silkscreen labels
  └──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴──┬──┘
     │     │     │     │     │     │
   3V3   IO4   IO5   IO6   IO7   GND
   (pwr) (SDA) (SCL) (INT) (RST) (gnd)
          │     │     │     │
          │     │     │     └──► ESP32-S3 IO7  (touch reset)
          │     │     └────────► ESP32-S3 IO6  (touch interrupt, active-low)
          │     └──────────────► ESP32-S3 IO5  (I²C clock)
          └────────────────────► ESP32-S3 IO4  (I²C data, FT6236 @ 0x38)
```

- Pins **1 (VDD)** and **6 (GND)** take the display's shared 3V3 / GND — the
  FT6236 runs at 3.3 V.
- Only four signal wires are new: **SDA→IO4, SCL→IO5, INT→IO6, RST→IO7** — all
  broken out on the ESP32-S3 **left-lower header** (`… IO7 IO6 IO5 IO4`), clear
  of the SPI pins (9/10/11/13/14), the strapping pins (0/3/45/46), and the
  reserved set.

> **Pad-order caution:** different 35002 batches reorder these pads or swap the
> FPC-vs-pin-header footprint. Trust the silkscreen on *your* board over this
> diagram — read the `1…6` labels, then map `SDA→IO4, SCL→IO5, INT→IO6,
> RST→IO7, VDD→3V3, GND→GND`.

### Updated layout diagram (display + touch)

```
            ESP32-S3 (sparkleIoT XH-S3E)                 3.5" ILI9488 + FT6236
         ┌────────────────────────────────┐           ┌──────────────────────┐
         │   --- display (SPI) ---      5V├───────────┤VCC                   │
         │                             GND├───────────┤GND                   │
         │                             3V3├───────────┤LED (backlight)       │
         │                            IO14├───────────┤SCK                   │
         │                             IO9├───────────┤SDI (MOSI)            │
         │                            IO11├───────────┤DC                    │
         │                            IO13├───────────┤RST                   │
         │                            IO10├───────────┤CS                    │
         │   --- touch (I2C, FT6236) --- │            │                      │
         │                             IO4├───────────┤CTP SDA               │
         │                             IO5├───────────┤CTP SCL               │
         │                             IO6├───────────┤CTP INT               │
         │                             IO7├───────────┤CTP RST               │
         └────────────────────────────────┘           └──────────────────────┘
```

### ESPHome config sketch (for when touch is wired)

```yaml
i2c:
  sda: GPIO4
  scl: GPIO5
  scan: true           # on first boot, confirm FT6236 answers at 0x38

touchscreen:
  - platform: ft63x6   # FT6236/FT6336 family
    id: my_touch
    interrupt_pin: GPIO6
    reset_pin: GPIO7
    # calibration: swap/mirror to match the display transform if taps are offset
    transform:
      swap_xy: true
      mirror_x: false
      mirror_y: true
```

> **Bring-up gate:** with `i2c: scan: true`, the boot log must show a device at
> `0x38`. If taps land in the wrong place, adjust the touchscreen `transform`
> (not the display's) until a tap top-left registers top-left.

See [`TOUCH-ROADMAP.md`](TOUCH-ROADMAP.md) for the feature plan that this wiring
unlocks.
