#!/usr/bin/env bash
set -euo pipefail

ops_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$ops_dir/.." && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
env_file="$project_root/.env"

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file. Copy .env.example to .env and configure it first." >&2
  exit 1
fi

vault_dir="$(awk -F= '$1 == "CLIPPER_VAULT_DIR" {sub(/^[^=]*=/, ""); print; exit}' "$env_file")"
if [[ "$vault_dir" != /* ]]; then
  echo "CLIPPER_VAULT_DIR must be an absolute path." >&2
  exit 1
fi

for value in "$project_root" "$vault_dir" "$HOME"; do
  if [[ "$value" == *'|'* || "$value" == *$'\n'* ]]; then
    echo "Install paths cannot contain a pipe or newline." >&2
    exit 1
  fi
done

render_unit() {
  local source="$1"
  local target="$2"
  sed \
    -e "s|@PROJECT_ROOT@|$project_root|g" \
    -e "s|@VAULT_DIR@|$vault_dir|g" \
    -e "s|@USER_HOME@|$HOME|g" \
    "$source" > "$target"
  chmod 0644 "$target"
}

install -d -m 0700 "$project_root/var"
mkdir -p "$unit_dir"
render_unit "$ops_dir/systemd/clipper-api.service" "$unit_dir/clipper-api.service"
render_unit "$ops_dir/systemd/clipper-worker.service" "$unit_dir/clipper-worker.service"
render_unit "$ops_dir/systemd/clipper-backup.service" "$unit_dir/clipper-backup.service"
install -m 0644 "$ops_dir/systemd/clipper-backup.timer" "$unit_dir/clipper-backup.timer"
systemctl --user daemon-reload
echo "Units installed but not enabled. Follow README.md after reviewing .env."
