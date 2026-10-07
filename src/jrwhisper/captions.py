"""Legendas ao vivo: o som do computador transcrito e traduzido enquanto toca (`dictate --captions`).

Captura → Chunker (corta nas pausas da fala, no máx. MAX_CHUNK s) → fila de transcrição →
fila de tradução → overlay. Uma thread por etapa: as frases saem na ordem e a tradução de uma
frase roda enquanto a próxima é transcrita. Inglês sai do próprio Whisper (task "translate"),
sem IA; os outros idiomas usam o provedor de IA configurado (NVIDIA NIM ou Ollama).
"""
import os
import queue
import threading
import time
import wave

import numpy as np
from gi.repository import GLib, Gtk

from . import ai, history
from .audio import SYSTEM_AUDIO, AudioCapture
from .config import RUNTIME_DIR, TICK_INTERVAL, _debug_log
from .paste import copy_text
from .transcribe import Transcriber

LANG_NAMES = {"pt": "português do Brasil", "en": "inglês", "es": "espanhol"}
MIN_VOICED = 0.3     # s de som numa frase para valer a pena transcrever
PAUSE_SECS = 0.45    # pausa que fecha a frase
MAX_CHUNK = 7.0      # fala sem pausa: corta no ponto mais baixo dos últimos 2 s
QUIET_FLOOR = 0.0001  # áudio digital: silêncio é ~0; vídeo baixinho (volume do app em 15%) fica em ~0,0003
IDLE_SECS = 60       # tanto tempo sem som: o vídeo acabou
INTERIM_EVERY = 1.0  # s entre prévias da frase em andamento
SYSTEM = ("Você traduz legendas de vídeo em tempo real. Traduza fielmente e com naturalidade, "
          "sem comentários, sem aspas, sem explicações. Nomes próprios ficam como estão.")


def _write_wav(path, audio, sr):
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if 1e-4 < peak < 0.5:  # vídeo baixinho chega a -70 dBFS e o Whisper ouve outra língua: normaliza
        audio = audio * (0.5 / peak)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


class Chunker:
    """Corta o áudio em frases: pausa (volume abaixo de 30% da média da fala por PAUSE_SECS) ou,
    em fala contínua/música de fundo, o ponto mais baixo dos últimos 2 s ao passar de MAX_CHUNK."""

    def __init__(self, sr):
        self.sr = sr
        self.buf = np.zeros(0, np.float32)
        self.avg = 0.0      # volume médio da fala (EMA)
        self.quiet = 0.0    # s de pausa contínua no fim do buffer
        self.voiced = 0.0   # s com som no buffer

    def feed(self, samples):
        """Acrescenta áudio; devolve as frases fechadas."""
        if len(samples) == 0:
            return []
        self.buf = np.concatenate([self.buf, samples])
        secs = len(samples) / self.sr
        rms = float(np.sqrt(np.mean(samples ** 2)))
        if rms < max(0.3 * self.avg, QUIET_FLOOR):
            self.quiet += secs
        else:
            self.quiet = 0.0
            self.voiced += secs
            self.avg = rms if not self.avg else 0.9 * self.avg + 0.1 * rms
        if self.quiet >= PAUSE_SECS:
            if self.voiced >= MIN_VOICED:
                return [self._take(len(self.buf))]
            self.buf = self.buf[-int(0.3 * self.sr):]  # só silêncio: guarda um respiro antes da próxima fala
            self.voiced = 0.0
        elif len(self.buf) >= MAX_CHUNK * self.sr:
            frame = int(0.1 * self.sr)
            tail = self.buf[-2 * self.sr:]
            energy = [np.mean(tail[i:i + frame] ** 2) for i in range(0, len(tail) - frame, frame // 2)]
            cut = len(self.buf) - len(tail) + int(np.argmin(energy)) * (frame // 2) + frame // 2
            return [self._take(cut)]
        return []

    def _take(self, n):
        chunk, self.buf = self.buf[:n], self.buf[n:]
        self.voiced = len(self.buf) / self.sr if self.quiet == 0 else 0.0
        self.quiet = 0.0
        return chunk

    def flush(self):
        chunk = self.buf if self.voiced >= MIN_VOICED else None
        self.buf = np.zeros(0, np.float32)
        return chunk


class CaptionThread(threading.Thread):
    """Mesma interface que o DictateThread usa com o overlay/run_overlay_mode: run, hotkey,
    cancelled, restore_audio."""

    def __init__(self, overlay, config, **_):
        super().__init__(daemon=True)
        self.overlay = overlay
        self.config = config
        self.sr = config.get("sample_rate", 16000)
        self.target = config.get("caption_language", "pt")  # "" = sem tradução
        self.cancelled = False
        self.stop = threading.Event()
        self.asr_q, self.mt_q = queue.Queue(), queue.Queue()
        self.asr_busy = False
        self.lines = []         # legendas prontas (já traduzidas)
        self.pending = []       # transcritas, esperando a tradução (aparecem esmaecidas)
        self.interim = ""       # prévia da frase em andamento
        self.language = None    # idioma falado, travado após 2 detecções iguais
        self._seen = []
        self._lock = threading.Lock()
        self._warned = False

    def hotkey(self):
        """2º toque no atalho: encerra (o que já foi captado ainda é legendado)."""
        self.stop.set()
        return False

    def restore_audio(self):  # nada pausado nem abaixado: o som é o que se quer legendar
        pass

    # ── laço de captura ────────────────────────────────────────────
    def run(self):
        workers = [threading.Thread(target=self._asr_worker, daemon=True),
                   threading.Thread(target=self._mt_worker, daemon=True)]
        try:
            capture = AudioCapture(SYSTEM_AUDIO, self.sr)
            capture.start()
            self.transcriber = Transcriber(self.config)
            for w in workers:
                w.start()
            label = "Legendas" + (f" → {self.target.upper()}" if self.target else "")
            self._status(f"{label} · aguardando som…", "status-waiting")
            chunker = Chunker(self.sr)
            last_sound = last_interim = time.time()
            listening = False
            while not self.stop.is_set() and not self.cancelled:
                time.sleep(TICK_INTERVAL)
                rms = capture.get_rms()
                GLib.idle_add(self.overlay.update_level, rms, 0.01)
                for chunk in chunker.feed(capture.get_audio_float32()):
                    self.interim = ""
                    self.asr_q.put(("final", chunk))
                now = time.time()
                if rms > QUIET_FLOOR:
                    last_sound = now
                    if not listening:
                        listening = True
                        self._status(f"{label} · atalho encerra", "status-listening")
                elif now - last_sound > IDLE_SECS:
                    _debug_log("Legendas: sem som, encerrando")
                    break
                if (chunker.voiced >= 0.5 and now - last_interim >= INTERIM_EVERY
                        and self.asr_q.empty() and not self.asr_busy):
                    last_interim = now
                    self.asr_q.put(("interim", chunker.buf.copy()))
            capture.stop()
            tail = chunker.flush()
            if tail is not None:
                self.asr_q.put(("final", tail))
            self.asr_q.put(None)
            if not self.cancelled:
                self._status("Terminando a legenda…", "status-transcribing")
            for w in workers:
                w.join(60)
            self._finish()
        except Exception as e:
            _debug_log(f"Legendas: erro {e!r}")
            self._status("Erro nas legendas", "status-error")
            time.sleep(2)
        if not self.cancelled:
            GLib.idle_add(self._cleanup_gtk)

    def _finish(self):
        text = " ".join(self.lines).strip()
        if self.cancelled or not text:
            self._status("Nada para legendar", "status-error")
            return
        copy_text(text)
        if self.config.get("history_enabled"):
            try:
                history.add({"text": text, "raw": "", "app": "Legendas", "mode": self.target or ""})
            except OSError as e:
                _debug_log(f"Histórico: {e}")
        self._status("Legenda copiada", "status-success")
        time.sleep(1.5)

    def _cleanup_gtk(self):
        def _done():
            self.overlay.destroy()
            Gtk.main_quit()
        self.overlay.fade_out(_done)

    # ── etapas ─────────────────────────────────────────────────────
    def _asr_worker(self):
        whisper_translates = self.target == "en"  # o Whisper só traduz para inglês, e de graça
        while True:
            item = self.asr_q.get()
            if item is None:
                self.mt_q.put(None)
                return
            kind, audio = item
            self.asr_busy = True
            path = os.path.join(RUNTIME_DIR, f"dictate_caption_{kind}.wav")
            try:
                _write_wav(path, audio, self.sr)
                # idioma livre (áudio limpo detecta bem), sem o vocabulário de ditado; transcriber é só desta thread
                self.transcriber.config = dict(self.config, language=self.language or "auto", auto_languages=[],
                                               initial_prompt="",
                                               task="translate" if whisper_translates else "transcribe")
                text = self.transcriber.transcribe_file(path, denoise=False, second_pass=False)
            except Exception as e:  # uma frase perdida não derruba a legenda
                _debug_log(f"Legendas: transcrição falhou ({e!r})")
                text = ""
            finally:
                self.asr_busy = False
            lang = self.transcriber.last_language
            if kind == "interim":
                if text and self.asr_q.empty():  # já chegou a frase final: a prévia ficou velha
                    self.interim = text
                    self._refresh()
                continue
            self._lock_language(lang)
            if text:
                with self._lock:
                    self.pending.append(text)
                self.mt_q.put((text, "en" if whisper_translates else lang))
                self._refresh()

    def _lock_language(self, lang):
        if self.language or not lang:
            return
        self._seen.append(lang)
        if self._seen[-2:] == [lang, lang]:
            self.language = lang
            _debug_log(f"Legendas: idioma falado {lang}")

    def _mt_worker(self):
        prev = ""
        while True:
            item = self.mt_q.get()
            if item is None:
                return
            text, lang = item
            out = text
            if self.target and lang != self.target:
                context = f"\nFrase anterior, só como contexto (não traduza): {prev}" if prev else ""
                try:
                    out = ai.complete(self.config, f"Traduza para {LANG_NAMES.get(self.target, self.target)}.",
                                      text, timeout=6, system=SYSTEM + context)
                except ai.AIError as e:
                    _debug_log(f"Legendas: tradução falhou ({e}); mostrando o original")
                    if not self._warned:
                        self._warned = True
                        self._status("Tradução indisponível · mostrando o original", "status-error")
            prev = text
            with self._lock:
                self.pending.remove(text)
                self.lines.append(out)
            self._refresh()

    # ── tela ───────────────────────────────────────────────────────
    def _refresh(self):
        with self._lock:
            parts = self.lines[-6:] + self.pending + ([self.interim] if self.interim else [])
            final = not (self.pending or self.interim)
        GLib.idle_add(self.overlay.update_text, " ".join(parts), final)

    def _status(self, text, state):
        GLib.idle_add(self.overlay.update_status, text, state)
