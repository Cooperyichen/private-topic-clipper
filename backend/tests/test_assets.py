from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

PNG = b"\x89PNG\r\n\x1a\n" + b"preview image"
PDF = b"%PDF-1.7\n" + b"0123456789abcdef" + b"\n%%EOF"


def upload_asset(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    content: bytes,
    media_type: str,
    filename: str,
    key: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/captures/files",
        headers={
            **auth_headers,
            "Idempotency-Key": key,
            "Content-Type": media_type,
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
        content=content,
    )
    assert response.status_code == 201
    return response.json()["data"]["assets"][0]


def test_reads_image_with_inline_filename_and_media_type(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    asset = upload_asset(
        client,
        auth_headers,
        content=PNG,
        media_type="image/png",
        filename="SQL notes.png",
        key="asset-image",
    )

    response = client.get(f"/api/v1/assets/{asset['id']}/content", headers=auth_headers)

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == "inline; filename*=utf-8''SQL%20notes.png"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"


def test_reads_pdf_and_supports_byte_ranges(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    asset = upload_asset(
        client,
        auth_headers,
        content=PDF,
        media_type="application/pdf",
        filename="paper.pdf",
        key="asset-pdf",
    )

    full = client.get(f"/api/v1/assets/{asset['id']}/content", headers=auth_headers)
    ranged = client.get(
        f"/api/v1/assets/{asset['id']}/content",
        headers={**auth_headers, "Range": "bytes=5-11"},
    )

    assert full.status_code == 200
    assert full.content == PDF
    assert full.headers["content-type"] == "application/pdf"
    assert "paper.pdf" in full.headers["content-disposition"]
    assert ranged.status_code == 206
    assert ranged.content == PDF[5:12]
    assert ranged.headers["content-range"] == f"bytes 5-11/{len(PDF)}"
    assert ranged.headers["accept-ranges"] == "bytes"


def test_asset_content_requires_the_configured_tailscale_identity(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    asset = upload_asset(
        client,
        auth_headers,
        content=PNG,
        media_type="image/png",
        filename="private.png",
        key="asset-private",
    )
    path = f"/api/v1/assets/{asset['id']}/content"

    missing = client.get(path)
    wrong = client.get(path, headers={"Tailscale-User-Login": "intruder@example.com"})

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "FORBIDDEN"


def test_returns_json_error_for_unknown_asset(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/assets/does-not-exist/content", headers=auth_headers)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_rejects_asset_path_outside_the_asset_directory(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path
) -> None:
    asset = upload_asset(
        client,
        auth_headers,
        content=PNG,
        media_type="image/png",
        filename="safe.png",
        key="asset-traversal",
    )
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    database = client.app.state.database
    with database.connect() as connection:
        connection.execute(
            "UPDATE assets SET relative_path = ? WHERE id = ?",
            (str(outside), asset["id"]),
        )

    response = client.get(f"/api/v1/assets/{asset['id']}/content", headers=auth_headers)

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "INVALID_ASSET_PATH"


def test_returns_json_error_when_asset_file_is_missing(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    asset = upload_asset(
        client,
        auth_headers,
        content=PNG,
        media_type="image/png",
        filename="missing.png",
        key="asset-missing",
    )
    database = client.app.state.database
    settings = client.app.state.settings
    with database.connect() as connection:
        row = connection.execute(
            "SELECT relative_path FROM assets WHERE id = ?", (asset["id"],)
        ).fetchone()
    (settings.assets_dir / row["relative_path"]).unlink()

    response = client.get(f"/api/v1/assets/{asset['id']}/content", headers=auth_headers)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "ASSET_FILE_MISSING"


def test_sanitizes_historical_filename_before_building_response_header(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    asset = upload_asset(
        client,
        auth_headers,
        content=PNG,
        media_type="image/png",
        filename="safe.png",
        key="asset-header",
    )
    database = client.app.state.database
    with database.connect() as connection:
        connection.execute(
            "UPDATE assets SET original_name = ? WHERE id = ?",
            ('notes.png\r\nX-Injected: yes', asset["id"]),
        )

    response = client.get(f"/api/v1/assets/{asset['id']}/content", headers=auth_headers)

    disposition = response.headers["content-disposition"]
    assert response.status_code == 200
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert "X-Injected:" not in disposition


def test_rejects_unsafe_stored_media_type_before_building_response_header(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    asset = upload_asset(
        client,
        auth_headers,
        content=PNG,
        media_type="image/png",
        filename="safe.png",
        key="asset-media-header",
    )
    database = client.app.state.database
    with database.connect() as connection:
        connection.execute(
            "UPDATE assets SET media_type = ? WHERE id = ?",
            ("image/png\r\nX-Injected: yes", asset["id"]),
        )

    response = client.get(f"/api/v1/assets/{asset['id']}/content", headers=auth_headers)

    assert response.status_code == 415
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA"
