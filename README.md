# Private Topic Clipper

This application captures material from Apple share sheets and browsers into a private, searchable inbox. It stores originals and editable representations separately, performs local MinerU `4.0.9` extraction at the `basic` tier, and exports ordered topics to the Obsidian `Clippings` source area.

## Architecture

The FastAPI service binds only to `127.0.0.1:8766`. Tailscale Serve terminates tailnet HTTPS and injects `Tailscale-User-Login`; the API accepts only the login configured in `.env`. SQLite uses WAL mode and FTS5. Attachments are immutable and addressed by their SHA-256 checksum.

The React interface is served by FastAPI from `frontend/dist`. It is designed for iPad, desktop, and narrow mobile viewports. MinerU work runs in a separate single-process worker, so file capture returns without waiting for extraction.

Archiving only changes a clip's status. Permanent deletion is a separate, confirmed batch action that removes the clip, search index, tag and topic relations, extraction jobs, MinerU output, and any original asset no longer referenced by another clip. It does not rewrite previously exported Obsidian files or historical backup snapshots.

## Install

1. Copy `.env.example` to `.env`, set `CLIPPER_ALLOWED_LOGIN`, and keep the file readable only by the service account.
2. Install `uv` through its official installer and ensure Docker is available.
3. Run `ops/install-runtime.sh`. It creates a Python `3.12` environment, installs the locked application and MinerU dependencies, downloads and verifies the local `basic` model set, and builds React in the fixed Node container. The worker uses the stateless local `mineru-kit` command, removes remote API credentials from its child environment, and never passes a remote parsing option.
4. Run `ops/install-user-services.sh`, inspect the copied units, then enable them with `systemctl --user enable --now clipper-api.service clipper-worker.service clipper-backup.timer`.
5. Confirm `ops/healthcheck.sh` succeeds.
6. Review and run `ops/configure-tailscale-serve.sh`. This publishes the loopback service inside the tailnet without changing ACL policy.
7. Open the HTTPS address reported by `tailscale serve status` on the iPad.

The install scripts do not enable services or change Tailscale configuration automatically.

## Tests

From `backend`, run `.venv/bin/python -m pytest` and `.venv/bin/ruff check app tests`.

From `frontend`, run the following through the fixed Node image:

```sh
docker run --rm --user "$(id -u):$(id -g)" --volume "$PWD:/app" --workdir /app node:22.12.0-bookworm-slim npm test
docker run --rm --user "$(id -u):$(id -g)" --volume "$PWD:/app" --workdir /app node:22.12.0-bookworm-slim npm run build
```

Browser tests use the pinned Playwright image:

```sh
docker run --rm --ipc=host --volume "$PWD:/app" --workdir /app mcr.microsoft.com/playwright:v1.64.1-noble npm run test:e2e
```

## Backup and restore

The timer creates a consistent SQLite backup and copies content-addressed assets into a compressed archive. It keeps the newest `14` daily archives and `8` weekly archives under `var/snapshots`.

Stop the API and worker before a restore. Then run:

```sh
.venv/bin/clipper-backup --restore /absolute/path/to/snapshot.tar.gz --confirm-restore
```

Restore validates archive paths and SQLite integrity, creates a pre-restore safety copy, replaces the database atomically, and merges missing immutable assets. Existing unreferenced assets remain untouched.

## Logs

Services write to the systemd journal, which uses the host journald rotation policy. Inspect recent events with `journalctl --user -u clipper-api.service -u clipper-worker.service`. The units rate-limit repeated messages.

## Apple devices

Follow `shortcuts/README.md` to construct Quick Clip and Detailed Clip. Apple signs exported shortcut files against the owner's account, so the repository keeps reproducible action specifications and does not commit an unsigned shortcut binary.
