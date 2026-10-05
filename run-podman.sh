#!/usr/bin/env bash
set -e

CONTAINER_NAME="btms-monitor"
IMAGE_NAME="btms-dashboard:latest"
PORT="8000"

echo "=========================================================="
echo "  Microchannel BTMS - Podman Container Deployment"
echo "=========================================================="

# Check if podman is available
if ! command -v podman &> /dev/null; then
    echo "Error: podman command not found in PATH."
    exit 1
fi

echo "[1/4] Stopping and removing any existing container '$CONTAINER_NAME'..."
podman stop "$CONTAINER_NAME" 2>/dev/null || true
podman rm "$CONTAINER_NAME" 2>/dev/null || true

echo "[2/4] Building Podman image '$IMAGE_NAME' from Containerfile..."
podman build -t "$IMAGE_NAME" -f Containerfile .

echo "[3/4] Running container '$CONTAINER_NAME' on port $PORT..."
podman run -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT:8000" \
  --restart unless-stopped \
  "$IMAGE_NAME"

echo "[4/4] Verifying container health..."
for i in {1..20}; do
  if curl -sf "http://127.0.0.1:$PORT/api/health" > /dev/null 2>&1; then
    echo "Container is UP and HEALTHY!"
    echo "----------------------------------------------------------"
    echo "Dashboard URL: http://localhost:$PORT"
    echo "REST API Docs: http://localhost:$PORT/docs"
    echo "Health Probe:  http://localhost:$PORT/api/health"
    echo "----------------------------------------------------------"
    echo "View logs with: podman logs -f $CONTAINER_NAME"
    echo "Stop with:      ./stop-podman.sh"
    exit 0
  fi
  sleep 1
done

echo "Warning: Healthcheck timed out. Checking container logs:"
podman logs "$CONTAINER_NAME"
exit 1
