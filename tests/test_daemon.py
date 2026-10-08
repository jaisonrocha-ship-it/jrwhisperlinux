#!/usr/bin/env python3
"""
Test: Comunicação com o Daemon e velocidade de resposta do dictate v3.0
"""
import sys, os

VENV_PYTHON = os.path.expanduser("~/.local/share/dictation-venv/bin/python3")
if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

import time, socket, json, wave, tempfile

RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
DAEMON_SOCKET = os.path.join(RUNTIME_DIR, "dictate_daemon.sock")
LAST_WAV = os.path.join(RUNTIME_DIR, "dictate_last.wav")

def test_daemon_client():
    print("=" * 60)
    print("TEST: Cliente de Daemon do Whisper")
    print("=" * 60)

    if not os.path.exists(DAEMON_SOCKET):
        print(f"ERRO: Daemon socket {DAEMON_SOCKET} não existe.")
        return False

    # Último ditado, ou 1s de silêncio só para validar o protocolo.
    wav_path = LAST_WAV
    if not os.path.exists(wav_path):
        wav_path = os.path.join(RUNTIME_DIR, "dictate_test_silence.wav")
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 16000)

    print(f"\nEnviando requisição de transcrição para {wav_path}...")
    
    t0 = time.time()
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(60.0)
        s.connect(DAEMON_SOCKET)
        
        req = {
            "action": "transcribe",
            "wav_path": wav_path,
            "language": "pt",
            "initial_prompt": "Termos portuários Incoterms FOB CIF TESC ArcelorMittal",
            "no_speech_threshold": 0.6,
            "log_prob_threshold": -1.0,
            "compression_ratio_threshold": 2.4,
        }
        s.sendall(json.dumps(req).encode('utf-8'))
        
        # Recebe resposta
        data = []
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data.append(chunk)
        s.close()
        
        t1 = time.time()
        resp = json.loads(b''.join(data).decode('utf-8'))
        
        if "text" in resp:
            print(f"✅ SUCESSO ({t1-t0:.3f}s)")
            print(f"   Texto: \"{resp['text']}\"")
            return True
        print(f"❌ ERRO DO DAEMON: {resp.get('error')}")
    except Exception as e:
        print(f"❌ FALHA NA COMUNICAÇÃO: {e}")
    return False

if __name__ == "__main__":
    sys.exit(0 if test_daemon_client() else 1)
