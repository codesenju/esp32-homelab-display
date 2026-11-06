# Touch feature roadmap — 3.5" ILI9488 (FT6236 CTP)

A plan for what to build **once the capacitive touch is wired** (see the touch
wiring table in [`hardware-35.md`](hardware-35.md#proposed-touch-wiring-ft6236-over-i2c)).
The current build is a read-only, single-screen dashboard. Touch turns it into
an **interactive homelab control surface** — the goal is to let someone glance
at the display and act on what they see without reaching for a laptop.

Guiding principles (carried over from the project's rules):

1. **No secrets on the ESP.** Every action is a Home Assistant service call over
   the existing encrypted API — the device never holds Proxmox/K8s credentials.
2. **Confirm destructive actions on-device.** A tap that reboots a node must
   require a second confirm tap; never one-tap-destroy.
3. **Least privilege in the bridge.** Any new "action" (reboot a node, cordon,
   restart a pod) is a dedicated, auditable HA service backed by a
   least-privilege token in the bridge — not root.
4. **Truthful UI.** Buttons disable/grey out when the backing data is stale or
   the API is disconnected, so you never act on a lie.

## Table of contents

- [Phase 1 — Navigation & comfort](#phase-1--navigation--comfort-low-risk-read-only)
- [Phase 2 — Safe, reversible actions](#phase-2--safe-reversible-actions-medium-risk-confirm-on-tap)
- [Phase 3 — Higher-impact controls](#phase-3--higher-impact-controls-high-risk-hard-confirm--guard-rails)
- [Phase 4 — Proactive / ambient intelligence](#phase-4--proactive--ambient-intelligence-nice-to-have)
- [Suggested build order](#suggested-build-order)
- [Implementation checklist (per feature)](#implementation-checklist-per-feature)

---

## Phase 1 — Navigation & comfort (low risk, read-only)

Pure UI; no new backend. Makes the single screen scale to more info.

| Feature | Touch gesture | Why it helps |
|---------|---------------|--------------|
| **Swipeable pages** | swipe left/right | Add detail pages (per-node drill-down, network, storage, UPS) without cramming one screen. The current single screen stays as the "home" overview. |
| **Tap a node row → detail** | tap row | Opens kubelab-N detail: load avg, disk %, uptime, per-core temp, top pods on that node. |
| **Tap the clock → brightness/sleep** | tap | Dim or blank the backlight on a schedule / tap-to-wake (saves burn-in, nicer at night). Needs LED moved to a PWM GPIO (see hardware-35 backlight note). |
| **Pull-to-refresh** | swipe down | Force an immediate bridge poll instead of waiting for the interval. |

**Backend needed:** none for navigation; brightness needs the LED on a PWM pin
+ an `output/light` in YAML.

---

## Phase 2 — Safe, reversible actions (medium risk, confirm-on-tap)

Each is a Home Assistant `button`/`script` entity the bridge or HA exposes; the
display calls it via `homeassistant.service`. All require a **confirm step**.

| Feature | Flow | Backend (HA service) |
|---------|------|----------------------|
| **Acknowledge / silence an alert** | tap a red node → "Ack" | `script.kubelab_ack_alert` (clears a banner, mutes repeat) |
| **Cordon / uncordon a K8s node** | tap node → "Cordon" → confirm | bridge runs `kubectl cordon/uncordon <node>` via a scoped service |
| **Restart a workload** | tap a failing pod/deployment → confirm | `kubectl rollout restart deploy/<x>` in the bridge |
| **Toggle a HA automation / scene** | tap a tile | `automation.turn_on/off`, `scene.turn_on` — e.g. "quiet hours", "lab lights" |
| **Wake-on-LAN a host** | tap offline node → "Wake" | `button.wol_<host>` (HA WoL integration) |

**Why it helps:** the two most common homelab micro-tasks — "that node is hot/stuck,
bounce the workload" and "ack this so it stops nagging" — become a 2-tap action
at the rack instead of SSH + kubectl from another room.

---

## Phase 3 — Higher-impact controls (high risk, hard-confirm + guard rails)

Only with explicit guard rails: a confirm dialog, a visible countdown, an
audit-logged HA service, and auto-disable when data is stale.

| Feature | Guard rails | Backend |
|---------|-------------|---------|
| **Reboot a Proxmox node** | hold-to-confirm 3 s + "are you sure" dialog; disabled if node already offline | scoped `script.pve_reboot_<node>` (NOT the audit token — a separate, deliberately-scoped action token) |
| **Start/stop a VM or LXC** | confirm dialog; show current state first | Proxmox API via bridge, dedicated service |
| **Drain a node for maintenance** | confirm + shows pods that will move | `kubectl drain --ignore-daemonsets` in bridge |
| **Power/UPS actions** | confirm | depends on UPS integration |

**Rule:** anything in Phase 3 must be reversible or clearly warned, must log who/
what/when in HA's logbook, and must be togglable off entirely via a single
`enable_dangerous_actions` flag in `secrets.yaml`/bridge env (default **off**).

---

## Phase 4 — Proactive / ambient intelligence (nice-to-have)

| Feature | Idea |
|---------|------|
| **Attention routing** | screen auto-jumps to the node/page that just went critical, with a soft highlight; taps dismiss. |
| **Trend sparklines** | tiny CPU/temp history graphs per node (LVGL chart), so you see "rising" vs "spiked". |
| **Quick filters** | tap "CPU"/"MEM"/"TEMP" header to sort nodes by that metric (worst first). |
| **On-screen keyboard-free search** | tap to cycle a "focus node" for the detail page. |
| **Haptic-ish feedback** | brief colour flash / backlight pulse to confirm a tap registered. |

---

## Suggested build order

```
Phase 1 (nav, brightness)        -> immediately useful, zero backend risk
   └─ Phase 2 (ack, cordon, WoL) -> the daily-driver actions; add confirm UX
        └─ Phase 3 (reboot/VM)   -> only behind guard rails + a kill-switch flag
             └─ Phase 4 (ambient) -> polish once the above is trusted
```

## Implementation checklist (per feature)

- [ ] Wire + verify FT6236 at I²C `0x38` (`i2c: scan: true` in boot log).
- [ ] Calibrate touch `transform` so taps land where you touch.
- [ ] Add the HA service/entity in the bridge **with least privilege**; verify it
      is denied anything beyond its one job.
- [ ] Add the on-screen control (button/tile) that calls `homeassistant.service`.
- [ ] Add confirm UX appropriate to risk (none / 2-tap / hold-to-confirm).
- [ ] Disable/grey the control when the API is down or data is stale.
- [ ] Verify end-to-end with evidence (tap → HA logbook entry → observed effect).
- [ ] Document the new entity in `docs/home-assistant-entities.md`.

> The agent guide ([`AGENT_REPLICATION_GUIDE.md`](AGENT_REPLICATION_GUIDE.md))
> gates still apply: "wired" ≠ "calibrated", and a control isn't "done" until a
> tap produces a verified, logged effect in Home Assistant.
