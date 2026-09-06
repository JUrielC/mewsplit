#!/usr/bin/env bash
# Empaqueta el backend de Python como binario único para el sidecar de Tauri.
#
# Tauri exige que el nombre del binario termine en el target triple de Rust,
# y lo busca en desktop/src-tauri/binaries/.
#
# Los checkpoints NO se empaquetan: se descargan en la primera ejecución.
# Los pesos de BTC tienen una ambigüedad de licencia (ver README) y Demucs
# pesa 84 MB.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/backend/.venv/bin/python}"
TARGET_DIR="$ROOT/desktop/src-tauri/binaries"
NAME="mewsplit-backend"

TRIPLE="${TARGET_TRIPLE:-$(rustc -vV 2>/dev/null | sed -n 's/^host: //p')}"
if [[ -z "$TRIPLE" ]]; then
  echo "No se pudo determinar el target triple. Instala Rust o exporta TARGET_TRIPLE." >&2
  echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh" >&2
  exit 1
fi

echo "Empaquetando con PyInstaller para $TRIPLE..."
"$PYTHON" -m pip install --quiet pyinstaller

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/entrypoint.py" <<'PY'
from mewsplit.api import run

if __name__ == "__main__":
    run()
PY

(cd "$ROOT/backend" && "$PYTHON" -m PyInstaller \
  --onefile \
  --name "$NAME" \
  --distpath "$WORK/dist" \
  --workpath "$WORK/build" \
  --specpath "$WORK" \
  --collect-all audio_separator \
  --collect-all transformers \
  --collect-all librosa \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  "$WORK/entrypoint.py")

mkdir -p "$TARGET_DIR"
cp "$WORK/dist/$NAME" "$TARGET_DIR/$NAME-$TRIPLE"
chmod +x "$TARGET_DIR/$NAME-$TRIPLE"

echo "Sidecar en $TARGET_DIR/$NAME-$TRIPLE"
du -h "$TARGET_DIR/$NAME-$TRIPLE"
