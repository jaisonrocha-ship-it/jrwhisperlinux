"""Histórico local dos ditados: ~/.local/share/dictate/history.jsonl (0600, só no seu disco).

Com keep_audio, o áudio de cada ditado fica em audio/<ts>.opus (~16 MB por hora de fala): base para
re-transcrever, cadastrar a sua voz e treinar o Whisper. Some junto com a entrada.
"""
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import date, timedelta

HISTORY_DIR = os.path.expanduser("~/.local/share/dictate")
HISTORY_FILE = os.path.join(HISTORY_DIR, "history.jsonl")


def audio_dir(path=HISTORY_FILE):
    return os.path.join(os.path.dirname(path), "audio")


def keep_audio(wav_path, ts, path=HISTORY_FILE):
    """Comprime o WAV em Opus numa thread (o ditado não espera). Devolve o caminho do .opus.

    O WAV é movido antes: o próximo trecho (mãos livres) pode sobrescrever o original.
    """
    d = audio_dir(path)
    os.makedirs(d, mode=0o700, exist_ok=True)
    out = os.path.join(d, f"{ts:.3f}.opus")
    tmp = out + ".wav"
    shutil.move(wav_path, tmp)

    def encode():
        try:
            subprocess.run(["nice", "-n", "19", "ffmpeg", "-y", "-loglevel", "error", "-i", tmp,
                            "-c:a", "libopus", "-b:a", "24k", "-application", "voip", out],
                           timeout=60, check=True)
            os.chmod(out, 0o600)
        except (OSError, subprocess.SubprocessError):
            pass  # sem ffmpeg/libopus: fica sem áudio, o texto já está salvo
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    threading.Thread(target=encode, daemon=True).start()
    return out


def add(entry, path=HISTORY_FILE, ts=None):
    """entry: {"text", "raw", "app", "mode"} e, se houver, "ai_text" (antes das correções), "edits"
    ([velho, novo]), "wid" e "audio"; data/hora preenchidas aqui."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    record = {"ts": ts or time.time(), **entry}
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
    d = audio_dir(path)
    for name in os.listdir(d) if os.path.isdir(d) else []:
        f = os.path.join(d, name)
        if os.path.getmtime(f) < cutoff:
            os.remove(f)


def clear(path=HISTORY_FILE):
    if os.path.exists(path):
        os.remove(path)
    shutil.rmtree(audio_dir(path), ignore_errors=True)


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
    day, today = date.fromtimestamp(ts), date.fromtimestamp(time.time())
    if day == today:
        return time.strftime("Hoje %H:%M", t)
    if day == today - timedelta(days=1):  # data, não tm_yday: 1º/jan após ano de 365 dias errava
        return time.strftime("Ontem %H:%M", t)
    return time.strftime("%d/%m %H:%M", t)
