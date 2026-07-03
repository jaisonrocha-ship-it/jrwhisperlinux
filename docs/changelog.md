# Changelog — JRWhisperLinux

## v3.2 — 2026-07-03 (Estável / Atual)

### Funcionalidades & Otimizações
* **Limpeza e Refatoração de Código:** Remoção de comentários redundantes e estruturação limpa do código principal para conformidade open-source.
* **Documentação Profissional GitHub:** Criação de documentação completa contendo guias de dependências, setup híbrido (Wayland/X11), e tabelas de configuração do sistema.

---

## v3.1 — 2026-07-03

### Funcionalidades & Otimizações
* **Interface Deslizante de 3 Linhas (Pango Markup):** O modal agora exibe exatamente as 3 últimas linhas ativas do ditado, travando a altura física da janela pop-up e eliminando qualquer tremor ou redimensionamento vertical. Linhas anteriores deslizam com opacidades calculadas (`25%` -> `60%` -> `95%`).
* **Isolamento de Voz Neural Integrado (RNNoise):** Integração transparente do filtro `arnndn` do FFmpeg utilizando o modelo `bd.rnnn` (Beguiling Drafter). Ruído de fundo, teclado e música são cancelados no áudio antes de ir ao Whisper.
* **Isolamento nas Parciais e Final:** O filtro de voz é aplicado tanto nas amostras parciais (streaming de 800ms) quanto no arquivo final, garantindo que o Whisper não perca trechos de fala longa mesmo em locais barulhentos.
* **Histerese do Silêncio Otimizada (VAD):** O tempo padrão para detecção de silêncio foi reduzido de `2.5s` para `1.7s`. O algoritmo de VAD foi aprimorado para exigir **150ms consecutivos (3 ticks)** de som para resetar o silêncio, ignorando de vez cliques rápidos de teclado e estalos de boca.
* **Prioridade de Processo Nice:** Subprocessos do FFmpeg rodam sob `nice -n 19`, assegurando que o processador dê prioridade à interface do Cinnamon e às aplicações do usuário.
* **Suporte Multi-Monitor Inteligente:** Rastreia as coordenadas do mouse via API Gdk Seat para posicionar o overlay no monitor ativo.

### Bugs Resolvidos
1. **Alucinações no Silêncio:** Resolvido forçando `temperature=0.0` e `condition_on_previous_text=False` nas requisições do transcritor. O Whisper não carrega mais erros entre segmentos e processa o áudio de forma determinística e imediata.
2. **Overlay fora da tela secundária:** O overlay agora abre na tela correta em setups de múltiplos monitores.

---

## v3.0 — 2026-07-03

### Funcionalidades & Otimizações
* **Fundo de Transparência Real (Cinnamon):** Adicionada a flag `set_app_paintable(True)` e conexão do sinal Cairo `draw` (`on_window_draw`) para limpar o canvas da janela pop-up. Cantos arredondados antialiased agora funcionam sem bordas ou cantos pretos no Cinnamon X11.
* **Ajuste de Posição do Modal:** Overlay movido verticalmente para `geo.height - 310` para flutuar acima de docks de sistema e painéis inferiores.
* **Cores por Estado de Status:** Adicionadas 6 classes CSS para colorir dinamicamente a etiqueta de status (Calibrando = Amarelo, Aguardando = Branco, Ouvindo = Ciano, Transcrevendo = Roxo, Sucesso = Verde, Erro = Vermelho).
* **Contraste Aprimorado:** Status label ajustado para opacidade `0.65` e tamanho `10px`, melhorando o contraste e a acessibilidade em conformidade com as diretrizes de design.

### Bugs Resolvidos
1. **Erro Fatal de CSS (Crash no Startup):** Removida a propriedade `text-transform: uppercase` do CssProvider (não suportada pela engine de CSS do GTK3). O uppercase agora é aplicado diretamente via Python na chamada do rótulo.

---

## v2.5 — 2026-07-02

### Funcionalidades & Otimizações
* **Daemon Mode & Client (Socket Unix):** O WhisperModel fica carregado de forma persistente em background no login do usuário. Comunicação via `/tmp/dictate_daemon.sock`. Latência de carregamento do modelo reduzida de 2.0s para **0s** (transcrição final em 0.8s).
* **Design System brutaldev:** Interface ajustada para a paleta de widgets de desktop do usuário: background `rgba(0, 0, 0, 0.42)`, cantos de `12px` e fonte `'Inter', sans-serif`.
* **Onda Siri Dinâmica (Cairo):** Widget `SiriWaveform` a 60 FPS com 3 ondas senoidais translúcidas sobrepostas e gradiente de cores da Siri, moduladas pela voz real.
* **Texto Multi-linha:** Transcrição redefinida para fonte de `13px` com redimensionamento vertical automático e suporte a quebras de linhas de parágrafos longos.
* **Latência do parec Resolvida:** Adicionado `--latency-msec=30` nos argumentos da captura PulseAudio, fazendo com que o `parec` inicie em 70ms (antes demorava 2.013s) e transmita áudio de forma linear sem buffering do PipeWire.
* **Segurança no Threshold:** Limitado o teto do threshold dinâmico em `0.015` para impedir que transient ou ruídos de calibração tornem o gatilho da fala insensível.

---

## v2.0 — 2026-07-02
* **GPU CUDA Habilitada:** Pré-carregamento automático de `libcublas.so.12` e `libcublasLt.so.12` a partir de caminhos locais conhecidos (como DaVinci Resolve `/opt/resolve/libs`). Reduziu o tempo de transcrição em até 5.6x.
* **Calibração de Threshold Robusta:** Agora o script espera que o processo do `parec` envie dados reais antes de iniciar a medição de ruído.
* **Detecção de Silêncio Aprimorada:** Histerese baseada em RMS instantâneo por ticks, com confirmação de fala (150ms) e tolerancia a gaps (2.5s).
* **Pré-buffer de Áudio (300ms):** Um ring buffer de 300ms agora armazena os milissegundos anteriores à detecção da fala.
* **Remoção de Overhead Incremental:** Transcrição ocorre apenas no final da fala para evitar stuttering.

---

## v1.0 — 2026-07-02
* **Overlay GTK3 estilo WhisperFlow:** borderless, popup centro-inferior.
* **faster-whisper medium CPU:** transcrição em português local.
* **Captura via parec (PulseAudio CLI).**
* **Auto-paste via xdotool com windowfocus.**
