"""
separation.py — envoltura de `audio-separator` (Demucs v4).

No importa nada de `core`: la dependencia va en un solo sentido.
El cronómetro llega como parámetro y solo se necesita que exponga
`measure(etiqueta)` como context manager.
"""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf

if TYPE_CHECKING:
    from mewsplit.core import Stopwatch

# Verificado con `audio-separator --list_models`. Demucs v4 estándar, 4 stems.
DEFAULT_MODEL = "htdemucs.yaml"

# 6 stems (añade guitarra y piano). Opcional: degrada los 4 stems base.
SIX_STEM_MODEL = "htdemucs_6s.yaml"

NON_VOCAL_STEMS = ("bass", "drums", "other", "guitar", "piano")

_STEM_NAMES = ("vocals", "bass", "drums", "other", "guitar", "piano", "instrumental")


def separate(
    audio_path: str | Path,
    output_dir: str | Path,
    model: str = DEFAULT_MODEL,
    model_cache_dir: str | Path | None = None,
    timer: "Stopwatch | None" = None,
) -> dict[str, Path]:
    """
    Separa un archivo de audio en stems.

    Devuelve {nombre_stem: Path}, ej. {"vocals": Path(...), "bass": Path(...)}.

    `model_cache_dir` importa: por defecto `audio-separator` guarda los
    checkpoints en /tmp, que macOS purga.
    """
    from audio_separator.separator import Separator

    audio_path = Path(audio_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    options = {"output_dir": str(output_dir), "output_format": "wav"}
    if model_cache_dir is not None:
        cache = Path(model_cache_dir).expanduser().resolve()
        cache.mkdir(parents=True, exist_ok=True)
        options["model_file_dir"] = str(cache)

    separator = Separator(**options)

    # La carga es diferida: sin este bloque el tiempo aparecería dentro del de separación.
    with _timed(timer, "load_separation_model"):
        separator.load_model(model_filename=model)

    with _timed(timer, "separation"):
        produced = separator.separate(str(audio_path))

    return _map_stems(produced, output_dir)


def _map_stems(produced, output_dir: Path) -> dict[str, Path]:
    """
    Normaliza el retorno de `separate()`, que según la versión de
    audio-separator devuelve rutas absolutas o solo nombres de archivo.
    """
    stems: dict[str, Path] = {}
    for item in produced:
        path = Path(item)
        if not path.is_absolute():
            path = output_dir / path
        if not path.exists():
            continue

        name = path.stem.lower()
        for candidate in _STEM_NAMES:
            if candidate in name:
                stems[candidate] = path
                break
        else:
            stems[path.stem] = path
    return stems


def build_instrumental(
    stems: dict[str, Path],
    output_dir: str | Path,
    timer: "Stopwatch | None" = None,
) -> Path | None:
    """
    Suma los stems no vocales en un único `instrumental.wav`.

    Devuelve None si no hay ningún stem no vocal disponible.
    """
    if "instrumental" in stems and stems["instrumental"].exists():
        return stems["instrumental"]

    present = [stems[s] for s in NON_VOCAL_STEMS if s in stems and stems[s].exists()]
    if not present:
        return None

    output_dir = Path(output_dir).resolve()

    with _timed(timer, "instrumental_mix"):
        mix = None
        samplerate = None

        for path in present:
            try:
                data, sr = sf.read(str(path), dtype="float32", always_2d=True)
            except Exception as e:
                print(f"  aviso: no se pudo mezclar el stem {path.name}: {e}")
                continue

            if samplerate is None:
                samplerate = sr
            if mix is None:
                mix = data
            else:
                # Los stems pueden diferir en unos pocos frames
                min_len = min(len(mix), len(data))
                mix = mix[:min_len] + data[:min_len]

        if mix is None or samplerate is None:
            return None

        peak = float(np.max(np.abs(mix)))
        if peak > 1.0:
            mix = mix / peak

        out_path = output_dir / "instrumental.wav"
        sf.write(str(out_path), mix, samplerate)

    return out_path


def _timed(timer, label: str):
    return timer.measure(label) if timer is not None else nullcontext()
