#!/usr/bin/env python3
"""IA ligada: o texto espera a escolha (reescrever, corrigir palavras, colar, copiar, descartar).

Sem janela, rede nem áudio; o desenho e o clique nas palavras são testados com o overlay de verdade.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import dictation, pipeline
from jrwhisper.config import DEFAULT_CONFIG

calls = []
dictation.GLib.idle_add = lambda f, *a: f(*a)
dictation.paste_text = lambda text, win, method="ctrl+v", **kw: calls.append(("paste", text))
dictation.copy_text = lambda text: calls.append(("copy", text))
dictation.press_key = lambda key: calls.append(("key", key))


class FakeOverlay:
    def __init__(self):
        self.shown, self.pick, self.edited, self.text = [], None, False, ""

    def get_final_text(self):
        return self.text

    def update_status(self, text, state=None):
        calls.append(("status", text))

    def show_choices(self, text, modes, selected, on_pick):
        self.shown.append((text, selected))
        self.pick, self.text, self.edited = on_pick, text, False

    def hide_choices(self):
        calls.append(("hide",))


def _session(raw, picks, edit=None, **extra):
    calls.clear()
    cfg = dict(DEFAULT_CONFIG, ai_enabled=True, history_enabled=False, **extra)
    overlay = FakeOverlay()
    thread = dictation.DictateThread(overlay, cfg)
    result = pipeline.process(dict(cfg, ai_enabled=False), raw, wm_class=extra.get("wm"))
    t = threading.Thread(target=thread._choose, args=(raw, result), daemon=True)
    t.start()
    for action in picks:
        time.sleep(0.3)
        if edit and action == "paste":  # usuário corrigiu uma palavra antes de colar
            overlay.text, overlay.edited = overlay.text.replace(*edit), True
        overlay.pick(action)
    t.join(3)
    assert not t.is_alive(), "a escolha final precisa encerrar a espera"
    return overlay, thread


def test_original_then_paste():
    overlay, thread = _session("modo email preciso remarcar a reunião", ["original", "paste"])
    assert overlay.shown[-1] == ("Preciso remarcar a reunião.", "original")  # prefixo de voz some
    assert ("paste", "Preciso remarcar a reunião.") in calls and thread.pasted


def test_copy_and_discard_do_not_paste():
    _, thread = _session("teste de cópia", ["copy"])
    assert ("copy", "Teste de cópia.") in calls and not thread.pasted
    _, thread = _session("teste descartado", ["discard"])
    assert not any(c[0] in ("paste", "copy") for c in calls) and not thread.pasted


def test_send_pastes_then_presses_send_key():
    _session("chego às 3", ["send"])
    assert calls[-4:-2] == [("paste", "Chego às 3."), ("key", "Return")], calls
    assert ("status", "Enviado") in calls
    _session("segue o relatório", ["send"], profiles_enabled=True, wm="thunderbird")  # e-mail: Ctrl+Enter
    assert ("key", "ctrl+Return") in calls
    _session("só colar", ["paste"])
    assert not any(c[0] == "key" for c in calls)  # Enter normal nunca envia


def test_raw_is_pure_whisper_output():
    overlay, _ = _session("modo email oi joão vírgula tudo bem", ["raw", "paste"])
    assert overlay.shown[-1] == ("modo email oi joão vírgula tudo bem", "raw")  # sem formatação nem comandos
    assert ("paste", "modo email oi joão vírgula tudo bem") in calls


def test_edited_word_is_pasted():
    _session("reunião com o marcus amanhã", ["paste"], edit=("marcus", "Marcos"))
    assert ("paste", "Reunião com o Marcos amanhã.") in calls


def test_overlay_word_edit():
    import cairo
    from jrwhisper.ui.overlay import WhisperFlowOverlay
    o = WhisperFlowOverlay(dict(DEFAULT_CONFIG, ai_enabled=True))
    o.show_choices("Reunião com o Marcus amanhã.", [], "original", lambda a: None)
    o.text_alpha, o.box_h = 1.0, 400
    o._on_draw(o, cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, o.W, o.H)))
    words = [r for r in o._chip_rects if isinstance(r[4], tuple)]
    assert [o.text[w[4][1]:w[4][2]] for w in words] == "Reunião com o Marcus amanhã.".split()
    x, y, w, h, word = words[3]
    o._edit_word(word[1], word[2], (x, y, w, h))
    o._editor[1].set_text("Marcos")
    o._finish_edit(True)
    assert o.get_final_text() == "Reunião com o Marcos amanhã." and o.edited
    o._edit_word(word[1], word[2], (x, y, w, h))
    o._editor[1].set_text("")  # vazio apaga a palavra sem deixar espaço duplo
    o._finish_edit(True)
    assert o.get_final_text() == "Reunião com o amanhã."
    o.destroy()


def test_overlay_keys_and_scroll():
    import cairo
    from gi.repository import Gdk
    from jrwhisper.ui.overlay import WhisperFlowOverlay
    o = WhisperFlowOverlay(dict(DEFAULT_CONFIG, ai_enabled=True))
    picked = []
    modes = [{"id": "email", "name": "E-mail"}, {"id": "ingles", "name": "Inglês"}]
    long_text = " ".join(f"Linha {i} de um e-mail comprido que ocupa a largura toda." for i in range(12))
    o.show_choices(long_text, modes, "original", picked.append)

    def key(keyval, ctrl=False):
        ev = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        ev.key.keyval = keyval
        ev.key.state = Gdk.ModifierType.CONTROL_MASK if ctrl else 0
        o.choices_busy = False
        return o._on_key(o, ev)
    assert key(Gdk.KEY_Return) and key(Gdk.KEY_Escape) and key(Gdk.KEY_c, ctrl=True)
    ev = Gdk.Event.new(Gdk.EventType.KEY_PRESS)  # Shift+Enter: colar e enviar
    ev.key.keyval, ev.key.state = Gdk.KEY_Return, Gdk.ModifierType.SHIFT_MASK
    o.choices_busy = False
    assert o._on_key(o, ev) and picked.pop() == "send"
    assert key(Gdk.KEY_1) and key(Gdk.KEY_3) and key(Gdk.KEY_KP_2) and key(Gdk.KEY_0)
    assert picked == ["paste", "discard", "copy", "original", "ingles", "email", "raw"], picked
    picked.pop()
    key(Gdk.KEY_9)  # só 3 opções: o 9 não escolhe nada
    assert len(picked) == 6
    assert not key(Gdk.KEY_a)  # outras teclas não são engolidas

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, o.W, o.H)
    o.text_alpha, o.box_h = 1.0, 400
    o._on_draw(o, cairo.Context(surface))
    first = o._visible_lines(cairo.Context(surface))[0][0]
    assert first.startswith("Linha 0") and o._more == (False, True)  # revisão começa do topo
    o._scroll = 99  # rolar além do fim para na última página
    last = o._visible_lines(cairo.Context(surface))
    assert o._more == (True, False) and last[-1][0].endswith("comprido que ocupa a largura toda.")
    o.destroy()


def test_hotkey_second_press():
    quit_calls = []
    dictation.Gtk.main_quit = lambda: quit_calls.append(1)
    overlay = FakeOverlay()
    thread = dictation.DictateThread(overlay, dict(DEFAULT_CONFIG))
    thread.hotkey()                          # nada dito ainda: cancela
    assert quit_calls == [1]
    thread.stage = "listening"
    thread.hotkey()                          # falando: encerra e transcreve, sem voltar a ouvir
    assert thread.finish_now and thread.stop_after and quit_calls == [1]
    thread.stage = "busy"
    thread.finish_now = False
    thread.hotkey()                          # transcrevendo: ignora
    assert not thread.finish_now and quit_calls == [1]
    # revisão: 2º toque cola
    thread = dictation.DictateThread(FakeOverlay(), dict(DEFAULT_CONFIG, ai_enabled=True))
    raw = "teste do atalho"
    t = threading.Thread(target=thread._choose, args=(raw, pipeline.process(DEFAULT_CONFIG, raw)), daemon=True)
    calls.clear()
    t.start()
    time.sleep(0.3)
    assert thread.stage == "choosing"
    thread.hotkey()
    t.join(3)
    assert ("paste", "Teste do atalho.") in calls and thread.stage == "busy"


def run_tests():
    failed = False
    for fn in (test_original_then_paste, test_copy_and_discard_do_not_paste, test_send_pastes_then_presses_send_key,
               test_raw_is_pure_whisper_output, test_edited_word_is_pasted,
               test_overlay_word_edit, test_overlay_keys_and_scroll, test_hotkey_second_press):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
