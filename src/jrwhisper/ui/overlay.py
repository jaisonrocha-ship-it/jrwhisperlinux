"""HUD do ditado: visual (Orbe/Ondas/Barras) + status + texto, tudo em Cairo/Pango.

Sem widgets GTK dentro: o tema do sistema não interfere e a janela é
click-through, exceto a engrenagem e, com a IA ligada, a revisão: botões de escolha,
palavras do texto (clique numa palavra abre um campo para corrigi-la), roda do mouse
rola o texto e o teclado vem para o overlay (Enter cola, Esc descarta, Ctrl+C copia, 1–9 modos).
API usada pelo DictateThread: update_level, update_spectrum, update_status,
update_text, show_choices, hide_choices, pick, fade_out, dictate_thread, wants_spectrum.
"""
import math
import re

import cairo
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo

from .. import learning
from ..config import _debug_log, load_config
from .theme import icon_pixbuf
from .captionview import CaptionView
from .visuals import make_visual, rounded_rect

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


def _focus_event(window, focus_in):
    ev = Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE)
    ev.focus_change.window = window.get_window()
    ev.focus_change.in_ = focus_in
    return ev


# rótulos em markup Pango; a tecla vem esmaecida, como o número dos modos
ACTIONS = (("Colar  <span alpha='55%'>↵</span>", "paste"), ("Colar e enviar  <span alpha='55%'>⇧↵</span>", "send"),
           ("Continuar  <span alpha='55%'>␣</span>", "continue"), ("Copiar", "copy"), ("Descartar", "discard"))


class WhisperFlowOverlay(Gtk.Window):
    MAX_LINES = 3
    CHOICE_LINES = 6   # revisão com IA: mais texto à vista
    CHIP_ROWS = 6      # espaço reservado: 2 linhas de modos + "contexto" + "lembrar" + 2 de ações
    MODE_ROWS = 2

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
        # legendas: mais linhas e cartão mais largo (ditado: 3 linhas que acompanham o fim)
        self.max_lines = int(config.get("overlay_lines", self.MAX_LINES))
        # legendas ao vivo (update_captions): desenho em CaptionView, o mesmo da prévia dos Ajustes
        self.captions = bool(config.get("overlay_captions"))
        # IA ligada (fora do mãos livres): o texto espera a escolha em vez de colar sozinho
        self.choices_enabled = bool(config.get("ai_enabled")) and not config.get("handsfree_enabled")
        self.learn = bool(config.get("learn_corrections", True))
        position = config.get("overlay_position", "bottom")
        s = self.scale = self.visual.scale

        self.vw, self.vh = self.visual.size()
        self.text_w = (640 if self.max_lines > self.MAX_LINES else 440) * s
        self.capview = CaptionView(config, s, self.visual.accent[0]) if self.captions else None
        if self.capview:  # com a lente, o cartão alarga para a linha aumentada caber
            self.text_w = min(self.text_w * self.capview.zoom, 1100 * s)
        self.font_px = 14.5 * s
        self.line_h = self.font_px * 1.45
        self.text_pad = 12 * s
        self.chip_h, self.chip_gap = 26 * s, 6 * s
        has_text = self.show_text or self.choices_enabled
        text_max_h = (2 * self.text_pad + self.line_h * self.max_lines) if self.show_text else 0
        if self.choices_enabled:
            text_max_h = max(text_max_h, 2 * self.text_pad + self.line_h * self.CHOICE_LINES + self._chips_h(self.CHIP_ROWS))
        status_h = 24 * s
        gap = 10 * s
        self.W = int(max(self.vw, self.text_w) + 48 * s)
        self.H = int(self.vh + status_h + (text_max_h + gap if has_text else 0) + 16 * s)
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
        self.gear_icon = icon_pixbuf("settings", int(15 * s), "#FFFFFF", 1.8)

        self.status = "Iniciando…"
        self.text = ""
        self.final = False
        self.text_alpha = 0.0
        self.box_h = 0.0
        self._final_text = ""
        self.dictate_thread = None
        self.on_handoff = None   # chamado quando a engrenagem transforma o processo em Ajustes
        self._last_frame = None
        self.choices = None      # (modos, selecionado, callback) enquanto espera a escolha
        self.choices_busy = False
        self._chip_rects = []    # [(x, y, w, h, ação)] do último desenho; palavra: ("word", início, fim)
        self.edited = False      # o usuário corrigiu palavras desde o último show_choices
        self._editor = None      # (janela, entry, início, fim) da palavra em edição
        self.corrections = []    # [{"old", "new", "remember"}]: palavras corrigidas que viram regra ao colar
        self.context = None      # (resumo, ligado) do campo em foco; o chip liga/desliga para este ditado
        self._hover = None
        self._scroll = 0         # 1ª linha visível na revisão (texto longo, ex.: e-mail)
        self._more = (False, False)  # há linhas (acima, abaixo) fora da vista

        self._place(screen, position)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK | Gdk.EventMask.SCROLL_MASK
                        | Gdk.EventMask.SMOOTH_SCROLL_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("button-press-event", self._on_press)
        self.connect("scroll-event", self._on_scroll)
        self.connect("key-press-event", self._on_key)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("leave-notify-event", lambda *_: self._set_hover(None))
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
        self._update_input_shape()

    def _update_input_shape(self):
        # Click-through: só a engrenagem e os botões de escolha recebem clique.
        region = cairo.Region(cairo.RectangleInt(*self.gear))
        for x, y, w, h, _a in self._chip_rects:
            region.union(cairo.RectangleInt(int(x), int(y), int(w) + 1, int(h) + 1))
        self.input_shape_combine_region(region)

    def _on_press(self, _w, event):
        gx, gy, gw, gh = self.gear
        if gx <= event.x <= gx + gw and gy <= event.y <= gy + gh:
            self.on_settings_icon_clicked(None, event)
            return True
        hit = self._hit(event.x, event.y)
        self._finish_edit(True)  # clicar em outra coisa confirma a palavra em edição
        if hit and self.choices and not self.choices_busy:
            x, y, w, h, action = hit
            if action == ("context",):
                self.pick("context")
            elif isinstance(action, tuple) and action[0] == "learn":
                c = self.corrections[action[1]]
                c["remember"] = not c["remember"]
                self.queue_draw()
            elif isinstance(action, tuple):
                self._edit_word(action[1], action[2], (x, y, w, h))
            else:
                self.pick(action)
        return True

    def pick(self, action):
        """Escolha da revisão (clique, teclado ou 2º toque no atalho): "paste", "copy", "discard",
        "original" ou id de modo. Ignorada enquanto a thread processa a anterior."""
        self._finish_edit(True)
        if self.choices and not self.choices_busy:
            self.choices_busy = True  # até a thread responder (reescrever leva ~1-2 s)
            if action in ("paste", "send", "copy", "discard"):
                # solta o teclado já: o Ctrl+V do xdotool iria para o grab, não para o app
                self.get_display().get_default_seat().ungrab()
                self.get_display().flush()
            self.choices[2](action)

    def _on_key(self, _w, ev):
        if not self.choices or self._editor:
            return False
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        ch = chr(Gdk.keyval_to_unicode(ev.keyval) or 0)
        if ev.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.pick("send" if ev.state & Gdk.ModifierType.SHIFT_MASK else "paste")
        elif ev.keyval == Gdk.KEY_Escape:
            self.pick("discard")
        elif ctrl and ch.lower() == "c":
            self.pick("copy")
        elif ev.keyval == Gdk.KEY_space:
            self.pick("continue")
        elif not ctrl and ch == "0":
            self.pick("raw")
        elif not ctrl and ch in "123456789":
            options = ["original"] + [m["id"] for m in self.choices[0]]
            if int(ch) <= len(options):
                self.pick(options[int(ch) - 1])
        else:
            return False
        return True

    def _on_scroll(self, _w, ev):
        if not (self.choices or self.captions):
            return False
        step = {Gdk.ScrollDirection.UP: -1, Gdk.ScrollDirection.DOWN: 1}.get(ev.direction)
        if step is None:  # touchpad: rolagem suave
            ok, _dx, dy = ev.get_scroll_deltas()
            step = (dy > 0) - (dy < 0) if ok else 0
        if self.captions:  # reler: pausa o acompanhamento até voltar ao fim (ou 8 s parado)
            self.capview.scroll_by(step)
            return True
        self._scroll = max(0, self._scroll + step)  # o limite de baixo é aplicado no desenho
        return True

    def _grab_keys(self):
        """Revisão aberta: o teclado vem para o overlay (como num menu GTK) até a escolha."""
        if self.choices and not self._editor and self.get_window():
            self.get_display().get_default_seat().grab(
                self.get_window(), Gdk.SeatCapabilities.KEYBOARD, True, None, None, None, None)

    def _hit(self, ex, ey):
        return next((r for r in self._chip_rects if r[4] != "box"
                     and r[0] <= ex <= r[0] + r[2] and r[1] <= ey <= r[1] + r[3]), None)

    def _on_motion(self, _w, event):
        hit = self._hit(event.x, event.y)
        self._set_hover(hit[4] if hit and isinstance(hit[4], tuple) and hit[4][0] == "word" else None)

    def _set_hover(self, word):
        if word != self._hover and self.get_window():
            self._hover = word
            cursor = Gdk.Cursor.new_from_name(self.get_display(), "text") if word else None
            self.get_window().set_cursor(cursor)

    # ── edição de palavra ──────────────────────────────────────────
    def _edit_word(self, start, end, rect):
        """Campo de texto por cima da palavra. Enter/clicar fora confirma, Esc cancela, vazio apaga."""
        word = self.text[start:end]
        x, y, w, h = rect
        ox, oy = self.get_position()
        # Popup como o overlay (janela normal ficaria atrás dele); o teclado vem por grab, como nos menus GTK.
        win = Gtk.Window(type=Gtk.WindowType.POPUP)
        entry = Gtk.Entry(text=word, width_chars=max(len(word), 3) + 1)
        r, g, b = (int(c * 255) for c in self.visual.accent[0])
        css = Gtk.CssProvider()
        css.load_from_data((
            f"entry {{ font-family: Inter; font-size: {self.font_px:.1f}px; min-height: 0; padding: 1px 6px;"
            f" border-radius: 7px; border: 1px solid rgb({r},{g},{b}); background: #2C2C2E;"
            f" color: #F5F5F7; box-shadow: none; }}").encode())
        entry.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        entry.connect("changed", lambda e: e.set_width_chars(max(len(e.get_text()), 3) + 1))
        entry.connect("activate", lambda _e: self._finish_edit(True))
        entry.connect("key-press-event", lambda _e, ev: ev.keyval == Gdk.KEY_Escape and (self._finish_edit(False) or True))
        win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        win.connect("button-press-event", self._on_editor_press)
        win.add(entry)
        win.move(int(ox + x - 4 * self.scale), int(oy + y))
        win.show_all()
        entry.grab_focus()
        entry.event(_focus_event(win, True))  # popup não ganha foco do WM: liga o cursor na mão
        self._editor = (win, entry, start, end)
        # owner_events: cliques no overlay seguem para ele; fora das nossas janelas chegam aqui
        win.get_display().get_default_seat().grab(
            win.get_window(), Gdk.SeatCapabilities.KEYBOARD | Gdk.SeatCapabilities.POINTER, True, None, None, None, None)

    def _on_editor_press(self, win, event):
        w, h = win.get_size()
        if not (0 <= event.x <= w and 0 <= event.y <= h):
            self._finish_edit(True)  # clique fora confirma
        return False

    def _finish_edit(self, commit):
        ed, self._editor = self._editor, None
        if not ed:
            return
        win, entry, start, end = ed
        win.get_display().get_default_seat().ungrab()
        new = entry.get_text().strip()
        if commit and new != self.text[start:end]:
            self._note_correction(self.text[start:end], new)
            text = re.sub(r" {2,}", " ", self.text[:start] + new + self.text[end:]).strip()
            self.text = self._final_text = text
            self.edited = True
        win.destroy()
        self._grab_keys()  # o editor tinha o teclado; devolve para a revisão

    def _note_correction(self, old, new):
        """Grafia corrigida vira candidata a regra (marcada "lembrar"; clique no selo desmarca)."""
        if not self.learn:
            return
        prev = next((c for c in self.corrections if c["new"] == learning._word(old)), None)
        pair = learning.candidate(prev["old"] if prev else old, new)  # corrigiu de novo: vale a 1ª grafia
        if prev:
            self.corrections.remove(prev)
        if pair:
            self.corrections.append({"old": pair[0], "new": pair[1], "remember": True})

    def _visible_corrections(self):
        """Só as que ainda aparecem no texto (trocar de modo pode reescrever a palavra)."""
        words = {learning._word(w) for w in self.text.split()}
        return [(i, c) for i, c in enumerate(self.corrections) if c["new"] in words]

    def on_settings_icon_clicked(self, widget, event):
        _debug_log("Settings icon clicked: opening SettingsWindow")
        if self.dictate_thread:
            self.dictate_thread.cancelled = True
        if self.on_handoff:
            self.on_handoff()  # este processo agora é só os Ajustes: o atalho volta a iniciar ditados
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
        if self.captions:
            self.capview.advance(dt)
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

    def update_captions(self, blocks, live):
        """Legendas: frases fechadas (cada uma um bloco que não muda mais) e a prévia, esmaecida."""
        self.capview.set_text(blocks, live)
        self.text = " ".join(blocks + [live]).strip()

    def get_final_text(self):
        return self._final_text

    def show_choices(self, text, modes, selected, on_pick):
        """Mostra o texto com botões; on_pick(ação) roda na thread GTK: "paste", "copy", "discard",
        "original" ou o id de um modo de IA."""
        self._finish_edit(False)
        self.text, self.final, self._final_text = text, True, text
        self.choices = (modes, selected, on_pick)
        self.choices_busy = False
        self.edited = False
        self._scroll = 0
        self._grab_keys()

    def set_context(self, label, on):
        label = label if len(label) <= 52 else label[:51] + "…"  # chip cabe numa linha
        self.context = (label, on) if label else None
        self.queue_draw()

    def hide_choices(self):
        self._finish_edit(False)
        self.choices = None
        self._chip_rects = []
        self._update_input_shape()
        self.get_display().get_default_seat().ungrab()

    # ── desenho ────────────────────────────────────────────────────
    def _layout(self, cr, text, px, weight=Pango.Weight.NORMAL, width=None, markup=False):
        layout = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription.from_string("Inter")
        fd.set_absolute_size(px * Pango.SCALE)
        fd.set_weight(weight)
        layout.set_font_description(fd)
        layout.set_alignment(Pango.Alignment.CENTER)
        if width:
            layout.set_width(int(width * Pango.SCALE))
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_markup(text, -1) if markup else layout.set_text(text, -1)
        return layout

    def _visible_lines(self, cr):
        """Linhas do texto quebrado pelo Pango (quebra real): as últimas ao ditar, a janela rolável na revisão."""
        if not self.text:
            return []
        layout = self._layout(cr, self.text, self.font_px, width=self.text_w - 2 * self.text_pad)
        raw = self.text.encode()
        lines = []  # (linha, posição do 1º caractere em self.text): a edição troca a palavra no texto todo
        for ln in layout.get_lines_readonly():
            seg = raw[ln.start_index:ln.start_index + ln.length].decode(errors="ignore")
            if seg.strip() or self.choices:  # na revisão, linha vazia separa parágrafos (e-mail)
                lead = len(seg) - len(seg.lstrip())
                lines.append((seg.strip(), len(raw[:ln.start_index].decode(errors="ignore")) + lead))
        if not self.choices:
            return lines[-self.max_lines:]  # ditando/legenda: acompanha o fim
        # revisão: lê-se de cima, rolando com a roda do mouse
        self._scroll = start = min(self._scroll, max(0, len(lines) - self.CHOICE_LINES))
        self._more = (start > 0, start + self.CHOICE_LINES < len(lines))
        return lines[start:start + self.CHOICE_LINES]

    def _chips_h(self, rows):
        return rows * self.chip_h + (rows - 1) * self.chip_gap + 12 * self.scale if rows else 0

    def _chip_rows(self, cr):
        """Botões em linhas centralizadas: modos de IA (quebrando) e, por último, as ações."""
        if not self.choices:
            return []
        modes, selected, _cb = self.choices
        px = 11 * self.scale
        max_w = self.text_w - 2 * self.text_pad

        def chip(label, action, kind):  # label em markup Pango
            w = self._layout(cr, label, 12 * self.scale, Pango.Weight.MEDIUM, markup=True).get_pixel_size()[0]
            return label, action, kind, w + 2 * px

        rows, row, row_w = [], [], 0
        # número = tecla do modo (0 = Bruto, 1–9)
        items = [chip("Reescrever:", None, "label")] + [
            chip(f"<span alpha='50%'>{i}</span>  {GLib.markup_escape_text(label)}" if i <= 9
                 else GLib.markup_escape_text(label), action, "selected" if action == selected else "mode")
            for i, (label, action) in enumerate([("Bruto", "raw"), ("Original", "original")]
                                                + [(m["name"], m["id"]) for m in modes])]
        for it in items:
            if row and row_w + self.chip_gap + it[3] > max_w:
                rows.append(row)
                row, row_w = [], 0
            row_w += (self.chip_gap if row else 0) + it[3]
            row.append(it)
        rows.append(row)
        # ponytail: além de MODE_ROWS linhas os modos somem; com muitos modos, aumentar MODE_ROWS e CHIP_ROWS
        rows = rows[: self.MODE_ROWS]
        if self.context:  # o que a IA está usando do campo em foco; clique desliga e refaz
            label, on = self.context
            rows.append([chip("Contexto:", None, "label"),
                         chip(f"{'✓' if on else '○'}  {GLib.markup_escape_text(label)}", ("context",),
                              "learn" if on else "learn_off")])
        learn = self._visible_corrections()
        if learn:  # ✓ = vira regra ao colar; clique alterna
            row = [chip("Lembrar:", None, "label")]
            row_w = row[0][3]
            for i, c in learn:
                mark = "✓" if c["remember"] else "○"
                it = chip(f"{mark}  <span alpha='60%'>{GLib.markup_escape_text(c['old'])} →</span> "
                          f"{GLib.markup_escape_text(c['new'])}", ("learn", i),
                          "learn" if c["remember"] else "learn_off")
                if row_w + self.chip_gap + it[3] > max_w:
                    break  # ponytail: correções além da largura do cartão ficam sem selo (aprendem marcadas)
                row_w += self.chip_gap + it[3]
                row.append(it)
            rows.append(row)
        # ações em dois grupos: o que termina/continua o ditado em cima, copiar/descartar embaixo
        for group in (ACTIONS[:3], ACTIONS[3:]):
            rows.append([chip(label, action, "primary" if action == "paste" else "action") for label, action in group])
        return rows

    def _target_box_h(self):
        if not self.text:
            return 0.0
        if self.captions:  # altura fixa: o cartão não estica nem encolhe enquanto o texto corre
            return 2 * self.text_pad + self.line_h * self.max_lines
        n = getattr(self, "_n_lines", 1)
        return 2 * self.text_pad + self.line_h * n + self._chips_h(getattr(self, "_n_chip_rows", 0))

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

    def _draw_captions(self, cr):
        if self.box_h < 1 or self.text_alpha < 0.02:
            self._set_chip_rects([])
            return
        x = self.cx - self.text_w / 2
        y = self.text_anchor - self.box_h if self.text_above else self.text_anchor
        self.capview.draw(cr, x, y, self.text_w, self.box_h, self.text_alpha)
        self._set_chip_rects([(x, y, self.text_w, self.box_h, "box")])  # o cartão recebe a roda do mouse

    def _draw_text(self, cr):
        if self.captions:
            return self._draw_captions(cr)
        lines = self._visible_lines(cr) if (self.show_text or self.choices) else []
        self._n_lines = max(len(lines), 1)
        chip_rows = self._chip_rows(cr)
        self._n_chip_rows = len(chip_rows)
        if self.box_h < 1 or self.text_alpha < 0.02:
            self._set_chip_rects([])
            return
        word_rects = []
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
        alphas = [0.38, 0.62, 1.0][-n:] if n <= 3 else [0.5 + 0.5 * i / (n - 1) for i in range(n)]
        if self.choices:
            alphas = [1.0] * n  # revisão: tudo legível
        chips_h = self._chips_h(len(chip_rows))
        ty = y + self.text_pad + (self.box_h - chips_h - 2 * self.text_pad - self.line_h * n) / 2
        for i, ((line, offset), la) in enumerate(zip(lines, alphas)):
            current = i == n - 1
            weight = Pango.Weight.MEDIUM if (current and self.final and not self.choices) else Pango.Weight.NORMAL
            lay = self._layout(cr, line, self.font_px, weight)
            w, h = lay.get_pixel_size()
            # legenda (várias linhas de texto corrido) lê melhor alinhada à esquerda
            lx = x + self.text_pad if self.max_lines > self.MAX_LINES and not self.choices else self.cx - w / 2
            if self.choices:  # cada palavra vira alvo de clique para edição
                remembered = {c["new"] for _i, c in self._visible_corrections() if c["remember"]}
                for m in re.finditer(r"\S+", line):
                    p0 = lay.index_to_pos(len(line[:m.start()].encode()))
                    p1 = lay.index_to_pos(len(line[:m.end() - 1].encode()))
                    wx0, wx1 = lx + p0.x / Pango.SCALE, lx + (p1.x + p1.width) / Pango.SCALE
                    pad = 3 * self.scale
                    word = ("word", offset + m.start(), offset + m.end())
                    word_rects.append((wx0 - pad, ty, wx1 - wx0 + 2 * pad, self.line_h, word))
                    if word == self._hover:
                        rounded_rect(cr, wx0 - pad, ty + 1, wx1 - wx0 + 2 * pad, self.line_h - 2, 6 * self.scale)
                        cr.set_source_rgba(1, 1, 1, 0.12 * a)
                        cr.fill()
                    if learning._word(m.group()) in remembered:  # sublinhado = vai ser lembrada (sem a pontuação)
                        core = len(m.group().rstrip(".,;:!?\"'”)"))
                        pe = lay.index_to_pos(len(line[:m.start() + core - 1].encode()))
                        ux1 = lx + (pe.x + pe.width) / Pango.SCALE
                        uy = ty + (self.line_h + h) / 2 + 1 * self.scale
                        rounded_rect(cr, wx0, uy, ux1 - wx0, 2 * self.scale, self.scale)
                        cr.set_source_rgba(*self.visual.accent[0], 0.9 * a)
                        cr.fill()
            cr.move_to(lx, ty + (self.line_h - h) / 2)
            cr.set_source_rgba(1, 1, 1, a * la * (1.0 if (self.final or not current) else 0.85))
            PangoCairo.show_layout(cr, lay)
            ty += self.line_h
        if self.choices:  # setinhas: há texto acima/abaixo (roda do mouse rola)
            top = y + self.text_pad + (self.box_h - chips_h - 2 * self.text_pad - self.line_h * n) / 2
            k, cx = 4 * self.scale, x + bw - 14 * self.scale
            for more, cy, d in ((self._more[0], top + k, -1), (self._more[1], ty - k, 1)):
                if more:
                    cr.move_to(cx - k, cy - d * k / 2)
                    cr.line_to(cx, cy + d * k / 2)
                    cr.line_to(cx + k, cy - d * k / 2)
            cr.set_source_rgba(1, 1, 1, 0.5 * a)
            cr.set_line_width(1.5 * self.scale)
            cr.stroke()
        chip_rects = self._draw_chips(cr, chip_rows, y + self.box_h - self.text_pad - chips_h + 12 * self.scale, a)
        # revisão: o cartão todo recebe a roda do mouse (no resto, click-through)
        box = [(x, y, bw, self.box_h, "box")] if self.choices else []
        self._set_chip_rects(box + word_rects + chip_rects)
        cr.restore()

    def _draw_chips(self, cr, rows, top, a):
        rects = []
        accent = self.visual.accent[0]
        dim = 0.4 if self.choices_busy else 1.0
        cy = top
        for row in rows:
            row_w = sum(it[3] for it in row) + self.chip_gap * (len(row) - 1)
            cx = self.cx - row_w / 2
            for label, action, kind, w in row:
                if kind != "label":
                    rounded_rect(cr, cx, cy, w, self.chip_h, self.chip_h / 2)
                    if kind in ("selected", "primary", "learn"):  # modo atual mais suave que a ação principal
                        cr.set_source_rgba(*accent, {"primary": 0.95, "selected": 0.45}.get(kind, 0.28) * a * dim)
                    elif kind == "learn_off":
                        cr.set_source_rgba(1, 1, 1, 0.04 * a * dim)
                    else:
                        cr.set_source_rgba(1, 1, 1, 0.09 * a * dim)
                    cr.fill()
                    rects.append((cx, cy, w, self.chip_h, action))
                lay = self._layout(cr, label, 12 * self.scale,
                                   Pango.Weight.SEMIBOLD if kind == "primary" else Pango.Weight.MEDIUM, markup=True)
                tw, th = lay.get_pixel_size()
                cr.move_to(cx + (w - tw) / 2, cy + (self.chip_h - th) / 2)
                cr.set_source_rgba(1, 1, 1, {"label": 0.5, "learn_off": 0.45}.get(kind, 0.92) * a * dim)
                PangoCairo.show_layout(cr, lay)
                cx += w + self.chip_gap
            cy += self.chip_h + self.chip_gap
        return rects

    def _set_chip_rects(self, rects):
        rounded = [tuple(int(v) for v in r[:4]) + (r[4],) for r in rects]
        if rounded != [tuple(int(v) for v in r[:4]) + (r[4],) for r in self._chip_rects]:
            self._chip_rects = rects
            self._update_input_shape()
