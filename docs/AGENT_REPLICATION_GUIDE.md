# Agent Replication Guide — IY HOMELAB style ESP32 monitoring display

Audience: an autonomous coding agent asked to build the same thing on a
**different** person's homelab. This is a procedure, not a script to run blind.
Discover the target environment first; never assume the values from the
reference build (IPs, SSIDs, tokens, entity names) carry over.

> Golden rules
> 1. Positively identify the chip/flash before flashing. Don't guess the port.
> 2. No secrets on the microcontroller, ever. Use the encrypted ESPHome↔HA API.
> 3. Don't invent Home Assistant entity IDs — discover the real ones.
> 4. Verify each stage with evidence before claiming it works. "Compiled" ≠
>    "running". "Flashed" ≠ "displaying correct data".
> 5. Prefer existing data sources over building new ones. A metrics bridge is a
>    fallback, not the goal.
> 6. Never disable TLS verification to "make it work". Pin a fingerprint instead.

---

## 0. Inputs you must gather from the user / environment

| Need | How to get it | Notes |
|------|---------------|-------|
| The board model | Ask / inspect USB | This guide assumes a Waveshare ESP32-C6-LCD-1.47 (ST7789 172×320). Other boards change pins + display driver. |
| Home Assistant URL | Ask | e.g. `https://ha.example.com` |
| HA long-lived token | Env var or user | Create under HA → Profile → Security if absent. **Use the var name that actually exists; flag, don't silently rename, any mismatch.** |
| WiFi SSID + password (2.4 GHz) | Ask / env / keychain | ESP32-C6 needs a 2.4 GHz SSID. |
| Metric sources | Discover (step 4) | Proxmox? Kubernetes? UPS? SigNoz/Beszel/Prometheus? |

Create the project dir and a Python venv:

```bash
mkdir -p <repo> && cd <repo>
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -U pip esphome esptool pyserial websocket-client
```

Pinned reference versions that are known-good: ESPHome `2026.10.2`,
esptool `5.x`, aioesphomeapi `46.x`. Newer is usually fine.

---

## 1. Identify the board (do NOT skip)

```bash
ls /dev/cu.* 2>/dev/null                 # macOS; /dev/ttyUSB*|ttyACM* on Linux
ioreg -p IOUSB -l -w 0 | grep -iE "idVendor|idProduct|USB Product|Serial Number"  # macOS
python -m esptool --port <PORT> chip-id  # must print the expected chip
python -m esptool --port <PORT> flash-id # read REAL flash size
```

Record: chip model, **flash size** (e.g. ESP32-C6FH8 ⇒ 8 MB), MAC, port.
Espressif VID is `0x303A`. The ESP32-C6 uses native USB-Serial/JTAG — no driver
needed. If no port appears: bad cable (charge-only), or hold BOOT + tap RESET to
enter download mode.

**Gate:** you can name the exact chip and flash size from `esptool` output.

---

## 2. Confirm hardware pinout from the vendor, not from a compile

For the Waveshare ESP32-C6-LCD-1.47 (verified against the wiki):

| Function | GPIO |  | Function | GPIO |
|----------|------|--|----------|------|
| SPI MOSI | 6 |  | LCD RST | 21 |
| SPI SCLK | 7 |  | LCD Backlight (PWM) | 22 |
| LCD CS | 14 |  | BOOT button (user) | 9 |
| LCD DC | 15 |  | RGB LED | 8 |

Display: ST7789, 172×320, `offset_width: 34`, `color_order: bgr`,
`invert_colors: true`, SPI MODE3. A different board ⇒ re-derive all of this.

**Gate:** pin map comes from the datasheet/wiki, not "it compiled".

---

## 3. Load auth securely + test HA connectivity

```bash
# Confirm the token var EXISTS without printing it:
[ -n "$HA_TOKEN" ] && echo "token present (len=${#HA_TOKEN})" || echo MISSING
curl --fail-with-body -sS "$HA_URL/api/" -H "Authorization: Bearer $HA_TOKEN"
# expect: {"message":"API running."}
```

If TLS fails because of a private CA, fix trust — do not add `-k`/`--insecure`
to anything that ships. For self-signed service certs you control (e.g.
Proxmox), pin the SHA-256 fingerprint in the bridge instead.

**Gate:** `/api/` returns `API running.` over verified TLS.

---

## 4. Discover real metric sources (decision point)

Pull everything and classify:

```bash
curl -s "$HA_URL/api/states"  -H "Authorization: Bearer $HA_TOKEN" > /tmp/states.json
curl -s "$HA_URL/api/config"  -H "Authorization: Bearer $HA_TOKEN"   # -> components[]
```

Check which integrations are loaded (`components`) and whether entities already
exist for your targets (CPU, mem, node status, cluster health, UPS). Decision
tree:

```
Do HA entities already exist for the metrics?
├─ YES → subscribe to them directly from ESPHome. No bridge. Best outcome.
└─ NO  → Is there a reachable source?
         ├─ Proxmox API (:8006)      → bridge reads it with a read-only token
         ├─ Kubernetes (kubeconfig)  → bridge runs kubectl
         ├─ Prometheus / SigNoz      → bridge queries PromQL/range API
         ├─ Beszel (PocketBase)      → bridge reads /api/collections/systems/records (needs token)
         └─ none reachable           → record the gap; display "--" for it
```

Write a **sanitized** discovery report to `docs/home-assistant-entities.md`
using the *real* entity IDs you found (and the gaps). Never fabricate IDs.

**Gate:** the YAML in step 7 references only entity IDs that exist (or that the
bridge in step 5 will create).

---

## 5. (If needed) Build the metrics bridge

A ~250-line Python script (`integrations/proxmox_bridge.py` is the reference)
that: reads sources → `POST $HA_URL/api/states/<entity>` with the bearer token →
HA now has `sensor.*` entities the ESP can subscribe to. Key design points:

- **Least privilege.** For Proxmox, create a dedicated read-only token, don't
  use root:
  ```bash
  ssh root@<pve-node> \
    'pveum user add monitoring@pve 2>/dev/null; \
     pveum acl modify / --users monitoring@pve --roles PVEAuditor; \
     pveum user token add monitoring@pve display --privsep 0'
  ```
  Then verify it is **denied writes** (expect HTTP 403 on a POST). Pin the
  node's TLS fingerprint (`openssl s_client ... | openssl x509 -fingerprint
  -sha256`) rather than disabling verification.
- **Health classification happens in the bridge or the firmware**, consistently:
  online + worst(cpu,mem) <60 = healthy, 60–85 = warning, ≥85 or offline =
  critical, missing/stale = unknown. A node is never "healthy" just because an
  old CPU reading was low — require `status == online`.
- **Config via a gitignored `bridge.env`** (HA token, source tokens, fingerprint,
  node list, poll interval). Ship a `bridge.env.example` with placeholders.
- Run it: foreground for testing (`ONESHOT=1` to publish once), then as a
  service. macOS: a launchd user agent (`com.*.bridge.plist`) that sources the
  env via a wrapper. Linux: a systemd user service with `EnvironmentFile=`.

**Gate:** `curl $HA_URL/api/states/<new_entity>` returns real, changing values.

---

## 6. Secrets & encryption keys

```bash
# ESPHome native-API encryption key (base64, 32 bytes):
python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
# OTA password:
python3 -c "import secrets;print(secrets.token_hex(24))"
```

Put `wifi_ssid`, `wifi_password`, `ota_password`, `api_encryption_key` into a
**gitignored `secrets.yaml`**. Ship `secrets.example.yaml` with placeholders.
`.gitignore` must cover `secrets.yaml`, `bridge.env`, `.env`, `*.pem`, `*.key`.
Verify with `git check-ignore secrets.yaml`.

**Never** put a HA long-lived token on the ESP. The ESP uses only the
`api_encryption_key` (Noise PSK).

---

## 7. Write the firmware (`iy-homelab.yaml`)

Reference file is in the repo root; adapt names/entities. Essentials:

- `esp32:` with the **real** `flash_size`, `variant: esp32c6`,
  `framework: type: esp-idf` (ESP-IDF is recommended for reliable C6 support).
- `api:` with `encryption: key: !secret api_encryption_key` and
  `reboot_timeout: 0s` (don't reboot when HA blips).
- `ota:`, `wifi:` (+ a fallback `ap:` and `captive_portal:` for recoverability),
  `time:` SNTP with the user's timezone.
- `display:` `platform: mipi_spi`, ST7789 geometry from step 2.
- `sensor:`/`text_sensor:` `platform: homeassistant` entries that subscribe to
  the discovered/created entity IDs, with `on_value:` → render scripts (event
  driven; do not blind-poll).
- `lvgl:` dark theme, one page per metric group. **Multi-page + button nav:**
  a `binary_sensor` on the user button (GPIO9 here; `pullup: true, inverted:
  true` because it's a boot-strap pin) with `on_press:` cycling pages. Keep all
  pages continuously updated so switching is instant.
- **On-screen button legend** in the bottom corners matching the physical
  buttons (`< PAGE` for the user button, `RESET >` dimmed for the hw reset).
- **Connectivity truthfully:** derive "HA connected" from
  `api::global_api_server->is_connected()`, never from a sensor value. Grey out
  data older than a staleness threshold (`millis()` timestamps + a 5s interval
  watchdog).
- **Glyph gotcha:** text fonts (Montserrat) lack `●` (U+25CF). Use a dedicated
  `font:` including `•` (U+2022) for status dots, or draw LVGL circles.
  Avoid em-dashes/arrows not in the font — they render as boxes. Prefer ASCII
  (`<`, `>`, `-`) unless you add the glyph.

Validate + compile:

```bash
esphome config  iy-homelab.yaml   # must end "Configuration is valid!"
esphome compile iy-homelab.yaml   # must end "Successfully compiled program."
```

If compile fails: read the real error, fix the actual cause, re-validate. Don't
declare success with errors outstanding. Check the size report shows two OTA app
slots and the image fits with headroom.

**Gate:** clean compile + a partition layout that supports OTA.

---

## 8. Flash (USB first, then OTA)

```bash
esphome upload iy-homelab.yaml --device <PORT>          # first flash over USB
# later:
esphome upload iy-homelab.yaml --device <DEVICE_IP>     # OTA over network
```

Watch logs (`esphome logs ... --device <PORT|IP>`). On ESP32-C6 the USB-JTAG
logger is sparse — prefer network logs. Confirm from the boot log: flash size,
`setup() finished successfully`, WiFi `Connected`, and the OTA-capable partition
table.

**Gate:** device boots once (no reboot loop; look for the safe-mode "boot
seems successful" line), joins WiFi, and gets an IP (mDNS `<name>.local` or
router/ARP).

---

## 9. Adopt into Home Assistant

HA with `zeroconf` usually auto-discovers the device. To do it headless with
just the token (no browser login), drive the REST config flow:

```bash
# start flow
curl -s -X POST "$HA_URL/api/config/config_entries/flow" \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"handler":"esphome","show_advanced_options":true}'          # -> flow_id, step "user"
# submit host/port
curl -s -X POST "$HA_URL/api/config/config_entries/flow/<FLOW_ID>" \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"host":"<DEVICE_IP>","port":6053}'                          # -> step "encryption_key"
# submit the Noise PSK (api_encryption_key from secrets.yaml)
curl -s -X POST "$HA_URL/api/config/config_entries/flow/<FLOW_ID>" \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"noise_psk":"<KEY>"}'                                       # -> type "create_entry"
```

(The reference `scripts/ha_adopt_esphome.py` wraps this and refuses to create a
duplicate.) If a browser session is needed for something REST can't do, use
Playwright — but assume it has no cookies and may hit a login wall; fall back to
REST.

**Gate:** the esphome config entry shows `state: loaded` and the device's own
entities (e.g. the backlight light) appear in `/api/states`.

---

## 10. Verify end-to-end with evidence

Don't trust "it should work". Check:

- **Data path:** `curl $HA_URL/api/states/<metric>` shows live, changing values
  AND the esphome entry is `loaded`.
- **Bidirectional API (proves the subscribe channel):** toggle the device's
  backlight via `POST /api/services/light/turn_on` with `brightness_pct` and
  read the reported `brightness` back. If control round-trips, subscriptions
  work.
- **OTA:** a successful `esphome upload --device <IP>` ("OTA successful",
  "Encrypted connection established").
- **Resilience:** after an OTA reboot the device reconnects and the entry
  returns to `loaded`.
- **Button:** the button's `binary_sensor` toggles in HA when pressed.
- **The one thing you cannot self-verify:** the actual pixels on the LCD and a
  physical button press. State this limitation explicitly and ask the user to
  confirm (a photo is ideal). Do not claim a visual PASS without evidence.

Report every item as PASS / FAIL / BLOCKED / NOT TESTED with the evidence.

---

## 11. Repository layout to leave behind

```
<repo>/
├── README.md
├── .gitignore                      # secrets.yaml, bridge.env, .env, *.pem, *.key
├── iy-homelab.yaml
├── secrets.example.yaml
├── docs/{OVERVIEW,architecture,hardware,home-assistant-entities,troubleshooting}.md
├── scripts/{detect-device,validate,flash,monitor}.sh + ha_adopt_esphome.py
└── integrations/{proxmox_bridge.py,bridge.env.example,run-bridge.sh,*.plist.example,README.md}
```

Commit with a non-interactive identity if none is set
(`git -c user.name=... -c user.email=... commit`). Before committing, grep the
staged set for real secret values and confirm `git check-ignore` covers the
secret files.

---

## Pitfalls observed in the reference build (save yourself the loops)

- **Flash size lie:** starter YAML said 4 MB; the chip was 8 MB. Trust esptool.
- **Token name mismatch:** the brief referenced a misspelled env var that didn't
  exist; the real one had the correct spelling. Flag it; use the var that
  exists; don't silently rename.
- **No Proxmox/K8s/UPS integration in HA** — expected to subscribe, had to build
  the bridge. Check `components` early so you plan for this.
- **Missing glyphs** render as boxes (`●`, em-dash, `‹›`). Add a glyph font or
  use ASCII.
- **ESP32-C6 USB-serial logs are sparse** — verify via HA/network, not serial.
- **GPIO9 is a boot-strap pin** — fine as a runtime button, but holding it during
  reset enters download mode (blank screen until next clean reset).
- **UPS/other gaps:** ship the working dashboard anyway, show `--`/unknown for
  missing metrics; don't block the whole build on one source.
