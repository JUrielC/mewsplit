#!/usr/bin/env bash
# Construye el paquete que instala scripts/install.sh: un wheel de Python con
# la interfaz ya compilada y la ventana nativa de macOS dentro, para que quien
# lo instala no necesite Node ni Xcode.
#
# Salida: dist/mewsplit-<versión>-py3-none-macosx_12_0_arm64.whl
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB="$ROOT/backend/mewsplit/web"

echo "Compilando la interfaz estática…"
# MEWSPLIT_STATIC=1: export estático sin token incrustado. El token llega en
# tiempo de ejecución por window.__MEWSPLIT__ (ver backend/mewsplit/app.py).
(cd "$ROOT/frontend" && MEWSPLIT_STATIC=1 npm run build)

rm -rf "$WEB"
cp -R "$ROOT/frontend/out" "$WEB"

echo "Compilando la ventana nativa…"
# Basta con las Command Line Tools: si Xcode está instalado pero sin aceptar
# su licencia, xcrun falla, y ahí se usan ellas directamente.
if ! xcrun swiftc --version >/dev/null 2>&1; then
  export DEVELOPER_DIR=/Library/Developer/CommandLineTools
fi
mkdir -p "$ROOT/backend/mewsplit/bin"
xcrun swiftc -O -target arm64-apple-macos12 \
  "$ROOT/native/macos/main.swift" -o "$ROOT/backend/mewsplit/bin/mewsplit-window"

# La licencia exige que quien reciba una copia reciba también sus términos y
# el `Required Notice`. hatchling mete en el wheel el LICENSE de backend/;
# el original vive en la raíz, así que se copia (la copia está ignorada).
cp "$ROOT/LICENSE" "$ROOT/backend/LICENSE"

echo "Construyendo el wheel…"
rm -rf "$ROOT/dist"
(cd "$ROOT/backend" && uv build --wheel --out-dir "$ROOT/dist")

# Lleva un binario de macOS ARM: marcarlo como `any` dejaría que uv lo
# instalara en cualquier sistema y fallara al abrir la ventana.
uvx --quiet --from wheel wheel tags --remove --platform-tag macosx_12_0_arm64 "$ROOT"/dist/*.whl >/dev/null

WHEEL="$(ls "$ROOT"/dist/*.whl)"
# Si la interfaz no entró, el comando `mewsplit` arrancaría sin nada que servir.
# Sin -q: grep -q corta la tubería, unzip recibe SIGPIPE y pipefail lo da por fallo.
for required in mewsplit/web/index.html mewsplit/bin/mewsplit-window; do
  unzip -l "$WHEEL" | grep "$required" >/dev/null || {
    echo "El wheel no incluye $required." >&2
    exit 1
  }
done

echo "Listo: $WHEEL ($(du -h "$WHEEL" | cut -f1))"
