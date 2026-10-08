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
import time

import cairo
import numpy as np

from gi.repository import Gtk, Gdk, GLib

from .. import history, shortcuts
from ..audio import (SYSTEM_AUDIO, AudioCapture, calibration_state, default_source_name, friendly_mic_name,
                     is_system_audio, list_source_names, resolve_mic, rms_db)
from ..config import DEFAULT_CONFIG, RUNTIME_DIR, _debug_log, save_config
from ..paste import copy_text
from ..transcribe import is_daemon_running
from . import theme as t
from .calibration import CalibrationWindow
from .captionview import CaptionView
from .visuals import VISUAL_LABELS, make_visual, rounded_rect, spectrum_bands

DICTATE_CMD = os.path.expanduser("~/.local/bin/dictate")
AI_CHAINS = [("ollama,nvidia,deepseek", "Local → NVIDIA → DeepSeek"),
             ("ollama,deepseek,nvidia", "Local → DeepSeek → NVIDIA"),
             ("nvidia,deepseek", "Só nuvem: NVIDIA → DeepSeek"),
             ("ollama", "Só local (Ollama)")]
SEND_KEYS = {"Return": "Enter", "ctrl+Return": "Ctrl+Enter", "shift+Return": "Shift+Enter"}

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


class CaptionPreview(Gtk.DrawingArea):
    """Legenda de exemplo correndo com o mesmo desenho do overlay (CaptionView): ajuste vendo o efeito."""
    SAMPLE = ["O navio chega ao porto amanhã de manhã.", "Precisamos descarregar os contêineres antes do meio-dia.",
              "Por favor, confirme a reserva com o terminal.",
              "O despachante já liberou a carga e o armador confirmou a atracação.",
              "Se houver atraso, avise o terminal com antecedência para remarcar a janela.",
              "A estufagem do contêiner refrigerado começa às sete da manhã."]
    EVERY = 1.6  # s por frase: fala rápida, como nas legendas de verdade

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.rebuild()
        self._last, self._t = None, 0.0
        self.connect("draw", self._draw)
        self.add_tick_callback(self._tick)

    def rebuild(self):
        self.view = CaptionView(self.config, 1.0, t.hex_to_rgb(t.ui_accent(self.config)))
        lines = min(int(self.config.get("caption_lines", 8)), 8)
        self.set_size_request(-1, int(2 * self.view.pad + self.view.line_h * lines))
        self.queue_resize()

    def _tick(self, _w, clock):
        now = clock.get_frame_time() / 1e6
        dt = min(now - self._last, 0.05) if self._last else 1 / 60
        self._last = now
        self._t += dt
        i, frac = divmod(self._t / self.EVERY, 1.0)
        n = int(i) % (len(self.SAMPLE) * 3)  # recomeça depois de 3 voltas para a lista não crescer sem fim
        done = [self.SAMPLE[k % len(self.SAMPLE)] for k in range(n)]
        nxt = self.SAMPLE[n % len(self.SAMPLE)]
        self.view.set_text(done[-12:], nxt[: max(1, int(len(nxt) * min(frac * 1.4, 1.0)))] + "…" if frac < 0.7 else "")
        if frac >= 0.7:  # frase fechou: entra como bloco
            self.view.set_text((done + [nxt])[-12:], "")
        self.view.advance(dt)
        self.queue_draw()
        return True

    def _draw(self, w, cr):
        self.view.draw(cr, 0, 0, w.get_allocated_width(), w.get_allocated_height())
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
        t.apply_theme(self.get_screen(), config)

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(root)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.get_style_context().add_class("sidebar")
        side.set_size_request(220, -1)
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand.set_margin_top(18)
        brand.set_margin_bottom(8)
        brand.set_margin_start(20)
        brand.pack_start(t.app_icon(34), False, False, 0)
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
        self._shortcut_row(lb, "Atalho de ditado", "Toque para ditar; aperte de novo para encerrar e transcrever.",
                           "Dictate", DICTATE_CMD)
        t.choice_row(lb, "Idioma", None, [("pt", "Português"), ("en", "Inglês"), ("es", "Espanhol"),
                                          ("auto", "Detectar (português ou inglês)")],
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
            row.subtitle.set_text("Iniciando…" if on else "Parando…")
            s.set_sensitive(False)

            def work():  # systemctl pode levar segundos: fora da thread do GTK
                cmd = ["systemctl", "--user", "enable" if on else "disable", "--now", "dictate-daemon"]
                try:
                    subprocess.run(cmd, capture_output=True, timeout=15)
                except (OSError, subprocess.TimeoutExpired) as e:
                    _debug_log(f"systemctl: {e}")
                time.sleep(1.5)  # o PID aparece quando o serviço sobe
                GLib.idle_add(done)

            def done():
                s.set_sensitive(True)
                row.subtitle.set_text("Em execução" if is_daemon_running() else "Parado")
            threading.Thread(target=work, daemon=True).start()
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
                     "Se o microfone escolhido estiver desconectado, o ditado usa o padrão do sistema e avisa. "
                     "Som do computador transcreve o que está tocando (vídeo, reunião) direto da saída de áudio: "
                     "não para nas pausas, termina no 2º toque do atalho ou na duração máxima.")
        options = [("@DEFAULT_SOURCE@", "Padrão do sistema")] + [(n, friendly_mic_name(n)) for n in list_source_names()]
        options.append((SYSTEM_AUDIO, "Som do computador"))
        self.mic_combo = t.choice_row(lb, "Entrada", None, options,
                                      self.config.get("mic_device", "@DEFAULT_SOURCE@"), self._on_mic_changed)
        self.meter = LevelMeter(self._selected_mic, self.config.get("sample_rate", 16000))
        t.row(lb, "Nível", "Fale (ou toque algo) para ver o sinal chegando.", self.meter)
        self._shortcut_row(lb, "Atalho: som do computador", "Transcreve o que está tocando, sem mudar a entrada acima.",
                           "Dictate: som do computador", f"{DICTATE_CMD} --system")

        lb = t.group(box, "Calibração", "Cada microfone guarda a própria calibração. Sem calibração, o ditado mede o "
                                        "ruído a cada uso.")
        self.cal_label = t.label("", "row-subtitle")
        btn = self.cal_btn = Gtk.Button(label="Calibrar…")
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
        t.switch_row(lb, "Pausar música e vídeos", "Pausa o que estiver tocando (navegador, Spotify…) enquanto "
                     "você fala e retoma depois. Sem isso, o mic ouve a música como se fosse voz.",
                     self.config.get("pause_media", True), lambda v: self.set("pause_media", v))
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
        self.cal_btn.set_sensitive(not is_system_audio(self._selected_mic()))
        if is_system_audio(self._selected_mic()):
            self.cal_label.set_text("Não precisa: áudio digital")
            return
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
        lb = t.group(box, "Modelo", "Modelos maiores erram menos e usam mais GPU. turbo é o melhor custo-benefício. "
                                    "A troca vale no próximo ditado (o primeiro uso baixa o modelo).")
        models = [("tiny", "tiny"), ("base", "base"), ("small", "small"), ("medium", "medium"),
                  ("turbo", "large-v3-turbo"), ("large-v3", "large-v3")]
        t.choice_row(lb, "Modelo Whisper", None, models, self.config.get("model", "medium"),
                     lambda v: self.set("model", v))

        lb = t.group(box, "Legendas ao vivo",
                     "Legenda o som do computador (vídeo em inglês, chinês, russo…) enquanto toca, traduzida. "
                     "Inglês é traduzido pelo próprio Whisper; os outros idiomas usam o tradutor abaixo. "
                     "O idioma do vídeo é detectado nos primeiros segundos. No fim, a legenda inteira fica copiada.")
        t.choice_row(lb, "Legendar em", None, [("pt", "Português"), ("en", "Inglês"), ("es", "Espanhol"),
                                               ("", "Idioma original (sem traduzir)")],
                     self.config.get("caption_language", "pt"), lambda v: self.set("caption_language", v))
        t.choice_row(lb, "Tradutor", "DeepSeek: a melhor tradução, ~0,9 s, sem limite. NVIDIA: ~0,4 s, prévia "
                     "a cada 2,5 s (limite do plano grátis). Hunyuan MT: local no Ollama, 0,2 s e 2,2 GB de GPU, "
                     "mas às vezes acrescenta trechos. Troca vale na próxima legenda; nada para reiniciar.",
                     [("auto", "Automático (DeepSeek, NVIDIA, Ollama)"), ("deepseek", "DeepSeek (nuvem)"),
                      ("nvidia", "NVIDIA NIM (nuvem)"), ("hymt", "Hunyuan MT 1.5 (local)"),
                      ("ollama", "Ollama (outro modelo local)")],
                     self.config.get("caption_translator", "auto"), lambda v: self.set("caption_translator", v))
        self._shortcut_row(lb, "Atalho das legendas", "Toque para começar; de novo para encerrar.",
                           "Dictate: legendas", f"{DICTATE_CMD} --captions")

        lb = t.group(box, "Aparência da legenda",
                     "Lente: a linha em foco fica maior e as vizinhas encolhem e esmaecem, como uma lupa. O foco "
                     "acompanha a frase mais nova; a frase em andamento vem por baixo. Com o foco no centro sobra "
                     "espaço embaixo; \u201cAbaixo\u201d mostra mais frases anteriores.")
        preview = CaptionPreview(self.config)
        r = Gtk.ListBoxRow()
        r.set_activatable(False)
        r.add(preview)
        lb.add(r)

        def apply(key, value):
            self.set(key, value)
            preview.rebuild()
        t.slider_row(lb, "Linhas na tela", None, 3, 14, 1, self.config.get("caption_lines", 8),
                     lambda v: f"{int(v)}", lambda v: apply("caption_lines", int(v)))
        lens_rows = []

        def toggle_lens(on):
            apply("caption_lens", on)
            for row in lens_rows:
                row.set_sensitive(on)
        t.switch_row(lb, "Efeito lente", "Linha em foco maior, as de cima e de baixo menores.",
                     self.config.get("caption_lens", True), toggle_lens)
        lens_rows.append(t.slider_row(lb, "Aumento", "Tamanho da linha em foco.", 1.1, 2.0, 0.1,
                                      self.config.get("caption_lens_zoom", 1.5), lambda v: f"{v:.1f}×".replace(".", ","),
                                      lambda v: apply("caption_lens_zoom", round(v, 1))).get_ancestor(Gtk.ListBoxRow))
        lens_rows.append(t.slider_row(lb, "Alcance", "Quantas linhas em volta do foco também crescem.", 1, 4, 0.5,
                                      self.config.get("caption_lens_reach", 2),
                                      lambda v: f"{v:g} linha{'s' if v > 1 else ''}".replace(".", ","),
                                      lambda v: apply("caption_lens_reach", round(v, 1))).get_ancestor(Gtk.ListBoxRow))
        lens_rows.append(t.row(lb, "Posição do foco", None, t.segmented(
            [("top", "Acima"), ("center", "Centro"), ("bottom", "Abaixo")],
            self.config.get("caption_lens_pos", "center"), lambda v: apply("caption_lens_pos", v))))
        for row in lens_rows:
            row.set_sensitive(bool(self.config.get("caption_lens", True)))

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
                     self.config.get("silence_duration", 2.5), lambda v: f"{v:.1f} s",
                     lambda v: self.set("silence_duration", round(v, 1)))
        t.slider_row(lb, "Esperar fala por", "Tempo máximo até você começar a falar.", 5, 60, 1,
                     self.config.get("listen_timeout", 15), lambda v: f"{int(v)} s",
                     lambda v: self.set("listen_timeout", int(v)))
        t.slider_row(lb, "Duração máxima", None, 15, 300, 5, self.config.get("max_duration", 60),
                     lambda v: f"{int(v)} s", lambda v: self.set("max_duration", int(v)))
        return root

    def page_text(self):
        root, box = t.page("Texto", "Pontuação, correções e atalhos de texto.")
        lb = t.group(box, "Formatação")
        t.switch_row(lb, "Formatação automática", "Maiúsculas, espaços e ponto final.",
                     self.config.get("enable_formatting", True), lambda v: self.set("enable_formatting", v))
        t.switch_row(lb, "Remover hesitações", "“hmm”, “ahn”, “éh”…",
                     self.config.get("remove_fillers", True), lambda v: self.set("remove_fillers", v))
        t.switch_row(lb, "Comandos de voz", "“vírgula”, “ponto final”, “nova linha”, “novo parágrafo”…",
                     self.config.get("voice_commands", True), lambda v: self.set("voice_commands", v))
        t.switch_row(lb, "Aprender com as correções",
                     "Palavra corrigida na revisão vira regra do Dicionário ao colar. Clique no selo para não lembrar.",
                     self.config.get("learn_corrections", True), lambda v: self.set("learn_corrections", v))
        self._kv_editor(box, "Dicionário", "Corrige grafias recorrentes: o que o Whisper escreve → como deve ficar.",
                        "word_overrides", "escrito", "corrigido")
        self._kv_editor(box, "Atalhos de texto", "Diga o gatilho e o texto inteiro entra no lugar. Ex.: “minha assinatura”.",
                        "snippets", "gatilho falado", "texto", multiline=True)
        return root

    def page_ai(self):
        root, box = t.page("Inteligência", "Reescreve o ditado com um modelo de linguagem antes de colar.")
        content = self._feature_gate(box, "ai_enabled", "Reescrita com IA",
                                     "Corrigir, transformar em e-mail, traduzir, resumir em tópicos.")

        lb = t.group(content, "Provedores", "Tenta em ordem: se uma falhar, demorar mais de 3 s ou a placa de vídeo "
                                            "estiver sem espaço ou quente, passa para a próxima. Só cola o original "
                                            "se todas falharem.")
        provider_rows = {}

        def set_chain(v):
            self.set("ai_chain", v.split(","))
            self._ai_provider_rows(provider_rows)
        t.choice_row(lb, "Ordem", None, AI_CHAINS, ",".join(self.config.get("ai_chain") or [self.config["ai_provider"]]),
                     set_chain)
        from .. import ai
        provider_rows["ollama_url"] = t.row(lb, "Endereço do Ollama", None, self._entry(
            "ai_ollama_url", "http://localhost:11434"))
        provider_rows["ollama_model"] = t.row(lb, "Modelo local (Ollama)", "1º da fila: grátis e nada sai do computador.", self._entry("ai_ollama_model", "qwen2.5"))
        provider_rows["nvidia_key"] = self._key_row(lb, "nvidia", "NVIDIA", "nvapi-…")
        provider_rows["nvidia_model"] = t.choice_row(
            lb, "Modelo da NVIDIA", "Testados com a sua chave; os mais rápidos deixam o ditado fluido.", ai.RECOMMENDED,
            self.config.get("ai_model"), lambda v: self.set("ai_model", v)).get_ancestor(Gtk.ListBoxRow)
        provider_rows["deepseek_key"] = self._key_row(lb, "deepseek", "DeepSeek", "sk-…")
        provider_rows["deepseek_model"] = t.choice_row(
            lb, "Modelo da DeepSeek", "Flash é o rápido (~0,8 s, sem raciocínio); Pro pensa mais e demora.", ai.DEEPSEEK_MODELS,
            self.config.get("ai_deepseek_model", "deepseek-flash"),
            lambda v: self.set("ai_deepseek_model", v)).get_ancestor(Gtk.ListBoxRow)
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
        self._style_group(content)

        lb3 = t.group(content, "Contexto")
        t.switch_row(lb3, "Usar o campo em foco", "App, janela, rótulo do campo e o texto selecionado (a maior pista "
                     "do assunto) ajudam a IA com nomes e termos; nomes próprios também vão para o reconhecimento. "
                     "Nunca troca o modo sozinho.",
                     self.config.get("context_enabled", True), lambda v: self.set("context_enabled", v))
        content.pack_start(t.label("Privacidade: com o Ollama tudo fica no seu computador. Quando a fila chega à "
                                   "NVIDIA ou ao DeepSeek, o ditado e o contexto vão para a nuvem deles; a revisão "
                                   "mostra “via NVIDIA/DeepSeek” quando isso acontece.",
                                   "group-footer", wrap=True), False, False, 0)
        return root

    def _style_group(self, box):
        """Meu estilo: nota no Obsidian estudada dos seus textos enviados; usada nos modos de e-mail."""
        from .. import style
        lb = t.group(box, "Meu estilo", "Os modos de e-mail escrevem como você: regras da nota “Meu estilo de "
                                        "escrita” (edite à vontade no Obsidian) e as suas últimas correções. O estudo "
                                        "roda na IA local; os e-mails não saem do computador.")
        t.switch_row(lb, "Usar meu estilo nos e-mails", None, self.config.get("style_enabled", True),
                     lambda v: self.set("style_enabled", v))
        open_btn = Gtk.Button(label="Abrir")
        open_btn.connect("clicked", lambda _b: subprocess.Popen(
            ["xdg-open", self.config["style_note"]]) if os.path.exists(self.config.get("style_note", "")) else None)
        t.row(lb, "Nota", self._short_path(self.config.get("style_note")) or "Nenhuma", open_btn)

        src_lb = t.group(box, "Fontes do estilo", "Pastas do vault com textos seus. “Só enviados” lê exports de "
                                                  "e-mail (linha “Pasta:” com enviados); “nota inteira” serve para "
                                                  "posts e artigos seus.")
        status = t.label("", "row-subtitle")

        def save_sources():
            self.set("style_sources", copy.deepcopy(self.config["style_sources"]))

        def refresh():
            for r in src_lb.get_children():
                src_lb.remove(r)
            for src in self.config.get("style_sources", []):
                sw = Gtk.Switch(active=src.get("enabled", True), valign=Gtk.Align.CENTER)
                sw.connect("notify::active", lambda w, _p, src=src: (src.update(enabled=w.get_active()), save_sources()))
                rm = Gtk.Button()
                rm.add(t.icon("trash", 14, "#98989D"))
                rm.get_style_context().add_class("btn-flat")
                rm.set_tooltip_text("Remover fonte")
                rm.connect("clicked", lambda _b, src=src: (self.config["style_sources"].remove(src), save_sources(),
                                                            refresh()))
                ctl = Gtk.Box(spacing=8)
                ctl.pack_start(sw, False, False, 0)
                ctl.pack_start(rm, False, False, 0)
                kind = "só enviados" if src.get("filter", "sent") == "sent" else "nota inteira"
                row = t.row(src_lb, os.path.basename(src["path"].rstrip("/")), f"{kind} · contando…", ctl)
                count_source(src, row)
            src_lb.show_all()

        def count_source(src, row):
            def work():
                n, words = next(((n, w) for _s, n, w in style.preview([dict(src, enabled=True)])), (0, 0))
                kind = "só enviados" if src.get("filter", "sent") == "sent" else "nota inteira"
                sub = f"{kind} · {n} textos · {words:,} palavras".replace(",", ".")
                GLib.idle_add(lambda: row.subtitle.set_text(sub) and False)
            threading.Thread(target=work, daemon=True).start()

        def add_source(_b):
            dlg = Gtk.FileChooserDialog(title="Pasta com textos seus", transient_for=self,
                                        action=Gtk.FileChooserAction.SELECT_FOLDER)
            dlg.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Escolher", Gtk.ResponseType.OK)
            vault = os.path.dirname(os.path.dirname(self.config.get("style_note") or "")) or os.path.expanduser("~")
            dlg.set_current_folder(vault)
            path = dlg.get_filename() if dlg.run() == Gtk.ResponseType.OK else None
            dlg.destroy()
            if not path:
                return

            def build(b):
                combo = t.choice_row(t.group(b), "Ler", None, [("sent", "Só e-mails enviados"),
                                                               ("whole", "Nota inteira")], "sent", lambda v: None)
                return lambda: combo.get_active_id()
            kind = self._dialog(os.path.basename(path), build, "Adicionar")
            if kind:
                self.config.setdefault("style_sources", []).append(
                    {"path": path, "filter": kind, "subdirs": True, "enabled": True})
                save_sources()
                refresh()

        def restudy(btn):
            btn.set_sensitive(False)

            def progress(msg):
                GLib.idle_add(status.set_text, msg)

            def work():
                t0 = time.time()
                try:
                    block = style.study(self.config, self.config.get("style_sources", []), progress)
                    style.write_note(self.config["style_note"], block)
                    msg = f"Estilo atualizado em {time.time() - t0:.0f} s"
                except Exception as e:
                    msg = f"Falhou: {str(e)[:70]}"
                GLib.idle_add(lambda: (status.set_text(msg), btn.set_sensitive(True)) and False)
            threading.Thread(target=work, daemon=True).start()

        refresh()
        add = Gtk.Button(label="Adicionar pasta…")
        add.connect("clicked", add_source)
        study = Gtk.Button(label="Reestudar meu estilo")
        study.get_style_context().add_class("btn-primary")
        study.connect("clicked", restudy)
        bar = Gtk.Box(spacing=10)
        for w in (add, study, status):
            bar.pack_start(w, False, False, 0)
        box.pack_start(bar, False, False, 0)

    def _entry(self, key, placeholder):
        e = Gtk.Entry(text=self.config.get(key) or "", placeholder_text=placeholder)
        e.set_width_chars(26)
        e.connect("changed", lambda w: self.set(key, w.get_text().strip()))
        return e

    def _ai_provider_rows(self, rows):
        chain = self.config.get("ai_chain") or [self.config.get("ai_provider", "nvidia")]
        for name, r in rows.items():
            r.set_visible(name.split("_")[0] in chain)
        return False

    def _key_row(self, lb, provider, name, placeholder):
        """Chave de API (só no chaveiro do sistema) com o botão Alterar…"""
        from .. import ai, secrets
        key_label = t.label(secrets.masked(secrets.get_key(provider)), "dim")
        kb = Gtk.Box(spacing=10)
        kb.pack_start(key_label, False, False, 0)
        change = Gtk.Button(label="Alterar…")

        def change_key(_b):
            def build(b):
                b.pack_start(t.label(f"Chave de API da {name} ({placeholder}). Fica no chaveiro do sistema.",
                                     wrap=True), False, False, 0)
                e = Gtk.Entry(visibility=False, placeholder_text=placeholder)
                b.pack_start(e, False, False, 0)
                return e.get_text
            key = self._dialog(f"Chave da {name}", build)
            if key:
                secrets.set_key(provider, key)
                ai._cached_key.cache_clear()  # o Testar desta janela já usa a nova
                key_label.set_text(secrets.masked(key))
        change.connect("clicked", change_key)
        kb.pack_start(change, False, False, 0)
        return t.row(lb, f"Chave da {name}", "Guardada no chaveiro do sistema (gnome-keyring).", kb)

    def _test_ai(self, label):
        label.set_text("Testando…")

        def work():
            try:
                from .. import ai
                ms, _sample, who = ai.test(self.config)
                msg, color = f"OK · {ms:.0f} ms · {who}", t.SUCCESS
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
        if p.get("send_key", "Return") != "Return":
            bits.append("envia com " + SEND_KEYS.get(p["send_key"], p["send_key"]))
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
            send = t.choice_row(lb, "Enviar com", "Tecla que “Colar e enviar” (⇧Enter na revisão) aperta.",
                                list(SEND_KEYS.items()), p.get("send_key", "Return"), lambda v: None)
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
                            "ai_mode": ai.get_active_id() or "", "send_key": send.get_active_id() or "Return",
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
        root, box = t.page("Histórico", "Ditados anteriores no seu computador e, se quiser, no Obsidian.")
        self._obsidian_group(box)
        content = self._feature_gate(box, "history_enabled", "Guardar histórico",
                                     "Busque e recole ditados antigos.")
        lb = t.group(content)
        t.choice_row(lb, "Manter por", None, [("7", "7 dias"), ("30", "30 dias"), ("90", "90 dias"),
                                              ("365", "1 ano"), ("0", "Sempre")],
                     str(self.config.get("history_retention_days", 30)),
                     lambda v: self.set("history_retention_days", int(v)))
        t.switch_row(lb, "Guardar o áudio", "Cópia compacta de cada ditado (~16 MB por hora de fala), apagada junto "
                     "com o histórico. Serve para cadastrar sua voz e treinar o reconhecimento.",
                     self.config.get("keep_audio", True), lambda v: self.set("keep_audio", v))
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
                copy_btn.connect("clicked", lambda _b, txt=rec.get("text", ""): copy_text(txt))
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

    def _obsidian_group(self, box):
        """Cópia no Obsidian: liga/desliga e a pasta da nota do dia (independe do histórico)."""
        lb = t.group(box, "Obsidian", "Uma nota por dia (AAAA-MM-DD.md), um bloco por ditado com o bruto recolhido; "
                                      "legendas também. Só acrescenta no fim e a retenção não apaga. Com o Obsidian "
                                      "Sync ligado, as notas vão para a nuvem do Obsidian.")
        folder = t.label(self._short_path(self.config.get("obsidian_dir")) or "Nenhuma pasta", "dim")
        pick = Gtk.Button(label="Escolher…")

        def choose(_b):
            dlg = Gtk.FileChooserDialog(title="Pasta dos ditados no vault", transient_for=self,
                                        action=Gtk.FileChooserAction.SELECT_FOLDER)
            dlg.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Escolher", Gtk.ResponseType.OK)
            start = self.config.get("obsidian_dir") or os.path.expanduser("~/Documentos")
            dlg.set_current_folder(start if os.path.isdir(start) else os.path.dirname(start))
            if dlg.run() == Gtk.ResponseType.OK:
                self.set("obsidian_dir", dlg.get_filename())
                folder.set_text(self._short_path(dlg.get_filename()))
            dlg.destroy()
        pick.connect("clicked", choose)
        fb = Gtk.Box(spacing=10)
        fb.pack_start(folder, False, False, 0)
        fb.pack_start(pick, False, False, 0)
        t.switch_row(lb, "Copiar ditados para o Obsidian", None, self.config.get("obsidian_enabled", False),
                     lambda v: self.set("obsidian_enabled", v))
        t.row(lb, "Pasta", None, fb)

    @staticmethod
    def _short_path(path):
        """~/…/01 - Pessoal/Ditados: cabe na linha sem esconder a parte que importa."""
        if not path:
            return ""
        path = path.replace(os.path.expanduser("~"), "~", 1)
        parts = path.split(os.sep)
        return path if len(parts) <= 3 else os.sep.join([parts[0], "…"] + parts[-2:])

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
