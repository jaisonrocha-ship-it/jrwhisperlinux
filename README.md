# 🎤 JRWhisperLinux

> Fale. O texto aparece onde você está. Ditado por voz para Linux, roda na sua máquina, offline.

<p align="center">
  <a href="https://jrwhisper.jasonrock.dev"><img src="https://img.shields.io/badge/Site-jrwhisper.jasonrock.dev-F59E0B?style=flat-square" alt="Site"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/Licença-MIT-blue.svg?style=flat-square" alt="MIT"></a>
  <a href="docs/licenses.md"><img src="https://img.shields.io/badge/Deps-100%25%20livre-F59E0B?style=flat-square" alt="Open Source"></a>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/GPU-CUDA-76B900?style=flat-square&logo=nvidia" alt="CUDA">
</p>

---

## O que é

JRWhisperLinux captura áudio do microfone, transcreve com um modelo de IA rodando localmente e cola o texto no campo ativo. Aperte Super+Shift+V, fale, e o texto aparece onde você está. Sua voz nunca sai da sua máquina.

---

## Tecnologias

| Camada | Tecnologia | O que faz |
| :--- | :--- | :--- |
| **IA** | `faster-whisper` (turbo) | Transcrição local em GPU NVIDIA (CUDA int8_float16) ou CPU (int8). |
| **Voz** | `RNNoise` via FFmpeg `arnndn` | Rede neural que separa sua voz do ruído ambiente — teclado, música, conversa de fundo. |
| **Visual** | GTK3 / Cairo / Pango | Janela overlay translúcida com VU meter e texto ao vivo. |
| **Áudio** | PulseAudio / PipeWire (`parec`) | Captura em 16kHz mono com 30ms de latência. |
| **Input** | `xdotool` / `wtype` / `xclip` / `wl-clipboard` | Detecta X11 ou Wayland e injeta o texto na janela ativa. |

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

## Para quem serve

| Perfil | Uso |
|--------|-----|
| **Desenvolvimento** | Escreva comentários, commits e documentação sem tirar as mãos do teclado |
| **Produção de texto** | Artigos, correspondência e relatórios — falar é mais rápido que digitar |
| **Acessibilidade** | Alternativa ao teclado para LER, tendinite ou limitações motoras |
| **Português brasileiro** | 95% de acurácia com o modelo turbo; vocabulário customizável por domínio |

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

## Instalação

### Via script (recomendado)

```bash
curl -fsSL https://jrwhisper.jasonrock.dev/install.sh | bash
```

Instala tudo automaticamente: dependências do sistema, ambiente Python, atalho de teclado, daemon e pré-carrega o modelo. Funciona em qualquer Debian/Ubuntu/Mint.

Pressione **Super+Shift+V** e comece a ditar. Pronto.

### Manual (via Git)

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
