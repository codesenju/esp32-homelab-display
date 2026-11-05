# IY HOMELAB — ESP32-C6 Monitoring Display

An always-on monitoring dashboard for the **IY HOMELAB** running on a
**Waveshare ESP32-C6-LCD-1.47-M** (1.47" ST7789, 172×320, 8 MB flash).

The display shows live Proxmox cluster CPU usage, node health, Kubernetes
cluster health, UPS battery (when available), Wi-Fi / Home Assistant
connectivity, and the current Johannesburg time.

> **New here?** Read [`docs/OVERVIEW.md`](docs/OVERVIEW.md) for a plain-language
> explanation. Replicating this on another homelab (human or agent)? Follow
> [`docs/AGENT_REPLICATION_GUIDE.md`](docs/AGENT_REPLICATION_GUIDE.md).

```
┌─────────────────────┐
│ IY HOMELAB     WiFi │
│ 14:15               │
├─────────────────────┤
│ PROXMOX CLUSTER     │
│ ● kubelab-1   24%   │
│ ███████░░░░░░░░░░   │
│ ● kubelab-2   38%   │
│ ██████████░░░░░░    │
│ ● kubelab-3   16%   │
│ ████░░░░░░░░░░░░░   │
├─────────────────────┤
│ ● K8S Degraded 6/6  │
│ UPS --              │
├─────────────────────┤
│ HA connected        │
└─────────────────────┘
```

## How it works

```
Proxmox API (read-only token) ─┐
                               ├─► metrics bridge ─► Home Assistant ─► (native ESPHome API, encrypted) ─► ESP32-C6 LCD
Kubernetes (kubeconfig) ───────┘        (Mac)          (sensors)
```

The ESP32 holds **no** credentials for Proxmox/K8s/HA. It only speaks the
encrypted ESPHome ↔ Home Assistant API and subscribes to sensor entities that
the bridge (`integrations/proxmox_bridge.py`) publishes into Home Assistant.

See `docs/architecture.md` for details.

## Hardware (verified)

| Property | Value |
|----------|-------|
| Board    | Waveshare ESP32-C6-LCD-1.47-M |
| Chip     | ESP32-C6FH8 (QFN32) rev v0.2 |
| Flash    | 8 MB (device 0x4017) |
| Display  | ST7789, 172×320, SPI |
| MAC      | `XX:XX:XX:XX:XX:XX` |
| USB      | native USB-Serial/JTAG (VID 0x303A / PID 0x1001) |

Pinout (from the Waveshare wiki, matches firmware): MOSI=GPIO6, SCLK=GPIO7,
CS=GPIO14, DC=GPIO15, RST=GPIO21, BL=GPIO22. See `docs/hardware.md`.

## Quick start

```bash
cd <repo>
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -U pip esphome esptool pyserial websocket-client

# 1. secrets
cp secrets.example.yaml secrets.yaml      # fill in wifi/ota/api key
cp integrations/bridge.env.example integrations/bridge.env   # fill in tokens

# 2. identify board
scripts/detect-device.sh

# 3. validate + compile
scripts/validate.sh

# 4. first flash (USB), then OTA afterwards
scripts/flash.sh /dev/cu.usbmodem1101      # USB
# scripts/flash.sh <DEVICE_IP>           # OTA by IP

# 5. run the metrics bridge (publishes entities HA -> ESP subscribes)
./integrations/run-bridge.sh               # foreground
# or install the launchd agent (see integrations/README.md) for always-on
```

## Rebuild / reflash / OTA

| Action | Command |
|--------|---------|
| Validate + compile | `scripts/validate.sh` |
| USB flash | `scripts/flash.sh /dev/cu.usbmodem1101` |
| OTA update (by IP) | `scripts/flash.sh <DEVICE_IP>` |
| Serial logs | `scripts/monitor.sh` |
| Network logs | `scripts/monitor.sh <DEVICE_IP>` |
| Adopt into HA | `HA_TOKEN=$HA_TOKEN python3 scripts/ha_adopt_esphome.py <DEVICE_IP> 6053 "<noise_psk>"` |

## Repository layout

```
kubelab-display/
├── README.md
├── .gitignore
├── iy-homelab.yaml              # ESPHome firmware (LVGL dashboard)
├── secrets.example.yaml         # template; real secrets.yaml is gitignored
├── docs/
│   ├── OVERVIEW.md                 # plain-language "what is this" (start here)
│   ├── AGENT_REPLICATION_GUIDE.md  # how an agent rebuilds this on another homelab
│   ├── architecture.md
│   ├── hardware.md
│   ├── home-assistant-entities.md
│   └── troubleshooting.md
├── scripts/
│   ├── detect-device.sh
│   ├── validate.sh
│   ├── flash.sh
│   ├── monitor.sh
│   └── ha_adopt_esphome.py
└── integrations/
    ├── README.md
    ├── proxmox_bridge.py        # Proxmox + K8s -> Home Assistant
    ├── bridge.env.example       # template; real bridge.env is gitignored
    ├── run-bridge.sh
    └── com.iyhomelab.bridge.plist.example
```

## Security notes

- No tokens live on the ESP32. The HA↔ESP link uses the encrypted ESPHome API.
- Proxmox is read via a dedicated least-privilege `PVEAuditor` token
  (`monitoring@pve!display`) that is denied writes (verified 403 on write).
- `secrets.yaml`, `bridge.env`, `*.pem`, `.env` are gitignored and never committed.
- Proxmox self-signed TLS is pinned by SHA-256 fingerprint, not disabled.
