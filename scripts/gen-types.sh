#!/usr/bin/env bash
# Genera shared/types.ts desde el esquema OpenAPI de FastAPI.
# No editar shared/types.ts a mano: se desincroniza del backend.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/backend/.venv/bin/python}"
TARGET="$ROOT/shared/types.ts"
SCHEMA="$(mktemp -t mewsplit-openapi).json"
trap 'rm -f "$SCHEMA"' EXIT

if [[ ! -x "$PYTHON" ]]; then
  echo "No existe el intérprete $PYTHON. Crea el entorno del backend primero:" >&2
  echo "  cd backend && uv venv .venv --python 3.11 && uv pip install -e '.[dev]'" >&2
  exit 1
fi

# Se importa la app en vez de levantar el servidor: no hace falta puerto ni token.
echo "Extrayendo el esquema OpenAPI..."
(cd "$ROOT/backend" && "$PYTHON" -c '
import json, sys
from mewsplit.api import app
json.dump(app.openapi(), open(sys.argv[1], "w"), indent=2)
' "$SCHEMA")

echo "Generando $TARGET..."
npx --yes openapi-typescript@7 "$SCHEMA" -o "$TARGET"

# La cabecera de openapi-typescript no dice de dónde sale el archivo.
TEMP="$(mktemp)"
{
  echo "// GENERADO POR scripts/gen-types.sh — NO EDITAR A MANO."
  echo "// Fuente: backend/mewsplit/api.py (esquema OpenAPI de FastAPI)."
  echo "// Regenerar tras cualquier cambio en los modelos de la API."
  echo
  cat "$TARGET"
} > "$TEMP"
mv "$TEMP" "$TARGET"

echo "Listo."
