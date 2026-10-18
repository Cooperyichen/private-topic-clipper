#!/usr/bin/env bash
set -euo pipefail

curl --fail --silent --show-error \
  --max-time 5 \
  http://127.0.0.1:8766/api/v1/health
