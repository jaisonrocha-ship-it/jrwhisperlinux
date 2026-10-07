import os
import json
import time
import tempfile


CONFIG_DIR = os.path.expanduser("~/.config/dictate")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
# $XDG_RUNTIME_DIR é 0700 por usuário: áudio, transcrições e socket ficam privados.
RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
PID_FILE = os.path.join(RUNTIME_DIR, "dictate.pid")
DAEMON_SOCKET = os.path.join(RUNTIME_DIR, "dictate_daemon.sock")
DAEMON_PID_FILE = os.path.join(RUNTIME_DIR, "dictate_daemon.pid")
DEBUG_LOG = os.path.join(RUNTIME_DIR, "dictate_debug.log")
ERROR_LOG = os.path.join(RUNTIME_DIR, "dictate_error.log")
LAST_WAV = os.path.join(RUNTIME_DIR, "dictate_last.wav")
PARTIAL_WAV = os.path.join(RUNTIME_DIR, "dictate_partial.wav")


DEFAULT_CONFIG = {
    "model": "medium",
    "language": "pt",
    "sample_rate": 16000,
    "mic_device": "@DEFAULT_SOURCE@",
    "silence_threshold": 0,
    "silence_duration": 1.7,
    "listen_timeout": 15,
    "max_duration": 60,
    "gpu_min_vram_mb": 2500,
    "initial_prompt": (
        "Termos portuários e de comércio exterior: "
        "Incoterms, FOB, CIF, CFR, DAP, chartering, "
        "breakbulk, M2A Metais, ArcelorMittal, TESC, "
        "reefer, contêiner refrigerado, Inova MM, "
        "despachante aduaneiro, estufagem, desova, "
        "navio, porto, terminal, armador, frete, "
        "conhecimento de embarque, BL, booking"
    ),
    "no_speech_threshold": 0.6,
    "log_prob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
    "enable_formatting": True,
    "remove_fillers": True,
    "voice_commands": True,
    "audio_ducking": True,
    "ducking_volume": 0.20,
    "noise_suppression": True,
    # Aparência (flat: load_config faz merge raso com o config do usuário)
    "accent": "indigo",
    "accent_custom": None,
    "overlay_style": "orb",
    "overlay_size": "m",
    "overlay_position": "bottom",
    "overlay_show_text": True,
    "overlay_glow": 0.8,
    "reduce_motion": False,
    "word_overrides": {
        "m2a metais": "M2A Metais",
        "arcelormittal": "ArcelorMittal",
        "tesc": "TESC",
        "brutaldev": "brutaldev",
        "bl": "B/L",
        "booking": "Booking",
        "incoterms": "Incoterms"
    }
}


TICK_INTERVAL = 0.05
SPEECH_START_TICKS = 3
CALIBRATION_WAIT_TIMEOUT = 5.0
CALIBRATION_MEASURE_SECS = 1.0
PRE_BUFFER_SECS = 0.3
# Mic dinâmico com noise gate (Yeti GX) fala a ~0.0005–0.003 RMS; 0.003 cortava a voz.
THRESHOLD_FLOOR = 0.0005
# Unidades de ganho do Yeti toleradas antes de a calibração salva deixar de valer.
HW_GAIN_TOLERANCE = 5
DAEMON_TIMEOUT = 60.0
RNNOISE_MODEL_NAME = "bd.rnnn"

# veredito → (título, cor, explicação), compartilhado por terminal e janela
CALIBRATION_VERDICTS = {
    "ok": ("Calibrado", "#64FFA0", "Voz bem acima do ruído. Pronto para ditar."),
    "low": ("Calibrado · sinal baixo", "#FFC83C",
            "Funciona, mas suba o ganho do mic ou fale mais perto (~5 cm) para transcrever melhor."),
    "weak": ("A voz não se destacou do ruído", "#FF7864",
             "Mic mutado, ganho no mínimo ou longe demais. Nada salvo."),
    "muted": ("Sem sinal", "#FF7864",
              "Zero digital: mic mutado (no Yeti, LED vermelho) ou noise gate fechado. Nada salvo."),
}


def load_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)


def save_config(config):
    """Escrita atômica: o painel salva a cada mudança; um crash no meio não corrompe o config."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_FILE)


def _debug_log(msg):
    """Append debug info to log file."""
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except OSError:
        pass
