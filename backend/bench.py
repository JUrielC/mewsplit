"""
bench.py — comparativa htdemucs vs htdemucs_ft, y acordes sobre original vs instrumental.

Consume las funciones sueltas de `separation` y `chords` en vez de `analyze()`,
porque necesita otro orden de etapas. Ese es el patrón correcto cuando el
pipeline por defecto no encaja.

Resultado en `bench_output/bench.json`; los stems quedan separados por modelo
en subcarpetas para poder escucharlos.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from mewsplit.chords import chord_at, condense, detect_chords
from mewsplit.core import Stopwatch, get_device, get_duration
from mewsplit.separation import build_instrumental, separate

MODELS = {
    "htdemucs": "htdemucs.yaml",
    "htdemucs_ft": "htdemucs_ft.yaml",
}


def build_timeline(duration: float, series: dict[str, list[dict]], step: float = 10.0) -> list[dict]:
    """Tabla alineada cada `step` segundos para comparar las series lado a lado."""
    rows = []
    current = 0.0
    while current < duration:
        end = min(current + step, duration)
        middle = current + (end - current) / 2.0
        row = {"range": f"{int(current // 60):02d}:{int(current % 60):02d}-{int(end // 60):02d}:{int(end % 60):02d}"}
        row.update({key: chord_at(chords, middle) for key, chords in series.items()})
        rows.append(row)
        current += step
    return rows


def count_matches(rows: list[dict], a: str, b: str) -> tuple[int, int]:
    equal = sum(1 for row in rows if row[a] == row[b])
    return equal, len(rows)


def run(audio_path: str | Path, base_out: str | Path = "./bench_output") -> dict:
    audio_path = Path(audio_path).resolve()
    base_out = Path(base_out).resolve()
    base_out.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        raise FileNotFoundError(f"No se encontró el audio: {audio_path}")

    duration = get_duration(audio_path) or 0.0
    device = get_device()

    print("=" * 78)
    print(f"BENCHMARK · {audio_path.name}")
    print(f"Duración: {duration:.2f}s ({int(duration // 60):02d}:{duration % 60:04.1f}) · Dispositivo: {device.upper()}")
    print("=" * 78)

    performance: dict[str, dict] = {}
    series: dict[str, list[dict]] = {}

    # Acordes sobre el audio original: una sola vez, no depende del modelo de separación.
    print("\nAcordes [audio original]")
    series["original"] = detect_chords(audio_path, timer=Stopwatch())

    for name, model_file in MODELS.items():
        print(f"\n{name} ({model_file})")
        print("-" * 60)
        clock = Stopwatch()
        output_dir = base_out / name
        output_dir.mkdir(parents=True, exist_ok=True)

        started = time.perf_counter()
        stems = separate(audio_path, output_dir, model=model_file, timer=clock)
        separation_time = round(time.perf_counter() - started, 2)

        instrumental = build_instrumental(stems, output_dir, timer=clock)
        series[f"{name}_instrumental"] = detect_chords(instrumental or audio_path, timer=clock)

        performance[name] = {
            "model": model_file,
            "separation_seconds": separation_time,
            "rtf": round(separation_time / duration, 4) if duration else None,
            "realtime_factor": round(duration / separation_time, 2) if separation_time else None,
            "stages": clock.timings,
            "stems_dir": str(output_dir),
        }

    rows = build_timeline(duration, series)

    standard = performance["htdemucs"]["separation_seconds"]
    finetuned = performance["htdemucs_ft"]["separation_seconds"]

    data = {
        "audio": {"path": str(audio_path), "filename": audio_path.name, "duration_seconds": duration},
        "device": device,
        "performance": performance,
        "comparison": {
            "htdemucs_vs_ft": round(finetuned / standard, 2) if standard else None,
            "seconds_saved": round(finetuned - standard, 2),
        },
        "chords": {
            key: {"total": len(value), "summary": condense(value)[:8], "segments": value}
            for key, value in series.items()
        },
        "timeline": rows,
        "original_vs_instrumental_agreement": {
            key: "%d/%d" % count_matches(rows, "original", key)
            for key in series
            if key != "original"
        },
    }

    target = base_out / "bench.json"
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    print("\n" + "=" * 78)
    print(f"{'Métrica':<34} | {'htdemucs':<16} | {'htdemucs_ft':<16}")
    print("-" * 78)
    print(f"{'Separación (s)':<34} | {standard:<16.2f} | {finetuned:<16.2f}")
    for key in ("rtf", "realtime_factor"):
        print(f"{key:<34} | {str(performance['htdemucs'][key]):<16} | {str(performance['htdemucs_ft'][key]):<16}")
    print("-" * 78)
    print(f"htdemucs es {data['comparison']['htdemucs_vs_ft']}x más rápido ({data['comparison']['seconds_saved']}s ahorrados)")

    print("\nCoincidencia de acordes contra el audio original (muestreo cada 10s):")
    for key, value in data["original_vs_instrumental_agreement"].items():
        print(f"  {key:<26} {value} tramos idénticos")

    print(f"\nResultado completo: {target}\n")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Comparativa de modelos de separación y acordes.")
    parser.add_argument("audio", help="Ruta al archivo de audio")
    parser.add_argument("--out", default="./bench_output", help="Directorio de salida (default: ./bench_output)")
    args = parser.parse_args()

    if not Path(args.audio).exists():
        print(f"Error: no existe {args.audio}", file=sys.stderr)
        sys.exit(1)

    run(args.audio, args.out)


if __name__ == "__main__":
    main()
