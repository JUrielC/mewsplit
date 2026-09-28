from __future__ import annotations

import numpy as np
import pytest

from mewsplit.chords import (
    FAMILIES,
    FAMILY_N,
    FRAME_SECONDS,
    QUALITIES,
    _load,
    assign_quality,
    beat_pool,
    chord_at,
    condense,
    family_label,
    family_of,
    path_to_segments,
    simple_label,
    smooth,
    to_families,
    tuning_to_apply,
)

SEGMENTS = [
    {"start": 0.0, "end": 1.8, "chord": "N"},
    {"start": 1.8, "end": 10.2, "chord": "B"},
    {"start": 10.2, "end": 11.3, "chord": "B"},
    {"start": 11.3, "end": 20.1, "chord": "E:min"},
    {"start": 20.1, "end": 30.0, "chord": "B"},
]


def test_condense_collapses_repeats_and_drops_silence():
    assert condense(SEGMENTS) == ["B", "E:min", "B"]


def test_condense_empty_list():
    assert condense([]) == []


def test_chord_at_uses_half_open_interval():
    assert chord_at(SEGMENTS, 0.0) == "N"
    assert chord_at(SEGMENTS, 11.3) == "E:min"
    assert chord_at(SEGMENTS, 20.0) == "E:min"


def test_chord_after_the_end_returns_the_last_one():
    assert chord_at(SEGMENTS, 999.0) == "B"


def test_chord_at_without_segments():
    assert chord_at([], 1.0) == "N"


@pytest.mark.slow
@pytest.mark.parametrize(("large_vocabulary", "classes"), [(True, 170), (False, 25)])
def test_each_vocabulary_loads_its_own_checkpoint(large_vocabulary, classes):
    """
    AutoModel se tragaba `large_voca` y siempre cargaba el de 170 clases:
    `--simple-chords` no hacía nada y nadie lo notó porque no falla, solo miente.
    """
    model = _load(large_vocabulary, timer=None)
    assert len(model._idx_to_chord) == classes


def _large(**mass: float) -> np.ndarray:
    """Un frame del vocabulario grande con la masa repartida como se indique."""
    # Solo raíces sin sostenido: "C#_maj" no sería un nombre de argumento válido.
    roots = {"C": 0, "D": 2, "G": 7, "A": 9}
    frame = np.zeros(170)
    for label, value in mass.items():
        root, quality = label.split("_")
        frame[roots[root] * len(QUALITIES) + QUALITIES.index(quality)] = value
    return frame[None, :]


def test_families_pool_the_mass_split_among_qualities():
    """C, C7 y Cmaj7 separados pierden contra Am; sumados como "do mayor", ganan."""
    frame = _large(C_maj=0.25, C_7=0.2, C_maj7=0.15, A_min=0.4)
    assert frame.argmax() == 9 * len(QUALITIES) + QUALITIES.index("min")

    families = to_families(frame)
    assert families.shape == (1, FAMILIES)
    assert family_label(int(families.argmax())) == "C"


def test_families_count_the_third_not_the_extension():
    families = to_families(_large(A_min7=0.6, A_min6=0.4))
    assert family_label(int(families.argmax())) == "A:min"


def test_augmented_has_its_own_family():
    """Dentro de la familia mayor, un aumentado nunca se separaba de su vecino."""
    families = to_families(_large(C_maj=0.4, C_aug=0.6))
    assert family_label(int(families.argmax())) == "C:aug"


def test_diminished_family_is_weighted_against_its_fewer_classes():
    """Sin el peso, 0.3 de m7b5 perdería contra 0.7 de menor; con ×3 gana."""
    families = to_families(_large(A_min=0.7, A_hdim7=0.3))
    assert family_label(int(families.argmax())) == "A:dim"
    assert families.sum() == pytest.approx(1.0)


def test_simple_label_folds_aug_and_dim_by_their_third():
    assert simple_label(family_of(0, "aug")) == "C"
    assert simple_label(family_of(9, "dim")) == "A:min"
    assert simple_label(FAMILY_N) == "N"


def test_quality_inside_the_diminished_family():
    frames = np.vstack([_large(A_dim=0.1, A_hdim7=0.9)] * 4)
    assert assign_quality(family_of(9, "dim"), frames, margin=3.0) == "A:hdim7"


def test_smoothing_removes_a_one_frame_blip():
    c, am = np.zeros(FAMILIES), np.zeros(FAMILIES)
    c[0], c[FAMILY_N] = 0.9, 0.1
    am[19], am[0] = 0.55, 0.45
    probs = np.array([c] * 10 + [am] + [c] * 10)

    assert set(probs.argmax(1)) == {0, 19}
    assert set(smooth(probs, 0.95)) == {0}


def test_smoothing_keeps_a_sustained_change():
    c, g = np.zeros(FAMILIES), np.zeros(FAMILIES)
    c[0], g[14] = 1.0, 1.0
    probs = np.array([c] * 20 + [g] * 20) * 0.9 + 0.1 / FAMILIES
    path = smooth(probs, 0.95)
    assert path[0] == 0 and path[-1] == 14


def test_quality_needs_a_margin_over_the_triad():
    frames = np.vstack([_large(C_maj=0.4, C_7=0.5)] * 4)
    assert assign_quality(0, frames, margin=1.0) == "C:7"
    assert assign_quality(0, frames, margin=2.0) == "C"


def test_quality_never_crosses_the_third():
    """Una familia mayor no puede acabar etiquetada como menor, aunque pese más."""
    frames = _large(C_maj=0.2, C_min7=0.8)
    assert assign_quality(0, frames, margin=1.0) == "C"


def test_path_to_segments_merges_runs_and_uses_frame_times():
    path = np.array([0, 0, 0, 14, 14, FAMILY_N])
    segments = path_to_segments(path, lambda family, _: family_label(family))
    assert [s["chord"] for s in segments] == ["C", "G", "N"]
    assert segments[1]["start"] == round(3 * FRAME_SECONDS, 3)
    assert segments[-1]["end"] == round(6 * FRAME_SECONDS, 3)


def test_path_to_segments_joins_neighbours_with_the_same_label():
    """Dos familias distintas pueden acabar con la misma etiqueta: no es un cambio."""
    segments = path_to_segments(np.array([0, 0, 1, 1]), lambda *_: "C")
    assert len(segments) == 1


def test_beat_pool_averages_frames_within_each_beat():
    probs = np.eye(3)[[0, 0, 1, 1, 2, 2]]
    beats = np.array([2, 4]) * FRAME_SECONDS
    pooled, owner = beat_pool(probs, beats)
    assert owner.tolist() == [0, 0, 1, 1, 2, 2]
    assert pooled.argmax(1).tolist() == [0, 1, 2]


def test_small_detuning_is_left_alone():
    """Estimar la afinación no es exacto: corregir unos cents de más solo mete ruido."""
    assert tuning_to_apply(0.05) == 0.0
    assert tuning_to_apply(-0.19) == 0.0


def test_real_detuning_is_compensated():
    """Nirvana, +43 cents: sin compensar, cada nota cae entre dos casillas del CQT."""
    assert tuning_to_apply(0.43) == 0.43
    assert tuning_to_apply(-0.3) == -0.3
