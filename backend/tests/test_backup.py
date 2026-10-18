from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app.backup import create_snapshot, restore_snapshot
from app.config import get_settings
from app.database import Database


def test_snapshot_restores_database_and_assets(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/captures/files",
        headers={
            **auth_headers,
            "Idempotency-Key": "snapshot-asset",
            "Content-Type": "image/png",
            "Content-Disposition": 'attachment; filename="snapshot.png"',
        },
        content=b"\x89PNG\r\n\x1a\nsnapshot image",
    )
    clip = response.json()["data"]
    settings = get_settings()
    snapshot = create_snapshot(settings, dt.date(2026, 10, 18))
    assert snapshot.is_file()

    with Database(settings.database_path).connect() as connection:
        connection.execute("DELETE FROM clips")
    assert client.get("/api/v1/clips", headers=auth_headers).json()["data"] == []

    restore_snapshot(settings, snapshot, confirm=True)
    restored = client.get("/api/v1/clips", headers=auth_headers).json()["data"]
    assert restored[0]["id"] == clip["id"]
    asset = settings.assets_dir / restored[0]["assets"][0]["relativePath"]
    assert asset.is_file()


def test_restore_requires_explicit_confirmation(client: TestClient) -> None:
    settings = get_settings()
    snapshot = create_snapshot(settings, dt.date(2026, 10, 18))
    try:
        restore_snapshot(settings, snapshot)
    except ValueError as error:
        assert "explicit confirmation" in str(error)
    else:
        raise AssertionError("restore should require confirmation")
