#!/usr/bin/env python3
"""
Test: GPU CUDA + cublas detection e fallback para dictate v2.0
"""
import sys, os

VENV_PYTHON = os.path.expanduser("~/.local/share/dictation-venv/bin/python3")
if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

import time, subprocess

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
        current = os.environ.get("LD_LIBRARY_PATH", "")
        if cublas_path not in current:
            os.environ["LD_LIBRARY_PATH"] = f"{cublas_path}:{current}" if current else cublas_path

        from faster_whisper import WhisperModel

        # GPU test
        t0 = time.time()
        try:
            model = WhisperModel('medium', device='cuda', compute_type='int8_float16')
            t1 = time.time()
            print(f"   Model loaded: {t1-t0:.2f}s")

            if os.path.exists('/tmp/dictate_last.wav'):
                segments, _ = model.transcribe('/tmp/dictate_last.wav', beam_size=3, language='pt', vad_filter=True)
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
        model = WhisperModel('medium', device='cpu', compute_type='int8')
        t1 = time.time()
        print(f"   Model loaded: {t1-t0:.2f}s")

        if os.path.exists('/tmp/dictate_last.wav'):
            segments, _ = model.transcribe('/tmp/dictate_last.wav', beam_size=3, language='pt', vad_filter=True)
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
