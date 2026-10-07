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

from .audio import AudioCapture, calibrate_threshold, calibrated_threshold, friendly_mic_name, get_current_volume, is_yeti, resolve_mic, set_volume, yeti_hw_problem
from .config import CALIBRATION_WAIT_TIMEOUT, ERROR_LOG, LAST_WAV, PARTIAL_WAV, PID_FILE, SPEECH_START_TICKS, TICK_INTERVAL, _debug_log
from .paste import get_display_server
from .textproc import format_transcript
from .transcribe import Transcriber
from .ui.overlay import WhisperFlowOverlay


class DictateThread(threading.Thread):
    def __init__(self, overlay, config, active_win=None):
        super().__init__(daemon=True)
        self.overlay = overlay
        self.config = config
        self.active_win = active_win
        self.cancelled = False
        self.partial_transcribing = False
        self.recording_active = True
        self.transcriber = None
        self.original_volume = None

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
        def _done():
            self.overlay.destroy()
            Gtk.main_quit()
        self.overlay.fade_out(_done)

    def _paste_text(self, text, active_win):
        """Cola texto na janela ativa de forma compatível com X11 e Wayland."""
        display_server = get_display_server()
        _debug_log(f"Colando texto no {display_server}...")
        
        if display_server == "wayland":
            try:

                proc = subprocess.Popen(
                    ["wl-copy"],
                    stdin=subprocess.PIPE
                )
                proc.communicate(input=text.encode("utf-8"), timeout=3)
                

                subprocess.run([
                    "wtype", "-M", "ctrl", "-k", "v"
                ], timeout=3)
            except (FileNotFoundError, subprocess.TimeoutExpired):

                try:
                    subprocess.run([
                        "wtype", "--", text
                    ], timeout=10)
                except Exception as e:
                    _debug_log(f"Falha ao colar no Wayland: {e}")
        else:

            try:
                proc = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"],
                    stdin=subprocess.PIPE
                )
                proc.communicate(input=text.encode("utf-8"), timeout=3)

                if active_win:
                    subprocess.run([
                        "xdotool", "windowfocus", "--sync", active_win
                    ], timeout=2)
                    time.sleep(0.1)

                subprocess.run([
                    "xdotool", "key", "--clearmodifiers", "ctrl+v"
                ], timeout=3)
            except (FileNotFoundError, subprocess.TimeoutExpired):

                try:
                    if active_win:
                        subprocess.run([
                            "xdotool", "windowfocus", "--sync", active_win
                        ], timeout=2)
                        time.sleep(0.1)
                        subprocess.run([
                            "xdotool", "type", "--window", active_win,
                            "--clearmodifiers", "--delay", "2", "--", text
                        ], timeout=10)
                    else:
                        subprocess.run([
                            "xdotool", "type", "--clearmodifiers", "--delay", "2",
                            "--", text
                        ], timeout=10)
                except Exception as e:
                    _debug_log(f"Falha ao colar no X11: {e}")

    def run(self):
        try:
            # Sem o mic configurado (ex.: Yeti desplugado), usa o padrão do sistema.
            mic, fell_back = resolve_mic(self.config)
            sr = self.config["sample_rate"]
            manual = self.config.get("silence_threshold", 0)
            threshold = manual or calibrated_threshold(self.config, mic) or 0
            silence_secs = self.config["silence_duration"]
            listen_timeout = self.config.get("listen_timeout", 15)


            if self.config.get("audio_ducking", True):
                self.original_volume, _ = get_current_volume()
                if self.original_volume is not None:
                    duck_vol = self.config.get("ducking_volume", 0.20)
                    _debug_log(f"Audio Ducking: salvando volume ({self.original_volume:.2f}) e reduzindo para {duck_vol:.2f}")
                    set_volume(duck_vol)


            # Usa janela capturada antes do overlay aparecer
            active_win = self.active_win


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
            if threshold == 0:
                threshold = calibrate_threshold(capture, self.config)
            else:
                capture.wait_for_data(timeout=CALIBRATION_WAIT_TIMEOUT)
                time.sleep(0.2)
                _debug_log(f"Threshold {'manual' if manual else 'calibrado'} ({mic}): {threshold:.6f}")


            capture.get_audio_float32()

            GLib.idle_add(self.overlay.update_status, "Aguardando voz...", "status-waiting")

            recording_start = time.time()
            started = False
            all_audio = np.array([], dtype=np.float32)
            speech_confirm_ticks = 0
            silence_counter = 0
            peak_rms = 0.0
            silence_samples_needed = int(silence_secs / TICK_INTERVAL)
            pre_buffer_captured = False
            last_partial_time = time.time()
            self.recording_active = True

            while not self.cancelled:
                time.sleep(TICK_INTERVAL)


                rms = capture.get_rms()
                peak_rms = max(peak_rms, rms)
                GLib.idle_add(self.overlay.update_level, rms, threshold)

                now = time.time()

                if rms > threshold:
                    speech_confirm_ticks += 1

                    if not started and speech_confirm_ticks >= SPEECH_START_TICKS:

                        started = True
                        GLib.idle_add(self.overlay.update_status, "Ouvindo...", "status-listening")


                        if not pre_buffer_captured:
                            pre_audio = capture.take_pre_buffer_clear_live()
                            if len(pre_audio) > 0:
                                all_audio = np.concatenate([all_audio, pre_audio])
                            pre_buffer_captured = True




                    if started and speech_confirm_ticks >= SPEECH_START_TICKS:
                        silence_counter = 0
                else:
                    speech_confirm_ticks = 0
                    if started:
                        silence_counter += 1


                if not started and (now - recording_start) > listen_timeout:
                    _debug_log(f"Timeout: {listen_timeout}s sem fala")
                    break


                if started and silence_counter >= silence_samples_needed:
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
                        audio_snapshot = np.copy(all_audio)
                        threading.Thread(
                            target=self._run_partial_transcription,
                            args=(audio_snapshot, sr),
                            daemon=True
                        ).start()

            self.recording_active = False
            capture.stop()

            if self.cancelled:
                _debug_log("DictateThread cancelada pelo usuário (configurações abertas). Abortando.")
                return

            final_audio = capture.get_audio_float32()
            if len(final_audio) > 0:
                all_audio = np.concatenate([all_audio, final_audio])


            if started and len(all_audio) > sr * 0.3:
                duration = len(all_audio) / sr
                GLib.idle_add(self.overlay.update_status, "Transcrevendo...", "status-transcribing")
                _debug_log(f"Áudio capturado: {duration:.1f}s, {len(all_audio)} samples")


                try:
                    with wave.open(LAST_WAV, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(sr)
                        wf.writeframes((all_audio * 32767).astype(np.int16).tobytes())
                except OSError:
                    pass

                final_text = self.transcriber.transcribe_file(LAST_WAV)

                if final_text:

                    if self.config.get("enable_formatting", True):
                        formatted_text = format_transcript(final_text, self.config)
                        _debug_log(f"Formatador: {repr(final_text)} -> {repr(formatted_text)}")
                        final_text = formatted_text

                    _debug_log(f"Texto: {final_text}")
                    GLib.idle_add(self.overlay.update_text, final_text, True)


                    self._paste_text(final_text, active_win)

                    GLib.idle_add(self.overlay.update_status, "Texto colado!", "status-success")
                else:
                    audio_rms = float(np.sqrt(np.mean(all_audio**2)))
                    _debug_log(f"Nenhuma fala reconhecida (RMS={audio_rms:.4f})")
                    GLib.idle_add(self.overlay.update_status,
                        "Nenhuma fala detectada", "status-error")
            else:
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
            self.restore_volume()

    def restore_volume(self):
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


def run_overlay_mode(config):

    lock_file = PID_FILE + ".lock"
    lock_fd = open(lock_file, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):

        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            if _is_dictate_process(pid):
                os.kill(pid, signal.SIGTERM)
                for _ in range(50):
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        break
                    time.sleep(0.1)
        except (OSError, ValueError):
            pass
        lock_fd.close()
        sys.exit(0)


    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


    def _sigterm_handler(signum, frame):
        GLib.idle_add(Gtk.main_quit)
    signal.signal(signal.SIGTERM, _sigterm_handler)

    try:
        # Captura janela ativa ANTES de mostrar o overlay
        try:
            active_win = subprocess.check_output(
                ["xdotool", "getactivewindow"], timeout=2
            ).decode().strip()
        except Exception:
            active_win = None

        overlay = WhisperFlowOverlay()
        overlay.show_all()

        thread = DictateThread(overlay, config, active_win=active_win)
        overlay.dictate_thread = thread
        thread.start()

        Gtk.main()
        thread.cancelled = True
        thread.restore_volume()

    finally:
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
