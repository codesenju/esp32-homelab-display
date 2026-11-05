# Troubleshooting

## Device / flashing

**No `/dev/cu.usbmodem*` port**
- Check the USB-C cable is data-capable (not charge-only).
- `ls /dev/cu.*`; re-plug; try another port.
- The ESP32-C6 uses native USB-Serial/JTAG — no CP210x/CH34x driver needed.

**esptool can't connect**
- Hold **BOOT**, tap **RESET**, release **BOOT** to force download mode, then
  retry `scripts/detect-device.sh`.

**Wrong chip / flash size reported**
- Confirm with `python -m esptool --port <port> flash-id`. This board must read
  `ESP32-C6` and `8MB`.

## Serial logs look empty

The ESP32-C6 USB-Serial/JTAG peripheral often shows little output unless a host
is draining the port at boot. This is cosmetic. Prefer **network logs**:
```
scripts/monitor.sh <DEVICE_IP>
```
Device liveness can also be confirmed from HA (entry `loaded`, backlight entity
responding) without serial at all.

## Wi-Fi

- 2.4 GHz only (ESP32-C6 Wi-Fi 6 still associates on 2.4 GHz band here).
- Credentials come from `secrets.yaml` (`wifi_ssid` / `wifi_password`).
- If home Wi-Fi is down, the device raises the `IY-HOMELAB Fallback` AP
  (password = OTA password) + captive portal so it stays recoverable.
- Find the IP: `dns-sd -q iy-homelab-display.local` or check the router.

## Home Assistant adoption

**Device not discovered automatically**
- Adopt explicitly:
  ```
  HA_TOKEN=$HA_TOKEN python3 scripts/ha_adopt_esphome.py <DEVICE_IP> 6053 "<noise_psk>"
  ```
  where `<noise_psk>` is `api_encryption_key` from `secrets.yaml`.
- The script will not create a duplicate if the device is already adopted.

**"Invalid encryption key"**
- The key in HA must equal `api_encryption_key` in `secrets.yaml`. Re-adopt
  after a key change (delete the old entry first).

## Display

**Blank screen** – backlight may be off; toggle
`light.iy_homelab_display_lcd_backlight` in HA.

**Inverted / wrong colours** – the ST7789 on this panel needs
`invert_colors: true` and `color_order: bgr`. Both are set.

**Content shifted left/right** – the `offset_width: 34` column offset is
specific to this 172-wide panel; do not remove it.

**Button doesn't switch pages**
- `binary_sensor.iy_homelab_display_page_button` should toggle in HA when you
  press BOOT. If it never changes, the press isn't reaching GPIO9 — confirm you
  press **BOOT** (left, `< PAGE`), not RESET (right). Each press advances
  CPU → MEMORY → TEMP → CPU.

## Temperature page shows `--`

- A node needs `lm-sensors` installed and exposing `coretemp`:
  ```
  ssh root@<node> "apt-get install -y lm-sensors && sensors -j | grep -i package"
  ```
- Temperature is read over SSH by the bridge, so it needs `ENABLE_TEMP=1`, a
  valid `TEMP_SSH_KEY`, and a correct `TEMP_NODE_HOSTS` mapping in `bridge.env`.
- Verify the entity:
  ```
  curl -s $HA_URL/api/states/sensor.kubelab_1_temperature -H "Authorization: Bearer $HA_TOKEN"
  ```

## Metrics show `--` or grey dots

- The bridge isn't publishing. Check it:
  ```
  tail -f /tmp/iy-homelab-bridge.log      # or /tmp/iy-homelab-bridge.err
  ```
- Verify entities exist in HA:
  ```
  curl -s $HA_URL/api/states/sensor.kubelab_1_cpu_usage -H "Authorization: Bearer $HA_TOKEN"
  ```
- Grey dots specifically mean *stale* (no update within 90 s) or the ESP↔HA API
  link is down. Confirm the ESPHome entry is `loaded` in HA.

**Proxmox 401 / token issues**
- The read-only token is `monitoring@pve!display` (role `PVEAuditor`). Recreate:
  ```
  ssh root@<PVE_NODE_IP> "pveum user token remove monitoring@pve display; \
    pveum user token add monitoring@pve display --privsep 0"
  ```
  then update `PVE_TOKEN_SECRET` in `integrations/bridge.env`.

## Kubernetes health shows "Degraded"

That's real: the bridge counts nodes not `Ready` and pods not `Running+Ready`.
Investigate with `kubectl get pods -A | grep -vE 'Running|Completed'`.
