#!/usr/bin/env python3
"""Espectro e visuais do overlay, sem janela nem áudio."""
import os
import sys

import cairo
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper.ui.visuals import VISUALS, spectrum_bands, make_visual


def test_spectrum_bands():
    sr = 16000
    t = np.arange(1024) / sr
    assert spectrum_bands(np.zeros(1024)).max() == 0.0
    bands = spectrum_bands(0.03 * np.sin(2 * np.pi * 440 * t), sr)
    edges = np.geomspace(90, 7000, 33)
    expected = np.searchsorted(edges, 440) - 1
    assert abs(int(np.argmax(bands)) - expected) <= 1, (np.argmax(bands), expected)
    assert bands.max() > 0.6          # fala normal enche a barra
    assert len(spectrum_bands(np.zeros(100))) == 32  # buffer curto não quebra


def test_visuals_draw_every_state():
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 600, 400)
    for style in VISUALS:
        for size in ("s", "m", "l"):
            v = make_visual({"overlay_style": style, "overlay_size": size, "accent": "cyan"})
            for state in ("calibrating", "waiting", "listening", "transcribing", "success", "error"):
                v.set_state(state)
                v.set_level(0.8)
                v.set_bands(np.linspace(0, 1, 32))
                v.advance(1 / 60)
                v.draw(cairo.Context(surf), 300, 200)
    reduced = make_visual({"overlay_style": "orb", "reduce_motion": True})
    reduced.advance(1.0)
    assert reduced.angle == 0.0       # reduzir movimento: sem rotação


def run_tests():
    failed = False
    for fn in (test_spectrum_bands, test_visuals_draw_every_state):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
