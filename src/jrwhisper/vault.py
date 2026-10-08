"""Cópia dos ditados no Obsidian: uma nota por dia (<pasta>/AAAA-MM-DD.md), um bloco por ditado.

Só acrescenta no fim: a nota é sua para editar. A retenção do histórico não apaga nada aqui.
"""
import os
import time

from .config import _debug_log


def _quote(text):
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def block(ts, text, app="", mode="", raw="", where=""):
    """### 14:05 · Thunderbird · E-mail / contexto em itálico / texto / bruto recolhido (se difere)."""
    head = " · ".join(b for b in (time.strftime("%H:%M", time.localtime(ts)), app, mode) if b)
    out = [f"### {head}"]
    if where:
        out.append(f"*{where}*\n")
    out.append(text.strip())
    if raw and raw.strip() != text.strip():
        out.append(f"\n> [!quote]- Bruto\n{_quote(raw.strip())}")
    return "\n".join(out) + "\n\n"


def append(folder, ts, text, **meta):
    """Acrescenta o ditado na nota do dia; cria a pasta e a nota (frontmatter + título) se faltarem."""
    if not folder or not text.strip():
        return None
    folder = os.path.expanduser(folder)
    path = os.path.join(folder, time.strftime("%Y-%m-%d", time.localtime(ts)) + ".md")
    try:
        os.makedirs(folder, exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as f:
            if new:
                f.write(f"---\ntags: [ditado]\n---\n# Ditados · {time.strftime('%d/%m/%Y', time.localtime(ts))}\n\n")
            f.write(block(ts, text, **meta))
        return path
    except OSError as e:  # vault fora do ar (disco desmontado) não pode derrubar o ditado
        _debug_log(f"Obsidian: {e}")
        return None


def paragraphs(blocks, per=5):
    """Legendas: frases agrupadas em parágrafos (um parágrafo único de 10 min é ilegível)."""
    return "\n\n".join(" ".join(blocks[i:i + per]) for i in range(0, len(blocks), per))
