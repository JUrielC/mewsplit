from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mewsplit import api
from mewsplit import app as launcher
from mewsplit.app import APP_MODE_BROWSERS, build_app, default_browser


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
