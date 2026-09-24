"""
core.py — orquestación del pipeline. Lógica pura.

**No sabe dónde corre.** Sin FastAPI, Gradio, Modal, Tauri ni nada de
plataforma: recibe rutas de archivo y devuelve datos. `api.py` depende de
este módulo, nunca al revés.

Si una tarea parece requerir que este archivo importe algo de plataforma,
la solución está mal planteada.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

import soundfile as sf
import torch

from mewsplit.chords import detect_chords
from mewsplit.separation import (
    DEFAULT_MODEL,
    SIX_STEM_MODEL,
    build_instrumental,
    separate,
)

__all__ = [
    "DEFAULT_MODEL",
    "SIX_STEM_MODEL",
    "Analysis",
    "Chord",
    "Stopwatch",
    "analyze",
    "get_device",
]


@dataclass(frozen=True)
class Chord:
    start: float
    end: float
    chord: str


@dataclass
class Analysis:
    source: str
    device: str
    model: str
    duration: float | None
    stems: dict[str, str] = field(default_factory=dict)
    instrumental: str | None = None
    chords: list[Chord] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Stopwatch:
    """
    Mide etapas. Una instancia por análisis — nada de estado global, porque
    dos peticiones concurrentes se pisarían los tiempos.
    """

    def __init__(self, verbose: bool = True) -> None:
        self.timings: dict[str, float] = {}
        self.verbose = verbose

    @contextmanager
    def measure(self, label: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.timings[label] = round(elapsed, 2)
            if self.verbose:
                print(f"  [{label}] {elapsed:.2f}s")


def get_device() -> str:
    """Dispositivo preferido para separación: MPS en Apple Silicon, CUDA, o CPU."""
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def get_duration(audio_path: str | Path) -> float | None:
    try:
        info = sf.info(str(audio_path))
        return round(info.frames / info.samplerate, 2)
    except Exception:
        return None


def analyze(
    audio_path: str | Path,
    output_dir: str | Path,
    model: str = DEFAULT_MODEL,
    with_chords: bool = True,
    large_vocabulary: bool = True,
    model_cache_dir: str | Path | None = None,
    verbose: bool = True,
    on_progress=None,
    on_chords=None,
) -> Analysis:
    """
    Punto de entrada del pipeline.

    Separación y acordes corren **en paralelo**: está medido que detectar
    acordes sobre el instrumental no mejora la precisión (20 de 22 tramos
    idénticos), así que los acordes no esperan a los stems. El instrumental
    se sigue generando porque es una salida útil por sí misma.

    `on_progress(avance: float)` informa SOLO de la separación, que es ~92%
    del tiempo total y por tanto el único avance que significa algo. No
    recibe el nombre de la etapa a propósito: un progreso compartido entre
    las dos ramas paralelas se pisa a sí mismo, y la rama corta acaba
    marcando 100% mientras la larga sigue trabajando.

    `on_chords(acordes)` avisa en cuanto la armonía está lista —unos dos
    segundos— para que la capa de transporte pueda publicarla sin esperar a
    los stems.
    """
    audio_path = Path(audio_path).resolve()
    output_dir = Path(output_dir).resolve()

    if not audio_path.exists():
        raise FileNotFoundError(f"Archivo de audio no encontrado: {audio_path}")

    clock = Stopwatch(verbose=verbose)
    device = get_device()

    if verbose:
        print(f"\nIniciando análisis: {audio_path.name}")
        print(f"Dispositivo preferido: {device.upper()}")

    def report(progress: float) -> None:
        if on_progress is not None:
            on_progress(progress)

    def run_separation() -> dict[str, Path]:
        report(0.0)
        stems = separate(
            audio_path,
            output_dir,
            model=model,
            model_cache_dir=model_cache_dir,
            timer=clock,
            on_progress=report,
        )
        report(1.0)
        return stems

    def run_chords() -> list[Chord]:
        if not with_chords:
            return []
        # Sobre el audio original, no sobre el instrumental: no espera a los stems.
        raw = detect_chords(audio_path, large_vocabulary=large_vocabulary, timer=clock)
        chords = [Chord(start=c["start"], end=c["end"], chord=c["chord"]) for c in raw]
        if on_chords is not None:
            on_chords(chords)
        return chords

    with clock.measure("total"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_stems = pool.submit(run_separation)
            future_chords = pool.submit(run_chords)
            stems = future_stems.result()
            chords = future_chords.result()

        instrumental_path = build_instrumental(stems, output_dir, timer=clock)

    if verbose:
        print(f"  stems generados: {', '.join(sorted(stems))}")

    return Analysis(
        source=str(audio_path),
        device=device,
        model=model,
        duration=get_duration(audio_path),
        stems={name: str(path) for name, path in stems.items()},
        instrumental=str(instrumental_path) if instrumental_path else None,
        chords=chords,
        timings=clock.timings,
    )
