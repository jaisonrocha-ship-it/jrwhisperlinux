#!/bin/sh
# Lançador do JRWhisper, instalado em ~/.local/bin/dictate (atalhos, menu e o serviço chamam este).
# Guarda o caminho do repositório; se ele for movido ou renomeado, procura de novo em ~ e se corrige.
# Executa o src/dictate do repositório: mudanças no código valem na hora, sem reinstalar.
STATE="${XDG_CONFIG_HOME:-$HOME/.config}/dictate/repo"

repo=$(cat "$STATE" 2>/dev/null)
if [ ! -f "$repo/src/jrwhisper/cli.py" ]; then
    # ponytail: busca em ~ até 6 níveis só quando o caminho salvo some; cópias de trabalho
    # (worktrees, lixeira, caches) ficam de fora para não "achar" a errada
    found=$(find "$HOME" -maxdepth 6 \
        \( -name .cache -o -name Trash -o -name node_modules -o -name worktrees -o -name .claude -o -name .git \) -prune \
        -o -path '*/src/jrwhisper/cli.py' -print 2>/dev/null | head -1)
    repo=${found%/src/jrwhisper/cli.py}
    if [ -z "$found" ]; then
        msg="Repositório não encontrado em $HOME. Rode scripts/install.sh na pasta nova."
        notify-send -a JRWhisper -i dialog-error "JRWhisper" "$msg" 2>/dev/null
        echo "JRWhisper: $msg" >&2
        exit 1
    fi
    mkdir -p "$(dirname "$STATE")"
    printf '%s\n' "$repo" > "$STATE"
fi
exec "$repo/src/dictate" "$@"
