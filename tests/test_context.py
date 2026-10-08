#!/usr/bin/env python3
"""Contexto do campo em foco (AT-SPI de verdade numa janela GTK), seleção PRIMARY recente e uso pela IA."""
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from jrwhisper import ai, context
from jrwhisper.context import Context


def test_atspi_focused_field_and_selection():
    win = Gtk.Window(title="JRWhisper teste contexto")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    label = Gtk.Label(label="Mensagem")
    entry = Gtk.Entry(text="Booking MSC Marcos para amanhã")
    entry.get_accessible().set_name("Mensagem")
    box.add(label)
    box.add(entry)
    win.add(box)
    win.show_all()
    out = {}

    def run():
        time.sleep(0.6)
        wid = subprocess.run(["xdotool", "search", "--name", "JRWhisper teste contexto"],
                             capture_output=True, text=True).stdout.split()[0]
        subprocess.run(["xdotool", "windowactivate", "--sync", wid], timeout=3)
        GLib.idle_add(lambda: (entry.grab_focus(), entry.select_region(0, 11)) and False)
        time.sleep(0.4)
        t = time.perf_counter()
        out["ctx"] = context.capture(int(wid), "python3")
        out["ms"] = (time.perf_counter() - t) * 1000
        GLib.idle_add(Gtk.main_quit)
    threading.Thread(target=run, daemon=True).start()
    GLib.timeout_add_seconds(10, Gtk.main_quit)
    Gtk.main()
    win.destroy()
    ctx = out["ctx"]
    print(f"   capturado em {out['ms']:.0f} ms: {ctx}")
    assert ctx.title == "JRWhisper teste contexto" and ctx.field == "Mensagem"
    assert ctx.selection == "Booking MSC" and ctx.in_field  # seleção dentro do campo editável
    assert out["ms"] < 400


def test_context_texts():
    ctx = Context(app="Thunderbird", title="Re: Booking MSC – Caixa de entrada", field="Mensagem",
                  selection="Olá Marcos, o navio da MSC atraca no TESC na quarta. Abraço, Ana")
    assert ctx.label() == "Thunderbird · Mensagem · seleção 13 palavras"
    assert {"Marcos", "MSC", "TESC", "Ana", "Booking"} <= set(ctx.names())
    assert not {"Olá", "Abraço", "Caixa", "Re"} & set(ctx.names())  # início de frase e interface não são nomes
    p = ctx.prompt()
    assert p.startswith("App: Thunderbird\nJanela: Re: Booking MSC") and "maior evidência" in p
    assert not Context() and Context().prompt() == ""


def test_stale_primary_is_ignored():
    real = context._run
    now = int(time.monotonic() * 1000)
    context._run = lambda cmd: str(now - 5000) if "TIMESTAMP" in cmd else "texto recente"
    assert context._fresh_primary() == "texto recente"           # selecionou há 5 s: vale
    context._run = lambda cmd: str(now - 600000) if "TIMESTAMP" in cmd else "esquecido"
    assert context._fresh_primary() == ""                        # há 10 min: seleção esquecida
    context._run = lambda cmd: "" if "TIMESTAMP" in cmd else "sem dono"
    assert context._fresh_primary() == ""
    context._run = real


def test_ai_gets_context_and_chain_falls_back():
    calls = []

    def fake(config, instruction, text, timeout=None, system=ai.SYSTEM):
        calls.append((config["ai_provider"], text, system, round(timeout, 1)))
        if config["ai_provider"] == "nvidia":
            raise ai.AIError("503")
        return "<ditado>Chego às 3.</ditado>"
    real, ai.complete = ai.complete, fake
    ai._gpu.update(t=time.time(), ok=False, why="sem VRAM")  # local pulada: vai para a nuvem
    try:
        cfg = {"ai_chain": ["ollama", "nvidia", "deepseek"], "ai_timeout": 8}
        out = ai.rewrite(cfg, "chego às 3", {"prompt": "Corrija."}, context="App: Thunderbird")
        assert out == "Chego às 3." and ai.last_provider == "deepseek"
        assert [c[0] for c in calls] == ["nvidia", "deepseek"]
        assert calls[0][1].startswith("<contexto>\nApp: Thunderbird\n</contexto>\n<ditado>")
        assert ai.CONTEXT_RULE in calls[0][2] and calls[0][3] == 3.0  # 3 s por tentativa
        ai._gpu.update(ok=True)
        calls.clear()
        ai.rewrite(cfg, "oi", {"prompt": "Corrija."})
        assert [c[0] for c in calls] == ["ollama"] and ai.CONTEXT_RULE not in calls[0][2]
    finally:
        ai.complete = real
        ai._gpu.update(t=0.0)


def run_tests():
    failed = False
    for fn in (test_atspi_focused_field_and_selection, test_context_texts, test_stale_primary_is_ignored,
               test_ai_gets_context_and_chain_falls_back):
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
