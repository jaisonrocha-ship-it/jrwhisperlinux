# AGENTS.md — JRWhisperLinux

Instruções para agentes de IA (Hermes, Claude, Codex, Gemini) trabalhando neste projeto.

## Identidade

- **Nome:** JRWhisperLinux
- **Propósito:** Ditado por voz para Linux com IA local (faster-whisper + GTK3 overlay)
- **Linguagem:** Python 3.12 (system Python, venv com --system-site-packages)
- **Usuário:** JR (português brasileiro, Linux Mint 22 Cinnamon X11, NVIDIA RTX 4060)
- **Licença:** MIT · 100% open source

## Antes de Começar

1. Leia `README.md` — visão geral e quick start
2. Leia `docs/architecture.md` — como o sistema funciona internamente
3. Leia `docs/licenses.md` — auditoria completa de dependências
4. Leia `DESIGN.md` — tokens de design do site
5. Consulte a wiki: `[[JRWhisperLinux]]` no vault JasonRock.DEV

## Arquivos-Chave

| Arquivo | Função |
|---------|--------|
| `src/dictate` | Porta de entrada (bootstrap do venv + `jrwhisper.cli.main`) |
| `src/jrwhisper/` | Pacote. Núcleo: `config`, `audio` (captura, calibração por mic, Yeti), `transcribe` (Whisper/daemon/RNNoise), `dictation` (laço de sessão: PTT, mãos livres), `pipeline` (perfil → modo IA → formatação → IA → atalhos de texto), `textproc`, `learning` (correção da revisão → regra do dicionário), `paste`, `profiles`, `ai`, `history`, `ptt`, `shortcuts` (dconf), `secrets` (keyring), `cli` |
| `src/jrwhisper/ui/` | `theme` (tokens macOS, ícone padrão das janelas, componentes inset-grouped, PopupChoice, Swatch), `visuals` (Orbe de plasma/Ondas/Barras + FFT), `overlay` (HUD em Cairo), `captionview` (legendas: blocos, rolagem, efeito lente; também a prévia dos Ajustes), `settings` (10 abas), `calibration`, `history_search` (Spotlight) |
| `assets/fonts/` | Inter variável (OFL), instalada pelo `install.sh` |
| `assets/icons/jrwhisper.svg` | Ícone do app (dock/menu). `install.sh` instala no hicolor + `jrwhisper.desktop` com `StartupWMClass=dictate` (é assim que o Plank casa a janela) |
| `scripts/install.sh` | One-line installer (curl | bash) |
| `config/config.json` | Configuração padrão (não trackeada no git) |
| `config/dictate-daemon.service` | Serviço systemd para modo daemon |
| `tests/` | Testes manuais (ainda sem pytest automatizado) |
| `docs/` | Documentação complementar |

## Ambiente de Execução

```bash
# O venv usa --system-site-packages (GTK3 vem do sistema)
VENV=~/.local/share/dictation-venv
PYTHON=$VENV/bin/python3

# Testar
$PYTHON src/dictate --status

# Instalar do zero
bash scripts/install.sh
```

## Regras de Ouro

1. **Nunca usar PortAudio/sounddevice** — capture de mic é via `parec` (PulseAudio CLI). Device indices do PortAudio são instáveis.
2. **Nunca suavizar RMS** — suavização adiciona latência. Use RMS instantâneo com ticks de confirmação de fala.
3. **GPU via preload** — CUDA é carregado com `ctypes.cdll.LoadLibrary` do `/opt/resolve/libs/`. Não depende de `libcublas.so.12` no sistema.
4. **xclip + xdotool** — injeção usa clipboard (`xclip -selection clipboard` + `ctrl+v`) com fallback para `xdotool type --window`.
5. **Daemon via socket Unix** — `$XDG_RUNTIME_DIR/dictate_daemon.sock` (logs, WAVs e PID também ficam lá, nunca em /tmp). Mantém modelo carregado para latência zero. Cada requisição leva `model`/`language`/prompt do config (via `transcribe._transcribe_kwargs`); se o modelo mudou, o daemon recarrega sozinho. `language: "auto"` vira `None` (o faster-whisper rejeita "auto").
6. **Silence detection com histerese** — confirmação de fala 150ms + gap tolerance 2.5s.
7. **GTK3 threads** — use `GLib.idle_add` para atualizar UI de threads background.
8. **`os.execv` no bootstrap** — reexecuta o script dentro do venv. Cuidado com `sys.argv`.
9. **Instalação por symlink** — `~/.local/bin/dictate` aponta para `src/dictate`, que acha o pacote via `realpath`. Nunca copie só o `src/dictate`.
10. **2º toque no atalho = SIGUSR1** — a segunda instância só sinaliza e sai. `DictateThread.hotkey()` decide pelo `stage`: waiting cancela, listening encerra e transcreve, choosing cola, busy ignora. SIGTERM continua sendo "sair".

## Pitfalls Conhecidos

- **CUDA OOM na RTX 4060**: desktop ocupa 4-5GB. Modelo turbo em int8_float16 usa ~1GB.
- **Yeti GX mute físico**: microfone captura near-zero quando mutado. Verificar antes de debugar "sem áudio".
- **Yeti GX ganho de hardware**: o miniapp OSBOT Control (seção Yeti) ajusta o ganho interno do mic. Em zero, a voz chega a ~-80 dBFS mesmo com ALSA/PipeWire em 100% — o `amixer` não enxerga esse ganho. Diagnóstico rápido: `dictate --calibrate` (voz normal fica entre -20 e -50 dBFS); com `~/dev/yeti-ctl` presente ele mostra ganho/mute do hardware e o overlay diz "Yeti mutado no hardware" / "Ganho do Yeti em X/100". Calibração é por mic (`mic_calibrations` no config, com `hw_gain` do Yeti); ganho fora de ±5 invalida e volta ao automático. Janela: `CalibrationWindow` (`--calibrate-gui`), aberta também pelo applet OBSBOT Control (aba MIC).
- **parec latency (PipeWire)**: use `--latency-msec=30` para evitar buffer de 2 segundos.
- **Config.json no .gitignore**: alterações locais não são commitadas.
- **RNNoise**: `config/bd.rnnn` (~300KB, domínio público) é o único modelo usado. Instalado em `~/.config/dictate/`. O teste `test_capture_prebuffer.py` rejeita arquivo < 100KB (já houve um "404: Not Found" salvo no lugar).
- **Tema GTK do sistema (MacTahoe-Dark)**: impõe 44 px a ComboBox e tamanho mínimo a botões. Use `theme.PopupChoice` (não `Gtk.ComboBoxText`) e `theme.Swatch` (Cairo) para bolinhas de cor; regras de cor de botão precisam mirar o `label` filho (`label {}` global sobrescreve).
- **NVIDIA NIM**: dos 59 modelos listados por `/v1/models`, só 8 respondiam com a chave (out/2026); o resto dá 404. Modelos Nemotron/gpt-oss são de raciocínio: `ai._no_reasoning` manda `enable_thinking: false` / `reasoning_effort: low`, senão gastam segundos "pensando". Lista verificada em `ai.RECOMMENDED`. A chave fica só no gnome-keyring (`secret-tool lookup service jrwhisper provider nvidia`); nunca em config, código ou log.
- **Overlay click-through**: `input_shape_combine_region` só na engrenagem; o resto da janela não captura cliques. Tudo desenhado em Cairo/PangoCairo (sem widgets), então o tema do sistema não interfere.
- **Ajustes aplicam na hora**: `SettingsWindow.set()` grava com debounce de 350 ms (escrita atômica). Chaves novas de config devem ser planas (o `load_config` faz merge raso).
- **Wayland overlay**: overlay GTK3 funciona via XWayland. Em Wayland puro, use `wtype` em vez de `xdotool`.

## Infra de Publicação

| O que | Onde |
|-------|------|
| **GitHub** | github.com/jaisonrocha-ship-it/jrwhisperlinux |
| **Site** | jrwhisper.jasonrock.dev (Oracle VM, Nginx) |
| **Site source** | ~/projects/jr-whisper/index.html + tokens.css |
| **Installer** | ~/projects/jr-whisper/install.sh → servido no site |
| **DNS** | Cloudflare, zone jasonrock.dev, API key em ~/.hermes/secrets/ |

### Deploy do site

```bash
scp ~/projects/jr-whisper/index.html ~/projects/jr-whisper/tokens.css jrdev-oracle:/tmp/
ssh jrdev-oracle 'sudo mv /tmp/index.html /tmp/tokens.css /var/www/sites/jrwhisper.jasonrock.dev/ && sudo chown -R www-data:www-data /var/www/sites/jrwhisper.jasonrock.dev/'
```

### Deploy do installer

```bash
scp ~/projects/jr-whisper/install.sh jrdev-oracle:/tmp/
ssh jrdev-oracle 'sudo mv /tmp/install.sh /var/www/sites/jrwhisper.jasonrock.dev/ && sudo chmod 755 /var/www/sites/jrwhisper.jasonrock.dev/install.sh && sudo chown www-data:www-data /var/www/sites/jrwhisper.jasonrock.dev/install.sh'
```

## Roadmap Priorizado

0. ~~Redesign estilo macOS + IA, perfis, histórico, PTT, mãos livres~~ (out/2026)
1. **Packaging .deb** — instalação nativa via apt
2. **Testes automatizados** — pytest para motor de áudio e VAD
3. **CI/CD** — GitHub Actions para Ubuntu/Mint/Fedora
4. **AppIndicator** — ícone na bandeja do sistema
5. ~~Config GUI — painel GTK3 para configurações~~ (Ajustes, out/2026)
6. **Wayland nativo** — overlay sem XWayland
7. **Flatpak** — distribuição universal

## Design do Site

- **Fonte:** Red Hat Display + Red Hat Text + Red Hat Mono (Google Fonts)
- **Cor:** Âmbar #F59E0B sobre carvão #0C0C0F (dark) / #FBF9F6 (light)
- **Ícones:** Lucide SVG (MIT) — inline, sem dependências
- **Estilo:** Impeccable Brand Register + anti-slop copy
- **Regras:** zero emoji, zero voz passiva, zero filler words
