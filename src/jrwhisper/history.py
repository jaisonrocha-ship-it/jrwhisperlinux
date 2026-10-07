"""Histórico local dos ditados: ~/.local/share/dictate/history.jsonl (0600, só no seu disco)."""
import json
import os
import time

HISTORY_DIR = os.path.expanduser("~/.local/share/dictate")
HISTORY_FILE = os.path.join(HISTORY_DIR, "history.jsonl")


def add(entry, path=HISTORY_FILE):
    """entry: {"text", "raw", "app", "mode"}; data/hora preenchidas aqui."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    record = {"ts": time.time(), **entry}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load(path=HISTORY_FILE, query="", limit=500):
    """Mais recentes primeiro; filtra por trecho (sem diferenciar maiúsculas)."""
    if not os.path.exists(path):
        return []
    q = query.strip().lower()
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue  # linha corrompida não derruba o histórico
            if not q or q in rec.get("text", "").lower() or q in rec.get("app", "").lower():
                out.append(rec)
    out.reverse()
    return out[:limit]


def prune(retention_days, path=HISTORY_FILE):
    """Remove entradas mais antigas que retention_days (0 = guardar tudo)."""
    if not retention_days or not os.path.exists(path):
        return
    cutoff = time.time() - retention_days * 86400
    keep = [r for r in reversed(load(path, limit=10**9)) if r.get("ts", 0) >= cutoff]
    _rewrite(keep, path)


def clear(path=HISTORY_FILE):
    if os.path.exists(path):
        os.remove(path)


def _rewrite(records, path):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def when(ts):
    """Rótulo curto estilo macOS: hoje 14:05, ontem 09:12, 03/10 18:40."""
    t = time.localtime(ts)
    today = time.localtime()
    if t.tm_yday == today.tm_yday and t.tm_year == today.tm_year:
        return time.strftime("Hoje %H:%M", t)
    if time.time() - ts < 2 * 86400 and (today.tm_yday - t.tm_yday) % 366 == 1:
        return time.strftime("Ontem %H:%M", t)
    return time.strftime("%d/%m %H:%M", t)
