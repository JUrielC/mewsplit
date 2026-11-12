"""Avisos de versión nueva y actualización desde la app, sin red: el manifiesto es un archivo local."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mewsplit import __version__, api, updates

HEADERS = {"X-Mewsplit-Token": api.TOKEN}


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(updates, "STATE_FILE", tmp_path / "data" / "updates.json")
    monkeypatch.setattr(updates, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(updates, "_latest", None)
    monkeypatch.setattr(updates, "_checked", False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(api.app, headers=HEADERS)


def fake_release(version: str = "9.9.9", assets: dict | None = None) -> dict:
    return {
        "version": version,
        "notes": ["Nueva función"],
        "url": f"https://github.com/JUrielC/mewsplit/releases/tag/v{version}",
        "published_at": "2026-11-10T00:00:00Z",
        "assets": assets or {},
    }


def test_reports_a_new_version_and_asks_once_per_launch(client, monkeypatch):
    calls = []
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: calls.append(1) or fake_release())

    info = client.get("/updates").json()
    assert info["current_version"] == __version__
    assert info["latest_version"] == "9.9.9"
    assert info["update_available"] is True
    assert info["notes"] == ["Nueva función"]
    # Desde el repositorio no se puede: lo dice y da el comando para hacerlo a mano.
    assert info["can_self_update"] is False
    assert "git pull" in info["self_update_unavailable_reason"]
    assert info["install_command"]

    client.get("/updates")
    assert len(calls) == 1
    client.get("/updates?force=true")
    assert len(calls) == 2


def test_a_skipped_version_is_remembered(client, monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: fake_release())

    assert client.post("/updates/skip", json={"version": "9.9.9"}).status_code == 204

    info = client.get("/updates").json()
    assert info["update_available"] is True
    assert info["skipped"] is True


def test_without_releases_or_connection(client, monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: None)
    info = client.get("/updates?force=true").json()
    assert info["latest_version"] is None
    assert info["update_available"] is False
    assert info["error"] is None

    def offline():
        raise OSError("sin red")

    monkeypatch.setattr(updates, "fetch_latest_release", offline)
    assert "conexión" in client.get("/updates?force=true").json()["error"]


def test_an_invalid_manifest_is_a_check_error(client, monkeypatch, tmp_path: Path):
    manifest = tmp_path / "latest.json"
    manifest.write_text('{"sin": "versión"}', encoding="utf-8")
    monkeypatch.setattr(updates, "MANIFEST_URL", manifest.as_uri())

    info = client.get("/updates?force=true").json()
    assert info["update_available"] is False
    assert info["error"]


def test_the_updated_notice_stays_until_acknowledged(client, monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: fake_release(__version__))

    assert client.get("/updates").json()["updated_from"] is None
    updates._save_state(last_seen_version="0.0.1")
    info = client.get("/updates").json()
    assert info["updated_from"] == "0.0.1"
    assert info["update_available"] is False

    assert client.post("/updates/acknowledge").status_code == 204
    assert client.get("/updates").json()["updated_from"] is None


def test_the_update_routes_need_the_token():
    bare = TestClient(api.app)
    assert bare.get("/updates").status_code == 401
    assert bare.post("/updates/install").status_code == 401


def test_installing_is_refused_outside_the_installed_app(client):
    response = client.post("/updates/install")
    assert response.status_code == 409
    assert "git pull" in response.json()["detail"]


def test_installing_is_refused_in_the_middle_of_an_analysis(client, monkeypatch):
    """Cerrar la app a mitad de una separación la dejaría interrumpida."""
    monkeypatch.setattr(updates, "self_update_unavailable_reason", lambda: None)
    monkeypatch.setattr(api, "busy", lambda: True)
    monkeypatch.setattr(updates, "start_update", lambda: pytest.fail("no debía empezar"))

    response = client.post("/updates/install")
    assert response.status_code == 409
    assert "termine" in response.json()["detail"]


def installer_name() -> str:
    return "install.ps1" if sys.platform == "win32" else "install.sh"


def test_installing_verifies_the_downloads_and_launches_the_updater(client, monkeypatch, tmp_path):
    sources = {"mewsplit-9.9.9-py3-none-any.whl": b"wheel", installer_name(): b"installer"}
    assets = {}
    for name, content in sources.items():
        (tmp_path / name).write_bytes(content)
        assets[name] = {"url": (tmp_path / name).as_uri(), "sha256": hashlib.sha256(content).hexdigest()}

    launched, exits = [], []
    monkeypatch.setattr(updates, "self_update_unavailable_reason", lambda: None)
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: fake_release(assets=assets))
    monkeypatch.setattr(updates, "_launch_detached", lambda script, log: launched.append(script))
    monkeypatch.setattr(updates, "_schedule_exit", lambda: exits.append(1))

    response = client.post("/updates/install")
    assert response.status_code == 200
    assert response.json() == {"version": "9.9.9"}
    downloaded = tmp_path / "cache" / "updates" / "9.9.9" / "mewsplit-9.9.9-py3-none-any.whl"
    assert downloaded.read_bytes() == b"wheel"
    assert str(downloaded) in launched[0].read_text()
    assert exits == [1]

    assets[installer_name()]["sha256"] = "0" * 64
    tampered = client.post("/updates/install")
    assert tampered.status_code == 409
    assert "huella" in tampered.json()["detail"]
    assert len(launched) == 1


def test_the_manifest_from_the_release_script_is_installable(monkeypatch, tmp_path: Path):
    """El latest.json que genera el workflow con scripts/update_manifest.py lo lee la app tal cual."""
    release = tmp_path / "release"
    release.mkdir()
    files = [release / "mewsplit-9.9.9-py3-none-any.whl", release / installer_name()]
    for f in files:
        f.write_bytes(f"contenido de {f.name}".encode())
    notes = tmp_path / "changes.txt"
    notes.write_text("Primer cambio\n\nSegundo cambio\n", encoding="utf-8")
    manifest = tmp_path / "latest.json"

    script = Path(__file__).resolve().parents[2] / "scripts" / "update_manifest.py"
    subprocess.run(
        [
            sys.executable, str(script),
            "--version", "9.9.9",
            "--base-url", release.as_uri(),
            "--release-url", "https://github.com/JUrielC/mewsplit/releases/tag/v9.9.9",
            "--notes-file", str(notes),
            "--output", str(manifest),
            *map(str, files),
        ],
        check=True,
    )
    assert json.loads(manifest.read_text(encoding="utf-8"))["version"] == "9.9.9"

    monkeypatch.setattr(updates, "MANIFEST_URL", manifest.as_uri())
    latest = updates.fetch_latest_release()
    assert latest["notes"] == ["Primer cambio", "Segundo cambio"]
    assert set(latest["assets"]) == {f.name for f in files}

    launched = []
    monkeypatch.setattr(updates, "self_update_unavailable_reason", lambda: None)
    monkeypatch.setattr(updates, "_launch_detached", lambda script, log: launched.append(script))
    monkeypatch.setattr(updates, "_schedule_exit", lambda: None)
    assert updates.start_update() == {"version": "9.9.9"}
    assert len(launched) == 1


def test_only_a_copy_installed_by_uv_tool_can_update_itself(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "tools" / "mewsplit"))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("MEWSPLIT_NATIVE", raising=False)
    assert updates.self_update_unavailable_reason() == "open_from_icon"

    monkeypatch.setenv("MEWSPLIT_NATIVE", "1")
    assert updates.self_update_unavailable_reason() is None

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("MEWSPLIT_NATIVE")
    assert updates.self_update_unavailable_reason() is None

    monkeypatch.setattr(sys, "prefix", str(tmp_path / "backend" / ".venv"))
    assert updates.self_update_unavailable_reason() == "not_installer_copy"


def test_the_windows_updater_waits_and_reopens_the_old_version_if_it_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    wheel = tmp_path / "mewsplit-9.9.9-py3-none-any.whl"

    script = updates.write_updater_script(tmp_path, wheel, tmp_path / "install.ps1", [111, 222])

    text = script.read_text(encoding="utf-8")
    assert script.name == "update.ps1"
    assert "@(111, 222)" in text and "Wait-Process" in text
    assert f"$env:MEWSPLIT_WHEEL = '{wheel}'" in text
    assert "-m mewsplit.app" in text


@pytest.mark.skipif(sys.platform == "win32", reason="El actualizador de macOS es un script de shell")
def test_the_updater_waits_for_the_app_and_runs_the_installer(tmp_path: Path):
    marker = tmp_path / "instalado.txt"
    installer = tmp_path / "install.sh"
    installer.write_text(f'echo "$MEWSPLIT_WHEEL" > {shlex.quote(str(marker))}\n')
    wheel = tmp_path / "mewsplit-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    # Huérfano para que al terminar no quede como zombi (kill -0 seguiría respondiendo).
    app_pid = int(subprocess.check_output(["/bin/sh", "-c", "sleep 1.5 >/dev/null 2>&1 & echo $!"]))

    script = updates.write_updater_script(tmp_path, wheel, installer, [app_pid])
    started = time.monotonic()
    subprocess.run(["/bin/sh", str(script)], check=True, timeout=30)

    assert time.monotonic() - started >= 1.0
    assert marker.read_text().strip() == str(wheel)


@pytest.mark.skipif(sys.platform == "win32", reason="El actualizador de macOS es un script de shell")
def test_the_updater_reopens_the_installed_app_when_the_installer_fails(tmp_path: Path):
    installer = tmp_path / "install.sh"
    installer.write_text("exit 1\n")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    opened = tmp_path / "abierto.txt"
    fake_open = fake_bin / "open"
    fake_open.write_text(f'#!/bin/sh\necho "$*" > {shlex.quote(str(opened))}\n')
    fake_open.chmod(0o755)

    script = updates.write_updater_script(tmp_path, tmp_path / "mewsplit.whl", installer, [])
    subprocess.run(
        ["/bin/sh", str(script)], env={"PATH": f"{fake_bin}:/usr/bin:/bin"}, check=True, timeout=30
    )

    assert opened.read_text().strip() == f"-b {updates.MACOS_BUNDLE_ID}"


def test_versions_compare_as_numbers():
    assert updates.is_newer("0.10.0", "0.9.9")
    assert updates.is_newer("1.0.0", "0.99.0")
    assert not updates.is_newer("0.1.2", "0.1.2")
