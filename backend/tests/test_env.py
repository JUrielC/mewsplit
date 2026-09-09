"""El cargador de .env: puerto y token vienen de aquí en desarrollo."""

from __future__ import annotations

import os
from pathlib import Path

from mewsplit.api import load_env_file


def test_reads_simple_pairs(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("MEWSPLIT_PORT=8000\nMEWSPLIT_TOKEN=dev-token\n")

    assert load_env_file(env) == {"MEWSPLIT_PORT": "8000", "MEWSPLIT_TOKEN": "dev-token"}


def test_ignores_comments_and_blank_lines(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("# un comentario\n\n  \nMEWSPLIT_PORT=8000\n# otro\n")

    assert load_env_file(env) == {"MEWSPLIT_PORT": "8000"}


def test_strips_export_prefix(tmp_path: Path):
    """Es habitual copiar el .env desde una línea de comandos."""
    env = tmp_path / ".env"
    env.write_text("export MEWSPLIT_TOKEN=abc\n")

    assert load_env_file(env) == {"MEWSPLIT_TOKEN": "abc"}


def test_strips_matching_quotes(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("A=\"con espacios\"\nB='simples'\nC=sin-comillas\n")

    assert load_env_file(env) == {"A": "con espacios", "B": "simples", "C": "sin-comillas"}


def test_keeps_equals_inside_the_value(tmp_path: Path):
    """Un token base64 puede acabar en '=' y no debe truncarse."""
    env = tmp_path / ".env"
    env.write_text("MEWSPLIT_TOKEN=eyJhbGciOi==\n")

    assert load_env_file(env) == {"MEWSPLIT_TOKEN": "eyJhbGciOi=="}


def test_skips_lines_without_separator(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("basura sin igual\nMEWSPLIT_PORT=8000\n")

    assert load_env_file(env) == {"MEWSPLIT_PORT": "8000"}


def test_missing_file_is_not_an_error(tmp_path: Path):
    """En escritorio no hay .env: el sidecar recibe todo por entorno."""
    assert load_env_file(tmp_path / "no-existe.env") == {}


def test_real_environment_wins_over_the_file(tmp_path: Path, monkeypatch):
    """
    Tauri y CI imponen sus valores; el archivo solo cubre el hueco local.
    Si esto se invierte, un .env olvidado pisaría la config de producción.

    Se limpian las dos variables antes: importar `mewsplit.api` ya cargó el
    backend/.env real en el entorno del proceso, y sin esto la prueba mediría
    ese arrastre en vez de la precedencia.
    """
    monkeypatch.delenv("MEWSPLIT_TOKEN", raising=False)
    monkeypatch.setenv("MEWSPLIT_PORT", "9999")
    env = tmp_path / ".env"
    env.write_text("MEWSPLIT_PORT=8000\nMEWSPLIT_TOKEN=del-archivo\n")

    load_env_file(env)

    assert os.environ["MEWSPLIT_PORT"] == "9999"
    assert os.environ["MEWSPLIT_TOKEN"] == "del-archivo"
