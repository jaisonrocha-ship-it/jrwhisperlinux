#!/usr/bin/env python3
"""Legendas ao vivo: o corte em frases (pausa / fala contínua) e a ordem fila → tradução → tela."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import captions

SR = 16000
TICK = 800  # 50 ms


def voice(secs, amp=0.05):
    t = np.arange(int(secs * SR)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(secs):
    return np.zeros(int(secs * SR), np.float32)


def feed(chunker, audio):
    out = []
    for i in range(0, len(audio), TICK):
        out += chunker.feed(audio[i:i + TICK])
    return out


def test_cuts_on_pauses():
    c = captions.Chunker(SR)
    chunks = feed(c, np.concatenate([voice(1.2), silence(0.6), voice(2.0), silence(0.6)]))
    assert len(chunks) == 2 and 1.2 <= len(chunks[0]) / SR <= 1.8, [len(x) / SR for x in chunks]


def test_quiet_video_still_cuts():  # volume do app em 15%: ~0,0003 de RMS
    c = captions.Chunker(SR)
    chunks = feed(c, np.concatenate([voice(1.5, amp=0.0005), silence(0.6)]))
    assert len(chunks) == 1


def test_silence_only_never_emits_and_stays_small():
    c = captions.Chunker(SR)
    assert feed(c, silence(20)) == [] and len(c.buf) <= SR and c.flush() is None


def test_continuous_speech_cut_at_quietest_point():
    c = captions.Chunker(SR)
    audio = np.concatenate([voice(6.0), voice(0.15, amp=0.001), voice(3.0)])  # leve queda aos 6 s
    chunks = feed(c, audio)
    assert len(chunks) == 1 and 5.9 <= len(chunks[0]) / SR <= 6.3, len(chunks[0]) / SR


def test_translation_keeps_order_and_falls_back():
    captions.GLib.idle_add = lambda f, *a: f(*a)

    class Overlay:
        def update_text(self, text, final):
            self.text, self.final = text, final

        def update_status(self, *a):
            pass
    calls = []

    def fake_complete(config, instruction, text, timeout=None, system=None):
        calls.append(text)
        if text == "falha":
            raise captions.ai.AIError("fora do ar")
        return text.upper()
    captions.ai.complete = fake_complete
    th = captions.CaptionThread(Overlay(), {"caption_language": "pt"})
    for text, lang in (("hello", "en"), ("já em pt", "pt"), ("falha", "ru")):
        th.pending.append(text)
        th.mt_q.put((text, lang))
    th.mt_q.put(None)
    th._mt_worker()
    assert th.lines == ["HELLO", "já em pt", "falha"]  # pt não vai para a IA; erro mostra o original
    assert calls == ["hello", "falha"] and th.overlay.final and not th.pending


def run_tests():
    failed = False
    for fn in (test_cuts_on_pauses, test_quiet_video_still_cuts, test_silence_only_never_emits_and_stays_small,
               test_continuous_speech_cut_at_quietest_point, test_translation_keeps_order_and_falls_back):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
