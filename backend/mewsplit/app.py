"""
app.py — mewsplit como aplicación local: un comando que arranca el backend,
sirve la interfaz ya compilada y la abre en una ventana.

Es el papel que hacía la cáscara de Tauri, en Python: así no hay un .app
descargado que macOS bloquee por no estar firmado. Lo instalado con uv desde
la terminal no lleva la marca de cuarentena, así que Gatekeeper no interviene,
y en Windows el acceso directo lo crea el instalador, así que SmartScreen
tampoco.

La ventana: en macOS la nativa (native/macos/main.swift); en Windows una de
WebView2 (pywebview), o el modo app de Edge o Chrome si no hay WebView2; si
nada de eso está, el navegador.

Envoltorio de `api`, igual que `api` lo es de `core`: nada importa este módulo.
"""

from __future__ import annotations

import asyncio
import ctypes
import html
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

from mewsplit.paths import CACHE_DIR

# La interfaz compilada (`next build` estático) se copia aquí al construir el
# paquete; en el repositorio no existe y está ignorada por git.
WEB_DIR = Path(__file__).resolve().parent / "web"

# La ventana nativa de macOS (native/macos/main.swift), compilada por
# build-release.sh. Con ella mewsplit tiene su propio icono en el Dock en vez
# de ser una ventana más del navegador. Si no está, se usa el navegador.
NATIVE_WINDOW = Path(__file__).resolve().parent / "bin" / "mewsplit-window"

# Debe coincidir con el identificador que scripts/install.ps1 pone en los accesos directos.
WINDOWS_APP_ID = "app.mewsplit.launcher"

# Contrato con la ventana nativa: cuando es ella quien arranca el servidor
# (MEWSPLIT_NATIVE=1), espera esta línea en stdout para saber qué cargar y si
# el servidor es suyo (lo detiene al cerrarse) o ya existía (no lo toca).
READY_PREFIX = "MEWSPLIT_APP_READY"

# Puerto fijo preferido: el origen incluye el puerto, y si cambiara en cada
# arranque el navegador olvidaría lo guardado en localStorage (el modo
# simples/completos, por ejemplo). Si está ocupado, cualquiera libre.
PREFERRED_PORT = 47820

# Dónde está sirviendo la instancia abierta, para que un segundo arranque
# reabra la ventana en vez de levantar otro servidor. Queda obsoleto cuando el
# proceso termina (uvicorn relanza la señal de cierre y no hay limpieza que
# alcance a correr); no importa, `_running_instance` pregunta a /health antes
# de fiarse.
STATE_FILE = CACHE_DIR / "instance.json"

# Abierto con pythonw.exe (el acceso directo de Windows) no hay consola.
LOG_FILE = CACHE_DIR / "mewsplit.log"

LOCAL_HOSTS = ["127.0.0.1", "localhost"]

# Desde el acceso directo no hay terminal que cerrar: sin esto el servidor
# quedaría vivo para siempre. La página avisa cada minuto que sigue abierta
# (keepAlive en frontend/lib/api.ts); tras este silencio, y sin ningún
# análisis en marcha, se apaga solo.
IDLE_SECONDS = 180

_last_seen = time.monotonic()
# La ventana de WebView2, para traerla al frente si se vuelve a abrir mewsplit.
_window = None


def message_page(text: str) -> str:
    """Lo que muestra la ventana de Windows antes de que cargue la interfaz."""
    return (
        '<!doctype html><html lang="es"><body style="margin:0;height:100vh;display:flex;'
        "align-items:center;justify-content:center;padding:0 48px;background:#101114;"
        'color:#a8acb6;font:12px system-ui,sans-serif;letter-spacing:.14em">'
        f"{html.escape(text)}</body></html>"
    )


def _ensure_stdio() -> None:
    """Con pythonw.exe, stdout y stderr son None y el primer print() o log de uvicorn revienta."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def build_app(token: str, web_dir: Path = WEB_DIR):
    """
    La API de siempre, más la interfaz servida desde el mismo origen.

    Envuelve a `api.app` sin modificarla: la misma API sigue sirviendo a
    `next dev`, a las pruebas y a un despliegue web tal cual.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import HTMLResponse, Response
    from starlette.routing import Mount, Route
    from starlette.staticfiles import StaticFiles

    from mewsplit import api

    web_dir = web_dir.resolve()
    index = (web_dir / "index.html").read_text(encoding="utf-8")
    # api "" = rutas relativas al mismo servidor. Mismo contrato que Tauri:
    # frontend/lib/api.ts lee window.__MEWSPLIT__ antes que cualquier otra cosa.
    config = json.dumps({"api": "", "token": token})
    page = index.replace("<head>", f"<head><script>window.__MEWSPLIT__ = {config};</script>", 1)

    async def home(request):
        _touch()
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    async def show_window(request):
        given = request.headers.get("X-Mewsplit-Token", "")
        if not secrets.compare_digest(given, token) or _window is None:
            return Response(status_code=404)
        await asyncio.to_thread(_bring_window_to_front)
        return Response(status_code=204)

    static = StaticFiles(directory=web_dir)

    async def dispatch(scope, receive, send):
        _touch()
        # Lo que exista como archivo de la interfaz se sirve estático; todo lo
        # demás (/health, /projects, /docs…) es la API.
        target = (web_dir / scope["path"].lstrip("/")).resolve()
        if target.is_file() and target.is_relative_to(web_dir):
            await static(scope, receive, send)
        else:
            await api.app(scope, receive, send)

    return Starlette(
        routes=[
            Route("/", home),
            Route("/window/show", show_window, methods=["POST"]),
            Mount("/", app=dispatch),
        ],
        # La página lleva el token dentro. Sin esto, una web maliciosa podría
        # apuntar un dominio suyo a 127.0.0.1 (DNS rebinding) y leerla como
        # si fuera del mismo origen.
        middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)],
    )


def _bring_window_to_front() -> None:
    _window.restore()
    _window.show()


def _touch() -> None:
    global _last_seen
    _last_seen = time.monotonic()


def _shutdown_when_idle(server, idle_seconds: float = IDLE_SECONDS, poll: float = 5) -> None:
    from mewsplit import api

    while not server.should_exit:
        time.sleep(poll)
        if time.monotonic() - _last_seen > idle_seconds and not api.busy():
            say("Ninguna ventana abierta desde hace un rato: mewsplit se cierra.")
            server.should_exit = True


def _bind(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # En Windows SO_REUSEADDR deja que dos procesos escuchen en el mismo puerto:
    # el segundo mewsplit se quedaría con el 47820 en vez de caer al libre.
    if sys.platform != "win32":
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
    # La ventana puede pedir la página antes de que uvicorn arranque: escuchando
    # ya, la conexión espera en cola en vez de ser rechazada.
    sock.listen()
    return sock


def _running_instance() -> dict | None:
    """La instancia que ya esté sirviendo ({"url", "token"}), o None."""
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        with urllib.request.urlopen(f"{state['url']}/health", timeout=1) as response:
            return state if response.status == 200 else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _remember(url: str, token: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"url": url, "token": token, "pid": os.getpid()}))


def _show_existing_window(state: dict) -> bool:
    """Pide a la instancia abierta que traiga su ventana al frente; False si no tiene una."""
    if sys.platform != "win32":
        return False
    # Windows solo deja pasar al frente la ventana de otro proceso si lo
    # autoriza este, que es el que acaba de abrir el usuario.
    ctypes.windll.user32.AllowSetForegroundWindow(-1)
    request = urllib.request.Request(
        f"{state['url']}/window/show",
        method="POST",
        headers={"X-Mewsplit-Token": state.get("token", "")},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status == 204
    except OSError:
        return False


# Navegadores basados en Chromium: aceptan --app=URL, una ventana propia sin
# barra de direcciones que se siente como una aplicación. Safari y Firefox no
# tienen modo app; con ellos se abre una pestaña normal.
APP_MODE_BROWSERS = {
    "com.google.chrome",
    "com.google.chrome.beta",
    "com.google.chrome.canary",
    "com.microsoft.edgemac",
    "com.brave.browser",
    "com.vivaldi.vivaldi",
    "com.operasoftware.opera",
    "org.chromium.chromium",
}

LAUNCH_SERVICES = (
    Path.home()
    / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
)


def default_browser(handlers: list[dict]) -> str:
    """
    Identificador del navegador por defecto según los manejadores de
    LaunchServices: el que abre `https`. Sin ninguno asignado, macOS usa
    Safari, que es el de fábrica.
    """
    for handler in handlers:
        if handler.get("LSHandlerURLScheme") == "https" and handler.get("LSHandlerRoleAll"):
            return handler["LSHandlerRoleAll"].lower()
    return "com.apple.safari"


def _read_handlers() -> list[dict]:
    import plistlib

    try:
        return plistlib.loads(LAUNCH_SERVICES.read_bytes()).get("LSHandlers", [])
    except (OSError, plistlib.InvalidFileException):
        return []


def _windows_app_browser() -> str | None:
    """Edge (viene con Windows) o Chrome, para abrir en modo app sin barra de direcciones."""
    candidates = [
        shutil.which("msedge"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        shutil.which("chrome"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    return next((path for path in candidates if path and Path(path).is_file()), None)


def ready_line(url: str, owner: str) -> str:
    return f"{READY_PREFIX} url={url} owner={owner}"


def open_window(url: str) -> None:
    """
    En la ventana nativa si el paquete la trae. Si no, en el navegador por
    defecto del usuario: en modo app si es de la familia Chromium, y en una
    pestaña si no.
    """
    if sys.platform == "darwin" and NATIVE_WINDOW.exists():
        # Solo ventana: el servidor lo lleva este proceso, no ella.
        subprocess.Popen([str(NATIVE_WINDOW), url])
        return
    if sys.platform == "darwin":
        browser = default_browser(_read_handlers())
        if browser in APP_MODE_BROWSERS:
            # -n: aunque el navegador ya esté abierto, así recibe --app.
            subprocess.run(["open", "-nb", browser, "--args", f"--app={url}"], check=False)
            return
    if sys.platform == "win32" and (browser := _windows_app_browser()):
        subprocess.Popen([browser, f"--app={url}", "--new-window"])
        return
    webbrowser.open(url)


def say(message: str) -> None:
    # flush: desde el acceso directo no hay terminal y la salida va a un
    # archivo de log, que sin esto no se escribe hasta llenar el búfer.
    print(message, flush=True)


def _create_server():
    """El servidor con la interfaz. Importa PyTorch: tarda unos segundos."""
    import uvicorn

    from mewsplit import api

    config = uvicorn.Config(build_app(api.TOKEN), log_level="warning")
    return uvicorn.Server(config), api.TOKEN


def _run_in_webview(sock: socket.socket, url: str) -> bool:
    """
    Windows: abre mewsplit en una ventana de WebView2 y apaga el servidor al
    cerrarla. False si WebView2 no está, para usar el modo app de Edge o Chrome.
    """
    try:
        import webview
        from webview.platforms import winforms
    except Exception:
        traceback.print_exc()
        return False
    # Sin WebView2, pywebview usa en silencio el motor de Internet Explorer, que no puede con la interfaz.
    if winforms.renderer != "edgechromium":
        return False

    # Sin identificador propio, la barra de tareas agrupa la ventana con Python y muestra su icono.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    global _window
    # La ventana sale antes de cargar PyTorch: si no, el doble clic no daría señales durante segundos.
    _window = webview.create_window(
        "mewsplit",
        html=message_page("arrancando mewsplit…"),
        width=1280,
        height=820,
        min_size=(900, 600),
        background_color="#101114",
    )
    running = []

    def boot() -> None:
        try:
            server, token = _create_server()
            running.append(server)
            thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
            thread.start()
            while not server.started and thread.is_alive():
                time.sleep(0.1)
            if not server.started:
                raise RuntimeError("el servidor no arrancó")
            _remember(url, token)
            _window.load_url(url)
        except Exception as error:
            traceback.print_exc()
            _window.load_html(message_page(f"mewsplit no pudo arrancar: {error}. revisa {LOG_FILE}"))

    # private_mode=False y una carpeta propia: sin ellas localStorage se borra al cerrar.
    webview.start(
        boot,
        gui="edgechromium",
        private_mode=False,
        storage_path=str(CACHE_DIR / "webview"),
    )
    for server in running:
        server.should_exit = True
    return True


def main() -> None:
    _ensure_stdio()
    if not (WEB_DIR / "index.html").exists():
        sys.exit(
            "No se encontró la interfaz compilada. Si estás en el repositorio, "
            "genera el paquete con scripts/build-release.sh."
        )

    native = bool(os.environ.get("MEWSPLIT_NATIVE"))
    browser = not native and not os.environ.get("MEWSPLIT_NO_BROWSER")

    existing = _running_instance()
    if existing:
        if native:
            say(ready_line(existing["url"], "existing"))
        else:
            say(f"mewsplit ya está abierto en {existing['url']}")
        if browser and not _show_existing_window(existing):
            open_window(existing["url"])
        return

    sock = _bind(int(os.environ.get("MEWSPLIT_APP_PORT", PREFERRED_PORT)))
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"

    if browser and sys.platform == "win32" and _run_in_webview(sock, url):
        sys.stdout.flush()
        sys.stderr.flush()
        # Al salir normal, Python descargaría .NET (pywebview) y tardaría varios segundos sin nada que cerrar.
        os._exit(0)

    server, token = _create_server()

    def open_when_ready() -> None:
        while not server.started:
            time.sleep(0.1)
        _remember(url, token)
        if native:
            say(ready_line(url, "new"))
            return
        say(f"mewsplit está listo en {url}")
        minutes = IDLE_SECONDS // 60
        say(f"Se cierra solo {minutes} minutos después de cerrar su ventana (o Ctrl+C aquí).")
        if browser:
            open_window(url)

    threading.Thread(target=open_when_ready, daemon=True).start()
    threading.Thread(target=_shutdown_when_idle, args=(server,), daemon=True).start()
    say("Arrancando mewsplit…")
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
