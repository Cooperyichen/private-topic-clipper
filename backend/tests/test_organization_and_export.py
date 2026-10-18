from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def create_text_clip(
    client: TestClient,
    headers: dict[str, str],
    key: str,
    text: str,
    kind: str = "TEXT",
) -> dict:
    response = client.post(
        "/api/v1/captures",
        headers={**headers, "Idempotency-Key": key},
        json={"kind": kind, "rawText": text, "sourceTitle": f"Source for {key}"},
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_updates_editable_representation_without_changing_original(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    clip = create_text_clip(client, auth_headers, "immutable-original", "raw original")

    response = client.patch(
        f"/api/v1/clips/{clip['id']}",
        headers=auth_headers,
        json={"editableText": "corrected text", "note": "A local note"},
    )

    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["rawText"] == "raw original"
    assert updated["editableText"] == "corrected text"
    assert updated["note"] == "A local note"

    rejected = client.patch(
        f"/api/v1/clips/{clip['id']}",
        headers=auth_headers,
        json={"rawText": "replace the original"},
    )
    assert rejected.status_code == 422


def test_tags_and_batch_archive(client: TestClient, auth_headers: dict[str, str]) -> None:
    first = create_text_clip(client, auth_headers, "batch-1", "first")
    second = create_text_clip(client, auth_headers, "batch-2", "second")

    tag_response = client.post("/api/v1/tags", headers=auth_headers, json={"name": "Photonics"})
    assert tag_response.status_code == 201
    tag_id = tag_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/clips/batch",
        headers=auth_headers,
        json={"clipIds": [first["id"], second["id"]], "status": "ARCHIVED", "addTagIds": [tag_id]},
    )

    assert response.status_code == 200
    assert response.json()["data"]["updated"] == 2
    listing = client.get("/api/v1/clips?status=ARCHIVED", headers=auth_headers).json()["data"]
    assert {clip["id"] for clip in listing} == {first["id"], second["id"]}
    assert listing[0]["tags"][0]["name"] == "Photonics"


def test_topic_references_clips_and_preserves_local_order(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    first = create_text_clip(client, auth_headers, "topic-1", "alpha")
    second = create_text_clip(client, auth_headers, "topic-2", "beta")
    topic_response = client.post(
        "/api/v1/topics",
        headers=auth_headers,
        json={"title": "Optical compute", "description": "Working collection"},
    )
    assert topic_response.status_code == 201
    topic_id = topic_response.json()["data"]["id"]

    for clip, annotation in ((first, "context A"), (second, "context B")):
        added = client.post(
            f"/api/v1/topics/{topic_id}/clips",
            headers=auth_headers,
            json={"clipId": clip["id"], "annotation": annotation, "representation": "EDITED"},
        )
        assert added.status_code == 201

    reordered = client.put(
        f"/api/v1/topics/{topic_id}/clips/order",
        headers=auth_headers,
        json={"clipIds": [second["id"], first["id"]]},
    )

    assert reordered.status_code == 200
    topic = client.get(f"/api/v1/topics/{topic_id}", headers=auth_headers).json()["data"]
    assert [item["clip"]["id"] for item in topic["clips"]] == [second["id"], first["id"]]
    assert [item["annotation"] for item in topic["clips"]] == ["context B", "context A"]


def test_export_detects_conflict_and_restores_revision(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    clip = create_text_clip(client, auth_headers, "export-1", "Energy per bit matters", "CODE")
    topic = client.post(
        "/api/v1/topics",
        headers=auth_headers,
        json={"title": "Interconnect Notes", "description": "Evidence"},
    ).json()["data"]
    client.post(
        f"/api/v1/topics/{topic['id']}/clips",
        headers=auth_headers,
        json={
            "clipId": clip["id"],
            "annotation": "Use in section one",
            "representation": "ORIGINAL",
        },
    )

    preview = client.post(f"/api/v1/topics/{topic['id']}/exports/preview", headers=auth_headers)
    assert preview.status_code == 200
    assert preview.json()["data"]["conflict"] is False
    assert "Energy per bit matters" in preview.json()["data"]["markdown"]

    exported = client.post(
        f"/api/v1/topics/{topic['id']}/exports",
        headers=auth_headers,
        json={"confirmOverwrite": False},
    )
    assert exported.status_code == 201
    markdown_path = Path(exported.json()["data"]["markdownPath"])
    manifest_path = Path(exported.json()["data"]["manifestPath"])
    assert markdown_path.exists()
    assert json.loads(manifest_path.read_text())["schemaVersion"] == 1

    markdown_path.write_text("manual Obsidian edit\n", encoding="utf-8")
    conflict = client.post(
        f"/api/v1/topics/{topic['id']}/exports",
        headers=auth_headers,
        json={"confirmOverwrite": False},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "EXPORT_CONFLICT"

    overwritten = client.post(
        f"/api/v1/topics/{topic['id']}/exports",
        headers=auth_headers,
        json={"confirmOverwrite": True},
    )
    assert overwritten.status_code == 201
    revisions = client.get(
        f"/api/v1/topics/{topic['id']}/exports/revisions", headers=auth_headers
    ).json()["data"]
    assert len(revisions) == 2

    markdown_path.write_text("another manual edit\n", encoding="utf-8")
    restored = client.post(
        f"/api/v1/topics/{topic['id']}/exports/revisions/{revisions[-1]['id']}/restore",
        headers=auth_headers,
    )
    assert restored.status_code == 200
    assert "Energy per bit matters" in markdown_path.read_text(encoding="utf-8")
