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


def _icon_pixels(cx, cy, size, ds=1):
    from jrwhisper.ui.theme import draw_icon
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(80 * ds), int(80 * ds))
    surf.set_device_scale(ds, ds)
    draw_icon(cairo.Context(surf), "mic", cx, cy, size)
    surf.flush()
    return np.frombuffer(bytes(surf.get_data()), np.uint8).reshape(int(80 * ds), -1)[:, 3::4]


def test_icons_are_crisp():
    """Ícone do overlay: posição fracionária não reamostra (borra), e em 2× sai com o dobro de pixels."""
    a, b = _icon_pixels(40.0, 40.0, 34), _icon_pixels(40.3, 39.6, 34)
    assert (a == b).all()                         # alinhado ao pixel: idêntico, sem meio-tom extra
    hi = _icon_pixels(40.0, 40.0, 34, ds=2)
    assert hi.shape == (160, 160) and (hi > 0).sum() > 3 * (a > 0).sum()  # HiDPI: detalhe real, não esticado


def _orb_over_red(level):
    """Orbe sem brilho (glow 0: só o corpo) sobre fundo vermelho opaco."""
    v = make_visual({"overlay_style": "orb", "overlay_glow": 0.0, "reduce_motion": True})
    v.set_level(level)
    for _ in range(120):
        v.advance(1 / 60)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 300, 300)
    cr = cairo.Context(surf)
    cr.set_source_rgb(1, 0, 0); cr.paint()
    v.draw(cr, 150, 150)
    surf.flush()
    return np.frombuffer(bytes(surf.get_data()), np.uint8).reshape(300, 300, 4)  # BGRA


def test_orb_is_glass_and_reacts():
    quiet, loud = _orb_over_red(0.0), _orb_over_red(1.0)
    assert quiet[150 + 30, 150 - 30, 2] > 90        # o fundo aparece através do corpo (antes: opaco, ~8)
    body = lambda img: int((img[..., 2] < 200).sum())  # pixels escurecidos pelo corpo de vidro
    assert body(loud) > 1.4 * body(quiet), (body(loud), body(quiet))  # voz forte: esfera bem maior


def run_tests():
    failed = False
    for fn in (test_spectrum_bands, test_visuals_draw_every_state, test_icons_are_crisp, test_orb_is_glass_and_reacts):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
