from __future__ import annotations

from mewsplit.chords import chord_at, condense

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
