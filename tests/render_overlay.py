#!/usr/bin/env python3
"""Prints do overlay sem tela: cada estado de cada estilo, sobre fundo escuro e claro.

Uso: render_overlay.py <pasta>   (gera <estilo>_<estado>.png e captions_*.png)
Serve para comparar antes/depois de mudanças visuais e para o loop de front-end.
"""
import os
import sys

import cairo
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
from jrwhisper.config import load_config  # noqa: E402
from jrwhisper.ui.overlay import WhisperFlowOverlay  # noqa: E402

TEXT = ("Prezado Marcos, segue o booking confirmado para o navio MSC, com o BL em anexo "
        "e a previsão de chegada no terminal amanhã cedo.")
CAPTIONS = ["A carga saiu do armazém às oito.", "O navio atracou no berço três.",
            "O despachante confirmou a liberação.", "Falta só o BL original chegar."]


def backdrop(w, h, light):
    """Fundo de área de trabalho: degradê com formas, para a translucidez aparecer."""
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    g = cairo.LinearGradient(0, 0, w, h)
    if light:
        g.add_color_stop_rgb(0, 0.96, 0.95, 0.93); g.add_color_stop_rgb(1, 0.85, 0.88, 0.93)
    else:
        g.add_color_stop_rgb(0, 0.10, 0.12, 0.20); g.add_color_stop_rgb(1, 0.25, 0.10, 0.22)
    cr.set_source(g); cr.paint()
    cr.set_source_rgba(*((0.2, 0.4, 0.9, 0.35) if light else (0.95, 0.6, 0.2, 0.35)))
    cr.arc(w * 0.3, h * 0.4, min(w, h) * 0.25, 0, 6.3); cr.fill()
    cr.set_source_rgba(0.1, 0.1, 0.1, 0.8 if light else 0.0)
    for i in range(0, h, 22):  # "texto" de documento atrás
        cr.rectangle(30, i + 8, w * (0.4 + 0.5 * ((i * 7) % 10) / 10), 6); cr.fill()
    return surf


def settle(o, secs=1.0, level=None, bands=True):
    for i in range(int(secs * 60)):
        if level is not None:
            o.visual.set_level(level * (0.85 + 0.15 * np.sin(i / 3)))
        if bands:
            o.visual.set_bands(np.abs(np.sin(np.arange(32) / 3 + i / 5)) * (level or 0.3))
        o.visual.advance(1 / 60)
        k = 1 - np.exp(-10 / 60)
        o.text_alpha += ((1.0 if o.text else 0.0) - o.text_alpha) * k
        o.box_h += (o._target_box_h() - o.box_h) * k
        if o.captions:
            o.capview.advance(1 / 60)


def shot(o, path):
    W, H = o.W, o.H
    layer = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(layer)
    o._on_draw(o, cr)
    if hasattr(o, "_n_lines"):  # o 1º desenho mede o texto; o 2º já sai com a caixa na altura certa
        settle(o, 0.6, level=None, bands=False)
        cr = cairo.Context(layer); o._on_draw(o, cr)
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, W * 2 + 12, H)
    oc = cairo.Context(out)
    for i, light in enumerate((False, True)):
        oc.save(); oc.translate(i * (W + 12), 0)
        oc.set_source_surface(backdrop(W, H, light)); oc.paint()
        oc.set_source_surface(layer); oc.paint(); oc.restore()
    out.write_to_png(path)


def main(folder):
    os.makedirs(folder, exist_ok=True)
    base = load_config()
    for style in ("orb", "waves", "bars"):
        cfg = dict(base, overlay_style=style, overlay_captions=False, ai_enabled=False)
        for state, status, level, text, final in (
                ("waiting", "status-waiting", 0.0, "", False),
                ("listening_quiet", "status-listening", 0.15, "", False),
                ("listening_loud", "status-listening", 0.95, TEXT[:60], False),
                ("transcribing", "status-transcribing", 0.0, TEXT, False),
                ("success", "status-success", 0.0, TEXT, True)):
            o = WhisperFlowOverlay(cfg); o.hide()
            o.update_status({"waiting": "Fale agora", "transcribing": "Transcrevendo…", "success": "Colado"}
                            .get(state, "Ouvindo..."), status)
            o.update_text(text, final)
            settle(o, 1.0, level)
            shot(o, os.path.join(folder, f"{style}_{state}.png"))
            o.destroy()
    # revisão com IA (chips)
    o = WhisperFlowOverlay(dict(base, ai_enabled=True, handsfree_enabled=False)); o.hide()
    o.update_status("Escolha", "status-success")
    o.show_choices(TEXT, [m for m in base.get("ai_modes", []) if m.get("enabled", True)], "original", lambda a: None)
    settle(o, 1.0, 0.0); shot(o, os.path.join(folder, "review_choices.png")); o.destroy()
    # legendas: quadros da rolagem logo depois de uma frase nova (é aí que a lente atrasa)
    o = WhisperFlowOverlay(dict(base, overlay_captions=True, overlay_lines=base.get("caption_lines", 8))); o.hide()
    o.update_status("Legendas", "status-listening")
    o.update_captions(CAPTIONS[:3], "falta só o")
    settle(o, 2.0, 0.4)
    o.update_captions(CAPTIONS, "")
    for i, t in enumerate((0.0, 0.08, 0.16, 0.3)):
        settle(o, t - (0 if i == 0 else (0.0, 0.08, 0.16, 0.3)[i - 1]), 0.4)
        shot(o, os.path.join(folder, f"captions_{int(t * 1000):03d}ms.png"))
    o.destroy()


def bench(frames=300):
    """Custo de um quadro inteiro do overlay (ms, p50/p95) por estilo, ouvindo com texto: porta "não piorar"."""
    import time
    base = load_config()
    for style in ("orb", "waves", "bars"):
        o = WhisperFlowOverlay(dict(base, overlay_style=style, overlay_captions=False, ai_enabled=False)); o.hide()
        o.update_status("Ouvindo…", "status-listening"); o.update_text(TEXT[:90])
        settle(o, 0.5, 0.6)
        layer = cairo.ImageSurface(cairo.FORMAT_ARGB32, o.W, o.H)
        ts = []
        for i in range(frames):
            o.visual.set_level(0.5 + 0.5 * np.sin(i / 9))
            o.visual.set_bands(np.abs(np.sin(np.arange(32) / 3 + i / 5)))
            o.visual.advance(1 / 165)
            cr = cairo.Context(layer)
            t = time.perf_counter(); o._on_draw(o, cr); layer.flush(); ts.append((time.perf_counter() - t) * 1000)
        ts.sort()
        print(f"{style:6s} p50 {ts[len(ts) // 2]:.2f} ms  p95 {ts[int(len(ts) * .95)]:.2f} ms")
        o.destroy()


if __name__ == "__main__":
    if sys.argv[1:] == ["--bench"]:
        bench()
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "overlay_shots")
