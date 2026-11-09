# Iteration history

Private Topic Clipper was developed as a sequence of working vertical slices. Each milestone remained deployable before the next capability was added.

| Milestone | User-visible outcome | Engineering focus |
| --- | --- | --- |
| Secure capture API | Text, links, files, and video references enter one inbox | FastAPI validation, Tailscale identity, idempotency, SQLite migrations, content hashing |
| Local extraction worker | Image and PDF capture returns immediately while OCR continues | Asynchronous jobs, MinerU `basic`, safe ZIP extraction, retryable errors |
| Responsive workspace | The same inbox works on iPad, MacBook, and ThinkPad | React, TypeScript, touch targets, mobile and desktop layouts |
| Organization model | Clips can carry tags and appear in multiple ordered topics | FTS5 search, batch actions, many-to-many references, per-topic ordering |
| Safe Obsidian export | Topics become stable Markdown and JSON manifests | Checksums, relative assets, conflict detection, revision restore, atomic writes |
| Reproducible operations | A fresh host can install and run the system consistently | Python `3.12`, locked dependencies, fixed Node container, systemd, health checks |
| Backup lifecycle | SQLite, assets, relations, and export history are recoverable | Consistent snapshots, retention rules, archive validation, pre-restore copy |
| WSL persistence | The self-hosted service survives the end of an SSH session | systemd linger, independent Windows scheduled task, documented rollback |
| Authenticated originals | Existing images and PDFs can be inspected without re-upload | Asset-ID endpoint, path-boundary validation, inline delivery, byte ranges |
| iPad-safe preview | Full-screen originals can be opened and closed inside the installed web app | Portal-based viewer, safe-area layout, explicit return path |
| Focused browsing | Inbox cards show title and personal note rather than full OCR output | Information hierarchy, compact cards, detail-on-demand |
| Explicit lifecycle and video context | Users can permanently delete confirmed selections and see saved video ranges | Referential cleanup, derived-file cleanup, time formatting, regression tests |

## Validation evidence

- `33` backend tests cover capture, identity, idempotency, storage boundaries, extraction, topics, export, restore, and deletion.
- `15` frontend tests cover inbox actions, editing, original previews, multi-asset switching, error recovery, compact topic display, and video times.
- The production interface has been exercised at desktop and iPad viewports through the Tailscale HTTPS endpoint.

The history intentionally keeps operational fixes and UX refinements visible. The repository therefore shows not only the final architecture, but how real device behavior and failure modes changed the design.
