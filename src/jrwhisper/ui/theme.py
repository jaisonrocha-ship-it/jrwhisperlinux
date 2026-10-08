"""Linguagem visual estilo macOS (modo escuro): tokens, CSS, ícones e linhas de ajuste.

Tudo que é janela (Configurações, Calibração, Histórico) monta a UI com estes
helpers; o overlay usa só ACCENTS/accent_pair (desenha com Cairo).
"""
import math
import os

import cairo
from gi.repository import GObject, Gtk, Gdk, GdkPixbuf

from ..config import load_config

# <repo>/assets/icons (realpath: ~/.local/bin/dictate é symlink)
APP_ICON = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "assets", "icons", "jrwhisper.svg")

# Acento: (cor sólida da UI, início do gradiente, fim do gradiente).
# O gradiente tem contraste de matiz (ex.: azul → magenta) para o orbe ter profundidade.
ACCENTS = {
    "indigo": ("#7C6CFF", "#3D6BFF", "#D45CFF"),
    "cyan": ("#2EC8FF", "#2FE6FF", "#3A55FF"),
    "amber": ("#F59E0B", "#FFC83A", "#FF4D3A"),
    "green": ("#30D158", "#7CF08F", "#00A8C8"),
    "pink": ("#FF5FA2", "#FF7AB8", "#7C5CFF"),
}
ACCENT_LABELS = {"indigo": "Índigo", "cyan": "Ciano", "amber": "Âmbar", "green": "Verde", "pink": "Rosa"}

SUCCESS = "#30D158"
WARNING = "#FFC83C"
DANGER = "#FF6B5E"


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _shift(color, factor):
    r, g, b = hex_to_rgb(color)
    mix = (lambda c: c + (1 - c) * factor) if factor > 0 else (lambda c: c * (1 + factor))
    return "#{:02X}{:02X}{:02X}".format(*(int(mix(c) * 255) for c in (r, g, b)))


def ui_accent(config):
    if config.get("accent") == "custom" and config.get("accent_custom"):
        return config["accent_custom"]
    return ACCENTS.get(config.get("accent", "indigo"), ACCENTS["indigo"])[0]


def accent_pair(config):
    """Gradiente (início, fim) do acento; cor livre vira clara → escura."""
    if config.get("accent") == "custom" and config.get("accent_custom"):
        c = config["accent_custom"]
        return _shift(c, 0.35), _shift(c, -0.35)
    return ACCENTS.get(config.get("accent", "indigo"), ACCENTS["indigo"])[1:]


CSS_TEMPLATE = """
@define-color accent {accent};
@define-color bg #1C1C1E;
@define-color sidebar #161618;
@define-color card #2C2C2E;
@define-color control #3A3A3C;
@define-color text #F5F5F7;
@define-color text2 #98989D;
@define-color hairline rgba(255, 255, 255, 0.07);

window {{
    background-color: @bg;
    color: @text;
    font-family: 'Inter', sans-serif;
    font-size: 13px;
}}
label {{ color: @text; }}

/* ── Sidebar ─────────────────────────────────────── */
.sidebar, .sidebar list {{ background-color: @sidebar; border: none; }}
.sidebar list {{ padding: 10px 0; }}
.sidebar row {{
    padding: 5px 8px;
    margin: 1px 10px;
    border-radius: 7px;
    background: transparent;
    outline: none;
}}
.sidebar row:hover {{ background-color: rgba(255, 255, 255, 0.04); }}
.sidebar row:selected {{ background-color: @accent; }}
.sidebar row:selected label {{ color: #FFFFFF; }}
.sidebar-label {{ font-size: 13px; font-weight: 500; }}
.sidebar-sep {{ background-color: @hairline; min-width: 1px; }}

/* ── Páginas e grupos (inset grouped, estilo Ajustes) ── */
.page {{ background-color: @bg; }}
.page-title {{ font-size: 22px; font-weight: 700; color: @text; }}
.page-subtitle {{ font-size: 12px; color: @text2; }}
.group-title {{ font-size: 12px; font-weight: 600; color: @text2; }}
.group-footer {{ font-size: 11px; color: @text2; }}
list.group {{
    background-color: @card;
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.04);
}}
list.group row {{
    padding: 9px 14px;
    background: transparent;
    border-bottom: 1px solid @hairline;
    outline: none;
}}
list.group row:last-child {{ border-bottom: none; }}
list.group row:hover, list.group row:selected {{ background: transparent; }}
.row-title {{ font-size: 13px; color: @text; }}
.row-subtitle {{ font-size: 11px; color: @text2; }}
.dim {{ color: @text2; }}

/* ── Controles ───────────────────────────────────── */
button {{
    background-image: none;
    background-color: @control;
    color: @text;
    border: none;
    border-radius: 6px;
    padding: 4px 12px;
    box-shadow: none;
    font-weight: 500;
}}
button:hover {{ background-color: #48484A; }}
button:active {{ background-color: #2C2C2E; }}
button:disabled {{ opacity: 0.4; }}
.btn-primary {{
    background-color: @accent;
    color: #FFFFFF;
    border-radius: 999px;
    padding: 5px 18px;
    font-weight: 600;
}}
.btn-primary:hover {{ background-color: shade(@accent, 1.12); }}
.btn-secondary {{ background-color: @control; border-radius: 999px; padding: 5px 16px; }}
.btn-danger, .btn-danger label {{ color: {danger}; }}
.popup-choice {{ padding: 3px 8px 3px 12px; min-width: 120px; }}
.btn-flat {{ background: transparent; color: @accent; padding: 2px 6px; }}
.btn-flat:hover {{ background: rgba(255, 255, 255, 0.05); }}

switch {{
    background-color: @control;
    border: none;
    border-radius: 999px;
    min-width: 38px;
    min-height: 22px;
    background-image: none;
}}
switch:checked {{ background-color: @accent; }}
switch slider {{
    background-color: #FFFFFF;
    border: none;
    border-radius: 999px;
    min-width: 20px;
    min-height: 20px;
    margin: 1px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
}}
switch image {{ color: transparent; }}

scale trough {{ background-color: @control; min-height: 4px; border-radius: 2px; border: none; }}
scale highlight {{ background-color: @accent; border-radius: 2px; border: none; }}
scale slider {{
    background-color: #FFFFFF;
    min-width: 18px;
    min-height: 18px;
    border-radius: 999px;
    border: none;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
}}
scale value {{ color: @text2; font-size: 11px; }}

combobox button, combobox box {{ background-color: @control; border-radius: 6px; padding: 2px 8px; }}
combobox arrow {{ color: @text2; }}
menu, .menu, .context-menu {{ background-color: #2C2C2E; color: @text; border-radius: 8px; padding: 4px; }}
menuitem {{ padding: 4px 10px; border-radius: 4px; }}
menuitem:hover {{ background-color: @accent; color: #FFFFFF; }}

entry, textview text, textview {{
    background-color: #232325;
    color: @text;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 5px 8px;
    caret-color: @accent;
}}
entry:focus {{ border-color: @accent; box-shadow: 0 0 0 3px alpha(@accent, 0.30); }}
entry selection, textview text selection {{ background-color: alpha(@accent, 0.5); }}

treeview, treeview.view {{ background-color: @card; color: @text; }}
treeview.view:selected {{ background-color: alpha(@accent, 0.6); }}
treeview header button {{ background-color: @card; color: @text2; border-radius: 0; font-size: 11px; }}

progressbar trough {{ background-color: @control; border: none; border-radius: 3px; min-height: 6px; }}
progressbar progress {{ background-color: @accent; border: none; border-radius: 3px; min-height: 6px; }}

scrollbar {{ background: transparent; border: none; }}
scrollbar slider {{ background-color: rgba(255, 255, 255, 0.18); border-radius: 999px; min-width: 6px; min-height: 6px; border: none; }}


messagedialog, messagedialog .dialog-action-area {{ background-color: @card; }}

.segmented {{ background-color: @control; border-radius: 7px; padding: 2px; }}
.segmented button {{
    background: transparent;
    border-radius: 5px;
    padding: 2px 12px;
    min-height: 20px;
    color: @text;
    font-weight: 500;
}}
.segmented button:checked {{ background-color: #636366; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35); }}
/* compacto: o tema do sistema infla campos */
entry {{ min-height: 24px; padding-top: 3px; padding-bottom: 3px; }}
list.group row switch {{ margin-top: 0; margin-bottom: 0; }}
.keycap {{ background-color: @control; border-radius: 6px; padding: 3px 10px; font-weight: 600; }}
"""

_provider = None


def build_css(config):
    return CSS_TEMPLATE.format(accent=ui_accent(config), danger=DANGER)


def apply_theme(screen, config=None):
    """Aplica (ou reaplica, ao trocar o acento) o tema em todas as janelas da tela."""
    global _provider
    css = build_css(config if config is not None else load_config()).encode()
    if _provider is None:
        try:  # ícone de todas as janelas (dock/Alt+Tab); 256 px fica nítido com zoom do Plank
            Gtk.Window.set_default_icon(GdkPixbuf.Pixbuf.new_from_file_at_size(APP_ICON, 256, 256))
        except Exception:
            pass
        _provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(screen, _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _provider.load_from_data(css)


# ── Ícones (Lucide, ISC) ────────────────────────────────────────────
ICONS = {
    "settings": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "palette": '<circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>',
    "mic": '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/>',
    "audio-lines": '<path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/>',
    "type": '<polyline points="4 7 4 4 20 4 20 7"/><line x1="9" x2="15" y1="20" y2="20"/><line x1="12" x2="12" y1="4" y2="20"/>',
    "sparkles": '<path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/>',
    "app-window": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M10 4v4"/><path d="M2 8h20"/><path d="M6 4v4"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    "keyboard": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="M6 8h.01"/><path d="M10 8h.01"/><path d="M14 8h.01"/><path d="M18 8h.01"/><path d="M8 12h.01"/><path d="M12 12h.01"/><path d="M16 12h.01"/><path d="M7 16h10"/>',
    "sliders": '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "clipboard": '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "chevrons": '<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>',
}


def _svg_pixbuf(svg, size):
    loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
    loader.set_size(size, size)
    loader.write(svg.encode())
    loader.close()
    return loader.get_pixbuf()


def icon_pixbuf(name, size, color="#F5F5F7", stroke=2.0):
    """Ícone Lucide como pixbuf (o overlay desenha em Cairo; as janelas usam icon())."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    return _svg_pixbuf(svg, size)


def icon(name, size=16, color="#F5F5F7", stroke=2.0):
    return Gtk.Image.new_from_pixbuf(icon_pixbuf(name, size, color, stroke))


def app_icon(size=32):
    """Ícone do app (o mesmo da dock), nítido em telas HiDPI."""
    scale = Gdk.Screen.get_default().get_monitor_scale_factor(0) or 1
    pb = GdkPixbuf.Pixbuf.new_from_file_at_size(APP_ICON, size * scale, size * scale)
    return Gtk.Image.new_from_surface(Gdk.cairo_surface_create_from_pixbuf(pb, scale, None))


def tile_icon(name, color, size=22):
    """Ícone branco num quadrado arredondado colorido, como na sidebar dos Ajustes do macOS."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           f'<rect width="24" height="24" rx="6" fill="{color}"/>'
           f'<g transform="translate(5 5) scale(0.5833)" fill="none" stroke="#FFFFFF" stroke-width="2.3" '
           f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g></svg>')
    return Gtk.Image.new_from_pixbuf(_svg_pixbuf(svg, size))


# ── Componentes de página (inset grouped) ──────────────────────────
def label(text, cls=None, xalign=0.0, wrap=False):
    lbl = Gtk.Label(label=text, xalign=xalign)
    if cls:
        lbl.get_style_context().add_class(cls)
    if wrap:
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(60)
    return lbl


def page(title, subtitle=None):
    """Página rolável com título grande. Devolve (widget_raiz, caixa_de_conteúdo)."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(26 if side in ("start", "end") else 22)
    head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
    head.pack_start(label(title, "page-title"), False, False, 0)
    if subtitle:
        head.pack_start(label(subtitle, "page-subtitle", wrap=True), False, False, 0)
    box.pack_start(head, False, False, 0)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("page")
    scroll.add(box)
    return scroll, box


def group(parent, title=None, footer=None):
    """Cartão arredondado com linhas separadas por hairline. Devolve o ListBox."""
    wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    if title:
        t = label(title, "group-title")
        t.set_margin_start(12)
        wrap.pack_start(t, False, False, 0)
    lb = Gtk.ListBox()
    lb.set_selection_mode(Gtk.SelectionMode.NONE)
    lb.get_style_context().add_class("group")
    wrap.pack_start(lb, False, False, 0)
    if footer:
        f = label(footer, "group-footer", wrap=True)
        f.set_margin_start(12)
        f.set_margin_end(12)
        wrap.pack_start(f, False, False, 0)
    parent.pack_start(wrap, False, False, 0)
    return lb


def row(lb, title, subtitle=None, control=None):
    """Título (e subtítulo) à esquerda, controle à direita. Devolve o ListBoxRow."""
    r = Gtk.ListBoxRow()
    r.set_activatable(False)
    h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
    texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    texts.set_valign(Gtk.Align.CENTER)
    texts.pack_start(label(title, "row-title"), False, False, 0)
    if subtitle:
        r.subtitle = label(subtitle, "row-subtitle", wrap=True)
        texts.pack_start(r.subtitle, False, False, 0)
    h.pack_start(texts, True, True, 0)
    if control is not None:
        control.set_valign(Gtk.Align.CENTER)
        h.pack_end(control, False, False, 0)
    r.add(h)
    lb.add(r)
    return r


def switch_row(lb, title, subtitle, active, on_change):
    sw = Gtk.Switch()
    sw.set_valign(Gtk.Align.CENTER)
    sw.set_active(bool(active))
    sw.connect("notify::active", lambda s, _p: on_change(s.get_active()))
    row(lb, title, subtitle, sw)
    return sw


class PopupChoice(Gtk.Button):
    """Botão popup do macOS (texto + chevron → menu). API compatível com ComboBoxText.

    O ComboBox nativo herda 44 px de altura do tema do sistema; este segue o nosso CSS.
    """
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self):
        super().__init__()
        self.get_style_context().add_class("popup-choice")
        self._items = []
        self._active = None
        box = Gtk.Box(spacing=8)
        self._label = Gtk.Label(xalign=0)
        self._label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        self._label.set_max_width_chars(34)
        box.pack_start(self._label, True, True, 0)
        box.pack_end(icon("chevrons", 12, "#98989D"), False, False, 0)
        self.add(box)
        self.connect("clicked", self._popup)

    def append(self, oid, olabel):
        self._items.append((oid, olabel))

    def set_active_id(self, oid):
        for i, l in self._items:
            if i == oid:
                self._active = oid
                self._label.set_text(l)
                return True
        return False

    def set_active(self, index):
        if 0 <= index < len(self._items):
            self.set_active_id(self._items[index][0])

    def get_active_id(self):
        return self._active

    def _popup(self, _b):
        menu = Gtk.Menu()
        for oid, olabel in self._items:
            item = Gtk.MenuItem(label=("✓  " if oid == self._active else "    ") + olabel)
            item.connect("activate", lambda _i, o=oid: self._choose(o))
            menu.append(item)
        menu.show_all()
        menu.attach_to_widget(self, None)
        menu.popup_at_widget(self, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def _choose(self, oid):
        if oid != self._active:
            self.set_active_id(oid)
            self.emit("changed")


def choice_row(lb, title, subtitle, options, active_id, on_change):
    combo = PopupChoice()
    for oid, olabel in options:
        combo.append(oid, olabel)
    if active_id not in [o[0] for o in options] and active_id is not None:
        combo.append(active_id, str(active_id))
    combo.set_active_id(active_id)
    combo.connect("changed", lambda c: c.get_active_id() is not None and on_change(c.get_active_id()))
    row(lb, title, subtitle, combo)
    return combo


def slider_row(lb, title, subtitle, lo, hi, step, value, fmt, on_change, width=200):
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
    scale.set_draw_value(False)
    scale.set_value(value)
    scale.set_size_request(width, -1)
    val = label(fmt(value), "dim", xalign=1.0)
    val.set_width_chars(6)

    def changed(s):
        val.set_text(fmt(s.get_value()))
        on_change(s.get_value())
    scale.connect("value-changed", changed)
    box.pack_start(scale, False, False, 0)
    box.pack_start(val, False, False, 0)
    row(lb, title, subtitle, box)
    return scale


def entry_row(lb, title, subtitle, text, on_change, secret=False, width=240, placeholder=""):
    e = Gtk.Entry()
    e.set_text(text or "")
    e.set_visibility(not secret)
    e.set_placeholder_text(placeholder)
    e.set_size_request(width, -1)
    e.connect("changed", lambda w: on_change(w.get_text()))
    row(lb, title, subtitle, e)
    return e


def button_row(lb, title, subtitle, button_label, on_click, cls=None):
    b = Gtk.Button(label=button_label)
    if cls:
        b.get_style_context().add_class(cls)
    b.connect("clicked", lambda _b: on_click())
    row(lb, title, subtitle, b)
    return b


def segmented(options, active, on_change):
    """Controle segmentado do macOS: [(id, rótulo), ...]."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
    box.get_style_context().add_class("segmented")
    first = None
    for oid, olabel in options:
        b = Gtk.RadioButton.new_with_label_from_widget(first, olabel)
        b.set_mode(False)  # aparência de botão, sem bolinha de rádio
        first = first or b
        b.set_active(oid == active)
        b.connect("toggled", lambda w, i=oid: w.get_active() and on_change(i))
        box.pack_start(b, False, False, 0)
    box.set_valign(Gtk.Align.CENTER)
    return box


class Swatch(Gtk.DrawingArea):
    """Bolinha de cor desenhada (botões GTK herdam tamanho mínimo do tema do sistema)."""
    SIZE = 24

    def __init__(self, colors, tooltip, on_click):
        super().__init__()
        self.colors = [hex_to_rgb(c) for c in colors]
        self.selected = False
        self.set_size_request(self.SIZE, self.SIZE)
        self.set_valign(Gtk.Align.CENTER)
        self.set_tooltip_text(tooltip)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", lambda *_: on_click())
        self.connect("realize", lambda w: w.get_window().set_cursor(
            Gdk.Cursor.new_from_name(w.get_display(), "pointer")))
        self.connect("draw", self._draw)

    def set_selected(self, selected):
        self.selected = selected
        self.queue_draw()

    def _draw(self, _w, cr):
        c = self.SIZE / 2
        grad = cairo.LinearGradient(0, 0, self.SIZE, self.SIZE)
        for i, rgb in enumerate(self.colors):
            grad.add_color_stop_rgb(i / max(len(self.colors) - 1, 1), *rgb)
        cr.set_source(grad)
        cr.arc(c, c, c - (4 if self.selected else 2), 0, 2 * math.pi)
        cr.fill()
        if self.selected:
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.set_line_width(1.6)
            cr.arc(c, c, c - 1, 0, 2 * math.pi)
            cr.stroke()


def accent_picker(current, on_change, custom_color=None):
    """Bolinhas de acento como no macOS; a última abre o seletor de cor livre."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    swatches = {}

    def select(key):
        for k, sw in swatches.items():
            sw.set_selected(k == key)

    for key, (_ui, *pair) in ACCENTS.items():
        swatches[key] = Swatch(pair, ACCENT_LABELS[key], lambda k=key: (select(k), on_change(k, None)))
        box.pack_start(swatches[key], False, False, 0)

    def pick():
        dlg = Gtk.ColorChooserDialog(title="Cor de destaque", transient_for=box.get_toplevel())
        dlg.set_use_alpha(False)
        if custom_color:
            rgba = Gdk.RGBA()
            rgba.parse(custom_color)
            dlg.set_rgba(rgba)
        if dlg.run() == Gtk.ResponseType.OK:
            c = dlg.get_rgba()
            hexc = "#{:02X}{:02X}{:02X}".format(int(c.red * 255), int(c.green * 255), int(c.blue * 255))
            select("custom")
            on_change("custom", hexc)
        dlg.destroy()

    rainbow = ["#FF5E57", "#FFC83C", "#30D158", "#2EC8FF", "#A45CFF"]
    swatches["custom"] = Swatch(rainbow, "Cor personalizada…", pick)
    box.pack_start(swatches["custom"], False, False, 0)
    select(current)
    return box
