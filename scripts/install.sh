#!/bin/sh
# Instala mewsplit en una Mac con Apple Silicon:
#
#   curl -fsSL https://raw.githubusercontent.com/JUrielC/mewsplit/master/scripts/install.sh | sh
#
# Por qué un comando y no un .dmg: macOS bloquea lo descargado con el
# navegador si no está firmado y notarizado por Apple. Lo que instala uv desde
# la terminal no lleva esa marca de cuarentena, y el acceso directo que se crea
# aquí tampoco, porque nace en la propia Mac. Así se abre con doble clic.
#
# Variables para probar sin publicar nada:
#   MEWSPLIT_WHEEL      ruta o URL del paquete (por defecto, la última release)
#   MEWSPLIT_APP_DIR    dónde crear mewsplit.app (por defecto, ~/Applications)
#   MEWSPLIT_NO_LAUNCH  no abrir mewsplit al terminar
set -eu

REPO="JUrielC/mewsplit"
APP_DIR="${MEWSPLIT_APP_DIR:-$HOME/Applications}"
APP="$APP_DIR/mewsplit.app"
LOG="$HOME/Library/Logs/mewsplit.log"

say() { printf '%s\n' "$*"; }
fail() { printf '\n%s\n' "$*" >&2; exit 1; }

say ""
say "Instalando mewsplit…"

[ "$(uname -s)" = "Darwin" ] || fail "mewsplit por ahora solo funciona en macOS."
[ "$(uname -m)" = "arm64" ] || fail "mewsplit necesita una Mac con Apple Silicon (M1 o posterior)."

# uv instala Python y todo lo demás sin tocar el Python del sistema.
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  say "→ Instalando uv (el instalador de Python de Astral)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
command -v uv >/dev/null 2>&1 || fail "No se pudo instalar uv. Revisa tu conexión a internet y vuelve a intentarlo."

WHEEL="${MEWSPLIT_WHEEL:-}"
if [ -z "$WHEEL" ]; then
  WHEEL="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | grep -o '"browser_download_url": *"[^"]*\.whl"' | head -1 | sed 's/.*"\(https[^"]*\)"/\1/')" \
    || true
  [ -n "$WHEEL" ] || fail "No se encontró ninguna versión publicada de mewsplit."
fi

# La versión sale del nombre del wheel (mewsplit-<versión>-py3-none-any.whl),
# sea ruta local o URL de la release: así el acceso directo no queda fijo.
VERSION="$(basename "$WHEEL" | sed -n 's/^mewsplit-\([^-]*\)-.*\.whl$/\1/p')"
VERSION="${VERSION:-0.0.0}"

say "→ Instalando mewsplit $VERSION. La primera vez baja ~1 GB (PyTorch); puede tardar unos minutos."
uv tool install --force --python 3.11 "$WHEEL"
# --color never: uv pinta la ruta de color aun capturada, y los códigos ANSI
# quedarían pegados a la ruta del ejecutable.
BIN="$(uv tool dir --bin --color never)/mewsplit"
[ -x "$BIN" ] || fail "La instalación terminó pero no se encuentra el comando mewsplit."

say "→ Creando el acceso directo en $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

cat > "$APP/Contents/MacOS/mewsplit" <<EOF
#!/bin/sh
# Lanza mewsplit sin terminal. La salida va a un log para poder diagnosticar.
mkdir -p "\$HOME/Library/Logs"
exec "$BIN" >> "$LOG" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/mewsplit"

# LSUIElement: sin icono en el Dock. El servidor corre en segundo plano, se
# ve la ventana del navegador, y se apaga solo al cerrarla (ver app.py).
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>mewsplit</string>
  <key>CFBundleDisplayName</key><string>mewsplit</string>
  <key>CFBundleIdentifier</key><string>app.mewsplit.launcher</string>
  <key>CFBundleExecutable</key><string>mewsplit</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
EOF

say ""
say "Listo. mewsplit está en tu carpeta de Aplicaciones: búscalo con Spotlight (⌘ + espacio)."
say "La primera canción tarda un poco más: se descargan los modelos (~100 MB)."
say "Para actualizarlo, vuelve a ejecutar este mismo comando."
say "Para desinstalarlo: uv tool uninstall mewsplit && rm -rf \"$APP\" ~/.cache/mewsplit"

if [ -z "${MEWSPLIT_NO_LAUNCH:-}" ]; then
  open "$APP"
fi
