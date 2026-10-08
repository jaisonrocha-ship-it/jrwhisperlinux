#!/usr/bin/env python3
"""Léxico de logística: filtro de jargão, sigla ambígua, nota com riscados, pistas, traduções e prompt do Whisper."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import lexicon
from jrwhisper.config import DEFAULT_CONFIG

GLOSSARY = {"terms": [
    {"termo": "demurrage", "sigla": "", "domain": "shipping"},
    {"termo": "laytime", "sigla": "", "domain": "shipping"},
    {"termo": "preço", "sigla": "", "domain": "economia"},                       # comum: fora
    {"termo": "polar stratospheric cloud", "sigla": "PSC", "domain": "shipping"},  # você usa a sigla
    {"termo": "come to", "sigla": "", "domain": "shipping"},                     # frase comum: fora
    {"termo": "Brooklyn Bridge", "sigla": "", "domain": "shipping"},             # nome próprio: fora
    {"termo": "breakbulk", "sigla": "", "domain": "shipping"},                   # só nos livros
    {"termo": "metacenter", "sigla": "", "domain": "shipping"},                  # livro raro: fora
]}


def _setup(d):
    with open(os.path.join(d, "g.json"), "w") as f:
        json.dump(GLOSSARY, f)
    emails = os.path.join(d, "emails")
    os.makedirs(emails)
    with open(os.path.join(emails, "t.md"), "w") as f:
        f.write("### 2026-09-01 · Eu · X\nPasta: Mensagens enviadas\n\n> Bom dia, o laytime estourou e a demurrage "
                "vai ser cobrada. Inspeção PSC amanhã, come to the office, preço ok.\n> Atenciosamente,\n")
    book = os.path.join(d, "livros", "port-management")
    os.makedirs(book)
    with open(os.path.join(book, "c1.md"), "w") as f:
        f.write("breakbulk " * 30 + "metacenter demurrage")
    lexicon.DICTS = [os.path.join(d, "dict")]
    with open(lexicon.DICTS[0], "w") as f:
        f.write("preço\ncome\nto\nthe\noffice\n")
    return dict(DEFAULT_CONFIG, lexicon_glossary=os.path.join(d, "g.json"), lexicon_books=os.path.join(d, "livros"),
                lexicon_note=os.path.join(d, "Léxico de logística.md"), history_enabled=False,
                style_sources=[{"path": emails, "filter": "sent"}])


def test_build_and_note():
    with tempfile.TemporaryDirectory() as d:
        cfg = _setup(d)
        lexicon.history.load = lambda limit=0: []
        terms = lexicon.build(cfg)
        names = [t[0] for t in terms]
        assert names[:3] == ["demurrage", "laytime", "PSC"] or set(names[:3]) == {"demurrage", "laytime", "PSC"}
        assert "breakbulk" in names and "metacenter" not in names  # livro: ≥20 ocorrências
        assert not {"preço", "come to", "Brooklyn Bridge", "polar stratospheric cloud"} & set(names)
        lexicon.write(cfg, terms)
        text = open(cfg["lexicon_note"], encoding="utf-8").read()
        assert "| laytime |  | 1 |  |" in text and "| estufagem | stuffing |" in text and "## Meus termos" in text
        # você risca um termo e acrescenta outro; recriar mantém o riscado
        text = text.replace("| breakbulk |", "| ~~breakbulk~~ |").replace(
            "## Meus termos\n| Termo | Sigla |\n| --- | --- |\n", "## Meus termos\n| Termo | Sigla |\n| --- | --- |\n| TESC | |\n")
        open(cfg["lexicon_note"], "w", encoding="utf-8").write(text)
        lexicon.write(cfg, terms)
        text = open(cfg["lexicon_note"], encoding="utf-8").read()
        assert "| ~~breakbulk~~ |" in text and "| TESC | |" in text
        lex = lexicon.load(cfg)
        loaded = [t[0] for t in lex["terms"]]
        assert loaded[0] == "TESC" and "breakbulk" not in loaded and "demurrage" in loaded
        assert lexicon.load(dict(cfg, lexicon_enabled=False)) is None


def test_hints_translations_and_whisper_budget():
    lex = {"terms": [("demurrage", "", 3), ("laytime", "", 2), ("dunnage", "", 1), ("breakbulk", "", 0)],
           "pt_en": dict(lexicon.TRANSLATIONS)}
    assert lexicon.hints(lex, "o laitime estourou e vai ter demorage, falta danage") == ["laytime", "demurrage", "dunnage"]
    assert lexicon.hints(lex, "não sei se o contêiner chegou hoje") == []
    assert lexicon.hints(lex, "a demurrage foi paga") == []  # já certo: sem pista
    pairs = lexicon.translations(lex, "A estufagem atrasou e a peação das bobinas de aço será no plano de estivagem")
    assert ("estufagem", "stuffing") in pairs and ("peação", "lashing") in pairs
    assert ("bobina de aço", "steel coil") in pairs and ("plano de estivagem", "stowage plan") in pairs
    assert ("estivagem", "stowage") not in pairs  # a frase mais longa ganha
    assert ("demurrage", "sobre-estadia") in lexicon.translations(lex, "they charged demurrage", "pt")
    cfg_terms = lexicon.whisper_terms(lex, "Termos: laytime, BL")
    assert cfg_terms == ["demurrage", "dunnage"]  # sem repetir o vocabulário, sem os que só estão nos livros
    many = {"terms": [(f"termo{i:03d}xyz", "", 10) for i in range(100)], "pt_en": {}}
    assert sum(len(w) + 2 for w in lexicon.whisper_terms(many)) <= lexicon.WHISPER_CHARS


def test_guidance_keeps_correct_terms():
    lex = {"terms": [("dunnage", "", 1)], "pt_en": dict(lexicon.TRANSLATIONS)}
    real = lexicon.load
    lexicon.load = lambda cfg: lex
    try:
        g = lexicon.ai_guidance({}, "falta danage pra peação no porão", {"id": "corrigir", "prompt": ""})
        assert "mantenha como estão): peação, porão" in g and "dunnage" in g
        g = lexicon.ai_guidance({}, "a estufagem atrasou", {"id": "ingles", "prompt": ""})
        assert "estufagem → stuffing" in g
        assert lexicon.ai_guidance({}, "tudo certo por aqui", {"id": "corrigir", "prompt": ""}) is None
    finally:
        lexicon.load = real


def run_tests():
    failed = False
    for fn in (test_build_and_note, test_hints_translations_and_whisper_budget, test_guidance_keeps_correct_terms):
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
