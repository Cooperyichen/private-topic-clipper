#!/usr/bin/env bash
set -euo pipefail

ops_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$ops_dir/.." && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
install -d -m 0700 "$project_root/var"
mkdir -p "$unit_dir"
install -m 0644 "$ops_dir/systemd/clipper-api.service" "$unit_dir/clipper-api.service"
install -m 0644 "$ops_dir/systemd/clipper-worker.service" "$unit_dir/clipper-worker.service"
install -m 0644 "$ops_dir/systemd/clipper-backup.service" "$unit_dir/clipper-backup.service"
install -m 0644 "$ops_dir/systemd/clipper-backup.timer" "$unit_dir/clipper-backup.timer"
systemctl --user daemon-reload
echo "Units installed but not enabled. Follow README.md after reviewing .env."
