"""HUD do ditado: visual (Orbe/Ondas/Barras) + status + texto, tudo em Cairo/Pango.

Sem widgets GTK dentro: o tema do sistema não interfere e a janela é
click-through, exceto a engrenagem (input shape só nela).
API usada pelo DictateThread: update_level, update_spectrum, update_status,
update_text, fade_out, dictate_thread, wants_spectrum.
"""
import math

import cairo
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo

from ..config import _debug_log, load_config
from .visuals import _icon_pixbuf, make_visual, rounded_rect

# classe CSS antiga (vinda do DictateThread) → estado do visual
STATES = {
    "status-calibrating": "calibrating",
    "status-waiting": "waiting",
    "status-listening": "listening",
    "status-transcribing": "transcribing",
    "status-success": "success",
    "status-error": "error",
}


def _status_text(text):
    text = text.strip()
    if text.endswith("..."):
        text = text[:-3] + "…"
    return text.rstrip("!")


class WhisperFlowOverlay(Gtk.Window):
    MAX_LINES = 3

    def __init__(self, config=None):
        Gtk.Window.__init__(self, type=Gtk.WindowType.POPUP)
        config = config or load_config()
        self.set_title("Dictate")
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_accept_focus(False)
        self.set_opacity(0.0)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
        self.set_app_paintable(True)

        self.visual = make_visual(config)
        self.wants_spectrum = config.get("overlay_style") == "bars"
        self.show_text = bool(config.get("overlay_show_text", True))
        position = config.get("overlay_position", "bottom")
        s = self.scale = self.visual.scale

        self.vw, self.vh = self.visual.size()
        self.text_w = 440 * s
        self.font_px = 14.5 * s
        self.line_h = self.font_px * 1.45
        self.text_pad = 12 * s
        text_max_h = (2 * self.text_pad + self.line_h * self.MAX_LINES) if self.show_text else 0
        status_h = 24 * s
        gap = 10 * s
        self.W = int(max(self.vw, self.text_w) + 48 * s)
        self.H = int(self.vh + status_h + (text_max_h + gap if self.show_text else 0) + 16 * s)
        self.set_size_request(self.W, self.H)
        self.resize(self.W, self.H)

        # Embaixo da tela o texto cresce para cima (acima do visual); no resto, para baixo.
        self.text_above = position == "bottom"
        self.cx = self.W / 2
        if self.text_above:
            self.text_anchor = text_max_h + 8 * s           # base do bloco de texto
            self.cy = self.text_anchor + gap + self.vh / 2
        else:
            self.cy = 8 * s + self.vh / 2
            self.text_anchor = self.cy + self.vh / 2 + status_h + gap  # topo do bloco de texto
        self.status_y = self.cy + self.vh / 2 + 4 * s

        # engrenagem (único ponto clicável)
        if config.get("overlay_style", "orb") == "orb":
            gx, gy = self.cx + self.vw / 2 - 30 * s, self.cy - self.vh / 2 + 18 * s
        else:
            gx, gy = self.cx + self.vw / 2 + 6 * s, self.cy - 8 * s
        self.gear = (int(gx), int(gy), int(16 * s) + 6, int(16 * s) + 6)
        self.gear_icon = _icon_pixbuf("settings", int(15 * s), stroke=1.8)

        self.status = "Iniciando…"
        self.text = ""
        self.final = False
        self.text_alpha = 0.0
        self.box_h = 0.0
        self._final_text = ""
        self.dictate_thread = None
        self._last_frame = None

        self._place(screen, position)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self._on_press)
        self.connect("draw", self._on_draw)
        self.connect("realize", self._on_realize)
        self.add_tick_callback(self._on_tick)
        self.fade_in()

    # ── posição e entrada ──────────────────────────────────────────
    def _place(self, screen, position):
        display = screen.get_display()
        try:
            _, x, y = display.get_default_seat().get_pointer().get_position()
            monitor = display.get_monitor_at_point(x, y)
        except Exception:
            monitor = display.get_primary_monitor()
        geo = monitor.get_geometry()
        x = geo.x + (geo.width - self.W) // 2
        if position == "top":
            y = geo.y + 48
        elif position == "center":
            y = geo.y + (geo.height - self.H) // 2
        else:
            y = geo.y + geo.height - self.H - 56
        self.move(x, y)

    def _on_realize(self, _w):
        # Click-through: só a engrenagem recebe clique.
        self.input_shape_combine_region(cairo.Region(cairo.RectangleInt(*self.gear)))

    def _on_press(self, _w, event):
        gx, gy, gw, gh = self.gear
        if gx <= event.x <= gx + gw and gy <= event.y <= gy + gh:
            self.on_settings_icon_clicked(None, event)
        return True

    def on_settings_icon_clicked(self, widget, event):
        _debug_log("Settings icon clicked: opening SettingsWindow")
        if self.dictate_thread:
            self.dictate_thread.cancelled = True
        from .settings import SettingsWindow  # import tardio: não pesa na abertura do overlay
        SettingsWindow(load_config()).show_all()
        self.destroy()

    # ── animação ───────────────────────────────────────────────────
    def _on_tick(self, widget, clock):
        now = clock.get_frame_time() / 1e6
        dt = min(now - self._last_frame, 0.05) if self._last_frame else 1 / 60
        self._last_frame = now
        self.visual.advance(dt)
        k = 1 - math.exp(-dt * 10)
        self.text_alpha += ((1.0 if self.text else 0.0) - self.text_alpha) * k
        self.box_h += (self._target_box_h() - self.box_h) * k
        self.queue_draw()
        return True

    def fade_in(self):
        self._fade_val = 0.0

        def _step():
            if self._fade_val < 1.0:
                self._fade_val += 0.10
                self.set_opacity(min(self._fade_val, 1.0))
                return True
            return False
        GLib.timeout_add(14, _step)

    def fade_out(self, callback):
        self._fade_val = self.get_opacity()

        def _step():
            if self._fade_val > 0.0:
                self._fade_val -= 0.10
                self.set_opacity(max(self._fade_val, 0.0))
                return True
            callback()
            return False
        GLib.timeout_add(14, _step)

    # ── API do DictateThread ───────────────────────────────────────
    def update_level(self, rms, threshold):
        # Fala típica fica ~4× acima do limiar calibrado.
        self.visual.set_level(min(rms / max(threshold * 4, 0.004), 1.0))

    def update_spectrum(self, bands):
        self.visual.set_bands(bands)

    def update_status(self, text, css_state=None):
        self.status = _status_text(text)
        if css_state in STATES:
            self.visual.set_state(STATES[css_state])

    def update_text(self, text, final=False):
        if not self.show_text:
            return
        self.text = text
        self.final = final
        if final:
            self._final_text = text

    def get_final_text(self):
        return self._final_text

    # ── desenho ────────────────────────────────────────────────────
    def _layout(self, cr, text, px, weight=Pango.Weight.NORMAL, width=None):
        layout = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription.from_string("Inter")
        fd.set_absolute_size(px * Pango.SCALE)
        fd.set_weight(weight)
        layout.set_font_description(fd)
        layout.set_alignment(Pango.Alignment.CENTER)
        if width:
            layout.set_width(int(width * Pango.SCALE))
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_text(text, -1)
        return layout

    def _visible_lines(self, cr):
        """Últimas MAX_LINES linhas do texto quebrado pelo Pango (quebra real, não por caracteres)."""
        if not self.text:
            return []
        layout = self._layout(cr, self.text, self.font_px, width=self.text_w - 2 * self.text_pad)
        raw = self.text.encode()
        lines = [raw[ln.start_index:ln.start_index + ln.length].decode(errors="ignore").strip()
                 for ln in layout.get_lines_readonly()]
        return [ln for ln in lines if ln][-self.MAX_LINES:]

    def _target_box_h(self):
        if not self.text:
            return 0.0
        n = getattr(self, "_n_lines", 1)
        return 2 * self.text_pad + self.line_h * n

    def _on_draw(self, _w, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        self.visual.draw(cr, self.cx, self.cy)

        # status
        if self.status:
            lay = self._layout(cr, self.status, 11.5 * self.scale, Pango.Weight.MEDIUM)
            w, h = lay.get_pixel_size()
            px, py = 9 * self.scale, 3 * self.scale
            # pílula escura: legível sobre qualquer coisa atrás
            rounded_rect(cr, self.cx - w / 2 - px, self.status_y - py, w + 2 * px, h + 2 * py, (h + 2 * py) / 2)
            cr.set_source_rgba(0.09, 0.09, 0.11, 0.78)
            cr.fill()
            cr.move_to(self.cx - w / 2, self.status_y)
            cr.set_source_rgba(1, 1, 1, 0.78)
            PangoCairo.show_layout(cr, lay)

        # engrenagem discreta
        gx, gy, gw, gh = self.gear
        Gdk.cairo_set_source_pixbuf(cr, self.gear_icon, gx + 3, gy + 3)
        cr.paint_with_alpha(0.35)

        self._draw_text(cr)
        return False

    def _draw_text(self, cr):
        lines = self._visible_lines(cr) if self.show_text else []
        self._n_lines = max(len(lines), 1)
        if self.box_h < 1 or self.text_alpha < 0.02:
            return
        a = self.text_alpha
        bw = self.text_w
        x = self.cx - bw / 2
        y = self.text_anchor - self.box_h if self.text_above else self.text_anchor
        rounded_rect(cr, x, y, bw, self.box_h, 16 * self.scale)
        cr.set_source_rgba(0.09, 0.09, 0.11, 0.86 * a)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.08 * a)
        cr.set_line_width(1)
        cr.stroke()

        cr.save()
        rounded_rect(cr, x, y, bw, self.box_h, 16 * self.scale)
        cr.clip()
        n = len(lines)
        # linhas antigas esmaecem; a atual é branca (parcial um pouco mais suave)
        alphas = [0.38, 0.62, 1.0][-n:] if n else []
        ty = y + self.text_pad + (self.box_h - 2 * self.text_pad - self.line_h * n) / 2
        for line, la in zip(lines, alphas):
            current = line is lines[-1]
            weight = Pango.Weight.MEDIUM if (current and self.final) else Pango.Weight.NORMAL
            lay = self._layout(cr, line, self.font_px, weight)
            w, h = lay.get_pixel_size()
            cr.move_to(self.cx - w / 2, ty + (self.line_h - h) / 2)
            cr.set_source_rgba(1, 1, 1, a * la * (1.0 if (self.final or not current) else 0.85))
            PangoCairo.show_layout(cr, lay)
            ty += self.line_h
        cr.restore()
