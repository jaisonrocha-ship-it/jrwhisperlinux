#!/bin/bash
# JRWhisperLinux — One-Line Installer
# curl -fsSL https://jrwhisper.jasonrock.dev/install.sh | bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}→${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; exit 1; }

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🎤 JRWhisperLinux Installer        ║${NC}"
echo -e "${GREEN}║   Ditado por voz para Linux          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Pre-flight checks ──
command -v python3 >/dev/null 2>&1 || err "Python 3 não encontrado. Instale com: sudo apt install python3"
command -v apt-get >/dev/null 2>&1 || err "Este instalador requer APT (Debian/Ubuntu/Mint). Para outras distros, veja: https://jrwhisper.jasonrock.dev"

# ── 1. System packages ──
info "Instalando dependências do sistema..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    python3-venv python3-pip \
    pulseaudio-utils \
    xdotool xclip wtype wl-clipboard \
    ffmpeg
ok "Pacotes de sistema instalados"

# ── 2. Clone repo (if not already in it) ──
if [ ! -f "./src/dictate" ]; then
    REPO_DIR="$HOME/.local/share/jrwhisperlinux"
    if [ -d "$REPO_DIR" ]; then
        info "Repositório já existe, atualizando..."
        git -C "$REPO_DIR" pull --ff-only
    else
        info "Baixando JRWhisperLinux..."
        git clone --depth 1 https://github.com/jaisonrocha-ship-it/jrwhisperlinux.git "$REPO_DIR"
    fi
    cd "$REPO_DIR"
fi
ok "Código fonte pronto"

# ── 3. Python venv ──
VENV="$HOME/.local/share/dictation-venv"
info "Criando ambiente virtual Python..."
rm -rf "$VENV"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q faster-whisper numpy
ok "Ambiente Python configurado"

# ── 4. Install dictate command ──
info "Instalando comando 'dictate'..."
mkdir -p "$HOME/.local/bin"
cp "$PWD/src/dictate" "$HOME/.local/bin/dictate"
chmod +x "$HOME/.local/bin/dictate"
ok "Comando 'dictate' instalado"

# ── 5. Default config ──
if [ ! -f "$HOME/.config/dictate/config.json" ]; then
    info "Criando configuração padrão..."
    mkdir -p "$HOME/.config/dictate"
    cp "$PWD/config/config.json" "$HOME/.config/dictate/config.json"
    ok "Configuração criada"
else
    ok "Configuração já existe — mantida"
fi

# ── 6. Keyboard shortcut (Cinnamon only, skip if not Cinnamon) ──
if command -v cinnamon >/dev/null 2>&1 || pgrep -x cinnamon >/dev/null 2>&1; then
    info "Configurando atalho Super+Shift+V (Cinnamon)..."
    dconf write /org/cinnamon/desktop/keybindings/custom-list "['custom0']"
    dconf write /org/cinnamon/desktop/keybindings/custom-keybindings/custom0/name "'Dictate'"
    dconf write /org/cinnamon/desktop/keybindings/custom-keybindings/custom0/command "'$HOME/.local/bin/dictate'"
    dconf write /org/cinnamon/desktop/keybindings/custom-keybindings/custom0/binding "['<Super><Shift>v']"
    ok "Atalho Super+Shift+V configurado"
else
    info "Cinnamon não detectado — configure o atalho manualmente para: $HOME/.local/bin/dictate"
fi

# ── 7. Daemon service ──
info "Configurando daemon (carrega modelo no boot para latência zero)..."
mkdir -p "$HOME/.config/systemd/user"
cp "$PWD/config/dictate-daemon.service" "$HOME/.config/systemd/user/dictate-daemon.service"
systemctl --user daemon-reload
systemctl --user enable --now dictate-daemon.service 2>/dev/null || true
ok "Daemon configurado"

# ── 8. Pre-cache model (background) ──
info "Pré-carregando modelo Whisper turbo (~1.5GB) em background..."
nohup "$VENV/bin/python3" -c "
import sys
sys.stdout = open('/tmp/dictate_install.log', 'w')
from faster_whisper import WhisperModel
WhisperModel('turbo', device='cpu', compute_type='int8')
print('OK')
" > /dev/null 2>&1 &
MODEL_PID=$!
ok "Download do modelo iniciado em background (PID $MODEL_PID)"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ JRWhisperLinux instalado com sucesso!        ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                                  ║${NC}"
echo -e "${GREEN}║  🎤 Pressione Super+Shift+V e comece a ditar!    ║${NC}"
echo -e "${GREEN}║  📖 dictate --help    · comandos                 ║${NC}"
echo -e "${GREEN}║  🌐 jrwhisper.jasonrock.dev · documentação       ║${NC}"
echo -e "${GREEN}║                                                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
if [ -n "$MODEL_PID" ]; then
    echo "⏳ Aguardando download do modelo... (verifique com: cat /tmp/dictate_install.log)"
    echo "   O ditado funcionará quando o download concluir (~2 minutos)."
fi
