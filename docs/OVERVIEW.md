# KUBELAB Display — What Is This?

A tiny screen that sits on your desk and shows how your home server cluster is
doing, at a glance. No phone, no laptop, no logging in — just look at it.

## What you see

A small 1.47" screen on a Waveshare ESP32-C6 board. It has **three pages**:

1. **CPU page** — how hard each of the three Proxmox servers (kubelab-1/2/3)
   is working right now.
2. **MEMORY page** — how much RAM each server is using.
3. **TEMP page** — how hot each server's CPU is running (in °C).

Each server gets a row with a coloured dot, a value, and a bar:

- 🟢 **green** = healthy
- 🟡 **amber** = getting busy / warm
- 🔴 **red** = under pressure, too hot, or the server is down
- ⚪ **grey** = unknown / no fresh data

(For CPU and memory, amber starts around 60%; for temperature it starts around
70 °C.)

All three pages also show:

- The **Kubernetes** cluster health (e.g. `K8S Degraded 6/6` = all 6 nodes up,
  but something inside the cluster isn't happy).
- The **time** (Johannesburg).
- **WiFi** and **"HA connected"** status, so you know the data is live.

## The buttons

There are two physical buttons on the sides of the board:

- **Left button** → labelled **`< PAGE`** on screen. Press it to move through
  the pages: CPU → MEMORY → TEMP → back to CPU.
- **Right button** → labelled **`RESET >`**. This just restarts the device
  (like unplugging and replugging it). Use it only if the screen ever freezes.

## How it gets the numbers (in plain words)

```
Your servers  ──►  a small helper program  ──►  Home Assistant  ──►  the screen
(Proxmox +         (runs on your Mac,            (your smart-home
 Kubernetes)        reads the servers)            hub)
```

1. A small helper program on the Mac asks Proxmox and Kubernetes "how are you?"
   every 15 seconds, and reads each server's CPU temperature over SSH.
2. It writes those answers into **Home Assistant** (the hub you already run).
3. The screen is connected to Home Assistant and just displays whatever Home
   Assistant knows — over an **encrypted** link.

The screen itself holds **no passwords**. It can't touch your servers directly;
it only ever reads display values from Home Assistant. That's deliberate and
safe.

## What it does NOT show (yet)

- **UPS / battery** — not wired up yet (no UPS connected to the hub). The space
  is reserved for later.

## Everyday use

- **Just leave it on.** It reconnects by itself after WiFi blips or if Home
  Assistant restarts.
- **Press the left button** to cycle CPU → MEMORY → TEMP.
- If every number shows `--` or the dots go grey, the helper program probably
  stopped — see `docs/troubleshooting.md` (or just ask whoever set it up).

## Where things live

- The screen's program: `iy-homelab.yaml`
- The helper program: `integrations/proxmox_bridge.py`
- Deeper docs: `docs/architecture.md` (how), `docs/hardware.md` (the board),
  `docs/troubleshooting.md` (when something's off).
