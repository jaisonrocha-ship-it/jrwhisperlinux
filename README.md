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

Minimalista por padrão: um atalho, um orbe que reage à sua voz, o texto colado onde o cursor está. Os recursos avançados ficam em **Ajustes** (`dictate -s`), cada um com seu próprio interruptor.

### Essencial
* **Um atalho, dois toques:** o primeiro começa a ouvir; o segundo encerra e transcreve na hora (antes de você falar, cancela). Nada do que foi dito se perde.
* **Latência zero:** o modelo Whisper fica carregado na GPU por um serviço (`$XDG_RUNTIME_DIR/dictate_daemon.sock`); a captura começa assim que o atalho é pressionado. Trocar o modelo nos Ajustes vale no próximo ditado, sem reiniciar nada.
* **Comandos de voz:** "vírgula", "ponto final", "nova linha", "novo parágrafo"… mesmo quando o Whisper já pontuou o comando, sai uma pontuação só.
* **Overlay em três estilos:** Orbe (padrão, esfera de plasma com o mic no centro), Ondas ou Barras de espectro. Cor de destaque, tamanho, posição, brilho e "reduzir movimento" ajustáveis, com pré-visualização ao vivo. Aparece no monitor onde está o mouse e não bloqueia cliques.
* **Isolamento de voz:** RNNoise limpa música, ventilador e teclado antes da transcrição; o que estiver tocando no computador (navegador, Spotify…) é pausado durante o ditado e retomado depois.
* **Detecção de fala com histerese:** 150 ms para confirmar que você começou e uma pausa configurável para encerrar.
* **Calibração por microfone:** medidor ao vivo com espectro; cada mic guarda o próprio limiar. Sem o mic preferido, usa o padrão do sistema e avisa.

### Avançado (Ajustes)
* **Reescrita com IA:** modos Corrigir, E-mail, Mensagem, Inglês e Tópicos (editáveis). Ative dizendo "modo e-mail, …" no começo, por atalho próprio (`dictate --mode email`) ou por aplicativo. NVIDIA NIM (nuvem) ou Ollama (local). Com a IA ligada, o texto não é colado sozinho: fica na tela, qualquer palavra pode ser corrigida com um clique (Enter confirma, Esc cancela), e há botões para trocar de modo (ou voltar ao original), colar, copiar ou descartar. Pelo teclado: Enter cola, Esc descarta, Ctrl+C copia, 1–9 trocam o modo; o 2º toque no atalho também cola. Texto longo rola com a roda do mouse. No modo mãos livres ele continua colando direto. Se a IA falhar, aparece o texto original.
* **Perfis por aplicativo:** terminais colam com Ctrl+Shift+V, em minúscula e sem ponto final; chat sem ponto final; e-mail com pontuação completa. Regras editáveis por classe de janela.
* **Atalhos de texto:** diga "minha assinatura" e o bloco inteiro entra no lugar.
* **Histórico:** local (0600), com retenção configurável e busca estilo Spotlight (`dictate --history`; Enter cola).
* **Push-to-talk:** segure o atalho para falar e solte para enviar (X11).
* **Mãos livres:** depois de colar, volta a ouvir; para com "parar ditado", silêncio longo ou o atalho (que antes transcreve o trecho em andamento).

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

### 3. Calibrar o Microfone (opcional)

Abra **Configurações → Áudio & Captação → Calibrar…** (ou `dictate --calibrate-gui`). A janela mostra o nível do mic ao vivo em dBFS, mede 3 s de silêncio e 5 s de fala e salva o limiar **por microfone**. No terminal: `dictate --calibrate`.

* Cada mic guarda a própria calibração. Sem calibração, o ditado mede o ruído a cada uso (automático).
* Se o mic configurado estiver desconectado, o ditado usa o mic padrão do sistema e avisa no overlay.
* Yeti GX com `yeti-ctl` (controle HID++ do ganho) em `~/dev/yeti-ctl`: a calibração registra o ganho de hardware; se ele mudar mais de 5 unidades, o ditado volta ao automático até você recalibrar.

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
* Verifique se o daemon está travado ou se o arquivo de lock `$XDG_RUNTIME_DIR/dictate.pid` ficou órfão.

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
| `requests` *(apt)* | Apache 2.0 | Cliente da reescrita por IA |
| `python-xlib` *(apt)* | LGPL 2.1+ | Push-to-talk (estado do teclado no X11) |

### Interface (sistema) — Todas LGPL/MPL

| Componente | Licença | Função |
|------------|---------|--------|
| PyGObject (GTK3) | LGPL 2.1+ | Overlay visual |
| Pango | LGPL 2.1 | Renderização de texto |
| Cairo | LGPL 2.1 / MPL 1.1 | Gráficos vetoriais |
| Inter (fonte, embarcada) | SIL OFL 1.1 | Tipografia da interface |
| Lucide (ícones, embutidos) | ISC | Ícones da interface |

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
| `libsecret-tools` | LGPL 2.1 | Chave de API no chaveiro do sistema |

> ⚠️ xclip, wl-clipboard e ffmpeg têm licenças GPL, mas são **dependências externas de sistema** — o usuário as instala via `apt`, não são bundadas no projeto. O JRWhisperLinux em si (MIT) não herda obrigações de copyleft.

### Modelos de Rede Neural

| Modelo | Licença |
|--------|---------|
| Whisper (OpenAI) | MIT |
| RNNoise Models | Domínio Público |
| Silero VAD | MIT |

> A reescrita por IA é opcional e desligada por padrão. Com a NVIDIA NIM, o texto ditado vai para a API da NVIDIA (serviço externo, sujeito aos termos dela); com o Ollama, tudo fica no computador.

### Auditoria

- **Data:** 24/07/2026
- **Método:** `pip show` para cada pacote Python + verificação de licenças de sistema
- **Resultado:** ✅ Zero código proprietário. Zero dependência fechada. Zero restrições de uso comercial.

---

## 📄 Licença

Este projeto é disponibilizado sob a **Licença MIT**. Sinta-se livre para usar, modificar e distribuir.
