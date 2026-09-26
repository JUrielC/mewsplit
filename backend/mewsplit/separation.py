"""
separation.py — envoltura de `audio-separator` (Demucs v4).

No importa nada de `core`: la dependencia va en un solo sentido.
El cronómetro llega como parámetro y solo se necesita que exponga
`measure(etiqueta)` como context manager.
"""

from __future__ import annotations

import os
import shutil
from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf

if TYPE_CHECKING:
    from collections.abc import Callable

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
    on_progress: "Callable[[float], None] | None" = None,
) -> dict[str, Path]:
    """
    Separa un archivo de audio en stems.

    Devuelve {nombre_stem: Path}, ej. {"vocals": Path(...), "bass": Path(...)}.

    `model_cache_dir` importa: por defecto `audio-separator` guarda los
    checkpoints en /tmp, que macOS purga.

    `on_progress` recibe un float 0..1 con el avance de la separación.
    """
    from audio_separator.separator import Separator

    ensure_ffmpeg()

    audio_path = Path(audio_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    options: dict = {"output_dir": str(output_dir), "output_format": "wav"}
    if model_cache_dir is not None:
        cache = Path(model_cache_dir).expanduser().resolve()
        cache.mkdir(parents=True, exist_ok=True)
        options["model_file_dir"] = str(cache)

    separator = Separator(**options)

    # La carga es diferida: sin este bloque el tiempo aparecería dentro del de separación.
    with _timed(timer, "load_separation_model"):
        separator.load_model(model_filename=model)

    # Demucs hardcodea set_progress_bar=None dentro de demix_demucs, así que
    # la única forma de capturar el progreso es parchear apply_model para que
    # inyecte nuestro callback. Se restaura al terminar.
    patched = _patch_progress(on_progress)

    try:
        with _timed(timer, "separation"):
            produced = separator.separate(str(audio_path))
    finally:
        patched.restore()

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


def ensure_ffmpeg() -> None:
    """
    Garantiza que haya un `ffmpeg` en el PATH.

    `audio-separator` se niega a arrancar sin él, y quien instala mewsplit para
    tocar no tiene por qué tener Homebrew. Si el sistema ya tiene uno se usa
    ese; si no, el que trae `imageio-ffmpeg` dentro de su wheel. Ese binario se
    llama `ffmpeg-macos-aarch64-v7.1` y audio-separator busca literalmente
    `ffmpeg`, así que se le pone un enlace con ese nombre en la caché.
    """
    if shutil.which("ffmpeg"):
        return

    import imageio_ffmpeg

    bundled = Path(imageio_ffmpeg.get_ffmpeg_exe())
    bin_dir = Path.home() / ".cache" / "mewsplit" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / "ffmpeg"
    # Una actualización de imageio-ffmpeg cambia la ruta del binario: el enlace
    # viejo quedaría apuntando a la nada.
    if link.is_symlink() and link.resolve() != bundled.resolve():
        link.unlink()
    if not link.exists():
        link.symlink_to(bundled)
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def _timed(timer, label: str):
    return timer.measure(label) if timer is not None else nullcontext()


class _patch_progress:
    """
    Parchea temporalmente `apply_model` en el módulo de demucs para inyectar
    un callback de progreso. Necesario porque `demix_demucs` hardcodea
    `set_progress_bar=None`.

    Hay que parchear los DOS módulos: `demucs_separator` hace
    `from ...apply import apply_model` y guarda su propia referencia, así que
    parchear solo `apply` no alcanza la llamada de arriba; y `apply` se llama
    a sí mismo recursivamente por el nombre global de su módulo.
    """

    def __init__(self, on_progress: "Callable[[float], None] | None") -> None:
        self._original = None
        self._modules: list = []

        if on_progress is None:
            return

        try:
            import audio_separator.separator.architectures.demucs_separator as demucs_separator
            import audio_separator.separator.uvr_lib_v5.demucs.apply as demucs_apply
        except ImportError:
            return

        original = demucs_apply.apply_model
        self._original = original
        self._modules = [demucs_apply, demucs_separator]

        def patched_apply_model(*args, **kwargs):
            # Inyectar nuestro callback si la llamada no trae uno propio.
            if kwargs.get("set_progress_bar") is None:
                def _hook(base: float, value: float) -> None:
                    on_progress(min(base + value, 1.0))
                kwargs["set_progress_bar"] = _hook
            return original(*args, **kwargs)

        for module in self._modules:
            module.apply_model = patched_apply_model

    def restore(self) -> None:
        for module in self._modules:
            module.apply_model = self._original
