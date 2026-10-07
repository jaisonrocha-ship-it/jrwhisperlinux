"""Ajustes do Whisper no estilo Ajustes do Sistema do macOS.

Sidebar com ícones, páginas com grupos arredondados e aplicação instantânea
(sem Salvar/Cancelar): cada mudança grava o config com debounce e escrita atômica.
Recursos avançados ficam atrás de um switch mestre em cada aba.
"""
import copy
import math
import os
import subprocess
import threading

import cairo
import numpy as np

from gi.repository import Gtk, Gdk, GLib

from .. import history, shortcuts
from ..audio import (AudioCapture, calibration_state, default_source_name, friendly_mic_name,
                     list_source_names, resolve_mic, rms_db)
from ..config import DEFAULT_CONFIG, RUNTIME_DIR, _debug_log, save_config
from ..transcribe import is_daemon_running
from . import theme as t
from .calibration import CalibrationWindow
from .visuals import VISUAL_LABELS, make_visual, rounded_rect, spectrum_bands

DICTATE_CMD = os.path.expanduser("~/.local/bin/dictate")
CRITICAL_KEYS = ("model", "language", "initial_prompt")  # exigem reiniciar o daemon

PAGES = [
    # id, rótulo, ícone, cor do quadradinho
    ("general", "Geral", "settings", "#8E8E93"),
    ("appearance", "Aparência", "palette", "#7C6CFF"),
    ("microphone", "Microfone", "mic", "#FF5E57"),
    ("recognition", "Reconhecimento", "audio-lines", "#0A84FF"),
    ("text", "Texto", "type", "#FF9F0A"),
    ("ai", "Inteligência", "sparkles", "#BF5AF2"),
    ("apps", "Aplicativos", "app-window", "#30B0C7"),
    ("history", "Histórico", "history", "#64D2FF"),
    ("handsfree", "Mãos livres", "keyboard", "#30D158"),
    ("advanced", "Avançado", "sliders", "#636366"),
]


class VisualPreview(Gtk.DrawingArea):
    """Pré-visualização do overlay reagindo ao mic de verdade (ou a uma voz simulada)."""

    def __init__(self, config):
        super().__init__()
        self.set_size_request(-1, 250)
        self.config = config
        self.visual = make_visual(config)
        self.capture = None
        self._last = None
        self.connect("draw", self._draw)
        self.connect("map", lambda *_: self._start())
        self.connect("unmap", lambda *_: self._stop())
        self.add_tick_callback(self._tick)

    def rebuild(self):
        self.visual = make_visual(self.config)
        self.visual.set_state("listening")

    def _start(self):
        mic, _ = resolve_mic(self.config)
        self.capture = AudioCapture(mic, self.config.get("sample_rate", 16000))
        self.capture.start()
        self.visual.set_state("listening")

    def _stop(self):
        if self.capture:
            self.capture.stop()
            self.capture = None

    def _tick(self, _w, clock):
        now = clock.get_frame_time() / 1e6
        dt = min(now - self._last, 0.05) if self._last else 1 / 60
        self._last = now
        if self.capture:
            rms = self.capture.get_rms()
            level = min(rms / 0.012, 1.0) if rms > 0 else 0.0
            if level < 0.02:  # mic mudo: voz simulada para ver o visual se mexer
                level = 0.35 + 0.25 * abs(math.sin(now * 1.7))
            self.visual.set_level(level)
            if self.config.get("overlay_style") == "bars":
                bands = spectrum_bands(self.capture.recent_samples())
                if bands.max() < 0.05:
                    i = np.arange(32)
                    bands = 0.3 + 0.3 * np.abs(np.sin(i * 0.45 + now * 3))
                self.visual.set_bands(bands)
        self.visual.advance(dt)
        self.queue_draw()
        return True

    def _draw(self, w, cr):
        width, height = w.get_allocated_width(), w.get_allocated_height()
        rounded_rect(cr, 0, 0, width, height, 12)
        cr.clip()
        g = cairo.LinearGradient(0, 0, width, height)
        g.add_color_stop_rgb(0, 0.10, 0.11, 0.15)
        g.add_color_stop_rgb(1, 0.16, 0.13, 0.20)
        cr.set_source(g)
        cr.paint()
        self.visual.draw(cr, width / 2, height / 2)
        return False


class LevelMeter(Gtk.DrawingArea):
    """Barra fina de nível (dBFS) do mic selecionado, ao vivo."""

    def __init__(self, get_mic, sample_rate):
        super().__init__()
        self.set_size_request(220, 8)
        self.set_valign(Gtk.Align.CENTER)
        self.get_mic = get_mic
        self.sr = sample_rate
        self.capture = None
        self.level = 0.0
        self.connect("draw", self._draw)
        self.connect("map", lambda *_: self.restart())
        self.connect("unmap", lambda *_: self.stop())
        self.add_tick_callback(self._tick)

    def restart(self):
        self.stop()
        self.capture = AudioCapture(self.get_mic(), self.sr)
        self.capture.start()

    def stop(self):
        if self.capture:
            self.capture.stop()
            self.capture = None

    def _tick(self, *_):
        target = (rms_db(self.capture.get_rms()) + 80) / 80 if self.capture else 0
        self.level += (max(0.0, min(target, 1.0)) - self.level) * 0.35
        self.queue_draw()
        return True

    def _draw(self, w, cr):
        width, height = w.get_allocated_width(), w.get_allocated_height()
        rounded_rect(cr, 0, 0, width, height, height / 2)
        cr.set_source_rgba(1, 1, 1, 0.10)
        cr.fill()
        if self.level > 0.01:
            g = cairo.LinearGradient(0, 0, width, 0)
            g.add_color_stop_rgb(0, 0.19, 0.82, 0.35)
            g.add_color_stop_rgb(0.75, 1.0, 0.78, 0.24)
            g.add_color_stop_rgb(1, 1.0, 0.33, 0.33)
            rounded_rect(cr, 0, 0, width * self.level, height, height / 2)
            cr.set_source(g)
            cr.fill()
        return False


class SettingsWindow(Gtk.Window):
    def __init__(self, config, page="general"):
        Gtk.Window.__init__(self, title="Ajustes do Whisper")
        self.set_default_size(900, 640)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.config = config
        self._save_id = 0
        self._critical_changed = False
        t.apply_theme(self.get_screen(), config)
        try:
            self.set_icon(t._svg_pixbuf(
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" '
                f'fill="{t.ui_accent(config)}"/><g transform="translate(5 5) scale(0.5833)" fill="none" stroke="#fff" '
                f'stroke-width="2.3" stroke-linecap="round">{t.ICONS["mic"]}</g></svg>', 64))
        except Exception as e:
            _debug_log(f"Ícone da janela: {e}")

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(root)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.get_style_context().add_class("sidebar")
        side.set_size_request(220, -1)
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand.set_margin_top(18)
        brand.set_margin_bottom(8)
        brand.set_margin_start(20)
        brand.pack_start(t.tile_icon("mic", t.ui_accent(config), 28), False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        names.pack_start(t.label("JRWhisper", "row-title"), False, False, 0)
        names.pack_start(t.label("Ditado por voz", "row-subtitle"), False, False, 0)
        brand.pack_start(names, False, False, 0)
        side.pack_start(brand, False, False, 0)

        self.sidebar = Gtk.ListBox()
        self.sidebar.get_style_context().add_class("sidebar")
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)
        for pid, plabel, picon, pcolor in PAGES:
            row = Gtk.ListBoxRow()
            row.page_id = pid
            h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            h.pack_start(t.tile_icon(picon, pcolor), False, False, 0)
            h.pack_start(t.label(plabel, "sidebar-label"), False, False, 0)
            row.add(h)
            self.sidebar.add(row)
            self.stack.add_named(getattr(self, f"page_{pid}")(), pid)
        self.sidebar.connect("row-selected", lambda lb, r: r and self.stack.set_visible_child_name(r.page_id))
        side.pack_start(self.sidebar, True, True, 0)
        root.pack_start(side, False, False, 0)
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.get_style_context().add_class("sidebar-sep")
        root.pack_start(sep, False, False, 0)
        root.pack_start(self.stack, True, True, 0)

        self.connect("destroy", self._on_destroy)
        idx = [p[0] for p in PAGES].index(page) if page in [p[0] for p in PAGES] else 0
        self.sidebar.select_row(self.sidebar.get_row_at_index(idx))

    # ── persistência ───────────────────────────────────────────────
    def set(self, key, value):
        if self.config.get(key) == value:
            return
        self.config[key] = value
        if key in CRITICAL_KEYS:
            self._critical_changed = True
            self._show_restart_callout()
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(350, self._flush)

    def _flush(self):
        self._save_id = 0
        save_config(self.config)
        return False

    def _on_destroy(self, *_):
        if self._save_id:
            GLib.source_remove(self._save_id)
            self._flush()
        Gtk.main_quit()

    # ── helpers de UI ──────────────────────────────────────────────
    def _feature_gate(self, box, key, title, description):
        """Switch mestre: com o recurso desligado, o resto da página fica oculto."""
        lb = t.group(box)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        def toggle(on):
            self.set(key, on)
            content.set_visible(on)
        t.switch_row(lb, title, description, self.config.get(key), toggle)
        box.pack_start(content, False, False, 0)
        content.set_no_show_all(False)
        GLib.idle_add(lambda: content.set_visible(bool(self.config.get(key))))
        return content

    def _dialog(self, title, build, ok_label="Salvar"):
        """Folha modal simples; build(box) monta campos e devolve uma função que lê os valores."""
        dlg = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dlg.set_default_size(460, -1)
        area = dlg.get_content_area()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(18)
        area.add(box)
        read = build(box)
        dlg.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        ok = dlg.add_button(ok_label, Gtk.ResponseType.OK)
        ok.get_style_context().add_class("btn-primary")
        dlg.show_all()
        result = read() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        return result

    def _shortcut_row(self, lb, title, subtitle, name, command):
        current = shortcuts.get_binding(command)
        keycap = t.label(shortcuts.pretty(current), "keycap")
        btn = Gtk.Button(label="Alterar…")
        box = Gtk.Box(spacing=10)
        box.pack_start(keycap, False, False, 0)
        box.pack_start(btn, False, False, 0)

        def record(_b):
            accel = self._record_accel(title)
            if accel:
                try:
                    shortcuts.set_binding(name, command, accel)
                    keycap.set_text(shortcuts.pretty(accel))
                except Exception as e:
                    self._error("Não foi possível gravar o atalho", str(e))
        btn.connect("clicked", record)
        t.row(lb, title, subtitle, box)

    def _record_accel(self, what):
        dlg = Gtk.Dialog(title="Novo atalho", transient_for=self, modal=True)
        dlg.set_default_size(360, 160)
        box = dlg.get_content_area()
        box.set_spacing(10)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(22)
        box.pack_start(t.label(what, "row-title", xalign=0.5), False, False, 0)
        cap = t.label("Pressione a combinação…", "keycap", xalign=0.5)
        box.pack_start(cap, False, False, 6)
        box.pack_start(t.label("Esc cancela", "row-subtitle", xalign=0.5), False, False, 0)
        result = {}

        def on_key(_w, ev):
            mods = ev.state & Gtk.accelerator_get_default_mod_mask()
            if ev.keyval == Gdk.KEY_Escape and not mods:
                dlg.response(Gtk.ResponseType.CANCEL)
                return True
            if Gtk.accelerator_valid(ev.keyval, mods) and mods:
                accel = Gtk.accelerator_name(Gdk.keyval_to_lower(ev.keyval), mods)
                result["accel"] = accel.replace("<Mod4>", "<Super>")
                cap.set_text(shortcuts.pretty(result["accel"]))
                GLib.timeout_add(350, lambda: dlg.response(Gtk.ResponseType.OK) or False)
            return True
        dlg.connect("key-press-event", on_key)
        dlg.show_all()
        ok = dlg.run() == Gtk.ResponseType.OK
        dlg.destroy()
        return result.get("accel") if ok else None

    def _error(self, title, text):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR,
                              buttons=Gtk.ButtonsType.OK, text=title)
        d.format_secondary_text(text)
        d.run()
        d.destroy()

    def _confirm(self, title, text, ok_label):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.NONE, text=title)
        d.format_secondary_text(text)
        d.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        b = d.add_button(ok_label, Gtk.ResponseType.OK)
        b.get_style_context().add_class("btn-danger")
        ok = d.run() == Gtk.ResponseType.OK
        d.destroy()
        return ok

    def _kv_editor(self, box, title, footer, key, key_ph, val_ph, multiline=False):
        """Lista editável gatilho → valor (dicionário, atalhos de texto)."""
        lb = t.group(box, title, footer)

        def save():
            data = {}
            for r in lb.get_children():
                if hasattr(r, "read"):
                    k, v = r.read()
                    if k.strip() and v.strip():
                        data[k.strip().lower()] = v.strip() if not multiline else v.rstrip()
            self.set(key, data)

        def add_row(k="", v=""):
            r = Gtk.ListBoxRow()
            r.set_activatable(False)
            h = Gtk.Box(spacing=10)
            ek = Gtk.Entry(text=k, placeholder_text=key_ph)
            ek.set_width_chars(16)
            if multiline:
                buf = Gtk.TextBuffer(text=v)
                ev = Gtk.TextView(buffer=buf)
                ev.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
                ev.set_size_request(-1, 54)
                buf.connect("changed", lambda *_: save())
                read_v = lambda: buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
            else:
                ev = Gtk.Entry(text=v, placeholder_text=val_ph)
                ev.connect("changed", lambda *_: save())
                read_v = ev.get_text
            ek.connect("changed", lambda *_: save())
            rm = Gtk.Button()
            rm.add(t.icon("trash", 14, "#98989D"))
            rm.get_style_context().add_class("btn-flat")
            rm.set_tooltip_text("Remover")
            rm.connect("clicked", lambda _b: (lb.remove(r), save()))
            h.pack_start(ek, False, False, 0)
            h.pack_start(t.label("→", "dim"), False, False, 0)
            h.pack_start(ev, True, True, 0)
            h.pack_start(rm, False, False, 0)
            r.add(h)
            r.read = lambda: (ek.get_text(), read_v())
            lb.insert(r, len(lb.get_children()) - 1)
            r.show_all()
            return ek

        add = Gtk.ListBoxRow()
        add.set_activatable(False)
        b = Gtk.Button()
        hb = Gtk.Box(spacing=6)
        hb.pack_start(t.icon("plus", 14, t.ui_accent(self.config)), False, False, 0)
        hb.pack_start(t.label("Adicionar"), False, False, 0)
        b.add(hb)
        b.get_style_context().add_class("btn-flat")
        b.set_halign(Gtk.Align.START)
        b.connect("clicked", lambda _b: add_row().grab_focus())
        add.add(b)
        lb.add(add)
        for k, v in (self.config.get(key) or {}).items():
            add_row(k, v)

    # ── páginas ────────────────────────────────────────────────────
    def page_general(self):
        root, box = t.page("Geral", "O essencial do ditado.")
        lb = t.group(box, "Ditado")
        self._shortcut_row(lb, "Atalho de ditado", "Toque para ditar; aperte de novo para cancelar.",
                           "Dictate", DICTATE_CMD)
        t.choice_row(lb, "Idioma", None, [("pt", "Português"), ("en", "Inglês"), ("es", "Espanhol"),
                                          ("auto", "Detectar automaticamente")],
                     self.config.get("language", "pt"), lambda v: self.set("language", v))
        t.switch_row(lb, "Sons de início e fim", "Um toque discreto ao começar a ouvir e ao colar.",
                     self.config.get("sounds"), lambda v: self.set("sounds", v))

        lb = t.group(box, "Serviço", "O serviço mantém o modelo na memória (GPU) para o ditado começar sem espera.")
        running = is_daemon_running()
        sw = Gtk.Switch()
        sw.set_active(running)
        row = t.row(lb, "Manter modelo carregado", "Em execução" if running else "Parado", sw)

        def toggle_daemon(s, _p):
            on = s.get_active()
            cmd = ["systemctl", "--user", "enable" if on else "disable", "--now", "dictate-daemon"]
            subprocess.run(cmd, capture_output=True, timeout=15)
            row.subtitle.set_text("Iniciando…" if on else "Parado")
        sw.connect("notify::active", toggle_daemon)
        box.pack_start(t.label("JRWhisperLinux · MIT · 100% local, exceto a reescrita por IA na nuvem (opcional).",
                               "group-footer"), False, False, 0)
        return root

    def page_appearance(self):
        root, box = t.page("Aparência", "Como o Whisper aparece enquanto você dita.")
        self.preview = VisualPreview(self.config)
        frame = Gtk.Box()
        frame.pack_start(self.preview, True, True, 0)
        box.pack_start(frame, False, False, 0)

        def apply(key, value):
            self.set(key, value)
            self.preview.rebuild()
            if key in ("accent", "accent_custom"):
                t.apply_theme(self.get_screen(), self.config)

        lb = t.group(box, "Visual")
        t.row(lb, "Estilo", None, t.segmented(list(VISUAL_LABELS.items()), self.config.get("overlay_style", "orb"),
                                              lambda v: apply("overlay_style", v)))

        def accent(key, custom):
            if custom:
                self.config["accent_custom"] = custom
            apply("accent", key)
        t.row(lb, "Cor de destaque", None, t.accent_picker(self.config.get("accent", "indigo"), accent,
                                                           self.config.get("accent_custom")))
        t.row(lb, "Tamanho", None, t.segmented([("s", "Pequeno"), ("m", "Médio"), ("l", "Grande")],
                                               self.config.get("overlay_size", "m"),
                                               lambda v: apply("overlay_size", v)))
        t.row(lb, "Posição", "Onde o overlay aparece no monitor do mouse.",
              t.segmented([("bottom", "Embaixo"), ("center", "Centro"), ("top", "Topo")],
                          self.config.get("overlay_position", "bottom"), lambda v: apply("overlay_position", v)))

        lb = t.group(box, "Detalhes")
        t.slider_row(lb, "Brilho", "Intensidade do halo do orbe e das ondas.", 0, 1, 0.05,
                     self.config.get("overlay_glow", 0.8), lambda v: f"{int(round(v * 100))}%",
                     lambda v: apply("overlay_glow", round(v, 2)))
        t.switch_row(lb, "Mostrar texto", "A transcrição aparece junto do visual enquanto você fala.",
                     self.config.get("overlay_show_text", True), lambda v: apply("overlay_show_text", v))
        t.switch_row(lb, "Reduzir movimento", "Sem rotação nem pulsação; só reage ao volume.",
                     self.config.get("reduce_motion"), lambda v: apply("reduce_motion", v))
        return root

    def page_microphone(self):
        root, box = t.page("Microfone", "Entrada de áudio e calibração.")
        lb = t.group(box, "Entrada",
                     "Se o microfone escolhido estiver desconectado, o ditado usa o padrão do sistema e avisa.")
        options = [("@DEFAULT_SOURCE@", "Padrão do sistema")] + [(n, friendly_mic_name(n)) for n in list_source_names()]
        self.mic_combo = t.choice_row(lb, "Microfone", None, options,
                                      self.config.get("mic_device", "@DEFAULT_SOURCE@"), self._on_mic_changed)
        self.meter = LevelMeter(self._selected_mic, self.config.get("sample_rate", 16000))
        t.row(lb, "Nível", "Fale para ver o sinal chegando.", self.meter)

        lb = t.group(box, "Calibração", "Cada microfone guarda a própria calibração. Sem calibração, o ditado mede o "
                                        "ruído a cada uso.")
        self.cal_label = t.label("", "row-subtitle")
        btn = Gtk.Button(label="Calibrar…")
        btn.get_style_context().add_class("btn-primary")
        btn.connect("clicked", self._open_calibration)
        cal_box = Gtk.Box(spacing=12)
        cal_box.pack_start(self.cal_label, False, False, 0)
        cal_box.pack_start(btn, False, False, 0)
        t.row(lb, "Estado", None, cal_box)
        self._refresh_cal()

        lb = t.group(box, "Processamento")
        t.switch_row(lb, "Supressão de ruído", "Isola a voz com RNNoise antes de transcrever.",
                     self.config.get("noise_suppression", True), lambda v: self.set("noise_suppression", v))
        t.switch_row(lb, "Abaixar o som ao ditar", "Reduz o volume do sistema enquanto você fala.",
                     self.config.get("audio_ducking", True), lambda v: self.set("audio_ducking", v))
        t.slider_row(lb, "Volume durante o ditado", None, 0, 1, 0.05, self.config.get("ducking_volume", 0.2),
                     lambda v: f"{int(round(v * 100))}%", lambda v: self.set("ducking_volume", round(v, 2)))
        return root

    def _selected_mic(self):
        mic = self.config.get("mic_device", "@DEFAULT_SOURCE@")
        return (default_source_name() or mic) if mic == "@DEFAULT_SOURCE@" else mic

    def _on_mic_changed(self, mic):
        self.set("mic_device", mic)
        self.meter.restart()
        self._refresh_cal()

    def _refresh_cal(self):
        state, cal = calibration_state(self.config, self._selected_mic())
        text, color = {
            "ok": (f"Calibrado · limiar {cal['threshold']:.4f}" if cal else "", t.SUCCESS),
            "stale": ("Ganho do mic mudou: recalibre", t.WARNING),
            "none": ("Automático", "#98989D"),
        }[state]
        self.cal_label.set_markup(f"<span foreground='{color}'>{GLib.markup_escape_text(text)}</span>")

    def _open_calibration(self, _b):
        def saved():
            self._refresh_cal()
        win = CalibrationWindow(self.config, mic=self._selected_mic(), on_saved=saved)
        win.set_transient_for(self)
        win.set_modal(True)
        self.meter.stop()  # libera o mic para a janela de calibração
        win.connect("destroy", lambda *_: self.meter.restart())
        win.show_all()

    def page_recognition(self):
        root, box = t.page("Reconhecimento", "Modelo Whisper e quando encerrar a gravação.")
        self.restart_box = Gtk.Box(spacing=12)
        self.restart_box.get_style_context().add_class("callout")
        self.restart_box.pack_start(t.label("Reinicie o serviço para aplicar a mudança de modelo, idioma ou prompt.",
                                            wrap=True), True, True, 0)
        rb = Gtk.Button(label="Reiniciar agora")
        rb.get_style_context().add_class("btn-primary")
        rb.connect("clicked", self._restart_daemon)
        self.restart_box.pack_start(rb, False, False, 0)
        self.restart_box.set_no_show_all(True)
        box.pack_start(self.restart_box, False, False, 0)

        lb = t.group(box, "Modelo", "Modelos maiores erram menos e usam mais GPU. turbo é o melhor custo-benefício.")
        models = [("tiny", "tiny"), ("base", "base"), ("small", "small"), ("medium", "medium"),
                  ("turbo", "large-v3-turbo"), ("large-v3", "large-v3")]
        t.choice_row(lb, "Modelo Whisper", None, models, self.config.get("model", "medium"),
                     lambda v: self.set("model", v))

        lb = t.group(box, "Vocabulário", "Nomes, siglas e jargões que o Whisper deve reconhecer, separados por vírgula.")
        r = Gtk.ListBoxRow()
        r.set_activatable(False)
        buf = Gtk.TextBuffer(text=self.config.get("initial_prompt", ""))
        tv = Gtk.TextView(buffer=buf)
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        tv.set_size_request(-1, 90)
        buf.connect("changed", lambda b: self.set("initial_prompt", b.get_text(b.get_start_iter(),
                                                                                 b.get_end_iter(), True).strip()))
        r.add(tv)
        lb.add(r)

        lb = t.group(box, "Gravação")
        t.slider_row(lb, "Pausa para encerrar", "Silêncio contínuo que conclui o ditado.", 0.5, 5, 0.1,
                     self.config.get("silence_duration", 1.7), lambda v: f"{v:.1f} s",
                     lambda v: self.set("silence_duration", round(v, 1)))
        t.slider_row(lb, "Esperar fala por", "Tempo máximo até você começar a falar.", 5, 60, 1,
                     self.config.get("listen_timeout", 15), lambda v: f"{int(v)} s",
                     lambda v: self.set("listen_timeout", int(v)))
        t.slider_row(lb, "Duração máxima", None, 15, 300, 5, self.config.get("max_duration", 60),
                     lambda v: f"{int(v)} s", lambda v: self.set("max_duration", int(v)))
        return root

    def _show_restart_callout(self):
        if is_daemon_running() and hasattr(self, "restart_box"):
            self.restart_box.show_all()

    def _restart_daemon(self, btn):
        self._flush()
        btn.set_sensitive(False)
        btn.set_label("Reiniciando…")

        def work():
            r = subprocess.run(["systemctl", "--user", "restart", "dictate-daemon"], capture_output=True, timeout=20)
            GLib.idle_add(done, r.returncode == 0)

        def done(ok):
            btn.set_sensitive(True)
            btn.set_label("Reiniciar agora")
            if ok:
                self.restart_box.hide()
            else:
                self._error("Não foi possível reiniciar o serviço", "Veja: systemctl --user status dictate-daemon")
        threading.Thread(target=work, daemon=True).start()

    def page_text(self):
        root, box = t.page("Texto", "Pontuação, correções e atalhos de texto.")
        lb = t.group(box, "Formatação")
        t.switch_row(lb, "Formatação automática", "Maiúsculas, espaços e ponto final.",
                     self.config.get("enable_formatting", True), lambda v: self.set("enable_formatting", v))
        t.switch_row(lb, "Remover hesitações", "“hmm”, “ahn”, “éh”…",
                     self.config.get("remove_fillers", True), lambda v: self.set("remove_fillers", v))
        t.switch_row(lb, "Comandos de voz", "“vírgula”, “ponto final”, “nova linha”, “novo parágrafo”…",
                     self.config.get("voice_commands", True), lambda v: self.set("voice_commands", v))
        self._kv_editor(box, "Dicionário", "Corrige grafias recorrentes: o que o Whisper escreve → como deve ficar.",
                        "word_overrides", "escrito", "corrigido")
        self._kv_editor(box, "Atalhos de texto", "Diga o gatilho e o texto inteiro entra no lugar. Ex.: “minha assinatura”.",
                        "snippets", "gatilho falado", "texto", multiline=True)
        return root

    def page_ai(self):
        root, box = t.page("Inteligência", "Reescreve o ditado com um modelo de linguagem antes de colar.")
        content = self._feature_gate(box, "ai_enabled", "Reescrita com IA",
                                     "Corrigir, transformar em e-mail, traduzir, resumir em tópicos.")

        lb = t.group(content, "Provedor")
        provider_rows = {}
        t.row(lb, "Serviço", None, t.segmented([("nvidia", "NVIDIA NIM"), ("ollama", "Ollama (local)")],
                                               self.config.get("ai_provider", "nvidia"),
                                               lambda v: (self.set("ai_provider", v), self._ai_provider_rows(provider_rows))))
        from .. import secrets
        key_label = t.label(secrets.masked(secrets.get_key("nvidia")), "dim")
        kb = Gtk.Box(spacing=10)
        kb.pack_start(key_label, False, False, 0)
        change = Gtk.Button(label="Alterar…")

        def change_key(_b):
            def build(b):
                b.pack_start(t.label("Chave de API da NVIDIA (nvapi-…). Fica no chaveiro do sistema.", wrap=True),
                             False, False, 0)
                e = Gtk.Entry(visibility=False, placeholder_text="nvapi-…")
                b.pack_start(e, False, False, 0)
                return e.get_text
            key = self._dialog("Chave da NVIDIA", build)
            if key:
                secrets.set_key("nvidia", key)
                key_label.set_text(secrets.masked(key))
        change.connect("clicked", change_key)
        kb.pack_start(change, False, False, 0)
        provider_rows["nvidia_key"] = t.row(lb, "Chave de API", "Guardada no chaveiro do sistema (gnome-keyring).", kb)
        self.ai_model_combo = t.PopupChoice()
        self.ai_model_combo.append(self.config.get("ai_model"), self.config.get("ai_model"))
        self.ai_model_combo.set_active_id(self.config.get("ai_model"))
        self.ai_model_combo.connect("changed", lambda c: c.get_active_id() and self.set("ai_model", c.get_active_id()))
        provider_rows["nvidia_model"] = t.row(lb, "Modelo", "Modelos rápidos deixam o ditado mais fluido.",
                                              self.ai_model_combo)
        self._load_models_async()
        provider_rows["ollama_url"] = t.row(lb, "Endereço do Ollama", None, self._entry(
            "ai_ollama_url", "http://localhost:11434"))
        provider_rows["ollama_model"] = t.row(lb, "Modelo do Ollama", None, self._entry("ai_ollama_model", "llama3.2"))
        test_label = t.label("", "row-subtitle")
        tb = Gtk.Box(spacing=10)
        tb.pack_start(test_label, False, False, 0)
        test = Gtk.Button(label="Testar")
        test.connect("clicked", lambda _b: self._test_ai(test_label))
        tb.pack_start(test, False, False, 0)
        t.row(lb, "Conexão", None, tb)
        GLib.idle_add(self._ai_provider_rows, provider_rows)

        lb = t.group(content, "Modos", "Use um modo dizendo “modo e-mail, …” no começo do ditado, por atalho "
                                       "próprio ou como padrão de um aplicativo.")
        for mode in self.config.get("ai_modes", []):
            self._mode_row(lb, mode)
        opts = [("", "Nenhum (só quando pedir)")] + [(m["id"], m["name"]) for m in self.config.get("ai_modes", [])]
        lb2 = t.group(content, "Uso")
        t.choice_row(lb2, "Modo padrão", "Aplicado em todo ditado, exceto quando um app define outro.",
                     opts, self.config.get("ai_default_mode", ""), lambda v: self.set("ai_default_mode", v))
        t.switch_row(lb2, "Ativar por voz", "Diga “modo <nome>” no começo: “modo e-mail, preciso remarcar…”.",
                     self.config.get("ai_voice_prefix", True), lambda v: self.set("ai_voice_prefix", v))
        content.pack_start(t.label("Privacidade: com a NVIDIA NIM o texto ditado vai para a nuvem da NVIDIA. "
                                   "Com o Ollama tudo fica no seu computador. Se a IA falhar ou demorar, "
                                   "o texto original é colado.", "group-footer", wrap=True), False, False, 0)
        return root

    def _entry(self, key, placeholder):
        e = Gtk.Entry(text=self.config.get(key) or "", placeholder_text=placeholder)
        e.set_width_chars(26)
        e.connect("changed", lambda w: self.set(key, w.get_text().strip()))
        return e

    def _ai_provider_rows(self, rows):
        ollama = self.config.get("ai_provider") == "ollama"
        for name, r in rows.items():
            r.set_visible(name.startswith("ollama") == ollama)
        return False

    def _load_models_async(self):
        def work():
            try:
                from .. import ai
                models = ai.list_models(self.config)
            except Exception as e:
                _debug_log(f"IA: lista de modelos falhou: {e}")
                models = []
            GLib.idle_add(fill, models)

        def fill(models):
            current = self.config.get("ai_model")
            for m in models:
                if m != current:
                    self.ai_model_combo.append(m, m)
        threading.Thread(target=work, daemon=True).start()

    def _test_ai(self, label):
        label.set_text("Testando…")

        def work():
            try:
                from .. import ai
                ms, sample = ai.test(self.config)
                msg, color = f"OK · {ms:.0f} ms", t.SUCCESS
            except Exception as e:
                msg, color = f"Falhou: {str(e)[:60]}", t.DANGER
            GLib.idle_add(lambda: label.set_markup(
                f"<span foreground='{color}'>{GLib.markup_escape_text(msg)}</span>") or False)
        threading.Thread(target=work, daemon=True).start()

    def _mode_row(self, lb, mode):
        sw = Gtk.Switch()
        sw.set_valign(Gtk.Align.CENTER)
        sw.set_active(mode.get("enabled", True))
        edit = Gtk.Button(label="Editar")
        box = Gtk.Box(spacing=10)
        box.pack_start(edit, False, False, 0)
        box.pack_start(sw, False, False, 0)
        row = t.row(lb, mode["name"], f"dictate --mode {mode['id']}", box)

        def save_modes():
            self.set("ai_modes", copy.deepcopy(self.config["ai_modes"]))

        def toggle(s, _p):
            mode["enabled"] = s.get_active()
            save_modes()
        sw.connect("notify::active", toggle)

        def do_edit(_b):
            def build(b):
                name = Gtk.Entry(text=mode["name"])
                b.pack_start(t.label("Nome"), False, False, 0)
                b.pack_start(name, False, False, 0)
                b.pack_start(t.label("Instrução para a IA"), False, False, 0)
                buf = Gtk.TextBuffer(text=mode["prompt"])
                tv = Gtk.TextView(buffer=buf)
                tv.set_wrap_mode(Gtk.WrapMode.WORD)
                tv.set_size_request(420, 120)
                b.pack_start(tv, True, True, 0)
                return lambda: (name.get_text().strip(), buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True))
            res = self._dialog(f"Modo {mode['name']}", build)
            if res and res[0]:
                mode["name"], mode["prompt"] = res
                row.get_child().get_children()[0].get_children()[0].set_text(mode["name"])
                save_modes()
        edit.connect("clicked", do_edit)

    def page_apps(self):
        root, box = t.page("Aplicativos", "Regras por aplicativo: como colar e formatar em cada janela.")
        content = self._feature_gate(box, "profiles_enabled", "Perfis por aplicativo",
                                     "Terminais colam com Ctrl+Shift+V e sem ponto final; e-mail usa pontuação "
                                     "completa…")
        lb = t.group(content, "Perfis", "O primeiro perfil cuja regra combina com a classe da janela ativa é usado. "
                                        "Use | para várias classes (ex.: kitty|guake).")
        self.profiles_lb = lb
        for p in self.config.get("profiles", []):
            self._profile_row(lb, p)
        add = Gtk.Button(label="Adicionar perfil…")
        add.set_halign(Gtk.Align.START)
        add.connect("clicked", lambda _b: self._edit_profile(None))
        content.pack_start(add, False, False, 0)
        return root

    def _profile_summary(self, p):
        bits = [p["match"], {"ctrl+v": "Ctrl+V", "ctrl+shift+v": "Ctrl+Shift+V", "type": "digitar"}[p["paste"]]]
        if not p.get("formatting", True):
            bits.append("sem formatação")
        elif not p.get("final_period", True):
            bits.append("sem ponto final")
        if p.get("ai_mode"):
            bits.append(f"IA: {p['ai_mode']}")
        return " · ".join(bits)

    def _profile_row(self, lb, p):
        edit = Gtk.Button(label="Editar")
        edit.connect("clicked", lambda _b: self._edit_profile(p))
        r = t.row(lb, p["name"], self._profile_summary(p), edit)
        r.profile = p
        r.show_all()

    def _rebuild_profiles(self):
        for r in self.profiles_lb.get_children():
            self.profiles_lb.remove(r)
        for p in self.config["profiles"]:
            self._profile_row(self.profiles_lb, p)

    def _edit_profile(self, profile):
        p = dict(profile or {"match": "", "name": "", "paste": "ctrl+v", "formatting": True,
                             "final_period": True, "capitalize": True, "ai_mode": ""})

        def build(b):
            fields = {}
            for key, lbl, ph in (("name", "Nome", "Ex.: Terminais"),
                                 ("match", "Classe da janela", "Ex.: kitty|guake")):
                b.pack_start(t.label(lbl), False, False, 0)
                fields[key] = Gtk.Entry(text=p[key], placeholder_text=ph)
                b.pack_start(fields[key], False, False, 0)
            b.pack_start(t.label("Descubra a classe com: xdotool getactivewindow getwindowclassname",
                                 "row-subtitle", wrap=True), False, False, 0)
            lb = t.group(b)
            paste = t.choice_row(lb, "Colar com", None, [("ctrl+v", "Ctrl+V"), ("ctrl+shift+v", "Ctrl+Shift+V"),
                                                          ("type", "Digitar o texto")], p["paste"], lambda v: None)
            switches = {k: t.switch_row(lb, lbl, None, p.get(k, True), lambda v: None)
                        for k, lbl in (("formatting", "Formatação"), ("final_period", "Ponto final"),
                                       ("capitalize", "Maiúscula inicial"))}
            modes = [("", "Nenhum")] + [(m["id"], m["name"]) for m in self.config.get("ai_modes", [])]
            ai = t.choice_row(lb, "Modo de IA", None, modes, p.get("ai_mode", ""), lambda v: None)
            if profile is not None:
                rm = Gtk.Button(label="Remover perfil")
                rm.get_style_context().add_class("btn-danger")
                rm.set_halign(Gtk.Align.START)

                def remove(_b):
                    self.config["profiles"].remove(profile)
                    self.set("profiles", copy.deepcopy(self.config["profiles"]))
                    self._rebuild_profiles()
                    b.get_toplevel().response(Gtk.ResponseType.CANCEL)
                rm.connect("clicked", remove)
                b.pack_start(rm, False, False, 0)
            return lambda: {**p, "name": fields["name"].get_text().strip() or fields["match"].get_text().strip(),
                            "match": fields["match"].get_text().strip(), "paste": paste.get_active_id(),
                            "ai_mode": ai.get_active_id() or "",
                            **{k: s.get_active() for k, s in switches.items()}}
        res = self._dialog("Perfil de aplicativo", build)
        if not res or not res["match"]:
            return
        profiles = self.config.setdefault("profiles", [])
        if profile is not None and profile in profiles:
            profiles[profiles.index(profile)] = res
        else:
            profiles.append(res)
        self.set("profiles", copy.deepcopy(profiles))
        self._rebuild_profiles()

    def page_history(self):
        root, box = t.page("Histórico", "Ditados anteriores, só no seu computador.")
        content = self._feature_gate(box, "history_enabled", "Guardar histórico",
                                     "Busque e recole ditados antigos.")
        lb = t.group(content)
        t.choice_row(lb, "Manter por", None, [("7", "7 dias"), ("30", "30 dias"), ("90", "90 dias"),
                                              ("365", "1 ano"), ("0", "Sempre")],
                     str(self.config.get("history_retention_days", 30)),
                     lambda v: self.set("history_retention_days", int(v)))
        self._shortcut_row(lb, "Busca rápida", "Abre uma busca estilo Spotlight; Enter cola.",
                           "Dictate: histórico", f"{DICTATE_CMD} --history")

        search = Gtk.SearchEntry(placeholder_text="Buscar no histórico")
        content.pack_start(search, False, False, 0)
        self.history_lb = t.group(content)
        clear = Gtk.Button(label="Apagar histórico…")
        clear.get_style_context().add_class("btn-danger")
        clear.set_halign(Gtk.Align.START)
        content.pack_start(clear, False, False, 0)

        def refresh(*_):
            for r in self.history_lb.get_children():
                self.history_lb.remove(r)
            items = history.load(query=search.get_text(), limit=60)
            if not items:
                t.row(self.history_lb, "Nada por aqui ainda" if not search.get_text() else "Nenhum resultado")
            for rec in items:
                copy_btn = Gtk.Button()
                copy_btn.add(t.icon("copy", 14, "#98989D"))
                copy_btn.get_style_context().add_class("btn-flat")
                copy_btn.set_tooltip_text("Copiar")
                copy_btn.connect("clicked", lambda _b, txt=rec.get("text", ""): Gtk.Clipboard.get(
                    Gdk.SELECTION_CLIPBOARD).set_text(txt, -1))
                meta = history.when(rec.get("ts", 0)) + (f" · {rec['app']}" if rec.get("app") else "") + \
                    (f" · IA: {rec['mode']}" if rec.get("mode") else "")
                text = rec.get("text", "")
                t.row(self.history_lb, text if len(text) < 140 else text[:137] + "…", meta, copy_btn)
            self.history_lb.show_all()
        search.connect("search-changed", refresh)
        self.connect("map", refresh)

        def do_clear(_b):
            if self._confirm("Apagar todo o histórico?", "Os ditados guardados serão removidos deste computador.",
                             "Apagar"):
                history.clear()
                refresh()
        clear.connect("clicked", do_clear)
        GLib.idle_add(refresh)
        return root

    def page_handsfree(self):
        root, box = t.page("Mãos livres", "Outros jeitos de ditar além de tocar no atalho.")
        lb = t.group(box, "Segurar para falar",
                     "Com ele ligado, segure o atalho enquanto fala e solte para transcrever. Um toque rápido "
                     "continua funcionando como antes. Só no X11.")
        t.switch_row(lb, "Push-to-talk", None, self.config.get("ptt_enabled"), lambda v: self.set("ptt_enabled", v))
        lb = t.group(box, "Ditado contínuo",
                     "Depois de colar, volta a ouvir. Cada pausa vira um trecho colado. Para com o atalho, com a "
                     "frase de parada ou após o tempo sem fala.")
        t.switch_row(lb, "Mãos livres", None, self.config.get("handsfree_enabled"),
                     lambda v: self.set("handsfree_enabled", v))
        t.slider_row(lb, "Encerrar após", "Tempo sem fala que encerra o modo contínuo.", 5, 120, 5,
                     self.config.get("handsfree_idle_secs", 20), lambda v: f"{int(v)} s",
                     lambda v: self.set("handsfree_idle_secs", int(v)))
        t.row(lb, "Frase de parada", None, self._entry("handsfree_stop_phrase", "parar ditado"))
        return root

    def page_advanced(self):
        root, box = t.page("Avançado", "Ajustes finos. Os padrões funcionam para a maioria.")
        lb = t.group(box, "Detecção de fala", "O limite manual ignora a calibração por microfone. 0 = automático.")
        t.slider_row(lb, "Limite manual", None, 0, 0.02, 0.0005, self.config.get("silence_threshold", 0),
                     lambda v: "Auto" if v == 0 else f"{v:.4f}", lambda v: self.set("silence_threshold", round(v, 4)))
        lb = t.group(box, "Whisper", "Filtros contra alucinações em silêncio e repetições.")
        t.slider_row(lb, "Sem fala acima de", "no_speech_threshold", 0.1, 1.0, 0.05,
                     self.config.get("no_speech_threshold", 0.6), lambda v: f"{v:.2f}",
                     lambda v: self.set("no_speech_threshold", round(v, 2)))
        t.slider_row(lb, "Log-prob mínimo", "log_prob_threshold", -3.0, 0.0, 0.1,
                     self.config.get("log_prob_threshold", -1.0), lambda v: f"{v:.1f}",
                     lambda v: self.set("log_prob_threshold", round(v, 1)))
        t.slider_row(lb, "Taxa de compressão", "compression_ratio_threshold", 1.5, 4.0, 0.1,
                     self.config.get("compression_ratio_threshold", 2.4), lambda v: f"{v:.1f}",
                     lambda v: self.set("compression_ratio_threshold", round(v, 1)))
        lb = t.group(box, "GPU")
        t.slider_row(lb, "VRAM livre mínima", "Abaixo disso o modelo roda na CPU.", 500, 8000, 100,
                     self.config.get("gpu_min_vram_mb", 2500), lambda v: f"{int(v)} MB",
                     lambda v: self.set("gpu_min_vram_mb", int(v)))
        lb = t.group(box, "Manutenção")
        t.button_row(lb, "Logs", "Depuração e erros do ditado.", "Abrir pasta",
                     lambda: subprocess.Popen(["xdg-open", RUNTIME_DIR]))
        t.button_row(lb, "Restaurar padrões", "Volta todos os ajustes ao original. Calibrações são mantidas.",
                     "Restaurar…", self._reset, cls="btn-danger")
        return root

    def _reset(self):
        if not self._confirm("Restaurar todos os ajustes?", "As calibrações de microfone são mantidas.", "Restaurar"):
            return
        keep = {k: self.config[k] for k in ("mic_calibrations",) if k in self.config}
        self.config.clear()
        self.config.update(copy.deepcopy(DEFAULT_CONFIG), **keep)
        self._flush()
        page = self.stack.get_visible_child_name()
        self.disconnect_by_func(self._on_destroy)
        self.destroy()
        SettingsWindow(self.config, page).show_all()
