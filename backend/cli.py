"""
cli.py — entrada de terminal. Envoltorio sobre `mewsplit.core`.

Guarda `analysis.json` en el directorio de salida y muestra el desglose
de tiempos por etapa.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mewsplit.chords import condense
from mewsplit.core import DEFAULT_MODEL, SIX_STEM_MODEL, analyze


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mewsplit",
        description="Separación de stems + detección de acordes.",
    )
    parser.add_argument("audio", help="Archivo de audio de entrada (WAV, MP3, FLAC...)")
    parser.add_argument("--out", default="./output", help="Directorio de salida (default: ./output)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Modelo de separación (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--6-stems",
        dest="six_stems",
        action="store_true",
        help=f"Usar {SIX_STEM_MODEL} (añade guitarra y piano, degrada los 4 base)",
    )
    parser.add_argument("--skip-chords", action="store_true", help="Omitir la detección de acordes")
    parser.add_argument(
        "--simple-chords",
        action="store_true",
        help="Solo tríadas mayores y menores, sin séptimas ni otras calidades",
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Caché de checkpoints (por defecto la de audio-separator, en /tmp)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    model = SIX_STEM_MODEL if args.six_stems else args.model

    analysis = analyze(
        audio_path=args.audio,
        output_dir=args.out,
        model=model,
        with_chords=not args.skip_chords,
        large_vocabulary=not args.simple_chords,
        model_cache_dir=args.model_dir,
    )

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "analysis.json"
    target.write_text(json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False))

    print("\n" + "=" * 52)
    print("TIEMPOS POR ETAPA (s)")
    print("=" * 52)
    for stage, seconds in analysis.timings.items():
        if stage != "total":
            print(f"  · {stage.ljust(28)}: {seconds:6.2f}")
    print("-" * 52)
    print(f"  · {'TOTAL'.ljust(28)}: {analysis.timings.get('total', 0.0):6.2f}")
    print("=" * 52)

    if analysis.chords:
        sequence = condense([{"chord": c.chord} for c in analysis.chords])
        print(f"\nAcordes ({len(analysis.chords)} segmentos): {' → '.join(sequence[:10])}")

    print(f"\nStems en:  {out_dir}")
    print(f"Análisis:  {target}")


if __name__ == "__main__":
    main()
