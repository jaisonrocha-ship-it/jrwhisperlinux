import time
import cairo
import math
import numpy as np
from gi.repository import Gtk, GLib

from ..audio import AudioCapture, calibration_state, default_source_name, evaluate_levels, friendly_mic_name, is_yeti, list_source_names, remove_mic_calibration, resolve_mic, rms_db, save_mic_calibration, yeti_hw_status
from ..config import CALIBRATION_VERDICTS, TICK_INTERVAL
from .theme import apply_settings_css


def _hint_markup(text):
    return f"<span foreground='#FFFFFFB3'>{GLib.markup_escape_text(text)}</span>"


def _db_text(rms):
    db = rms_db(rms)
    return f"{db:.0f}" if db > -80 else "< −80"


class CalibrationWindow(Gtk.Window):
    """Calibração guiada: medidor ao vivo, 3 s de silêncio, 5 s de fala, salva por mic.

    Aberta pelo painel (Calibrar…), pelo OBSBOT Control e por `dictate --calibrate-gui`.
    Mesmo núcleo (evaluate_levels/save_mic_calibration) do `--calibrate` de terminal.
    """
    SETTLE_SECS = 0.5  # descarta o clique do botão
    PHASES = {"silence": 3.0, "voice": 5.0}
    PHRASE = "“Hoje vou ditar um texto longo, com calma, no meu tom de voz normal.”"
    DB_MIN = -80.0

    def __init__(self, config, mic=None, on_saved=None, standalone=False):
        Gtk.Window.__init__(self, title="Calibrar microfone")
        self.set_default_size(540, -1)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        apply_settings_css(self.get_screen())

        self.config = config
        self.on_saved = on_saved
        self.standalone = standalone
        self.capture = None
        self.mic = None
        self.level = 0.0
        self.peak = 0.0
        self.phase = "idle"
        self.phase_start = 0.0
        self.phase_title = ""
        self.samples = {"silence": [], "voice": []}
        self.marks = {}

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.set_margin_top(20)
        root.set_margin_bottom(18)
        root.set_margin_start(22)
        root.set_margin_end(22)
        self.add(root)

        title = Gtk.Label(xalign=0)
        title.set_markup("<span size='large' weight='bold' foreground='#FFFFFF'>Calibrar microfone</span>")
        root.pack_start(title, False, False, 0)
        subtitle = Gtk.Label(xalign=0)
        subtitle.set_line_wrap(True)
        subtitle.set_max_width_chars(62)
        subtitle.set_markup("<span size='small' foreground='#FFFFFF80'>Mede o ruído do ambiente e a sua voz. "
                            "O ditado passa a saber quando você começou e parou de falar.</span>")
        root.pack_start(subtitle, False, False, 0)

        mic_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mic_row.pack_start(Gtk.Label(label="Microfone:"), False, False, 0)
        self.combo = Gtk.ComboBoxText()
        names = list_source_names()
        default = default_source_name()
        initial = mic or resolve_mic(config)[0]
        if initial not in names:
            names.append(initial)
        for n in names:
            self.combo.append(n, friendly_mic_name(n) + ("  ·  padrão do sistema" if n == default else ""))
        mic_row.pack_start(self.combo, True, True, 0)
        root.pack_start(mic_row, False, False, 0)

        self.lbl_mic_state = Gtk.Label(xalign=0)
        self.lbl_mic_state.set_line_wrap(True)
        self.lbl_mic_state.set_max_width_chars(70)
        root.pack_start(self.lbl_mic_state, False, False, 0)

        self.meter = Gtk.DrawingArea()
        self.meter.set_size_request(-1, 76)
        self.meter.connect("draw", self.on_draw_meter)
        root.pack_start(self.meter, False, False, 4)

        self.lbl_step = Gtk.Label(xalign=0)
        root.pack_start(self.lbl_step, False, False, 0)
        self.lbl_hint = Gtk.Label(xalign=0)
        self.lbl_hint.set_line_wrap(True)
        self.lbl_hint.set_max_width_chars(62)
        root.pack_start(self.lbl_hint, False, False, 0)
        self.progress = Gtk.ProgressBar()
        root.pack_start(self.progress, False, False, 0)
        self.lbl_result = Gtk.Label(xalign=0)
        self.lbl_result.set_line_wrap(True)
        self.lbl_result.set_no_show_all(True)
        root.pack_start(self.lbl_result, False, False, 0)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bar.set_margin_top(6)
        self.btn_auto = Gtk.Button(label="Usar automático")
        self.btn_auto.get_style_context().add_class("btn-secondary")
        self.btn_auto.set_tooltip_text("Apaga a calibração deste mic; o ditado volta a medir o ruído a cada uso.")
        self.btn_auto.connect("clicked", self.on_auto)
        bar.pack_start(self.btn_auto, False, False, 0)
        self.btn_start = Gtk.Button(label="Iniciar calibração")
        self.btn_start.get_style_context().add_class("btn-primary")
        self.btn_start.connect("clicked", self.on_start)
        bar.pack_end(self.btn_start, False, False, 0)
        btn_close = Gtk.Button(label="Fechar")
        btn_close.get_style_context().add_class("btn-secondary")
        btn_close.connect("clicked", lambda b: self.destroy())
        bar.pack_end(btn_close, False, False, 0)
        root.pack_start(bar, False, False, 0)

        self.connect("destroy", self.on_destroy)
        self.combo.connect("changed", self.on_mic_changed)
        self.combo.set_active_id(initial)
        self._tick_id = GLib.timeout_add(int(TICK_INTERVAL * 1000), self._tick)

    # ── mic ────────────────────────────────────────────────────────
    def on_mic_changed(self, combo):
        mic = combo.get_active_id()
        if not mic or mic == self.mic:
            return
        if self.capture:
            self.capture.stop()
        self.mic = mic
        self.capture = AudioCapture(mic, self.config.get("sample_rate", 16000))
        self.capture.start()
        self.peak = 0.0
        self._refresh_mic_state()
        self._show_idle()

    def _refresh_mic_state(self):
        hw = yeti_hw_status() if is_yeti(self.mic) else None
        state, cal = calibration_state(self.config, self.mic, hw.get("gain") if hw else None)
        parts = []
        if hw:
            if hw.get("muted"):
                parts.append("<span foreground='#FF7864'>Yeti mutado no hardware: desmute no knob ou no OBSBOT Control</span>")
            else:
                parts.append(f"Ganho de hardware {hw.get('gain')}/100")
        if state == "ok":
            parts.append(f"Calibrado em {cal['date']} · limiar {cal['threshold']:.4f}")
        elif state == "stale":
            parts.append(f"<span foreground='#FFC83C'>Ganho mudou desde a calibração (era {cal['hw_gain']}): recalibre</span>")
        else:
            parts.append("Sem calibração · o ditado mede o ruído a cada uso")
        if self.config.get("silence_threshold"):
            parts.append(f"<span foreground='#FFC83C'>Limite manual {self.config['silence_threshold']:.4f} no painel; calibrar substitui</span>")
        self.lbl_mic_state.set_markup("<span size='small' foreground='#FFFFFF99'>" + "  ·  ".join(parts) + "</span>")
        self.btn_auto.set_sensitive(cal is not None)
        self.marks = {k: cal[k] for k in ("noise", "voice", "threshold")} if cal else {}

    # ── fluxo ──────────────────────────────────────────────────────
    def _show_idle(self):
        self.phase = "idle"
        self.lbl_step.set_markup("<span size='x-large' weight='bold' foreground='#FFFFFF'>Pronto</span>")
        self.lbl_hint.set_markup(_hint_markup(
            "Fale algo e veja a barra reagir. Ao iniciar: 3 s em silêncio, depois 5 s falando."))
        self.progress.set_fraction(0.0)
        self.lbl_result.hide()
        self.btn_start.set_label("Iniciar calibração")
        self.btn_start.set_sensitive(True)

    def on_start(self, btn):
        self.samples = {"silence": [], "voice": []}
        self.marks = {}
        self.lbl_result.hide()
        self.btn_start.set_sensitive(False)
        self._enter("silence")

    def _enter(self, phase):
        self.phase = phase
        self.phase_start = time.time()
        if phase == "silence":
            self.phase_title = "1/2 · Silêncio"
            self.lbl_hint.set_markup(_hint_markup("Não fale. Medindo o ruído do ambiente…"))
        else:
            self.phase_title = "2/2 · Fale agora"
            self.lbl_hint.set_markup(_hint_markup(f"Leia em voz alta, no seu tom normal:\n{self.PHRASE}"))

    def _tick(self):
        self.level = self.capture.get_rms() if self.capture else 0.0
        self.peak = max(self.level, self.peak * 0.96)
        if self.phase in self.PHASES:
            t = time.time() - self.phase_start
            total = self.SETTLE_SECS + self.PHASES[self.phase]
            if t >= self.SETTLE_SECS:
                self.samples[self.phase].append(self.level)
            left = max(0, math.ceil(total - t))
            self.lbl_step.set_markup(
                f"<span size='x-large' weight='bold' foreground='#FFFFFF'>{self.phase_title}</span>"
                f"   <span size='x-large' foreground='#64DCFF'>{left}</span>")
            self.progress.set_fraction(min(t / total, 1.0))
            if self.samples["silence"]:
                self.marks["noise"] = float(np.median(self.samples["silence"]))
            if self.samples["voice"]:
                self.marks["voice"] = float(np.percentile(self.samples["voice"], 75))
            if t >= total:
                if self.phase == "silence":
                    self._enter("voice")
                else:
                    self._finish()
        self.meter.queue_draw()
        return True

    def _finish(self):
        self.phase = "done"
        r = evaluate_levels(np.array(self.samples["silence"]), np.array(self.samples["voice"]))
        title, color, text = CALIBRATION_VERDICTS[r["verdict"]]
        self.lbl_step.set_markup(f"<span size='x-large' weight='bold' foreground='{color}'>{title}</span>")
        self.lbl_hint.set_markup(_hint_markup(text))
        margin = max(rms_db(r["voice"]), -80) - max(rms_db(r["noise"]), -80)
        nums = f"Ruído {_db_text(r['noise'])} dBFS  ·  Voz {_db_text(r['voice'])} dBFS  ·  Margem {margin:.0f} dB"
        if r["threshold"] is not None:
            save_mic_calibration(self.config, self.mic, r)
            nums += f"  ·  Limiar {r['threshold']:.4f}\nSalvo para {friendly_mic_name(self.mic)}."
            if self.on_saved:
                self.on_saved()
        self._refresh_mic_state()
        self.marks = {"noise": r["noise"], "voice": r["voice"], "threshold": r["threshold"]}
        self.lbl_result.set_markup(f"<span size='small' foreground='#FFFFFFCC'>{GLib.markup_escape_text(nums)}</span>")
        self.lbl_result.show()
        self.progress.set_fraction(1.0)
        self.btn_start.set_label("Refazer")
        self.btn_start.set_sensitive(True)

    def on_auto(self, btn):
        remove_mic_calibration(self.config, self.mic)
        self._refresh_mic_state()
        if self.on_saved:
            self.on_saved()

    def on_destroy(self, *args):
        GLib.source_remove(self._tick_id)
        if self.capture:
            self.capture.stop()
            self.capture = None
        if self.standalone:
            Gtk.main_quit()

    # ── medidor ────────────────────────────────────────────────────
    def _x(self, rms, x0, w):
        return x0 + w * float(np.clip((rms_db(rms) - self.DB_MIN) / -self.DB_MIN, 0, 1))

    def on_draw_meter(self, widget, cr):
        width = widget.get_allocated_width()
        x0, w = 4, width - 8
        bar_y, bar_h = 22, 20

        def rounded(x, y, ww, hh, r):
            if ww <= 0:
                return
            r = min(r, ww / 2, hh / 2)
            cr.new_sub_path()
            cr.arc(x + ww - r, y + r, r, -math.pi / 2, 0)
            cr.arc(x + ww - r, y + hh - r, r, 0, math.pi / 2)
            cr.arc(x + r, y + hh - r, r, math.pi / 2, math.pi)
            cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
            cr.close_path()

        cr.set_source_rgba(1, 1, 1, 0.06)
        rounded(x0, bar_y, w, bar_h, 6)
        cr.fill()

        # Gradiente fixo na escala: âmbar/vermelho só perto do clipping.
        grad = cairo.LinearGradient(x0, 0, x0 + w, 0)
        grad.add_color_stop_rgb(0.0, 0.0, 0.48, 1.0)
        grad.add_color_stop_rgb(0.75, 0.39, 0.86, 1.0)
        grad.add_color_stop_rgb(0.92, 1.0, 0.78, 0.24)
        grad.add_color_stop_rgb(1.0, 1.0, 0.33, 0.33)
        cr.set_source(grad)
        rounded(x0, bar_y, self._x(self.level, x0, w) - x0, bar_h, 6)
        cr.fill()

        px = self._x(self.peak, x0, w)
        cr.set_source_rgba(1, 1, 1, 0.75)
        cr.rectangle(px - 1, bar_y, 2, bar_h)
        cr.fill()

        cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(10)
        for key, label, rgb in (("noise", "ruído", (0.62, 0.62, 0.68)),
                                ("threshold", "limiar", (1.0, 0.78, 0.24)),
                                ("voice", "voz", (0.39, 1.0, 0.63))):
            v = self.marks.get(key)
            if v is None:
                continue
            mx = self._x(v, x0, w)
            cr.set_source_rgb(*rgb)
            cr.rectangle(mx - 1, bar_y - 3, 2, bar_h + 6)
            cr.fill()
            ext = cr.text_extents(label)
            cr.move_to(min(max(mx - ext.width / 2, x0), x0 + w - ext.width), bar_y - 7)
            cr.show_text(label)

        cr.set_source_rgba(1, 1, 1, 0.4)
        for db in (-80, -60, -40, -20, 0):
            text = f"{db} dB"
            ext = cr.text_extents(text)
            tx = x0 + w * (db - self.DB_MIN) / -self.DB_MIN
            cr.move_to(min(max(tx - ext.width / 2, x0), x0 + w - ext.width), bar_y + bar_h + 16)
            cr.show_text(text)
        return False
