"""
api.py — FastAPI encima de core.

Depende de `core`, nunca al revés. Es envoltorio: reemplazarlo por otro
transporte no debería tocar una línea de `core.py`.

El mismo servidor sirve a escritorio (localhost, arrancado por Tauri como
sidecar) y a web (remoto). El frontend solo cambia la URL base.
"""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from mewsplit import projects
from mewsplit.core import DEFAULT_MODEL, SIX_STEM_MODEL, Chord, analyze, get_device
from mewsplit.projects import Project


def load_env_file(path: Path) -> dict[str, str]:
    """
    Carga pares KEY=VALUE de un .env en el entorno, SIN pisar lo ya definido.

    El entorno real gana sobre el archivo, así que Tauri y CI pueden imponer
    sus valores y el archivo solo cubre el hueco del desarrollo local.

    Devuelve lo que leyó del archivo (no lo que quedó en el entorno), para
    poder probarlo sin depender de os.environ.
    """
    leidos: dict[str, str] = {}
    if not path.exists():
        return leidos

    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()

        key, sep, value = line.partition("=")
        if not sep:
            continue

        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]

        leidos[key] = value
        os.environ.setdefault(key, value)

    return leidos


# Fuente única de puerto y token en desarrollo: frontend/next.config.ts lee
# ESTE MISMO archivo. Tenerlos en dos sitios era la causa de que el frontend
# apuntara a un puerto donde ya no había nadie.
ENV_FILE = Path(os.environ.get("MEWSPLIT_ENV_FILE", Path(__file__).resolve().parent.parent / ".env"))
load_env_file(ENV_FILE)

# Token aleatorio por arranque: en localhost cualquier proceso de la máquina
# puede hablarle al servidor. Se lo pasamos al frontend por variable de entorno.
TOKEN = os.environ.get("MEWSPLIT_TOKEN") or secrets.token_urlsafe(32)

# Sin este directorio los checkpoints de Demucs caen en /tmp, que macOS purga.
MODEL_CACHE = Path(
    os.environ.get("MEWSPLIT_MODEL_DIR", Path.home() / ".cache" / "mewsplit" / "models")
)

JOBS_DIR = Path(os.environ.get("MEWSPLIT_WORK_DIR", Path(tempfile.gettempdir()) / "mewsplit"))

EXTENSIONS = {".wav", ".mp3", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}


class Status(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class ChordOut(BaseModel):
    start: float
    end: float
    chord: str


class ProjectSummary(BaseModel):
    """Lo que necesita la lista de proyectos: sin acordes ni stems."""

    id: str
    name: str
    status: Status
    created_at: str
    # Avance de la separación, no del trabajo entero: los acordes terminan en
    # ~2s y marcarlos aquí dejaría la barra al 100% durante toda la separación.
    progress: float = 0.0
    error: str | None = None
    duration: float | None = None
    model: str | None = None
    size_bytes: int = 0


class ProjectOut(ProjectSummary):
    """
    Espejo tipado de `core.Analysis` para que OpenAPI (y por tanto
    `shared/types.ts`) tenga un contrato explícito. La duplicación es
    deliberada: mantiene a `core` libre de dependencias de transporte.
    """

    filename: str
    # Los acordes se pueden pintar mucho antes de que existan los stems.
    chords_ready: bool = False
    device: str | None = None
    stems: dict[str, str] = {}
    chords: list[ChordOut] = []
    # Desvío de la grabación respecto a La 440, en cents: la interfaz avisa
    # cuando es grande, porque tocar encima exige afinar el instrumento a ella.
    tuning_cents: float | None = None
    timings: dict[str, float] = {}


class HealthOut(BaseModel):
    ok: bool
    version: str
    device: str
    models: dict[str, str]


@dataclass
class Job:
    """Un proyecto más lo que solo existe mientras el proceso vive (el avance)."""

    project: Project
    progress: float = 0.0
    # Se llenan en cuanto la rama de acordes termina, sin esperar a los stems.
    chords_ready: bool = False
    # Eliminado mientras se analizaba: el análisis termina y se descarta.
    deleted: bool = False


# Los proyectos terminados viven en disco (projects.py); este registro añade el
# estado vivo de los que se están analizando. Se carga la primera vez que hace
# falta y no al importar: así las pruebas pueden apuntar PROJECTS_DIR a otro lado.
_jobs: dict[str, Job] = {}
_loaded = False
_lock = threading.Lock()

# Un análisis a la vez. Dos separaciones simultáneas sobre la GPU (MPS) desde
# hilos distintos chocan dentro de Metal (`failed assertion _status <
# MTLCommandBufferStatusCommitted`) y macOS mata el proceso entero: subir
# varias canciones seguidas tumbaba el servidor. Las demás esperan en "queued";
# repartir la GPU entre varias tampoco sería más rápido.
_analysis_slot = threading.Lock()


def _registry() -> dict[str, Job]:
    global _loaded
    with _lock:
        if not _loaded:
            for project in projects.load_all():
                _jobs.setdefault(project.id, Job(project=project, progress=1.0))
            _loaded = True
    return _jobs


app = FastAPI(title="mewsplit", version="0.1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("MEWSPLIT_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def busy() -> bool:
    """¿Hay algún análisis en cola o en proceso? Para no apagar a mitad de uno."""
    with _lock:
        return any(job.project.status in projects.UNFINISHED for job in _jobs.values())


def verify_token(x_mewsplit_token: str | None = Header(default=None)) -> None:
    if not secrets.compare_digest(x_mewsplit_token or "", TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido o ausente")


def _get_job(project_id: str) -> Job:
    job = _registry().get(project_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return job


def _summary(job: Job) -> ProjectSummary:
    project = job.project
    return ProjectSummary(
        id=project.id,
        name=project.name,
        status=Status(project.status),
        created_at=project.created_at,
        progress=job.progress,
        error=project.error,
        duration=project.duration,
        model=project.model,
        size_bytes=projects.size_bytes(project.id) if project.status == "done" else 0,
    )


def _serialize(job: Job) -> ProjectOut:
    project = job.project
    return ProjectOut(
        **_summary(job).model_dump(),
        filename=project.filename,
        chords_ready=job.chords_ready or project.status == "done",
        device=project.device,
        # El cliente recibe nombres de stem, no rutas del disco del servidor.
        stems={name: name for name in project.stems},
        chords=[ChordOut(start=c.start, end=c.end, chord=c.chord) for c in project.chords],
        tuning_cents=project.tuning_cents,
        timings=project.timings,
    )


def _process(job: Job, model: str, with_chords: bool, large_vocabulary: bool) -> None:
    # Recibe el Job y no el id: si lo eliminan antes de que arranque, ya no
    # está en el registro, pero el análisis sigue necesitando saber que se borró.
    project = job.project
    project_id = project.id

    with _analysis_slot:
        if job.deleted:
            # Se eliminó mientras esperaba su turno: ni siquiera se analiza.
            projects.delete(project_id)
            return
        _analyze(job, model, with_chords, large_vocabulary)


def _analyze(job: Job, model: str, with_chords: bool, large_vocabulary: bool) -> None:
    project = job.project
    project_id = project.id
    project.status = Status.PROCESSING.value
    projects.save(project)

    # La separación escribe WAV en una carpeta de trabajo; al proyecto solo
    # llegan los FLAC. Así un análisis a medias no deja basura en el proyecto.
    work = JOBS_DIR / project_id

    def on_progress(progress: float) -> None:
        job.progress = progress

    def on_chords(chords: list[Chord]) -> None:
        project.chords = chords
        job.chords_ready = True

    try:
        analysis = analyze(
            projects.original_path(project),
            work / "stems",
            model=model,
            with_chords=with_chords,
            large_vocabulary=large_vocabulary,
            model_cache_dir=MODEL_CACHE,
            verbose=False,
            on_progress=on_progress,
            on_chords=on_chords,
        )
        if not job.deleted:
            # Sin el instrumental: la interfaz no lo usa y costaría otro stem en disco.
            project.stems = projects.store_stems(
                project_id, {name: Path(path) for name, path in analysis.stems.items()}
            )
            project.model = analysis.model
            project.device = analysis.device
            project.duration = analysis.duration
            project.chords = analysis.chords
            project.tuning_cents = analysis.tuning_cents
            project.timings = analysis.timings
            project.status = Status.DONE.value
            job.progress = 1.0
    except Exception as e:
        project.status = Status.ERROR.value
        project.error = str(e)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if job.deleted:
        projects.delete(project_id)
    else:
        projects.save(project)


@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    """Sin token: el sidecar la usa para saber cuándo el backend está vivo."""
    return HealthOut(
        ok=True,
        version=app.version,
        device=get_device(),
        models={"four_stems": DEFAULT_MODEL, "six_stems": SIX_STEM_MODEL},
    )


@app.get("/projects", response_model=list[ProjectSummary], dependencies=[Depends(verify_token)])
def list_projects() -> list[ProjectSummary]:
    jobs = sorted(_registry().values(), key=lambda j: j.project.created_at, reverse=True)
    return [_summary(job) for job in jobs]


@app.post(
    "/projects", response_model=ProjectOut, status_code=202, dependencies=[Depends(verify_token)]
)
async def create_project(
    tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = DEFAULT_MODEL,
    with_chords: bool = True,
    large_vocabulary: bool = True,
) -> ProjectOut:
    filename = Path(file.filename or "audio").name
    if Path(filename).suffix.lower() not in EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Formato no soportado: {filename}")

    project = Project(
        id=uuid.uuid4().hex,
        name=Path(filename).stem,
        filename=filename,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    original = projects.original_path(project)
    original.parent.mkdir(parents=True, exist_ok=True)
    with original.open("wb") as target:
        shutil.copyfileobj(file.file, target)
    projects.save(project)

    job = Job(project=project)
    _registry()
    with _lock:
        _jobs[project.id] = job

    tasks.add_task(_process, job, model, with_chords, large_vocabulary)
    return _serialize(job)


@app.get("/projects/{project_id}", response_model=ProjectOut, dependencies=[Depends(verify_token)])
def read_project(project_id: str) -> ProjectOut:
    return _serialize(_get_job(project_id))


@app.get("/projects/{project_id}/stems/{name}", dependencies=[Depends(verify_token)])
def read_stem(project_id: str, name: str) -> FileResponse:
    job = _get_job(project_id)
    path = projects.stem_path(project_id, name)
    if name not in job.project.stems or not path.exists():
        raise HTTPException(status_code=404, detail=f"Stem no disponible: {name}")
    return FileResponse(path, media_type="audio/flac", filename=f"{name}.flac")


@app.delete("/projects/{project_id}", status_code=204, dependencies=[Depends(verify_token)])
def delete_project(project_id: str) -> None:
    job = _get_job(project_id)
    with _lock:
        _jobs.pop(project_id, None)
    if job.project.status in projects.UNFINISHED:
        # La separación no se puede cortar a mitad: termina y _process lo borra.
        job.deleted = True
    else:
        projects.delete(project_id)


def run(host: str = "127.0.0.1", port: int | None = None) -> None:
    """
    Arranca el servidor.

    Sin `MEWSPLIT_PORT` toma un puerto libre del sistema: fijar uno por
    defecto revienta si el usuario lo tiene ocupado, y el sidecar de Tauri
    no necesita saberlo de antemano porque lo lee de la línea de arranque.

    En desarrollo sí conviene fijarlo: el frontend lee la URL de
    `NEXT_PUBLIC_MEWSPLIT_API` al arrancar, así que un puerto que cambia en
    cada reinicio obliga a reescribir `.env.local` y reiniciar `next dev`.

    Imprime `MEWSPLIT_READY port=<n> token=<t>` en stdout — esa línea es el
    contrato con el sidecar de Tauri, que la parsea para saber a dónde hablar.
    """
    import socket

    import uvicorn

    if port is None:
        port = int(os.environ.get("MEWSPLIT_PORT", "0"))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    bound_port = sock.getsockname()[1]

    print(f"MEWSPLIT_READY port={bound_port} token={TOKEN}", flush=True)

    config = uvicorn.Config(app, log_level="info")
    server = uvicorn.Server(config)
    server.run(sockets=[sock])


if __name__ == "__main__":
    run()
