"""El almacén de proyectos en disco, sin modelos: solo archivos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from mewsplit import projects
from mewsplit.core import Chord
from mewsplit.projects import Project


@pytest.fixture(autouse=True)
def store(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    return tmp_path / "projects"


def make(project_id: str, created_at: str = "2026-09-28T10:00:00", **kwargs) -> Project:
    return Project(
        id=project_id, name="Canción", filename="cancion.mp3", created_at=created_at, **kwargs
    )


def test_a_saved_project_comes_back_with_its_chords():
    projects.save(make("a", status="done", chords=[Chord(0.0, 1.5, "C:maj7")], duration=30.0))

    [loaded] = projects.load_all()

    assert loaded.status == "done"
    assert loaded.chords == [Chord(0.0, 1.5, "C:maj7")]
    assert loaded.duration == 30.0


def test_an_unfinished_project_is_marked_as_interrupted_on_load():
    """Si se cerró la app a mitad de la separación, no debe quedar "procesando" para siempre."""
    projects.save(make("a", status="processing"))

    [loaded] = projects.load_all()

    assert loaded.status == "error"
    assert loaded.error == projects.INTERRUPTED
    # Y se persiste: la próxima vez ya carga como error.
    assert projects.load(projects.project_dir("a")).status == "error"


def test_a_corrupt_project_does_not_break_the_list(store: Path):
    projects.save(make("bueno", status="done"))
    (store / "roto").mkdir()
    (store / "roto" / "project.json").write_text("{no es json")

    assert [p.id for p in projects.load_all()] == ["bueno"]


def test_projects_are_listed_newest_first():
    projects.save(make("viejo", created_at="2026-09-01T00:00:00"))
    projects.save(make("nuevo", created_at="2026-09-28T00:00:00"))
    projects.save(make("medio", created_at="2026-09-15T00:00:00"))

    assert [p.id for p in projects.load_all()] == ["nuevo", "medio", "viejo"]


def test_stems_are_stored_as_lossless_flac(tone):
    source = tone("vocals.wav")  # PCM de 16 bits, como los que produce la separación

    names = projects.store_stems("a", {"vocals": source})

    stored = projects.stem_path("a", "vocals")
    assert names == ["vocals"]
    assert sf.info(str(stored)).format == "FLAC"
    original, _ = sf.read(str(source), dtype="int16")
    copy, _ = sf.read(str(stored), dtype="int16")
    assert np.array_equal(original, copy)


def test_delete_removes_everything():
    projects.save(make("a"))
    projects.delete("a")

    assert not projects.project_dir("a").exists()
    assert projects.load_all() == []
