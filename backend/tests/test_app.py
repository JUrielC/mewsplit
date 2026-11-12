from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mewsplit import api
from mewsplit import app as launcher
from mewsplit.app import APP_MODE_BROWSERS, build_app, default_browser, ready_line


@pytest.fixture
def web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    (web / "_next").mkdir(parents=True)
    (web / "index.html").write_text("<html><head><title>x</title></head><body></body></html>")
    (web / "_next" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("no debería salir")
    return web


def client(web: Path, host: str = "127.0.0.1") -> TestClient:
    return TestClient(build_app("secreto", web), base_url=f"http://{host}")


def test_home_injects_the_runtime_config(web: Path):
    """Sin esto el frontend no sabe a dónde hablar ni con qué token."""
    body = client(web).get("/").text
    assert '<head><script>window.__MEWSPLIT__ = {"api": "", "token": "secreto"};</script>' in body


def test_interface_files_are_served_and_the_rest_is_the_api(web: Path):
    c = client(web)
    assert c.get("/_next/app.js").text == "console.log(1)"
    assert c.get("/health").status_code == 200


def test_files_outside_the_interface_are_not_served(web: Path):
    response = client(web).get("/%2e%2e/secret.txt")
    assert "no debería salir" not in response.text


def test_foreign_hosts_are_rejected(web: Path):
    """La página lleva el token: un dominio ajeno apuntado a 127.0.0.1 no debe leerla."""
    assert client(web, host="evil.example").get("/").status_code == 400
    assert client(web, host="localhost").get("/").status_code == 200


def _watch(monkeypatch, busy: bool) -> SimpleNamespace:
    """Arranca el vigilante con 1 s de tolerancia y la última visita hace 10 s."""
    server = SimpleNamespace(should_exit=False)
    monkeypatch.setattr(api, "busy", lambda: busy)
    monkeypatch.setattr(launcher, "_last_seen", time.monotonic() - 10)
    options = {"idle_seconds": 1, "poll": 0.01}
    watcher = threading.Thread(target=launcher._shutdown_when_idle, args=(server,), kwargs=options)
    watcher.start()
    time.sleep(0.1)
    server.decided_to_exit = server.should_exit
    server.should_exit = True  # que el hilo termine en cualquier caso
    watcher.join()
    return server


def test_shuts_down_when_no_window_has_checked_in(monkeypatch):
    """Desde el acceso directo no hay terminal que cerrar: sin esto quedaría vivo para siempre."""
    assert _watch(monkeypatch, busy=False).decided_to_exit


def test_never_shuts_down_in_the_middle_of_an_analysis(monkeypatch):
    assert not _watch(monkeypatch, busy=True).decided_to_exit


def _https(bundle: str) -> dict:
    return {"LSHandlerURLScheme": "https", "LSHandlerRoleAll": bundle}


def test_default_browser_is_the_one_that_opens_https():
    mail = {"LSHandlerURLScheme": "mailto", "LSHandlerRoleAll": "com.apple.mail"}
    handlers = [mail, _https("com.Brave.Browser")]
    assert default_browser(handlers) == "com.brave.browser"


def test_without_a_handler_the_default_is_safari():
    """Es el navegador de fábrica: macOS no guarda nada hasta que el usuario elige otro."""
    assert default_browser([]) == "com.apple.safari"


def test_only_chromium_browsers_get_app_mode():
    assert "com.brave.browser" in APP_MODE_BROWSERS
    assert "com.google.chrome" in APP_MODE_BROWSERS
    assert "com.apple.safari" not in APP_MODE_BROWSERS
    assert "org.mozilla.firefox" not in APP_MODE_BROWSERS


def test_ready_line_is_what_the_native_window_parses():
    """native/macos/main.swift busca exactamente este formato en stdout."""
    assert ready_line("http://127.0.0.1:47820", "new") == (
        "MEWSPLIT_APP_READY url=http://127.0.0.1:47820 owner=new"
    )


class FakeWindow:
    def __init__(self):
        self.calls = []

    def restore(self):
        self.calls.append("restore")

    def show(self):
        self.calls.append("show")


def test_a_second_launch_brings_the_open_window_to_the_front(web: Path, monkeypatch):
    """En Windows, abrir mewsplit otra vez trae al frente la ventana que ya hay en vez de otra."""
    window = FakeWindow()
    monkeypatch.setattr(launcher, "_window", window)

    assert client(web).post("/window/show", headers={"X-Mewsplit-Token": "otro"}).status_code == 404
    assert window.calls == []

    response = client(web).post("/window/show", headers={"X-Mewsplit-Token": "secreto"})
    assert response.status_code == 204
    assert window.calls == ["restore", "show"]


def test_without_a_window_there_is_nothing_to_bring_to_the_front(web: Path):
    response = client(web).post("/window/show", headers={"X-Mewsplit-Token": "secreto"})
    assert response.status_code == 404


def test_without_a_console_the_output_goes_to_the_log(monkeypatch, tmp_path: Path):
    """pythonw.exe (el acceso directo de Windows) arranca con stdout y stderr en None."""
    monkeypatch.setattr(launcher, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(launcher, "LOG_FILE", tmp_path / "mewsplit.log")
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    launcher._ensure_stdio()
    print("hola", file=sys.stdout, flush=True)
    # Windows no deja borrar la carpeta temporal con el log abierto.
    sys.stdout.close()

    assert (tmp_path / "mewsplit.log").read_text(encoding="utf-8") == "hola\n"


def test_a_busy_preferred_port_falls_back_to_a_free_one():
    first = launcher._bind(0)
    taken = first.getsockname()[1]
    try:
        second = launcher._bind(taken)
        assert second.getsockname()[1] != taken
        second.close()
    finally:
        first.close()


def test_the_startup_message_page_escapes_the_error():
    page = launcher.message_page("falló <script>")
    assert "&lt;script&gt;" in page
    assert "<script>" not in page
