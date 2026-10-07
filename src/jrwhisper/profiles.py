"""Perfis por aplicativo: a classe da janela ativa decide como colar e formatar."""
import re
import subprocess


def window_class(win_id):
    """WM_CLASS da janela (X11). None no Wayland ou se o xdotool falhar."""
    if not win_id:
        return None
    try:
        return subprocess.check_output(["xdotool", "getwindowclassname", str(win_id)],
                                       timeout=2, stderr=subprocess.DEVNULL).decode().strip() or None
    except Exception:
        return None


def match_profile(config, wm_class):
    """Primeiro perfil cuja regra (classes separadas por |) bate com a classe, sem diferenciar maiúsculas."""
    if not config.get("profiles_enabled") or not wm_class:
        return None
    for profile in config.get("profiles", []):
        pattern = profile.get("match", "").strip()
        if pattern and re.search(rf"(?<![\w-])(?:{pattern})(?![\w-])", wm_class, re.I):
            return profile
    return None


def effective_config(config, profile):
    """Config com as regras do perfil por cima (sem alterar o original)."""
    if not profile:
        return config
    return {**config,
            "enable_formatting": profile.get("formatting", True) and config.get("enable_formatting", True),
            "final_period": profile.get("final_period", True),
            "capitalize": profile.get("capitalize", True),
            "paste_method": profile.get("paste", "ctrl+v")}
