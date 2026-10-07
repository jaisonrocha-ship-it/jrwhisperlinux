import sys
import os
import signal
import subprocess
import json
import time
import socket

from .config import CONFIG_DIR, DAEMON_PID_FILE, DAEMON_SOCKET, DAEMON_TIMEOUT, RNNOISE_MODEL_NAME, _debug_log
from .textproc import is_hallucination


CUBLAS_SEARCH_PATHS = [
    "/opt/resolve/libs",
    "/usr/local/cuda-12/lib64",
    "/usr/local/cuda/lib64",
]


def resolve_rnnoise_model_path():
    """Localiza bd.rnnn: cópia do instalador em ~/.config/dictate, senão o repo."""
    # realpath: ~/.local/bin/dictate costuma ser symlink para src/dictate.
    # src/jrwhisper/transcribe.py → <repo>/config (realpath: ~/.local/bin/dictate é symlink)
    repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    candidates = [
        os.path.join(CONFIG_DIR, RNNOISE_MODEL_NAME),
        os.path.join(repo_dir, "config", RNNOISE_MODEL_NAME),
    ]
    for path in candidates:
        resolved = os.path.normpath(path)
        if os.path.isfile(resolved):
            return resolved
    return None


def get_free_vram_mb():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            timeout=3
        ).decode().strip()
        return max(int(x) for x in out.split('\n') if x.strip())
    except Exception:
        return 0


def _find_cublas_path():
    """Procura libcublas.so.12 em caminhos conhecidos."""
    for path in CUBLAS_SEARCH_PATHS:
        if os.path.isfile(os.path.join(path, "libcublas.so.12")):
            return path
    return None


_cublas_preloaded = False


def _preload_cublas():
    """Pré-carrega libcublas.so.12 e libcublasLt.so.12 via ctypes.

    Setar LD_LIBRARY_PATH depois que o processo já iniciou não funciona —
    o linker dinâmico não relê a variável. ctypes.cdll.LoadLibrary() é
    a forma correta de disponibilizar libs para módulos carregados depois.
    """
    global _cublas_preloaded
    if _cublas_preloaded:
        return True

    import ctypes
    cublas_path = _find_cublas_path()
    if not cublas_path:
        return False

    try:
        ctypes.cdll.LoadLibrary(os.path.join(cublas_path, "libcublas.so.12"))
        ctypes.cdll.LoadLibrary(os.path.join(cublas_path, "libcublasLt.so.12"))
        _cublas_preloaded = True
        _debug_log(f"cuBLAS preloaded from {cublas_path}")
        return True
    except OSError as e:
        _debug_log(f"cuBLAS preload falhou: {e}")
        return False


def choose_device(config):
    """Decide CUDA vs CPU baseado na VRAM livre e disponibilidade de cublas."""
    min_vram = config.get("gpu_min_vram_mb", 2500)
    free = get_free_vram_mb()

    if free >= min_vram:
        if _preload_cublas():
            _debug_log(f"GPU: VRAM={free}MB, cublas preloaded")
            return "cuda", "int8_float16"
        else:
            _debug_log(f"GPU: VRAM={free}MB mas cublas.so.12 não encontrado, usando CPU")

    _debug_log(f"CPU: VRAM={free}MB (min={min_vram}MB)")
    return "cpu", "int8"


def _transcribe_kwargs(cfg):
    """Parâmetros do Whisper a partir do config (ou da requisição do daemon, mesmas chaves)."""
    language = cfg.get("language") or "pt"
    return dict(
        beam_size=5,
        vad_filter=cfg.get("vad_filter", True),
        language=None if language == "auto" else language,  # None = o Whisper detecta
        initial_prompt=cfg.get("initial_prompt", ""),
        no_speech_threshold=cfg.get("no_speech_threshold", 0.6),
        log_prob_threshold=cfg.get("log_prob_threshold", -1.0),
        compression_ratio_threshold=cfg.get("compression_ratio_threshold", 2.4),
        condition_on_previous_text=False,
        temperature=0.0,
        task=cfg.get("task") or "transcribe",  # "translate": o próprio Whisper traduz para inglês
    )


def _pick_language(model, wav_path, allowed):
    """Idioma "automático" só entre os que você usa: livre, o Whisper chuta entre 99 a cada trecho
    curto ("artı tutarlar düzgün" para português falado com música atrás)."""
    from faster_whisper import decode_audio
    _lang, _p, probs = model.detect_language(decode_audio(wav_path))
    probs = dict(probs)
    return max(allowed, key=lambda lang: probs.get(lang, 0.0))


def _run(model, wav_path, cfg):
    """(texto, idioma falado, confiança do idioma, [(início, fim, texto)] dos segmentos)."""
    kwargs = _transcribe_kwargs(cfg)
    if kwargs["language"] is None and cfg.get("auto_languages"):
        kwargs["language"] = _pick_language(model, wav_path, cfg["auto_languages"])
        _debug_log(f"Idioma detectado: {kwargs['language']}")
    segments, info = model.transcribe(wav_path, **kwargs)
    if not cfg.get("vad_filter", True):
        # Sem VAD, ruído vira frase inventada com confiança baixa (avg_logprob ~-1,4; música ~-0,3).
        floor = cfg.get("log_prob_threshold", -1.0)
        segments = [s for s in segments if s.avg_logprob >= floor]
    segments = list(segments)
    return (" ".join(s.text.strip() for s in segments).strip(), info.language, info.language_probability,
            [(s.start, s.end, s.text.strip()) for s in segments])


class Transcriber:
    def __init__(self, config):
        self.config = config
        self.model = None
        self._device = None
        self.last_language = None  # idioma detectado na última transcrição
        self.last_language_prob = 0.0
        self.last_segments = []      # [(início, fim, texto)]: as legendas cortam o áudio nesses limites
        self.use_daemon = self._check_daemon_alive()
        if not self.use_daemon:
            _debug_log("Daemon não detectado. Carregando modelo localmente (fallback)...")
            self._load_model()
        else:
            _debug_log("Daemon detectado. Usando modo cliente.")

    def _check_daemon_alive(self):
        if not os.path.exists(DAEMON_SOCKET):
            return False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.2)
            s.connect(DAEMON_SOCKET)
            s.close()
            return True
        except Exception:
            return False

    def _load_model(self):
        from faster_whisper import WhisperModel
        device, compute = choose_device(self.config)

        try:
            self.model = WhisperModel(
                self.config["model"],
                device=device,
                compute_type=compute
            )
            self._device = device
            _debug_log(f"Modelo carregado localmente: {self.config['model']} em {device} ({compute})")
        except Exception as e:
            if device == "cuda":
                _debug_log(f"CUDA load local falhou ({e}), fallback CPU")
                self.model = WhisperModel(
                    self.config["model"],
                    device="cpu",
                    compute_type="int8"
                )
                self._device = "cpu"
            else:
                raise

    def _denoise_file(self, wav_path):
        """Aplica o filtro de isolamento de voz RNNoise do FFmpeg."""
        model_path = resolve_rnnoise_model_path()
        if not model_path:
            _debug_log("RNNoise: modelo bd.rnnn não encontrado, pulando isolamento de voz")
            return wav_path

        denoised_path = wav_path + ".denoised.wav"
        try:
            cmd = [
                "nice", "-n", "19", "ffmpeg", "-y", "-i", wav_path,
                "-af", f"arnndn=m={model_path},aresample=16000",
                denoised_path
            ]
            result = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
            )
            if (
                result.returncode == 0
                and os.path.exists(denoised_path)
                and os.path.getsize(denoised_path) > 1000
            ):
                _debug_log(f"Isolamento de voz aplicado com sucesso: {denoised_path}")
                return denoised_path
            _debug_log(f"RNNoise: ffmpeg retornou {result.returncode}, usando WAV original")
        except Exception as e:
            _debug_log(f"Falha ao aplicar isolamento de voz: {e}")
        return wav_path

    def transcribe_file(self, wav_path, denoise=True, second_pass=True):
        """Transcreve o arquivo WAV. Tenta via Daemon, fallback para local."""
        if not os.path.exists(wav_path):
            return ""

        original_path = wav_path
        if denoise and self.config.get("noise_suppression", True):
            wav_path = self._denoise_file(wav_path)

        try:
            text = self._clean(self._transcribe_internal(wav_path))
            if not text and second_pass:
                text = self._second_pass(original_path)
            return text
        finally:
            if wav_path != original_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    def _second_pass(self, wav_path):
        """Nada na passada normal: tenta de novo sem os filtros que derrubam música.

        O RNNoise apaga a música e o vocal junto; o VAD (Silero) não vê voz cantada como fala;
        o idioma fixo transforma letra em inglês em lixo ("Tchau, tchau."). Sem esses filtros,
        ruído vira frase inventada: _run corta segmentos de confiança baixa e aqui só valem 4+ palavras
        (alucinação curta como "Thank you." vem com confiança alta).
        """
        # ponytail: corte por nº de palavras; se ruído longo passar, usar no_speech_prob dos segmentos
        cfg = dict(self.config, language="auto", initial_prompt="", vad_filter=False)
        text = self._clean(self._transcribe_internal(wav_path, cfg))
        _debug_log(f"2ª passada (sem RNNoise/VAD, idioma automático): {text!r}")
        return text if len(text.split()) >= 4 else ""

    @staticmethod
    def _clean(text):
        if is_hallucination(text):
            _debug_log(f"Alucinação descartada: {text!r}")
            return ""
        return text

    def _transcribe_internal(self, wav_path, cfg=None):
        """Lógica interna de transcrição (Daemon / Local)."""
        cfg = cfg or self.config

        if self.use_daemon:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(DAEMON_TIMEOUT)
                s.connect(DAEMON_SOCKET)

                keys = ("model", "language", "initial_prompt", "no_speech_threshold",
                        "log_prob_threshold", "compression_ratio_threshold", "vad_filter", "auto_languages", "task")
                req = {"action": "transcribe", "wav_path": wav_path, **{k: cfg[k] for k in keys if k in cfg}}
                s.sendall(json.dumps(req).encode('utf-8'))


                data = []
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data.append(chunk)
                s.close()

                resp = json.loads(b''.join(data).decode('utf-8'))
                if "text" in resp:
                    self.last_language = resp.get("language")
                    self.last_language_prob = resp.get("language_probability", 0.0)
                    self.last_segments = resp.get("segments", [])
                    return resp["text"].strip()
                else:
                    _debug_log(f"Erro do daemon: {resp.get('error')}")
            except socket.timeout:
                _debug_log(f"Daemon não respondeu em {DAEMON_TIMEOUT:.0f}s")
                return ""
            except Exception as e:
                _debug_log(f"Falha de comunicação com o daemon ({e}), tentando local...")
                self.use_daemon = False


        if not self.model:
            self._load_model()

        try:
            text, self.last_language, self.last_language_prob, self.last_segments = _run(self.model, wav_path, cfg)
            return text
        except Exception as e:
            if self._device != "cuda":
                return ""
            _debug_log(f"CUDA transcribe local falhou ({e}), recriando modelo CPU")
            try:
                from faster_whisper import WhisperModel
                self.model = WhisperModel(self.config["model"], device="cpu", compute_type="int8")
                self._device = "cpu"
                text, self.last_language, self.last_language_prob, self.last_segments = _run(self.model, wav_path, cfg)
                return text
            except Exception:
                return ""


def is_daemon_running():
    if not os.path.exists(DAEMON_PID_FILE):
        return False
    try:
        with open(DAEMON_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def run_daemon(config):
    """Inicializa o daemon do Whisper persistente."""

    if is_daemon_running():
        with open(DAEMON_PID_FILE) as f:
            pid = int(f.read().strip())
        print(f"Daemon já está rodando no PID {pid}")
        sys.exit(0)
    else:
        try:
            if os.path.exists(DAEMON_PID_FILE):
                os.remove(DAEMON_PID_FILE)
        except OSError:
            pass

    with open(DAEMON_PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    _debug_log("=== DAEMON INICIADO ===")

    if os.path.exists(DAEMON_SOCKET):
        try:
            os.remove(DAEMON_SOCKET)
        except OSError:
            pass

    from faster_whisper import WhisperModel

    def load(name):
        device, compute = choose_device(config)
        _debug_log(f"Daemon: Carregando modelo '{name}' em {device} ({compute})...")
        return WhisperModel(name, device=device, compute_type=compute)

    loaded = config["model"]
    try:
        model = load(loaded)
        _debug_log("Daemon: Modelo carregado e pronto.")
    except Exception as e:
        _debug_log(f"Daemon: Erro crítico ao carregar modelo: {e}")
        try:
            os.remove(DAEMON_PID_FILE)
        except OSError:
            pass
        sys.exit(1)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(DAEMON_SOCKET)
    server.listen(5)

    os.chmod(DAEMON_SOCKET, 0o600)

    def shutdown(signum, frame):
        _debug_log("Daemon: Encerrando...")
        server.close()
        for f in [DAEMON_SOCKET, DAEMON_PID_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print("Daemon do Whisper iniciado no socket:", DAEMON_SOCKET)

    while True:
        try:
            conn, _ = server.accept()
            conn.settimeout(5.0)
            req_data = conn.recv(16384)
            if not req_data:
                conn.close()
                continue

            req = json.loads(req_data.decode('utf-8'))
            action = req.get("action")

            if action == "transcribe":
                wav_path = req.get("wav_path")
                if not wav_path or not os.path.exists(wav_path):
                    conn.sendall(json.dumps({"error": "WAV file not found"}).encode('utf-8'))
                    conn.close()
                    continue

                _debug_log(f"Daemon: Transcrevendo {wav_path}...")
                t0 = time.time()
                # Modelo trocado nos Ajustes: recarrega aqui, sem reiniciar o serviço.
                want = req.get("model") or loaded
                if want != loaded:
                    model = None  # libera a VRAM antes de carregar o outro
                    try:
                        model, loaded = load(want), want
                    except Exception as ex:
                        _debug_log(f"Daemon: modelo '{want}' falhou ({ex}); mantendo '{loaded}'")
                        model = load(loaded)
                try:
                    text, language, prob, segs = _run(model, wav_path, req)
                    t1 = time.time()
                    _debug_log(f"Daemon: Sucesso em {t1-t0:.2f}s -> {text[:100]}")
                    conn.sendall(json.dumps({"text": text, "language": language, "language_probability": prob,
                                              "segments": segs}).encode('utf-8'))
                except Exception as ex:
                    _debug_log(f"Daemon: Erro de transcrição: {ex}")
                    conn.sendall(json.dumps({"error": str(ex)}).encode('utf-8'))
            else:
                conn.sendall(json.dumps({"error": "Unknown action"}).encode('utf-8'))

            conn.close()
        except Exception as e:
            _debug_log(f"Daemon: Erro no loop de conexão: {e}")
