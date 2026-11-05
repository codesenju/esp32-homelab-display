#!/usr/bin/env python3
"""
Adopt (or verify) the IY HOMELAB ESPHome device in Home Assistant using the
authenticated REST config-flow API and a long-lived token. No browser login
needed, and it will not create a duplicate if the device is already adopted.

Usage:
  export HA_TOKEN="$HA_TOKEN"
  python3 scripts/ha_adopt_esphome.py <host> <port> <noise_psk>
  # e.g.
  python3 scripts/ha_adopt_esphome.py <DEVICE_IP> 6053 "$(grep ^api_encryption_key secrets.yaml | cut -d'"' -f2)"
"""
import json
import os
import sys
import urllib.request

HA_URL = os.environ.get("HA_URL", "https://ha.example.com").rstrip("/")
TOKEN = os.environ.get("HA_TOKEN", "")


def api(method, path, body=None):
    url = f"{HA_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "<DEVICE_IP>"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 6053
    psk = sys.argv[3] if len(sys.argv) > 3 else ""
    if not TOKEN:
        sys.exit("FATAL: HA_TOKEN not set")

    # Already adopted?
    entries = api("GET", "/api/config/config_entries/entry")
    for e in entries:
        if e.get("domain") == "esphome" and (host in json.dumps(e) or
                                             "iy-homelab" in e.get("title", "").lower() or
                                             "iy homelab" in e.get("title", "").lower()):
            print(f"Already adopted: '{e['title']}' state={e['state']} — not duplicating.")
            return

    # Start flow
    flow = api("POST", "/api/config/config_entries/flow",
               {"handler": "esphome", "show_advanced_options": True})
    fid = flow["flow_id"]
    print(f"flow {fid}: step={flow['step_id']}")

    # Submit host/port
    step = api("POST", f"/api/config/config_entries/flow/{fid}",
               {"host": host, "port": port})
    print(f"after host: step={step.get('step_id')} type={step.get('type')}")

    # Supply encryption key if requested
    if step.get("step_id") == "encryption_key":
        if not psk:
            sys.exit("Device needs noise_psk but none supplied.")
        step = api("POST", f"/api/config/config_entries/flow/{fid}", {"noise_psk": psk})

    if step.get("type") == "create_entry":
        print(f"ADOPTED: '{step.get('title')}'")
    else:
        print("Flow did not complete:", json.dumps(step)[:300])


if __name__ == "__main__":
    main()
