# Integrations — metrics bridge

`proxmox_bridge.py` reads homelab telemetry and publishes it into Home
Assistant as `sensor.*` entities. The ESP32 display subscribes to those
entities over the encrypted ESPHome API.

## Published entities

| Entity | Source | Unit |
|--------|--------|------|
| `sensor.kubelab_{1,2,3}_cpu_usage` | Proxmox API | % |
| `sensor.kubelab_{1,2,3}_memory_usage` | Proxmox API | % |
| `sensor.kubelab_{1,2,3}_status` | Proxmox API | online/offline |
| `sensor.kubelab_{1,2,3}_temperature` | lm-sensors over SSH | °C (CPU package) |
| `sensor.homelab_kubernetes_health` | kubectl | Healthy/Degraded/Critical |
| `sensor.homelab_kubernetes_nodes_ready` | kubectl | nodes |
| `sensor.homelab_kubernetes_nodes_total` | kubectl | nodes |
| `sensor.homelab_kubernetes_pods_not_ready` | kubectl | pods |

> UPS is deferred — no `sensor.homelab_ups_battery_charge` is published yet.
> The bridge has a reserved `UPS_SOURCE` env var for when a NUT/SNMP source
> is added.

## Setup

```bash
cp bridge.env.example bridge.env     # fill in HA + Proxmox tokens
# HA_TOKEN defaults to $HA_TOKEN from ~/.zsh_profile
source bridge.env
python3 proxmox_bridge.py            # foreground, Ctrl-C to stop
```

One-shot (publish once and exit) — handy for testing:
```bash
ONESHOT=1 python3 proxmox_bridge.py
```

## Run always-on (macOS launchd)

```bash
cp com.iyhomelab.bridge.plist.example ~/Library/LaunchAgents/com.iyhomelab.bridge.plist
# edit the absolute repo path in the plist if needed
launchctl load -w ~/Library/LaunchAgents/com.iyhomelab.bridge.plist
# logs: /tmp/iy-homelab-bridge.log  /  /tmp/iy-homelab-bridge.err
```

`run-bridge.sh` sources `~/.zsh_profile` (HA token) and `bridge.env` (Proxmox
token + config) so no secrets live in the plist.

## Security

- Proxmox: dedicated `monitoring@pve!display` token, role `PVEAuditor`
  (read-only). Verified denied on write (HTTP 403).
- Proxmox self-signed TLS is pinned by SHA-256 fingerprint (`PVE_FINGERPRINT`),
  not disabled.
- `bridge.env` is gitignored. Never commit it.

## Swapping the Proxmox source for Beszel / SigNoz

See `../docs/architecture.md` → "Alternative metric sources". In short, replace
`collect_proxmox()` with a collector hitting Beszel's PocketBase API or SigNoz's
query-range API; the HA publish + ESP subscription layers stay unchanged.
