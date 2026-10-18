from __future__ import annotations

import argparse
import os
import sqlite3
import stat
import subprocess
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

from .config import Settings, get_settings
from .database import Database

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def process_next_job(
    settings: Settings,
    run_command: CommandRunner = subprocess.run,
) -> bool:
    database = Database(settings.database_path)
    database.initialize()
    job = claim_job(database)
    if job is None:
        return False

    job_id = job["id"]
    attempt = job["attempt_count"]
    output_dir = settings.data_dir / "extractions" / job_id / f"attempt-{attempt}"
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = output_dir / "result.zip"
    input_path = safe_asset_path(settings.assets_dir, job["relative_path"])
    command = [
        "mineru-kit",
        "parse",
        str(input_path),
        "-o",
        str(bundle_path),
        "--format",
        "zip",
        "--tier",
        "basic",
    ]
    try:
        completed = run_command(
            command,
            capture_output=True,
            text=True,
            timeout=60 * 60 * 4,
            check=False,
            env=local_mineru_environment(),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "MinerU failed").strip()
            raise RuntimeError(detail)
        actual_bundle = locate_bundle(output_dir, bundle_path)
        extracted_dir = output_dir / "output"
        safe_extract(actual_bundle, extracted_dir)
        markdown_path = first_file(extracted_dir, "*.md")
        json_path = preferred_json(extracted_dir)
        markdown = markdown_path.read_text(encoding="utf-8") if markdown_path else ""
        latex = "\n\n".join(
            path.read_text(encoding="utf-8") for path in sorted(extracted_dir.rglob("*.tex"))
        )
        structured_path = str(json_path.relative_to(settings.data_dir)) if json_path else None
        mark_completed(
            database,
            job_id,
            job["clip_id"],
            markdown,
            latex,
            str(extracted_dir.relative_to(settings.data_dir)),
            structured_path,
        )
    except Exception as error:
        mark_failed(database, job_id, str(error))
    return True


def claim_job(database: Database) -> sqlite3.Row | None:
    connection = sqlite3.connect(database.path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT jobs.*, assets.relative_path
            FROM extraction_jobs AS jobs
            JOIN assets ON assets.id = jobs.asset_id
            WHERE jobs.status = 'PENDING'
            ORDER BY jobs.created_at, jobs.rowid LIMIT 1
            """
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        connection.execute(
            """
            UPDATE extraction_jobs
            SET status = 'PROCESSING', attempt_count = attempt_count + 1,
                error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (row["id"],),
        )
        connection.commit()
        return connection.execute(
            """
            SELECT jobs.*, assets.relative_path
            FROM extraction_jobs AS jobs
            JOIN assets ON assets.id = jobs.asset_id WHERE jobs.id = ?
            """,
            (row["id"],),
        ).fetchone()
    finally:
        connection.close()


def mark_completed(
    database: Database,
    job_id: str,
    clip_id: str,
    markdown: str,
    latex: str,
    output_path: str,
    structured_path: str | None,
) -> None:
    with database.connect() as connection:
        connection.execute(
            """
            UPDATE extraction_jobs
            SET status = 'COMPLETED', output_path = ?, structured_json_path = ?,
                error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (output_path, structured_path, job_id),
        )
        connection.execute(
            """
            UPDATE clips SET ocr_markdown = ?, ocr_text = ?, ocr_latex = ?,
                editable_text = CASE WHEN editable_text IS NULL OR editable_text = '' THEN ?
                                     ELSE editable_text END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (markdown, markdown, latex or None, markdown, clip_id),
        )
        refresh_search_with_ocr(connection, clip_id)


def mark_failed(database: Database, job_id: str, error: str) -> None:
    with database.connect() as connection:
        connection.execute(
            """
            UPDATE extraction_jobs
            SET status = 'FAILED', error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (error[:8_000], job_id),
        )


def refresh_search_with_ocr(connection: sqlite3.Connection, clip_id: str) -> None:
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


def safe_asset_path(root: Path, relative: str) -> Path:
    resolved_root = root.resolve()
    path = (resolved_root / relative).resolve()
    if resolved_root not in path.parents or not path.is_file():
        raise RuntimeError("Asset path is missing or outside the asset directory")
    return path


def locate_bundle(output_dir: Path, expected: Path) -> Path:
    candidates = [expected, expected.with_suffix(expected.suffix + ".zip")]
    candidates.extend(output_dir.glob("*.zip"))
    for candidate in candidates:
        if candidate.is_file() and zipfile.is_zipfile(candidate):
            return candidate
    raise RuntimeError("MinerU did not create a valid ZIP result")


def safe_extract(bundle: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    total_size = 0
    with zipfile.ZipFile(bundle) as archive:
        for member in archive.infolist():
            total_size += member.file_size
            if total_size > 2 * 1024 * 1024 * 1024:
                raise RuntimeError("MinerU output exceeds the extraction limit")
            target = (destination / member.filename).resolve()
            if destination.resolve() not in target.parents:
                raise RuntimeError("MinerU ZIP contains an unsafe path")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise RuntimeError("MinerU ZIP contains a symbolic link")
        archive.extractall(destination)


def first_file(root: Path, pattern: str) -> Path | None:
    return next(iter(sorted(root.rglob(pattern))), None)


def preferred_json(root: Path) -> Path | None:
    candidates = sorted(root.rglob("*.json"))
    for candidate in candidates:
        if "middle" in candidate.name.casefold():
            return candidate
    return candidates[0] if candidates else None


def local_mineru_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("MINERU_API_KEY", None)
    environment.pop("MINERU_REMOTE_URL", None)
    environment["MINERU_TELEMETRY_ENABLED"] = "false"
    return environment


def run_loop(settings: Settings, poll_seconds: float) -> None:
    while True:
        processed = process_next_job(settings)
        if not processed:
            time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process MinerU extraction jobs")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    arguments = parser.parse_args()
    settings = get_settings()
    if arguments.once:
        process_next_job(settings)
    else:
        run_loop(settings, arguments.poll_seconds)


if __name__ == "__main__":
    main()
