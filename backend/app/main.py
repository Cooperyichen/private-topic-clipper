from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from email.message import Message
from typing import Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .database import Database
from .errors import ApiError
from .organization import install_organization_routes
from .records import serialize_clip
from .schemas import CaptureCreate
from .storage import safe_filename, store_asset


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def create_app() -> FastAPI:
    settings = get_settings()
    database = Database(settings.database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.assets_dir.mkdir(parents=True, exist_ok=True)
        database.initialize()
        yield

    app = FastAPI(title="Second Brain Clipper", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database

    install_error_handlers(app)
    install_middleware(app, settings)
    install_routes(app)
    install_organization_routes(app)
    if (settings.frontend_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, error: ApiError) -> JSONResponse:
        body: dict[str, Any] = {"error": {"code": error.code, "message": error.message}}
        if error.details:
            body["error"]["details"] = error.details
        return JSONResponse(status_code=error.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": json.loads(json.dumps(error.errors(), default=str))},
                }
            },
        )


def install_middleware(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'"
        )
        return response

    @app.middleware("http")
    async def tailscale_identity(request: Request, call_next):
        if not request.url.path.startswith("/api/v1") or request.url.path == "/api/v1/health":
            return await call_next(request)
        login = request.headers.get("Tailscale-User-Login", "").strip().casefold()
        if not login:
            return error_response(401, "AUTHENTICATION_REQUIRED", "Tailscale identity is required")
        if not settings.allowed_login or login != settings.allowed_login:
            return error_response(403, "FORBIDDEN", "This Tailscale identity is not authorized")
        return await call_next(request)


def install_routes(app: FastAPI) -> None:
    @app.get("/api/v1/health")
    def health(request: Request) -> dict[str, Any]:
        database: Database = request.app.state.database
        with database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"data": {"status": "ok"}}

    @app.post("/api/v1/captures")
    def create_capture(
        request: Request,
        payload: CaptureCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        key = require_idempotency_key(idempotency_key)
        serializable = payload.model_dump(mode="json", by_alias=True)
        fingerprint = fingerprint_request(serializable)
        database: Database = request.app.state.database

        with database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM clips WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise ApiError(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "The idempotency key was already used for another request",
                    )
                return JSONResponse(
                    status_code=200,
                    content={"data": serialize_clip(connection, existing)},
                )

            clip_id = str(uuid.uuid4())
            timestamp = now_iso()
            raw_text = payload.raw_text
            values = (
                clip_id,
                payload.kind,
                raw_text,
                raw_text,
                payload.note,
                str(payload.source_url) if payload.source_url else None,
                payload.source_title,
                payload.video_start_seconds,
                payload.video_end_seconds,
                key,
                fingerprint,
                timestamp,
                timestamp,
            )
            connection.execute(
                """
                INSERT INTO clips(
                    id, kind, raw_text, editable_text, note, source_url, source_title,
                    video_start_seconds, video_end_seconds, idempotency_key,
                    request_fingerprint, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            connection.execute(
                "INSERT INTO clip_search VALUES (?, ?, ?, ?, ?)",
                (clip_id, raw_text, raw_text, payload.note, payload.source_title),
            )
            row = connection.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            return JSONResponse(status_code=201, content={"data": serialize_clip(connection, row)})

    @app.post("/api/v1/captures/files")
    async def create_file_capture(
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        content_disposition: str | None = Header(default=None, alias="Content-Disposition"),
    ) -> JSONResponse:
        key = require_idempotency_key(idempotency_key)
        settings: Settings = request.app.state.settings
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        data = await read_limited_body(request, settings.max_upload_bytes)
        filename = filename_from_disposition(content_disposition)
        normalized_name = safe_filename(filename, media_type)
        fingerprint = hashlib.sha256(
            b"file\0" + media_type.encode() + b"\0" + normalized_name.encode() + b"\0" + data
        ).hexdigest()
        database: Database = request.app.state.database

        with database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM clips WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise ApiError(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "The idempotency key was already used for another request",
                    )
                return JSONResponse(
                    status_code=200,
                    content={"data": serialize_clip(connection, existing)},
                )

            stored = store_asset(settings.assets_dir, data, normalized_name, media_type)
            clip_id = str(uuid.uuid4())
            asset_id = str(uuid.uuid4())
            job_id = str(uuid.uuid4())
            timestamp = now_iso()
            kind = "PDF" if media_type == "application/pdf" else "IMAGE"
            connection.execute(
                """
                INSERT INTO clips(
                    id, kind, idempotency_key, request_fingerprint, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clip_id, kind, key, fingerprint, timestamp, timestamp),
            )
            connection.execute(
                """
                INSERT INTO assets(
                    id, clip_id, original_name, media_type, byte_size, checksum_sha256,
                    relative_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    clip_id,
                    stored.original_name,
                    stored.media_type,
                    stored.byte_size,
                    stored.checksum_sha256,
                    stored.relative_path,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO extraction_jobs(id, clip_id, asset_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, clip_id, asset_id, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO clip_search VALUES (?, NULL, NULL, NULL, NULL)", (clip_id,)
            )
            row = connection.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            return JSONResponse(status_code=201, content={"data": serialize_clip(connection, row)})

    @app.get("/api/v1/clips")
    def list_clips(
        request: Request,
        q: str | None = Query(default=None, max_length=500),
        status: str | None = Query(default=None, pattern="^(INBOX|ARCHIVED)$"),
        kind: str | None = Query(
            default=None,
            pattern="^(TEXT|RICH_TEXT|CODE|FORMULA|LINK|VIDEO|IMAGE|PDF)$",
        ),
        tag_id: str | None = Query(default=None, alias="tagId", max_length=100),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    ) -> dict[str, Any]:
        database: Database = request.app.state.database
        offset = (page - 1) * page_size
        with database.connect() as connection:
            joins: list[str] = []
            conditions: list[str] = []
            parameters: list[Any] = []
            if q and q.strip():
                query = f'"{q.strip().replace(chr(34), chr(34) * 2)}"*'
                joins.append("JOIN clip_search ON clip_search.clip_id = clips.id")
                conditions.append("clip_search MATCH ?")
                parameters.append(query)
            if tag_id:
                joins.append("JOIN clip_tags ON clip_tags.clip_id = clips.id")
                conditions.append("clip_tags.tag_id = ?")
                parameters.append(tag_id)
            if status:
                conditions.append("clips.status = ?")
                parameters.append(status)
            if kind:
                conditions.append("clips.kind = ?")
                parameters.append(kind)
            from_clause = " FROM clips " + " ".join(joins)
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            count = connection.execute(
                "SELECT COUNT(DISTINCT clips.id)" + from_clause + where_clause,
                parameters,
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT DISTINCT clips.*"
                + from_clause
                + where_clause
                + " ORDER BY clips.created_at DESC LIMIT ? OFFSET ?",
                (*parameters, page_size, offset),
            ).fetchall()
            return {
                "data": [serialize_clip(connection, row) for row in rows],
                "pagination": {
                    "page": page,
                    "pageSize": page_size,
                    "totalItems": count,
                    "totalPages": (count + page_size - 1) // page_size,
                },
            }


def require_idempotency_key(value: str | None) -> str:
    key = (value or "").strip()
    if not key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key is required")
    if len(key) > 200 or not re.fullmatch(r"[A-Za-z0-9._:-]+", key):
        raise ApiError(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key has an invalid format")
    return key


def fingerprint_request(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


async def read_limited_body(request: Request, limit: int) -> bytes:
    announced = request.headers.get("content-length")
    if announced and announced.isdigit() and int(announced) > limit:
        raise ApiError(413, "FILE_TOO_LARGE", "File exceeds the configured upload limit")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise ApiError(413, "FILE_TOO_LARGE", "File exceeds the configured upload limit")
    if not body:
        raise ApiError(400, "EMPTY_FILE", "Uploaded file is empty")
    return bytes(body)


def filename_from_disposition(value: str | None) -> str | None:
    if not value:
        return None
    message = Message()
    message["content-disposition"] = value
    return message.get_filename()


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


app = create_app()
