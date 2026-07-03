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
                                        │  (medium)    │
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
                                                          │    Salva WAV parcial ──► FFmpeg (nice RNNoise)
                                                          │    ──► Transcritor Cliente ──► Socket Unix ──► Daemon (CUDA)
                                                          │    ──► Retorna texto parcial ──► UI (3-Line Pango Sliding Window)
                                                          │
                                                          ▼ [Fim da fala (1.7s silêncio)]
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
                                                          ├──► Formatador (remover alucinações repetidas)
                                                          ▼
                                                    Text Output
                                                          │
                                                          ├──► X11: xclip + xdotool key ctrl+v
                                                          └──► Wayland: wl-copy + wtype -M ctrl -k v
```

## Component Details

### 1. WhisperFlowOverlay (`src/dictate`)
* **Layout**: Janela GTK3 `Gtk.WindowType.POPUP` sem decoração, com fundo transparente via Cairo (`on_window_draw`) e cantos arredondados translúcidos via CSS.
* **Componentes**: 
  * `SiriWaveform`: Área de desenho Cairo a 60 FPS com 3 ondas senoidais sobrepostas moduladas pela amplitude real da fala do usuário.
  * `status_label`: Rótulo de status contendo cores CSS mapeadas por estado (Amarelo = Calibrando, Branco = Aguardando, Ciano = Ouvindo, Roxo = Transcrevendo, Verde = Sucesso, Vermelho = Erro).
  * `text_label`: Exibição de texto com `set_use_markup(True)` para suporte a marcação Pango.
* **Janela Deslizante de 3 Linhas**: 
  * O texto de transcrição parcial e final é processado pela função `wrap_text_to_lines` para limitar o conteúdo a no máximo 45 caracteres por linha.
  * Apenas as **3 últimas linhas** são enviadas para a interface. 
  * As linhas anteriores rolam para cima e ganham fading de opacidade através de cores em hexadecimal com canal alfa no Pango:
    * Linha 1 (antiga): `#FFFFFF40` (25% opacidade)
    * Linha 2 (média): `#FFFFFF99` (60% opacidade)
    * Linha 3 (ativa): `#FFFFFFF2` (95% opacidade e itálico se parcial) ou `#FFFFFF` (negrito se final).
  * Linhas ausentes são substituídas por espaços vazios invisíveis (`#FFFFFF00`) para travar a altura física do modal e evitar pulos e deformações no Cinnamon.
* **Monitor Inteligente**: Usa a API Gdk Seat (`seat.get_pointer().get_position()`) para mover a janela do overlay para a tela em que o mouse está posicionado no momento de ativação do atalho.

### 2. AudioCapture (`src/dictate`)
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

### 4. Transcriber e Daemon Mode
* **Modo Cliente (Socket Unix)**: O transcritor tenta enviar o arquivo WAV local para o socket Unix `/tmp/dictate_daemon.sock`.
* **Modo Daemon**: Processo persistente rodando como serviço de usuário do systemd (`dictate --daemon`). Ele mantém o modelo Whisper carregado na GPU CUDA (`int8_float16`) reduzindo a latência de load do modelo de 2.2s para 0s.
* **Greedy Decoding & Zero Context**: As transcrições parciais e finais utilizam `temperature=0.0` (greedy search determinístico) e `condition_on_previous_text=False`. Isso elimina loops de retentativa de temperatura no silêncio (evitando alucinações repetitivas do Whisper) e aumenta a velocidade do modelo na GPU RTX 4060 para ~30ms para trechos curtos.

---

## Silence Detection & VAD Hysteresis Algorithm

O algoritmo foi otimizado para evitar que ruídos curtos isolados (estalos de teclado mecânico ou respirações curtas) travem ou reiniciem a gravação de silêncio:

```
speech_confirm_ticks = 0
silence_counter = 0
SPEECH_START_TICKS = 3             # 150ms contínuos acima do threshold para começar
silence_samples_needed = 1.7 / 0.05 = 34  # 1.7s de silêncio contínuo para parar

em cada tick (50ms):
    rms = capture.get_rms()
    
    if rms > threshold:
        speech_confirm_ticks += 1
        if not started and speech_confirm_ticks >= SPEECH_START_TICKS:
            started = True
            include_pre_buffer()
            
        # Histerese: Apenas reinicia o contador de silêncio se o som for
        # sustentado por pelo menos 150ms consecutivos (3 ticks).
        # Ruídos rápidos (ex: clique de tecla) não resetam mais o silêncio.
        if started and speech_confirm_ticks >= SPEECH_START_TICKS:
            silence_counter = 0
    else:
        speech_confirm_ticks = 0
        if started:
            silence_counter += 1
            
    if silence_counter >= silence_samples_needed:
        stop_recording()
```

---

## Configuration (`config.json`)

* `model`: Modelo Whisper local (default: `"medium"`).
* `mic_device`: Nome da fonte PipeWire (default: `"easyeffects_source"` ou `"@DEFAULT_SOURCE@"`).
* `silence_duration`: Tempo para corte automático (default: `1.7`s).
* `noise_suppression`: Ativa/desativa o filtro neural integrado do FFmpeg (default: `true`).
