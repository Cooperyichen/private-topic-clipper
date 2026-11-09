from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

PNG = b"\x89PNG\r\n\x1a\n" + b"permanent deletion"


def upload_image(client: TestClient, auth_headers: dict[str, str], key: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/captures/files",
        headers={
            **auth_headers,
            "Idempotency-Key": key,
            "Content-Type": "image/png",
            "Content-Disposition": 'attachment; filename="delete-me.png"',
        },
        content=PNG,
    )
    assert response.status_code == 201
    return response.json()["data"]


def delete_clips(
    client: TestClient,
    auth_headers: dict[str, str],
    clip_ids: list[str],
    *,
    confirm: bool = True,
):
    return client.post(
        "/api/v1/clips/batch-delete",
        headers=auth_headers,
        json={"clipIds": clip_ids, "confirm": confirm},
    )


def test_permanent_delete_cleans_relations_outputs_and_unreferenced_assets(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    first = upload_image(client, auth_headers, "delete-first")
    second = upload_image(client, auth_headers, "delete-second")
    first_id = str(first["id"])
    second_id = str(second["id"])
    database = client.app.state.database
    settings = client.app.state.settings

    tag = client.post("/api/v1/tags", headers=auth_headers, json={"name": "temporary"})
    topic = client.post(
        "/api/v1/topics",
        headers=auth_headers,
        json={"title": "Delete test"},
    )
    assert tag.status_code == 201
    assert topic.status_code == 201
    tag_id = tag.json()["data"]["id"]
    topic_id = topic.json()["data"]["id"]
    assert (
        client.post(
            "/api/v1/clips/batch",
            headers=auth_headers,
            json={"clipIds": [first_id], "addTagIds": [tag_id]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/topics/{topic_id}/clips",
            headers=auth_headers,
            json={"clipId": first_id},
        ).status_code
        == 201
    )

    with database.connect() as connection:
        asset_rows = connection.execute(
            "SELECT clip_id, relative_path FROM assets WHERE clip_id IN (?, ?)",
            (first_id, second_id),
        ).fetchall()
        assert len(asset_rows) == 2
        assert asset_rows[0]["relative_path"] == asset_rows[1]["relative_path"]
        asset_path = settings.assets_dir / asset_rows[0]["relative_path"]
        job_id = connection.execute(
            "SELECT id FROM extraction_jobs WHERE clip_id = ?", (first_id,)
        ).fetchone()["id"]
    output_dir = settings.data_dir / "extractions" / job_id / "attempt-1"
    output_dir.mkdir(parents=True)
    (output_dir / "result.md").write_text("temporary", encoding="utf-8")

    deleted = delete_clips(client, auth_headers, [first_id])

    assert deleted.status_code == 200
    assert deleted.json() == {"data": {"deleted": 1}}
    assert asset_path.is_file()
    assert not (settings.data_dir / "extractions" / job_id).exists()
    with database.connect() as connection:
        assert (
            connection.execute("SELECT 1 FROM clips WHERE id = ?", (first_id,)).fetchone() is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM clip_search WHERE clip_id = ?", (first_id,)
            ).fetchone()
            is None
        )
        assert (
            connection.execute("SELECT 1 FROM clip_tags WHERE clip_id = ?", (first_id,)).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM topic_clips WHERE clip_id = ?", (first_id,)
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM extraction_jobs WHERE clip_id = ?", (first_id,)
            ).fetchone()
            is None
        )
    second_asset_id = second["assets"][0]["id"]
    assert (
        client.get(f"/api/v1/assets/{second_asset_id}/content", headers=auth_headers).status_code
        == 200
    )

    assert delete_clips(client, auth_headers, [second_id]).status_code == 200
    assert not asset_path.exists()


def test_permanent_delete_requires_auth_confirmation_and_existing_clips(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    clip = upload_image(client, auth_headers, "delete-guards")
    clip_id = str(clip["id"])

    assert (
        delete_clips(client, auth_headers, [clip_id], confirm=False).json()["error"]["code"]
        == "DELETE_CONFIRMATION_REQUIRED"
    )
    assert (
        client.post(
            "/api/v1/clips/batch-delete", json={"clipIds": [clip_id], "confirm": True}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/clips/batch-delete",
            headers={"Tailscale-User-Login": "intruder@example.com"},
            json={"clipIds": [clip_id], "confirm": True},
        ).status_code
        == 403
    )
    missing = delete_clips(client, auth_headers, ["missing"])
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CLIP_NOT_FOUND"


def test_permanent_delete_rejects_processing_extraction(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    clip = upload_image(client, auth_headers, "delete-processing")
    clip_id = str(clip["id"])
    database = client.app.state.database
    with database.connect() as connection:
        connection.execute(
            "UPDATE extraction_jobs SET status = 'PROCESSING' WHERE clip_id = ?", (clip_id,)
        )

    response = delete_clips(client, auth_headers, [clip_id])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CLIP_EXTRACTION_IN_PROGRESS"
    assert client.get(f"/api/v1/clips/{clip_id}", headers=auth_headers).status_code == 200


def test_permanent_delete_rejects_asset_path_outside_storage(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path
) -> None:
    clip = upload_image(client, auth_headers, "delete-unsafe-path")
    clip_id = str(clip["id"])
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    database = client.app.state.database
    with database.connect() as connection:
        connection.execute(
            "UPDATE assets SET relative_path = ? WHERE clip_id = ?", (str(outside), clip_id)
        )

    response = delete_clips(client, auth_headers, [clip_id])

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ASSET_PATH"
    assert outside.read_bytes() == PNG
    assert client.get(f"/api/v1/clips/{clip_id}", headers=auth_headers).status_code == 200
