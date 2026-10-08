#!/usr/bin/env python3
"""Prints das janelas GTK (Ajustes em cada aba, Spotlight do histórico, calibração) sem abrir nada na tela.

Uso: render_windows.py <pasta>. O conteúdo de cada janela é desenhado numa Gtk.OffscreenWindow;
nada é salvo no config (só olha, não clica).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from jrwhisper import config as cfgmod  # noqa: E402

cfgmod.save_config = lambda c: None  # nunca grava o config real
from jrwhisper.config import load_config  # noqa: E402
from jrwhisper.ui import settings as settings_mod  # noqa: E402

settings_mod.save_config = lambda c: None


def snap(window, path, size=None):
    """Move o conteúdo da janela para uma janela fora da tela e salva o desenho em PNG."""
    child = window.get_child()
    window.remove(child)
    off = Gtk.OffscreenWindow()
    off.add(child)
    if size:
        off.set_size_request(*size)
    off.show_all()
    for _ in range(40):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
    off.get_pixbuf().savev(path, "png", [], [])
    off.remove(child)
    window.add(child)
    off.destroy()


def main(folder):
    os.makedirs(folder, exist_ok=True)
    config = load_config()
    win = settings_mod.SettingsWindow(config)
    for i, page in enumerate(settings_mod.PAGES):
        win.sidebar.select_row(win.sidebar.get_row_at_index(i))
        win.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        snap(win, os.path.join(folder, f"settings_{i:02d}_{page[0]}.png"), (900, 640))
    win.destroy()

    from jrwhisper.ui.history_search import HistorySearch
    hs = HistorySearch(config)
    snap(hs, os.path.join(folder, "history_search.png"), (660, -1))
    hs.destroy()

    from jrwhisper.ui.calibration import CalibrationWindow
    cw = CalibrationWindow(config, standalone=False)
    snap(cw, os.path.join(folder, "calibration.png"))
    cw.destroy()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "window_shots")
