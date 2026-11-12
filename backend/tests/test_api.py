"""La capa HTTP, con `analyze` sustituido: aquí no se cargan modelos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from mewsplit import api, projects, youtube
from mewsplit.core import Analysis, Chord


def restart_server() -> None:
    """Lo que ve la API tras cerrar y abrir la app: solo lo que quedó en disco."""
    api._jobs.clear()
    api._loaded = False


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    restart_server()
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
        tuning_cents=43.0,
        timings={"total": 1.0},
    )


def test_health_needs_no_token(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_rejects_missing_token(client, tone):
    with tone("a.wav").open("rb") as f:
        response = client.post("/projects", files={"file": ("a.wav", f, "audio/wav")})
    assert response.status_code == 401


def test_rejects_wrong_token(client, tone):
    with tone("a.wav").open("rb") as f:
        response = client.post(
            "/projects",
            files={"file": ("a.wav", f, "audio/wav")},
            headers={"X-Mewsplit-Token": "wrong"},
        )
    assert response.status_code == 401


def test_rejects_unsupported_format(client, headers, tmp_path: Path):
    junk = tmp_path / "document.pdf"
    junk.write_bytes(b"%PDF")
    with junk.open("rb") as f:
        response = client.post(
            "/projects", files={"file": ("document.pdf", f, "application/pdf")}, headers=headers
        )
    assert response.status_code == 415


def test_full_project_lifecycle(client, headers, tone, monkeypatch):
    monkeypatch.setattr(api, "analyze", fake_analyze)

    with tone("song.wav").open("rb") as f:
        files = {"file": ("song.wav", f, "audio/wav")}
        created = client.post("/projects", files=files, headers=headers)

    assert created.status_code == 202
    job_id = created.json()["id"]

    # TestClient corre las BackgroundTasks antes de devolver la respuesta.
    body = client.get(f"/projects/{job_id}", headers=headers).json()

    assert body["status"] == "done"
    assert body["chords"] == [{"start": 0.0, "end": 30.0, "chord": "C"}]
    # El cliente recibe nombres de stem, nunca rutas del disco del servidor.
    assert body["stems"] == {"vocals": "vocals"}

    audio = client.get(f"/projects/{job_id}/stems/vocals", headers=headers)
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/flac"

    assert client.delete(f"/projects/{job_id}", headers=headers).status_code == 204
    assert client.get(f"/projects/{job_id}", headers=headers).status_code == 404


def test_pipeline_failure_lands_on_the_project(client, headers, tone, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("checkpoint corrupto")

    monkeypatch.setattr(api, "analyze", boom)

    with tone("song.wav").open("rb") as f:
        files = {"file": ("song.wav", f, "audio/wav")}
        created = client.post("/projects", files=files, headers=headers)

    body = client.get(f"/projects/{created.json()['id']}", headers=headers).json()
    assert body["status"] == "error"
    assert "checkpoint corrupto" in body["error"]


def test_missing_stem(client, headers, tone, monkeypatch):
    monkeypatch.setattr(api, "analyze", fake_analyze)
    with tone("song.wav").open("rb") as f:
        files = {"file": ("song.wav", f, "audio/wav")}
        created = client.post("/projects", files=files, headers=headers)
    response = client.get(f"/projects/{created.json()['id']}/stems/piano", headers=headers)
    assert response.status_code == 404


def upload(client, headers, tone, name: str = "song.wav") -> str:
    with tone(name).open("rb") as f:
        created = client.post("/projects", files={"file": (name, f, "audio/wav")}, headers=headers)
    return created.json()["id"]


def test_projects_survive_a_restart(client, headers, tone, monkeypatch):
    """Es la razón de ser de los proyectos: antes todo se perdía al cerrar la app."""
    monkeypatch.setattr(api, "analyze", fake_analyze)
    project_id = upload(client, headers, tone, "Evidencias.wav")

    restart_server()

    [listed] = client.get("/projects", headers=headers).json()
    assert listed["id"] == project_id
    assert listed["name"] == "Evidencias"
    assert listed["status"] == "done"
    assert listed["size_bytes"] > 0
    body = client.get(f"/projects/{project_id}", headers=headers).json()
    assert body["chords"] == [{"start": 0.0, "end": 30.0, "chord": "C"}]
    # La afinación medida viaja con el proyecto: la interfaz avisa si es grande.
    assert body["tuning_cents"] == 43.0
    assert client.get(f"/projects/{project_id}/stems/vocals", headers=headers).status_code == 200


def test_the_list_needs_the_token(client):
    assert client.get("/projects").status_code == 401


def test_deleting_during_the_analysis_leaves_nothing_behind(client, headers, tone, monkeypatch):
    """La separación no se puede cortar: termina, y al ver que se borró no guarda nada."""

    def analyze_and_get_deleted(audio_path, output_dir, **kwargs):
        [job] = api._jobs.values()
        assert client.delete(f"/projects/{job.project.id}", headers=headers).status_code == 204
        return fake_analyze(audio_path, output_dir, **kwargs)

    monkeypatch.setattr(api, "analyze", analyze_and_get_deleted)
    project_id = upload(client, headers, tone)

    assert not projects.project_dir(project_id).exists()
    restart_server()
    assert client.get("/projects", headers=headers).json() == []


def test_the_work_folder_is_cleaned_after_the_analysis(
    client, headers, tone, monkeypatch, tmp_path
):
    monkeypatch.setattr(api, "analyze", fake_analyze)
    project_id = upload(client, headers, tone)
    assert not (tmp_path / "jobs" / project_id).exists()


def _job(project_id: str) -> api.Job:
    project = projects.Project(
        id=project_id, name=project_id, filename="a.wav", created_at="2026-09-28T00:00:00"
    )
    projects.save(project)
    return api.Job(project=project)


def test_only_one_analysis_runs_at_a_time(client, monkeypatch, tone):
    """Dos separaciones simultáneas en la GPU tumbaban el servidor (error de Metal)."""
    import threading
    import time

    running = 0
    peak = 0
    guard = threading.Lock()

    def slow_analyze(audio_path, output_dir, **kwargs):
        nonlocal running, peak
        with guard:
            running += 1
            peak = max(peak, running)
        time.sleep(0.2)
        with guard:
            running -= 1
        return fake_analyze(tone("s.wav"), output_dir, **kwargs)

    monkeypatch.setattr(api, "analyze", slow_analyze)
    jobs = [_job(f"p{i}") for i in range(3)]
    threads = [
        threading.Thread(target=api._process, args=(job, "htdemucs.yaml", True, True))
        for job in jobs
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak == 1
    assert all(job.project.status == "done" for job in jobs)


def test_a_project_deleted_while_queued_is_never_analyzed(client, monkeypatch):
    monkeypatch.setattr(api, "analyze", lambda *a, **k: pytest.fail("no debía analizarse"))
    job = _job("en-cola")
    job.deleted = True

    api._process(job, "htdemucs.yaml", True, True)

    assert not projects.project_dir("en-cola").exists()


def fake_download(title: str = "Evidencias"):
    """Sustituye a youtube.download: deja un audio en la carpeta sin tocar la red."""

    def download(video, folder, on_title=None, on_progress=None):
        on_title(title)
        on_progress(0.5)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "audio.wav"
        sf.write(str(target), np.zeros((4410, 2), dtype=np.float32), 44100)
        return target

    return download


def from_youtube(client, headers, link: str = "https://youtu.be/jNQXAC9IVRw?si=abc"):
    return client.post("/projects/youtube", json={"url": link}, headers=headers)


def test_a_youtube_link_becomes_a_project(client, headers, monkeypatch):
    monkeypatch.setattr(api, "analyze", fake_analyze)
    monkeypatch.setattr(api.youtube, "download", fake_download("Evidencias / Chitãozinho: ao vivo"))

    created = from_youtube(client, headers)

    assert created.status_code == 202
    assert created.json()["status"] == "downloading"
    body = client.get(f"/projects/{created.json()['id']}", headers=headers).json()
    assert body["status"] == "done"
    assert body["name"] == "Evidencias / Chitãozinho: ao vivo"
    assert body["source_url"] == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    # Da nombre a la mezcla exportada: nada que un sistema de archivos rechace.
    assert body["filename"] == "Evidencias   Chitãozinho  ao vivo.wav"
    assert body["chords"] == [{"start": 0.0, "end": 30.0, "chord": "C"}]


def test_a_link_that_is_not_a_video_is_rejected_before_creating_anything(client, headers):
    response = from_youtube(client, headers, "https://www.youtube.com/@jawed")
    assert response.status_code == 422
    assert "YouTube" in response.json()["detail"]
    assert client.get("/projects", headers=headers).json() == []


def test_the_youtube_link_needs_the_token(client):
    assert client.post("/projects/youtube", json={"url": "https://youtu.be/jNQXAC9IVRw"}).status_code == 401


def test_a_failed_download_lands_on_the_project(client, headers, monkeypatch):
    def unavailable(*args, **kwargs):
        raise youtube.Unavailable("YouTube no dejó descargarlo: Private video")

    monkeypatch.setattr(api, "analyze", lambda *a, **k: pytest.fail("no había audio que analizar"))
    monkeypatch.setattr(api.youtube, "download", unavailable)

    created = from_youtube(client, headers)

    body = client.get(f"/projects/{created.json()['id']}", headers=headers).json()
    assert body["status"] == "error"
    assert body["error"] == "YouTube no dejó descargarlo: Private video"


def test_deleting_during_the_download_cuts_it_and_leaves_nothing(client, headers, monkeypatch):
    def download_and_get_deleted(video, folder, on_title=None, on_progress=None):
        [job] = api._jobs.values()
        assert client.delete(f"/projects/{job.project.id}", headers=headers).status_code == 204
        on_progress(0.1)
        pytest.fail("la descarga debía cortarse")

    monkeypatch.setattr(api, "analyze", lambda *a, **k: pytest.fail("no debía analizarse"))
    monkeypatch.setattr(api.youtube, "download", download_and_get_deleted)

    project_id = from_youtube(client, headers).json()["id"]

    assert not projects.project_dir(project_id).exists()
    restart_server()
    assert client.get("/projects", headers=headers).json() == []


def test_a_download_cut_by_closing_the_app_shows_as_interrupted(client, headers):
    projects.save(
        projects.Project(
            id="a-medias", name="youtu.be/jNQXAC9IVRw", filename="",
            created_at="2026-11-10T10:00:00", status="downloading",
        )
    )
    restart_server()

    [listed] = client.get("/projects", headers=headers).json()
    assert listed["status"] == "error"
