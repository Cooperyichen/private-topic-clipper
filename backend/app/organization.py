from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .config import Settings
from .database import Database
from .errors import ApiError
from .exporter import (
    atomic_write,
    checksum_text,
    copy_export_assets,
    file_checksum,
    render_export,
    safe_child,
    slugify,
)
from .records import serialize_clip
from .schemas import (
    BatchUpdate,
    ClipUpdate,
    ExportConfirm,
    ExtractionUpdate,
    TagCreate,
    TagUpdate,
    TopicClipCreate,
    TopicClipUpdate,
    TopicCreate,
    TopicOrderUpdate,
    TopicUpdate,
)


def install_organization_routes(app: FastAPI) -> None:
    @app.get("/api/v1/clips/{clip_id}")
    def get_clip(request: Request, clip_id: str) -> dict[str, Any]:
        database: Database = request.app.state.database
        with database.connect() as connection:
            row = require_row(
                connection,
                "SELECT * FROM clips WHERE id = ?",
                (clip_id,),
                "CLIP_NOT_FOUND",
            )
            return {"data": serialize_clip(connection, row)}

    @app.patch("/api/v1/clips/{clip_id}")
    def update_clip(request: Request, clip_id: str, payload: ClipUpdate) -> dict[str, Any]:
        database: Database = request.app.state.database
        supplied = payload.model_fields_set
        if not supplied:
            raise ApiError(400, "EMPTY_UPDATE", "At least one editable field is required")
        mapping = {
            "editable_text": "editable_text",
            "note": "note",
            "source_url": "source_url",
            "source_title": "source_title",
            "status": "status",
            "video_start_seconds": "video_start_seconds",
            "video_end_seconds": "video_end_seconds",
        }
        assignments: list[str] = []
        values: list[Any] = []
        for field in mapping:
            if field in supplied:
                assignments.append(f"{mapping[field]} = ?")
                value = getattr(payload, field)
                values.append(str(value) if field == "source_url" and value is not None else value)
        timestamp = current_time()
        assignments.append("updated_at = ?")
        values.extend([timestamp, clip_id])
        with database.connect() as connection:
            existing = require_row(
                connection,
                "SELECT * FROM clips WHERE id = ?",
                (clip_id,),
                "CLIP_NOT_FOUND",
            )
            start = (
                payload.video_start_seconds
                if "video_start_seconds" in supplied
                else existing["video_start_seconds"]
            )
            end = (
                payload.video_end_seconds
                if "video_end_seconds" in supplied
                else existing["video_end_seconds"]
            )
            if start is not None and end is not None and end < start:
                raise ApiError(
                    422,
                    "VALIDATION_ERROR",
                    "videoEndSeconds must not precede videoStartSeconds",
                )
            connection.execute(f"UPDATE clips SET {', '.join(assignments)} WHERE id = ?", values)
            refresh_search(connection, clip_id)
            row = connection.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            return {"data": serialize_clip(connection, row)}

    @app.post("/api/v1/tags")
    def create_tag(request: Request, payload: TagCreate) -> JSONResponse:
        name = payload.name.strip()
        if not name:
            raise ApiError(422, "VALIDATION_ERROR", "Tag name cannot be blank")
        database: Database = request.app.state.database
        with database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM tags WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if existing:
                return JSONResponse(status_code=200, content={"data": serialize_tag(existing)})
            tag_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO tags(id, name, created_at) VALUES (?, ?, ?)",
                (tag_id, name, current_time()),
            )
            row = connection.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
            return JSONResponse(status_code=201, content={"data": serialize_tag(row)})

    @app.patch("/api/v1/clips/{clip_id}/extraction")
    def update_extraction(
        request: Request, clip_id: str, payload: ExtractionUpdate
    ) -> dict[str, Any]:
        supplied = payload.model_fields_set
        if not supplied:
            raise ApiError(400, "EMPTY_UPDATE", "At least one extraction field is required")
        mapping = {
            "ocr_markdown": "ocr_markdown",
            "ocr_text": "ocr_text",
            "ocr_latex": "ocr_latex",
        }
        assignments = [f"{mapping[field]} = ?" for field in mapping if field in supplied]
        values = [getattr(payload, field) for field in mapping if field in supplied]
        assignments.append("updated_at = ?")
        values.extend([current_time(), clip_id])
        database: Database = request.app.state.database
        with database.connect() as connection:
            require_row(
                connection,
                "SELECT * FROM clips WHERE id = ?",
                (clip_id,),
                "CLIP_NOT_FOUND",
            )
            connection.execute(f"UPDATE clips SET {', '.join(assignments)} WHERE id = ?", values)
            refresh_search(connection, clip_id)
            row = connection.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            return {"data": serialize_clip(connection, row)}

    @app.get("/api/v1/extraction-jobs")
    def list_extraction_jobs(request: Request) -> dict[str, Any]:
        database: Database = request.app.state.database
        with database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM extraction_jobs ORDER BY created_at DESC, rowid DESC"
            ).fetchall()
            return {"data": [serialize_job(row) for row in rows]}

    @app.post("/api/v1/extraction-jobs/{job_id}/retry")
    def retry_extraction_job(request: Request, job_id: str) -> dict[str, Any]:
        database: Database = request.app.state.database
        with database.connect() as connection:
            row = require_row(
                connection,
                "SELECT * FROM extraction_jobs WHERE id = ?",
                (job_id,),
                "EXTRACTION_JOB_NOT_FOUND",
            )
            if row["status"] not in {"FAILED", "COMPLETED"}:
                raise ApiError(409, "JOB_NOT_RETRYABLE", "Only finished jobs can be retried")
            connection.execute(
                """
                UPDATE extraction_jobs
                SET status = 'PENDING', error = NULL, updated_at = ? WHERE id = ?
                """,
                (current_time(), job_id),
            )
            updated = connection.execute(
                "SELECT * FROM extraction_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return {"data": serialize_job(updated)}

    @app.get("/api/v1/extraction-jobs/{job_id}")
    def get_extraction_job(request: Request, job_id: str) -> dict[str, Any]:
        database: Database = request.app.state.database
        with database.connect() as connection:
            row = require_row(
                connection,
                "SELECT * FROM extraction_jobs WHERE id = ?",
                (job_id,),
                "EXTRACTION_JOB_NOT_FOUND",
            )
            return {"data": serialize_job(row)}

    @app.get("/api/v1/tags")
    def list_tags(request: Request) -> dict[str, Any]:
        database: Database = request.app.state.database
        with database.connect() as connection:
            rows = connection.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()
            return {"data": [serialize_tag(row) for row in rows]}

    @app.patch("/api/v1/tags/{tag_id}")
    def update_tag(request: Request, tag_id: str, payload: TagUpdate) -> dict[str, Any]:
        name = payload.name.strip()
        if not name:
            raise ApiError(422, "VALIDATION_ERROR", "Tag name cannot be blank")
        database: Database = request.app.state.database
        with database.connect() as connection:
            require_row(connection, "SELECT * FROM tags WHERE id = ?", (tag_id,), "TAG_NOT_FOUND")
            try:
                connection.execute("UPDATE tags SET name = ? WHERE id = ?", (name, tag_id))
            except sqlite3.IntegrityError as error:
                raise ApiError(
                    409, "TAG_NAME_EXISTS", "A tag with this name already exists"
                ) from error
            row = connection.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
            return {"data": serialize_tag(row)}

    @app.delete("/api/v1/tags/{tag_id}", status_code=204)
    def delete_tag(request: Request, tag_id: str) -> Response:
        database: Database = request.app.state.database
        with database.connect() as connection:
            require_row(connection, "SELECT * FROM tags WHERE id = ?", (tag_id,), "TAG_NOT_FOUND")
            connection.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        return Response(status_code=204)

    @app.post("/api/v1/clips/batch")
    def batch_update(request: Request, payload: BatchUpdate) -> dict[str, Any]:
        database: Database = request.app.state.database
        clip_ids = list(dict.fromkeys(payload.clip_ids))
        tag_ids = list(dict.fromkeys(payload.add_tag_ids))
        with database.connect() as connection:
            ensure_ids_exist(connection, "clips", clip_ids, "CLIP_NOT_FOUND")
            ensure_ids_exist(connection, "tags", tag_ids, "TAG_NOT_FOUND")
            if payload.status:
                placeholders = ",".join("?" for _ in clip_ids)
                connection.execute(
                    f"UPDATE clips SET status = ?, updated_at = ? WHERE id IN ({placeholders})",
                    (payload.status, current_time(), *clip_ids),
                )
            for clip_id in clip_ids:
                for tag_id in tag_ids:
                    connection.execute(
                        "INSERT OR IGNORE INTO clip_tags(clip_id, tag_id) VALUES (?, ?)",
                        (clip_id, tag_id),
                    )
            return {"data": {"updated": len(clip_ids)}}

    @app.post("/api/v1/topics")
    def create_topic(request: Request, payload: TopicCreate) -> JSONResponse:
        topic_id = str(uuid.uuid4())
        title = payload.title.strip()
        timestamp = current_time()
        database: Database = request.app.state.database
        basename = f"{slugify(title)}-{topic_id[:8]}"
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO topics(id, title, description, export_basename, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (topic_id, title, payload.description, basename, timestamp, timestamp),
            )
            row = connection.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            return JSONResponse(status_code=201, content={"data": serialize_topic(connection, row)})

    @app.get("/api/v1/topics")
    def list_topics(request: Request) -> dict[str, Any]:
        database: Database = request.app.state.database
        with database.connect() as connection:
            rows = connection.execute("SELECT * FROM topics ORDER BY updated_at DESC").fetchall()
            return {"data": [serialize_topic(connection, row, include_clips=False) for row in rows]}

    @app.get("/api/v1/topics/{topic_id}")
    def get_topic(request: Request, topic_id: str) -> dict[str, Any]:
        database: Database = request.app.state.database
        with database.connect() as connection:
            row = require_topic(connection, topic_id)
            return {"data": serialize_topic(connection, row)}

    @app.patch("/api/v1/topics/{topic_id}")
    def update_topic(request: Request, topic_id: str, payload: TopicUpdate) -> dict[str, Any]:
        supplied = payload.model_fields_set
        if not supplied:
            raise ApiError(400, "EMPTY_UPDATE", "At least one topic field is required")
        if "title" in supplied and (payload.title is None or not payload.title.strip()):
            raise ApiError(422, "VALIDATION_ERROR", "Topic title cannot be blank")
        assignments: list[str] = []
        values: list[Any] = []
        if "title" in supplied:
            assignments.append("title = ?")
            values.append(payload.title.strip())
        if "description" in supplied:
            assignments.append("description = ?")
            values.append(payload.description)
        assignments.append("updated_at = ?")
        values.extend([current_time(), topic_id])
        database: Database = request.app.state.database
        with database.connect() as connection:
            require_topic(connection, topic_id)
            connection.execute(f"UPDATE topics SET {', '.join(assignments)} WHERE id = ?", values)
            row = connection.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            return {"data": serialize_topic(connection, row)}

    @app.post("/api/v1/topics/{topic_id}/clips")
    def add_topic_clip(request: Request, topic_id: str, payload: TopicClipCreate) -> JSONResponse:
        database: Database = request.app.state.database
        with database.connect() as connection:
            require_topic(connection, topic_id)
            require_row(
                connection,
                "SELECT id FROM clips WHERE id = ?",
                (payload.clip_id,),
                "CLIP_NOT_FOUND",
            )
            position = connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM topic_clips WHERE topic_id = ?",
                (topic_id,),
            ).fetchone()[0]
            try:
                connection.execute(
                    """
                    INSERT INTO topic_clips(topic_id, clip_id, position, annotation, representation)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        topic_id,
                        payload.clip_id,
                        position,
                        payload.annotation,
                        payload.representation,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ApiError(409, "TOPIC_CLIP_EXISTS", "Clip is already in this topic") from error
            connection.execute(
                "UPDATE topics SET updated_at = ? WHERE id = ?", (current_time(), topic_id)
            )
            row = connection.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            return JSONResponse(status_code=201, content={"data": serialize_topic(connection, row)})

    @app.put("/api/v1/topics/{topic_id}/clips/order")
    def reorder_topic(request: Request, topic_id: str, payload: TopicOrderUpdate) -> dict[str, Any]:
        database: Database = request.app.state.database
        requested = payload.clip_ids
        if len(requested) != len(set(requested)):
            raise ApiError(422, "DUPLICATE_CLIP", "Topic order contains a duplicate clip")
        with database.connect() as connection:
            require_topic(connection, topic_id)
            current = [
                row["clip_id"]
                for row in connection.execute(
                    "SELECT clip_id FROM topic_clips WHERE topic_id = ? ORDER BY position",
                    (topic_id,),
                ).fetchall()
            ]
            if set(current) != set(requested):
                raise ApiError(
                    422,
                    "ORDER_MISMATCH",
                    "Topic order must contain every referenced clip exactly once",
                )
            connection.execute(
                "UPDATE topic_clips SET position = position + 1000000 WHERE topic_id = ?",
                (topic_id,),
            )
            for position, clip_id in enumerate(requested):
                connection.execute(
                    "UPDATE topic_clips SET position = ? WHERE topic_id = ? AND clip_id = ?",
                    (position, topic_id, clip_id),
                )
            connection.execute(
                "UPDATE topics SET updated_at = ? WHERE id = ?", (current_time(), topic_id)
            )
            row = connection.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            return {"data": serialize_topic(connection, row)}

    @app.patch("/api/v1/topics/{topic_id}/clips/{clip_id}")
    def update_topic_clip(
        request: Request,
        topic_id: str,
        clip_id: str,
        payload: TopicClipUpdate,
    ) -> dict[str, Any]:
        supplied = payload.model_fields_set
        if not supplied:
            raise ApiError(400, "EMPTY_UPDATE", "At least one topic clip field is required")
        assignments: list[str] = []
        values: list[Any] = []
        for field in ("annotation", "representation"):
            if field in supplied:
                assignments.append(f"{field} = ?")
                values.append(getattr(payload, field))
        values.extend([topic_id, clip_id])
        database: Database = request.app.state.database
        with database.connect() as connection:
            require_row(
                connection,
                "SELECT * FROM topic_clips WHERE topic_id = ? AND clip_id = ?",
                (topic_id, clip_id),
                "TOPIC_CLIP_NOT_FOUND",
            )
            connection.execute(
                f"UPDATE topic_clips SET {', '.join(assignments)} "
                "WHERE topic_id = ? AND clip_id = ?",
                values,
            )
            connection.execute(
                "UPDATE topics SET updated_at = ? WHERE id = ?", (current_time(), topic_id)
            )
            row = connection.execute(
                "SELECT * FROM topic_clips WHERE topic_id = ? AND clip_id = ?",
                (topic_id, clip_id),
            ).fetchone()
            return {
                "data": {
                    "position": row["position"],
                    "annotation": row["annotation"],
                    "representation": row["representation"],
                    "clip": serialize_clip(
                        connection,
                        connection.execute(
                            "SELECT * FROM clips WHERE id = ?", (clip_id,)
                        ).fetchone(),
                    ),
                }
            }

    @app.delete("/api/v1/topics/{topic_id}/clips/{clip_id}", status_code=204)
    def delete_topic_clip(request: Request, topic_id: str, clip_id: str) -> Response:
        database: Database = request.app.state.database
        with database.connect() as connection:
            require_row(
                connection,
                "SELECT * FROM topic_clips WHERE topic_id = ? AND clip_id = ?",
                (topic_id, clip_id),
                "TOPIC_CLIP_NOT_FOUND",
            )
            connection.execute(
                "DELETE FROM topic_clips WHERE topic_id = ? AND clip_id = ?",
                (topic_id, clip_id),
            )
            remaining = connection.execute(
                "SELECT clip_id FROM topic_clips WHERE topic_id = ? ORDER BY position",
                (topic_id,),
            ).fetchall()
            for position, row in enumerate(remaining):
                connection.execute(
                    "UPDATE topic_clips SET position = ? WHERE topic_id = ? AND clip_id = ?",
                    (position, topic_id, row["clip_id"]),
                )
            connection.execute(
                "UPDATE topics SET updated_at = ? WHERE id = ?", (current_time(), topic_id)
            )
        return Response(status_code=204)

    @app.post("/api/v1/topics/{topic_id}/exports/preview")
    def preview_export(request: Request, topic_id: str) -> dict[str, Any]:
        database: Database = request.app.state.database
        settings: Settings = request.app.state.settings
        with database.connect() as connection:
            topic, items = export_inputs(connection, topic_id)
            rendered = render_export(settings.vault_dir, topic, items, current_time())
            return {
                "data": {
                    "conflict": export_conflict(connection, topic_id, rendered.markdown_path),
                    "markdown": rendered.markdown,
                    "manifest": json.loads(rendered.manifest),
                    "markdownPath": str(rendered.markdown_path),
                    "manifestPath": str(rendered.manifest_path),
                }
            }

    @app.post("/api/v1/topics/{topic_id}/exports")
    def export_topic(request: Request, topic_id: str, payload: ExportConfirm) -> JSONResponse:
        database: Database = request.app.state.database
        settings: Settings = request.app.state.settings
        with database.connect() as connection:
            topic, items = export_inputs(connection, topic_id)
            timestamp = current_time()
            rendered = render_export(settings.vault_dir, topic, items, timestamp)
            conflict = export_conflict(connection, topic_id, rendered.markdown_path)
            if conflict and not payload.confirm_overwrite:
                raise ApiError(
                    409,
                    "EXPORT_CONFLICT",
                    "The Obsidian file changed since the previous export",
                )
            copy_export_assets(settings.assets_dir, settings.vault_dir, items)
            atomic_write(rendered.manifest_path, rendered.manifest)
            atomic_write(rendered.markdown_path, rendered.markdown)
            revision_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO export_revisions(
                    id, topic_id, markdown_path, manifest_path, markdown_content,
                    manifest_content, output_checksum, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    topic_id,
                    str(rendered.markdown_path),
                    str(rendered.manifest_path),
                    rendered.markdown,
                    rendered.manifest,
                    checksum_text(rendered.markdown),
                    timestamp,
                ),
            )
            return JSONResponse(
                status_code=201,
                content={
                    "data": {
                        "revisionId": revision_id,
                        "markdownPath": str(rendered.markdown_path),
                        "manifestPath": str(rendered.manifest_path),
                        "conflictOverwritten": conflict,
                    }
                },
            )

    @app.get("/api/v1/topics/{topic_id}/exports/revisions")
    def list_export_revisions(request: Request, topic_id: str) -> dict[str, Any]:
        database: Database = request.app.state.database
        with database.connect() as connection:
            require_topic(connection, topic_id)
            rows = connection.execute(
                """
                SELECT id, output_checksum, created_at FROM export_revisions
                WHERE topic_id = ? ORDER BY created_at DESC, rowid DESC
                """,
                (topic_id,),
            ).fetchall()
            return {
                "data": [
                    {
                        "id": row["id"],
                        "outputChecksum": row["output_checksum"],
                        "createdAt": row["created_at"],
                    }
                    for row in rows
                ]
            }

    @app.post("/api/v1/topics/{topic_id}/exports/revisions/{revision_id}/restore")
    def restore_export_revision(
        request: Request, topic_id: str, revision_id: str
    ) -> dict[str, Any]:
        database: Database = request.app.state.database
        settings: Settings = request.app.state.settings
        with database.connect() as connection:
            require_topic(connection, topic_id)
            revision = require_row(
                connection,
                "SELECT * FROM export_revisions WHERE id = ? AND topic_id = ?",
                (revision_id, topic_id),
                "REVISION_NOT_FOUND",
            )
            root = (settings.vault_dir / "Clippings").resolve()
            markdown_path = safe_child(root, relative_to_root(revision["markdown_path"], root))
            manifest_path = safe_child(root, relative_to_root(revision["manifest_path"], root))
            atomic_write(manifest_path, revision["manifest_content"])
            atomic_write(markdown_path, revision["markdown_content"])
            return {
                "data": {
                    "revisionId": revision_id,
                    "markdownPath": str(markdown_path),
                    "manifestPath": str(manifest_path),
                }
            }


def serialize_tag(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "name": row["name"]}


def serialize_job(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "clipId": row["clip_id"],
        "assetId": row["asset_id"],
        "status": row["status"],
        "minerUVersion": row["mineru_version"],
        "tier": row["tier"],
        "attemptCount": row["attempt_count"],
        "error": row["error"],
        "outputPath": row["output_path"],
        "structuredJsonPath": row["structured_json_path"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def serialize_topic(
    connection: sqlite3.Connection, row: sqlite3.Row, include_clips: bool = True
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "exportBasename": row["export_basename"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if include_clips:
        result["clips"] = topic_items(connection, row["id"])
    else:
        result["clipCount"] = connection.execute(
            "SELECT COUNT(*) FROM topic_clips WHERE topic_id = ?", (row["id"],)
        ).fetchone()[0]
    return result


def topic_items(connection: sqlite3.Connection, topic_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM topic_clips WHERE topic_id = ? ORDER BY position", (topic_id,)
    ).fetchall()
    items = []
    for row in rows:
        clip = connection.execute("SELECT * FROM clips WHERE id = ?", (row["clip_id"],)).fetchone()
        items.append(
            {
                "position": row["position"],
                "annotation": row["annotation"],
                "representation": row["representation"],
                "clip": serialize_clip(connection, clip),
            }
        )
    return items


def export_inputs(
    connection: sqlite3.Connection, topic_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row = require_topic(connection, topic_id)
    topic = dict(row)
    return topic, topic_items(connection, topic_id)


def export_conflict(connection: sqlite3.Connection, topic_id: str, markdown_path) -> bool:
    if not markdown_path.exists():
        return False
    latest = connection.execute(
        """
        SELECT output_checksum FROM export_revisions
        WHERE topic_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1
        """,
        (topic_id,),
    ).fetchone()
    return latest is None or file_checksum(markdown_path) != latest["output_checksum"]


def refresh_search(connection: sqlite3.Connection, clip_id: str) -> None:
    row = connection.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    connection.execute("DELETE FROM clip_search WHERE clip_id = ?", (clip_id,))
    connection.execute(
        "INSERT INTO clip_search VALUES (?, ?, ?, ?, ?)",
        (
            clip_id,
            row["ocr_text"] or row["raw_text"],
            row["editable_text"],
            row["note"],
            row["source_title"],
        ),
    )


def ensure_ids_exist(
    connection: sqlite3.Connection, table: str, values: list[str], error_code: str
) -> None:
    if not values:
        return
    if table not in {"clips", "tags"}:
        raise ValueError("Unsupported table")
    placeholders = ",".join("?" for _ in values)
    count = connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE id IN ({placeholders})", values
    ).fetchone()[0]
    if count != len(values):
        raise ApiError(404, error_code, "One or more referenced records do not exist")


def require_topic(connection: sqlite3.Connection, topic_id: str) -> sqlite3.Row:
    return require_row(
        connection, "SELECT * FROM topics WHERE id = ?", (topic_id,), "TOPIC_NOT_FOUND"
    )


def require_row(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[Any, ...],
    error_code: str,
) -> sqlite3.Row:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise ApiError(404, error_code, "Requested record was not found")
    return row


def relative_to_root(value: str, root) -> str:
    from pathlib import Path

    path = Path(value).resolve()
    try:
        return str(path.relative_to(root))
    except ValueError as error:
        raise ApiError(400, "UNSAFE_PATH", "Stored export path is outside Clippings") from error


def current_time() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds")
