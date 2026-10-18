#!/usr/bin/env bash
set -euo pipefail

curl --fail --silent --show-error http://127.0.0.1:8766/api/v1/health >/dev/null
tailscale status >/dev/null
tailscale serve --bg http://127.0.0.1:8766
tailscale serve status
