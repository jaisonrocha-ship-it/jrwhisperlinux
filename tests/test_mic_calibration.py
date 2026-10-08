#!/usr/bin/env python3
"""Calibração por mic e mic de reserva, sem áudio nem hardware."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import audio as d
d.save_config = lambda config: None  # nunca toca ~/.config nos testes

YETI = "alsa_input.usb-Logitech_Yeti_GX_2404SG0012M8-00.capture.0.0"
PCI = "alsa_input.pci-0000_00_1f.3.capture.0.0"


def test_evaluate_levels():
    quiet = np.full(60, 0.0001)
    assert d.evaluate_levels(quiet, np.full(100, 0.012))["verdict"] == "ok"
    assert d.evaluate_levels(quiet, np.full(100, 0.002))["verdict"] == "low"
    assert d.evaluate_levels(quiet, np.full(100, 0.00015))["verdict"] == "weak"
    assert d.evaluate_levels(np.zeros(60), np.zeros(100))["verdict"] == "muted"
    r = d.evaluate_levels(quiet, np.full(100, 0.012))
    assert r["noise"] < r["threshold"] < r["voice"]


def test_calibration_follows_hw_gain():
    config = {}
    d.hw_gain_for = lambda mic: 69 if d.is_yeti(mic) else None
    d.save_mic_calibration(config, YETI, {"threshold": 0.003, "noise": 0.0001, "voice": 0.012})
    assert config["mic_calibrations"][YETI]["hw_gain"] == 69
    assert d.calibrated_threshold(config, YETI) == 0.003
    d.hw_gain_for = lambda mic: 72          # dentro da tolerância
    assert d.calibrated_threshold(config, YETI) == 0.003
    d.hw_gain_for = lambda mic: 87          # ganho mudou: volta ao automático
    assert d.calibrated_threshold(config, YETI) is None
    assert d.calibration_state(config, YETI)[0] == "stale"
    assert d.calibrated_threshold(config, PCI) is None


def test_resolve_mic_fallback():
    d.default_source_name = lambda: PCI
    d.list_source_names = lambda: [YETI, PCI]
    assert d.resolve_mic({"mic_device": YETI}) == (YETI, False)
    d.list_source_names = lambda: [PCI]     # Yeti desplugado
    assert d.resolve_mic({"mic_device": YETI}) == (PCI, True)
    assert d.resolve_mic({"mic_device": "@DEFAULT_SOURCE@"}) == (PCI, False)
    d.list_source_names = lambda: []        # pactl indisponível: confia no config
    assert d.resolve_mic({"mic_device": YETI}) == (YETI, False)


def test_mic_options_readable():
    pci0, pci2 = "alsa_input.pci-0000_00_1f.3.capture.0.0", "alsa_input.pci-0000_00_1f.3.capture.2.0"
    yeti = "alsa_input.usb-Logitech_Yeti_GX_2404SG0012M8-00.capture.0.0"
    labels = [l for _n, l in d.mic_options([pci0, pci2, yeti], yeti)]
    assert labels == ["Áudio Interno (PCI)", "Áudio Interno (PCI) · 2", "Yeti GX"]  # sem nomes repetidos
    assert d.mic_options([pci0], yeti)[-1] == (yeti, "Yeti GX · desconectado")   # nunca o id técnico
    assert d.mic_options([pci0], "@DEFAULT_SOURCE@") == [(pci0, "Áudio Interno (PCI)")]


def run_tests():
    failed = False
    for fn in (test_evaluate_levels, test_calibration_follows_hw_gain, test_resolve_mic_fallback, test_mic_options_readable):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
