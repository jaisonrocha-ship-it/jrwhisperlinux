#!/usr/bin/env python3
"""Push-to-talk (estado de tecla simulado) e frase de parada do mãos livres."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import ptt


class FakeDisplay:
    def __init__(self):
        self.pressed = set()

    def query_keymap(self):
        keymap = [0] * 32
        for kc in self.pressed:
            keymap[kc // 8] |= 1 << (kc % 8)
        return keymap


def test_key_watcher():
    w = ptt.KeyWatcher.__new__(ptt.KeyWatcher)
    w.display, w.keycode = FakeDisplay(), 40
    assert not w.held()
    w.display.pressed.add(40)
    assert w.held()
    w.display.pressed = {41}            # outra tecla não conta
    assert not w.held()


def test_watcher_disabled():
    assert ptt.watcher_for({"ptt_enabled": False}) is None


def test_stop_phrase():
    assert ptt.strip_stop_phrase("Mais uma linha. Parar ditado.", "parar ditado") == ("Mais uma linha.", True)
    assert ptt.strip_stop_phrase("Parar ditado!", "parar ditado") == ("", True)
    assert ptt.strip_stop_phrase("Não vou parar o ditado agora", "parar ditado")[1] is False
    assert ptt.strip_stop_phrase("qualquer coisa", "")[1] is False


def run_tests():
    failed = False
    for fn in (test_key_watcher, test_watcher_disabled, test_stop_phrase):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
