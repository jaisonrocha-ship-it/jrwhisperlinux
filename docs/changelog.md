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
* **Meu estilo nos e-mails** (Ajustes → Inteligência → Meu estilo): `dictate --study-style` (ou "Reestudar meu estilo") lê os e-mails enviados das pastas do vault escolhidas em "Fontes do estilo" (só a linha `Pasta:` com enviados; o export põe o corpo como citação, que é desfeita; histórico citado e assinatura saem), estuda com a IA local em lotes (~14 s cada, pausa se a GPU passar de 83 °C) e escreve "Meu estilo de escrita.md" com regras e expressões. Resumo em JSON e filtro de nomes/números: nada de cliente vai para a nota. A nota é sua: só o bloco automático é refeito. Os modos de e-mail usam a nota + as 3 últimas correções suas de e-mails da IA. Medido no mesmo ditado: sem estilo, abertura inventada e o destinatário sumia; com estilo, "Bom dia, Marcos, … Me fala se ficou ok." no mesmo ~1 s. Primeira rodada: 120 e-mails (TESC 2018, EGA 2025–26) em 3,5 min.
* Ajustes → Inteligência: chave e modelo identificados por serviço (NVIDIA, DeepSeek) e na ordem da fila (local primeiro).
* **Léxico de logística** (Ajustes → Texto; `dictate --build-lexicon`, ~6–16 s, sem LLM): jargão do glossário (`~/glossario-logistica`) que está fora dos dicionários comuns do sistema e aparece nos seus e-mails/ditados ou ≥20× nos livros de porto/comex do vault; sigla que você usa entra como sigla ("PSC" é Port State Control, não o "polar stratospheric cloud" do glossário). Vira a nota "Léxico de logística.md": risque para tirar (continua fora ao recriar), "Meus termos" e "Traduções" são seus. Usos: os termos que você usa vão para o vocabulário do Whisper; a IA recebe pistas de jargão mal transcrito e a lista de termos corretos para manter; o modo Inglês e as legendas usam ~90 traduções curadas (as do glossário eram palavra por palavra). Medido com o qwen2.5: "laitime… demorage" → "laytime… demurrage" (sem léxico: "latenete… demora"); "danage pra peação" → "dunnage para peação" (antes trocava peação por "instalação"); inglês "estufagem/peação/berço" → "stuffing/lashing/berth" (antes "steaming/uncoiling"). +0–50 ms; pistas em 0,3–6,5 ms. Os livros não entram no estilo: são de outros autores e em inglês.
* **Tempos por etapa no log** (transcrição e texto/IA, em ms) para medir o impacto de cada novidade na agilidade.

### Visual e fluidez
* **Orbe de vidro luminoso:** corpo translúcido (a tela aparece atrás) com plasma e borda de luz, sem o halo escuro que virava mancha em fundo claro. Reage com força à voz: curva perceptual (fala baixa já mexe), cresce até +25% (antes +10%), as bolhas até +40%, a borda acende. E ficou mais leve: 3,7 → ~2,8 ms por quadro.
* **Ondas de luz por frequência:** cada fita segue uma faixa do espectro (graves → agudos) em vez de todas seguirem o nível; a luz some antes de bater na borda.
* **Barras espelhadas** (estilo Gravador de Voz): graves no centro, crescendo para cima e para baixo, cor simétrica e marcador de pico que cai com gravidade. A calibração usa as mesmas barras. Desenhadas num caminho só: 0,50 → 0,47 ms.
* **Sinal de trabalho:** três pontinhos em onda no fim do texto parcial (com espaço reservado na linha) e uma faixa de luz atravessando o texto ao transcrever ou quando a IA reescreve na revisão.
* **Legendas com frase em foco estável** no lugar da lente: a lente recalculava a escala de cada linha pela distância ao foco a cada quadro, então durante a rolagem o texto lido crescia e encolhia, e as bordas desciam a 0,55× (ilegível). Agora a frase mais nova fica maior numa faixa fixa, as anteriores em tamanho normal esmaecendo com a idade, e o tamanho só muda na troca de foco (~0,2 s), com a frase nova entrando em fade. Prévia mais legível (62%) e rolagem mais ágil. Sai o ajuste "Alcance".
* **Fade do overlay no relógio de quadros:** o timer de 14 ms com passo linear andava aos degraus no painel de 165 Hz; agora entra em ~0,25 s e sai em ~0,16 s com curva suave.
* **Ícones nítidos em qualquer posição e em HiDPI:** o microfone e a engrenagem eram imagens coladas em posição fracionária (o borrão dobrava: 144 → 290 pixels de meio-tom); agora o vetor é rasterizado no tamanho exato em pixels do dispositivo e alinhado ao pixel. Os ícones das janelas saem na escala do monitor.
* **Um vidro só para os cartões do overlay** (caixa de texto, legendas, pílula, status), com sombra curta e borda: sobre página escura cheia de texto, o ditado se misturava com a página e o texto branco de trás aparecia sob os chips. A engrenagem ganhou um disco e não some mais em fundo claro.
* **Janelas coesas:** o texto de busca vazio era laranja no Spotlight e no histórico (cor do tema do sistema); a janela de Ajustes abria com 1297 px porque um ditado longo na aba Histórico alargava todas as abas (agora 900 px, títulos longos terminam em "…"); números com vírgula decimal em todo lugar ("0,60", "limiar 0,0029"); a calibração mostra a data como o histórico ("Calibrado · Ontem 13:35").
* **Nomes de microfone legíveis:** duas entradas iguais ("Áudio Interno (PCI)") ganham "· 2", e o mic escolhido mas desconectado aparece como "Yeti GX · desconectado" em vez do id do PulseAudio.

### IA local
* **Modelo local sempre pronto:** a reescrita pelo Ollama não pedia `keep_alive`, então depois de 5 min parado o modelo descarregava e recarregar (2–12 s) estourava os 3 s que a fila dá ao local: o ditado ia para a nuvem justamente quando o local seria o mais rápido. Agora o modelo fica 30 min carregado e começa a carregar quando você começa a falar, gerando 1 token para aquecer a GPU. Medido: 1,8 s de pré-carga durante a fala, 322 ms na 1ª reescrita, ~205 ms nas seguintes.
* **Ollama próprio do ditado** (`jrwhisper-ollama`, porta 11435, GPU, sobe no boot com o Docker): o ditado usava o Ollama que veio com o Moorcheh (memória do Hermes), e um `moorcheh down` levava a IA local e o tradutor das legendas junto. Reaproveita os modelos já baixados.

### Instalação
* **Macropad (opcional):** um teclado macro genérico de 6 teclas + knob (WCH CH57x, USB `1189:8890`, sem marca) vira painel do ditado: ditar, e-mail, som do computador, legendas, busca e Ajustes, com o knob no volume e o aperto ditando. Mapa em `config/macropad.yaml` (gravado no dispositivo com `ch57x-keyboard-tool`), push-to-talk segurando a tecla e ícones das teclas para gravação a laser em `assets/macropad/`. Passo a passo no README.
* **O comando `dictate` sobrevive a mover ou renomear o repositório:** era um symlink, e mover a pasta quebrava atalhos, menu e o serviço. Agora é um lançador que guarda o caminho e, se ele sumir, procura em `~` e se corrige; sem repositório, avisa na tela.
* O instalador passa a instalar `gir1.2-rsvg-2.0` e `gir1.2-atspi-2.0` (ícones e contexto do campo); numa instalação limpa, os Ajustes e o overlay quebravam.

### Correções
* **A IA cortava aspas do texto:** `Ele disse “sim”` virava `Ele disse “sim`, e um raciocínio `<think>` cortado pelo limite de tokens era colado no campo. Agora só sai o par de aspas que embrulha a resposta inteira, e raciocínio cortado faz o ditado colar o original.
* **Histórico mostrava "31/12" no lugar de "Ontem"** no 1º de janeiro depois de um ano de 365 dias (e no dia em que termina o horário de verão).
* `tests/test_gpu.py` baixava 1,5 GB de um modelo fixo; agora usa o modelo do config e o preload do cuBLAS.
* Documentação refeita: README completo (atalhos, recursos, Ajustes, privacidade, arquivos, problemas comuns), `docs/configuration.md` com cada chave do config e `docs/architecture.md` descrevendo o código atual.

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
