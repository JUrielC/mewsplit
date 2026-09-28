"""
chords.py — detección de progresión armónica con BTC (`puar-playground/btc-chord`).

Corre en CPU y tarda ~1s por canción: no depende de la separación y no
necesita GPU. Ver la nota de licencia sobre los pesos en el README.
"""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable

    from mewsplit.core import Stopwatch

MODEL = "puar-playground/btc-chord"

# 170 clases (séptimas, sus, disminuidos) frente a las 25 del vocabulario simple.
LARGE_VOCABULARY = True

# Medidos en GuitarSet (bench_chords.py). El resultado casi no cambia entre
# 0.9 y 0.995: no es un ajuste fino que se rompa con otra música.
SELF_PROBABILITY = 0.99
# Una séptima tiene que pesar 3 veces lo que la tríada para mostrarse. Es
# conservador a propósito: una séptima inventada choca al tocar encima; una
# omitida solo suena más simple.
QUALITY_MARGIN = 3.0

_model_cache: dict[bool, object] = {}


def detect_chords(
    audio_path: str | Path,
    large_vocabulary: bool = LARGE_VOCABULARY,
    timer: "Stopwatch | None" = None,
) -> list[dict]:
    """
    Devuelve [{"start": 0.0, "end": 1.48, "chord": "C:maj7"}, ...] en notación Harte.

    El acorde "N" significa ausencia de armonía detectable (silencio, ruido).

    Siempre corre el modelo de 170 clases: raíz y tiempos salen de su masa
    sumada por familia y suavizada con Viterbi; la calidad se decide después,
    por segmento. `large_vocabulary=False` se queda en mayor/menor, pero
    sumando el grande, que en GuitarSet acierta más que el checkpoint de 25.
    Los números de cada decisión están en CLAUDE.md.
    """
    _load(True, timer)

    with _timed(timer, "chords"):
        # tuning=None: compensa grabaciones desafinadas (ver cqt_features).
        probs = frame_probabilities(audio_path, large_vocabulary=True, overlap=True, tuning=None)
        path = smooth(to_families(probs), SELF_PROBABILITY)

    if not large_vocabulary:
        return path_to_segments(path, lambda family, _: simple_label(family))
    return path_to_segments(
        path, lambda family, frames: assign_quality(family, probs[frames], QUALITY_MARGIN)
    )


def _load(large_vocabulary: bool, timer: "Stopwatch | None"):
    """
    Cachea el modelo por vocabulario: en un servidor de larga vida releerlo
    en cada petición cuesta más que la propia inferencia.
    """
    if large_vocabulary in _model_cache:
        return _model_cache[large_vocabulary]

    from transformers.dynamic_module_utils import get_class_from_dynamic_module

    # NO usar AutoModel.from_pretrained: se queda `large_voca` como atributo de
    # la configuración y el from_pretrained de BTC nunca lo recibe, así que
    # siempre cargaba el de 170 clases. Llamar a la clase directamente sí lo pasa.
    with _timed(timer, "load_chord_model"):
        btc = get_class_from_dynamic_module("modeling_btc.BTCForChordRecognition", MODEL)
        model = btc.from_pretrained(MODEL, large_voca=large_vocabulary, device="cpu")

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


# ---------------------------------------------------------------------------
# Decodificación
#
# `model.predict()` toma el argmax de cada frame de ~93 ms y tira las
# probabilidades: un frame que duda 51/49 entre C y Am se convierte en un
# segmento propio. Todo lo de abajo trabaja sobre las probabilidades.
# ---------------------------------------------------------------------------

# Hiperparámetros fijos de BTC (ver modeling_btc.py del repositorio del modelo).
TIMESTEP = 108
FRAME_SECONDS = 10.0 / TIMESTEP

ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Orden de calidades del vocabulario grande: índice = raíz * 14 + calidad.
QUALITIES = [
    "min", "maj", "dim", "aug", "min6", "maj6", "min7",
    "minmaj7", "maj7", "7", "dim7", "hdim7", "sus2", "sus4",
]
# Calidades con tercera menor: es la regla del modo "simples" (mayor/menor).
# Los sus no tienen tercera; se cuentan como mayores, la convención de MIREX.
MINOR_THIRD = {"min", "dim", "min6", "min7", "minmaj7", "dim7", "hdim7"}
LARGE_X, LARGE_N = 168, 169

# Familias de la decodificación. Aumentado y disminuido tienen familia propia:
# dentro de la mayor y la menor, Viterbi nunca los separaba del acorde vecino
# y desaparecían (el F#aug de "Evidencias" quedaba absorbido en un F# de 4 s).
KIND_OF = {
    "maj": "maj", "maj6": "maj", "maj7": "maj", "7": "maj", "sus2": "maj", "sus4": "maj",
    "min": "min", "min6": "min", "min7": "min", "minmaj7": "min",
    "aug": "aug",
    "dim": "dim", "dim7": "dim", "hdim7": "dim",
}
# Índices: los 24 primeros son raíz * 2 + (0 mayor, 1 menor), el mismo orden
# que el vocabulario reducido; luego 12 aumentados, 12 disminuidos y "sin acorde".
AUG_OFFSET, DIM_OFFSET = 24, 36
FAMILIES = 49
FAMILY_N = 48
# La familia disminuida junta 3 calidades frente a las 6 de la mayor, así que
# parte con desventaja; ×3 la compensa. Medido en GuitarSet y Billboard: con
# ×1 casi no aparecen disminuidos y con ×3 la raíz no empeora. El aumentado
# con peso extra gana algo de detección pero pierde precisión, así que va ×1.
DIM_WEIGHT = 3.0


# Por debajo de este desvío no se compensa. Estimar la afinación no es exacto,
# y corregir unos pocos cents que no hacían falta solo mete ruido: en canciones
# afinadas (todas las medidas quedan por debajo de 20 cents) empeoraba un poco
# el resultado. Una grabación desafinada de verdad, como "The Man Who Sold The
# World" de Nirvana (+43 cents), pasaba de acordes erráticos a su progresión.
MIN_DETUNE_CENTS = 20


def tuning_to_apply(estimated: float) -> float:
    """El desvío estimado (en semitonos) si pasa el umbral; si no, 0."""
    return estimated if abs(estimated) * 100 >= MIN_DETUNE_CENTS else 0.0


def cqt_features(audio_path: str | Path, tuning: float | None = 0.0) -> np.ndarray:
    """
    Log-CQT [bins, T] con la misma ventana y parámetros que BTC
    (`btc_src.features.audio_to_features`), más la afinación.

    BTC aprendió con grabaciones afinadas a 440 Hz y calcula sus casillas de
    frecuencia (un cuarto de tono cada una) contando con eso. Una grabación
    desplazada ~45 cents pone cada nota entre dos casillas y el modelo duda
    entre semitonos vecinos (G#/A, C#/D…). `tuning=None` estima el
    desplazamiento de la grabación y, si pasa MIN_DETUNE_CENTS, corre las
    casillas esa misma cantidad;
    con 0.0 el resultado es idéntico al de BTC.
    """
    import librosa

    sr = 22050
    wav, _ = librosa.load(str(audio_path), sr=sr, mono=True)
    if tuning is None:
        # En fracciones de semitono; la CQT de BTC tiene 2 casillas por semitono.
        tuning = tuning_to_apply(float(librosa.estimate_tuning(y=wav, sr=sr)))

    def cqt(chunk: np.ndarray) -> np.ndarray:
        return librosa.cqt(
            chunk, sr=sr, n_bins=144, bins_per_octave=24, hop_length=2048, tuning=tuning * 2
        )

    # Bloques de 10 s sin solapar, como el original: el modelo se entrenó así.
    window = int(sr * 10.0)
    blocks = []
    start = 0
    while len(wav) > start + window:
        blocks.append(cqt(wav[start:start + window]))
        start += window
    blocks.append(cqt(wav[start:]))
    return np.log(np.abs(np.concatenate(blocks, axis=1)) + 1e-6)


def frame_probabilities(
    audio_path: str | Path, large_vocabulary: bool, overlap: bool = False,
    tuning: float | None = 0.0,
) -> np.ndarray:
    """
    Probabilidades por frame [T, clases], una fila cada FRAME_SECONDS.

    BTC ve el audio en bloques de 108 frames (10 s) sin contexto entre ellos.
    Con `overlap` se evalúan también bloques desplazados medio bloque y se
    promedian con peso triangular, para que cada frame lo decida un bloque en
    el que no está pegado al borde.
    """

    import torch

    model = _load(large_vocabulary, timer=None)
    feat = cqt_features(audio_path, tuning).T
    feat = (feat - model._mean) / model._std
    frames = feat.shape[0]

    hop = TIMESTEP // 2 if overlap else TIMESTEP
    padded = int(np.ceil(frames / TIMESTEP)) * TIMESTEP + (hop if overlap else 0)
    feat = np.pad(feat, ((0, padded - frames), (0, 0)))
    x = torch.tensor(feat, dtype=torch.float32).unsqueeze(0)

    weights = np.bartlett(TIMESTEP + 2)[1:-1] if overlap else np.ones(TIMESTEP)
    total = None
    norm = np.zeros(padded)
    with torch.no_grad():
        for start in range(0, padded - TIMESTEP + 1, hop):
            hidden, _ = model.model.self_attn_layers(x[:, start:start + TIMESTEP, :])
            logits = model.model.output_layer.output_projection(hidden)
            probs = torch.softmax(logits, dim=-1).squeeze(0).numpy()
            if total is None:
                total = np.zeros((padded, probs.shape[1]))
            total[start:start + TIMESTEP] += probs * weights[:, None]
            norm[start:start + TIMESTEP] += weights

    return (total / norm[:, None])[:frames]


def family_of(root: int, kind: str) -> int:
    if kind == "aug":
        return AUG_OFFSET + root
    if kind == "dim":
        return DIM_OFFSET + root
    return root * 2 + (kind == "min")


def kind_of_family(family: int) -> tuple[int, str]:
    """(raíz, tipo) de una familia. No acepta FAMILY_N."""
    if family >= DIM_OFFSET:
        return family - DIM_OFFSET, "dim"
    if family >= AUG_OFFSET:
        return family - AUG_OFFSET, "aug"
    root, minor = divmod(family, 2)
    return root, "min" if minor else "maj"


def to_families(probs: np.ndarray) -> np.ndarray:
    """
    Suma las probabilidades del vocabulario grande por familia.

    Con 170 clases, "do mayor" se reparte entre C, C:7, C:maj7, C:maj6...
    Cada una tiene poca masa y el argmax salta entre ellas aunque la armonía
    no cambie. Sumadas, recuperan la masa completa.
    """
    families = np.zeros((probs.shape[0], FAMILIES))
    for index in range(LARGE_X):
        root, quality = divmod(index, len(QUALITIES))
        families[:, family_of(root, KIND_OF[QUALITIES[quality]])] += probs[:, index]
    # "X" (acorde desconocido) no dice nada de la raíz: cuenta como ausencia.
    families[:, FAMILY_N] += probs[:, LARGE_X] + probs[:, LARGE_N]

    families[:, DIM_OFFSET:DIM_OFFSET + 12] *= DIM_WEIGHT
    return families / families.sum(axis=1, keepdims=True)


def smooth(probs: np.ndarray, self_probability: float) -> np.ndarray:
    """
    Camino de Viterbi sobre probabilidades [T, estados].

    Cambiar de acorde "cuesta": con `self_probability` alta, un frame dudoso
    no alcanza a pagar dos cambios y el fantasma desaparece. Un cambio real
    sostenido varios frames sí lo paga.
    """
    import librosa

    transition = librosa.sequence.transition_loop(probs.shape[1], self_probability)
    return librosa.sequence.viterbi_discriminative(
        np.ascontiguousarray(probs.T), transition
    )


def beat_pool(probs: np.ndarray, beats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Promedia las probabilidades dentro de cada intervalo entre beats.

    Devuelve (probabilidades por beat [B, estados], índice de beat por frame [T])
    para poder decodificar por beats y volver a expandir a frames.
    """
    times = np.arange(probs.shape[0]) * FRAME_SECONDS
    owner = np.searchsorted(beats, times, side="right")
    pooled = np.zeros((owner.max() + 1, probs.shape[1]))
    np.add.at(pooled, owner, probs)
    counts = np.bincount(owner, minlength=pooled.shape[0])
    used = counts > 0
    pooled[used] /= counts[used, None]
    # Un intervalo sin frames (beats más juntos que un frame) hereda uniforme.
    pooled[~used] = 1.0 / probs.shape[1]
    return pooled, owner


def family_label(family: int) -> str:
    if family == FAMILY_N:
        return "N"
    root, kind = kind_of_family(family)
    return ROOTS[root] if kind == "maj" else f"{ROOTS[root]}:{kind}"


def simple_label(family: int) -> str:
    """Solo mayor o menor, según la tercera: el aumentado es mayor, el disminuido menor."""
    if family == FAMILY_N:
        return "N"
    root, kind = kind_of_family(family)
    return f"{ROOTS[root]}:min" if kind in ("min", "dim") else ROOTS[root]


def assign_quality(family: int, large_probs: np.ndarray, margin: float) -> str:
    """
    Calidad de un segmento cuya familia ya está decidida.

    Suma la masa de cada calidad compatible (misma raíz, misma familia) en
    todo el segmento. La tríada gana salvo que otra la supere por `margin`:
    así una séptima necesita evidencia sostenida, no un par de frames.
    """
    if family == FAMILY_N:
        return "N"
    root, kind = kind_of_family(family)
    mass = large_probs.sum(axis=0)

    # La tríada de cada familia se llama igual que la familia: maj, min, aug, dim.
    triad = kind
    compatible = [q for q in QUALITIES if KIND_OF[q] == kind]
    scores = {q: mass[root * len(QUALITIES) + QUALITIES.index(q)] for q in compatible}
    best = max(scores, key=scores.get)

    quality = best if scores[best] > margin * scores[triad] else triad
    return ROOTS[root] if quality == "maj" else f"{ROOTS[root]}:{quality}"


def path_to_segments(
    path: np.ndarray, label: "Callable[[int, slice], str]"
) -> list[dict]:
    """Agrupa frames consecutivos del mismo estado en segmentos etiquetados."""
    segments: list[dict] = []
    start = 0
    for i in range(1, len(path) + 1):
        if i == len(path) or path[i] != path[start]:
            chord = label(int(path[start]), slice(start, i))
            if segments and segments[-1]["chord"] == chord:
                segments[-1]["end"] = round(i * FRAME_SECONDS, 3)
            else:
                segments.append(
                    {
                        "start": round(start * FRAME_SECONDS, 3),
                        "end": round(i * FRAME_SECONDS, 3),
                        "chord": chord,
                    }
                )
            start = i
    return segments
