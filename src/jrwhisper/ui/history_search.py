"""Busca rápida no histórico, estilo Spotlight: digite, ↑↓ escolhe, Enter cola, Esc fecha."""
import subprocess

from gi.repository import Gtk, Gdk, GLib, Pango

from .. import history
from ..paste import copy_text, paste_text
from . import theme as t

CSS = b"""
window.spotlight { background-color: transparent; }
.spotlight-box {
    background-color: rgba(30, 30, 33, 0.97);
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.09);
}
.spotlight-entry, .spotlight-entry:focus {
    font-size: 20px;
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 6px 4px;
}
.spotlight-list, .spotlight-list row { background: transparent; }
.spotlight-list row { padding: 8px 14px; border-radius: 8px; margin: 0 8px; }
.spotlight-list row:selected { background-color: @accent; }
.spotlight-list row:selected label { color: #FFFFFF; }
.spotlight-hint { font-size: 11px; color: #98989D; }
"""


class HistorySearch(Gtk.Window):
    MAX = 8

    def __init__(self, config):
        Gtk.Window.__init__(self)
        self.config = config
        # Janela onde colar: a ativa antes desta abrir.
        try:
            self.target = subprocess.check_output(["xdotool", "getactivewindow"], timeout=2).decode().strip()
        except Exception:
            self.target = None
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_default_size(660, -1)
        screen = self.get_screen()
        if screen.get_rgba_visual() and screen.is_composited():
            self.set_visual(screen.get_rgba_visual())
        self.set_app_paintable(True)
        t.apply_theme(screen, config)
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(screen, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.get_style_context().add_class("spotlight")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("spotlight-box")
        box.set_margin_top(4)
        self.add(box)
        top = Gtk.Box(spacing=10)
        top.set_margin_start(18)
        top.set_margin_end(18)
        top.set_margin_top(12)
        top.pack_start(t.icon("search", 22, "#98989D"), False, False, 0)
        self.entry = Gtk.Entry(placeholder_text="Buscar ditados")
        self.entry.get_style_context().add_class("spotlight-entry")
        top.pack_start(self.entry, True, True, 0)
        box.pack_start(top, False, False, 0)

        self.list = Gtk.ListBox()
        self.list.get_style_context().add_class("spotlight-list")
        self.list.set_selection_mode(Gtk.SelectionMode.BROWSE)
        box.pack_start(self.list, False, False, 0)
        self.hint = t.label("", "spotlight-hint", xalign=0.5)
        self.hint.set_margin_bottom(10)
        box.pack_start(self.hint, False, False, 0)

        self.entry.connect("changed", lambda *_: self.refresh())
        self.connect("key-press-event", self.on_key)
        self.connect("focus-out-event", lambda *_: GLib.timeout_add(150, self._close_if_unfocused))
        self.connect("destroy", Gtk.main_quit)
        self.list.connect("row-activated", lambda _lb, row: self.choose(row))
        self.refresh()

    def _close_if_unfocused(self):
        if not self.is_active():
            self.destroy()
        return False

    def refresh(self):
        for r in self.list.get_children():
            self.list.remove(r)
        if not self.config.get("history_enabled"):
            self.hint.set_text("O histórico está desligado. Ative em Ajustes → Histórico.")
            return
        items = history.load(query=self.entry.get_text(), limit=self.MAX)
        self.hint.set_text("↑↓ escolher · Enter colar · Ctrl+C copiar · Esc fechar" if items else "Nenhum ditado encontrado")
        for rec in items:
            row = Gtk.ListBoxRow()
            row.text = rec.get("text", "")
            h = Gtk.Box(spacing=12)
            lbl = t.label(row.text.replace("\n", " "), "row-title")
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_max_width_chars(60)
            h.pack_start(lbl, True, True, 0)
            meta = history.when(rec.get("ts", 0)) + (f" · {rec['mode']}" if rec.get("mode") else "")
            h.pack_end(t.label(meta, "row-subtitle"), False, False, 0)
            row.add(h)
            self.list.add(row)
        self.list.show_all()
        first = self.list.get_row_at_index(0)
        if first:
            self.list.select_row(first)

    def selected_text(self):
        row = self.list.get_selected_row()
        return row.text if row else None

    def choose(self, row=None):
        text = row.text if row else self.selected_text()
        if not text:
            return
        self.hide()
        # Depois de esconder, o foco volta para a janela alvo; aí cola.
        GLib.timeout_add(120, lambda: (paste_text(text, self.target), self.destroy(), False)[2])

    def on_key(self, _w, ev):
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        if ev.keyval == Gdk.KEY_Escape:
            self.destroy()
        elif ev.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.choose()
        elif ev.keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            row = self.list.get_selected_row()
            idx = (row.get_index() if row else -1) + (1 if ev.keyval == Gdk.KEY_Down else -1)
            nxt = self.list.get_row_at_index(max(idx, 0))
            if nxt:
                self.list.select_row(nxt)
        elif ctrl and ev.keyval in (Gdk.KEY_c, Gdk.KEY_C) and not self.entry.get_selection_bounds():
            text = self.selected_text()
            if text:
                copy_text(text)  # xclip persiste depois que esta janela fecha
                self.hint.set_text("Copiado")
        else:
            return False
        return True
