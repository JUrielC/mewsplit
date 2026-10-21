"""
projects.py — los proyectos guardados en disco.

Un proyecto es una canción ya analizada: su audio original, sus stems y lo
que se sabe de ella (acordes, duración, modelo). Sobrevive a cerrar la app;
antes los trabajos vivían solo en memoria y se perdían al salir.

Envoltorio de almacenamiento: `core` no sabe que esto existe. Lo usa `api`.

    <PROJECTS_DIR>/<id>/
      project.json     metadatos y acordes
      original.<ext>   el audio subido, para poder reanalizarlo sin volver a subirlo
      stems/<n>.flac   los stems, en FLAC
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

import soundfile as sf

from mewsplit.core import Chord

# En macOS, Application Support es donde van los datos que el usuario no
# gestiona a mano (ni Documentos, que es suyo, ni la caché, que el sistema
# puede vaciar).
PROJECTS_DIR = Path(
    os.environ.get(
        "MEWSPLIT_PROJECTS_DIR",
        Path.home() / "Library" / "Application Support" / "mewsplit" / "projects",
    )
)

# Estados que solo tienen sentido mientras el proceso sigue vivo: si aparecen
# al arrancar, el análisis se cortó (se cerró la app a mitad).
UNFINISHED = {"queued", "processing"}
INTERRUPTED = "El análisis se interrumpió: se cerró mewsplit antes de terminar."


@dataclass
class Project:
    id: str
    name: str
    filename: str
    created_at: str
    status: str = "queued"
    error: str | None = None
    model: str | None = None
    device: str | None = None
    duration: float | None = None
    chords: list[Chord] = field(default_factory=list)
    # Desvío respecto a La 440, en cents. None en proyectos de antes de medirlo.
    tuning_cents: float | None = None
    timings: dict[str, float] = field(default_factory=dict)
    stems: list[str] = field(default_factory=list)


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def original_path(project: Project) -> Path:
    return project_dir(project.id) / f"original{Path(project.filename).suffix.lower()}"


def stem_path(project_id: str, name: str) -> Path:
    return project_dir(project_id) / "stems" / f"{name}.flac"


def save(project: Project) -> None:
    """Escribe project.json de forma atómica: un corte a mitad no lo deja roto."""
    directory = project_dir(project.id)
    directory.mkdir(parents=True, exist_ok=True)
    data = asdict(project)
    temporary = directory / "project.json.tmp"
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    temporary.replace(directory / "project.json")


def load(directory: Path) -> Project | None:
    try:
        data = json.loads((directory / "project.json").read_text())
        data["chords"] = [Chord(**c) for c in data.get("chords", [])]
        return Project(**data)
    except (OSError, ValueError, TypeError):
        # Un proyecto ilegible no debe tumbar la lista entera.
        return None


def load_all() -> list[Project]:
    """Todos los proyectos guardados, del más nuevo al más viejo."""
    if not PROJECTS_DIR.exists():
        return []
    projects = []
    for directory in PROJECTS_DIR.iterdir():
        project = load(directory) if directory.is_dir() else None
        if project is None:
            continue
        if project.status in UNFINISHED:
            project.status = "error"
            project.error = INTERRUPTED
            save(project)
        projects.append(project)
    return sorted(projects, key=lambda p: p.created_at, reverse=True)


def store_stems(project_id: str, stems: dict[str, Path]) -> list[str]:
    """
    Copia los stems al proyecto en FLAC.

    FLAC es sin pérdida: mismas muestras que el WAV que produce la separación,
    en ~40–50% del espacio. Una canción separada ocupa 200–350 MB en WAV, y
    guardada para siempre eso llena el disco rápido.
    """
    target = project_dir(project_id) / "stems"
    target.mkdir(parents=True, exist_ok=True)
    names = []
    for name, source in stems.items():
        # La separación escribe PCM de 16 bits y ahí la copia es exacta. Si
        # alguna versión entregara más resolución (24 bits, flotante), se
        # guarda a 24: FLAC no admite flotante y 16 perdería calidad.
        high = sf.info(str(source)).subtype != "PCM_16"
        data, samplerate = sf.read(str(source), dtype="int32" if high else "int16")
        sf.write(
            str(stem_path(project_id, name)), data, samplerate,
            format="FLAC", subtype="PCM_24" if high else "PCM_16",
        )
        names.append(name)
    return names


def size_bytes(project_id: str) -> int:
    return sum(f.stat().st_size for f in project_dir(project_id).rglob("*") if f.is_file())


def delete(project_id: str) -> None:
    shutil.rmtree(project_dir(project_id), ignore_errors=True)
