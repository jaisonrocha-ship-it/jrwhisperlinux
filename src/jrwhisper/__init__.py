"""JRWhisperLinux — ditado por voz local (faster-whisper + GTK3)."""
import gi

__version__ = "4.0"

# Antes de qualquer `from gi.repository import Gtk` nos submódulos.
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('GdkPixbuf', '2.0')
