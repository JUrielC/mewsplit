"""
updates.py — avisar de versiones nuevas e instalarlas desde la app.

Cada release publica latest.json (scripts/update_manifest.py) con la versión,
los cambios y la URL y huella SHA-256 de cada archivo. Para actualizar se
descargan el wheel y el instalador, se verifican, y un script aparte espera a
que mewsplit se cierre para correr el mismo instalador que usa la gente
(install.sh / install.ps1), que deja la versión nueva instalada y abierta.

Envoltorio, como `projects`: `core` no sabe que existe. Lo usa `api`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from mewsplit import __version__
from mewsplit.paths import CACHE_DIR, DATA_DIR

# Queda grabada en cada copia instalada: tiene que ser una URL que se controle a
# largo plazo. Un dominio propio servido por GitHub Pages (.github/workflows/site.yml)
# permite cambiar de hosting sin dejar sin actualizaciones a nadie.
MANIFEST_URL = os.environ.get(
    "MEWSPLIT_UPDATE_URL", "https://mewsplit-releases.jurielc.com/updates/latest.json"
)

STATE_FILE = DATA_DIR / "updates.json"

# Debe coincidir con main.swift: la ventana de macOS se cierra en vez de mostrar un error.
UPDATE_EXIT_CODE = 75

# Debe coincidir con CFBundleIdentifier en scripts/install.sh.
MACOS_BUNDLE_ID = "app.mewsplit.launcher"

INSTALL_COMMANDS = {
    "darwin": "curl -fsSL https://github.com/JUrielC/mewsplit/releases/latest/download/install.sh | sh",
    "win32": "irm https://github.com/JUrielC/mewsplit/releases/latest/download/install.ps1 | iex",
}

UPDATE_ERRORS = {
    "not_installer_copy": "Esta copia no se instaló con el instalador de mewsplit: actualízala con git pull.",
    "unsupported_platform": "Actualizar desde la app solo funciona en macOS y Windows.",
    "open_from_icon": "Abre mewsplit desde su icono para actualizarlo desde la app.",
    "busy": "Hay una canción descargándose o analizándose: actualiza cuando termine.",
    "check_failed": "No se pudo comprobar si hay una versión nueva. Revisa tu conexión.",
    "release_incomplete": "La versión publicada no trae los archivos para actualizar desde la app.",
    "checksum_mismatch": "La descarga no coincide con la huella publicada: se canceló la actualización.",
    "already_latest": "Ya tienes la versión más reciente.",
    "download_failed": "No se pudo descargar la versión nueva. Revisa tu conexión.",
}


class UpdateError(Exception):
    def __init__(self, code: str):
        super().__init__(UPDATE_ERRORS[code])
        self.code = code


# Se consulta una vez por apertura de la app, no en cada visita a la pantalla de proyectos.
_latest: dict[str, Any] | None = None
_checked = False


def parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": f"mewsplit/{__version__}"})


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(**changes: Any) -> None:
    state = {**_load_state(), **changes}
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(STATE_FILE)


def fetch_latest_release(timeout: float = 6.0) -> dict[str, Any] | None:
    """El manifiesto de la última versión publicada; None si todavía no hay ninguna."""
    try:
        with urllib.request.urlopen(_request(MANIFEST_URL), timeout=timeout) as response:
            manifest = json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), str):
        raise ValueError("Manifiesto de actualizaciones inválido.")
    return {
        "version": manifest["version"],
        "notes": manifest.get("notes", []),
        "url": manifest.get("release_url"),
        "published_at": manifest.get("published_at"),
        "assets": manifest.get("assets", {}),
    }


def self_update_unavailable_reason() -> str | None:
    """None si esta copia puede actualizarse sola; si no, el código del motivo."""
    # uv instala cada herramienta en <tools>/<nombre>: así se sabe que vino del instalador.
    prefix = Path(sys.prefix)
    if prefix.name != "mewsplit" or prefix.parent.name != "tools":
        return "not_installer_copy"
    if sys.platform not in INSTALL_COMMANDS:
        return "unsupported_platform"
    # Desde la terminal, el proceso padre es la shell: el actualizador esperaría a que se cerrara.
    if sys.platform == "darwin" and os.environ.get("MEWSPLIT_NATIVE") != "1":
        return "open_from_icon"
    return None


def check_for_updates(force: bool = False) -> dict[str, Any]:
    global _latest, _checked

    reason = self_update_unavailable_reason()
    info: dict[str, Any] = {
        "current_version": __version__,
        "platform": sys.platform,
        "can_self_update": reason is None,
        "self_update_unavailable_reason": UPDATE_ERRORS[reason] if reason else None,
        "install_command": INSTALL_COMMANDS.get(sys.platform),
    }

    state = _load_state()
    last_seen = state.get("last_seen_version")
    if last_seen is None:
        _save_state(last_seen_version=__version__)
    elif last_seen != __version__:
        info["updated_from"] = last_seen

    if force or not _checked:
        try:
            _latest = fetch_latest_release()
        except (OSError, ValueError):
            info["error"] = UPDATE_ERRORS["check_failed"]
            return info
        _checked = True

    if not _latest:
        return info
    info.update(
        latest_version=_latest["version"],
        notes=_latest["notes"],
        release_url=_latest["url"],
        published_at=_latest["published_at"],
        update_available=is_newer(_latest["version"], __version__),
        skipped=state.get("skipped_version") == _latest["version"],
    )
    return info


def skip_version(version: str) -> None:
    _save_state(skipped_version=version)


def acknowledge_update() -> None:
    _save_state(last_seen_version=__version__)


def _download_verified(asset: dict[str, Any] | None, dest: Path) -> Path:
    if not asset or not asset.get("sha256"):
        raise UpdateError("release_incomplete")
    with urllib.request.urlopen(_request(asset["url"]), timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != asset["sha256"]:
        raise UpdateError("checksum_mismatch")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def _ps_quote(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _app_pids() -> list[int]:
    # El padre (la ventana nativa en macOS, el lanzador del entorno de uv en
    # Windows) también tiene que cerrarse antes de tocar la instalación.
    return [os.getpid(), os.getppid()]


def _wait_for(pids: list[int]) -> list[str]:
    """Líneas de script que esperan a que terminen `pids`, como mucho un minuto cada uno."""
    if sys.platform == "win32":
        ids = ", ".join(map(str, pids))
        return [
            f"foreach ($p in @({ids})) {{ Wait-Process -Id $p -Timeout 60 -ErrorAction SilentlyContinue }}"
        ]
    return [
        f"for pid in {' '.join(map(str, pids))}; do",
        "  tries=0",
        '  while kill -0 "$pid" 2>/dev/null && [ "$tries" -lt 120 ]; do sleep 0.5; tries=$((tries + 1)); done',
        "done",
    ]


def write_updater_script(directory: Path, wheel: Path, installer: Path, pids: list[int]) -> Path:
    """
    Script que espera a que la app se cierre e instala la versión descargada,
    que vuelve a abrir mewsplit. Si la instalación falla, abre la versión que
    ya estaba para no dejar a nadie sin app.
    """
    if sys.platform == "win32":
        script = directory / "update.ps1"
        python = _ps_quote(Path(sys.executable))
        lines = [
            *_wait_for(pids),
            f"$env:MEWSPLIT_WHEEL = {_ps_quote(wheel)}",
            f"try {{ & {_ps_quote(installer)} }} catch {{ Start-Process -FilePath {python} -ArgumentList '-m mewsplit.app' }}",
        ]
    else:
        script = directory / "update.sh"
        lines = [
            "#!/bin/sh",
            *_wait_for(pids),
            (
                f"MEWSPLIT_WHEEL={shlex.quote(str(wheel))} /bin/sh {shlex.quote(str(installer))}"
                f" || open -b {MACOS_BUNDLE_ID}"
            ),
        ]
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script


def _launch_detached(script: Path, log: Path) -> None:
    # El hijo hereda su propia copia del descriptor: cerrarlo aquí no le corta el log.
    with open(log, "a", encoding="utf-8") as log_file:
        if sys.platform == "win32":
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                 "-File", str(script)],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                # Con DETACHED_PROCESS, PowerShell se cierra sin ejecutar nada: necesita una consola, aunque sea oculta.
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
        else:
            subprocess.Popen(
                ["/bin/sh", str(script)],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )


def _schedule_exit() -> None:
    # El retraso deja que la respuesta HTTP llegue a la interfaz antes de cerrar.
    threading.Timer(1.0, os._exit, args=(UPDATE_EXIT_CODE,)).start()


def start_update() -> dict[str, str]:
    """Descarga y verifica la versión nueva, lanza el actualizador y programa el cierre de la app."""
    reason = self_update_unavailable_reason()
    if reason:
        raise UpdateError(reason)
    try:
        release = fetch_latest_release()
    except (OSError, ValueError) as e:
        raise UpdateError("check_failed") from e
    if not release or not is_newer(release["version"], __version__):
        raise UpdateError("already_latest")

    version = release["version"]
    directory = CACHE_DIR / "updates" / version
    wheel_name = f"mewsplit-{version}-py3-none-any.whl"
    installer_name = "install.ps1" if sys.platform == "win32" else "install.sh"
    try:
        wheel = _download_verified(release["assets"].get(wheel_name), directory / wheel_name)
        installer = _download_verified(
            release["assets"].get(installer_name), directory / installer_name
        )
    except OSError as e:
        raise UpdateError("download_failed") from e

    script = write_updater_script(directory, wheel, installer, _app_pids())
    _launch_detached(script, directory / "update.log")
    _schedule_exit()
    return {"version": version}
