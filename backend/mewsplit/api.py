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
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from mewsplit.core import DEFAULT_MODEL, SIX_STEM_MODEL, Analysis, Chord, analyze, get_device


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


class JobOut(BaseModel):
    """
    Espejo tipado de `core.Analysis` para que OpenAPI (y por tanto
    `shared/types.ts`) tenga un contrato explícito. La duplicación es
    deliberada: mantiene a `core` libre de dependencias de transporte.
    """

    id: str
    status: Status
    filename: str
    # Avance de la separación, no del trabajo entero: los acordes terminan en
    # ~2s y marcarlos aquí dejaría la barra al 100% durante toda la separación.
    progress: float = 0.0
    # Los acordes se pueden pintar mucho antes de que existan los stems.
    chords_ready: bool = False
    error: str | None = None
    device: str | None = None
    model: str | None = None
    duration: float | None = None
    stems: dict[str, str] = {}
    instrumental: str | None = None
    chords: list[ChordOut] = []
    timings: dict[str, float] = {}


class HealthOut(BaseModel):
    ok: bool
    version: str
    device: str
    models: dict[str, str]


@dataclass
class Job:
    id: str
    filename: str
    input_path: Path
    output_dir: Path
    status: Status = Status.QUEUED
    progress: float = 0.0
    error: str | None = None
    # Se llenan en cuanto la rama de acordes termina, sin esperar a los stems.
    chords: list[Chord] = field(default_factory=list)
    chords_ready: bool = False
    analysis: Analysis | None = None
    paths: dict[str, Path] = field(default_factory=dict)


# En memoria a propósito: en escritorio el proceso muere con la app. Si el
# despliegue web pasa a varios workers, esto necesita almacenamiento externo.
_jobs: dict[str, Job] = {}
_lock = threading.Lock()

app = FastAPI(title="mewsplit", version="0.1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("MEWSPLIT_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def busy() -> bool:
    """¿Hay algún trabajo en cola o en proceso? Para no apagar a mitad de un análisis."""
    with _lock:
        return any(job.status in (Status.QUEUED, Status.PROCESSING) for job in _jobs.values())


def verify_token(x_mewsplit_token: str | None = Header(default=None)) -> None:
    if not secrets.compare_digest(x_mewsplit_token or "", TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido o ausente")


def _get_job(job_id: str) -> Job:
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return job


def _serialize(job: Job) -> JobOut:
    out = JobOut(
        id=job.id,
        status=job.status,
        filename=job.filename,
        progress=job.progress,
        chords_ready=job.chords_ready,
        error=job.error,
        # Salen del trabajo, no del análisis: así viajan en cuanto están listos
        # aunque la separación siga corriendo.
        chords=[ChordOut(start=c.start, end=c.end, chord=c.chord) for c in job.chords],
    )
    if job.analysis is None:
        return out

    analysis = job.analysis
    out.device = analysis.device
    out.model = analysis.model
    out.duration = analysis.duration
    out.instrumental = "instrumental" if analysis.instrumental else None
    out.timings = analysis.timings
    # El cliente recibe nombres de stem, no rutas del disco del servidor.
    out.stems = {name: name for name in job.paths}
    return out


def _process(job_id: str, model: str, with_chords: bool, large_vocabulary: bool) -> None:
    job = _jobs[job_id]
    job.status = Status.PROCESSING

    def on_progress(progress: float) -> None:
        job.progress = progress

    def on_chords(chords: list[Chord]) -> None:
        job.chords = chords
        job.chords_ready = True

    try:
        analysis = analyze(
            job.input_path,
            job.output_dir,
            model=model,
            with_chords=with_chords,
            large_vocabulary=large_vocabulary,
            model_cache_dir=MODEL_CACHE,
            verbose=False,
            on_progress=on_progress,
            on_chords=on_chords,
        )
        paths = {name: Path(path) for name, path in analysis.stems.items()}
        if analysis.instrumental:
            paths["instrumental"] = Path(analysis.instrumental)

        job.analysis = analysis
        job.paths = paths
        job.chords = analysis.chords
        job.status = Status.DONE
        job.progress = 1.0
    except Exception as e:
        job.status = Status.ERROR
        job.error = str(e)


@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    """Sin token: el sidecar la usa para saber cuándo el backend está vivo."""
    return HealthOut(
        ok=True,
        version=app.version,
        device=get_device(),
        models={"four_stems": DEFAULT_MODEL, "six_stems": SIX_STEM_MODEL},
    )


@app.post("/jobs", response_model=JobOut, status_code=202, dependencies=[Depends(verify_token)])
async def create_job(
    tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = DEFAULT_MODEL,
    with_chords: bool = True,
    large_vocabulary: bool = True,
) -> JobOut:
    filename = Path(file.filename or "audio").name
    if Path(filename).suffix.lower() not in EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Formato no soportado: {filename}")

    job_id = uuid.uuid4().hex
    directory = JOBS_DIR / job_id
    directory.mkdir(parents=True, exist_ok=True)
    input_path = directory / filename

    with input_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)

    job = Job(
        id=job_id,
        filename=filename,
        input_path=input_path,
        output_dir=directory / "stems",
    )
    with _lock:
        _jobs[job_id] = job

    tasks.add_task(_process, job_id, model, with_chords, large_vocabulary)
    return _serialize(job)


@app.get("/jobs/{job_id}", response_model=JobOut, dependencies=[Depends(verify_token)])
def read_job(job_id: str) -> JobOut:
    return _serialize(_get_job(job_id))


@app.get("/jobs/{job_id}/stems/{name}", dependencies=[Depends(verify_token)])
def read_stem(job_id: str, name: str) -> FileResponse:
    job = _get_job(job_id)
    path = job.paths.get(name)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail=f"Stem no disponible: {name}")
    return FileResponse(path, media_type="audio/wav", filename=f"{name}.wav")


@app.delete("/jobs/{job_id}", status_code=204, dependencies=[Depends(verify_token)])
def delete_job(job_id: str) -> None:
    job = _get_job(job_id)
    shutil.rmtree(job.input_path.parent, ignore_errors=True)
    with _lock:
        _jobs.pop(job_id, None)


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
