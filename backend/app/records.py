from __future__ import annotations

import sqlite3
from typing import Any


def serialize_clip(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    assets = connection.execute(
        "SELECT * FROM assets WHERE clip_id = ? ORDER BY created_at", (row["id"],)
    ).fetchall()
    job = connection.execute(
        "SELECT * FROM extraction_jobs WHERE clip_id = ? ORDER BY created_at DESC LIMIT 1",
        (row["id"],),
    ).fetchone()
    tags = connection.execute(
        """
        SELECT tags.id, tags.name FROM tags
        JOIN clip_tags ON clip_tags.tag_id = tags.id
        WHERE clip_tags.clip_id = ? ORDER BY tags.name COLLATE NOCASE
        """,
        (row["id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "rawText": row["raw_text"],
        "editableText": row["editable_text"],
        "note": row["note"],
        "sourceUrl": row["source_url"],
        "sourceTitle": row["source_title"],
        "videoStartSeconds": row["video_start_seconds"],
        "videoEndSeconds": row["video_end_seconds"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "extractionStatus": job["status"] if job else None,
        "minerUVersion": job["mineru_version"] if job else None,
        "ocrMarkdown": None,
        "tags": [{"id": tag["id"], "name": tag["name"]} for tag in tags],
        "assets": [
            {
                "id": asset["id"],
                "originalName": asset["original_name"],
                "mediaType": asset["media_type"],
                "byteSize": asset["byte_size"],
                "checksumSha256": asset["checksum_sha256"],
                "relativePath": asset["relative_path"],
            }
            for asset in assets
        ],
    }
