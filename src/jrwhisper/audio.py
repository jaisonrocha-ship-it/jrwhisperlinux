import os
import subprocess
import json
import time
import threading
import math
import re
import shutil
from collections import deque
import numpy as np

from .config import CALIBRATION_MEASURE_SECS, CALIBRATION_WAIT_TIMEOUT, DEBUG_LOG, ERROR_LOG, HW_GAIN_TOLERANCE, PRE_BUFFER_SECS, THRESHOLD_FLOOR, TICK_INTERVAL, _debug_log, save_config


def _pcm16le_to_float32(data: bytes):
    if not data:
        return np.array([], dtype=np.float32)
    if len(data) % 2 != 0:
        data = data[:-1]
    if not data:
        return np.array([], dtype=np.float32)
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def get_current_volume():
    """Retorna o volume atual e se está mutado usando WirePlumber (wpctl)."""
    try:
        out = subprocess.check_output(
            ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
            timeout=1, stderr=subprocess.DEVNULL
        ).decode().strip()

        parts = out.split()
        if len(parts) >= 2:
            return float(parts[1]), "[MUTED]" in out
    except Exception as e:
        _debug_log(f"Falha ao ler volume: {e}")
    return None, False


def set_volume(val):
    """Define o volume de áudio padrão do sistema via WirePlumber."""
    try:
        subprocess.run(
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"],
            timeout=1, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        _debug_log(f"Falha ao definir volume: {e}")






class AudioCapture:
    """Captura áudio via parec com buffer thread-safe e pré-buffer."""

    def __init__(self, mic, sr=16000, pre_buffer_secs=PRE_BUFFER_SECS):
        self.sr = sr
        self.buffer = bytearray()
        self.running = False
        self.proc = None
        self.mic = mic
        self._lock = threading.Lock()
        self.current_rms = 0.0
        self._has_data = threading.Event()


        pre_buffer_bytes = int(pre_buffer_secs * sr * 2)
        self._pre_buffer = deque(maxlen=pre_buffer_bytes // 1024 + 1)

    def start(self):
        self.running = True
        self.proc = subprocess.Popen(
            ["parec", "--device", self.mic, "--format=s16le",
             "--rate", str(self.sr), "--channels=1", "--latency-msec=30"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        try:
            count = 0
            while self.running:
                chunk = self.proc.stdout.read(1024)
                if not chunk:
                    _debug_log("AudioCapture: parec stdout EOF")
                    break
                count += 1
                self._has_data.set()
                with self._lock:
                    self.buffer.extend(chunk)
                    self._pre_buffer.append(bytes(chunk))

                samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(samples ** 2)))
                self.current_rms = rms
                if count % 10 == 0 or count < 5:
                    _debug_log(f"AudioCapture: read chunk #{count}, RMS={rms:.6f}")
        except Exception as e:
            import traceback
            _debug_log(f"AudioCapture Thread CRASHED: {e}")
            try:
                with open(ERROR_LOG, "a") as f:
                    f.write(f"--- AudioCapture Crash ---\n")
                    traceback.print_exc(file=f)
            except OSError:
                pass

    def wait_for_data(self, timeout=CALIBRATION_WAIT_TIMEOUT):
        """Bloqueia até parec produzir dados reais. Retorna True se dados chegaram."""
        return self._has_data.wait(timeout=timeout)

    def get_audio_float32(self):
        with self._lock:
            data = bytes(self.buffer)
            self.buffer.clear()
        return _pcm16le_to_float32(data)

    def get_pre_buffer_float32(self):
        """Retorna o conteúdo do pré-buffer como float32 (para incluir no início da gravação)."""
        with self._lock:
            data = b''.join(self._pre_buffer)
        return _pcm16le_to_float32(data)

    def discard_live_buffer(self):
        """Descarta o buffer linear; o anel de 300ms permanece intacto."""
        with self._lock:
            self.buffer.clear()

    def take_pre_buffer_clear_live(self):
        """Copia o pré-buffer e zera o buffer linear para evitar overlap no ataque."""
        with self._lock:
            data = b''.join(self._pre_buffer)
            self.buffer.clear()
        return _pcm16le_to_float32(data)

    def recent_samples(self, n=1024):
        """Últimas n amostras do anel de pré-buffer (para o espectro do visual de Barras)."""
        with self._lock:
            data = b''.join(self._pre_buffer)
        return _pcm16le_to_float32(data[-2 * n:])

    def get_rms(self):
        return self.current_rms

    def has_data(self):
        with self._lock:
            return len(self.buffer) > 0

    def stop(self):
        self.running = False
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def calibrate_threshold(capture, config):
    """
    Calibra o threshold de silêncio de forma robusta.

    1. Espera parec produzir dados reais (até 5s)
    2. Descarta primeiros 200ms (transient de inicialização)
    3. Mede 1s de ruído ambiente (20 amostras × 50ms)
    4. Threshold = mediana × 3.0, com piso THRESHOLD_FLOOR e teto 0.015
    """

    try:
        with open(DEBUG_LOG, "w") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] Calibração iniciada\n")
    except OSError:
        pass


    t0 = time.time()
    if not capture.wait_for_data(timeout=CALIBRATION_WAIT_TIMEOUT):
        _debug_log("ERRO: parec não produziu dados em 5s")
        return max(config.get("silence_threshold", 0), THRESHOLD_FLOOR)

    wait_time = time.time() - t0
    _debug_log(f"parec iniciou em {wait_time:.3f}s")


    time.sleep(0.2)
    capture.get_audio_float32()


    n_samples = int(CALIBRATION_MEASURE_SECS / TICK_INTERVAL)
    rms_samples = []
    for _ in range(n_samples):
        time.sleep(TICK_INTERVAL)
        rms = capture.get_rms()
        if rms > 0:
            rms_samples.append(rms)

    if not rms_samples:
        _debug_log("AVISO: nenhuma amostra RMS > 0 durante calibração")
        return THRESHOLD_FLOOR


    arr = np.array(rms_samples)
    noise_median = float(np.median(arr))
    threshold = np.clip(noise_median * 3.0, THRESHOLD_FLOOR, 0.015)

    _debug_log(
        f"Calibração: samples={len(rms_samples)} "
        f"median={noise_median:.6f} min={arr.min():.6f} max={arr.max():.6f} "
        f"threshold={threshold:.6f}"
    )

    return float(threshold)


def friendly_mic_name(name):
    if name == "@DEFAULT_SOURCE@":
        return "Padrão do Sistema"
    if "usb-Logitech_Yeti_GX" in name:
        return "Yeti GX"
    if "usb-" in name:
        m = re.search(r'usb-(.*?)-', name)
        if m:
            return m.group(1).replace("_", " ") + " (USB)"
    if "pci-" in name:
        return "Áudio Interno (PCI)"
    if "easyeffects" in name:
        return "EasyEffects Source"
    return name


def list_source_names():
    """Entradas reais (sem .monitor) do PulseAudio/PipeWire; [] se o pactl falhar."""
    try:
        out = subprocess.check_output(["pactl", "list", "short", "sources"], timeout=2).decode("utf-8")
    except Exception as e:
        _debug_log(f"Falha ao listar microfones: {e}")
        return []
    names = [p[1] for p in (line.split() for line in out.splitlines()) if len(p) >= 2]
    return [n for n in names if not n.endswith(".monitor")]


def default_source_name():
    try:
        return subprocess.check_output(["pactl", "get-default-source"], timeout=2).decode().strip() or None
    except Exception:
        return None


def list_mic_devices():
    return [("@DEFAULT_SOURCE@", "Padrão do Sistema")] + [
        (n, f"{friendly_mic_name(n)} ({n})") for n in list_source_names()
    ]


def resolve_mic(config):
    """Mic a usar agora: o configurado se conectado, senão o padrão do sistema.

    Retorna (device, fallback). Resolve @DEFAULT_SOURCE@ para o nome real, para a
    calibração ficar presa ao mic físico. Sem resposta do pactl, confia no config.
    """
    wanted = config.get("mic_device", "@DEFAULT_SOURCE@")
    names = list_source_names()
    if wanted != "@DEFAULT_SOURCE@" and (wanted in names or not names):
        return wanted, False
    return default_source_name() or "@DEFAULT_SOURCE@", wanted != "@DEFAULT_SOURCE@"


def is_yeti(mic):
    return "Yeti_GX" in mic


def hw_gain_for(mic):
    """Ganho de hardware do mic, quando ele tem um que o ALSA não vê (hoje: Yeti GX)."""
    return yeti_hw_gain() if is_yeti(mic) else None


def rms_db(rms):
    return 20 * math.log10(max(rms, 1e-8))


def evaluate_levels(noise_vals, voice_vals):
    """Ruído (mediana) e voz (p75) → limiar e veredito: ok | low | weak | muted.

    Mediana: o limiar precisa vencer o ruído contínuo, não cliques isolados.
    Limiar acima do ruído e bem abaixo da voz: confirma fala sem disparar no ambiente.
    """
    noise = float(np.median(noise_vals)) if len(noise_vals) else 0.0
    voice = float(np.percentile(voice_vals, 75)) if len(voice_vals) else 0.0
    result = {"noise": noise, "voice": voice, "threshold": None}
    if voice == 0.0:
        result["verdict"] = "muted"
    elif voice < max(noise * 4, THRESHOLD_FLOOR / 5):
        result["verdict"] = "weak"
    else:
        result["threshold"] = round(max(noise * 3, voice / 4), 5)
        result["verdict"] = "low" if voice < 0.005 else "ok"
    return result


def save_mic_calibration(config, mic, result):
    config.setdefault("mic_calibrations", {})[mic] = {
        "threshold": result["threshold"],
        "noise": round(result["noise"], 6),
        "voice": round(result["voice"], 6),
        "hw_gain": hw_gain_for(mic),
        "date": time.strftime("%Y-%m-%d %H:%M"),
    }
    # Calibração por mic substitui o limiar global manual (slider do painel).
    config["silence_threshold"] = 0
    save_config(config)


def remove_mic_calibration(config, mic):
    if config.get("mic_calibrations", {}).pop(mic, None) is not None:
        save_config(config)


def calibration_state(config, mic, hw_gain=None):
    """(estado, calibração) com estado em none | ok | stale (ganho de hardware mudou)."""
    cal = config.get("mic_calibrations", {}).get(mic)
    if not cal:
        return "none", None
    saved = cal.get("hw_gain")
    if saved is not None:
        now = hw_gain if hw_gain is not None else hw_gain_for(mic)
        if now is not None and abs(now - saved) > HW_GAIN_TOLERANCE:
            return "stale", cal
    return "ok", cal


def calibrated_threshold(config, mic):
    """Limiar salvo para este mic, ou None (→ calibração automática da sessão)."""
    state, cal = calibration_state(config, mic)
    if state == "stale":
        _debug_log(f"Ganho do {friendly_mic_name(mic)} mudou desde a calibração ({cal['hw_gain']}): usando automático")
    return cal["threshold"] if state == "ok" else None


def _yeti_ctl(*args):
    """Roda yeti-ctl (HID++ do Yeti GX) se instalado; stdout ou None."""
    # ponytail: caminho do setup local; sem yeti-ctl tudo cai no caminho genérico.
    path = shutil.which("yeti-ctl") or os.path.expanduser("~/dev/yeti-ctl/yeti-ctl.py")
    if not os.path.isfile(path):
        return None
    try:
        return subprocess.run(["python3", path, *args], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return None


def yeti_hw_status():
    """Ganho/mute internos do Yeti GX (o ALSA não enxerga), ou None."""
    try:
        status = json.loads(_yeti_ctl("json") or "")
    except ValueError:
        return None
    return status if status.get("connected") else None


def yeti_hw_gain():
    """Só o ganho (~0,1 s, metade do status completo): roda a cada ditado."""
    m = re.search(r"Gain: (\d+)", _yeti_ctl("get") or "")
    return int(m.group(1)) if m else None


def yeti_hw_problem():
    """Texto curto se o hardware do Yeti explica falta de áudio, senão None."""
    hw = yeti_hw_status()
    if not hw:
        return None
    if hw.get("muted"):
        return "Yeti mutado no hardware"
    if hw.get("gain") is not None and hw["gain"] < 20:
        return f"Ganho do Yeti em {hw['gain']}/100"
    return None


def measure_levels(capture, secs, on_tick=None):
    vals = []
    end = time.time() + secs
    while time.time() < end:
        time.sleep(TICK_INTERVAL)
        vals.append(capture.get_rms())
        if on_tick:
            on_tick(vals[-1])
    return np.array(vals)
