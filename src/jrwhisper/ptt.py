"""Push-to-talk (X11): enquanto a tecla do atalho estiver pressionada, o ditado grava.

O Cinnamon dispara o comando no KeyPress; o processo leva ~0,5 s para subir.
Se nesse momento a tecla ainda está pressionada, é "segurar para falar";
se já foi solta, foi um toque e o ditado segue no modo normal.
"""
import os

from gi.repository import Gtk

from . import shortcuts
from .config import _debug_log
from .paste import get_display_server

DICTATE_CMD = os.path.expanduser("~/.local/bin/dictate")


class KeyWatcher:
    """Vigia a tecla principal de cada atalho (teclado e macropad): qualquer uma pressionada conta."""

    def __init__(self, accels):
        from Xlib import display  # python-xlib: só carrega quando o PTT está ligado
        self.display = display.Display()
        self.keycodes = []
        for accel in accels:
            keyval, _mods = Gtk.accelerator_parse(accel)
            # keyval do GDK == keysym do X; um keysym pode ter vários keycodes (XF86Tools: 179 e 191)
            if keyval:
                self.keycodes += [kc for kc, _i in self.display.keysym_to_keycodes(keyval)]
        if not self.keycodes:
            raise ValueError(f"sem keycode para {accels}")

    def held(self):
        keymap = self.display.query_keymap()
        return any(keymap[k // 8] & (1 << (k % 8)) for k in self.keycodes)


def watcher_for(config, command=DICTATE_CMD):
    """KeyWatcher da tecla principal do atalho, ou None (PTT desligado, Wayland ou sem atalho)."""
    if not config.get("ptt_enabled") or get_display_server() != "x11":
        return None
    accels = shortcuts.get_bindings(command)
    if not accels:
        return None
    try:
        return KeyWatcher(accels)
    except Exception as e:
        _debug_log(f"PTT indisponível: {e}")
        return None


def strip_stop_phrase(text, phrase):
    """('Mais uma linha. Parar ditado.', 'parar ditado') → ('Mais uma linha.', True)."""
    import re
    import unicodedata

    def norm(s):
        s = unicodedata.normalize("NFKD", s.lower())
        return "".join(c for c in s if c.isalnum() or c.isspace())

    phrase = phrase.strip()
    if not phrase:
        return text, False
    words = text.split()
    n = len(phrase.split())
    if len(words) >= n and norm(" ".join(words[-n:])).split() == norm(phrase).split():
        rest = " ".join(words[:-n]).rstrip(" ,;:-–—")
        return re.sub(r"\s+$", "", rest), True
    return text, False
