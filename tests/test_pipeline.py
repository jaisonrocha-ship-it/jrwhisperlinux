#!/usr/bin/env python3
"""Perfis, atalhos de texto, modos de IA (servidor HTTP falso, sem rede) e histórico."""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import ai, history, pipeline, secrets
from jrwhisper.config import DEFAULT_CONFIG
from jrwhisper.profiles import effective_config, match_profile
from jrwhisper.textproc import apply_case_rules, apply_snippets

secrets.get_key = lambda provider: "nvapi-teste"
CFG = {**DEFAULT_CONFIG, "profiles_enabled": True, "ai_enabled": True}


class FakeNIM(BaseHTTPRequestHandler):
    reply = "Texto reescrito."
    raw = None
    status = 200

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeNIM.last = body
        out = FakeNIM.raw or json.dumps({"choices": [{"message": {"content": FakeNIM.reply}}]}).encode()
        self.send_response(FakeNIM.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def test_profiles():
    assert match_profile(CFG, "kitty")["name"] == "Terminais"
    assert match_profile(CFG, "Guake")["name"] == "Terminais"
    assert match_profile(CFG, "Code")["name"] == "Editores de código"
    assert match_profile(CFG, "vscode-insiders") is None      # "code" não casa dentro de outra palavra
    assert match_profile(CFG, "firefox") is None
    assert match_profile({**CFG, "profiles_enabled": False}, "kitty") is None
    eff = effective_config(CFG, match_profile(CFG, "kitty"))
    assert eff["paste_method"] == "ctrl+shift+v" and eff["final_period"] is False


def test_send_key_per_profile():
    assert effective_config(CFG, match_profile(CFG, "Thunderbird"))["send_key"] == "ctrl+Return"
    assert effective_config(CFG, match_profile(CFG, "slack"))["send_key"] == "Return"
    assert "na verdade" in ai.SYSTEM  # correção no meio da fala: a IA mantém só a versão final


def test_text_rules():
    snippets = {"meu e-mail": "jr@example.com", "meu e-mail pessoal": "pessoal@example.com"}
    assert apply_snippets("Manda para meu e-mail pessoal.", snippets) == "Manda para pessoal@example.com"
    assert apply_snippets("Meu e-mail, por favor", snippets) == "jr@example.com por favor"
    term = {"capitalize": False, "final_period": False}
    assert apply_case_rules("Listar os arquivos.", term) == "listar os arquivos"
    assert apply_case_rules("API key nova.", term) == "API key nova"   # sigla preservada
    assert apply_case_rules("Espere...", term) == "espere..."          # reticências ficam


def test_voice_mode():
    for spoken in ("Modo e-mail, preciso remarcar a reunião.", "modo email preciso remarcar a reunião.",
                   "Modo E mail: preciso remarcar a reunião."):
        mode, rest = ai.detect_voice_mode(CFG, spoken)
        assert mode and mode["id"] == "email", spoken
        assert rest.startswith("Preciso remarcar"), rest
    mode, rest = ai.detect_voice_mode(CFG, "Modo tópicos, comprar pão e leite")
    assert mode["id"] == "topicos" and rest == "Comprar pão e leite"
    assert ai.detect_voice_mode(CFG, "Modo de usar o forno")[0] is None


def test_mode_priority():
    cfg = {**CFG, "ai_default_mode": "corrigir"}
    assert pipeline.choose_mode(cfg, "texto")[0]["id"] == "corrigir"
    assert pipeline.choose_mode(cfg, "texto", forced_mode="ingles")[0]["id"] == "ingles"
    assert pipeline.choose_mode(cfg, "Modo e-mail, oi", forced_mode="ingles")[0]["id"] == "email"
    assert pipeline.choose_mode({**cfg, "ai_enabled": False}, "Modo e-mail, oi")[0] is None


def test_ai_pipeline_with_fake_server():
    server = HTTPServer(("127.0.0.1", 0), FakeNIM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ai.CLOUD["nvidia"] = (f"http://127.0.0.1:{server.server_port}", *ai.CLOUD["nvidia"][1:])  # nunca a NVIDIA real
    try:
        FakeNIM.reply = "<think>pensando…</think>Olá João,\n\nPodemos remarcar?\n\nAtenciosamente,"
        r = pipeline.process(CFG, "Modo e-mail, oi joão podemos remarcar", wm_class="firefox")
        assert r.mode["id"] == "email" and r.ai_error is None
        assert r.text.startswith("Olá João") and "<think>" not in r.text
        assert FakeNIM.last["chat_template_kwargs"] == {"enable_thinking": False}  # nemotron: sem raciocínio

        FakeNIM.status = 500                     # IA fora do ar: cola o original formatado
        r = pipeline.process(CFG, "Modo e-mail, oi joão", wm_class="firefox")
        assert r.ai_error and r.text == "Oi joão."

        FakeNIM.status = 200
        for raw in (b"<html>gateway</html>", b'{"error": "quota"}'):  # 200 com corpo inesperado
            FakeNIM.raw = raw
            r = pipeline.process(CFG, "Modo e-mail, oi joão", wm_class="firefox")
            assert r.ai_error and r.text == "Oi joão."
    finally:
        FakeNIM.status, FakeNIM.raw = 200, None
        server.shutdown()


def test_history():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "h.jsonl")
        history.add({"text": "primeiro", "raw": "primeiro", "app": "kitty", "mode": ""}, path)
        history.add({"text": "segundo e-mail", "raw": "x", "app": "firefox", "mode": "E-mail"}, path)
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"
        assert [r["text"] for r in history.load(path)] == ["segundo e-mail", "primeiro"]
        assert [r["text"] for r in history.load(path, query="E-MAIL")] == ["segundo e-mail"]
        with open(path, "a") as f:
            f.write("linha quebrada\n")
        assert len(history.load(path)) == 2
        old = json.dumps({"ts": 1.0, "text": "antigo"})
        with open(path, "a") as f:
            f.write(old + "\n")
        history.prune(30, path)
        assert [r["text"] for r in history.load(path)] == ["segundo e-mail", "primeiro"]


def run_tests():
    failed = False
    for fn in (test_profiles, test_send_key_per_profile, test_text_rules, test_voice_mode, test_mode_priority,
               test_ai_pipeline_with_fake_server, test_history):
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
