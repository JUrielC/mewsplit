"""
youtube.py — el audio de un video de YouTube, para analizarlo como si se
hubiera subido.

Envoltorio de entrada, igual que `projects`: `core` no sabe que existe y sigue
recibiendo una ruta de archivo. Lo usa `api`.

Desde finales de 2025 YouTube exige resolver un reto en JavaScript para
servir los formatos. `yt-dlp` lo hace con Deno, que llega como dependencia de
Python (el extra `deno`) y no pide Homebrew a quien instala.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mewsplit.separation import ensure_ffmpeg

_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}
# youtube.com/shorts/<id>, /live/<id>, /embed/<id>, /v/<id>
_ID_IN_PATH = {"shorts", "live", "embed", "v"}

# YouTube a veces responde 403 a la URL de un formato recién resuelta (1 de
# cada ~12 descargas al probarlo); resolverla otra vez suele bastar.
ATTEMPTS = 3


class InvalidLink(ValueError):
    pass


class Unavailable(RuntimeError):
    pass


def video_id(link: str) -> str:
    """
    El identificador del video de un enlace de YouTube.

    Solo se acepta un video concreto: de una lista se toma el video y no la
    lista, y un canal o una lista sola no son una canción.
    """
    text = link.strip()
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    parts = [part for part in parsed.path.split("/") if part]

    candidate = None
    if host == "youtu.be" and parts:
        candidate = parts[0]
    elif host in _HOSTS and parts == ["watch"]:
        candidate = parse_qs(parsed.query).get("v", [None])[0]
    elif host in _HOSTS and len(parts) >= 2 and parts[0] in _ID_IN_PATH:
        candidate = parts[1]

    if candidate is None or not _VIDEO_ID.fullmatch(candidate):
        raise InvalidLink("No es un enlace a un video de YouTube")
    return candidate


def watch_url(video: str) -> str:
    return f"https://www.youtube.com/watch?v={video}"


def download(
    video: str,
    folder: Path,
    on_title: Callable[[str], None] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """
    Descarga el audio del video a `folder` y devuelve la ruta del archivo.

    Se pide el Opus que YouTube ya sirve y solo se cambia de contenedor (WebM
    a Ogg), sin recodificar: soundfile lee Ogg Opus, así que la duración y la
    separación funcionan como con cualquier archivo subido.

    `on_title` llega antes de la descarga, para nombrar el proyecto en cuanto
    se sabe. Si `on_progress` lanza una excepción, la descarga se corta.
    """
    import deno
    import yt_dlp

    ensure_ffmpeg()
    folder.mkdir(parents=True, exist_ok=True)

    def hook(status: dict) -> None:
        if on_progress is None or status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        if total:
            on_progress(min(status.get("downloaded_bytes", 0) / total, 1.0))

    options = {
        "format": "bestaudio[acodec=opus]/bestaudio",
        "outtmpl": str(folder / "audio.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "opus"}],
        "progress_hooks": [hook],
        # El enlace ya se normalizó a un video: ni listas ni el extractor genérico.
        "noplaylist": True,
        "allowed_extractors": ["youtube"],
        # La ruta explícita evita usar un Deno viejo del sistema.
        "js_runtimes": {"deno": {"path": deno.find_deno_bin()}},
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
    }

    attempt = 1
    while True:
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(watch_url(video), download=False)
                if info.get("is_live"):
                    raise Unavailable("Es una transmisión en directo: no tiene un final que descargar")
                if on_title is not None:
                    on_title(info.get("title") or video)
                result = ydl.process_ie_result(info, download=True)
            return Path(result["requested_downloads"][0]["filepath"])
        except yt_dlp.utils.DownloadError as e:
            if "HTTP Error 403" not in str(e) or attempt == ATTEMPTS:
                raise Unavailable(f"YouTube no dejó descargarlo: {_reason(str(e))}") from e
            attempt += 1


def _reason(message: str) -> str:
    """'ERROR: [youtube] abc: Video unavailable' -> 'Video unavailable'."""
    return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[\w-]+:\s*)?", "", message).strip()
