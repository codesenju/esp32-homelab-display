#!/bin/zsh
# Wrapper that loads secrets then runs the KUBELAB metrics bridge.
# Used by launchd (com.iyhomelab.bridge.plist) or by hand.
set -e
HERE="${0:A:h}"
REPO="${HERE:h}"

# Secrets: HA token comes from ~/.zsh_profile (HA_TOKEN); Proxmox token
# and other config from integrations/bridge.env (gitignored).
[ -f "$HOME/.zsh_profile" ] && source "$HOME/.zsh_profile"
[ -f "$HERE/bridge.env" ] && source "$HERE/bridge.env"

exec python3 "$HERE/proxmox_bridge.py"
