#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_dir="$project_root/frontend"
node_image="node:22.12.0-bookworm-slim"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$frontend_dir:/app" \
  --workdir /app \
  "$node_image" \
  npm ci

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$frontend_dir:/app" \
  --workdir /app \
  "$node_image" \
  npm run build
