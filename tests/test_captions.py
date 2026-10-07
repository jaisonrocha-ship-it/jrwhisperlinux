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
    audio = np.concatenate([voice(9.0), voice(0.15, amp=0.001), voice(3.0)])  # leve queda aos 9 s
    chunks = feed(c, audio)  # rede de segurança (MAX_CHUNK): sem pausa nem segmentos do ASR
    assert len(chunks) == 1 and 8.9 <= len(chunks[0]) / SR <= 9.3, len(chunks[0]) / SR


def test_asr_cut_keeps_epoch_honest():
    c = captions.Chunker(SR)
    feed(c, voice(3.0))
    epoch = c.epoch
    c.cut(SR)  # frase fechada pelo ASR no 1º segundo
    assert abs(len(c.buf) / SR - 2.0) < 0.06 and c.epoch != epoch


def _thread(fake):
    captions.GLib.idle_add = lambda f, *a: f(*a)
    captions.time.sleep = lambda s: None  # espera de 429 sem atrasar o teste

    class Overlay:
        def update_captions(self, blocks, live):
            self.blocks, self.live = blocks, live

        def update_status(self, *a):
            pass
    captions.ai.complete = fake
    return captions.CaptionThread(Overlay(), {"caption_language": "pt", "caption_translator": "nvidia"})


def _run_mt(th, items):
    for text, lang in items:
        th.pending.append(text)
        th.mt_q.put((text, lang))
    th.mt_q.put(None)
    th._mt_worker()


def test_queued_sentences_go_in_one_call():
    calls = []
    th = _thread(lambda cfg, ins, text, timeout=None, system=None: calls.append(text) or text.upper())
    _run_mt(th, [("hello", "en"), ("world", "en")])
    assert calls == ["<fala>hello world</fala>"] and th.lines == ["HELLO WORLD"]  # marcações saem da tela
    assert not th.pending and th.overlay.blocks == ["HELLO WORLD"] and not th.overlay.live


def test_429_retries_instead_of_showing_original():
    calls = []

    def fake(cfg, ins, text, timeout=None, system=None):
        calls.append(text)
        if len(calls) < 3:
            raise captions.ai.AIError("429 Client Error: Too Many Requests")
        return "olá"
    th = _thread(fake)
    _run_mt(th, [("hello", "en")])
    assert th.lines == ["olá"] and len(calls) == 3


def test_same_language_skips_ai_and_failure_falls_back():
    calls = []

    def fake(cfg, ins, text, timeout=None, system=None):
        calls.append(text)
        raise captions.ai.AIError("fora do ar")
    th = _thread(fake)
    _run_mt(th, [("já em pt", "pt")])
    assert th.lines == ["já em pt"] and calls == []
    th = _thread(fake)
    _run_mt(th, [("hello", "en")])
    assert th.lines == ["hello"] and len(calls) == 1  # sem 429: não insiste, mostra o original


def test_cjk_leak_is_stripped():
    th = _thread(lambda cfg, ins, text, timeout=None, system=None: "O navio chega,我们需要")
    _run_mt(th, [("The ship arrives, we need", "en")])
    assert th.lines == ["O navio chega,"]


def test_hunyuan_uses_official_prompt():
    sent = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "Olá"}}
    real = captions.ai._http.post
    captions.ai._http.post = lambda url, json=None, timeout=None: sent.append(json) or Resp()
    try:
        cfg = {"ai_ollama_model": "hy-mt1.5-1.8b"}
        assert captions.ai.translate_hymt(cfg, "Hello", "pt", "en") == "Olá"
        captions.ai.translate_hymt(cfg, "你好", "pt", "zh")
    finally:
        captions.ai._http.post = real
    en, zh = (m["messages"] for m in sent)
    assert len(en) == 1 and en[0]["content"].startswith("Translate the following segment into Brazilian Portuguese")
    assert zh[0]["content"].startswith("将以下文本翻译为巴西葡萄牙语")  # origem chinesa: template chinês


def test_pick_hunyuan_or_fall_back():
    real = captions._ollama_models
    try:
        captions._ollama_models = lambda cfg: ["qwen2.5:latest", "hy-mt1.5-1.8b:latest"]
        cfg = captions.pick_translator({"caption_translator": "hymt"})
        assert cfg["caption_hymt"] and cfg["ai_ollama_model"] == "hy-mt1.5-1.8b:latest"
        captions._ollama_models = lambda cfg: []
        assert not captions.pick_translator({"caption_translator": "hymt"}).get("caption_hymt")  # sem modelo: automático
    finally:
        captions._ollama_models = real


def test_lens_math():
    from jrwhisper.ui.captionview import MIN_EDGE, lens_edge, lens_map
    line, side = 21.0, 84.0  # 4 linhas de cada lado do foco
    for zoom in (1.2, 1.5, 2.0):
        for reach in (1, 2, 3):
            r = reach * line
            e = lens_edge(zoom, r, side)
            shift0, s0 = lens_map(0, zoom, r, e)
            assert shift0 == 0 and abs(s0 - zoom) < 1e-9  # o foco tem exatamente o aumento pedido
            shift, s_edge = lens_map(side, zoom, r, e)
            if e > MIN_EDGE:  # sem bater no mínimo legível, a borda continua na borda: o cartão não cresce
                assert abs(shift - side) < 0.5, (zoom, reach, shift)
            assert MIN_EDGE <= s_edge < zoom
            sh, _ = lens_map(-side, zoom, r, e)
            assert abs(sh + shift) < 1e-9  # simétrica
            prev = -1e9
            for d in range(0, int(side) + 1, 3):  # a ordem das linhas nunca se inverte
                cur = lens_map(d, zoom, r, e)[0]
                assert cur > prev
                prev = cur


def run_tests():
    failed = False
    for fn in (test_cuts_on_pauses, test_quiet_video_still_cuts, test_silence_only_never_emits_and_stays_small,
               test_continuous_speech_cut_at_quietest_point, test_asr_cut_keeps_epoch_honest,
               test_queued_sentences_go_in_one_call, test_429_retries_instead_of_showing_original,
               test_same_language_skips_ai_and_failure_falls_back, test_cjk_leak_is_stripped,
               test_hunyuan_uses_official_prompt, test_pick_hunyuan_or_fall_back, test_lens_math):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
