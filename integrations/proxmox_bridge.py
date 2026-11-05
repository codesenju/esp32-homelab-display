#!/usr/bin/env python3
"""
KUBELAB metrics bridge.

Reads homelab telemetry and publishes it into Home Assistant as sensor
entities, which the ESP32-C6 display then subscribes to over the native
ESPHome <-> Home Assistant API. No credentials ever live on the ESP32.

Sources
-------
- Proxmox VE API (read-only PVEAuditor token) : per-node CPU %, memory %,
  status, uptime for kubelab-1 / kubelab-2 / kubelab-3.
- Kubernetes (kubectl / kubeconfig)           : ready node count, total nodes,
  not-ready pods, overall cluster health.
- UPS                                          : optional; only published if a
  source is configured. Otherwise left absent so the display shows "unknown".

Published Home Assistant entities
---------------------------------
  sensor.kubelab_1_cpu_usage          (%)
  sensor.kubelab_2_cpu_usage          (%)
  sensor.kubelab_3_cpu_usage          (%)
  sensor.kubelab_1_memory_usage       (%)
  sensor.kubelab_2_memory_usage       (%)
  sensor.kubelab_3_memory_usage       (%)
  sensor.kubelab_1_status             (online/offline)
  sensor.kubelab_2_status
  sensor.kubelab_3_status
  sensor.homelab_kubernetes_health    (Healthy/Degraded/Critical/Unknown)
  sensor.homelab_kubernetes_nodes_ready
  sensor.homelab_kubernetes_nodes_total
  sensor.homelab_kubernetes_pods_not_ready
  sensor.homelab_ups_battery_charge   (%, only if UPS source configured)

Configuration is read from environment variables (see integrations/bridge.env.example).
Secrets are never logged.
"""

import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Configuration (from environment / bridge.env)
# --------------------------------------------------------------------------
HA_URL = os.environ.get("HA_URL", "https://ha.example.com").rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

PVE_HOST = os.environ.get("PVE_HOST", "<PVE_NODE_IP>")
PVE_PORT = os.environ.get("PVE_PORT", "8006")
PVE_TOKEN_ID = os.environ.get("PVE_TOKEN_ID", "")       # e.g. monitoring@pve!display
PVE_TOKEN_SECRET = os.environ.get("PVE_TOKEN_SECRET", "")
# Proxmox TLS uses a self-signed cert by default on homelab nodes. We pin the
# node's SHA-256 fingerprint instead of disabling verification entirely.
PVE_FINGERPRINT = os.environ.get("PVE_FINGERPRINT", "").upper().replace(":", "")

# Which Proxmox nodes map to which display rows.
PVE_NODES = os.environ.get("PVE_NODES", "kubelab-1,kubelab-2,kubelab-3").split(",")

# Node temperature (via SSH + lm-sensors). Optional: disable with ENABLE_TEMP=0.
# TEMP_SSH_KEY  : path to the SSH private key.
# TEMP_SSH_USER : SSH user (default root).
# TEMP_NODE_HOSTS : comma list of "name=ip" mapping each PVE_NODES entry to an
#                   SSH host, e.g. "kubelab-1=10.0.0.11,kubelab-2=..."
ENABLE_TEMP = os.environ.get("ENABLE_TEMP", "0") == "1"
TEMP_SSH_KEY = os.path.expanduser(os.environ.get("TEMP_SSH_KEY", ""))
TEMP_SSH_USER = os.environ.get("TEMP_SSH_USER", "root")
TEMP_NODE_HOSTS = os.environ.get("TEMP_NODE_HOSTS", "")

KUBECONFIG = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
KUBECTL = os.environ.get("KUBECTL", "kubectl")
ENABLE_K8S = os.environ.get("ENABLE_K8S", "1") == "1"

# UPS is optional. Leave UPS_SOURCE empty to publish nothing (display -> unknown).
UPS_SOURCE = os.environ.get("UPS_SOURCE", "")  # reserved for future NUT/SNMP wiring

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "15"))
ONESHOT = os.environ.get("ONESHOT", "0") == "1"


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# --------------------------------------------------------------------------
# Proxmox
# --------------------------------------------------------------------------
def _pve_ssl_context():
    """TLS context that pins the Proxmox node fingerprint if provided."""
    ctx = ssl.create_default_context()
    if PVE_FINGERPRINT:
        # We cannot easily hook fingerprint check into urllib; instead we
        # disable hostname/CA checks ONLY when a fingerprint is pinned, then
        # verify the fingerprint manually after the handshake below.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _verify_pve_fingerprint():
    """Open a raw TLS socket and confirm the server cert fingerprint matches."""
    import hashlib
    import socket

    if not PVE_FINGERPRINT:
        return True
    try:
        raw = ssl.create_default_context()
        raw.check_hostname = False
        raw.verify_mode = ssl.CERT_NONE
        with socket.create_connection((PVE_HOST, int(PVE_PORT)), timeout=8) as sock:
            with raw.wrap_socket(sock, server_hostname=PVE_HOST) as ssock:
                der = ssock.getpeercert(binary_form=True)
        got = hashlib.sha256(der).hexdigest().upper()
        if got != PVE_FINGERPRINT:
            log(f"PVE fingerprint mismatch (expected pinned value, got different cert) — refusing")
            return False
        return True
    except Exception as e:
        log(f"PVE fingerprint check failed: {e}")
        return False


def pve_get(path):
    url = f"https://{PVE_HOST}:{PVE_PORT}/api2/json{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"PVEAPIToken={PVE_TOKEN_ID}={PVE_TOKEN_SECRET}")
    with urllib.request.urlopen(req, timeout=10, context=_pve_ssl_context()) as resp:
        return json.loads(resp.read().decode())["data"]


def collect_proxmox():
    """Return {node: {cpu, mem, status, uptime}} for configured nodes."""
    out = {}
    if not (PVE_TOKEN_ID and PVE_TOKEN_SECRET):
        log("Proxmox token not configured — skipping Proxmox metrics")
        return out
    if PVE_FINGERPRINT and not _verify_pve_fingerprint():
        return out
    try:
        nodes = pve_get("/nodes")
    except Exception as e:
        log(f"Proxmox /nodes query failed: {e}")
        return out

    by_name = {n["node"]: n for n in nodes}
    for name in PVE_NODES:
        name = name.strip()
        n = by_name.get(name)
        if not n:
            out[name] = {"status": "offline", "cpu": None, "mem": None, "uptime": None}
            continue
        status = n.get("status", "unknown")
        if status == "online":
            cpu = round(float(n.get("cpu", 0.0)) * 100.0, 1)
            maxmem = float(n.get("maxmem", 0)) or 1.0
            mem = round(float(n.get("mem", 0)) / maxmem * 100.0, 1)
            uptime = int(n.get("uptime", 0))
        else:
            cpu = mem = uptime = None
        out[name] = {"status": status, "cpu": cpu, "mem": mem, "uptime": uptime}
    return out


# --------------------------------------------------------------------------
# Kubernetes
# --------------------------------------------------------------------------
def collect_kubernetes():
    if not ENABLE_K8S:
        return None
    env = dict(os.environ, KUBECONFIG=KUBECONFIG)
    try:
        nodes_raw = subprocess.run(
            [KUBECTL, "get", "nodes", "-o", "json"],
            capture_output=True, text=True, timeout=15, env=env,
        )
        if nodes_raw.returncode != 0:
            log(f"kubectl get nodes failed: {nodes_raw.stderr.strip()[:120]}")
            return None
        nodes = json.loads(nodes_raw.stdout)["items"]
        total = len(nodes)
        ready = 0
        for n in nodes:
            conds = {c["type"]: c["status"] for c in n.get("status", {}).get("conditions", [])}
            if conds.get("Ready") == "True":
                ready += 1

        pods_raw = subprocess.run(
            [KUBECTL, "get", "pods", "-A", "-o", "json"],
            capture_output=True, text=True, timeout=20, env=env,
        )
        not_ready = None
        if pods_raw.returncode == 0:
            pods = json.loads(pods_raw.stdout)["items"]
            not_ready = 0
            for p in pods:
                phase = p.get("status", {}).get("phase", "")
                if phase in ("Succeeded",):
                    continue
                cs = p.get("status", {}).get("containerStatuses", [])
                if phase != "Running" or any(not c.get("ready", False) for c in cs):
                    not_ready += 1

        # Health classification
        if ready == 0:
            health = "Critical"
        elif ready < total:
            health = "Degraded"
        elif not_ready is not None and not_ready > 0:
            health = "Degraded"
        else:
            health = "Healthy"

        return {"ready": ready, "total": total, "not_ready_pods": not_ready, "health": health}
    except Exception as e:
        log(f"Kubernetes collection error: {e}")
        return None


# --------------------------------------------------------------------------
# Node temperature (SSH + lm-sensors)
# --------------------------------------------------------------------------
def _temp_host_map():
    """Return {node_name: ssh_host} from TEMP_NODE_HOSTS 'name=ip,...'."""
    m = {}
    for pair in TEMP_NODE_HOSTS.split(","):
        pair = pair.strip()
        if "=" in pair:
            name, host = pair.split("=", 1)
            m[name.strip()] = host.strip()
    return m


def collect_temps():
    """Return {node: celsius_or_None} using lm-sensors 'coretemp Package id 0'."""
    out = {}
    if not ENABLE_TEMP:
        return out
    if not TEMP_SSH_KEY:
        log("Temperature enabled but TEMP_SSH_KEY not set — skipping temps")
        return out

    hosts = _temp_host_map()
    # Remote one-liner: emit just the CPU package temp as a number.
    remote = (
        "sensors -j 2>/dev/null | python3 -c "
        "'import json,sys;d=json.load(sys.stdin);"
        "c=d.get(\"coretemp-isa-0000\",{});"
        "p=c.get(\"Package id 0\",{});"
        "v=[x for k,x in p.items() if k.endswith(\"_input\")];"
        "print(v[0] if v else \"\")'"
    )
    for name in PVE_NODES:
        name = name.strip()
        host = hosts.get(name)
        if not host:
            out[name] = None
            continue
        try:
            res = subprocess.run(
                ["ssh", "-i", TEMP_SSH_KEY,
                 "-o", "ConnectTimeout=8",
                 "-o", "StrictHostKeyChecking=accept-new",
                 "-o", "BatchMode=yes",
                 f"{TEMP_SSH_USER}@{host}", remote],
                capture_output=True, text=True, timeout=15,
            )
            val = res.stdout.strip()
            out[name] = round(float(val), 1) if val else None
        except Exception as e:
            log(f"temp collect {name} failed: {e}")
            out[name] = None
    return out


# --------------------------------------------------------------------------
# Home Assistant publish
# --------------------------------------------------------------------------
def ha_set_state(entity_id, state, attributes=None):
    url = f"{HA_URL}/api/states/{entity_id}"
    payload = {"state": str(state), "attributes": attributes or {}}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {HA_TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as e:
        log(f"HA set {entity_id} -> HTTP {e.code}")
        return False
    except Exception as e:
        log(f"HA set {entity_id} failed: {e}")
        return False


def publish(proxmox, k8s, temps=None):
    now_iso = datetime.now(timezone.utc).isoformat()
    temps = temps or {}
    node_slug = {"kubelab-1": "kubelab_1", "kubelab-2": "kubelab_2", "kubelab-3": "kubelab_3"}
    ok = 0
    total = 0

    for name, data in proxmox.items():
        slug = node_slug.get(name, name.replace("-", "_"))
        base_attr = {"source": "proxmox", "node": name, "last_updated_bridge": now_iso}

        # CPU
        total += 1
        cpu = data["cpu"]
        ok += ha_set_state(
            f"sensor.{slug}_cpu_usage",
            cpu if cpu is not None else "unavailable",
            {**base_attr, "unit_of_measurement": "%", "friendly_name": f"{name} CPU usage",
             "icon": "mdi:cpu-64-bit"},
        )
        # Memory
        total += 1
        mem = data["mem"]
        ok += ha_set_state(
            f"sensor.{slug}_memory_usage",
            mem if mem is not None else "unavailable",
            {**base_attr, "unit_of_measurement": "%", "friendly_name": f"{name} memory usage",
             "icon": "mdi:memory"},
        )
        # Status
        total += 1
        ok += ha_set_state(
            f"sensor.{slug}_status",
            data["status"],
            {**base_attr, "friendly_name": f"{name} status", "uptime_seconds": data["uptime"]},
        )

        # Temperature (CPU package °C) — only published when temps were collected
        if name in temps:
            total += 1
            t = temps[name]
            ok += ha_set_state(
                f"sensor.{slug}_temperature",
                t if t is not None else "unavailable",
                {**base_attr, "source": "lm-sensors", "unit_of_measurement": "\u00b0C",
                 "device_class": "temperature",
                 "friendly_name": f"{name} temperature", "icon": "mdi:thermometer"},
            )

    if k8s is not None:
        attr = {"source": "kubernetes", "last_updated_bridge": now_iso}
        for ent, val, extra in [
            ("sensor.homelab_kubernetes_health", k8s["health"], {"icon": "mdi:kubernetes"}),
            ("sensor.homelab_kubernetes_nodes_ready", k8s["ready"], {"unit_of_measurement": "nodes"}),
            ("sensor.homelab_kubernetes_nodes_total", k8s["total"], {"unit_of_measurement": "nodes"}),
            ("sensor.homelab_kubernetes_pods_not_ready",
             k8s["not_ready_pods"] if k8s["not_ready_pods"] is not None else "unavailable",
             {"unit_of_measurement": "pods"}),
        ]:
            total += 1
            ok += ha_set_state(ent, val, {**attr, **extra,
                                          "friendly_name": ent.split(".")[1].replace("_", " ").title()})

    log(f"Published {ok}/{total} entities to Home Assistant")
    return ok, total


def main():
    if not HA_TOKEN:
        log("FATAL: HA_TOKEN not set. Source integrations/bridge.env first.")
        sys.exit(1)

    log(f"KUBELAB bridge starting | HA={HA_URL} | nodes={PVE_NODES} | k8s={ENABLE_K8S} "
        f"| temp={ENABLE_TEMP} | interval={POLL_INTERVAL}s | oneshot={ONESHOT}")
    while True:
        proxmox = collect_proxmox()
        k8s = collect_kubernetes()
        temps = collect_temps()
        publish(proxmox, k8s, temps)
        if ONESHOT:
            break
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
