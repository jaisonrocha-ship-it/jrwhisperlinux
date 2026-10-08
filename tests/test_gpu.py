#!/usr/bin/env python3
"""
Test: GPU CUDA + cublas detection e fallback para dictate v2.0
"""
import sys, os

VENV_PYTHON = os.path.expanduser("~/.local/share/dictation-venv/bin/python3")
if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

import time, subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper.config import load_config
from jrwhisper.transcribe import _preload_cublas

MODEL = load_config()["model"]  # o modelo que você usa (já baixado); fixo em 'medium' baixava 1,5 GB à toa

LAST_WAV = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "dictate_last.wav")

CUBLAS_SEARCH_PATHS = [
    "/opt/resolve/libs",
    "/usr/local/cuda-12/lib64",
    "/usr/local/cuda/lib64",
]

def test_gpu():
    print("=" * 60)
    print("TEST: GPU CUDA + cuBLAS Detection")
    print("=" * 60)

    # 1. Check nvidia-smi
    print("\n1. nvidia-smi:")
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.free,memory.total", "--format=csv,noheader"],
            timeout=3
        ).decode().strip()
        print(f"   {out}")
        free_vram = int(out.split(',')[1].strip().split()[0])
    except Exception as e:
        print(f"   FALHA: {e}")
        free_vram = 0

    # 2. Check cublas
    print("\n2. cuBLAS search:")
    cublas_path = None
    for path in CUBLAS_SEARCH_PATHS:
        exists = os.path.isfile(os.path.join(path, "libcublas.so.12"))
        print(f"   {path}: {'✅ FOUND' if exists else '❌ not found'}")
        if exists and not cublas_path:
            cublas_path = path

    # 3. Test ctranslate2
    print("\n3. ctranslate2 CUDA:")
    import ctranslate2
    print(f"   Version: {ctranslate2.__version__}")
    try:
        count = ctranslate2.get_cuda_device_count()
        print(f"   CUDA devices: {count}")
        types = ctranslate2.get_supported_compute_types('cuda')
        print(f"   CUDA types: {types}")
    except Exception as e:
        print(f"   CUDA error: {e}")

    # 4. Test model load + transcribe
    if cublas_path and free_vram >= 2500:
        print(f"\n4. GPU Transcription Test (cublas={cublas_path}):")
        # LD_LIBRARY_PATH com o processo rodando não vale (o linker não relê): preload, como o app (Regra 3)
        print(f"   preload: {_preload_cublas()}")

        from faster_whisper import WhisperModel

        # GPU test
        t0 = time.time()
        try:
            model = WhisperModel(MODEL, device='cuda', compute_type='int8_float16')
            t1 = time.time()
            print(f"   Model loaded: {t1-t0:.2f}s")

            if os.path.exists(LAST_WAV):
                segments, _ = model.transcribe(LAST_WAV, beam_size=3, language='pt', vad_filter=True)
                text = ' '.join(s.text.strip() for s in segments)
                t2 = time.time()
                print(f"   Transcribe: {t2-t1:.2f}s")
                print(f"   Text: {text[:100]}")
                print(f"   TOTAL GPU: {t2-t0:.2f}s ✅")
            else:
                print("   No test wav file")
            del model
        except Exception as e:
            print(f"   GPU FAILED: {e}")
            t1 = time.time()

        # CPU comparison
        print(f"\n5. CPU Comparison:")
        t0 = time.time()
        model = WhisperModel(MODEL, device='cpu', compute_type='int8')
        t1 = time.time()
        print(f"   Model loaded: {t1-t0:.2f}s")

        if os.path.exists(LAST_WAV):
            segments, _ = model.transcribe(LAST_WAV, beam_size=3, language='pt', vad_filter=True)
            text = ' '.join(s.text.strip() for s in segments)
            t2 = time.time()
            print(f"   Transcribe: {t2-t1:.2f}s")
            print(f"   TOTAL CPU: {t2-t0:.2f}s")
        del model
    else:
        print(f"\n4. Skipping GPU test (cublas={cublas_path}, vram={free_vram}MB)")

    print("\nDone!")


if __name__ == "__main__":
    test_gpu()
