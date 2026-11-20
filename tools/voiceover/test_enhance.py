"""pure-logic checks for enhance.py (no ffmpeg): phrase lookup, silence detection, pause planning, splicing."""

import numpy as np
import pytest

import enhance as e

SR = 1000
WORDS = [{"text": t, "start": s, "end": s + 0.3} for t, s in
         [("His", 0.0), ("only", 0.4), ("weapon?", 0.8), ("Your", 1.5), ("car's", 1.9), ("warranty.", 2.3),
          ("your", 3.0), ("cars", 3.4)]]


def tone(spans, n):
    """loud where spans say, silent elsewhere"""
    x = np.zeros((n, 1), np.float32)
    for a, b in spans:
        x[int(a * SR):int(b * SR)] = 0.5
    return x


def test_find_phrase_matches_words_case_and_punctuation_free():
    assert e.find_phrase(WORDS, "your CARS") == pytest.approx((1.5, 2.2))
    assert e.find_phrase(WORDS, "your car's", occurrence=2) == pytest.approx((3.0, 3.7))
    with pytest.raises(e.EnhanceError):
        e.find_phrase(WORDS, "your cars", occurrence=3)


def test_silences_and_pause_plan_only_grow_gaps():
    x = tone([(0, 1.0), (1.3, 2.0), (3.0, 4.0)], 4000)  # gaps: 0.3 s at 1.0, 1.0 s at 2.0
    sil = e.silences(x, SR, -40, 0.15)
    assert [(round(a, 2), round(b, 2)) for a, b in sil] == [(1.0, 1.3), (2.0, 3.0)]
    plan = e.pause_plan([{"at": 1.3, "seconds": 0.8}, {"at": 3.0, "seconds": 0.5}], None, sil, x, SR, 2.0)
    assert len(plan) == 1                      # the 1.0 s gap is already longer than 0.5: untouched
    at, add = plan[0]
    assert 1.0 < at < 1.3 and abs(add - 0.5) < 1e-9


def test_assemble_inserts_silence_and_maps_time():
    x = tone([(0, 1.0), (1.3, 2.0)], 2000)
    y, tm = e.assemble(x, SR, [(1.15, 0.5)], [])
    assert len(y) == 2500
    assert abs(tm(0.5) - 0.5) < 1e-3 and abs(tm(1.5) - 2.0) < 1e-3
    assert not y[1150:1650].any()               # the inserted silence


def test_assemble_rejects_overlaps():
    x = tone([(0, 2.0)], 2000)
    with pytest.raises(e.EnhanceError):
        e.assemble(x, SR, [(1.0, 0.2)], [(0.5, 1.5, {})])
