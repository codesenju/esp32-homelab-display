# KUBELAB metrics bridge — container image.
#
# Runs integrations/proxmox_bridge.py as a long-lived service that publishes
# Proxmox / Kubernetes / temperature metrics into Home Assistant, which the
# ESP32 displays subscribe to. In-cluster it uses its ServiceAccount for the
# Kubernetes collector (kubectl auto-detects in-cluster config) and an SSH key
# (mounted secret) for lm-sensors temperature collection.
#
# Build (linux/amd64 only — the homelab nodes that run this are amd64):
#   docker buildx build --platform linux/amd64 \
#     -t registry.jazziro.com/kubelab/ha-bridge:0.1.0 \
#     -t registry.jazziro.com/kubelab/ha-bridge:latest \
#     -f integrations/Dockerfile integrations --push
#
# The script uses only the Python standard library, so no pip install is needed.
FROM --platform=linux/amd64 python:3.12-slim

# kubectl (k8s collector) + openssh-client (temperature over SSH) + curl (probes/debug)
ARG KUBECTL_VERSION=v1.31.4
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client curl ca-certificates \
    && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY proxmox_bridge.py /app/proxmox_bridge.py

# Non-root. The SSH key secret is mounted read-only; ssh requires strict key
# perms, handled by mounting with defaultMode 0400 in the Deployment.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin bridge
USER 10001

# Point kubectl at in-cluster config by leaving KUBECONFIG unset to a missing
# path; kubectl falls back to the mounted ServiceAccount token automatically.
ENV KUBECONFIG=/nonexistent \
    HTTP_PORT=8080 \
    ONESHOT=0

EXPOSE 8080
ENTRYPOINT ["python3", "/app/proxmox_bridge.py"]
