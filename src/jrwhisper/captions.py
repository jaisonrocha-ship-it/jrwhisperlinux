"""Legendas ao vivo: o som do computador transcrito e traduzido enquanto toca (`dictate --captions`).

Captura → Chunker → transcrição → tradução → overlay. O trecho em andamento é retranscrito a
cada INTERIM_EVERY s; quando o Whisper devolve 2+ segmentos, os completos são fechados e o áudio
é cortado no fim do último (limite de frase do próprio Whisper, sem partir palavra). Pausas
também fecham; MAX_CHUNK é só a rede de segurança. A prévia é traduzida enquanto cresce (uma
tradução em voo; aparece a mais recente) e as frases fechadas são traduzidas na ordem. Inglês sai do próprio
Whisper (task "translate"), sem IA; os outros idiomas usam o provedor de IA (NVIDIA NIM ou Ollama).
"""
import collections
import os
import queue
import re
import threading
import time
import wave

import numpy as np
from gi.repository import GLib, Gtk

import requests

from . import ai, history, secrets
from .audio import SYSTEM_AUDIO, AudioCapture
from .config import RUNTIME_DIR, TICK_INTERVAL, _debug_log
from .paste import copy_text
from .transcribe import Transcriber

LANG_NAMES = {"pt": "português do Brasil", "en": "inglês", "es": "espanhol"}
MIN_VOICED = 0.3     # s de som numa frase para valer a pena transcrever
PAUSE_SECS = 0.4     # pausa que fecha a frase
MAX_CHUNK = 10.0     # rede de segurança: sem pausa nem 2 segmentos, corta no ponto mais baixo dos últimos 2 s
QUIET_FLOOR = 0.0001  # áudio digital: silêncio é ~0; vídeo baixinho (volume do app em 15%) fica em ~0,0003
IDLE_SECS = 60       # tanto tempo sem som: o vídeo acabou
INTERIM_EVERY = 0.5  # s entre prévias da frase em andamento
DETECT_SECS = 3.0    # o idioma é decidido antes de qualquer legenda, a partir deste tamanho de trecho: em
                     # 1–3 s o Whisper chuta (russo virava alemão/polonês). Depois fica fixo; vídeo que troca
                     # de língua: reinicie a legenda.
LANG_PROB = 0.7      # confiança para fixar; sem ela até MAX_CHUNK, fica o melhor palpite
NIM_LIVE_GAP = 2.5   # NVIDIA: prévia traduzida no máx. a cada 2,5 s
NIM_PER_MIN = 35     # orçamento de chamadas por minuto (o plano grátis devolve 429 acima de ~40)
NIM_RESERVE = 10     # a prévia só usa o orçamento se sobrarem estas para as frases fechadas
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uff00-\uffef]+")
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
        self.epoch = 0      # muda sempre que o início do buffer muda (valida cortes pedidos pelo ASR)
        self.hold = False   # idioma ainda indefinido: não fecha frase em pausa (o trecho cresce até dar para detectar)

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
        if self.quiet >= PAUSE_SECS and not (self.hold and self.voiced):
            if self.voiced >= MIN_VOICED:
                return [self._take(len(self.buf))]
            if len(self.buf) > 0.3 * self.sr:
                self.buf = self.buf[-int(0.3 * self.sr):]  # só silêncio: guarda um respiro antes da próxima fala
                self.epoch += 1
            self.voiced = 0.0
        elif len(self.buf) >= MAX_CHUNK * self.sr and not self.hold:
            frame = int(0.1 * self.sr)
            tail = self.buf[-2 * self.sr:]
            energy = [np.mean(tail[i:i + frame] ** 2) for i in range(0, len(tail) - frame, frame // 2)]
            cut = len(self.buf) - len(tail) + int(np.argmin(energy)) * (frame // 2) + frame // 2
            return [self._take(cut)]
        return []

    def cut(self, n):
        """Descarta o começo do buffer (frases já fechadas pelo ASR)."""
        self._take(n)

    def _take(self, n):
        self.epoch += 1
        chunk, self.buf = self.buf[:n], self.buf[n:]
        self.voiced = len(self.buf) / self.sr if self.quiet == 0 else 0.0
        self.quiet = 0.0
        return chunk

    def flush(self):
        chunk = self.buf if self.voiced >= MIN_VOICED else None
        self.buf = np.zeros(0, np.float32)
        return chunk


def pick_translator(config):
    """Config de IA para traduzir legendas. "auto": NVIDIA se houver chave (tradução melhor, ~0,7 s);
    senão Ollama local com um modelo de conversa (~0,4 s, sem limite, mas o qwen2.5 7B vazava chinês e
    traduzia "booking" como "livro"); senão o provedor da aba Inteligência."""
    choice = config.get("caption_translator", "auto")
    if choice == "auto" and secrets.get_key("nvidia"):
        choice = "nvidia"
    if choice in ("auto", "ollama"):
        url = config.get("ai_ollama_url", "http://localhost:11434")
        try:
            names = [m["name"] for m in requests.get(url + "/api/tags", timeout=1).json()["models"]]
        except (requests.RequestException, ValueError, KeyError):
            names = []
        chat = [n for n in names if "embed" not in n]
        wanted = config.get("ai_ollama_model", "")
        model = next((n for n in chat if n in (wanted, f"{wanted}:latest")), chat[0] if chat else None)
        if model:
            return dict(config, ai_provider="ollama", ai_ollama_model=model)
        if choice == "ollama":
            _debug_log("Legendas: Ollama sem modelo de conversa; usando o provedor da aba Inteligência")
    return dict(config, ai_provider="nvidia") if choice == "nvidia" else config


class CaptionThread(threading.Thread):
    """Mesma interface que o DictateThread usa com o overlay/run_overlay_mode: run, hotkey,
    cancelled, restore_audio."""

    def __init__(self, overlay, config, **_):
        super().__init__(daemon=True)
        self.overlay = overlay
        self.config = config
        self.sr = config.get("sample_rate", 16000)
        self.target = config.get("caption_language", "pt")  # "" = sem tradução
        self.whisper_translates = self.target == "en"       # o Whisper só traduz para inglês, e de graça
        self.cancelled = False
        self.stop = threading.Event()
        self.asr_q, self.mt_q = queue.Queue(), queue.Queue()
        self.asr_busy = False
        self.lines = []                         # legendas fechadas e traduzidas
        self.pending = collections.deque()      # frases fechadas esperando a tradução (mostra a prévia delas)
        # trecho em andamento: original, idioma e a tradução mais recente (pode ser de um original um pouco
        # mais curto: melhor que nada enquanto a próxima chega)
        self.live = {"src": "", "lang": None, "tr": "", "tr_src": ""}
        self.language = None                    # fixado na 1ª detecção confiável (DETECT_SECS)
        self.gen = 0                            # sobe quando a prévia vira frase: tradução atrasada da prévia velha cai
        self.commits = queue.Queue()            # (época, amostras, texto, idioma): frases fechadas pelo ASR
        self._lock = threading.Lock()
        self._warned = False
        self.mt_cfg = config                    # trocado por pick_translator() no início da tradução
        self._sent = collections.deque()        # horários das chamadas de tradução (orçamento por minuto)

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
                while not self.commits.empty():
                    epoch, n, text, lang = self.commits.get()
                    if epoch == chunker.epoch and n <= len(chunker.buf):
                        chunker.cut(n)
                        self._close(text, lang)
                chunker.hold = self.language is None and chunker.voiced < MAX_CHUNK
                for chunk in chunker.feed(capture.get_audio_float32()):
                    self._take_live()
                    self.asr_q.put(("final", chunk, None))
                now = time.time()
                if rms > QUIET_FLOOR:
                    last_sound = now
                    if not listening:
                        listening = True
                        self._status(f"{label} · atalho encerra", "status-listening")
                elif now - last_sound > IDLE_SECS:
                    _debug_log("Legendas: sem som, encerrando")
                    break
                if (chunker.voiced >= 0.4 and now - last_interim >= INTERIM_EVERY
                        and self.asr_q.empty() and not self.asr_busy):
                    last_interim = now
                    self.asr_q.put(("interim", chunker.buf.copy(), chunker.epoch))
            capture.stop()
            tail = chunker.flush()
            if tail is not None:
                self._take_live()
                self.asr_q.put(("final", tail, None))
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
    def _needs_mt(self, lang):
        return bool(self.target) and not self.whisper_translates and lang != self.target

    def _asr_worker(self):
        while True:
            item = self.asr_q.get()
            if item is None:
                self.mt_q.put(None)
                return
            kind, audio, epoch = item
            self.asr_busy = True
            path = os.path.join(RUNTIME_DIR, f"dictate_caption_{kind}.wav")
            long = len(audio) >= DETECT_SECS * self.sr
            if kind == "interim" and not self.language and not long:
                self.asr_busy = False  # prévia curta sem idioma definido sairia em outra língua: espera
                continue
            try:
                _write_wav(path, audio, self.sr)
                # Áudio digital limpo: sem VAD (o Silero descarta canto); sem o vocabulário
                # de ditado. _run corta segmentos de baixa confiança. O transcriber é só desta thread.
                self.transcriber.config = dict(
                    self.config, auto_languages=[], initial_prompt="",
                    language=self.language or "auto",
                    vad_filter=False, task="translate" if self.whisper_translates else "transcribe")
                text = self.transcriber.transcribe_file(path, denoise=False, second_pass=False)
            except Exception as e:  # uma frase perdida não derruba a legenda
                _debug_log(f"Legendas: transcrição falhou ({e!r})")
                text = ""
            finally:
                self.asr_busy = False
            lang, prob = self.transcriber.last_language, self.transcriber.last_language_prob
            if kind == "interim" and not self.language:
                if not text or (prob < LANG_PROB and len(audio) < MAX_CHUNK * self.sr):
                    continue  # ainda sem certeza do idioma: espera mais áudio em vez de mostrar outra língua
                self.language = lang
                _debug_log(f"Legendas: idioma {lang} ({prob:.2f}, {len(audio) / self.sr:.1f} s)")
            if kind == "interim":
                if text and self.asr_q.empty():  # se a frase já fechou, esta prévia ficou velha
                    segs = [sg for sg in self.transcriber.last_segments if sg[2]]
                    if len(segs) >= 2:  # os completos fecham já, cortados no limite que o Whisper marcou
                        self.commits.put((epoch, int(segs[-2][1] * self.sr), " ".join(sg[2] for sg in segs[:-1]), lang))
                        text = segs[-1][2]
                    with self._lock:
                        self.live = {**self.live, "src": text, "lang": lang}
                        if not self._needs_mt(lang):
                            self.live.update(tr=text, tr_src=text)
                    self._refresh()
                continue
            self.mt_q.put((text, lang))  # mesmo vazio: tira o provisório da tela

    def _take_live(self):
        """O trecho em andamento virou frase fechada: a prévia fica na tela (provisória) até a tradução
        final chegar, sem piscar vazio enquanto a frase é retranscrita."""
        with self._lock:
            self.pending.append(self.live["tr"])  # só a tradução (vazia = nada até a final chegar)
            self.live = {"src": "", "lang": None, "tr": "", "tr_src": ""}
            self.gen += 1

    def _close(self, text, lang):
        """Frase fechada pelo ASR (limite de segmento): sai da prévia e entra na fila de tradução."""
        with self._lock:
            # sem tradução própria ainda: mostra a da prévia (que incluía esta frase), não o original
            self.pending.append(self.live["tr"] if self._needs_mt(lang) else text)
            self.live = {**self.live, "tr": "", "tr_src": ""}
            self.gen += 1
        self.mt_q.put((text, lang))
        self._refresh()

    def _budget(self):
        """Chamadas restantes no minuto (NVIDIA grátis: ~40/min, acima disso devolve 429)."""
        if self.mt_cfg.get("ai_provider") == "ollama":
            return 99
        now = time.time()
        while self._sent and now - self._sent[0] > 60:
            self._sent.popleft()
        return NIM_PER_MIN - len(self._sent)

    def _translate(self, text, prev="", retries=0):
        """Tradução, ou None se falhou (a prévia espera a próxima; frase fechada tenta de novo)."""
        context = f"\nFrase anterior, só como contexto (não traduza): {prev}" if prev else ""
        lang_name = LANG_NAMES.get(self.target, self.target)
        for attempt in range(retries + 1):
            while self._budget() <= 0:
                time.sleep(0.2)
            self._sent.append(time.time())
            t0 = time.time()
            try:
                out = ai.complete(self.mt_cfg, f"Traduza para {lang_name}.", text, timeout=6,
                                  system=f"{SYSTEM} Responda somente em {lang_name}.{context}")
            except ai.AIError as e:
                _debug_log(f"Legendas: tradução falhou ({e})")
                if "429" in str(e) and attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return None
            _debug_log(f"Legendas: tradução em {time.time() - t0:.2f}s ({len(text)} car.)")
            if self.target not in ("zh", "ja", "ko"):  # qwen2.5 local vazava "我们需要" no meio do português
                out = CJK.sub("", out).strip()
            return out or None
        return None

    def _mt_worker(self):
        """Frases fechadas primeiro, na ordem (as que acumularam vão juntas numa chamada só);
        ociosa e com orçamento sobrando, traduz a prévia mais recente."""
        prev = ""
        if self.target and not self.whisper_translates:
            self.mt_cfg = pick_translator(self.config)
            local = self.mt_cfg.get("ai_provider") == "ollama"
            _debug_log(f"Legendas: tradutor {self.mt_cfg.get('ai_ollama_model') if local else self.mt_cfg.get('ai_model')}")
            if local:  # carrega o modelo já (a 1ª chamada leva ~8 s), enquanto o idioma ainda é detectado
                self._translate("ok")
        live_gap = 0.0 if self.mt_cfg.get("ai_provider") == "ollama" else NIM_LIVE_GAP
        last_live = 0.0
        stop = False
        while not stop:
            try:
                item = self.mt_q.get(timeout=0.05)
            except queue.Empty:
                with self._lock:
                    src, lang, done, gen = self.live["src"], self.live["lang"], self.live["tr_src"], self.gen
                if (src and src != done and self._needs_mt(lang) and time.time() - last_live >= live_gap
                        and self._budget() > NIM_RESERVE):  # a prévia nunca gasta o que as frases precisam
                    last_live = time.time()
                    out = self._translate(src, prev)
                    with self._lock:
                        if out and self.gen == gen:  # a prévia não virou frase fechada enquanto traduzia
                            self.live.update(tr=out, tr_src=src)
                    self._refresh()
                continue
            if item is None:
                return
            batch = [item]
            while True:  # frases que acumularam (tradução lenta/429) vão numa chamada só
                try:
                    nxt = self.mt_q.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    stop = True
                    break
                batch.append(nxt)
            text = " ".join(t for t, _l in batch if t)
            lang = next((l for t, l in batch if t), batch[0][1])
            out = text
            if text and self._needs_mt(lang):
                out = self._translate(text, prev, retries=3)
                if out is None:  # só depois de insistir: o original, com aviso
                    out = text
                    if not self._warned:
                        self._warned = True
                        self._status("Tradução indisponível · mostrando o original", "status-error")
            prev = text or prev
            with self._lock:
                for _ in batch:
                    if self.pending:
                        self.pending.popleft()
                if out:
                    self.lines.append(out)
            self._refresh()

    # ── tela ───────────────────────────────────────────────────────
    def _refresh(self):
        with self._lock:
            # Traduzindo, o original nunca vai para a tela (metade em cada língua era ilegível):
            # o que ainda não foi traduzido vira "…" até a tradução chegar.
            waiting = bool(self.live["src"]) and not self.live["tr"]
            live = self.live["tr"] or ("…" if waiting else "")
            if self.pending:  # o provisório da frase fechada já cobre o começo da prévia: sem duplicar
                live = "…" if self.live["src"] else ""
            parts = self.lines[-30:] + [p for p in self.pending if p] + ([live] if live else [])
            final = not (self.pending or live)
        GLib.idle_add(self.overlay.update_text, " ".join(parts), final)

    def _status(self, text, state):
        GLib.idle_add(self.overlay.update_status, text, state)
