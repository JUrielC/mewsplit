"""
chords.py — detección de progresión armónica con BTC (`puar-playground/btc-chord`).

Corre en CPU y tarda ~1s por canción: no depende de la separación y no
necesita GPU. Ver la nota de licencia sobre los pesos en el README.
"""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mewsplit.core import Stopwatch

MODEL = "puar-playground/btc-chord"

# 170 clases (séptimas, sus, disminuidos) frente a las 25 del vocabulario simple.
LARGE_VOCABULARY = True

_model_cache: dict[bool, object] = {}


def detect_chords(
    audio_path: str | Path,
    large_vocabulary: bool = LARGE_VOCABULARY,
    timer: "Stopwatch | None" = None,
) -> list[dict]:
    """
    Devuelve [{"start": 0.0, "end": 1.48, "chord": "C:maj7"}, ...] en notación Harte.

    El acorde "N" significa ausencia de armonía detectable (silencio, ruido).
    """
    model = _load(large_vocabulary, timer)

    with _timed(timer, "chords"):
        return model.predict(str(audio_path))


def _load(large_vocabulary: bool, timer: "Stopwatch | None"):
    """
    Cachea el modelo por vocabulario: en un servidor de larga vida releerlo
    en cada petición cuesta más que la propia inferencia.
    """
    if large_vocabulary in _model_cache:
        return _model_cache[large_vocabulary]

    from transformers import AutoModel

    with _timed(timer, "load_chord_model"):
        model = AutoModel.from_pretrained(
            MODEL,
            trust_remote_code=True,
            large_voca=large_vocabulary,
            device="cpu",
        )

    _model_cache[large_vocabulary] = model
    return model


def condense(chords: list[dict]) -> list[str]:
    """Secuencia de acordes únicos consecutivos, sin los tramos 'N'."""
    output: list[str] = []
    previous = None
    for segment in chords:
        chord = segment.get("chord", "N")
        if chord != previous and chord != "N":
            output.append(chord)
        previous = chord
    return output


def chord_at(chords: list[dict], second: float) -> str:
    """Acorde activo en un instante dado."""
    for segment in chords:
        if segment["start"] <= second < segment["end"]:
            return segment["chord"]
    return chords[-1]["chord"] if chords else "N"


def _timed(timer, label: str):
    return timer.measure(label) if timer is not None else nullcontext()
