"""
paths.py — dónde guarda mewsplit lo suyo en cada sistema.

Los datos (proyectos, versión vista y omitida) van donde cada sistema guarda lo
que el usuario no gestiona a mano: ni Documentos, que es suyo, ni la caché,
que se puede vaciar. La caché (modelos, ffmpeg, descargas) se puede borrar sin
perder nada.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _data_dir() -> Path:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(local) / "mewsplit"
    return Path.home() / "Library" / "Application Support" / "mewsplit"


DATA_DIR = Path(os.environ.get("MEWSPLIT_DATA_DIR") or _data_dir())
CACHE_DIR = Path(os.environ.get("MEWSPLIT_CACHE_DIR") or Path.home() / ".cache" / "mewsplit")
