from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SAMPLE_RATE = 44100


@pytest.fixture
def tone(tmp_path: Path):
    """Genera un wav estéreo corto; devuelve la ruta."""

    def create(name: str, frequency: float = 220.0, seconds: float = 0.5, amplitude: float = 0.4) -> Path:
        t = np.linspace(0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
        wave = (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
        path = tmp_path / name
        sf.write(str(path), np.stack([wave, wave], axis=1), SAMPLE_RATE)
        return path

    return create
