import cairo
import math
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

from ..config import _debug_log, load_config
from ..textproc import wrap_text_to_lines
from .settings import SettingsWindow


OVERLAY_BG = (10/255, 10/255, 12/255, 0.62)

CSS = """
.overlay {
    background-color: rgba(10, 10, 12, 0.62);
    border: none;
    border-radius: 16px;
    padding: 16px;
    box-shadow: inset 0 1px 0 0 rgba(255, 255, 255, 0.12),
                inset 0 -1px 0 0 rgba(255, 255, 255, 0.05);
}
.status-label {
    color: rgba(255, 255, 255, 0.65);
    font-size: 10px;
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    letter-spacing: 0.1em;
}
.status-calibrating {
    color: rgba(255, 200, 60, 0.8);
}
.status-waiting {
    color: rgba(255, 255, 255, 0.65);
}
.status-listening {
    color: rgba(100, 220, 255, 0.9);
}
.status-transcribing {
    color: rgba(200, 170, 255, 0.9);
}
.status-success {
    color: rgba(100, 255, 160, 0.9);
}
.status-error {
    color: rgba(255, 120, 100, 0.85);
}
.text-display {
    color: rgba(255, 255, 255, 0.95);
    font-size: 13.5px;
    font-family: 'Inter', sans-serif;
    font-weight: 400;
}
.partial-text {
    color: rgba(255, 255, 255, 0.6);
    font-style: italic;
}
.final-text {
    color: #FFFFFF;
    font-weight: 600;
}
"""


class SiriWaveform(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.set_size_request(410, 42)
        self.phase = 0.0
        self.amplitude = 0.02
        self.target_amplitude = 0.02
        self.set_margin_bottom(10)
        

        self.connect("draw", self.on_draw)
        

        GLib.timeout_add(16, self._tick)

    def _tick(self):
        self.phase += 0.15

        self.amplitude = self.amplitude * 0.82 + self.target_amplitude * 0.18
        self.queue_draw()
        return True

    def set_rms(self, rms, threshold):

        max_possible = max(threshold * 4, 0.01)
        val = min(rms / max_possible, 1.0)

        self.target_amplitude = max(val * 0.9, 0.04)

    def on_draw(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        mid_y = height / 2.0
        

        cr.set_source_rgba(*OVERLAY_BG)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        


        waves = [

            (0.012, 0.0, 1.0, 0.85, 2.5, "main"),
            (0.022, 1.8, 0.6, 0.45, 1.5, "electric"),
            (0.008, -1.5, 0.35, 0.20, 1.0, "warm")
        ]
        
        for freq, phase_offset, amp_mult, opacity, line_w, grad_type in waves:

            gradient = cairo.LinearGradient(0, 0, width, 0)
            
            if grad_type == "main":

                shift = 0.05 * math.sin(self.phase * 0.3)
                gradient.add_color_stop_rgba(0.0, 0.0, 0.48, 1.0, opacity)
                gradient.add_color_stop_rgba(0.5 + shift, 0.69, 0.32, 0.87, opacity)
                gradient.add_color_stop_rgba(1.0, 1.0, 0.18, 0.33, opacity)
            elif grad_type == "electric":

                shift = 0.07 * math.cos(self.phase * 0.4)
                gradient.add_color_stop_rgba(0.0, 0.0, 0.95, 1.0, opacity)
                gradient.add_color_stop_rgba(0.4 + shift, 0.0, 0.72, 0.92, opacity)
                gradient.add_color_stop_rgba(1.0, 0.48, 0.22, 0.95, opacity)
            else:

                shift = 0.04 * math.sin(self.phase * 0.2)
                gradient.add_color_stop_rgba(0.0, 0.60, 0.12, 0.85, opacity)
                gradient.add_color_stop_rgba(0.6 + shift, 0.95, 0.15, 0.42, opacity)
                gradient.add_color_stop_rgba(1.0, 1.0, 0.38, 0.10, opacity)
            
            cr.set_source(gradient)
            cr.set_line_width(line_w)
            
            cr.new_path()
            first = True
            
            for x in range(0, width + 4, 4):

                envelope = math.sin((x / width) * math.pi)
                
                y = mid_y + (self.amplitude * (height * 0.45) * amp_mult * envelope * 
                             math.sin(x * freq + self.phase + phase_offset))
                
                if first:
                    cr.move_to(x, y)
                    first = False
                else:
                    cr.line_to(x, y)

            
            cr.stroke()






class WhisperFlowOverlay(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, type=Gtk.WindowType.POPUP)

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



        self.connect("draw", self.on_window_draw)


        self.set_default_size(450, -1)
        self.set_size_request(450, -1)

        display = screen.get_display()

        try:
            seat = display.get_default_seat()
            pointer = seat.get_pointer()
            _, x, y = pointer.get_position()
            monitor = display.get_monitor_at_point(x, y)
        except Exception:
            monitor = display.get_primary_monitor()
            
        geo = monitor.get_geometry()

        self.move(
            geo.x + (geo.width - 450) // 2,
            geo.y + geo.height - 310
        )


        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            screen, style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_box.set_margin_top(16)
        self.main_box.set_margin_bottom(16)
        self.main_box.set_margin_start(18)
        self.main_box.set_margin_end(18)
        self.main_box.get_style_context().add_class('overlay')

        self.waveform = SiriWaveform()
        self.main_box.pack_start(self.waveform, False, False, 0)

        # Linha horizontal de status contendo label na esquerda e ícone discreto na direita
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status_box.set_hexpand(True)

        self.status_label = Gtk.Label(label="Iniciando...")
        self.status_label.get_style_context().add_class('status-label')
        self.status_label.set_halign(Gtk.Align.START)
        status_box.pack_start(self.status_label, False, False, 0)

        # SVG do ícone de engrenagem de configuração (opacidade 0.35 para ser bem discreto)
        svg_overlay_icon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.35">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>"""

        try:
            loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
            loader.set_size(14, 14)
            loader.write(svg_overlay_icon.encode('utf-8'))
            loader.close()
            pixbuf_overlay = loader.get_pixbuf()
            img_icon = Gtk.Image.new_from_pixbuf(pixbuf_overlay)
            img_icon.set_halign(Gtk.Align.END)
            img_icon.set_valign(Gtk.Align.CENTER)

            # EventBox para tornar o ícone clicável
            event_box = Gtk.EventBox()
            event_box.set_visible_window(False)
            event_box.add(img_icon)
            event_box.connect("button-press-event", self.on_settings_icon_clicked)

            # Alterar cursor para pointer (mãozinha)
            event_box.connect("realize", lambda widget: widget.get_window().set_cursor(
                Gdk.Cursor.new_from_name(widget.get_display(), "pointer")
            ))

            status_box.pack_end(event_box, False, False, 0)
        except Exception as e:
            _debug_log(f"Falha ao carregar ícone SVG do overlay: {e}")

        self.main_box.pack_start(status_box, False, False, 0)

        self.text_label = Gtk.Label(label="")
        self.text_label.get_style_context().add_class('text-display')
        self.text_label.set_halign(Gtk.Align.START)
        self.text_label.set_line_wrap(True)
        self.text_label.set_max_width_chars(45)
        self.text_label.set_use_markup(True)
        self.main_box.pack_start(self.text_label, True, True, 0)

        self.add(self.main_box)
        self._final_text = ""
        self.dictate_thread = None
        

        self.fade_in()

    def on_window_draw(self, widget, cr):


        cr.set_source_rgba(0.0, 0.0, 0.0, 0.0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        return False

    def on_settings_icon_clicked(self, widget, event):
        _debug_log("Settings icon clicked: opening SettingsWindow")
        if hasattr(self, 'dictate_thread') and self.dictate_thread:
            self.dictate_thread.cancelled = True
        
        config = load_config()
        win = SettingsWindow(config)
        win.show_all()
        self.destroy()

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

    def update_level(self, rms, threshold):
        """Atualiza a onda baseada no RMS."""
        self.waveform.set_rms(rms, threshold)

    def update_status(self, text, css_state=None):
        self.status_label.set_text(text.upper())
        ctx = self.status_label.get_style_context()
        for cls in ['status-calibrating', 'status-waiting', 'status-listening',
                    'status-transcribing', 'status-success', 'status-error']:
            ctx.remove_class(cls)
        if css_state:
            ctx.add_class(css_state)

    def update_text(self, text, final=False):
        import html
        lines = wrap_text_to_lines(text, max_chars=45)
        lines_to_show = lines[-3:]
        while len(lines_to_show) < 3:
            lines_to_show.insert(0, "")
            
        markup_lines = []
        

        if lines_to_show[0]:
            escaped = html.escape(lines_to_show[0])
            markup_lines.append(f'<span foreground="#FFFFFF40">{escaped}</span>')
        else:
            markup_lines.append('<span foreground="#FFFFFF00"> </span>')
            

        if lines_to_show[1]:
            escaped = html.escape(lines_to_show[1])
            markup_lines.append(f'<span foreground="#FFFFFF99">{escaped}</span>')
        else:
            markup_lines.append('<span foreground="#FFFFFF00"> </span>')
            

        if lines_to_show[2]:
            escaped = html.escape(lines_to_show[2])
            if not final:
                markup_lines.append(f'<span foreground="#FFFFFFF2"><i>{escaped}</i></span>')
            else:
                markup_lines.append(f'<span foreground="#FFFFFF"><b>{escaped}</b></span>')
        else:
            markup_lines.append('<span foreground="#FFFFFF00"> </span>')
            
        markup_text = "\n".join(markup_lines)
        self.text_label.set_markup(markup_text)
        
        if final:
            self._final_text = text

    def get_final_text(self):
        return self._final_text
