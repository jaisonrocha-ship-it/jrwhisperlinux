"""JRWhisperLinux — ditado por voz local (faster-whisper + GTK3)."""
import gi

# Antes de qualquer `from gi.repository import Gtk` nos submódulos.
gi.require_version('Gtk', '3.0')
gi.require_version('Pango', '1.0')
