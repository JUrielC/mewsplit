#!/usr/bin/env bash
# Construye el paquete que instala scripts/install.sh: un wheel de Python con
# la interfaz ya compilada dentro, para que quien lo instala no necesite Node.
#
# Salida: dist/mewsplit-<versión>-py3-none-any.whl
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB="$ROOT/backend/mewsplit/web"

echo "Compilando la interfaz estática…"
# MEWSPLIT_STATIC=1: export estático sin token incrustado. El token llega en
# tiempo de ejecución por window.__MEWSPLIT__ (ver backend/mewsplit/app.py).
(cd "$ROOT/frontend" && MEWSPLIT_STATIC=1 npm run build)

rm -rf "$WEB"
cp -R "$ROOT/frontend/out" "$WEB"

# La licencia exige que quien reciba una copia reciba también sus términos y
# el `Required Notice`. hatchling mete en el wheel el LICENSE de backend/;
# el original vive en la raíz, así que se copia (la copia está ignorada).
cp "$ROOT/LICENSE" "$ROOT/backend/LICENSE"

echo "Construyendo el wheel…"
rm -rf "$ROOT/dist"
(cd "$ROOT/backend" && uv build --wheel --out-dir "$ROOT/dist")

WHEEL="$(ls "$ROOT"/dist/*.whl)"
# Si la interfaz no entró, el comando `mewsplit` arrancaría sin nada que servir.
# Sin -q: grep -q corta la tubería, unzip recibe SIGPIPE y pipefail lo da por fallo.
unzip -l "$WHEEL" | grep "mewsplit/web/index.html" >/dev/null || {
  echo "El wheel no incluye la interfaz (mewsplit/web/index.html)." >&2
  exit 1
}

echo "Listo: $WHEEL ($(du -h "$WHEEL" | cut -f1))"
