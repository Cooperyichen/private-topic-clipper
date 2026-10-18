from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"
    monkeypatch.setenv("CLIPPER_ENV", "test")
    monkeypatch.setenv("CLIPPER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("CLIPPER_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("CLIPPER_ALLOWED_LOGIN", "owner@example.com")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Tailscale-User-Login": "owner@example.com"}
