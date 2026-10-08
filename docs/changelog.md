# Changelog — JRWhisperLinux

## Em desenvolvimento

### Novidades
* **Aprende com as suas correções:** a palavra corrigida na revisão ganha um selo "Lembrar" (✓ Paulo → Pablo) e um sublinhado; ao colar ou copiar, vira regra do Dicionário, e nome próprio/sigla entra também no vocabulário do Whisper. Clique no selo para não lembrar. Palavra comum ("mais" → "mas") e sigla trocada por sigla ("API" → "APP", caso real do uso) só viram regra na 2ª correção igual, em outro ditado; troca de palavra inteira nunca vira regra. Ajustes → Texto → "Aprender com as correções".
* **Histórico mais completo:** cada ditado guarda também o texto da IA antes das suas correções, as correções feitas e a janela; com "Guardar o áudio" (Ajustes → Histórico, ligado), uma cópia em Opus (~16 MB por hora de fala, comprimida depois de colar) que some junto com a entrada. Base para estilo pessoal, cadastro de voz e treino.
* **Correção no meio da fala:** com a IA, "chego às 2, não, na verdade às 3" sai "Chego às 3." (também "quer dizer", "aliás", "corrigindo"); um "não" de verdade fica. Medido com qwen2.5 local e DeepSeek: 5/5 casos certos (antes 1–2/5), sem custo de tempo perceptível.
* **Colar e enviar só por tecla ou clique** (nunca por voz): na revisão, Enter cola e Shift+Enter cola e envia. A tecla de envio é por perfil (Ajustes → Apps → "Enviar com"): Enter por padrão, Ctrl+Enter no perfil E-mail.
* **Contexto do campo em foco** (Ajustes → Inteligência → Contexto): app, janela, rótulo do campo (AT-SPI, ~14 ms em paralelo à fala) e o **texto selecionado, a maior pista do assunto**. A IA usa só para nomes e coerência, nunca troca o modo nem o tom; nomes próprios e siglas também entram no vocabulário do Whisper naquele ditado. A seleção PRIMARY só vale se feita há menos de 2 min (TIMESTAMP do X): seleção esquecida não vira contexto. Seleção dentro do próprio campo não é apagada: o texto entra depois dela. Medido: "olá gulsa" → "Olá Gülsah" com o e-mail selecionado (sem contexto saía "Olá, gulp"), +20–120 ms. Na revisão, o chip "Contexto" mostra o que foi usado e desliga com um clique.
* **Chip "0 Bruto"** na revisão: a saída pura do Whisper, sem formatação, dicionário nem IA (tecla 0).
* **Fila de IAs grátis primeiro:** qwen2.5 local (0,26 s, 5/5) → NVIDIA Nemotron (0,5 s, 4/5) → DeepSeek (0,9 s, 5/5, pago); 3 s por tentativa, só cola o original se todas falharem. A local só roda se já estiver na GPU ou se houver VRAM livre e a placa estiver abaixo de 85 °C (checado em paralelo à fala); na CPU o qwen2.5 leva ~2,1 s, então sem GPU a fila vai direto à nuvem. A revisão mostra "via NVIDIA/DeepSeek" quando o texto saiu do computador. Modelo local padrão: qwen2.5 (o llama3.2 não estava instalado e toda reescrita falhava).
* **Cópia dos ditados no Obsidian** (Ajustes → Histórico → Obsidian): uma nota por dia (`AAAA-MM-DD.md`) na pasta escolhida do vault, um bloco por ditado com hora · app · modo, a janela/campo em itálico, o texto com os parágrafos e o bruto num callout recolhido (só quando difere). Legendas ao vivo entram em parágrafos de 5 frases. Só acrescenta no fim, independe do histórico e da retenção; o texto selecionado (contexto) nunca vai para a nota.
* **Pausa curta não encerra mais o ditado** (bug medido nos áudios reais): com a voz perto do limiar (53–68% dos trechos de 50 ms abaixo dele, no Yeti), o silêncio acumulava durante a própria fala, porque só 150 ms seguidos de voz zeravam a contagem; uma pausa de 0,8 s encerrava o ditado configurado para 1,7 s. Agora qualquer trecho de voz zera a pausa (os 150 ms valem só para começar a gravar), e o padrão passou a 2,5 s.
* **"Continuar" na revisão** (chip ou Espaço): volta a ouvir e o que você falar entra no fim do texto, com as suas correções; o texto todo é refeito no modo atual (e-mail continua coeso). Pode repetir; o atalho sem falar nada volta à revisão. O histórico guarda o áudio do ditado inteiro.
* **Tempos por etapa no log** (transcrição e texto/IA, em ms) para medir o impacto de cada novidade na agilidade.

## v4.0 — 2026-10-07 (Estável / Atual)

### Novidades (desde a v3.2)
* **Redesign estilo macOS:** Ajustes com 10 abas e aplicação instantânea, overlay com Orbe de plasma, Ondas ou Barras, calibração guiada por microfone, ícone do app na dock.
* **Reescrita com IA** (NVIDIA NIM ou Ollama), **perfis por aplicativo**, **atalhos de texto**, **histórico** com busca estilo Spotlight, **push-to-talk** e **mãos livres**.
* **Revisão com IA:** o texto espera na tela; corrigir palavra com um clique, trocar de modo, colar, copiar ou descartar. Teclado: Enter cola, Esc descarta, Ctrl+C copia, 1–9 trocam o modo. Texto longo rola com a roda do mouse.
* **2º toque no atalho encerra e transcreve** (antes cancelava e descartava o áudio). Na revisão, cola; antes de falar, cancela.
* **Legendas ao vivo traduzidas** (`dictate --captions`): o trecho em andamento é retranscrito a cada 0,5 s e a prévia também é traduzida; frases fecham nos limites de segmento do próprio Whisper (sem partir palavra) ou nas pausas. Idioma detectado uma vez com ≥70% de confiança antes da 1ª legenda (em 1–3 s o Whisper confundia russo com alemão). Sem VAD (não descarta canto). Tradutor: NVIDIA (prévia a cada 2,5 s, sob o limite do plano grátis) ou Ollama local (~0,4 s, sem limite). Em inglês o próprio Whisper traduz.
* **Engrenagem durante um ditado deixava o atalho mudo** enquanto os Ajustes ficassem abertos (a trava do ditado continuava presa): agora é solta.
* **Som do computador como entrada** (`dictate --system` ou Ajustes → Microfone): transcreve vídeo/reunião direto da saída de áudio (`@DEFAULT_MONITOR@`), sem calibrar, pausar mídia, abaixar volume nem RNNoise; termina no 2º toque ou na duração máxima.
* **DeepSeek como provedor de IA** (ditado e legendas), V4.1 Flash sem raciocínio. Medido pelo mesmo código: tradução melhor que a NVIDIA (chrF 89,3 × 82,7; a NVIDIA chegou a devolver espanhol sem traduzir), porém ~2× mais lenta por chamada (805 × 430 ms); nas legendas, latência ponta a ponta equivalente e sem limite de requisições.
* **Efeito lente nas legendas**, ligado por padrão (Ajustes → Reconhecimento → Aparência da legenda): a linha em foco fica maior (1,1–2×) e as vizinhas encolhem e esmaecem numa curva gaussiana; a altura do cartão não muda (as bordas compensam). O foco acompanha a frase mais nova; alcance e posição (acima/centro/abaixo) ajustáveis, com pré-visualização ao vivo. Desenho das legendas extraído para `ui/captionview.py`, usado pelo overlay e pela pré-visualização.
* **Legenda legível com fala rápida:** cada frase é um bloco que não muda depois de traduzido (antes era um parágrafo único refeito a cada atualização, com palavras pulando de linha); a prévia fica num bloco próprio em itálico; o texto desliza para cima em vez de saltar, com degradê no topo; cartão de altura fixa; roda do mouse pausa para reler ("↓ ao vivo"), volta sozinho ao fim ou após 8 s.
* **Hunyuan MT 1.5 (local) como opção de tradutor das legendas**, com o prompt oficial da Tencent (template chinês quando a origem é chinês). Precisa do modelo no Ollama (Modelfile do README da Tencent); sem ele, cai no automático.
* **Tradutor das legendas no automático: DeepSeek → NVIDIA → Ollama**, pela qualidade medida. Avaliados e descartados como tradutor local: NLLB-200 1.3B (chrF 72,8, português de Portugal) e Hunyuan MT 1.5 1.8B (~71, acrescentava trechos que não estavam no áudio).
* **Conexão HTTPS reaproveitada e chave em cache:** a NVIDIA caiu de ~730 para ~430 ms por chamada.
* **Trocar o modelo não exige reiniciar o serviço:** o daemon recarrega no próximo ditado.
* **Pausa música e vídeos ao ditar** (MPRIS: navegador, Spotify, VLC…) e retoma depois. Com música tocando, o mic ouvia as caixas de som como fala: o ditado não encerrava, a letra aparecia na tela e o Whisper alucinava.

### Bugs resolvidos
1. **Idioma "Detectar automaticamente" não transcrevia nada:** o faster-whisper recusa `"auto"`. Agora detecta só entre português e inglês (`auto_languages`): livre, chutava turco em trechos curtos.
2. **Comandos de voz duplicavam pontuação:** "Olá vírgula, tudo bem ponto final." saía "Olá,, tudo bem.." e "Nova linha." perdia a quebra de linha.
3. **Resposta inesperada da IA (200 sem JSON) derrubava o ditado:** agora cola o texto original.
3b. **A IA respondia em vez de reescrever/traduzir:** "me diga uma piada" no modo Corrigir virava uma piada, "você pode me ajudar amanhã" no modo Mensagem virava "Claro, posso ajudar…" e, nas legendas, "you want anything?" virava "Não, obrigado…". O texto agora vai entre marcações, com a regra de nunca responder e um exemplo; verificado 3× por caso.
4. **"Copiar" do histórico sumia ao fechar a janela:** usa xclip/wl-copy, que persistem.
5. **config.json corrompido impedia o app de abrir:** usa os padrões e registra no log.
6. **Opção de linha de comando com erro de digitação começava a gravar:** agora mostra a ajuda.
7. O microfone fecha durante a transcrição e a revisão; o switch do serviço não trava mais os Ajustes.
8. **Música/voz cantada sumia:** o RNNoise apaga música (e o vocal junto), o VAD não vê canto como fala e o idioma fixo estraga letra em outra língua. Se a passada normal não der texto, uma 2ª passada no áudio original roda sem esses filtros, com idioma automático, aceitando só segmentos confiáveis e 4+ palavras (ruído continua descartado).
9. **Alucinações do Whisper em ruído** ("…receber notificações de novos vídeos", "Legendas pela comunidade Amara.org") eram coladas: agora são descartadas.
10. O instalador reaproveita o ambiente Python numa atualização (não baixa o faster-whisper de novo).

---

## v3.2 — 2026-07-03

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
