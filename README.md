# 🎤 JRWhisperLinux

> Ditado por voz premium com latência zero e isolamento de voz neural para Linux (X11 & Wayland), inspirado no fluxo de experiência (UX) do macOS WhisperFlow.

<p align="center">
  <a href="https://jrwhisper.jasonrock.dev"><img src="https://img.shields.io/badge/🌐%20Site-jrwhisper.jasonrock.dev-22C55E?style=flat-square" alt="Site"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/Licença-MIT-blue.svg?style=flat-square" alt="License"></a>
  <a href="docs/licenses.md"><img src="https://img.shields.io/badge/Dependências-100%25%20Open%20Source-22C55E?style=flat-square" alt="Open Source"></a>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/GPU-CUDA-76B900?style=flat-square&logo=nvidia" alt="CUDA">
</p>

---

## 🌟 O que é o JRWhisperLinux?

O **JRWhisperLinux** é um assistente de ditado por voz profissional desenvolvido para distribuições Linux. Ele permite que você converta sua fala em texto instantaneamente e a insira diretamente no cursor de qualquer aplicativo ativo, bastando pressionar um atalho de teclado global.

A aplicação combina um modelo de Inteligência Artificial local de alta fidelidade com uma interface gráfica minimalista e fluida, oferecendo uma experiência de entrada de texto nativa, veloz e de alta precisão.

---

## 🛠️ Tecnologias Utilizadas

A arquitetura do projeto foi desenhada para priorizar performance máxima, consumo eficiente de VRAM/CPU e latência zero:

| Camada | Tecnologia | Descrição |
| :--- | :--- | :--- |
| **Inteligência Artificial** | `faster-whisper` (medium) | Transcrição local otimizada rodando em GPU NVIDIA (CUDA `int8_float16`) ou fallback automático para CPU (`int8`). |
| **Isolamento de Voz** | `RNNoise` via FFmpeg `arnndn` | Filtro de rede neural recorrente (RNN) que isola a voz humana, eliminando músicas de fundo, cliques de teclado e estalos. |
| **Interface Visual** | GTK3 / Cairo / Pango | Janela de overlay translúcida antialiased com animação Cairo da onda Siri a 60 FPS e renderização de texto via Pango markup. |
| **Captura de Áudio** | PulseAudio / PipeWire (`parec`) | Captura direta em 16kHz mono com latência ultra-baixa de fragmentação (30ms). |
| **Simulação de Input** | `xclip` / `xdotool` / `wl-clipboard` / `wtype` | Emulador híbrido de área de transferência e teclas que detecta e suporta sessões gráficas X11 e Wayland. |

---

## 🚀 Principais Recursos

### 1. Modo Daemon Persistente (Latência 0s)
O modelo Whisper permanece pré-carregado na GPU em background através de um servidor de socket Unix (`/tmp/dictate_daemon.sock`). Ao ativar o atalho, a captura de voz inicia em **menos de 70ms**, eliminando o delay comum de inicialização de modelos de IA.

### 2. Interface Deslizante de 3 Linhas (Altura Rígida)
Para evitar que blocos de texto longos deformem ou redimensionem o modal durante a fala, a interface exibe exatamente as 3 últimas linhas ativas do ditado:
* **Linha anterior (antiga):** Renderizada com 25% de opacidade para contexto.
* **Linha do meio:** Renderizada com 60% de opacidade.
* **Linha atual (ativa):** Renderizada com 95% de opacidade e em itálico dinâmico.
* *A altura do modal permanece perfeitamente estática, eliminando trepidação visual.*

### 3. Isolamento de Voz Neural Integrado
O áudio capturado é processado localmente em frações de segundo por uma rede neural `RNNoise` antes de ir ao Whisper. Música ambiente, barulho de escritório ou digitação mecânica são totalmente ignorados. O processo é agendado com prioridade de CPU reduzida (`nice -n 19`) para não engasgar a máquina.

### 4. Inteligência Multi-Monitor
O overlay visual do ditado rastreia a posição do mouse e é exibido automaticamente no monitor onde o cursor do usuário está posicionado, ideal para setups profissionais de múltiplas telas.

### 5. VAD de Histerese Inteligente
O script calibra o threshold de ruído do seu ambiente automaticamente. Ele ignora barulhos curtos (como respirações rápidas ou estalos) usando uma janela de confirmação de fala de **150ms** e encerra o ditado após **1.7s** de silêncio contínuo.

---

## 🎯 Para quem é?

| Perfil | Uso |
|--------|-----|
| 👨‍💻 **Desenvolvedores** | Escreva código, commits, documentação e logs sem tirar as mãos do teclado |
| ✍️ **Escritores** | Produza textos longos, artigos e documentos falando naturalmente |
| ♿ **Acessibilidade** | Alternativa de entrada para LER, dificuldades motoras ou preferência por voz |
| 🌎 **Multilíngue** | Suporte nativo a PT-BR (95% acurácia) + 90+ idiomas do Whisper |

## 💻 Compatibilidade

| Distro | Status |
|--------|--------|
| Linux Mint 22 (Cinnamon) | ✅ **Ambiente primário de desenvolvimento** |
| Linux Mint 21 | ✅ Suportado |
| Ubuntu 24.04 | ✅ Suportado (GNOME, X11/Wayland) |
| Ubuntu 22.04 | ✅ Suportado |
| Debian 12 | ✅ Suportado |
| Fedora 38+ | ⚠️ Instalação manual (use `dnf`) |
| Arch Linux | ⚠️ Instalação manual (use `pacman`) |

**Desktops:** Cinnamon (atalho automático), GNOME, XFCE, KDE · **Display:** X11 (nativo), Wayland (suportado)
**Pré-requisitos:** Python 3.10+, 4GB RAM, 2GB disco · GPU NVIDIA opcional (acelera 10x)

---

## 📥 Instalação

### 1 comando (recomendado)

```bash
curl -fsSL https://jrwhisper.jasonrock.dev/install.sh | bash
```

Instala tudo automaticamente: dependências do sistema, ambiente Python, atalho de teclado, daemon e pré-carrega o modelo. Funciona em qualquer Debian/Ubuntu/Mint.

Pressione **Super+Shift+V** e comece a ditar. Pronto.

### Instalação manual (via Git)

```bash
git clone https://github.com/jaisonrocha-ship-it/jrwhisperlinux.git
cd jrwhisperlinux
bash scripts/install.sh
```

---

## ⚙️ Configuração do Sistema (Modo Daemon e Atalho)

### 1. Iniciar o Servidor Daemon com o Systemd

Para ter latência zero no acionamento, configure o Daemon para carregar o modelo de voz assim que você logar no computador:

1. Copie o arquivo de serviço para a pasta do systemd de usuário:
   ```bash
   mkdir -p ~/.config/systemd/user/
   cp config/dictate-daemon.service ~/.config/systemd/user/
   ```
2. Ative e inicie o serviço:
   ```bash
   systemctl --user enable dictate-daemon.service
   systemctl --user start dictate-daemon.service
   ```
3. Verifique o status:
   ```bash
   dictate --status
   ```

### 2. Configurar o Atalho de Teclado Global

No painel de controle da sua distribuição (ex: Configurações do Sistema -> Teclado -> Atalhos Personalizados):
* **Nome:** Ditado JRWhisper
* **Comando:** `~/.local/bin/dictate` (ou o caminho onde o script foi instalado)
* **Atalho:** `Super+Shift+V` (ou o de sua preferência)

---

## 📝 Arquivo de Configuração (`config.json`)

As configurações são salvas em `~/.config/dictate/config.json`. Veja os parâmetros disponíveis:

```json
{
  "model": "medium",
  "language": "pt",
  "mic_device": "easyeffects_source",
  "silence_threshold": 0,
  "silence_duration": 1.7,
  "listen_timeout": 15,
  "max_duration": 60,
  "noise_suppression": true,
  "voice_commands": true,
  "remove_fillers": true
}
```

* **`model`:** Modelo do faster-whisper. Recomenda-se `medium` para pt-BR (excelente relação velocidade/acurácia).
* **`mic_device`:** Dispositivo de captura. Use `"easyeffects_source"` para passar pelo EasyEffects, ou `"@DEFAULT_SOURCE@"` para capturar o microfone padrão do sistema diretamente.
* **`silence_duration`:** Segundos de silêncio necessários para autocompletar e colar o texto (padrão: `1.7`s).
* **`noise_suppression`:** Habilita o isolamento neural RNNoise integrado via FFmpeg.

---

## 🔍 Resolução de Problemas (Troubleshooting)

### O atalho não abre o overlay
* Certifique-se de que dependências como `python3-gi` estão instaladas no sistema.
* Verifique se o daemon está travado ou se o arquivo de lock `/tmp/dictate.pid` ficou órfão.

### Erro de VRAM / Carregamento CUDA
* Se você receber erros relativos a `libcublas.so.12` ausente, o script fará fallback automático para CPU. Para usar a GPU, certifique-se de instalar os pacotes CUDA apropriados ou configure caminhos de bibliotecas compatíveis no driver.

---

## 🔓 Stack Completa & Licenças — 100% Open Source

**JRWhisperLinux é software livre.** Cada dependência foi auditada. Nenhum componente proprietário ou código fechado.

### Python (pip) — Todas MIT/BSD/Apache 2.0

| Pacote | Licença | Função |
|--------|---------|--------|
| `faster-whisper` | MIT | Transcrição via CTranslate2 (SYSTRAN) |
| `ctranslate2` | MIT | Inferência otimizada GPU/CPU |
| `onnxruntime` | MIT | Runtime de redes neurais |
| `numpy` | BSD 3-Clause | Processamento de áudio, arrays |
| `huggingface-hub` | Apache 2.0 | Download de modelos |
| `PyAV` | BSD 3-Clause | Binding Python para FFmpeg |
| `tqdm` | MIT + MPL 2.0 | Barras de progresso |

### Interface (sistema) — Todas LGPL/MPL

| Componente | Licença | Função |
|------------|---------|--------|
| PyGObject (GTK3) | LGPL 2.1+ | Overlay visual |
| Pango | LGPL 2.1 | Renderização de texto |
| Cairo | LGPL 2.1 / MPL 1.1 | Gráficos vetoriais |

### Sistema (apt) — Ferramentas externas, não bundadas

| Ferramenta | Licença | Função |
|------------|---------|--------|
| `xdotool` | BSD | Injeção de texto (X11) |
| `wtype` | MIT | Injeção de texto (Wayland) |
| `xclip` | GPL 2 | Clipboard X11 *(externo)* |
| `wl-clipboard` | GPL 3 | Clipboard Wayland *(externo)* |
| `ffmpeg` | LGPL/GPL | Processamento de áudio *(externo)* |
| PulseAudio | LGPL 2.1 | Captura de microfone |
| PipeWire | LGPL 2.1 | Servidor de áudio moderno |

> ⚠️ xclip, wl-clipboard e ffmpeg têm licenças GPL, mas são **dependências externas de sistema** — o usuário as instala via `apt`, não são bundadas no projeto. O JRWhisperLinux em si (MIT) não herda obrigações de copyleft.

### Modelos de Rede Neural

| Modelo | Licença |
|--------|---------|
| Whisper (OpenAI) | MIT |
| RNNoise Models | Domínio Público |
| Silero VAD | MIT |

### Auditoria

- **Data:** 24/07/2026
- **Método:** `pip show` para cada pacote Python + verificação de licenças de sistema
- **Resultado:** ✅ Zero código proprietário. Zero dependência fechada. Zero restrições de uso comercial.

---

## 📄 Licença

Este projeto é disponibilizado sob a **Licença MIT**. Sinta-se livre para usar, modificar e distribuir.
