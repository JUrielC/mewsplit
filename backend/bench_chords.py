"""
bench_chords.py — precisión de la detección de acordes contra GuitarSet.

Cada variante del detector se mide con las mismas métricas para decidir con
números, no de oído, si un cambio mejora o empeora:

- `root`, `majmin`, `sevenths`: acierto ponderado por duración (mir_eval).
- `segmentation`: qué tan bien caen las fronteras, sin mirar la etiqueta.
- `ghosts_per_min`: segmentos más cortos que un beat. Es el síntoma que el
  usuario oye como "acorde fantasma"; en GuitarSet ningún acorde de referencia
  dura menos de 1.2 s.

Referencia: la anotación "instructed" (la partitura que recibió el músico),
no la "performed": esa se infirió de las notas y trae etiquetas como
`sus2(7)` que ningún detector debería imitar. Solo se usan los fragmentos
`comp` (acompañamiento); en los `solo` hay una línea melódica y no acordes.

El conjunto se parte por guitarrista para no ajustar y validar con la misma
persona: 00-03 para ajustar, 04-05 para validar. Si una variante solo mejora
en `tune`, es sobreajuste.

Los datos van a ~/.cache/mewsplit/datasets/guitarset (CC BY 4.0, Xi et al.,
ISMIR 2018), nunca al repositorio.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from functools import cache
from pathlib import Path

import mir_eval
import numpy as np

from mewsplit.chords import (
    _load,
    assign_quality,
    beat_pool,
    detect_chords,
    family_label,
    frame_probabilities,
    path_to_segments,
    smooth,
    to_families,
)

DATASET = Path("~/.cache/mewsplit/datasets/guitarset").expanduser()
# /tests en la raíz del repositorio, ignorado por git: ahí va toda la investigación.
RESULTS = Path(__file__).resolve().parents[1] / "tests" / "bench_output" / "chords.json"
VALIDATION_PLAYERS = {"04", "05"}

METRICS = ["root", "majmin", "sevenths", "segmentation"]

Detector = Callable[[Path], list[dict]]


@cache
def _probs(path: Path, large: bool, overlap: bool) -> np.ndarray:
    return frame_probabilities(path, large_vocabulary=large, overlap=overlap)


@cache
def _beats(path: Path) -> np.ndarray:
    import librosa

    y, sr = librosa.load(str(path), sr=22050, mono=True)
    _, frames = librosa.beat.beat_track(y=y, sr=sr)
    return librosa.frames_to_time(frames, sr=sr)


def decoder(
    source: str,
    self_probability: float | None = None,
    margin: float | None = None,
    overlap: bool = False,
    beats: bool = False,
) -> Detector:
    """
    Arma una variante a partir de sus piezas:

    - `source`: de dónde salen raíz y tiempos. "large" (170 sumadas por
      familia), "small" (25) o "ensemble" (promedio de ambas).
    - `self_probability`: Viterbi con esa probabilidad de quedarse; None = argmax.
    - `margin`: calidad desde el grande, con ese margen sobre la tríada;
      None = solo mayor/menor.
    - `beats`: decodificar por beats en vez de por frames.
    """

    def detect(path: Path) -> list[dict]:
        large = _probs(path, True, overlap)
        if source == "large":
            families = to_families(large)
        elif source == "small":
            families = _probs(path, False, overlap)
        else:
            families = (to_families(large) + _probs(path, False, overlap)) / 2.0

        if beats:
            pooled, owner = beat_pool(families, _beats(path))
            steps = smooth(pooled, self_probability) if self_probability else pooled.argmax(1)
            path_ = steps[owner]
        else:
            path_ = smooth(families, self_probability) if self_probability else families.argmax(1)

        if margin is None:
            return path_to_segments(path_, lambda family, _: family_label(family))
        return path_to_segments(
            path_, lambda family, frames: assign_quality(family, large[frames], margin)
        )

    return detect


# Cada variante recibe la ruta del audio y devuelve segmentos como
# `detect_chords`. Las nuevas se registran aquí para compararlas; `decoder()`
# arma casi cualquier combinación sin tocar `chords.py`.
VARIANTS: dict[str, Detector] = {
    # Lo que usa la app. Es la variante contra la que se compara todo lo demás.
    "current": detect_chords,
    # Punto de partida: el argmax por frame de BTC, sin suavizado.
    "btc_raw": lambda path: _load(True, None).predict(str(path)),
    "btc_raw_small": lambda path: _load(False, None).predict(str(path)),
    # Descartadas, se conservan para poder repetir la comparación:
    # el reducido como base y el grande para la calidad (pierde majmin frente
    # a sumar el grande por familia) y la votación por beat (el beat tracker
    # mete sus propios errores; con Viterbi encima empeora todo).
    "hybrid": decoder("small", margin=1.0),
    "beat_vote": decoder("large", margin=1.0, beats=True),
}


def load_excerpts(dataset: Path = DATASET) -> list[dict]:
    excerpts = []
    for jams_path in sorted((dataset / "annotation").glob("*_comp.jams")):
        name = jams_path.stem
        audio = dataset / "audio_mono-mic" / f"{name}_mic.wav"
        if not audio.exists():
            continue

        jams = json.loads(jams_path.read_text())
        chords = [a for a in jams["annotations"] if a["namespace"] == "chord"]
        tempo = next(a for a in jams["annotations"] if a["namespace"] == "tempo")
        # La primera anotación de acordes es la "instructed"; la segunda, la inferida.
        reference = [
            {"start": d["time"], "end": d["time"] + d["duration"], "chord": d["value"]}
            for d in chords[0]["data"]
        ]
        excerpts.append(
            {
                "name": name,
                "player": name[:2],
                "audio": audio,
                "reference": reference,
                "beat": 60.0 / tempo["data"][0]["value"],
                "duration": jams["file_metadata"]["duration"],
            }
        )
    return excerpts


def _intervals(segments: list[dict]) -> tuple[np.ndarray, list[str]]:
    intervals = np.array([[s["start"], s["end"]] for s in segments], dtype=float)
    return intervals, [s["chord"] for s in segments]


def score(reference: list[dict], estimate: list[dict], beat: float, duration: float) -> dict:
    ref_int, ref_lab = _intervals(reference)
    est_int, est_lab = _intervals(estimate)

    # mir_eval exige que la estimación cubra exactamente el mismo tramo que la
    # referencia: lo que falte se rellena con "N" y lo que sobre se recorta.
    no_chord = mir_eval.chord.NO_CHORD
    est_int, est_lab = mir_eval.util.adjust_intervals(
        est_int, est_lab, ref_int.min(), ref_int.max(), no_chord, no_chord
    )
    merged, ref_m, est_m = mir_eval.util.merge_labeled_intervals(ref_int, ref_lab, est_int, est_lab)
    durations = mir_eval.util.intervals_to_durations(merged)

    result = {}
    for metric in ("root", "majmin", "sevenths"):
        comparison = getattr(mir_eval.chord, metric)(ref_m, est_m)
        # Las etiquetas fuera del vocabulario de la métrica valen -1 y no cuentan.
        valid = comparison >= 0
        weight = durations[valid].sum()
        hits = (comparison[valid] * durations[valid]).sum()
        result[metric] = float(hits / weight) if weight else None
        result[f"{metric}_weight"] = float(weight)

    result["segmentation"] = float(mir_eval.chord.seg(ref_int, est_int))

    voiced = [s for s in estimate if s["chord"] != "N" and s["end"] - s["start"] > 0]
    result["ghosts"] = sum(1 for s in voiced if s["end"] - s["start"] < beat)
    result["segments"] = len(voiced)
    result["reference_segments"] = len(reference)
    result["duration"] = duration
    return result


def aggregate(rows: list[dict]) -> dict:
    """Promedia cada métrica ponderando por duración, como se reporta en MIREX."""
    summary: dict[str, float | int | None] = {"excerpts": len(rows)}
    for metric in ("root", "majmin", "sevenths"):
        pairs = [(r[metric], r[f"{metric}_weight"]) for r in rows if r[metric] is not None]
        weight = sum(w for _, w in pairs)
        summary[metric] = sum(v * w for v, w in pairs) / weight if weight else None

    total = sum(r["duration"] for r in rows)
    summary["segmentation"] = sum(r["segmentation"] * r["duration"] for r in rows) / total
    minutes = total / 60.0
    summary["ghosts_per_min"] = sum(r["ghosts"] for r in rows) / minutes
    summary["segments_per_min"] = sum(r["segments"] for r in rows) / minutes
    summary["reference_segments_per_min"] = sum(r["reference_segments"] for r in rows) / minutes
    return summary


def run(variants: list[str], limit: int | None, out: Path) -> dict:
    excerpts = load_excerpts()
    if not excerpts:
        raise SystemExit(f"No hay datos en {DATASET}: descarga GuitarSet primero (ver README).")
    if limit:
        excerpts = excerpts[:limit]

    report = {}
    for variant in variants:
        detector = VARIANTS[variant]
        rows = []
        started = time.perf_counter()
        for excerpt in excerpts:
            estimate = detector(excerpt["audio"])
            row = score(excerpt["reference"], estimate, excerpt["beat"], excerpt["duration"])
            rows.append({"name": excerpt["name"], "player": excerpt["player"], **row})
        elapsed = time.perf_counter() - started

        tune = [r for r in rows if r["player"] not in VALIDATION_PLAYERS]
        validation = [r for r in rows if r["player"] in VALIDATION_PLAYERS]
        report[variant] = {
            "tune": aggregate(tune) if tune else None,
            "validation": aggregate(validation) if validation else None,
            "all": aggregate(rows),
            "seconds": round(elapsed, 1),
            "excerpts": rows,
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print_report(report)
    print(f"\nDetalle por fragmento en {out}")
    return report


def print_report(report: dict) -> None:
    columns = ["root", "majmin", "sevenths", "segmentation", "ghosts_per_min", "segments_per_min"]
    titles = ["root", "majmin", "sevenths", "segment.", "fantasmas/min", "segmentos/min"]
    header = f"{'variante':<14}{'conjunto':<12}" + "".join(f"{t:>16}" for t in titles)
    print("\n" + header)
    print("-" * len(header))
    for variant, data in report.items():
        for split in ("tune", "validation"):
            summary = data[split]
            if summary is None:
                continue
            cells = "".join(
                f"{'—':>16}" if summary[c] is None else f"{summary[c]:>16.3f}" for c in columns
            )
            print(f"{variant:<14}{split:<12}{cells}")
    reference = next(iter(report.values()))["all"]["reference_segments_per_min"]
    print(f"\nReferencia: {reference:.1f} segmentos/min, 0 fantasmas.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("variants", nargs="*", help=f"Por defecto, todas: {', '.join(VARIANTS)}")
    parser.add_argument("--limit", type=int, help="Solo los N primeros fragmentos (prueba rápida)")
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args()
    # Validación a mano: en Python 3.11, `choices` con nargs="*" rechaza la lista vacía.
    unknown = set(args.variants) - set(VARIANTS)
    if unknown:
        parser.error(f"variantes desconocidas: {', '.join(sorted(unknown))}")
    run(args.variants or list(VARIANTS), args.limit, args.out)


if __name__ == "__main__":
    main()
