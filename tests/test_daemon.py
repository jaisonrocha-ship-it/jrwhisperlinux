#!/usr/bin/env python3
"""
Test: Comunicação com o Daemon e velocidade de resposta do dictate v3.0
"""
import sys, os

VENV_PYTHON = os.path.expanduser("~/.local/share/dictation-venv/bin/python3")
if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

import time, socket, json

DAEMON_SOCKET = "/tmp/dictate_daemon.sock"

def test_daemon_client():
    print("=" * 60)
    print("TEST: Cliente de Daemon do Whisper")
    print("=" * 60)

    if not os.path.exists(DAEMON_SOCKET):
        print(f"ERRO: Daemon socket {DAEMON_SOCKET} não existe.")
        return

    # Usar o wav de teste anterior
    wav_path = "/tmp/dictate_last.wav"
    if not os.path.exists(wav_path):
        print(f"ERRO: Arquivo de áudio {wav_path} para teste não encontrado.")
        return

    print(f"\nEnviando requisição de transcrição para {wav_path}...")
    
    t0 = time.time()
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10.0)
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
        else:
            print(f"❌ ERRO DO DAEMON: {resp.get('error')}")
            
    except Exception as e:
        print(f"❌ FALHA NA COMUNICAÇÃO: {e}")

if __name__ == "__main__":
    test_daemon_client()
