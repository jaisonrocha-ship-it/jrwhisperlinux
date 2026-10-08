# Arquitetura — JRWhisperLinux

Como as peças se encaixam. Para uso, veja o [README](../README.md); para cada chave do config, [configuration.md](configuration.md); para regras e armadilhas do projeto, o `AGENTS.md`.

---

## Processos

```
 Atalho global (dconf)            Menu / dock                 Login (systemd --user)        Boot (dockerd)
        │                              │                              │                            │
        ▼                              ▼                              ▼                            ▼
 ~/.local/bin/dictate  ── lançador: lê ~/.config/dictate/repo ──┐   dictate-daemon.service     jrwhisper-ollama
                         (repositório movido → procura em ~)    │   (dictate --daemon)         (Docker, GPU)
                                                                ▼          │                         │
                          <repo>/src/dictate  → reexecuta no venv          │                         │
                                   │            (os.execv)                 │                         │
                                   ▼                                       ▼                         ▼
                          jrwhisper.cli.main ── socket Unix ──▶  Whisper na GPU         127.0.0.1:11435
                          (ditado, legendas,   $XDG_RUNTIME_DIR/  (modelo sempre         Ollama do ditado
                           Ajustes, busca…)    dictate_daemon.sock carregado)            (qwen2.5, Hunyuan MT)
                                   │                                                          ▲
                                   └──────────────── HTTP (reescrita, tradução) ─────────────┘
                                                     e HTTPS para NVIDIA / DeepSeek
```

- **Uma sessão por vez.** Cada toque no atalho abre um processo `dictate`. Se já há um rodando (trava em `$XDG_RUNTIME_DIR/dictate.pid.lock`), o novo só manda `SIGUSR1` e sai: é o "2º toque". `SIGTERM` continua sendo "sair".
- **O serviço do Whisper** mantém o modelo na GPU desde o login (`Restart=always`). O cliente manda o caminho do WAV e os parâmetros do config em cada requisição; se o modelo pedido mudou, o serviço recarrega sozinho. Sem serviço, o cliente carrega o modelo localmente (mais lento na 1ª vez).
- **O Ollama do ditado** é um contêiner próprio (`scripts/ollama-container.sh`), independente do Ollama do Moorcheh/Hermes na 11434. Compartilha o volume de modelos (`compose_ollama_data`) para não baixar de novo.
- **Tudo que é privado fica em `$XDG_RUNTIME_DIR`** (memória, `0700`, por usuário): socket, PID, WAVs temporários e o log. Nunca em `/tmp`.

---

## Módulos

### Núcleo (`src/jrwhisper/`)

| Módulo | Responsabilidade |
|---|---|
| `cli` | Argumentos (`--system`, `--captions`, `-s`, `--history`…), trava de sessão, `SIGUSR1` |
| `config` | `DEFAULT_CONFIG`, caminhos, `load_config`/`save_config` (mescla rasa, escrita atômica), `OLLAMA_URL` |
| `audio` | Captura (`parec --latency-msec=30`), RMS instantâneo, pré-buffer de 300 ms, calibração por mic, Yeti GX, `mic_options` (nomes legíveis), pausa de mídia e volume |
| `transcribe` | Cliente e serviço do Whisper, escolha de GPU/CPU (preload do cuBLAS), RNNoise via FFmpeg, 2ª passada sem filtros |
| `dictation` | A sessão de ditado: calibrar, ouvir, transcrever, revisar, colar, continuar, mãos livres, push-to-talk |
| `pipeline` | Do texto transcrito ao texto colado: perfil → modo de IA → formatação → IA → atalhos de texto → regras do perfil |
| `textproc` | Comandos de voz, hesitações, dicionário, maiúsculas, alucinações conhecidas |
| `ai` | Fila de provedores, Ollama/NVIDIA/DeepSeek, keep-alive e pré-carga do modelo local, limpeza da resposta |
| `context` | Campo em foco via AT-SPI e a seleção recente (PRIMARY) |
| `learning` | Correção da revisão → regra do dicionário e vocabulário do Whisper |
| `style` | Estudo dos e-mails enviados → nota "Meu estilo de escrita" |
| `lexicon` | Léxico de logística: vocabulário do Whisper, pistas e traduções para a IA |
| `captions` | Legendas ao vivo: corte em frases, tradução em fila, cópia no fim |
| `history`, `vault` | Histórico local (+ áudio Opus) e a cópia diária no Obsidian |
| `paste` | Colar (clipboard + atalho) ou digitar; X11 e Wayland |
| `profiles`, `ptt`, `shortcuts`, `secrets` | Perfis por app, push-to-talk (X11), atalhos do desktop (dconf), chaves no keyring |

### Interface (`src/jrwhisper/ui/`)

| Módulo | Responsabilidade |
|---|---|
| `theme` | Tokens e CSS estilo macOS, componentes (linhas, `PopupChoice`, `Swatch`), ícones Lucide (`draw_icon` nítido em HiDPI), `num`/`when_text` (vírgula decimal, datas relativas) |
| `visuals` | Orbe, Ondas e Barras em Cairo; espectro (FFT); o vidro dos cartões (`CARD`, `card`) |
| `overlay` | O HUD do ditado: visual, status, texto, pontinhos, faixa de luz, revisão com chips |
| `captionview` | Legendas com frase em foco estável; usado pelo overlay e pela prévia dos Ajustes |
| `settings` | Ajustes em 10 abas, aplicados na hora |
| `calibration` | Janela de calibração com medidor ao vivo |
| `history_search` | Busca rápida estilo Spotlight |

---

## Fluxo do ditado

```
toque ─▶ overlay aparece (fade no relógio de quadros)
          │  em paralelo: contexto do campo (AT-SPI), checagem da GPU + pré-carga da IA local,
          │               pausa de mídia, volume baixo
          ▼
       calibração (limiar do mic, ou mede 1 s de ruído)
          ▼
       ouvindo: a cada 50 ms ─ RMS → visual
                             ─ 150 ms acima do limiar: começa (inclui o pré-buffer)
                             ─ qualquer voz zera a pausa; silence_duration de pausa encerra
                             ─ a cada 0,8 s: WAV parcial (sem RNNoise) → serviço → texto parcial
          ▼
       fim da fala (pausa, 2º toque, duração máxima ou tecla solta no push-to-talk)
          ▼
       WAV final ─▶ RNNoise (nice 19) ─▶ serviço Whisper ─▶ texto
          │            (nada? 2ª passada sem RNNoise/VAD, idioma automático, 4+ palavras)
          ▼
       pipeline: perfil → modo → formatação → IA (fila) → atalhos de texto → regras do perfil
          ▼
       sem IA: cola                    com IA: revisão na tela
          ▼                                 ├─ clicar palavra: editar (vira "Lembrar")
       histórico, Obsidian,                 ├─ 0/1/2–9: refaz em outro modo
       áudio Opus                           ├─ Espaço: continua ouvindo e acrescenta no fim
                                            └─ Enter / Shift+Enter / Ctrl+C / Esc
```

### Detecção de fala (`DictateThread._listen`)

A histerese vale só para **começar**: 150 ms seguidos acima do limiar confirmam a fala, então um estalo de tecla não dispara. Depois disso, **qualquer** tick de voz zera a pausa. Exigir 150 ms seguidos também para zerar a pausa deixava silêncio acumular durante a fala (com a voz perto do limiar, 53–68% dos ticks ficam abaixo, medido no Yeti) e uma pausa curta encerrava o ditado; corrigido em `c6a2ccb`.

```
speech_confirm_ticks = 0
silence_counter = 0
SPEECH_START_TICKS = 3                     # 150 ms seguidos acima do limiar para começar
silence_needed = silence_duration / 0.05   # padrão 2,5 s = 50 ticks

a cada tick (50 ms):
    rms = capture.get_rms()                # instantâneo, sem suavização
    if rms > threshold:
        speech_confirm_ticks += 1
        if not started and speech_confirm_ticks >= SPEECH_START_TICKS:
            started = True
            include_pre_buffer()
        if started:
            silence_counter = 0            # qualquer voz zera a pausa (NÃO exigir 3 ticks aqui)
    else:
        speech_confirm_ticks = 0
        if started:
            silence_counter += 1
    if silence_counter >= silence_needed and not system_audio:
        stop_recording()                   # som do computador só para no 2º toque ou em max_duration
```

### Serviço do Whisper (protocolo)

Requisição JSON pelo socket: `{"action": "transcribe", "wav_path", "model", "language", "initial_prompt", "no_speech_threshold", "log_prob_threshold", "compression_ratio_threshold", "vad_filter", "auto_languages", "task"}`. Resposta: `{"text", "language", "language_probability", "segments": [[início, fim, texto]]}` ou `{"error"}`.

Parâmetros fixos: `beam_size=5`, `temperature=0.0` (sem fallback de temperatura), `condition_on_previous_text=False`. `language: "auto"` vira `None` e o idioma é escolhido só entre `auto_languages`.

---

## Inteligência

```
rewrite(texto, modo) ─▶ para cada provedor em ai_chain (padrão: ollama → nvidia → deepseek):
                          ├─ ollama: só se a checagem da GPU disser que cabe (VRAM livre + margem, < 85 °C)
                          ├─ 3 s por tentativa; a última leva o resto de ai_timeout
                          └─ falhou ou vazio: próximo
                        todas falharam: cola o texto original
```

- **Modelo local quente:** toda chamada ao Ollama manda `keep_alive: 30m`. No início do ditado, `prefetch_local` checa a GPU numa thread e, se o modelo cabe mas está descarregado, `warm_local` o carrega gerando 1 token (que também aquece os kernels). Medido: 1,8 s de pré-carga enquanto se fala, depois 322 ms na 1ª reescrita e ~205 ms nas seguintes (a frio eram 2,2 s, acima dos 3 s que a fila dá).
- **Raciocínio desligado** nos modelos híbridos (`_no_reasoning`), e qualquer `<think>` que escape é removido, inclusive se cortado pelo limite de tokens. Aspas só saem se embrulham a resposta inteira.
- **O texto vai entre marcações** (`<ditado>`, `<contexto>`) com a regra de nunca responder, só reescrever.
- **Contexto, estilo e léxico** entram no prompt de sistema; o contexto serve só para nomes e coerência.

---

## Legendas ao vivo

```
@DEFAULT_MONITOR@ (saída de áudio) ─▶ captura ─▶ a cada 0,5 s: retranscreve o trecho em andamento (prévia)
                                              ─▶ frase fecha nos limites de segmento do Whisper ou numa pausa
                                              ─▶ fila de tradução (várias frases numa chamada; 429 espera e tenta de novo)
                                              ─▶ CaptionView: blocos estáveis + prévia em itálico
fim (2º toque) ─▶ legenda inteira copiada; histórico e Obsidian em parágrafos de 5 frases
```

O idioma é detectado uma vez, com 70%+ de confiança, antes da 1ª legenda. Em inglês, o próprio Whisper traduz (`task: "translate"`).

---

## Desenho do overlay

- **Uma janela POPUP transparente**, desenhada inteira em Cairo/PangoCairo no handler `draw`, sem widgets GTK: o tema do sistema não interfere. A única exceção é a edição de uma palavra na revisão, que abre um POPUP separado com `Gtk.Entry`.
- **Click-through:** `input_shape_combine_region` só na engrenagem e nos chips da revisão.
- **Relógio de quadros:** `_on_tick` (frame clock do GTK, sincronizado com o monitor, inclusive 165 Hz) avança o visual, a altura da caixa, a rolagem das legendas e o fade, com animação exponencial dependente de `dt`.
- **Vidro único:** caixa de texto, legendas, pílula das Ondas/Barras e status usam `visuals.card` (sombra curta, `CARD_ALPHA` 0,97, borda fina). A translucidez fica só no orbe.
- **Custo por quadro** (`tests/render_overlay.py --bench`, quadro inteiro com texto): orbe ~3 ms, ondas ~2,6 ms, barras ~1 ms; orçamento a 165 Hz: 6 ms.
- **Ícones:** `theme.draw_icon` rasteriza o vetor Lucide no tamanho exato em pixels do dispositivo (2× em HiDPI), guarda a máscara e cola alinhada ao pixel.

### Visuais

| Estilo | Desenho | Reação à voz |
|---|---|---|
| Orbe | Membrana ondulada de vidro fumê translúcido, bolhas de plasma somadas (`OPERATOR_ADD`), borda de luz (fresnel), reflexo | Curva perceptual (`nível^0,7`): cresce até +25%, bolhas até +40%, borda mais forte, membrana ondula mais |
| Ondas | 4 fitas de luz (brilho + fio), gradiente com pontas transparentes | Cada fita segue uma faixa do espectro (graves → agudos) |
| Barras | 16 pares espelhados a partir do centro, num único caminho; marcador de pico com gravidade | Espectro logarítmico de 32 bandas, 90 Hz–7 kHz |

### Legendas: frase em foco estável

A frase fechada mais nova fica `zoom` vezes maior, com o centro numa faixa fixa do cartão; as anteriores ficam em tamanho normal e esmaecem com a idade (0,78 → 0,32); a prévia vem logo abaixo, em itálico. O tamanho de cada frase é um estado animado **no tempo** (~0,2 s na troca de foco), nunca uma função da posição da rolagem: o texto que você está lendo não cresce nem encolhe enquanto anda. Todas as frases quebram na largura do cartão dividida pelo zoom, então a troca de tamanho nunca refaz a quebra de linha.

---

## Ajustes

`SettingsWindow` monta 10 abas com os helpers de `theme` (linhas no estilo inset-grouped). `set(chave, valor)` grava com 350 ms de espera e escrita atômica; as prévias dos Ajustes se refazem na hora e o próximo ditado já usa o valor novo. Títulos longos terminam em "…" para não alargar a janela (que abre em 900×640). Números saem com vírgula decimal e datas no formato do histórico ("Hoje 14:05").

---

## Instalação e inicialização

| Peça | Instalada por | Sobe com |
|---|---|---|
| `~/.local/bin/dictate` | `install.sh` (cópia de `scripts/dictate-launcher.sh`) | — |
| `dictate-daemon.service` | `install.sh` | login (`default.target`) |
| `jrwhisper-ollama` | `scripts/ollama-container.sh` | dockerd (`restart: unless-stopped`) |
| Atalhos | `install.sh` (padrão) e Ajustes | desktop (dconf) |

O lançador guarda o caminho do repositório; se ele sumir (repositório movido ou renomeado), procura em `~` (fora de worktrees, lixeira e caches), se corrige e segue; sem repositório, notifica pedindo o `install.sh`.
