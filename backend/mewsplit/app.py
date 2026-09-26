"""
app.py — mewsplit como aplicación local: un comando que arranca el backend,
sirve la interfaz ya compilada y la abre en una ventana.

Es el papel que hacía la cáscara de Tauri, en Python: así no hay un .app
descargado que macOS bloquee por no estar firmado. Lo instalado con uv desde
la terminal no lleva la marca de cuarentena, así que Gatekeeper no interviene.

Envoltorio de `api`, igual que `api` lo es de `core`: nada importa este módulo.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# La interfaz compilada (`next build` estático) se copia aquí al construir el
# paquete; en el repositorio no existe y está ignorada por git.
WEB_DIR = Path(__file__).resolve().parent / "web"

# Puerto fijo preferido: el origen incluye el puerto, y si cambiara en cada
# arranque el navegador olvidaría lo guardado en localStorage (el modo
# simples/completos, por ejemplo). Si está ocupado, cualquiera libre.
PREFERRED_PORT = 47820

# Dónde está sirviendo la instancia abierta, para que un segundo arranque
# reabra la ventana en vez de levantar otro servidor. Queda obsoleto cuando el
# proceso termina (uvicorn relanza la señal de cierre y no hay limpieza que
# alcance a correr); no importa, `_running_instance` pregunta a /health antes
# de fiarse.
STATE_FILE = Path.home() / ".cache" / "mewsplit" / "instance.json"

LOCAL_HOSTS = ["127.0.0.1", "localhost"]

# Desde el acceso directo no hay terminal que cerrar: sin esto el servidor
# quedaría vivo para siempre. La página avisa cada minuto que sigue abierta
# (keepAlive en frontend/lib/api.ts); tras este silencio, y sin ningún
# análisis en marcha, se apaga solo.
IDLE_SECONDS = 180

_last_seen = time.monotonic()


def build_app(token: str, web_dir: Path = WEB_DIR):
    """
    La API de siempre, más la interfaz servida desde el mismo origen.

    Envuelve a `api.app` sin modificarla: la misma API sigue sirviendo a
    `next dev`, a las pruebas y a un despliegue web tal cual.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import HTMLResponse
    from starlette.routing import Mount, Route
    from starlette.staticfiles import StaticFiles

    from mewsplit import api

    web_dir = web_dir.resolve()
    index = (web_dir / "index.html").read_text()
    # api "" = rutas relativas al mismo servidor. Mismo contrato que Tauri:
    # frontend/lib/api.ts lee window.__MEWSPLIT__ antes que cualquier otra cosa.
    config = json.dumps({"api": "", "token": token})
    page = index.replace("<head>", f"<head><script>window.__MEWSPLIT__ = {config};</script>", 1)

    async def home(request):
        _touch()
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    static = StaticFiles(directory=web_dir)

    async def dispatch(scope, receive, send):
        _touch()
        # Lo que exista como archivo de la interfaz se sirve estático; todo lo
        # demás (/health, /jobs, /docs…) es la API.
        target = (web_dir / scope["path"].lstrip("/")).resolve()
        if target.is_file() and target.is_relative_to(web_dir):
            await static(scope, receive, send)
        else:
            await api.app(scope, receive, send)

    return Starlette(
        routes=[Route("/", home), Mount("/", app=dispatch)],
        # La página lleva el token dentro. Sin esto, una web maliciosa podría
        # apuntar un dominio suyo a 127.0.0.1 (DNS rebinding) y leerla como
        # si fuera del mismo origen.
        middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)],
    )


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
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
    return sock


def _running_instance() -> str | None:
    """URL de una instancia que ya esté sirviendo, o None."""
    try:
        url = json.loads(STATE_FILE.read_text())["url"]
        with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
            return url if response.status == 200 else None
    except (OSError, ValueError, KeyError):
        return None


def open_window(url: str) -> None:
    """
    En una ventana propia si hay Chrome (modo app, sin barra de navegador);
    si no, en el navegador por defecto.
    """
    chrome = Path("/Applications/Google Chrome.app")
    if sys.platform == "darwin" and chrome.exists():
        subprocess.run(["open", "-na", str(chrome), "--args", f"--app={url}"], check=False)
    else:
        webbrowser.open(url)


def say(message: str) -> None:
    # flush: desde el acceso directo no hay terminal y la salida va a un
    # archivo de log, que sin esto no se escribe hasta llenar el búfer.
    print(message, flush=True)


def main() -> None:
    if not (WEB_DIR / "index.html").exists():
        sys.exit(
            "No se encontró la interfaz compilada. Si estás en el repositorio, "
            "genera el paquete con scripts/build-release.sh."
        )

    browser = not os.environ.get("MEWSPLIT_NO_BROWSER")

    existing = _running_instance()
    if existing:
        say(f"mewsplit ya está abierto en {existing}")
        if browser:
            open_window(existing)
        return

    import uvicorn

    from mewsplit import api

    sock = _bind(int(os.environ.get("MEWSPLIT_APP_PORT", PREFERRED_PORT)))
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"

    server = uvicorn.Server(uvicorn.Config(build_app(api.TOKEN), log_level="warning"))

    def open_when_ready() -> None:
        while not server.started:
            time.sleep(0.1)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({"url": url, "pid": os.getpid()}))
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
