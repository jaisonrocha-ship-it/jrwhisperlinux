#!/usr/bin/env python3
"""Cópia no Obsidian: nota do dia, bloco por ditado, bruto recolhido, contexto e legendas."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import dictation, vault
from jrwhisper.config import DEFAULT_CONFIG
from jrwhisper.context import Context
from jrwhisper.pipeline import Result

TS = time.mktime((2026, 10, 8, 14, 5, 0, 0, 0, -1))


def test_daily_note_blocks():
    with tempfile.TemporaryDirectory() as d:
        folder = os.path.join(d, "Ditados")
        path = vault.append(folder, TS, "Olá Gülsah,\n\nConfirmo o booking.\n\nAtenciosamente,", app="Thunderbird",
                            mode="E-mail", raw="olá gulsa confirmo o booking", where="Re: Booking MSC · Mensagem")
        vault.append(folder, TS + 420, "Chego às 3 no terminal.", app="WhatsApp", raw="Chego às 3 no terminal.")
        assert path.endswith("Ditados/2026-10-08.md")
        note = open(path, encoding="utf-8").read()
        assert note.startswith("---\ntags: [ditado]\n---\n# Ditados · 08/10/2026\n\n### 14:05 · Thunderbird · E-mail\n")
        assert "*Re: Booking MSC · Mensagem*\n\nOlá Gülsah,\n\nConfirmo o booking." in note  # parágrafos mantidos
        assert "> [!quote]- Bruto\n> olá gulsa confirmo o booking" in note
        assert "### 14:12 · WhatsApp\nChego às 3 no terminal.\n" in note
        assert note.count("[!quote]") == 1  # bruto igual ao final não se repete
        assert note.count("# Ditados") == 1  # o título só na criação
        assert vault.append(folder, TS, "   ") is None and vault.append("", TS, "oi") is None


def test_captions_paragraphs():
    assert vault.paragraphs([f"Frase {i}." for i in range(7)], per=5) == \
        "Frase 0. Frase 1. Frase 2. Frase 3. Frase 4.\n\nFrase 5. Frase 6."


def test_dictation_writes_even_without_history():
    with tempfile.TemporaryDirectory() as d:
        cfg = dict(DEFAULT_CONFIG, history_enabled=False, obsidian_enabled=True, obsidian_dir=d)
        th = dictation.DictateThread(None, cfg, wm_class="thunderbird")
        th._ctx = Context(app="Thunderbird", title="Re: Booking", field="Mensagem", selection="segredo do cliente")
        th._remember("chego as 3", Result(text="Chego às 3.", mode={"name": "Corrigir"}))
        note = open(os.path.join(d, os.listdir(d)[0]), encoding="utf-8").read()
        assert "· Thunderbird · Corrigir\n*Re: Booking · Mensagem*\n\nChego às 3." in note
        assert "segredo" not in note  # a seleção é só contexto: não vai para a nota


def run_tests():
    failed = False
    for fn in (test_daily_note_blocks, test_captions_paragraphs, test_dictation_writes_even_without_history):
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
