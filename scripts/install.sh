#!/bin/bash
# JRWhisperLinux v3.0 — Installation Script
# Run: bash scripts/install.sh
set -e

echo "=== JRWhisperLinux v3.0 Install ==="

# 1. System dependencies
echo "[1/6] Installing system packages..."
sudo apt-get install -y -qq python3-gi python3-gi-cairo pulseaudio-utils xdotool xclip 2>/dev/null

# 2. Python venv with system site packages (needed for GTK3)
echo "[2/6] Creating Python venv..."
VENV="$HOME/.local/share/dictation-venv"
rm -rf "$VENV"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install -q faster-whisper numpy

# 3. Install main script (symlink — dev = production)
echo "[3/6] Installing dictate..."
ln -sf "$PWD/src/dictate" "$HOME/.local/bin/dictate"
chmod +x "$HOME/.local/bin/dictate"

# 4. Default config
echo "[4/6] Creating default config..."
mkdir -p "$HOME/.config/dictate"
cp config/config.json "$HOME/.config/dictate/config.json"

# 5. Cinnamon keyboard shortcut (Super+Shift+V)
echo "[5/6] Setting up keyboard shortcut (Super+Shift+V)..."
dconf write /org/cinnamon/desktop/keybindings/custom-list "['custom0']"
dconf write /org/cinnamon/desktop/keybindings/custom-keybindings/custom0/name "'Dictate'"
dconf write /org/cinnamon/desktop/keybindings/custom-keybindings/custom0/command "'$HOME/.local/bin/dictate'"
dconf write /org/cinnamon/desktop/keybindings/custom-keybindings/custom0/binding "['<Super><Shift>v']"

# 6. Systemd user service for Daemon Mode
echo "[6/6] Setting up systemd user service for Daemon Mode..."
mkdir -p "$HOME/.config/systemd/user"
cp config/dictate-daemon.service "$HOME/.config/systemd/user/dictate-daemon.service"
systemctl --user daemon-reload
systemctl --user enable --now dictate-daemon.service

echo ""
echo "=== Installation Complete ==="
echo "  Script:   $HOME/.local/bin/dictate"
echo "  Config:   $HOME/.config/dictate/config.json"
echo "  Venv:     $VENV"
echo "  Shortcut: Super+Shift+V"
echo "  Daemon:   Enabled via systemd user service"
echo ""
echo "Downloading/pre-caching model (medium, ~1.5GB) — this may take a few minutes..."
"$VENV/bin/python3" -c "
from faster_whisper import WhisperModel
WhisperModel('medium', device='cpu', compute_type='int8')
print('Model ready!')
"
echo ""
echo "Test: Press Super+Shift+V and speak!"
