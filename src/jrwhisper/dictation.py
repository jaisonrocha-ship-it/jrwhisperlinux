import queue
import random
import sys
import os
import signal
import subprocess
import time
import threading
import fcntl
import wave
import numpy as np
from gi.repository import Gtk, GLib

from .audio import (AudioCapture, calibrate_threshold, calibrated_threshold, friendly_mic_name, get_current_volume,
                    is_yeti, pause_media, resolve_mic, resume_media, set_volume, yeti_hw_problem)
from .config import (CALIBRATION_WAIT_TIMEOUT, ERROR_LOG, LAST_WAV, PARTIAL_WAV, PID_FILE, SPEECH_START_TICKS,
                     THRESHOLD_FLOOR, TICK_INTERVAL, _debug_log)
from .paste import copy_text, paste_text
from .profiles import window_class
from . import ai, history, pipeline, ptt
from .textproc import format_transcript
from .transcribe import Transcriber
from .ui.overlay import WhisperFlowOverlay
from .ui.visuals import spectrum_bands


SOUNDS = {
    "start": "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga",
    "done": "/usr/share/sounds/freedesktop/stereo/complete.oga",
}


def play_sound(config, name):
    path = SOUNDS[name]
    if config.get("sounds") and os.path.exists(path):
        try:
            subprocess.Popen(["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


class DictateThread(threading.Thread):
    def __init__(self, overlay, config, active_win=None, wm_class=None, mode=None):
        super().__init__(daemon=True)
        self.overlay = overlay
        self.config = config
        self.active_win = active_win
        self.wm_class = wm_class
        self.mode = mode  # modo de IA forçado por atalho (dictate --mode <id>)
        self.cancelled = False
        self.partial_transcribing = False
        self.recording_active = True
        self.transcriber = None
        self.original_volume = None
        self.paused_media = []
        self.pasted = False
        # waiting (nada dito) | listening | busy (transcrevendo/IA) | choosing (revisão com IA)
        self.stage = "waiting"
        self.finish_now = False   # 2º toque ouvindo: encerra o trecho e transcreve
        self.stop_after = False   # ...e não volta a ouvir (mãos livres)

    def hotkey(self):
        """2º toque no atalho (SIGUSR1, roda na thread GTK): nunca descarta o que já foi dito."""
        _debug_log(f"Atalho de novo ({self.stage})")
        if self.stage == "listening":
            self.finish_now = self.stop_after = True
        elif self.stage == "choosing":
            self.overlay.pick("paste")
        elif self.stage == "waiting":
            Gtk.main_quit()
        return False

    def _run_partial_transcription(self, audio_snapshot, sr):
        try:
            with wave.open(PARTIAL_WAV, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes((audio_snapshot * 32767).astype(np.int16).tobytes())

            text = self.transcriber.transcribe_file(PARTIAL_WAV, denoise=False)
            if text and self.recording_active:
                if self.config.get("enable_formatting", True):
                    text = format_transcript(text, self.config)
                GLib.idle_add(self.overlay.update_text, text, False)
        except Exception as e:
            _debug_log(f"Partial transcribe error: {e}")
        finally:
            self.partial_transcribing = False

    def _cleanup_gtk(self):
        """Inicia o fade-out do overlay e encerra o GTK."""
        if self.cancelled:  # engrenagem: o overlay já fechou e os Ajustes são donos do laço do GTK
            return

        def _done():
            self.overlay.destroy()
            Gtk.main_quit()
        self.overlay.fade_out(_done)

    def _remember(self, raw_text, result):
        if not self.config.get("history_enabled"):
            return
        try:
            history.add({"text": result.text, "raw": raw_text, "app": self.wm_class or "",
                         "mode": result.mode["name"] if result.mode else ""})
            if random.random() < 0.05:  # poda ocasional; não vale ler o arquivo todo a cada ditado
                history.prune(self.config.get("history_retention_days", 30))
        except OSError as e:
            _debug_log(f"Histórico: {e}")

    def run(self):
        try:
            # Sem o mic configurado (ex.: Yeti desplugado), usa o padrão do sistema.
            mic, fell_back = resolve_mic(self.config)
            sr = self.config["sample_rate"]
            manual = self.config.get("silence_threshold", 0)
            threshold = manual or calibrated_threshold(self.config, mic) or 0
            keys = ptt.watcher_for(self.config)
            handsfree = bool(self.config.get("handsfree_enabled"))

            if self.config.get("pause_media", True):
                self.paused_media = pause_media()
            play_sound(self.config, "start")  # antes do ducking, senão sai baixo demais
            if self.config.get("audio_ducking", True):
                self.original_volume, _ = get_current_volume()
                if self.original_volume is not None:
                    duck_vol = self.config.get("ducking_volume", 0.20)
                    _debug_log(f"Audio Ducking: salvando volume ({self.original_volume:.2f}) e reduzindo para {duck_vol:.2f}")
                    set_volume(duck_vol)

            capture = AudioCapture(mic, sr)
            capture.start()
            # Sem daemon, carrega o modelo aqui (não no __init__, que roda na thread GTK).
            self.transcriber = Transcriber(self.config)

            if fell_back:
                _debug_log(f"Mic configurado ausente; usando {mic}")
                status = f"Mic ausente · usando {friendly_mic_name(mic)}"
            else:
                status = "Calibrando..."
            GLib.idle_add(self.overlay.update_status, status, "status-calibrating")
            # Ainda segurando o atalho depois de subir o processo? Então é "segurar para falar".
            push_to_talk = bool(keys and keys.held())
            if push_to_talk:
                _debug_log("Push-to-talk: gravando enquanto a tecla estiver pressionada")
                capture.wait_for_data(timeout=CALIBRATION_WAIT_TIMEOUT)
                threshold = threshold or THRESHOLD_FLOOR
            elif threshold == 0:
                threshold = calibrate_threshold(capture, self.config)
            else:
                capture.wait_for_data(timeout=CALIBRATION_WAIT_TIMEOUT)
                time.sleep(0.2)
                _debug_log(f"Threshold {'manual' if manual else 'calibrado'} ({mic}): {threshold:.6f}")

            timeout = self.config.get("listen_timeout", 15)
            segment = 0
            while not self.cancelled:
                capture.get_audio_float32()
                if push_to_talk:
                    GLib.idle_add(self.overlay.update_status, "Ouvindo · solte para enviar", "status-listening")
                elif segment:
                    GLib.idle_add(self.overlay.update_text, "", False)
                    GLib.idle_add(self.overlay.update_status, "Mãos livres · fale quando quiser", "status-waiting")
                else:
                    GLib.idle_add(self.overlay.update_status, "Aguardando voz...", "status-waiting")

                audio, started, peak_rms = self._listen(capture, threshold, timeout, keys if push_to_talk else None)
                if self.cancelled:
                    _debug_log("DictateThread cancelada pelo usuário (configurações abertas). Abortando.")
                    return
                last = push_to_talk or not handsfree or not started or self.stop_after
                if last:
                    capture.stop()  # o mic não fica aberto durante a transcrição e a revisão

                stop = self._finish_segment(audio, started, peak_rms, threshold, mic, sr, handsfree)
                segment += 1
                # Mãos livres segue até a frase de parada, um silêncio longo ou o 2º toque no atalho.
                if last or stop or self.stop_after:
                    break
                timeout = self.config.get("handsfree_idle_secs", 20)
                time.sleep(0.6)

            capture.stop()
            time.sleep(1.5)
            GLib.idle_add(self._cleanup_gtk)

        except Exception as e:
            import traceback
            try:
                with open(ERROR_LOG, "w") as f:
                    traceback.print_exc(file=f)
            except OSError:
                pass
            _debug_log(f"ERRO: {e}")
            GLib.idle_add(self.overlay.update_status, "Erro na captação. Tente novamente.", "status-error")
            time.sleep(2)
            GLib.idle_add(self._cleanup_gtk)
        finally:
            self.restore_audio()
            if self.pasted:
                play_sound(self.config, "done")

    def _listen(self, capture, threshold, timeout, keys=None):
        """Grava um trecho. Com keys (push-to-talk): do início até soltar a tecla.

        Sem keys: espera a fala (SPEECH_START_TICKS acima do limiar) e para no silêncio.
        Devolve (áudio, começou, pico de RMS).
        """
        sr = self.config["sample_rate"]
        silence_needed = int(self.config["silence_duration"] / TICK_INTERVAL)
        recording_start = time.time()
        started = keys is not None
        all_audio = capture.take_pre_buffer_clear_live() if started else np.array([], dtype=np.float32)
        speech_confirm_ticks = 0
        silence_counter = 0
        released_ticks = 0
        peak_rms = 0.0
        last_partial_time = time.time()
        self.recording_active = True
        self.stage = "listening" if started else "waiting"

        while not self.cancelled:
            time.sleep(TICK_INTERVAL)
            rms = capture.get_rms()
            peak_rms = max(peak_rms, rms)
            GLib.idle_add(self.overlay.update_level, rms, threshold)
            if self.overlay.wants_spectrum:
                GLib.idle_add(self.overlay.update_spectrum, spectrum_bands(capture.recent_samples(), sr))
            now = time.time()

            if keys is not None:
                released_ticks = 0 if keys.held() else released_ticks + 1
                if released_ticks >= 2:  # 100 ms solta: evita repique da tecla
                    _debug_log(f"Push-to-talk: tecla solta após {now - recording_start:.1f}s")
                    break
            elif rms > threshold:
                speech_confirm_ticks += 1
                if not started and speech_confirm_ticks >= SPEECH_START_TICKS:
                    started = True
                    self.stage = "listening"
                    GLib.idle_add(self.overlay.update_status, "Ouvindo...", "status-listening")
                    pre_audio = capture.take_pre_buffer_clear_live()
                    if len(pre_audio) > 0:
                        all_audio = np.concatenate([all_audio, pre_audio])
                if started and speech_confirm_ticks >= SPEECH_START_TICKS:
                    silence_counter = 0
            else:
                speech_confirm_ticks = 0
                if started:
                    silence_counter += 1

            if self.finish_now:
                _debug_log(f"Atalho: encerrando após {now - recording_start:.1f}s")
                break
            if keys is None:
                if not started and (now - recording_start) > timeout:
                    _debug_log(f"Timeout: {timeout}s sem fala")
                    break
                if started and silence_counter >= silence_needed:
                    _debug_log(f"Silêncio detectado após {now - recording_start:.1f}s")
                    break

            if started:
                chunk = capture.get_audio_float32()
                if len(chunk) > 0:
                    all_audio = np.concatenate([all_audio, chunk])
            else:
                capture.discard_live_buffer()

            if len(all_audio) > sr * self.config["max_duration"]:
                _debug_log(f"Limite máximo atingido: {self.config['max_duration']}s")
                break

            if started and (now - last_partial_time) > 0.8:
                if not self.partial_transcribing and len(all_audio) > sr * 0.5:
                    self.partial_transcribing = True
                    last_partial_time = now
                    threading.Thread(target=self._run_partial_transcription,
                                     args=(np.copy(all_audio), sr), daemon=True).start()

        self.recording_active = False
        self.stage = "busy"
        self.finish_now = False
        final_audio = capture.get_audio_float32() if started else np.array([], dtype=np.float32)
        if len(final_audio) > 0:
            all_audio = np.concatenate([all_audio, final_audio])
        return all_audio, started, peak_rms

    def _finish_segment(self, all_audio, started, peak_rms, threshold, mic, sr, handsfree):
        """Transcreve, processa e cola um trecho. Devolve True se a frase de parada foi dita."""
        if not (started and len(all_audio) > sr * 0.3):
            if started:
                msg = "Áudio muito curto"
            else:
                msg = "Microfone sem sinal" if peak_rms == 0.0 else "Nenhuma fala detectada"
                if peak_rms < threshold:
                    # Nada chegou ao limiar: mute/ganho do Yeti explicam mais que "sem fala".
                    msg = (yeti_hw_problem() if is_yeti(mic) else None) or msg
                    _debug_log(f"Pico {peak_rms:.5f} < limiar {threshold:.5f} em {mic}")
            _debug_log(msg)
            GLib.idle_add(self.overlay.update_status, msg, "status-error")
            return False

        GLib.idle_add(self.overlay.update_status, "Transcrevendo...", "status-transcribing")
        _debug_log(f"Áudio capturado: {len(all_audio) / sr:.1f}s, {len(all_audio)} samples")
        try:
            with wave.open(LAST_WAV, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes((all_audio * 32767).astype(np.int16).tobytes())
        except OSError:
            pass

        raw_text = self.transcriber.transcribe_file(LAST_WAV)
        stop = False
        if handsfree and raw_text:
            raw_text, stop = ptt.strip_stop_phrase(raw_text, self.config.get("handsfree_stop_phrase", ""))
            if stop:
                _debug_log("Mãos livres: frase de parada")
        if not raw_text:
            if not stop:
                _debug_log(f"Nenhuma fala reconhecida (RMS={float(np.sqrt(np.mean(all_audio ** 2))):.4f})")
                GLib.idle_add(self.overlay.update_status, "Nenhuma fala detectada", "status-error")
            return stop

        result = pipeline.process(
            self.config, raw_text, wm_class=self.wm_class, forced_mode=self.mode,
            on_status=lambda st: GLib.idle_add(self.overlay.update_status, st, "status-transcribing"))
        if self.config.get("ai_enabled") and not handsfree:
            self._choose(raw_text, result)
            return stop
        final_text = result.text
        if handsfree and self.pasted:
            final_text = " " + final_text  # trechos seguidos não grudam
        _debug_log(f"Texto: {raw_text!r} -> {final_text!r}")
        GLib.idle_add(self.overlay.update_text, final_text.strip(), True)
        paste_text(final_text, self.active_win, result.config.get("paste_method", "ctrl+v"))
        self.pasted = True
        self._remember(raw_text, result)
        if result.ai_error:
            status = "Colado sem IA"
        elif result.mode:
            status = f"Colado · {result.mode['name']}"
        else:
            status = "Texto colado!"
        GLib.idle_add(self.overlay.update_status, status, "status-success")
        return stop

    def _choose(self, raw_text, result):
        """IA ligada: o texto fica na tela com opções (reescrever, colar, copiar, descartar) até a escolha."""
        self.restore_audio()  # ninguém revisa texto com o som abafado
        modes = ai.enabled_modes(self.config)
        # Prefixo de voz já foi usado na 1ª passada; ao trocar de modo, vale o botão.
        body = ai.detect_voice_mode(self.config, raw_text)[1] if self.config.get("ai_voice_prefix", True) else raw_text
        picks = queue.Queue()
        selected = result.mode["id"] if result.mode else "original"

        def offer(res, sel):
            status = "IA falhou · texto original" if res.ai_error else "Enter cola · Esc descarta · clique para corrigir"
            GLib.idle_add(self.overlay.update_status, status, "status-error" if res.ai_error else "status-waiting")
            GLib.idle_add(self.overlay.show_choices, res.text, modes, sel, picks.put)

        offer(result, selected)
        self.stage = "choosing"
        while not self.cancelled:
            try:
                action = picks.get(timeout=0.2)
            except queue.Empty:
                continue
            if action in ("paste", "copy"):
                result.text = self.overlay.get_final_text() or result.text  # com as palavras corrigidas
            if action == "paste":
                paste_text(result.text, self.active_win, result.config.get("paste_method", "ctrl+v"))
                self.pasted = True
                self._remember(raw_text, result)
                done = f"Colado · {result.mode['name']}" if result.mode else "Texto colado"
            elif action == "copy":
                copy_text(result.text)
                self._remember(raw_text, result)
                done = "Copiado"
            elif action == "discard":
                done = "Descartado"
            else:  # "original" ou id de modo: reprocessa a partir do texto cru (ou do corrigido)
                src = body
                if self.overlay.edited:
                    src = self.overlay.get_final_text()
                    if selected == "original":
                        body = src  # correções no texto sem IA viram o novo "Original"
                src = body if action == "original" else src
                cfg = dict(self.config, ai_voice_prefix=False, ai_enabled=action != "original")
                result = pipeline.process(
                    cfg, src, wm_class=self.wm_class, forced_mode=None if action == "original" else action,
                    on_status=lambda st: GLib.idle_add(self.overlay.update_status, st, "status-transcribing"))
                selected = action if result.mode or action == "original" else selected
                offer(result, selected)
                continue
            self.stage = "busy"
            GLib.idle_add(self.overlay.hide_choices)
            GLib.idle_add(self.overlay.update_status, done, "status-error" if action == "discard" else "status-success")
            return

    def restore_audio(self):
        """Volume de volta e mídia pausada retomada (uma vez só, de qualquer thread)."""
        media, self.paused_media = self.paused_media, []
        resume_media(media)
        vol, self.original_volume = self.original_volume, None
        if vol is not None:
            _debug_log(f"Audio Ducking: restaurando volume original ({vol:.2f})")
            set_volume(vol)


def _is_dictate_process(pid):
    """Verifica se o PID pertence a um processo dictate via /proc/cmdline."""
    try:
        with open(f'/proc/{pid}/cmdline', 'rb') as f:
            cmdline = f.read().decode('utf-8', errors='replace')
        return 'dictate' in cmdline
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False


def is_running():
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return _is_dictate_process(pid)
    except (OSError, ValueError):
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        return False


def run_overlay_mode(config, mode=None):
    lock_file = PID_FILE + ".lock"
    lock_fd = open(lock_file, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        # Já há um ditado: este toque é o "2º toque" (encerra e transcreve, cola ou cancela).
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            if _is_dictate_process(pid):
                os.kill(pid, signal.SIGUSR1)
        except (OSError, ValueError):
            pass
        lock_fd.close()
        sys.exit(0)

    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    # GLib.unix_signal_add: o sinal acorda o laço do GTK direto (handler Python pode atrasar)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: Gtk.main_quit() or True)

    try:
        # Captura janela ativa ANTES de mostrar o overlay
        try:
            active_win = subprocess.check_output(
                ["xdotool", "getactivewindow"], timeout=2
            ).decode().strip()
        except Exception:
            active_win = None

        overlay = WhisperFlowOverlay(config)
        overlay.show_all()

        thread = DictateThread(overlay, config, active_win=active_win, wm_class=window_class(active_win), mode=mode)
        overlay.dictate_thread = thread
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, lambda: thread.hotkey() or True)
        thread.start()

        Gtk.main()
        thread.cancelled = True
        thread.restore_audio()

    finally:
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
