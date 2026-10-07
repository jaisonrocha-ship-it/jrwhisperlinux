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
    def __init__(self, accel):
        from Xlib import display  # python-xlib: só carrega quando o PTT está ligado
        keyval, _mods = Gtk.accelerator_parse(accel)
        if not keyval:
            raise ValueError(f"atalho inválido: {accel}")
        self.display = display.Display()
        self.keycode = self.display.keysym_to_keycode(keyval)  # keyval do GDK == keysym do X
        if not self.keycode:
            raise ValueError(f"sem keycode para {accel}")

    def held(self):
        keymap = self.display.query_keymap()
        return bool(keymap[self.keycode // 8] & (1 << (self.keycode % 8)))


def watcher_for(config, command=DICTATE_CMD):
    """KeyWatcher da tecla principal do atalho, ou None (PTT desligado, Wayland ou sem atalho)."""
    if not config.get("ptt_enabled") or get_display_server() != "x11":
        return None
    accel = shortcuts.get_binding(command)
    if not accel:
        return None
    try:
        return KeyWatcher(accel)
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
