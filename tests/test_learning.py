#!/usr/bin/env python3
"""Correções da revisão viram regra do dicionário (filtro, 2ª vez, selo no overlay) e o áudio vai para o histórico."""
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import history, learning
from jrwhisper.config import DEFAULT_CONFIG
from jrwhisper.textproc import format_transcript


def test_filter():
    assert learning.candidate("Paulo", "Pablo,") == ("Paulo", "Pablo")   # grafia: aprende
    assert learning.candidate("Marcus", "Marcos") == ("Marcus", "Marcos")
    assert learning.candidate("paulo", "Paulo") is None                   # só maiúscula
    assert learning.candidate("reunião", "almoço") is None                # troca de palavra
    assert learning.candidate("bom dia", "boa tarde") is None             # mais de uma palavra
    assert learning.candidate("Pablo", "") is None                        # apagou a palavra
    assert learning.needs_confirmation("mais", "mas")                     # comum: espera a 2ª
    assert not learning.needs_confirmation("Paulo", "Pablo")
    assert not learning.needs_confirmation("arcelor", "arcelormittal")    # rara: aprende já
    assert learning.needs_confirmation("API", "APP")                      # sigla por sigla: espera a 2ª


def test_apply_rules():
    cfg = {**DEFAULT_CONFIG, "word_overrides": {}, "learn_counts": {}}
    learned, pending = learning.apply(cfg, [("Paulo", "Pablo"), ("mais", "mas")])
    assert learned == ["Pablo"] and pending == ["mas"]
    assert cfg["word_overrides"] == {"paulo": "Pablo"} and cfg["initial_prompt"].endswith(", Pablo")
    assert format_transcript("falei com o paulo hoje", cfg) == "Falei com o Pablo hoje."
    learned, pending = learning.apply(cfg, [("mais", "mas")])        # 2ª vez igual: vira regra
    assert learned == ["mas"] and cfg["word_overrides"]["mais"] == "mas" and not cfg["learn_counts"]
    assert cfg["initial_prompt"].count("Pablo") == 1 and "mas" not in cfg["initial_prompt"].split(", ")
    learning.apply(cfg, [("Paulo", "Pablo")])                         # repetir não duplica o vocabulário
    assert cfg["initial_prompt"].count("Pablo") == 1
    assert learning.apply(cfg, [("API", "APP"), ("API", "APP")]) == ([], ["APP"])  # 2× no mesmo ditado = 1ª vez
    assert "api" not in cfg["word_overrides"]
    assert learning.apply(cfg, [("API", "APP")]) == (["APP"], [])     # confirmou em outro ditado


def test_learn_rereads_config():
    saved = {}
    disk = {**DEFAULT_CONFIG, "word_overrides": {"x": "y"}, "learn_counts": {}}
    learning.load_config, learning.save_config = lambda: dict(disk), saved.update
    assert learning.learn([("Paulo", "Pablo")]) == (["Pablo"], [])
    assert saved["word_overrides"] == {"x": "y", "paulo": "Pablo"}    # não perde o que já estava salvo


def test_overlay_learn_chips():
    import cairo
    from jrwhisper.ui.overlay import WhisperFlowOverlay
    o = WhisperFlowOverlay(dict(DEFAULT_CONFIG, ai_enabled=True))
    o.show_choices("Falei com o Paulo sobre o embarque.", [{"id": "email", "name": "E-mail"}], "original",
                   lambda a: None)
    o.text_alpha, o.box_h = 1.0, 400
    ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, o.W, o.H))
    o._on_draw(o, ctx)
    word = next(r for r in o._chip_rects if isinstance(r[4], tuple) and o.text[r[4][1]:r[4][2]] == "Paulo")
    o._edit_word(word[4][1], word[4][2], word[:4])
    o._editor[1].set_text("Pablo")
    o._finish_edit(True)
    assert o.corrections == [{"old": "Paulo", "new": "Pablo", "remember": True}]
    o._on_draw(o, ctx)
    chip = next(r for r in o._chip_rects if r[4] == ("learn", 0))
    o._on_press(o, type("E", (), {"x": chip[0] + 2, "y": chip[1] + 2})())  # clique no selo: não lembrar
    assert o.corrections[0]["remember"] is False
    o.show_choices("Bom dia, segue o e-mail.", [], "email", lambda a: None)  # IA reescreveu sem a palavra
    o._on_draw(o, ctx)
    assert not any(r[4] == ("learn", 0) for r in o._chip_rects)  # selo some junto com a palavra
    o.destroy()


def test_audio_kept_and_pruned():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "h.jsonl")
        wav = os.path.join(d, "last.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=220:d=1",
                        "-ar", "16000", "-ac", "1", wav], check=True)
        ts = time.time()
        out = history.keep_audio(wav, ts, path)
        history.add({"text": "oi", "raw": "oi", "audio": out}, path, ts=ts)
        assert not os.path.exists(wav)  # movido: o próximo trecho pode gravar no mesmo lugar
        for _ in range(50):
            if os.path.exists(out) and not os.path.exists(out + ".wav"):
                break
            time.sleep(0.1)
        assert os.path.getsize(out) > 500 and oct(os.stat(out).st_mode & 0o777) == "0o600"
        assert history.load(path)[0]["audio"] == out
        os.utime(out, (1, 1))  # áudio antigo some na poda, como a entrada
        history.prune(30, path)
        assert not os.path.exists(out)
        history.clear(path)
        assert not os.path.exists(history.audio_dir(path))


def run_tests():
    failed = False
    for fn in (test_filter, test_apply_rules, test_learn_rereads_config, test_overlay_learn_chips,
               test_audio_kept_and_pruned):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
