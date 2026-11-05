# Home Assistant Entity Discovery Report

Generated during IY HOMELAB display build. Entity IDs below are **actual**
identifiers returned by the Home Assistant REST API (`GET /api/states`) on
`https://ha.example.com`. No entity IDs are invented.

## Summary of discovery

At first inspection, the Home Assistant instance had **160 entities** and the
following integrations loaded (from `GET /api/config` → `components`): default
HA core, `mobile_app` (phone companion app sensors), game console,
`zha` (Zigbee), network routers, `backup`, `sun`, `weather`.

**No** monitoring integration for Proxmox, Kubernetes, or UPS/NUT was present:

| Integration looked for | Loaded? |
|------------------------|---------|
| `proxmoxve`            | ❌ no |
| `kubernetes`           | ❌ no |
| `nut` (UPS)            | ❌ no |
| `prometheus` / `rest` / `mqtt` scrapers | ❌ no |
| `esphome`              | ❌ not yet (added on device adoption) |

So none of the Proxmox / K8s / UPS metrics the display needs existed as
native HA entities. They are now supplied by the metrics bridge in
`integrations/proxmox_bridge.py` (see `docs/architecture.md`).

## Entities the display consumes

These are **published by the bridge** into Home Assistant and subscribed to by
the ESP32 over the native ESPHome API. Values shown are a real sample captured
during the build.

### Proxmox cluster (source: Proxmox API, read-only `monitoring@pve!display` token)

| Entity ID | Type | Sample value | Notes |
|-----------|------|--------------|-------|
| `sensor.kubelab_1_cpu_usage`    | % | `14.0`  | node CPU (0–100) |
| `sensor.kubelab_2_cpu_usage`    | % | `73.9`  | node CPU |
| `sensor.kubelab_3_cpu_usage`    | % | `34.9`  | node CPU |
| `sensor.kubelab_1_memory_usage` | % | `80.1`  | mem / maxmem |
| `sensor.kubelab_2_memory_usage` | % | real    | mem / maxmem |
| `sensor.kubelab_3_memory_usage` | % | real    | mem / maxmem |
| `sensor.kubelab_1_status`       | str | `online` | online/offline; `uptime_seconds` attr |
| `sensor.kubelab_2_status`       | str | `online` | |
| `sensor.kubelab_3_status`       | str | `online` | |

### Node temperature (source: lm-sensors over SSH, CPU package temp)

| Entity ID | Type | Sample value | Notes |
|-----------|------|--------------|-------|
| `sensor.kubelab_1_temperature` | °C | `83` | `coretemp` Package id 0 |
| `sensor.kubelab_2_temperature` | °C | `73` | |
| `sensor.kubelab_3_temperature` | °C | `70` | lm-sensors installed during the temp-page addition |

> Proxmox's API does not expose CPU/node temperature, so the bridge reads it via
> `sensors -j` over SSH. Requires `lm-sensors` on each node.

### Kubernetes (source: `kubectl` via local kubeconfig)

| Entity ID | Type | Sample value | Notes |
|-----------|------|--------------|-------|
| `sensor.homelab_kubernetes_health`         | str | `Degraded` | Healthy/Degraded/Critical/Unknown |
| `sensor.homelab_kubernetes_nodes_ready`    | nodes | `6` | Ready nodes |
| `sensor.homelab_kubernetes_nodes_total`    | nodes | `6` | Total nodes (3 control-plane + 3 worker) |
| `sensor.homelab_kubernetes_pods_not_ready` | pods | `7` | Pods not in Running+Ready (real: CrashLoopBackOff/Pending) |

> The sample `Degraded` / `7 pods not ready` is **genuine cluster state** at
> capture time (crowdsec, nexus-postgres, temporal-postgres, stirling-pdf etc.
> were unhealthy), not placeholder data.

### UPS

**Deferred by request.** No `sensor.homelab_ups_battery_charge` is published
and the display has no UPS widget in the current build. No UPS is integrated
into Home Assistant and no NUT/SNMP UPS endpoint was discoverable on the
network. When a UPS source is added later, wire it into
`integrations/proxmox_bridge.py` (`UPS_SOURCE`) to publish
`sensor.homelab_ups_battery_charge` and re-add a UPS widget to the firmware.

### Home Assistant connection

The display does **not** need an HA entity for HA connectivity — it derives
"HA connected" from the ESPHome native API connection state
(`api.connected` lambda), which is the authoritative signal and cannot be
spoofed by a stale sensor value.

## Pre-existing entities (NOT used by this display, left untouched)

The Home Assistant instance also had unrelated pre-existing entities — phone
companion-app sensors, game console, network routers, backup status, sun and
weather. None of them are read or modified by this display; they are listed
here only to note that the display scopes itself narrowly to the homelab
metrics and leaves everything else alone.
