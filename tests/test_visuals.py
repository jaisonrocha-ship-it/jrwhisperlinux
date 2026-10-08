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


def _pill_alpha(style, bands):
    v = make_visual({"overlay_style": style, "reduce_motion": True})
    v.set_state("listening"); v.set_level(0.9); v.set_bands(bands)
    for _ in range(60):
        v.advance(1 / 60)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 100)
    v.draw(cairo.Context(surf), 200, 50)
    surf.flush()
    a = np.frombuffer(bytes(surf.get_data()), np.uint8).reshape(100, 400, 4)
    return a, v


def test_bars_mirrored_and_waves_fade_out():
    img, _ = _pill_alpha("bars", np.linspace(1, 0, 32))       # graves fortes, agudos fracos
    lit = img[..., :3].max(axis=2).astype(int)
    assert np.abs(lit[:, :200] - lit[:, 200:][:, ::-1]).mean() < 4  # espelhada: esquerda = direita
    height = lambda x0, x1: int((lit[:, x0:x1] > 100).any(axis=1).sum())
    assert height(190, 210) > 2 * height(45, 70)               # graves no centro, mais altos
    img, v = _pill_alpha("waves", np.full(32, 0.8))
    w, h = v.size(); pad = h * 0.45
    x_end, x_mid = int(200 - w / 2 + pad + 2), 200
    glow = lambda x: int(img[30:70, x - 2:x + 3, :3].max())
    assert glow(x_end) < 0.25 * glow(x_mid), (glow(x_end), glow(x_mid))  # a luz some antes da borda


def test_ptbr_numbers_and_dates():
    import time
    import gi
    gi.require_version("Gtk", "3.0")
    from jrwhisper.ui import theme as t
    assert t.num(0.0029, 4) == "0,0029" and t.num(-1.0) == "-1,0"
    assert t.when_text(time.strftime("%Y-%m-%d %H:%M")).startswith("Hoje ")
    assert t.when_text("2026-03-05 09:07").endswith("05/03 09:07") and t.when_text(None) == ""


def run_tests():
    failed = False
    for fn in (test_spectrum_bands, test_visuals_draw_every_state, test_icons_are_crisp, test_orb_is_glass_and_reacts, test_bars_mirrored_and_waves_fade_out, test_ptbr_numbers_and_dates):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
