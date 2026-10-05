#!/usr/bin/env bash
CONTAINER_NAME="btms-monitor"

echo "Stopping Podman container '$CONTAINER_NAME'..."
podman stop "$CONTAINER_NAME" 2>/dev/null || true
podman rm "$CONTAINER_NAME" 2>/dev/null || true
echo "Container '$CONTAINER_NAME' stopped and removed."
