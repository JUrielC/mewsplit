"""
Genera latest.json, el manifiesto que mewsplit consulta para saber si hay una
versión nueva, con la URL y la huella SHA-256 de cada archivo de la release.

Lo corre .github/workflows/release.yml; backend/mewsplit/updates.py lo lee.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--base-url", required=True, help="URL donde quedan publicados los archivos")
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--notes-file", required=True, help="Un cambio por línea")
    parser.add_argument("--output", required=True)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    notes = Path(args.notes_file).read_text(encoding="utf-8").splitlines()
    manifest = {
        "version": args.version,
        "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "release_url": args.release_url,
        "notes": [line.strip() for line in notes if line.strip()],
        "assets": {
            Path(f).name: {
                "url": f"{args.base_url.rstrip('/')}/{Path(f).name}",
                "sha256": hashlib.sha256(Path(f).read_bytes()).hexdigest(),
            }
            for f in args.files
        },
    }
    Path(args.output).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
