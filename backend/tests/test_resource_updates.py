from __future__ import annotations

from fastapi.testclient import TestClient


def test_updates_topic_clip_metadata_and_video_location(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    clip = client.post(
        "/api/v1/captures",
        headers={**auth_headers, "Idempotency-Key": "video-update"},
        json={"kind": "VIDEO", "sourceUrl": "https://example.com/video"},
    ).json()["data"]
    updated_clip = client.patch(
        f"/api/v1/clips/{clip['id']}",
        headers=auth_headers,
        json={"note": "Detailed clip", "videoStartSeconds": 12.5, "videoEndSeconds": 44.0},
    ).json()["data"]
    assert updated_clip["videoStartSeconds"] == 12.5
    invalid_range = client.patch(
        f"/api/v1/clips/{clip['id']}",
        headers=auth_headers,
        json={"videoEndSeconds": 5},
    )
    assert invalid_range.status_code == 422
    unchanged_clip = client.get(f"/api/v1/clips/{clip['id']}", headers=auth_headers).json()["data"]
    assert unchanged_clip["videoEndSeconds"] == 44.0

    topic = client.post(
        "/api/v1/topics", headers=auth_headers, json={"title": "Original title"}
    ).json()["data"]
    client.post(
        f"/api/v1/topics/{topic['id']}/clips",
        headers=auth_headers,
        json={"clipId": clip["id"], "representation": "EDITED"},
    )
    response = client.patch(
        f"/api/v1/topics/{topic['id']}/clips/{clip['id']}",
        headers=auth_headers,
        json={"annotation": "Local context", "representation": "ORIGINAL"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["annotation"] == "Local context"

    renamed = client.patch(
        f"/api/v1/topics/{topic['id']}",
        headers=auth_headers,
        json={"title": "Renamed topic"},
    ).json()["data"]
    assert renamed["title"] == "Renamed topic"
    assert renamed["exportBasename"] == topic["exportBasename"]
    for invalid_title in (None, "   "):
        response = client.patch(
            f"/api/v1/topics/{topic['id']}",
            headers=auth_headers,
            json={"title": invalid_title},
        )
        assert response.status_code == 422


def test_updates_and_deletes_tag(client: TestClient, auth_headers: dict[str, str]) -> None:
    tag = client.post("/api/v1/tags", headers=auth_headers, json={"name": "Draft"}).json()["data"]
    renamed = client.patch(
        f"/api/v1/tags/{tag['id']}", headers=auth_headers, json={"name": "Reviewed"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["data"]["name"] == "Reviewed"
    deleted = client.delete(f"/api/v1/tags/{tag['id']}", headers=auth_headers)
    assert deleted.status_code == 204


def test_filters_clips_by_kind_and_tag(client: TestClient, auth_headers: dict[str, str]) -> None:
    text = client.post(
        "/api/v1/captures",
        headers={**auth_headers, "Idempotency-Key": "filter-text"},
        json={"kind": "TEXT", "rawText": "ordinary note"},
    ).json()["data"]
    code = client.post(
        "/api/v1/captures",
        headers={**auth_headers, "Idempotency-Key": "filter-code"},
        json={"kind": "CODE", "rawText": "print('selected')"},
    ).json()["data"]
    tag = client.post("/api/v1/tags", headers=auth_headers, json={"name": "Implementation"}).json()[
        "data"
    ]
    client.post(
        "/api/v1/clips/batch",
        headers=auth_headers,
        json={"clipIds": [code["id"]], "addTagIds": [tag["id"]]},
    )

    response = client.get(f"/api/v1/clips?kind=CODE&tagId={tag['id']}", headers=auth_headers)
    assert [item["id"] for item in response.json()["data"]] == [code["id"]]
    assert text["id"] != code["id"]
