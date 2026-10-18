#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$project_root/backend"

install -d -m 0700 "$project_root/var"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/ and rerun." >&2
  exit 1
fi

cd "$backend_dir"
uv python install 3.12
uv sync --python 3.12 --extra ocr --frozen

python_version="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$python_version" != "3.12" ]]; then
  echo "Expected Python 3.12, found $python_version" >&2
  exit 1
fi

.venv/bin/mineru-kit models download --tier basic
.venv/bin/mineru-kit models verify --tier basic
"$project_root/ops/build-frontend.sh"
