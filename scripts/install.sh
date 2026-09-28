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
#   MEWSPLIT_WHEEL      ruta o URL del paquete (por defecto, la última release;
#                       si aún no hay ninguna definitiva, la pre-release más nueva)
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

# Primer .whl de una respuesta de la API de releases de GitHub.
first_wheel() {
  grep -o '"browser_download_url": *"[^"]*\.whl"' | head -1 | sed 's/.*"\(https[^"]*\)"/\1/'
}

WHEEL="${MEWSPLIT_WHEEL:-}"
if [ -z "$WHEEL" ]; then
  # /releases/latest nunca devuelve una pre-release. Mientras no haya ninguna
  # versión definitiva, se cae a la lista completa, que viene de la más nueva
  # a la más vieja e incluye las pre-releases.
  WHEEL="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null | first_wheel || true)"
  if [ -z "$WHEEL" ]; then
    WHEEL="$(curl -fsSL "https://api.github.com/repos/$REPO/releases?per_page=10" 2>/dev/null | first_wheel || true)"
  fi
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

# La ventana nativa viaja dentro del paquete; se copia al acceso directo para
# que mewsplit tenga su propio icono en el Dock y en Cmd+Tab.
PYTHON="$(uv tool dir --color never)/mewsplit/bin/python"
WINDOW="$("$PYTHON" -c 'import mewsplit.app as a; print(a.NATIVE_WINDOW if a.NATIVE_WINDOW.exists() else "")' 2>/dev/null || true)"

if [ -n "$WINDOW" ]; then
  cp "$WINDOW" "$APP/Contents/MacOS/mewsplit"
  # MewsplitCommand: la ventana arranca este comando y lo detiene al cerrarse.
  EXTRA_KEYS="  <key>MewsplitCommand</key><string>$BIN</string>
  <key>NSHighResolutionCapable</key><true/>"
else
  # Paquete sin ventana nativa: un script que abre mewsplit en el navegador.
  # LSUIElement: sin icono en el Dock; el servidor se apaga solo al cerrar la
  # ventana del navegador (ver app.py).
  cat > "$APP/Contents/MacOS/mewsplit" <<EOF
#!/bin/sh
# Lanza mewsplit sin terminal. La salida va a un log para poder diagnosticar.
mkdir -p "\$HOME/Library/Logs"
exec "$BIN" >> "$LOG" 2>&1
EOF
  EXTRA_KEYS="  <key>LSUIElement</key><true/>"
fi
chmod +x "$APP/Contents/MacOS/mewsplit"

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
  <key>LSMinimumSystemVersion</key><string>12.0</string>
$EXTRA_KEYS
</dict>
</plist>
EOF

# Firma ad-hoc del paquete completo (no requiere cuenta de Apple; codesign
# viene con macOS). El binario trae la firma del enlazador, pensada para un
# ejecutable suelto: dentro de un .app, macOS espera una que selle también el
# Info.plist, y sin ella `codesign -v` da el paquete por inválido.
codesign --force --sign - "$APP" >/dev/null 2>&1 || true

say ""
say "Listo. mewsplit está en tu carpeta de Aplicaciones: búscalo con Spotlight (⌘ + espacio)."
say "La primera canción tarda un poco más: se descargan los modelos (~100 MB)."
say "Para actualizarlo, vuelve a ejecutar este mismo comando."
say "Para desinstalarlo: uv tool uninstall mewsplit && rm -rf \"$APP\" ~/.cache/mewsplit"

if [ -z "${MEWSPLIT_NO_LAUNCH:-}" ]; then
  open "$APP"
fi
