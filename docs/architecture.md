# Architecture — JRWhisperLinux

## System Overview

```
┌─────────────────────────────────────────────────────┐
│               Global Keyboard Shortcut              │
│         (X11 Keybinding / GNOME Shortcut)           │
│                   Super+Shift+V                      │
└──────────────────────┬──────────────────────────────┘
                       │ spawns client
                       ▼
┌─────────────────────────────────────────────────────┐
│  dictate (venv python3 + GTK3 via system-site)      │
│                                                     │
│  ┌─────────────┐  ┌──────────────┐                  │
│  │ GTK Overlay  │  │ AudioCapture │                  │
│  │ (main thread)│  │ (thread)     │                  │
│  │              │  │              │                  │
│  │ • Waveform   │  │ • parec proc │                  │
│  │ • 3-Line     │  │ • RMS inst.  │                  │
│  │   Sliding    │  │ • Pre-buffer │                  │
│  │   Window     │  │ • has_data   │                  │
│  │ └──────┬───────┘  └──────┬───────┘                  │
│           │          ┌──────┴──────────────┐         │
│           └──────────┤    DictateThread    ├───────┐ │
│                      │ (processing thread) │       │ │
│                      │                     │       │ │
│                      │ • Calibration       │       │ │
│                      │ • Silence detection │       │ │
│                      │ • Denoising (FFmpeg)│       │ │
│                      │ • Keyboard Paste    │       │ │
│                      └─────────────────────┘       │ │
└────────────────────────────────────────────────────┼─┘
                                           Unix      │
                                           Socket    ▼
                                        ┌──────────────┐
                                        │  DAEMON      │
                                        │  SERVER      │
                                        │  (config)    │
                                        │  CUDA        │
                                        └──────────────┘
```

## Data Flow

```
Microphone ──parec──▶ AudioCapture Thread ──buffer──▶ DictateThread
                          │                               │
                          │ RMS (instant, 32ms chunks)    │ calibration
                          │ Pre-buffer (300ms ring)       │ (wait for data + measure 1s)
                          ▼                               │
                   Siri Waveform (GTK)                    │ silence detection & VAD
                                                          │ (confirm start + hysteresis)
                                                          ▼
                                                    Audio Buffer
                                                          │
                                                          ├──► [A cada 800ms (Se fala ativa)]:
                                                          │    Salva WAV parcial (sem RNNoise: velocidade)
                                                          │    ──► Transcritor Cliente ──► Socket Unix ──► Daemon (CUDA)
                                                          │    ──► Retorna texto parcial ──► UI (3-Line Pango Sliding Window)
                                                          │
                                                          ▼ [Fim da fala (silence_duration)]
                                                    WAV Final
                                                          │
                                                          ├──► FFmpeg Denoise (nice -n 19 + RNNoise)
                                                          ▼
                                                    Denoised WAV
                                                          │
                                                          ├──► Transcritor Cliente ──► Socket Unix ──► Daemon
                                                          ▼
                                                    Final Text
                                                          │
                                                          ├──► pipeline.process: perfil → modo IA → formatação → IA → atalhos → regras
                                                          ▼
                                                    Text Output
                                                          │
                                                          ├──► X11: xclip + xdotool key ctrl+v
                                                          └──► Wayland: wl-copy + wtype -M ctrl -k v
```

## Component Details

### 1. WhisperFlowOverlay (`src/jrwhisper/ui/overlay.py`)
* **Layout**: Janela GTK3 `Gtk.WindowType.POPUP` sem decoração e sem foco. Tudo é desenhado em Cairo/PangoCairo no handler `draw` (sem widgets: o tema do sistema não interfere). Click-through: `input_shape_combine_region` só na engrenagem e nos chips de escolha (`_chip_rects`).
* **Visual**: `ui/visuals.py` (Orbe de plasma, Ondas, Barras + FFT), alimentado por `update_level`/`update_spectrum` via `GLib.idle_add`. A suavização ali é só visual; a detecção de fala usa o RMS instantâneo.
* **Texto**: as últimas `overlay_lines` linhas (padrão 3) da transcrição parcial e final; revisão com IA no próprio overlay; editar uma palavra abre um POPUP à parte com `Gtk.Entry` (`_edit_word`). Legendas ao vivo: `ui/captionview.py`.
* **Monitor Inteligente**: Usa a API Gdk Seat (`seat.get_pointer().get_position()`) para mover a janela do overlay para a tela em que o mouse está posicionado no momento de ativação do atalho.

### 2. AudioCapture (`src/jrwhisper/audio.py`)
* Spawns `parec --device <name> --format=s16le --rate=16000 --channels=1 --latency-msec=30`
* O buffer de latência de 30ms do parec elimina o delay de fragmentação de buffer do PipeWire (fazendo o parec iniciar em 70ms contra os 2.013s do default).
* A thread leitora retira blocos de áudio a cada 32ms (1024 bytes) e calcula a raiz da média quadrada (RMS) instantânea (sem suavização).
* Mantém um pré-buffer circular de 300ms de áudio antes de confirmar que a fala começou para evitar o corte da primeira sílaba do usuário.

### 3. Isolamento de Voz Integrado (RNNoise)
* Para assegurar precisão em salas ruidosas ou com música tocando, o arquivo `.wav` gravado passa por um pré-processamento via FFmpeg antes de ser transcrevido:
  ```bash
  nice -n 19 ffmpeg -y -i input.wav -af arnndn=m=bd.rnnn,aresample=16000 output.wav
  ```
* O filtro `arnndn` roda o modelo neural `bd.rnnn` (Beguiling Drafter) em C, convertendo internamente para 48kHz e limpando ruídos mecânicos e música de fundo. O áudio resultante é resamulado para 16kHz e repassado limpo para o Whisper.
* O processo é priorizado com `nice -n 19` para evitar picos de uso de CPU que causem travamentos no Cinnamon.

### 4. Transcriber e Daemon Mode (`src/jrwhisper/transcribe.py`)
* **Modo Cliente (Socket Unix)**: O transcritor tenta enviar o arquivo WAV local para o socket Unix `$XDG_RUNTIME_DIR/dictate_daemon.sock` (diretório 0700 por usuário).
* **Modo Daemon**: Processo persistente rodando como serviço de usuário do systemd (`dictate --daemon`). Ele mantém o modelo Whisper carregado na GPU CUDA (`int8_float16`) reduzindo a latência de load do modelo de 2.2s para 0s.
* **Cada requisição leva o config**: `model`, `language`, prompt etc. vão no JSON (`_transcribe_kwargs`); modelo trocado nos Ajustes faz o daemon recarregar sozinho; `language: "auto"` vira `None` e o idioma é escolhido só entre `auto_languages`.
* **Sem fallback de temperatura & Zero Context**: `temperature=0.0` (com `beam_size=5`) e `condition_on_previous_text=False`. Isso elimina loops de retentativa de temperatura no silêncio (evitando alucinações repetitivas do Whisper) e aumenta a velocidade do modelo na GPU RTX 4060 para ~30ms para trechos curtos.

---

## Silence Detection & VAD Hysteresis Algorithm (`DictateThread._listen`)

A histerese vale só para **começar**: 150 ms seguidos acima do limiar confirmam a fala (estalo de tecla não dispara). Depois disso, **qualquer** tick de voz zera a pausa. Exigir 150 ms seguidos também para zerar a pausa deixava silêncio acumular durante a fala (com a voz perto do limiar, 53–68% dos ticks ficam abaixo, medido no Yeti) e uma pausa curta encerrava o ditado; corrigido em `c6a2ccb`.

```
speech_confirm_ticks = 0
silence_counter = 0
SPEECH_START_TICKS = 3             # 150ms contínuos acima do threshold para começar
silence_needed = silence_duration / 0.05  # padrão 2.5 s = 50 ticks

em cada tick (50ms):
    rms = capture.get_rms()
    
    if rms > threshold:
        speech_confirm_ticks += 1
        if not started and speech_confirm_ticks >= SPEECH_START_TICKS:
            started = True
            include_pre_buffer()
            
        if started:
            silence_counter = 0        # qualquer voz zera a pausa (NÃO exigir 3 ticks aqui)
    else:
        speech_confirm_ticks = 0
        if started:
            silence_counter += 1
            
    if silence_counter >= silence_needed and not system_audio:
        stop_recording()   # som do computador só para no 2º toque ou em max_duration
```

---

## Configuration (`config.json`)

* `model`: Modelo Whisper local (default: `"medium"`).
* `mic_device`: Nome da fonte PipeWire (default: `"@DEFAULT_SOURCE@"`).
* `silence_duration`: Tempo para corte automático (default: `2.5`s).
* Lista completa e comentada: `DEFAULT_CONFIG` em `src/jrwhisper/config.py`. Chaves novas devem ser planas (`load_config` faz merge raso).
* `noise_suppression`: Ativa/desativa o filtro neural integrado do FFmpeg (default: `true`).
