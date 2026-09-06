"""La capa HTTP, con `analyze` sustituido: aquí no se cargan modelos."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mewsplit import api
from mewsplit.core import Analysis, Chord


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "JOBS_DIR", tmp_path / "jobs")
    api._jobs.clear()
    return TestClient(api.app)


@pytest.fixture
def headers():
    return {"X-Mewsplit-Token": api.TOKEN}


def fake_analyze(audio_path, output_dir, **kwargs) -> Analysis:
    return Analysis(
        source=str(audio_path),
        device="cpu",
        model=kwargs.get("model", "htdemucs.yaml"),
        duration=30.0,
        stems={"vocals": str(audio_path)},
        instrumental=None,
        chords=[Chord(0.0, 30.0, "C")],
        timings={"total": 1.0},
    )


def test_health_needs_no_token(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_rejects_missing_token(client, tone):
    with tone("a.wav").open("rb") as f:
        response = client.post("/jobs", files={"file": ("a.wav", f, "audio/wav")})
    assert response.status_code == 401


def test_rejects_wrong_token(client, tone):
    with tone("a.wav").open("rb") as f:
        response = client.post(
            "/jobs",
            files={"file": ("a.wav", f, "audio/wav")},
            headers={"X-Mewsplit-Token": "wrong"},
        )
    assert response.status_code == 401


def test_rejects_unsupported_format(client, headers, tmp_path: Path):
    junk = tmp_path / "document.pdf"
    junk.write_bytes(b"%PDF")
    with junk.open("rb") as f:
        response = client.post(
            "/jobs", files={"file": ("document.pdf", f, "application/pdf")}, headers=headers
        )
    assert response.status_code == 415


def test_full_job_lifecycle(client, headers, tone, monkeypatch):
    monkeypatch.setattr(api, "analyze", fake_analyze)

    with tone("song.wav").open("rb") as f:
        created = client.post("/jobs", files={"file": ("song.wav", f, "audio/wav")}, headers=headers)

    assert created.status_code == 202
    job_id = created.json()["id"]

    # TestClient corre las BackgroundTasks antes de devolver la respuesta.
    body = client.get(f"/jobs/{job_id}", headers=headers).json()

    assert body["status"] == "done"
    assert body["chords"] == [{"start": 0.0, "end": 30.0, "chord": "C"}]
    # El cliente recibe nombres de stem, nunca rutas del disco del servidor.
    assert body["stems"] == {"vocals": "vocals"}

    audio = client.get(f"/jobs/{job_id}/stems/vocals", headers=headers)
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"

    assert client.delete(f"/jobs/{job_id}", headers=headers).status_code == 204
    assert client.get(f"/jobs/{job_id}", headers=headers).status_code == 404


def test_pipeline_failure_lands_on_the_job(client, headers, tone, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("checkpoint corrupto")

    monkeypatch.setattr(api, "analyze", boom)

    with tone("song.wav").open("rb") as f:
        created = client.post("/jobs", files={"file": ("song.wav", f, "audio/wav")}, headers=headers)

    body = client.get(f"/jobs/{created.json()['id']}", headers=headers).json()
    assert body["status"] == "error"
    assert "checkpoint corrupto" in body["error"]


def test_missing_stem(client, headers, tone, monkeypatch):
    monkeypatch.setattr(api, "analyze", fake_analyze)
    with tone("song.wav").open("rb") as f:
        created = client.post("/jobs", files={"file": ("song.wav", f, "audio/wav")}, headers=headers)
    response = client.get(f"/jobs/{created.json()['id']}/stems/piano", headers=headers)
    assert response.status_code == 404
