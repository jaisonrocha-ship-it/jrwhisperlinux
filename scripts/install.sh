#!/bin/bash
# JRWhisperLinux — One-Line Installer
# curl -fsSL https://jrwhisper.jasonrock.dev/install.sh | bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}->${NC} $1"; }
ok()    { echo -e "${GREEN}ok${NC} $1"; }
err()   { echo -e "${RED}erro${NC} $1"; exit 1; }

echo ""
echo "JRWhisperLinux Installer"
echo "Ditado por voz para Linux"
echo ""

command -v python3 >/dev/null 2>&1 || err "Python 3 nao encontrado. Instale com: sudo apt install python3"
command -v apt-get >/dev/null 2>&1 || err "Este instalador requer APT (Debian/Ubuntu/Mint). Para outras distros: https://jrwhisper.jasonrock.dev"

info "Instalando dependencias do sistema..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    python3-venv python3-pip \
    pulseaudio-utils \
    xdotool xclip wtype wl-clipboard \
    ffmpeg
ok "Pacotes de sistema instalados"

if [ ! -f "./src/dictate" ]; then
    REPO_DIR="$HOME/.local/share/jrwhisperlinux"
    if [ -d "$REPO_DIR" ]; then
        info "Repositorio ja existe, atualizando..."
        git -C "$REPO_DIR" pull --ff-only
    else
        info "Baixando JRWhisperLinux..."
        git clone --depth 1 https://github.com/jaisonrocha-ship-it/jrwhisperlinux.git "$REPO_DIR"
    fi
    cd "$REPO_DIR"
fi
ok "Codigo fonte pronto"

VENV="$HOME/.local/share/dictation-venv"
info "Criando ambiente virtual Python..."
rm -rf "$VENV"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q faster-whisper numpy
ok "Ambiente Python configurado"

info "Instalando comando dictate..."
mkdir -p "$HOME/.local/bin"
# Symlink, não cópia: src/dictate carrega o pacote src/jrwhisper/ ao lado dele.
chmod +x "$PWD/src/dictate"
ln -sfn "$PWD/src/dictate" "$HOME/.local/bin/dictate"
ok "Comando dictate instalado"

mkdir -p "$HOME/.config/dictate"
if [ ! -f "$HOME/.config/dictate/config.json" ]; then
    # Sem config.json o dictate usa DEFAULT_CONFIG; o exemplo so facilita a edicao.
    cp "$PWD/config/config.example.json" "$HOME/.config/dictate/config.json"
    ok "Configuracao criada"
else
    ok "Configuracao ja existe — mantida"
fi

# Inter variável (OFL): a UI usa pesos 400–700; muitas distros só têm o Regular.
mkdir -p "$HOME/.local/share/fonts"
cp "$PWD/assets/fonts/InterVariable.ttf" "$HOME/.local/share/fonts/"
fc-cache -f "$HOME/.local/share/fonts" >/dev/null 2>&1 || true
ok "Fonte Inter instalada"

if [ -f "$PWD/config/bd.rnnn" ]; then
    cp "$PWD/config/bd.rnnn" "$HOME/.config/dictate/bd.rnnn"
    ok "Modelo RNNoise instalado"
else
    info "Modelo RNNoise (bd.rnnn) nao encontrado no repositorio"
fi

if command -v cinnamon >/dev/null 2>&1 || pgrep -x cinnamon >/dev/null 2>&1; then
    KB=/org/cinnamon/desktop/keybindings
    LIST=$(dconf read "$KB/custom-list")
    SLOT=""
    for id in $(echo "$LIST" | grep -o "custom[0-9]*"); do
        case "$(dconf read "$KB/custom-keybindings/$id/command")" in
            *"/dictate'") SLOT=$id; break ;;
        esac
    done
    if [ -n "$SLOT" ]; then
        ok "Atalho existente mantido: $(dconf read "$KB/custom-keybindings/$SLOT/binding")"
    else
        info "Configurando atalho Super+Shift+V (Cinnamon)..."
        n=0; while echo "$LIST" | grep -q "'custom$n'"; do n=$((n+1)); done
        SLOT="custom$n"
        # Acrescenta ao final: nunca sobrescreve atalhos do usuario.
        case "$LIST" in
            ""|"@as []") NEW="['$SLOT']" ;;
            *) NEW="${LIST%]}, '$SLOT']" ;;
        esac
        dconf write "$KB/custom-keybindings/$SLOT/name" "'Dictate'"
        dconf write "$KB/custom-keybindings/$SLOT/command" "'$HOME/.local/bin/dictate'"
        dconf write "$KB/custom-keybindings/$SLOT/binding" "['<Super><Shift>v']"
        dconf write "$KB/custom-list" "$NEW"
        ok "Atalho Super+Shift+V configurado"
    fi
else
    info "Cinnamon nao detectado — configure o atalho manualmente para: $HOME/.local/bin/dictate"
fi

info "Configurando daemon (carrega modelo no boot para latencia zero)..."
mkdir -p "$HOME/.config/systemd/user"
cp "$PWD/config/dictate-daemon.service" "$HOME/.config/systemd/user/dictate-daemon.service"
systemctl --user daemon-reload
systemctl --user enable --now dictate-daemon.service 2>/dev/null || true
ok "Daemon configurado"

CONFIG_JSON="$HOME/.config/dictate/config.json"
info "Pre-carregando modelo Whisper em background..."
nohup "$VENV/bin/python3" -c "
import json, os, sys
sys.stdout = open('/tmp/dictate_install.log', 'w')
from faster_whisper import WhisperModel
model = 'medium'
cfg = os.path.expanduser('$CONFIG_JSON')
if os.path.isfile(cfg):
    with open(cfg) as f:
        model = json.load(f).get('model', model)
WhisperModel(model, device='cpu', compute_type='int8')
print('OK', model)
" >/dev/null 2>&1 &
MODEL_PID=$!
ok "Download do modelo iniciado em background (PID $MODEL_PID)"

echo ""
echo "JRWhisperLinux instalado."
echo "  Super+Shift+V  — ditar"
echo "  dictate --help — comandos"
echo "  https://jrwhisper.jasonrock.dev"
echo ""
if [ -n "$MODEL_PID" ]; then
    echo "Aguardando download do modelo (cat /tmp/dictate_install.log)."
    echo "O ditado funciona quando o download concluir."
fi
