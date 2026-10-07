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
    "auto_languages": ["pt", "en"],  # "auto" escolhe só entre estes
    "caption_language": "pt",        # legendas ao vivo traduzem para este ("" = idioma original)
    "caption_lines": 8,              # linhas visíveis na legenda (o ditado mostra 3)
    "caption_translator": "auto",    # auto (NVIDIA se houver chave, senão Ollama local) | ollama | nvidia
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
    "pause_media": True,
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
    },
    # Geral
    "sounds": False,
    # Atalhos de texto: gatilho falado → expansão (aceita várias linhas)
    "snippets": {},
    # Inteligência (reescrita com IA). A chave da API fica no keyring, nunca aqui.
    "ai_enabled": False,
    "ai_provider": "nvidia",
    "ai_model": "nvidia/nemotron-3-super-120b-a12b",
    "ai_ollama_url": "http://localhost:11434",
    "ai_ollama_model": "llama3.2",
    "ai_default_mode": "",
    "ai_voice_prefix": True,
    "ai_timeout": 8.0,
    "ai_modes": [
        {"id": "corrigir", "name": "Corrigir", "enabled": True,
         "prompt": "Corrija ortografia, gramática e pontuação do texto ditado, mantendo palavras, tom e idioma. "
                   "Responda só com o texto corrigido."},
        {"id": "email", "name": "E-mail", "enabled": True,
         "prompt": "Reescreva o texto ditado como um e-mail profissional e cordial em português, com saudação e "
                   "despedida curtas. Não invente fatos nem nomes. Termine em \"Atenciosamente,\" sem assinatura "
                   "nem marcadores como [Seu nome]. Responda só com o e-mail."},
        {"id": "mensagem", "name": "Mensagem", "enabled": True,
         "prompt": "Reescreva o texto ditado como uma mensagem curta e natural de chat, mantendo o sentido. "
                   "Responda só com a mensagem."},
        {"id": "ingles", "name": "Inglês", "enabled": True,
         "prompt": "Traduza o texto ditado para inglês natural e fluente, mantendo o tom. Responda só com a tradução."},
        {"id": "topicos", "name": "Tópicos", "enabled": True,
         "prompt": "Transforme o texto ditado em uma lista de tópicos objetiva, um item por linha começando com "
                   "\"- \". Responda só com a lista."},
    ],
    # Perfis por aplicativo (classe da janela → regras)
    "profiles_enabled": False,
    "profiles": [
        {"match": "kitty|guake|gnome-terminal|xterm|terminator|tilix|alacritty|wezterm|konsole",
         "name": "Terminais", "paste": "ctrl+shift+v", "formatting": False, "final_period": False,
         "capitalize": False, "ai_mode": ""},
        {"match": "code|cursor|jetbrains|sublime_text|zed",
         "name": "Editores de código", "paste": "ctrl+v", "formatting": True, "final_period": False,
         "capitalize": True, "ai_mode": ""},
        {"match": "slack|discord|telegram|whatsapp|signal",
         "name": "Chat", "paste": "ctrl+v", "formatting": True, "final_period": False,
         "capitalize": True, "ai_mode": ""},
        {"match": "thunderbird|evolution|geary",
         "name": "E-mail", "paste": "ctrl+v", "formatting": True, "final_period": True,
         "capitalize": True, "ai_mode": ""},
    ],
    # Histórico
    "history_enabled": False,
    "history_retention_days": 30,
    # Mãos livres
    "ptt_enabled": False,
    "handsfree_enabled": False,
    "handsfree_idle_secs": 20,
    "handsfree_stop_phrase": "parar ditado",
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
    try:
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:  # config corrompido não pode impedir o ditado
        _debug_log(f"config.json ilegível ({e}); usando os padrões")
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
