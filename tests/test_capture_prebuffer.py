#!/usr/bin/env python3
"""Testes do pré-buffer e da resolução do modelo RNNoise (sem parec)."""
import os
import sys
import importlib.machinery
import importlib.util

dictate_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/dictate"))
loader = importlib.machinery.SourceFileLoader("dictate", dictate_path)
spec = importlib.util.spec_from_loader("dictate", loader)
dictate = importlib.util.module_from_spec(spec)
loader.exec_module(dictate)


def test_rnnoise_resolves_repo_model():
    path = dictate.resolve_rnnoise_model_path()
    assert path and os.path.isfile(path), f"bd.rnnn não encontrado: {path}"
    assert os.path.basename(path) == "bd.rnnn"
    # Já houve um "404: Not Found" de 14 bytes salvo como bd.rnnn; o modelo real tem ~300KB.
    assert os.path.getsize(path) > 100_000, f"bd.rnnn inválido ({os.path.getsize(path)} bytes): {path}"
    print(f"RNNoise: {path}")


def test_prebuffer_without_wait_overlap():
    cap = dictate.AudioCapture("@DEFAULT_SOURCE@", sr=16000)
    chunk_a = b"\x00\x10" * 512  # 1024 bytes, like parec
    chunk_b = b"\x00\x20" * 512
    wait_noise = b"\x00\x01" * 512 * 20  # ~20 chunks of silence while waiting

    with cap._lock:
        cap.buffer.extend(wait_noise)
        for _ in range(8):
            cap._pre_buffer.append(chunk_a)
        cap.buffer.extend(chunk_a * 8)

    cap.discard_live_buffer()
    assert len(cap.buffer) == 0

    pre = cap.take_pre_buffer_clear_live()
    assert len(pre) == 8 * 512
    assert len(cap.buffer) == 0

    with cap._lock:
        cap.buffer.extend(chunk_b)
    live = cap.get_audio_float32()
    assert len(live) == 512
    # Attack audio is only the pre-buffer, not the discarded wait noise.
    assert len(pre) < 512 * 20


def run_tests():
    failed = False
    for fn in (test_rnnoise_resolves_repo_model, test_prebuffer_without_wait_overlap):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
