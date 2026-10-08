#!/usr/bin/env python3
"""Estilo dos e-mails: leitura do export do vault, limpeza, filtro de dados de cliente, nota e uso no e-mail."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import ai, pipeline, style
from jrwhisper.config import DEFAULT_CONFIG

THREAD = """---
tags: [tesc, emails]
---
# Booking

### 2026-09-20 10:00 · Cliente · Booking
De: cliente@x.com · Para: eu@tesc.com
Pasta: Caixa de entrada

> Bom dia, pode confirmar o booking?

### 2026-09-20 11:00 · Eu · Re: Booking
De: eu@tesc.com · Para: cliente@x.com
Pasta: Mensagens enviadas

> Bom dia, Marina,
>
> Conforme alinhado, encaminho em anexo a proposta. Peço a gentileza de confirmar.
>
> Atenciosamente,
> Jason Rocha
> +55 11 99999-0000
>
> Em 20/09/2026 10:00, Marina escreveu:
> Bom dia, pode confirmar o booking?

### 2026-09-21 09:00 · Eu · Re: Booking
De: eu@tesc.com · Para: cliente@x.com
Pasta: Itens_Enviados

> (sem corpo de texto)
"""


def test_reads_only_sent_and_cleans():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "booking.md"), "w", encoding="utf-8") as f:
            f.write(THREAD)
        msgs = style.sent_messages(d)
        assert len(msgs) == 1  # recebido fica de fora; "(sem corpo de texto)" é vazio
        date, body = msgs[0]
        assert date == "2026-09-20"
        assert body.startswith("Bom dia, Marina,\n\nConforme alinhado") and body.endswith("Atenciosamente,")
        assert "99999" not in body and "escreveu" not in body  # assinatura e histórico citado saem
        assert style.preview([{"path": d, "filter": "sent"}])[0][1:] == (1, len(body.split()))


def test_closing_only_on_short_line():
    assert style.clean("Obrigado pelo retorno, segue a proposta revisada com os novos valores.\n\nAbs,\nJason") == \
        "Obrigado pelo retorno, segue a proposta revisada com os novos valores.\n\nAbs,"


def test_render_scrubs_client_data():
    raw = json.dumps({"regras": ["Abra com \"Bom dia, Khaleda,\" e o primeiro nome.",
                                 "Cite volumes como \"5.000 tons/mês de bobinas\"."],
                      "expressoes": ["Peço a gentileza", "Bom dia, Lucas", "encaminho em anexo", "5 mil t", "segue o BL"]})
    md = style.render(raw)
    assert "Khaleda" not in md and "Lucas" not in md and "5.000" not in md
    assert "“Bom dia, [nome],”" in md and "- “segue o BL”" in md and "- “Peço a gentileza”" in md
    try:
        style.render("isso não é json")
        assert False
    except ai.AIError:
        pass


def test_note_keeps_user_edits_and_feeds_email_mode():
    with tempfile.TemporaryDirectory() as d:
        note = os.path.join(d, "Pessoal", "Meu estilo de escrita.md")
        style.write_note(note, "## E-mail\n### Regras\n- Abra com Bom dia.")
        with open(note, "a", encoding="utf-8") as f:
            f.write("- Nunca use emoji.\n")  # o usuário edita a nota
        style.write_note(note, "## E-mail\n### Regras\n- Feche com Att.")
        text = open(note, encoding="utf-8").read()
        assert "Feche com Att." in text and "Abra com Bom dia." not in text and "Nunca use emoji." in text
        cfg = dict(DEFAULT_CONFIG, style_note=note, history_enabled=False)
        guide = style.guide(cfg)
        assert "Feche com Att." in guide and "Nunca use emoji." in guide and "jrwhisper:auto" not in guide
        email = ai.find_mode(cfg, "email")
        assert "Nunca use emoji." in pipeline._style(cfg, email)
        assert pipeline._style(cfg, ai.find_mode(cfg, "corrigir")) is None  # só nos modos de e-mail
        assert style.guide(dict(cfg, style_enabled=False)) == ""


def run_tests():
    failed = False
    for fn in (test_reads_only_sent_and_cleans, test_closing_only_on_short_line, test_render_scrubs_client_data,
               test_note_keeps_user_edits_and_feeds_email_mode):
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
