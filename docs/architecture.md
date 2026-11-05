# Architecture

## Data flow

```
 Proxmox VE API (HTTPS :8006, read-only PVEAuditor token)
        │  per-node cpu / mem / status / uptime
        ▼
 integrations/proxmox_bridge.py  ──────────┐
        ▲                                   │  POST /api/states (bearer token)
        │  kubectl (local kubeconfig)       ▼
 Kubernetes API  ────────────►      Home Assistant
   ready/total nodes, bad pods          (sensor.* entities)
                                            │
                                            │  native ESPHome API (Noise-encrypted, :6053)
                                            ▼
                                   ESP32-C6 LCD (LVGL)
                                   Page 1: CPU   Page 2: MEMORY
```

### Why a bridge instead of direct integrations

The Home Assistant instance has no Proxmox, Kubernetes, or NUT/UPS integration
installed (verified via `GET /api/config` → `components`). Rather than install
and maintain three HA custom integrations, a single ~250-line Python bridge
reads the two sources that are actually reachable and publishes plain HA
sensors. This keeps the moving parts minimal and the ESP firmware unchanged if
a source is later swapped.

### Why Home Assistant in the middle (not ESP → Proxmox directly)

- The ESP32 never holds Proxmox / K8s / HA credentials.
- ESPHome's native API is encrypted (Noise) and HA-managed.
- HA gives free history, availability tracking, and a UI for the same data.

## The ESP firmware

- **Framework:** ESP-IDF (recommended for reliable ESP32-C6 support in ESPHome).
- **Display:** `mipi_spi` driving an ST7789 at 172×320 with `offset_width: 34`
  (the panel's column offset), `color_order: bgr`, `invert_colors: true`.
- **UI:** LVGL, two pages, dark theme, colour-coded bars and status dots.
- **Event-driven:** metric widgets update from HA `on_value` callbacks, not a
  blind poll. The clock updates once a minute. A 5 s interval only refreshes the
  connectivity footer and runs the staleness watchdog.
- **Pages & navigation:**
  - Page 1 — `PROXMOX - CPU %` (3 node rows, each labelled `kubelab-N  NN%`).
  - Page 2 — `PROXMOX - MEMORY %` (same 3 nodes, RAM %).
  - Page 3 — `PROXMOX - TEMP C` (same 3 nodes, CPU package temperature in °C;
    bar scales 0–100 °C, colour: <70 green, 70–85 amber, ≥85 red).
  - The on-board **BOOT button (GPIO9)** cycles pages
    (`on_press → next_page`, CPU → MEMORY → TEMP → CPU). All pages are kept
    continuously up to date, so switching is instant.
  - A small `CPU 1/3` / `MEM 2/3` / `TEMP 3/3` indicator shows the active page.
- **Shared rows:** both pages also show Kubernetes health (`K8S <state> R/T`)
  and the clock / Wi-Fi / HA-connection footer.

## Health & staleness logic

| State | Meaning | Colour |
|-------|---------|--------|
| Healthy | node online, worst(cpu,mem) < 60 % | green `0x66D9A0` |
| Warning | worst(cpu,mem) 60–85 % | amber `0xF4C14E` |
| Critical | worst(cpu,mem) ≥ 85 %, or node `offline` | red `0xE8564B` |
| Unknown | missing/`unavailable` metric, or stale, or API down | grey `0x829AA8` |

- A node is **never** shown healthy just because an old CPU value was low: the
  dot colour requires `status == online` and uses the *worst* of CPU/MEM.
- **Staleness:** if no node update arrives within `stale_after` (90 s) — or the
  ESPHome API link to HA drops — node dots go grey. The "HA connected" footer is
  driven by the real API link state (`api::global_api_server->is_connected()`),
  so it can't show "connected" while actually disconnected.
- Unavailable numeric metrics render as `--`.

## UPS

Removed from the current build by request (no UPS source integrated yet). The
bridge still has a reserved `UPS_SOURCE` hook; when a NUT/SNMP UPS is added,
publish `sensor.homelab_ups_battery_charge` and re-add a UPS widget.

## Alternative metric sources (evaluated, not used)

The homelab also runs **SigNoz** (`signoz.example.com`) and **Beszel**
(`beszel.example.com`). For three CPU/MEM gauges the Proxmox API is the
simplest exact-fit source, so those were not wired in. If richer host metrics
(disk, temp, net) are wanted later:

- **Beszel** (PocketBase): needs an API/user auth token; then read
  `GET /api/collections/systems/records`. Swap `collect_proxmox()` for a
  `collect_beszel()` in the bridge.
- **SigNoz** (OTel/ClickHouse): use a SigNoz API key (e.g. from an env var) with
  the query-range API (PromQL). Heavier; best only if you want the display to
  mirror SigNoz dashboards.
