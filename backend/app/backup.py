from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path

from .config import Settings, get_settings
from .database import Database


def create_snapshot(settings: Settings, today: dt.date | None = None) -> Path:
    today = today or dt.date.today()
    database = Database(settings.database_path)
    database.initialize()
    snapshot_root = settings.data_dir / "snapshots"
    daily_dir = snapshot_root / "daily"
    weekly_dir = snapshot_root / "weekly"
    daily_dir.mkdir(parents=True, exist_ok=True)
    weekly_dir.mkdir(parents=True, exist_ok=True)
    target = daily_dir / f"{today.isoformat()}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="clipper-snapshot-", dir=snapshot_root) as temp_name:
        staging = Path(temp_name)
        snapshot_database(database.path, staging / "clipper.sqlite3")
        if settings.assets_dir.exists():
            shutil.copytree(settings.assets_dir, staging / "assets")
        temporary_archive = staging / "snapshot.tar.gz"
        with tarfile.open(temporary_archive, "w:gz") as archive:
            archive.add(staging / "clipper.sqlite3", arcname="clipper.sqlite3")
            if (staging / "assets").exists():
                archive.add(staging / "assets", arcname="assets")
        atomic_copy(temporary_archive, target)

    iso_year, iso_week, _ = today.isocalendar()
    weekly_target = weekly_dir / f"{iso_year}-W{iso_week:02d}.tar.gz"
    if not weekly_target.exists():
        atomic_copy(target, weekly_target)
    prune_archives(daily_dir, keep=14)
    prune_archives(weekly_dir, keep=8)
    return target


def restore_snapshot(settings: Settings, archive_path: Path, confirm: bool = False) -> Path:
    if not confirm:
        raise ValueError("Snapshot restore requires explicit confirmation")
    archive_path = archive_path.resolve()
    if not archive_path.is_file() or not tarfile.is_tarfile(archive_path):
        raise ValueError("Restore source is not a valid snapshot archive")

    restore_root = settings.data_dir / "restore-staging"
    restore_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="restore-", dir=restore_root) as temp_name:
        staging = Path(temp_name)
        safe_extract(archive_path, staging)
        database_file = staging / "clipper.sqlite3"
        validate_database(database_file)
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        if settings.database_path.exists():
            safety_copy = settings.data_dir / (
                "clipper.sqlite3.pre-restore-" + dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
            )
            snapshot_database(settings.database_path, safety_copy)
        temporary_database = settings.database_path.with_suffix(".restore.tmp")
        shutil.copy2(database_file, temporary_database)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(settings.database_path) + suffix)
            sidecar.unlink(missing_ok=True)
        os.replace(temporary_database, settings.database_path)
        restored_assets = staging / "assets"
        if restored_assets.exists():
            settings.assets_dir.mkdir(parents=True, exist_ok=True)
            merge_assets(restored_assets, settings.assets_dir)
    return settings.database_path


def snapshot_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as target:
        source_connection.backup(target)
        target.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def validate_database(path: Path) -> None:
    if not path.is_file():
        raise ValueError("Snapshot does not contain clipper.sqlite3")
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as error:
        raise ValueError("Snapshot database cannot be opened") from error
    if result is None or result[0] != "ok":
        raise ValueError("Snapshot database failed SQLite integrity checks")


def safe_extract(archive_path: Path, destination: Path) -> None:
    destination_root = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination_root / member.name).resolve()
            if target != destination_root and destination_root not in target.parents:
                raise ValueError("Snapshot contains an unsafe path")
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError("Snapshot contains an unsupported special file")
        archive.extractall(destination, filter="data")


def merge_assets(source: Path, destination: Path) -> None:
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source_file, target)


def atomic_copy(source: Path, target: Path) -> None:
    temporary = target.with_suffix(target.suffix + ".tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def prune_archives(directory: Path, keep: int) -> None:
    archives = sorted(directory.glob("*.tar.gz"), reverse=True)
    for archive in archives[keep:]:
        archive.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or restore Clipper snapshots")
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--confirm-restore", action="store_true")
    arguments = parser.parse_args()
    settings = get_settings()
    if arguments.restore:
        restored = restore_snapshot(settings, arguments.restore, arguments.confirm_restore)
        print(f"Restored {restored}")
    else:
        snapshot = create_snapshot(settings)
        print(snapshot)


if __name__ == "__main__":
    main()
