from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.worker import process_next_job


def create_image(client: TestClient, headers: dict[str, str], key: str) -> dict:
    response = client.post(
        "/api/v1/captures/files",
        headers={
            **headers,
            "Idempotency-Key": key,
            "Content-Type": "image/png",
            "Content-Disposition": 'attachment; filename="note.png"',
        },
        content=b"\x89PNG\r\n\x1a\nhandwritten note",
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_worker_runs_mineru_basic_and_persists_outputs(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    clip = create_image(client, auth_headers, "worker-success")
    commands: list[list[str]] = []

    def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        output = Path(command[command.index("-o") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("document.md", "Recognized $E = mc^2$")
            archive.writestr("middle.json", json.dumps({"pages": [{"text": "Recognized"}]}))
            archive.writestr("images/figure.png", b"image")
            archive.writestr("equations/formula.tex", "E = mc^2")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    assert process_next_job(get_settings(), run_command=fake_runner) is True
    assert Path(commands[0][0]).name == "mineru-kit"
    assert commands[0][1] == "parse"
    assert commands[0][-2:] == ["--tier", "basic"]

    updated = client.get(f"/api/v1/clips/{clip['id']}", headers=auth_headers).json()["data"]
    assert updated["extractionStatus"] == "COMPLETED"
    assert updated["ocrMarkdown"] == "Recognized $E = mc^2$"
    assert updated["ocrLatex"] == "E = mc^2"


def test_failed_job_can_be_retried(client: TestClient, auth_headers: dict[str, str]) -> None:
    create_image(client, auth_headers, "worker-failure")

    def failing_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="model unavailable")

    assert process_next_job(get_settings(), run_command=failing_runner) is True
    jobs = client.get("/api/v1/extraction-jobs", headers=auth_headers).json()["data"]
    assert jobs[0]["status"] == "FAILED"
    assert "model unavailable" in jobs[0]["error"]

    retried = client.post(f"/api/v1/extraction-jobs/{jobs[0]['id']}/retry", headers=auth_headers)
    assert retried.status_code == 200
    assert retried.json()["data"]["status"] == "PENDING"


def test_user_can_correct_extraction_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    clip = create_image(client, auth_headers, "manual-correction")
    response = client.patch(
        f"/api/v1/clips/{clip['id']}/extraction",
        headers=auth_headers,
        json={
            "ocrMarkdown": "Corrected markdown",
            "ocrText": "Corrected text",
            "ocrLatex": "\\mathbf{x} = 1",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["ocrLatex"] == "\\mathbf{x} = 1"
