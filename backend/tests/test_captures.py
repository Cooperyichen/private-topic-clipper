from __future__ import annotations

from fastapi.testclient import TestClient


def test_rejects_missing_tailscale_identity(client: TestClient) -> None:
    response = client.get("/api/v1/clips")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_rejects_wrong_tailscale_identity(client: TestClient) -> None:
    response = client.get("/api/v1/clips", headers={"Tailscale-User-Login": "intruder@example.com"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_creates_and_lists_text_capture(client: TestClient, auth_headers: dict[str, str]) -> None:
    create = client.post(
        "/api/v1/captures",
        headers={**auth_headers, "Idempotency-Key": "capture-text-1"},
        json={
            "kind": "TEXT",
            "rawText": "A useful passage",
            "note": "Keep this",
            "sourceUrl": "https://example.com/article",
            "sourceTitle": "Example article",
        },
    )

    assert create.status_code == 201
    clip = create.json()["data"]
    assert clip["kind"] == "TEXT"
    assert clip["rawText"] == "A useful passage"
    assert clip["editableText"] == "A useful passage"
    assert clip["status"] == "INBOX"

    listing = client.get("/api/v1/clips?page=1&pageSize=20", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()["pagination"]["totalItems"] == 1
    assert listing.json()["data"][0]["id"] == clip["id"]


def test_capture_creation_is_idempotent(client: TestClient, auth_headers: dict[str, str]) -> None:
    request = {
        "headers": {**auth_headers, "Idempotency-Key": "same-request"},
        "json": {"kind": "LINK", "sourceUrl": "https://example.com"},
    }

    first = client.post("/api/v1/captures", **request)
    second = client.post("/api/v1/captures", **request)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


def test_searches_capture_text(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post(
        "/api/v1/captures",
        headers={**auth_headers, "Idempotency-Key": "searchable"},
        json={"kind": "TEXT", "rawText": "photonic interconnect bottleneck"},
    )

    response = client.get("/api/v1/clips?q=photonic", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["pagination"]["totalItems"] == 1


def test_rejects_capture_without_idempotency_key(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/captures", headers=auth_headers, json={"kind": "TEXT", "rawText": "x"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_uploads_png_and_queues_extraction(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"image payload"
    response = client.post(
        "/api/v1/captures/files",
        headers={
            **auth_headers,
            "Idempotency-Key": "capture-image-1",
            "Content-Type": "image/png",
            "Content-Disposition": 'attachment; filename="../../notes.png"',
        },
        content=png,
    )

    assert response.status_code == 201
    clip = response.json()["data"]
    assert clip["kind"] == "IMAGE"
    assert clip["assets"][0]["originalName"] == "notes.png"
    assert ".." not in clip["assets"][0]["relativePath"]
    assert clip["extractionStatus"] == "PENDING"


def test_rejects_file_when_magic_bytes_do_not_match(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/captures/files",
        headers={
            **auth_headers,
            "Idempotency-Key": "fake-pdf",
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="paper.pdf"',
        },
        content=b"not really a pdf",
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA"


def test_security_headers_are_present(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/health", headers=auth_headers)

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
