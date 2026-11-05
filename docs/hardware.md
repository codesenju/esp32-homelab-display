# Hardware — Waveshare ESP32-C6-LCD-1.47-M

## Verified identity (esptool)

```
Chip type:  ESP32-C6FH8 (QFN32) (revision v0.2)
Features:   Wi-Fi 6, BT 5 (LE), IEEE802.15.4, Single Core + LP Core, 160MHz, Embedded Flash 8MB
Flash:      8 MB  (manufacturer 0x20, device 0x4017)
Base MAC:   XX:XX:XX:XX:XX:XX
USB:        native USB-Serial/JTAG  (VID 0x303A "Espressif" / PID 0x1001)
Serial port (macOS): /dev/cu.usbmodem1101
```

> Note: some Waveshare wiki revisions describe an ESP32-C6**FH4** (4 MB) board.
> The unit in hand is the **FH8 / 8 MB** variant — trust esptool, not the wiki
> blurb. The firmware sets `flash_size: 8MB`.

## Display

| Property | Value |
|----------|-------|
| Panel | 1.47" TFT, ST7789 controller |
| Resolution | 172 × 320 (portrait) |
| Column offset | 34 px (`offset_width: 34`) |
| Colour | 16-bit, `color_order: bgr`, `invert_colors: true` |
| SPI mode | MODE3, 40 MHz |

## Pin map (Waveshare wiki — matches firmware)

| Function | GPIO |
|----------|------|
| SPI MOSI | GPIO6 |
| SPI SCLK/CLK | GPIO7 |
| LCD CS | GPIO14 |
| LCD DC | GPIO15 *(strapping pin — warning is expected)* |
| LCD RST | GPIO21 |
| LCD Backlight (PWM) | GPIO22 |
| RGB LED | GPIO8 (unused here) |
| TF card CS / MISO | GPIO4 / GPIO5 (unused here) |
| **BOOT button** | **GPIO9** *(user button for page switching)* |
| RESET button | EN (hardware reset) |

### Buttons

- **BOOT (GPIO9):** used as the page-switch button. GPIO9 is the boot-strap
  pin; at runtime it idles HIGH (internal pull-up) and reads LOW when pressed,
  so the firmware configures it `pullup: true, inverted: true`. Each press
  fires `on_press → next_page`, cycling **CPU → MEMORY → TEMP → CPU**. It's
  exposed to Home Assistant as `binary_sensor.iy_homelab_display_page_button`.
- **RESET:** hardware reset only; not software-readable.

> **Naming note:** the ESPHome device `name:` is `iy-homelab-display`, so Home
> Assistant entity IDs are prefixed `iy_homelab_display_*`. The on-screen title
> shows **KUBELAB**. These are intentionally independent — renaming the display
> title does not change the device name or its HA entity IDs.

## Backlight

PWM on GPIO22 via `ledc` + a `monochromatic` light. Starts at **40 %** on boot
(`on_boot`), and is exposed to HA as `light.iy_homelab_display_lcd_backlight`
for remote dimming.

## Flash partitions (from boot log)

```
otadata   0x009000  0x002000
phy_init  0x00b000  0x001000
app0      0x010000  0x3c0000   (OTA slot A, ~3.75 MB)
app1      0x3d0000  0x3c0000   (OTA slot B, ~3.75 MB)
nvs       0x790000  0x070000
```

Two large OTA app slots → OTA updates fully supported. App image is ~1.27 MB
(≈32 % of a slot), leaving ~68 % headroom.
