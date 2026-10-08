import os
import subprocess
import time

from .config import _debug_log


def get_display_server():
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if "wayland" in session_type:
        return "wayland"
    return "x11"


def _type_x11(text, active_win):
    cmd = ["xdotool", "type", "--clearmodifiers", "--delay", "2"]
    if active_win:
        cmd[2:2] = ["--window", active_win]
    subprocess.run(cmd + ["--", text], timeout=10)


def copy_text(text):
    """Só copia para a área de transferência (sem colar)."""
    cmd = ["wl-copy"] if get_display_server() == "wayland" else ["xclip", "-selection", "clipboard"]
    try:
        subprocess.run(cmd, input=text.encode("utf-8"), timeout=3)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _debug_log(f"Falha ao copiar: {e}")


def press_key(key):
    """Aperta uma tecla na janela em foco (ex.: "Return", "ctrl+Return" para enviar)."""
    try:
        if get_display_server() == "wayland":
            *mods, k = key.split("+")
            subprocess.run(["wtype", *[a for m in mods for a in ("-M", m)], "-k", k], timeout=3)
        else:
            subprocess.run(["xdotool", "key", "--clearmodifiers", key], timeout=3)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _debug_log(f"Falha ao apertar {key}: {e}")


def paste_text(text, active_win, method="ctrl+v"):
    """Cola na janela ativa. method: ctrl+v | ctrl+shift+v (terminais) | type (digita).

    Clipboard + atalho é instantâneo; se xclip/xdotool faltarem, digita o texto.
    """
    _debug_log(f"Colando ({method}) no {get_display_server()}...")
    if get_display_server() == "wayland":
        try:
            if method == "type":
                raise FileNotFoundError
            subprocess.run(["wl-copy"], input=text.encode("utf-8"), timeout=3)
            mods = ["-M", "ctrl"] + (["-M", "shift"] if method == "ctrl+shift+v" else [])
            subprocess.run(["wtype", *mods, "-k", "v"], timeout=3)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            try:
                subprocess.run(["wtype", "--", text], timeout=10)
            except Exception as e:
                _debug_log(f"Falha ao colar no Wayland: {e}")
        return

    try:
        if active_win:
            subprocess.run(["xdotool", "windowfocus", "--sync", active_win], timeout=2)
            time.sleep(0.1)
        if method == "type":
            _type_x11(text, active_win)
            return
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), timeout=3)
        subprocess.run(["xdotool", "key", "--clearmodifiers", method], timeout=3)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        try:
            _type_x11(text, active_win)
        except Exception as e:
            _debug_log(f"Falha ao colar no X11: {e}")
