from __future__ import annotations

import threading
from pathlib import Path

import pytest

from mewsplit import core
from mewsplit.core import Analysis, Chord, Stopwatch, get_duration


def test_stopwatch_records_the_stage():
    clock = Stopwatch(verbose=False)
    with clock.measure("separation"):
        pass
    assert "separation" in clock.timings


def test_stopwatch_records_even_when_the_stage_fails():
    clock = Stopwatch(verbose=False)
    with pytest.raises(RuntimeError):
        with clock.measure("separation"):
            raise RuntimeError("modelo caído")
    assert "separation" in clock.timings


def test_stopwatches_do_not_collide_across_threads():
    """El motivo de que no sea estado global de módulo."""
    clocks = [Stopwatch(verbose=False) for _ in range(8)]

    def work(index: int) -> None:
        with clocks[index].measure(f"stage_{index}"):
            pass

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for index, clock in enumerate(clocks):
        assert list(clock.timings) == [f"stage_{index}"]


def test_duration_of_a_wav(tone):
    assert get_duration(tone("x.wav", seconds=0.5)) == pytest.approx(0.5, abs=0.01)


def test_duration_of_something_that_is_not_audio(tmp_path: Path):
    junk = tmp_path / "not_audio.txt"
    junk.write_text("hola")
    assert get_duration(junk) is None


def test_analyze_fails_when_the_file_is_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        core.analyze(tmp_path / "ghost.wav", tmp_path)


def test_analyze_runs_separation_and_chords_in_parallel(tmp_path: Path, tone, monkeypatch):
    """
    Está medido que los acordes no mejoran con el instrumental, así que no
    deben esperar a los stems. Si alguien vuelve a encadenarlos, esto falla.
    """
    source = tone("song.wav")
    barrier = threading.Barrier(2, timeout=5)

    def fake_separate(*args, **kwargs):
        barrier.wait()  # solo pasa si los acordes ya están corriendo
        return {"vocals": source}

    def fake_detect_chords(*args, **kwargs):
        barrier.wait()
        return [{"start": 0.0, "end": 1.0, "chord": "C"}]

    monkeypatch.setattr(core, "separate", fake_separate)
    monkeypatch.setattr(core, "detect_chords", fake_detect_chords)
    monkeypatch.setattr(core, "build_instrumental", lambda *a, **k: None)

    analysis = core.analyze(source, tmp_path, verbose=False)

    assert analysis.chords == [Chord(start=0.0, end=1.0, chord="C")]


def test_analyze_reports_progress(tmp_path: Path, tone, monkeypatch):
    source = tone("song.wav")
    monkeypatch.setattr(core, "separate", lambda *a, **k: {"vocals": source})
    monkeypatch.setattr(core, "detect_chords", lambda *a, **k: [])
    monkeypatch.setattr(core, "build_instrumental", lambda *a, **k: None)

    seen = []
    core.analyze(source, tmp_path, verbose=False, on_progress=seen.append)

    assert seen == [0.0, 1.0]


def test_chords_branch_never_touches_progress(tmp_path: Path, tone, monkeypatch):
    """
    El progreso mide SOLO la separación. Cuando lo compartían las dos ramas,
    los acordes —que acaban en ~2s— lo dejaban en 1.0 durante los ~25s
    restantes y la barra mentía.

    Aquí se invierten los tiempos a propósito: los acordes terminan DESPUÉS
    de la separación, así que cualquier escritura suya aparecería como un
    evento extra detrás del 1.0.
    """
    source = tone("song.wav")
    separation_done = threading.Event()

    def fast_separate(*args, **kwargs):
        separation_done.set()
        return {"vocals": source}

    def slow_chords(*args, **kwargs):
        separation_done.wait(timeout=5)
        return [{"start": 0.0, "end": 1.0, "chord": "C"}]

    monkeypatch.setattr(core, "separate", fast_separate)
    monkeypatch.setattr(core, "detect_chords", slow_chords)
    monkeypatch.setattr(core, "build_instrumental", lambda *a, **k: None)

    seen: list[float] = []
    core.analyze(source, tmp_path, verbose=False, on_progress=seen.append)

    assert seen == [0.0, 1.0], f"la rama de acordes escribió progreso: {seen}"


def test_chords_are_published_before_separation_finishes(tmp_path: Path, tone, monkeypatch):
    """Los acordes deben poder pintarse sin esperar a los stems."""
    source = tone("song.wav")
    chords_arrived = threading.Event()

    def slow_separate(*args, **kwargs):
        assert chords_arrived.wait(timeout=5), "on_chords no llegó antes de acabar la separación"
        return {"vocals": source}

    monkeypatch.setattr(core, "separate", slow_separate)
    monkeypatch.setattr(core, "detect_chords", lambda *a, **k: [{"start": 0.0, "end": 1.0, "chord": "C"}])
    monkeypatch.setattr(core, "build_instrumental", lambda *a, **k: None)

    received: list[Chord] = []

    def on_chords(chords):
        received.extend(chords)
        chords_arrived.set()

    core.analyze(source, tmp_path, verbose=False, on_chords=on_chords)

    assert received == [Chord(start=0.0, end=1.0, chord="C")]


def test_analysis_serializes_to_json(tmp_path: Path):
    analysis = Analysis(
        source="/a/b.wav",
        device="mps",
        model="htdemucs.yaml",
        duration=30.0,
        chords=[Chord(0.0, 1.0, "C")],
    )
    assert analysis.to_dict()["chords"] == [{"start": 0.0, "end": 1.0, "chord": "C"}]
