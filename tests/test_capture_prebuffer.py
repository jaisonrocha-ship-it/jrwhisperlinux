#!/usr/bin/env python3
"""Testes do pré-buffer e da resolução do modelo RNNoise (sem parec)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import audio, transcribe


def test_rnnoise_resolves_repo_model():
    path = transcribe.resolve_rnnoise_model_path()
    assert path and os.path.isfile(path), f"bd.rnnn não encontrado: {path}"
    assert os.path.basename(path) == "bd.rnnn"
    # Já houve um "404: Not Found" de 14 bytes salvo como bd.rnnn; o modelo real tem ~300KB.
    assert os.path.getsize(path) > 100_000, f"bd.rnnn inválido ({os.path.getsize(path)} bytes): {path}"
    print(f"RNNoise: {path}")


def test_singing_survives_rnnoise():
    """RNNoise apaga voz cantada (música no celular): sem texto, transcreve o áudio original."""
    import tempfile
    t = transcribe.Transcriber.__new__(transcribe.Transcriber)
    t.config = {"noise_suppression": True}
    seen = []
    t._denoise_file = lambda p: p + ".denoised.wav"
    t._transcribe_internal = lambda p: seen.append(p) or ("" if p.endswith(".denoised.wav") else "I think I love you")
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        assert t.transcribe_file(f.name) == "I think I love you"
        assert seen == [f.name + ".denoised.wav", f.name]
        seen.clear()
        t._transcribe_internal = lambda p: seen.append(p) or "Olá, tudo bem?"
        assert t.transcribe_file(f.name) == "Olá, tudo bem?" and len(seen) == 1  # fala normal: uma passada só


def test_prebuffer_without_wait_overlap():
    cap = audio.AudioCapture("@DEFAULT_SOURCE@", sr=16000)
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
    for fn in (test_rnnoise_resolves_repo_model, test_singing_survives_rnnoise, test_prebuffer_without_wait_overlap):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
