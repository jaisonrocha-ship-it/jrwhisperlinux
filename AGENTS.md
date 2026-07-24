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
| `src/dictate` | Script principal (2357 linhas) — código de produção |
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
5. **Daemon via socket Unix** — `/tmp/dictate_daemon.sock`. Mantém modelo carregado para latência zero.
6. **Silence detection com histerese** — confirmação de fala 150ms + gap tolerance 2.5s.
7. **GTK3 threads** — use `GLib.idle_add` para atualizar UI de threads background.
8. **`os.execv` no bootstrap** — reexecuta o script dentro do venv. Cuidado com `sys.argv`.

## Pitfalls Conhecidos

- **CUDA OOM na RTX 4060**: desktop ocupa 4-5GB. Modelo turbo em int8_float16 usa ~1GB.
- **Yeti GX mute físico**: microfone captura near-zero quando mutado. Verificar antes de debugar "sem áudio".
- **parec latency (PipeWire)**: use `--latency-msec=30` para evitar buffer de 2 segundos.
- **Config.json no .gitignore**: alterações locais não são commitadas.
- **RNNoise models**: em `config/rnnoise-models/`. Domínio público, trackeados no git (~2MB).
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

1. **Packaging .deb** — instalação nativa via apt
2. **Testes automatizados** — pytest para motor de áudio e VAD
3. **CI/CD** — GitHub Actions para Ubuntu/Mint/Fedora
4. **AppIndicator** — ícone na bandeja do sistema
5. **Config GUI** — painel GTK3 para configurações
6. **Wayland nativo** — overlay sem XWayland
7. **Flatpak** — distribuição universal

## Design do Site

- **Fonte:** Red Hat Display + Red Hat Text + Red Hat Mono (Google Fonts)
- **Cor:** Âmbar #F59E0B sobre carvão #0C0C0F (dark) / #FBF9F6 (light)
- **Ícones:** Lucide SVG (MIT) — inline, sem dependências
- **Estilo:** Impeccable Brand Register + anti-slop copy
- **Regras:** zero emoji, zero voz passiva, zero filler words
