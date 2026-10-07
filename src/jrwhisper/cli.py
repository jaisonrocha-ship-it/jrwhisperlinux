"""
JRWhisper — ditado por voz local para Linux (faster-whisper + GTK3).

USO:
  dictate                       → Dita (atalho padrão Super+Shift+V). De novo: encerra e transcreve
  dictate --settings / -s [aba] → Ajustes (abas: general, appearance, microphone, recognition,
                                  text, ai, apps, history, handsfree, advanced)
  dictate --mode <id>           → Dita já com um modo de IA (corrigir, email, mensagem, ingles, topicos)
  dictate --system              → Transcreve o som do computador (vídeo, reunião); de novo: encerra
  dictate --history             → Busca rápida no histórico (Enter cola)
  dictate --calibrate           → Mede ruído e voz, diagnostica o mic e salva o limiar
  dictate --calibrate-gui       → Mesma calibração em janela, com medidor ao vivo
  dictate --daemon              → Serviço que mantém o modelo carregado
  dictate --status              → Informações e estado
  dictate --config              → Mostra o config efetivo (JSON)
"""

import sys
import json
import time
import numpy as np
from gi.repository import Gtk

from . import __version__
from .audio import AudioCapture, calibration_state, evaluate_levels, friendly_mic_name, is_yeti, measure_levels, resolve_mic, rms_db, save_mic_calibration, yeti_hw_status
from .config import CALIBRATION_VERDICTS, load_config
from .dictation import is_running, run_overlay_mode
from .transcribe import _find_cublas_path, choose_device, get_free_vram_mb, is_daemon_running, run_daemon
from .ui.calibration import CalibrationWindow
from .ui.settings import SettingsWindow


def _level_bar(rms, width=30):
    """Barra em dBFS: -80 dB vazio, 0 dB cheio (mesma escala da janela)."""
    db = rms_db(rms)
    filled = int(np.clip((db + 80) / 80, 0, 1) * width)
    return "#" * filled + "." * (width - filled) + f" {rms:.5f} ({db:.0f} dBFS)"


def run_calibration(config):
    """Versão terminal da CalibrationWindow: mede, avalia e salva por mic."""
    mic, fell_back = resolve_mic(config)
    print(f"Microfone: {friendly_mic_name(mic)} ({mic})")
    if fell_back:
        print(f"  (mic configurado ausente: {config.get('mic_device')})")
    if is_yeti(mic):
        hw = yeti_hw_status()
        if hw:
            print(f"Yeti GX (hardware): ganho {hw.get('gain')}/100, {'MUTADO' if hw.get('muted') else 'ativo'}")
            if hw.get("muted"):
                print("Desmute (toque no knob ou OBSBOT Control) e rode de novo. Nada salvo.")
                return 1
    capture = AudioCapture(mic, config["sample_rate"])
    capture.start()
    try:
        if not capture.wait_for_data():
            print("ERRO: nenhum áudio chegou. Mic desconectado ou mic_device errado (veja: pactl list short sources).")
            return 1

        def measure(secs):
            time.sleep(0.5)  # descarta o clique do Enter (mic perto do teclado)
            vals = measure_levels(capture, secs, lambda v: print("\r  " + _level_bar(v), end="", flush=True))
            print()
            return vals

        input("\n1/2  Fique em SILÊNCIO e aperte Enter (mede 3s)...")
        noise_vals = measure(3)
        input("\n2/2  Aperte Enter e FALE uma frase longa, no tom normal (mede 5s)...")
        voice_vals = measure(5)
    finally:
        capture.stop()

    r = evaluate_levels(noise_vals, voice_vals)
    print(f"\nRuído: {_level_bar(r['noise'])}")
    print(f"Voz:   {_level_bar(r['voice'])}")
    if r["verdict"] in ("muted", "weak"):
        print("\n" + CALIBRATION_VERDICTS[r["verdict"]][2])
        return 1
    save_mic_calibration(config, mic, r)
    print(f"\nLimiar salvo para {friendly_mic_name(mic)}: {r['threshold']:.5f}  (0 no painel = automático)")
    if r["verdict"] == "low":
        print(CALIBRATION_VERDICTS["low"][2])
    return 0


def show_status():
    config = load_config()
    device, compute = choose_device(config)
    free_vram = get_free_vram_mb()
    cublas = _find_cublas_path()
    daemon_running = is_daemon_running()
    print(f"JRWhisper {__version__}")
    print(f"  Modelo:        {config['model']}")
    print(f"  Engine:        {device} ({compute})")
    print(f"  VRAM livre:    {free_vram} MB")
    print(f"  cuBLAS:        {cublas or 'não encontrado'}")
    print(f"  Microfone:     {config.get('mic_device', '@DEFAULT_SOURCE@')}")
    print(f"  Idioma:        {config['language']}")
    mic, fell_back = resolve_mic(config)
    state, cal = calibration_state(config, mic)
    if config.get("silence_threshold"):
        cal_txt = f"manual {config['silence_threshold']:.4f}"
    elif state == "ok":
        cal_txt = f"calibrado {cal['threshold']:.4f} ({cal['date']})"
    elif state == "stale":
        cal_txt = f"ganho mudou desde a calibração (era {cal['hw_gain']}): automático até recalibrar"
    else:
        cal_txt = "automático (não calibrado)"
    print(f"  Mic em uso:    {friendly_mic_name(mic)}{' (reserva: configurado ausente)' if fell_back else ''}")
    print(f"  Threshold:     {cal_txt}")
    print(f"  Silence dur:   {config.get('silence_duration', 1.7)}s")
    print(f"  Formatação:    {'Ativa' if config.get('enable_formatting', True) else 'Inativa'}")
    print(f"  Ducking Áudio: {'Ativo (Vol: ' + str(int(config.get('ducking_volume', 0.20)*100)) + '%)' if config.get('audio_ducking', True) else 'Inativo'}")
    print(f"  Overlay:       GTK3")
    print(f"  Status:        {'GRAVANDO' if is_running() else 'Parado'}")
    print(f"  Daemon Mode:   {'ATIVO (Em execução)' if daemon_running else 'Inativo (Fallback local)'}")


def main():
    config = load_config()
    flags = [a for a in sys.argv[1:] if a.startswith('-')]

    if not flags:
        run_overlay_mode(config)
        return

    arg = flags[0]
    if arg == "--mode":
        # dictate --mode email → ditado com esse modo de IA (para associar a um atalho próprio)
        rest = [a for a in sys.argv[1:] if not a.startswith("-")]
        run_overlay_mode(config, mode=rest[0] if rest else None)
    elif arg == "--system":
        from .audio import SYSTEM_AUDIO
        run_overlay_mode(dict(config, mic_device=SYSTEM_AUDIO))
    elif arg == "--history":
        from .ui.history_search import HistorySearch
        HistorySearch(config).show_all()
        Gtk.main()
    elif arg == "--daemon":
        run_daemon(config)
    elif arg == "--status":
        show_status()
    elif arg == "--calibrate-gui":
        win = CalibrationWindow(config, standalone=True)
        win.show_all()
        Gtk.main()
    elif arg == "--calibrate":
        try:
            sys.exit(run_calibration(config))
        except KeyboardInterrupt:
            print("\nCalibração cancelada. Nada salvo.")
            sys.exit(130)
    elif arg == "--config":
        print(json.dumps(config, indent=2))
    elif arg in ("--settings", "-s", "--config-panel"):
        rest = [a for a in sys.argv[1:] if not a.startswith("-")]
        win = SettingsWindow(config, rest[0] if rest else "general")
        win.show_all()
        Gtk.main()
    elif arg in ("-h", "--help"):
        print(__doc__)
    else:  # erro de digitação não pode começar a gravar
        print(f"Opção desconhecida: {arg}\n{__doc__}", file=sys.stderr)
        sys.exit(2)
