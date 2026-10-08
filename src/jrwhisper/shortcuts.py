"""Atalhos globais do Cinnamon via dconf (mesma regra do install.sh: nunca sobrescrever os do usuário)."""
import ast
import subprocess

KB = "/org/cinnamon/desktop/keybindings"


def _read(key):
    try:
        out = subprocess.check_output(["dconf", "read", key], timeout=2).decode().strip()
    except Exception:
        return None
    if not out:
        return None
    if out.startswith("@as "):
        out = out[4:]
    try:
        return ast.literal_eval(out)
    except (ValueError, SyntaxError):
        return out


def _write(key, value):
    subprocess.run(["dconf", "write", key, repr(value)], check=True, timeout=2)


def find_slot(command):
    """Slot customN cujo comando é exatamente `command`, ou None."""
    for slot in _read(f"{KB}/custom-list") or []:
        if _read(f"{KB}/custom-keybindings/{slot}/command") == command:
            return slot
    return None


def get_bindings(command):
    """Todos os atalhos do comando: o principal (o dos Ajustes) e extras, como a tecla do macropad."""
    slot = find_slot(command)
    return list(_read(f"{KB}/custom-keybindings/{slot}/binding") or []) if slot else []


def get_binding(command):
    return (get_bindings(command) or [None])[0]


def set_binding(name, command, accel):
    """Grava o atalho; cria slot novo no fim da lista se o comando ainda não tem um."""
    slots = list(_read(f"{KB}/custom-list") or [])
    slot = find_slot(command)
    if not slot:
        n = 0
        while f"custom{n}" in slots:
            n += 1
        slot = f"custom{n}"
        _write(f"{KB}/custom-keybindings/{slot}/name", name)
        _write(f"{KB}/custom-keybindings/{slot}/command", command)
        _write(f"{KB}/custom-keybindings/{slot}/binding", [accel])
        _write(f"{KB}/custom-list", slots + [slot])  # acrescenta no fim
    else:  # troca só o principal; extras (macropad) ficam
        _write(f"{KB}/custom-keybindings/{slot}/binding", [accel] + get_bindings(command)[1:])
    return slot


def remove_binding(command):
    slot = find_slot(command)
    if not slot:
        return
    slots = [s for s in (_read(f"{KB}/custom-list") or []) if s != slot]
    _write(f"{KB}/custom-list", slots)
    subprocess.run(["dconf", "reset", "-f", f"{KB}/custom-keybindings/{slot}/"], timeout=2)


def pretty(accel):
    """'<Super><Shift>d' → '⌘⇧D' no estilo macOS (Super mostrado como ❖)."""
    if not accel:
        return "Nenhum"
    symbols = {"<Super>": "❖", "<Shift>": "⇧", "<Control>": "Ctrl+", "<Primary>": "Ctrl+", "<Alt>": "Alt+"}
    out, rest = "", accel
    for tag, sym in symbols.items():
        if tag.lower() in rest.lower():
            out += sym
            idx = rest.lower().index(tag.lower())
            rest = rest[:idx] + rest[idx + len(tag):]
    return out + rest.upper()
