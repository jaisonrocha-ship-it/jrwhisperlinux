#!/usr/bin/env python3
"""
Test: calibração e silence detection do dictate v2.0
Executa sem overlay GTK — apenas testa o pipeline de áudio.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

VENV_PYTHON = os.path.expanduser("~/.local/share/dictation-venv/bin/python3")
if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

import time, json, subprocess, threading
from collections import deque
import numpy as np

# Import from dictate
CONFIG_DIR = os.path.expanduser("~/.config/dictate")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_CONFIG = {
    "model": "medium", "language": "pt", "sample_rate": 16000,
    "mic_device": "@DEFAULT_SOURCE@", "silence_threshold": 0,
    "silence_duration": 0.8, "listen_timeout": 15, "max_duration": 60,
    "gpu_min_vram_mb": 2500,
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)


class AudioCapture:
    def __init__(self, mic, sr=16000):
        self.sr = sr
        self.buffer = bytearray()
        self.running = False
        self.proc = None
        self.mic = mic
        self._lock = threading.Lock()
        self.current_rms = 0.0
        self._has_data = threading.Event()
        pre_buffer_bytes = int(0.3 * sr * 2)
        self._pre_buffer = deque(maxlen=pre_buffer_bytes // 1024 + 1)

    def start(self):
        self.running = True
        self.proc = subprocess.Popen(
            ["parec", "--device", self.mic, "--format=s16le",
             "--rate", str(self.sr), "--channels=1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        while self.running:
            chunk = self.proc.stdout.read(1024)
            if not chunk:
                break
            self._has_data.set()
            with self._lock:
                self.buffer.extend(chunk)
                self._pre_buffer.append(bytes(chunk))
            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples ** 2)))
            self.current_rms = rms

    def wait_for_data(self, timeout=5.0):
        return self._has_data.wait(timeout=timeout)

    def get_audio_float32(self):
        with self._lock:
            data = bytes(self.buffer)
            self.buffer.clear()
        if not data:
            return np.array([], dtype=np.float32)
        if len(data) % 2 != 0:
            data = data[:-1]
        if not data:
            return np.array([], dtype=np.float32)
        return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    def get_rms(self):
        return self.current_rms

    def stop(self):
        self.running = False
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def test_calibration():
    config = load_config()
    mic = config.get("mic_device", "@DEFAULT_SOURCE@")
    sr = config["sample_rate"]

    print("=" * 60)
    print("TEST: Calibração de threshold")
    print("=" * 60)

    capture = AudioCapture(mic, sr)
    capture.start()

    # Wait for parec
    print("\n1. Esperando parec iniciar...")
    t0 = time.time()
    got_data = capture.wait_for_data(timeout=5.0)
    wait_time = time.time() - t0
    print(f"   parec iniciou: {got_data} ({wait_time:.3f}s)")

    if not got_data:
        print("   FALHA: parec não produziu dados!")
        capture.stop()
        return

    # Discard transient
    print("2. Descartando transient (200ms)...")
    time.sleep(0.2)
    capture.get_audio_float32()

    # Collect RMS samples
    print("3. Medindo ruído ambiente (1s)...")
    rms_samples = []
    for _ in range(20):
        time.sleep(0.05)
        rms = capture.get_rms()
        rms_samples.append(rms)
        print(f"   RMS: {rms:.6f} {'(zero!)' if rms == 0 else ''}")

    nonzero = [r for r in rms_samples if r > 0]
    print(f"\n   Total: {len(rms_samples)}, Non-zero: {len(nonzero)}")

    if nonzero:
        arr = np.array(nonzero)
        median = float(np.median(arr))
        threshold = max(min(median * 3.0, 0.05), 0.003)
        print(f"   Median: {median:.6f}")
        print(f"   Threshold: {threshold:.6f}")
        print(f"   Range: [{arr.min():.6f}, {arr.max():.6f}]")

    # Now test silence detection
    print("\n" + "=" * 60)
    print("TEST: Silence detection (fale agora, depois fique em silêncio)")
    print("=" * 60)

    SPEECH_START_TICKS = 3
    silence_secs = config["silence_duration"]
    silence_needed = int(silence_secs / 0.05)

    started = False
    speech_confirm = 0
    silence_counter = 0

    print(f"\nThreshold: {threshold:.6f}")
    print(f"Speech start: {SPEECH_START_TICKS} ticks ({SPEECH_START_TICKS * 50}ms)")
    print(f"Silence stop: {silence_needed} ticks ({silence_secs}s)")
    print(f"\nMonitorando por 10s...\n")

    t_start = time.time()
    while time.time() - t_start < 10:
        time.sleep(0.05)
        rms = capture.get_rms()
        elapsed = time.time() - t_start

        if rms > threshold:
            speech_confirm += 1
            if not started and speech_confirm >= SPEECH_START_TICKS:
                started = True
                print(f"  {elapsed:.1f}s ▶ FALA INICIADA (RMS={rms:.6f})")
            silence_counter = 0
        else:
            speech_confirm = 0
            if started:
                silence_counter += 1

        if started and silence_counter >= silence_needed:
            print(f"  {elapsed:.1f}s ■ SILÊNCIO DETECTADO ({silence_secs}s)")
            break

        # Show state every 200ms
        if int(elapsed * 5) % 1 == 0:
            state = "SPEECH" if rms > threshold else "silent"
            bar = "█" * min(int(rms / threshold * 20), 40)
            if started or rms > threshold * 0.5:
                print(f"  {elapsed:.1f}s {state:7s} RMS={rms:.6f} |{bar}")

    if not started:
        print("  Nenhuma fala detectada nos 10s")

    capture.stop()
    print("\nDone!")


if __name__ == "__main__":
    test_calibration()
