"""El mapeo de stems y la mezcla instrumental, sin cargar modelos."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from mewsplit import separation
from mewsplit.separation import _map_stems, build_instrumental, ensure_ffmpeg


def test_maps_absolute_paths_and_bare_names(tmp_path: Path, tone):
    """audio-separator devuelve una u otra forma según la versión."""
    absolute = tone("song_(Vocals)_htdemucs.wav")
    bare = tone("song_(Bass)_htdemucs.wav")

    stems = _map_stems([str(absolute), bare.name], tmp_path)

    assert stems["vocals"] == absolute
    assert stems["bass"] == bare


def test_skips_missing_files(tmp_path: Path):
    assert _map_stems(["ghost_(Drums).wav"], tmp_path) == {}


def test_instrumental_sums_non_vocal_stems(tmp_path: Path, tone):
    stems = {
        "vocals": tone("v_(Vocals).wav", frequency=440.0),
        "bass": tone("b_(Bass).wav", frequency=110.0, amplitude=0.3),
        "drums": tone("d_(Drums).wav", frequency=150.0, amplitude=0.3),
    }

    instrumental = build_instrumental(stems, tmp_path)

    assert instrumental is not None and instrumental.name == "instrumental.wav"
    mix, _ = sf.read(str(instrumental), always_2d=True)
    bass, _ = sf.read(str(stems["bass"]), always_2d=True)
    # La voz no entra en la mezcla, así que el pico no puede ser el de los tres juntos.
    assert np.max(np.abs(mix)) <= 1.0
    assert len(mix) == len(bass)


def test_instrumental_normalizes_clipping(tmp_path: Path, tone):
    stems = {
        "bass": tone("b_(Bass).wav", frequency=110.0, amplitude=0.9),
        "drums": tone("d_(Drums).wav", frequency=110.0, amplitude=0.9),
        "other": tone("o_(Other).wav", frequency=110.0, amplitude=0.9),
    }

    instrumental = build_instrumental(stems, tmp_path)
    mix, _ = sf.read(str(instrumental), always_2d=True)

    assert np.max(np.abs(mix)) <= 1.0


def test_returns_none_without_non_vocal_stems(tmp_path: Path, tone):
    assert build_instrumental({"vocals": tone("v_(Vocals).wav")}, tmp_path) is None


def test_reuses_instrumental_when_model_provides_it(tmp_path: Path, tone):
    existing = tone("x_(Instrumental).wav")
    assert build_instrumental({"instrumental": existing}, tmp_path) == existing


def test_ensure_ffmpeg_falls_back_to_the_bundled_binary(tmp_path: Path, monkeypatch):
    """Quien instala mewsplit para tocar no tiene Homebrew: sin esto audio-separator no arranca."""
    monkeypatch.setattr(separation, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("PATH", str(tmp_path / "vacio"))
    assert shutil.which("ffmpeg") is None

    ensure_ffmpeg()
    # La segunda vez reutiliza lo que dejó la primera.
    ensure_ffmpeg()

    found = Path(shutil.which("ffmpeg"))
    assert found.parent == tmp_path / "cache" / "bin"
    assert found.stem.lower() == "ffmpeg"


def test_ensure_ffmpeg_keeps_the_system_one(tmp_path: Path, monkeypatch):
    system = tmp_path / "sys"
    system.mkdir()
    fake = system / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(separation, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("PATH", str(system))

    ensure_ffmpeg()

    assert Path(shutil.which("ffmpeg")).parent == system
    assert not (tmp_path / "cache").exists()
