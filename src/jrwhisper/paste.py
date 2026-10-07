import os


def get_display_server():
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if "wayland" in session_type:
        return "wayland"
    return "x11"
