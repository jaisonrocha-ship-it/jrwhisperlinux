"""Contexto do ditado: o campo em foco e a janela dele (outras janelas abertas não contam).

App, título da janela, rótulo/papel do campo (AT-SPI) e o texto selecionado, a maior pista do assunto.
A seleção vem do AT-SPI (do próprio campo) ou da seleção PRIMARY do X11 se foi feita há pouco: a PRIMARY
guarda a última seleção por horas, e uma seleção esquecida não pode virar "a maior evidência".

Roda numa thread enquanto você fala (capture_async); AT-SPI de app travado pode demorar, então tem prazo.
"""
import re
import subprocess
import threading
import time
from dataclasses import dataclass

from .config import _debug_log
from .learning import COMMON

SELECTION_MAX = 2000     # caracteres da seleção enviados à IA
SELECTION_FRESH_S = 120  # PRIMARY mais antiga que isso é seleção esquecida
DEADLINE_S = 0.3         # busca do campo em foco no AT-SPI
NAMES_MAX = 20           # nomes do contexto no vocabulário do Whisper
# palavras de título de janela que não são nome de ninguém
UI_WORDS = set("""caixa entrada saída mensagem mensagens nova novo rascunho rascunhos composição escrever
responder encaminhar enviados lixeira mozilla firefox thunderbird chrome brave chromium google gmail outlook
whatsapp slack discord telegram teams visual studio code terminal editor documento sem título""".split())


@dataclass
class Context:
    app: str = ""
    title: str = ""
    field: str = ""          # rótulo do campo ("Mensagem", "Assunto") ou papel ("campo de texto")
    selection: str = ""
    in_field: bool = False   # a seleção está no campo editável onde o texto vai entrar
    password: bool = False

    def prompt(self):
        """Bloco <contexto> para a IA (vazio se nada útil)."""
        lines = [f"{k}: {v}" for k, v in (("App", self.app), ("Janela", self.title), ("Campo", self.field)) if v]
        if self.selection:
            lines.append(f"Texto selecionado (maior evidência do assunto):\n{self.selection}")
        return "\n".join(lines)

    def names(self):
        """Nomes próprios e siglas da seleção e do título: o Whisper grafa certo já na transcrição.

        Maiúscula em início de frase ("Olá", "Confirma") não é nome; título traz palavras da interface."""
        seen, out = set(), []
        cap = r"(?:[A-ZÀ-Ý][a-zà-ÿ]{2,}|[A-Z][A-Z0-9]{1,})"
        found = [(m.group(), m.start()) for m in re.finditer(rf"\b{cap}\b", self.selection)]
        found = [(w, i) for w, i in found
                 if w.isupper() or not re.search(r"(^|[.!?:]\s*|\n\s*)$", self.selection[:i])]
        found += [(w, -1) for w in re.findall(rf"\b{cap}\b", self.title) if w.lower() not in UI_WORDS]
        for w, _i in found:
            if w.lower() not in COMMON and w.lower() not in seen:
                seen.add(w.lower())
                out.append(w)
        return out[:NAMES_MAX]

    def label(self):
        """Resumo curto para o chip da revisão: "Thunderbird · Mensagem · seleção 42 palavras"."""
        bits = [self.app, self.field]
        if self.selection:
            bits.append(f"seleção {len(self.selection.split())} palavras")
        return " · ".join(b for b in bits if b)

    def __bool__(self):
        return bool(self.app or self.title or self.field or self.selection)


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=1).stdout.decode(errors="ignore").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _fresh_primary():
    """Texto da seleção PRIMARY se feita há menos de SELECTION_FRESH_S (TIMESTAMP do dono vs relógio do X,
    que no Xorg é o CLOCK_MONOTONIC em ms)."""
    ts = _run(["xclip", "-o", "-selection", "primary", "-t", "TIMESTAMP"])
    if not ts.isdigit():
        return ""
    age = (int(time.monotonic() * 1000) - int(ts)) % 2**32 / 1000
    if age > SELECTION_FRESH_S:
        return ""
    return _run(["xclip", "-o", "-selection", "primary"])


def _atspi_focus(pid, deadline):
    """(objeto em foco, nome do app) dentro do app da janela ativa, ou (None, "")."""
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    desktop = Atspi.get_desktop(0)
    app = None
    for i in range(desktop.get_child_count()):
        a = desktop.get_child_at_index(i)
        try:
            if a and a.get_process_id() == pid:
                app = a
                break
        except Exception:
            continue  # app com AT-SPI quebrado (ex.: snap confinado) não derruba a busca
    if app is None:
        return None, ""
    S = Atspi.StateType
    frames = [app.get_child_at_index(i) for i in range(app.get_child_count())]
    frames = [f for f in frames if f and f.get_state_set().contains(S.ACTIVE)] or frames
    queue = list(frames)
    while queue and time.monotonic() < deadline:  # largura primeiro, só no que está visível
        node = queue.pop(0)
        try:
            states = node.get_state_set()
            if states.contains(S.FOCUSED):
                return node, app.get_name()
            if not states.contains(S.SHOWING) and node not in frames:
                continue
            queue.extend(c for c in (node.get_child_at_index(i) for i in range(min(node.get_child_count(), 200))) if c)
        except Exception:
            continue
    return None, app.get_name()


def _describe(node):
    """(rótulo do campo, editável, senha, texto selecionado nele)."""
    from gi.repository import Atspi
    S = Atspi.StateType
    states = node.get_state_set()
    role = node.get_role()
    label = (node.get_name() or "").strip()
    if not label:
        for rel in node.get_relation_set() or []:
            if rel.get_relation_type() == Atspi.RelationType.LABELLED_BY and rel.get_n_targets():
                label = (rel.get_target(0).get_name() or "").strip()
    label = label or {Atspi.Role.ENTRY: "campo de texto", Atspi.Role.TERMINAL: "terminal",
                      Atspi.Role.DOCUMENT_TEXT: "documento", Atspi.Role.DOCUMENT_WEB: "página"}.get(role, "")
    selection = ""
    try:
        text = node.get_text_iface()
        if text and Atspi.Text.get_n_selections(text):
            r = Atspi.Text.get_selection(text, 0)
            selection = Atspi.Text.get_text(text, r.start_offset, r.end_offset)
    except Exception:
        pass
    return label[:60], states.contains(S.EDITABLE), role == Atspi.Role.PASSWORD_TEXT, selection


def capture(win_id, app_class=""):
    t0 = time.monotonic()
    ctx = Context(app=app_class or "", title=_run(["xdotool", "getwindowname", str(win_id)]) if win_id else "")
    pid = _run(["xdotool", "getwindowpid", str(win_id)]) if win_id else ""
    if pid.isdigit():
        try:
            node, app_name = _atspi_focus(int(pid), t0 + DEADLINE_S)
            ctx.app = app_name or ctx.app
            if node is not None:
                ctx.field, editable, ctx.password, sel = _describe(node)
                if sel.strip():
                    ctx.selection, ctx.in_field = sel, editable
        except Exception as e:  # sem AT-SPI (Chrome sem acessibilidade, Wayland): fica com janela + PRIMARY
            _debug_log(f"Contexto: AT-SPI falhou ({type(e).__name__}: {e})")
    if not ctx.selection:
        ctx.selection = _fresh_primary()
    ctx.selection = ctx.selection.strip()[:SELECTION_MAX]
    _debug_log(f"Contexto ({(time.monotonic() - t0) * 1000:.0f} ms): {ctx.label() or 'nada'}"
               + (" · seleção no campo" if ctx.in_field else ""))
    return ctx


def capture_async(win_id, app_class=""):
    """Começa a captura já; .result(timeout) devolve o Context (vazio se não ficou pronto a tempo)."""
    box = {}
    th = threading.Thread(target=lambda: box.setdefault("ctx", capture(win_id, app_class)), daemon=True)
    th.start()

    class Pending:
        @staticmethod
        def result(timeout=0.5):
            th.join(timeout)
            return box.get("ctx") or Context()
    return Pending
