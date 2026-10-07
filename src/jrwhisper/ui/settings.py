import subprocess
from gi.repository import Gtk, GLib, GdkPixbuf

from ..audio import calibration_state, default_source_name, list_mic_devices
from ..config import _debug_log, save_config
from ..transcribe import is_daemon_running
from .calibration import CalibrationWindow
from .theme import apply_settings_css


class SettingsWindow(Gtk.Window):
    def __init__(self, config):
        Gtk.Window.__init__(self, title="Configurações do Dictate")
        self.set_default_size(650, 550)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.config = config
        self.original_config = dict(config)

        # SVG Icon (Microfone discreto e profissional)
        svg_icon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="#64DCFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
          <path d="M19 10v1a7 7 0 0 1-14 0v-1"/>
          <line x1="12" y1="18" x2="12" y2="22"/>
          <line x1="9" y1="22" x2="15" y2="22"/>
        </svg>"""

        pixbuf = None
        try:
            loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
            loader.set_size(32, 32)
            loader.write(svg_icon.encode('utf-8'))
            loader.close()
            pixbuf = loader.get_pixbuf()
            self.set_icon(pixbuf)
        except Exception as e:
            _debug_log(f"Falha ao carregar ícone SVG da janela: {e}")

        self.apply_premium_css()

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_box)

        # Header/Title Bar (Layout horizontal com ícone + textos)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        header.set_name("settings-header")
        header.set_margin_top(16)
        header.set_margin_bottom(16)
        header.set_margin_start(20)
        header.set_margin_end(20)

        # Caixa vertical de textos
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        title_label = Gtk.Label()
        title_label.set_markup("<span size='large' weight='bold' foreground='#FFFFFF'>Configurações do Dictate</span>")
        title_label.set_halign(Gtk.Align.START)
        text_box.pack_start(title_label, False, False, 0)

        subtitle_label = Gtk.Label()
        subtitle_label.set_markup("<span size='small' foreground='#FFFFFF80'>Ajuste as preferências de captação, modelo e formatação inteligente.</span>")
        subtitle_label.set_halign(Gtk.Align.START)
        text_box.pack_start(subtitle_label, False, False, 0)

        header.pack_start(text_box, True, True, 0)

        if pixbuf:
            img_icon = Gtk.Image.new_from_pixbuf(pixbuf)
            img_icon.set_valign(Gtk.Align.CENTER)
            img_icon.set_halign(Gtk.Align.END)
            header.pack_end(img_icon, False, False, 0)

        main_box.pack_start(header, False, False, 0)

        # Content Box
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_box.pack_start(content_box, True, True, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(200)

        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(self.stack)
        sidebar.set_size_request(160, -1)
        sidebar.set_name("settings-sidebar")

        content_box.pack_start(sidebar, False, False, 0)

        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        content_box.pack_start(separator, False, False, 0)

        # Pack Pages
        self.stack.add_titled(self.create_recognition_page(), "recognition", "Reconhecimento")
        self.stack.add_titled(self.create_audio_page(), "audio", "Áudio & Captação")
        self.stack.add_titled(self.create_formatting_page(), "formatting", "Formatação")
        self.stack.add_titled(self.create_overrides_page(), "overrides", "Dicionário")

        content_box.pack_start(self.stack, True, True, 0)

        # Bottom Action Bar
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        action_bar.set_name("action-bar")
        action_bar.set_margin_top(14)
        action_bar.set_margin_bottom(14)
        action_bar.set_margin_start(20)
        action_bar.set_margin_end(20)
        action_bar.set_halign(Gtk.Align.END)

        btn_cancel = Gtk.Button(label="Cancelar")
        btn_cancel.connect("clicked", self.on_cancel_clicked)
        btn_cancel.get_style_context().add_class("btn-secondary")
        action_bar.pack_start(btn_cancel, False, False, 0)

        btn_save = Gtk.Button(label="Salvar")
        btn_save.connect("clicked", self.on_save_clicked)
        btn_save.get_style_context().add_class("btn-primary")
        action_bar.pack_start(btn_save, False, False, 0)

        main_box.pack_start(action_bar, False, False, 0)

        self.connect("destroy", Gtk.main_quit)

    def apply_premium_css(self):
        apply_settings_css(self.get_screen())

    def create_recognition_page(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(15)
        grid.set_row_spacing(15)
        grid.set_margin_top(15)
        grid.set_margin_bottom(15)
        grid.set_margin_start(15)
        grid.set_margin_end(15)

        # Modelo Whisper
        lbl_model = Gtk.Label(label="Modelo Whisper:")
        lbl_model.set_halign(Gtk.Align.START)
        self.combo_model = Gtk.ComboBoxText()
        models = ["tiny", "base", "small", "medium", "large-v3"]
        for m in models:
            self.combo_model.append(m, m)
        self.combo_model.set_active_id(self.config.get("model", "medium"))

        grid.attach(lbl_model, 0, 0, 1, 1)
        grid.attach(self.combo_model, 1, 0, 1, 1)

        # Idioma
        lbl_lang = Gtk.Label(label="Idioma Padrão:")
        lbl_lang.set_halign(Gtk.Align.START)
        self.combo_lang = Gtk.ComboBoxText()
        self.combo_lang.append("pt", "Português (pt)")
        self.combo_lang.append("en", "Inglês (en)")
        self.combo_lang.append("es", "Espanhol (es)")
        self.combo_lang.append("auto", "Detectar automaticamente")
        self.combo_lang.set_active_id(self.config.get("language", "pt"))

        grid.attach(lbl_lang, 0, 1, 1, 1)
        grid.attach(self.combo_lang, 1, 1, 1, 1)

        # Prompt Inicial
        lbl_prompt = Gtk.Label(label="Prompt Inicial:")
        lbl_prompt.set_halign(Gtk.Align.START)
        lbl_prompt.set_valign(Gtk.Align.START)

        self.prompt_buffer = Gtk.TextBuffer()
        self.prompt_buffer.set_text(self.config.get("initial_prompt", ""))

        prompt_view = Gtk.TextView(buffer=self.prompt_buffer)
        prompt_view.set_wrap_mode(Gtk.WrapMode.WORD)
        prompt_view.set_size_request(-1, 120)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(prompt_view)

        grid.attach(lbl_prompt, 0, 2, 1, 1)
        grid.attach(scroll, 1, 2, 1, 1)

        lbl_tip = Gtk.Label()
        lbl_tip.set_markup("<span size='small' foreground='#FFFFFF60'><i>Dica: O Prompt ajuda o Whisper a transcrever jargões técnicos, nomes de empresas e abreviações corretamente. Separe por vírgulas.</i></span>")
        lbl_tip.set_line_wrap(True)
        lbl_tip.set_max_width_chars(50)
        lbl_tip.set_halign(Gtk.Align.START)
        grid.attach(lbl_tip, 1, 3, 1, 1)

        self.combo_model.set_hexpand(True)
        self.combo_lang.set_hexpand(True)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)

        return grid

    def create_audio_page(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(15)
        grid.set_row_spacing(12)
        grid.set_margin_top(15)
        grid.set_margin_bottom(15)
        grid.set_margin_start(15)
        grid.set_margin_end(15)

        # Microfone
        lbl_mic = Gtk.Label(label="Microfone:")
        lbl_mic.set_halign(Gtk.Align.START)
        self.combo_mic = Gtk.ComboBoxText()

        mics = list_mic_devices()
        for mic_val, mic_label in mics:
            self.combo_mic.append(mic_val, mic_label)

        current_mic = self.config.get("mic_device", "@DEFAULT_SOURCE@")
        found = False
        for mic_val, _ in mics:
            if mic_val == current_mic:
                found = True
                break
        if not found:
            self.combo_mic.append(current_mic, current_mic)
        self.combo_mic.set_active_id(current_mic)

        grid.attach(lbl_mic, 0, 0, 1, 1)
        grid.attach(self.combo_mic, 1, 0, 1, 1)
        self.combo_mic.set_hexpand(True)

        # Silence Threshold
        lbl_thresh = Gtk.Label(label="Limite Manual:")
        lbl_thresh.set_halign(Gtk.Align.START)

        self.adj_thresh = Gtk.Adjustment(value=self.config.get("silence_threshold", 0)*1000, lower=0, upper=15, step_increment=0.1, page_increment=1)
        self.scale_thresh = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.adj_thresh)
        # 1 casa (0.0001): limiares de mic dinâmico (~0.0004) não podem virar "Auto" ao salvar.
        self.scale_thresh.set_digits(1)
        self.scale_thresh.set_hexpand(True)

        self.lbl_thresh_val = Gtk.Label()
        self.update_thresh_label()
        self.scale_thresh.connect("value-changed", lambda w: self.update_thresh_label())

        grid.attach(lbl_thresh, 0, 1, 1, 1)
        grid.attach(self.scale_thresh, 1, 1, 1, 1)
        grid.attach(self.lbl_thresh_val, 2, 1, 1, 1)

        # Silence Duration
        lbl_dur = Gtk.Label(label="Aguardar Silêncio:")
        lbl_dur.set_halign(Gtk.Align.START)

        self.adj_dur = Gtk.Adjustment(value=self.config.get("silence_duration", 1.7), lower=0.5, upper=5.0, step_increment=0.1, page_increment=0.5)
        self.scale_dur = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.adj_dur)
        self.scale_dur.set_digits(1)
        self.scale_dur.set_hexpand(True)

        self.lbl_dur_val = Gtk.Label()
        self.update_dur_label()
        self.scale_dur.connect("value-changed", lambda w: self.update_dur_label())

        grid.attach(lbl_dur, 0, 2, 1, 1)
        grid.attach(self.scale_dur, 1, 2, 1, 1)
        grid.attach(self.lbl_dur_val, 2, 2, 1, 1)

        # Supressão de Ruído
        lbl_noise = Gtk.Label(label="Supressão de Ruído:")
        lbl_noise.set_halign(Gtk.Align.START)
        self.switch_noise = Gtk.Switch()
        self.switch_noise.set_active(self.config.get("noise_suppression", True))
        self.switch_noise.set_halign(Gtk.Align.START)

        grid.attach(lbl_noise, 0, 3, 1, 1)
        grid.attach(self.switch_noise, 1, 3, 1, 1)

        # Ducking
        lbl_duck = Gtk.Label(label="Atenuação de Áudio:")
        lbl_duck.set_halign(Gtk.Align.START)
        self.switch_duck = Gtk.Switch()
        self.switch_duck.set_active(self.config.get("audio_ducking", True))
        self.switch_duck.set_halign(Gtk.Align.START)

        grid.attach(lbl_duck, 0, 4, 1, 1)
        grid.attach(self.switch_duck, 1, 4, 1, 1)

        # Ducking Volume
        lbl_duck_vol = Gtk.Label(label="Volume Atenuado:")
        lbl_duck_vol.set_halign(Gtk.Align.START)

        self.adj_duck_vol = Gtk.Adjustment(value=self.config.get("ducking_volume", 0.20)*100, lower=0, upper=100, step_increment=5, page_increment=10)
        self.scale_duck_vol = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.adj_duck_vol)
        self.scale_duck_vol.set_digits(0)
        self.scale_duck_vol.set_hexpand(True)

        self.lbl_duck_vol_val = Gtk.Label()
        self.update_duck_vol_label()
        self.scale_duck_vol.connect("value-changed", lambda w: self.update_duck_vol_label())

        self.switch_duck.connect("notify::active", self.on_duck_switch_changed)
        self.scale_duck_vol.set_sensitive(self.switch_duck.get_active())

        grid.attach(lbl_duck_vol, 0, 5, 1, 1)
        grid.attach(self.scale_duck_vol, 1, 5, 1, 1)
        grid.attach(self.lbl_duck_vol_val, 2, 5, 1, 1)

        grid.insert_row(1)
        lbl_cal = Gtk.Label(label="Calibração:")
        lbl_cal.set_halign(Gtk.Align.START)
        cal_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.lbl_cal_state = Gtk.Label(xalign=0)
        cal_box.pack_start(self.lbl_cal_state, True, True, 0)
        btn_cal = Gtk.Button(label="Calibrar…")
        btn_cal.connect("clicked", self.on_calibrate_clicked)
        cal_box.pack_end(btn_cal, False, False, 0)
        grid.attach(lbl_cal, 0, 1, 1, 1)
        grid.attach(cal_box, 1, 1, 2, 1)
        self.combo_mic.connect("changed", lambda c: self.refresh_cal_state())
        self.refresh_cal_state()

        return grid

    def _selected_mic(self):
        mic = self.combo_mic.get_active_id() or "@DEFAULT_SOURCE@"
        return (default_source_name() or mic) if mic == "@DEFAULT_SOURCE@" else mic

    def refresh_cal_state(self):
        state, cal = calibration_state(self.config, self._selected_mic())
        if state == "ok":
            txt, color = f"Calibrado · limiar {cal['threshold']:.4f}", "#64FFA0"
        elif state == "stale":
            txt, color = "Ganho do mic mudou: recalibre", "#FFC83C"
        else:
            txt, color = "Automático (não calibrado)", "#FFFFFF80"
        self.lbl_cal_state.set_markup(f"<span size='small' foreground='{color}'>{GLib.markup_escape_text(txt)}</span>")

    def on_calibration_saved(self):
        # Calibrar zera o limite manual; o slider precisa refletir, senão Salvar o restaura.
        self.adj_thresh.set_value(self.config.get("silence_threshold", 0) * 1000)
        self.refresh_cal_state()

    def on_calibrate_clicked(self, btn):
        win = CalibrationWindow(self.config, mic=self._selected_mic(), on_saved=self.on_calibration_saved)
        win.set_transient_for(self)
        win.set_modal(True)
        win.show_all()

    def update_thresh_label(self):
        val = self.scale_thresh.get_value()
        if val == 0:
            self.lbl_thresh_val.set_markup("<span foreground='#64DCFF' weight='bold'>Auto</span>")
        else:
            self.lbl_thresh_val.set_text(f"{val/1000:.4f}")

    def update_dur_label(self):
        val = self.scale_dur.get_value()
        self.lbl_dur_val.set_text(f"{val:.1f}s")

    def update_duck_vol_label(self):
        val = self.scale_duck_vol.get_value()
        self.lbl_duck_vol_val.set_text(f"{int(val)}%")

    def on_duck_switch_changed(self, switch, gparamspec):
        self.scale_duck_vol.set_sensitive(switch.get_active())

    def create_formatting_page(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(15)
        grid.set_row_spacing(15)
        grid.set_margin_top(15)
        grid.set_margin_bottom(15)
        grid.set_margin_start(15)
        grid.set_margin_end(15)

        # Formatação
        lbl_fmt = Gtk.Label(label="Formatação Inteligente:")
        lbl_fmt.set_halign(Gtk.Align.START)
        self.switch_fmt = Gtk.Switch()
        self.switch_fmt.set_active(self.config.get("enable_formatting", True))
        self.switch_fmt.set_halign(Gtk.Align.START)

        lbl_fmt_desc = Gtk.Label()
        lbl_fmt_desc.set_markup("<span size='small' foreground='#FFFFFF60'>Ajusta automaticamente letras maiúsculas e pontuação do texto transcrito.</span>")
        lbl_fmt_desc.set_line_wrap(True)
        lbl_fmt_desc.set_halign(Gtk.Align.START)

        grid.attach(lbl_fmt, 0, 0, 1, 1)
        grid.attach(self.switch_fmt, 1, 0, 1, 1)
        grid.attach(lbl_fmt_desc, 1, 1, 1, 1)

        # Fillers
        lbl_fillers = Gtk.Label(label="Remover Hesitações:")
        lbl_fillers.set_halign(Gtk.Align.START)
        self.switch_fillers = Gtk.Switch()
        self.switch_fillers.set_active(self.config.get("remove_fillers", True))
        self.switch_fillers.set_halign(Gtk.Align.START)

        lbl_fillers_desc = Gtk.Label()
        lbl_fillers_desc.set_markup("<span size='small' foreground='#FFFFFF60'>Remove marcadores de hesitação como 'humm', 'er', 'ahn', 'eh'.</span>")
        lbl_fillers_desc.set_line_wrap(True)
        lbl_fillers_desc.set_halign(Gtk.Align.START)

        grid.attach(lbl_fillers, 0, 2, 1, 1)
        grid.attach(self.switch_fillers, 1, 2, 1, 1)
        grid.attach(lbl_fillers_desc, 1, 3, 1, 1)

        # Comandos de Voz
        lbl_cmds = Gtk.Label(label="Comandos de Voz:")
        lbl_cmds.set_halign(Gtk.Align.START)
        self.switch_cmds = Gtk.Switch()
        self.switch_cmds.set_active(self.config.get("voice_commands", True))
        self.switch_cmds.set_halign(Gtk.Align.START)

        lbl_cmds_desc = Gtk.Label()
        lbl_cmds_desc.set_markup("<span size='small' foreground='#FFFFFF60'>Substitui termos falados como 'ponto final', 'nova linha' pelas respectivas pontuações.</span>")
        lbl_cmds_desc.set_line_wrap(True)
        lbl_cmds_desc.set_halign(Gtk.Align.START)

        grid.attach(lbl_cmds, 0, 4, 1, 1)
        grid.attach(self.switch_cmds, 1, 4, 1, 1)
        grid.attach(lbl_cmds_desc, 1, 5, 1, 1)

        return grid

    def create_overrides_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_top(15)
        vbox.set_margin_bottom(15)
        vbox.set_margin_start(15)
        vbox.set_margin_end(15)

        lbl_title = Gtk.Label()
        lbl_title.set_markup("<b>Substituições de Palavras (Word Overrides)</b>")
        lbl_title.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl_title, False, False, 0)

        lbl_desc = Gtk.Label()
        lbl_desc.set_markup("<span size='small' foreground='#FFFFFF60'>Defina termos falados (em minúsculo) e sua respectiva substituição textual.</span>")
        lbl_desc.set_line_wrap(True)
        lbl_desc.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl_desc, False, False, 0)

        self.overrides_store = Gtk.ListStore(str, str)
        word_overrides = self.config.get("word_overrides", {})
        for wrong, right in word_overrides.items():
            self.overrides_store.append([wrong, right])

        self.tree_view = Gtk.TreeView(model=self.overrides_store)
        self.tree_view.set_hexpand(True)
        self.tree_view.set_vexpand(True)

        renderer_text1 = Gtk.CellRendererText()
        renderer_text1.set_property("editable", True)
        renderer_text1.connect("edited", self.on_cell_edited, 0)
        col_wrong = Gtk.TreeViewColumn("Falado (Minúsculo)", renderer_text1, text=0)
        col_wrong.set_resizable(True)
        col_wrong.set_expand(True)
        self.tree_view.append_column(col_wrong)

        renderer_text2 = Gtk.CellRendererText()
        renderer_text2.set_property("editable", True)
        renderer_text2.connect("edited", self.on_cell_edited, 1)
        col_right = Gtk.TreeViewColumn("Escrever como", renderer_text2, text=1)
        col_right.set_resizable(True)
        col_right.set_expand(True)
        self.tree_view.append_column(col_right)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree_view)
        vbox.pack_start(scroll, True, True, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        btn_add = Gtk.Button(label="Adicionar")
        btn_add.connect("clicked", self.on_add_override_clicked)
        btn_box.pack_start(btn_add, False, False, 0)

        btn_remove = Gtk.Button(label="Remover")
        btn_remove.connect("clicked", self.on_remove_override_clicked)
        btn_box.pack_start(btn_remove, False, False, 0)

        vbox.pack_start(btn_box, False, False, 0)

        return vbox

    def on_cell_edited(self, renderer, path, new_text, col_idx):
        if not new_text.strip():
            return
        self.overrides_store[path][col_idx] = new_text.strip()
        if col_idx == 0:
            self.overrides_store[path][0] = new_text.strip().lower()

    def on_add_override_clicked(self, btn):
        self.overrides_store.append(["palavra falada", "Como Escrever"])

    def on_remove_override_clicked(self, btn):
        selection = self.tree_view.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            model.remove(treeiter)

    def on_cancel_clicked(self, btn):
        self.close_window()

    def on_save_clicked(self, btn):
        new_model = self.combo_model.get_active_id()
        new_lang = self.combo_lang.get_active_id()

        start_iter, end_iter = self.prompt_buffer.get_bounds()
        new_prompt = self.prompt_buffer.get_text(start_iter, end_iter, True).strip()

        new_mic = self.combo_mic.get_active_id()
        new_thresh = self.scale_thresh.get_value() / 1000.0
        new_dur = self.scale_dur.get_value()
        new_noise = self.switch_noise.get_active()
        new_duck = self.switch_duck.get_active()
        new_duck_vol = self.scale_duck_vol.get_value() / 100.0

        new_fmt = self.switch_fmt.get_active()
        new_fillers = self.switch_fillers.get_active()
        new_cmds = self.switch_cmds.get_active()

        new_overrides = {}
        for row in self.overrides_store:
            wrong, right = row[0], row[1]
            if wrong.strip() and right.strip():
                new_overrides[wrong.strip().lower()] = right.strip()

        updated_config = {
            **self.config,
            "model": new_model,
            "language": new_lang,
            "sample_rate": self.config.get("sample_rate", 16000),
            "mic_device": new_mic,
            "silence_threshold": new_thresh,
            "silence_duration": new_dur,
            "listen_timeout": self.config.get("listen_timeout", 15),
            "max_duration": self.config.get("max_duration", 60),
            "gpu_min_vram_mb": self.config.get("gpu_min_vram_mb", 2500),
            "initial_prompt": new_prompt,
            "no_speech_threshold": self.config.get("no_speech_threshold", 0.6),
            "log_prob_threshold": self.config.get("log_prob_threshold", -1.0),
            "compression_ratio_threshold": self.config.get("compression_ratio_threshold", 2.4),
            "enable_formatting": new_fmt,
            "remove_fillers": new_fillers,
            "voice_commands": new_cmds,
            "audio_ducking": new_duck,
            "ducking_volume": new_duck_vol,
            "noise_suppression": new_noise,
            "word_overrides": new_overrides
        }

        save_config(updated_config)

        critical_changed = (
            self.original_config.get("model") != new_model or
            self.original_config.get("language") != new_lang or
            self.original_config.get("initial_prompt") != new_prompt
        )

        if critical_changed and is_daemon_running():
            self.ask_restart_daemon()
        else:
            self.close_window()

    def ask_restart_daemon(self):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Reiniciar Daemon do Whisper?"
        )
        dialog.format_secondary_text(
            "Você alterou configurações críticas de modelo/idioma.\n"
            "Deseja reiniciar o daemon do Whisper agora para aplicar as mudanças?"
        )
        dialog.get_style_context().add_class("settings-dialog")

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            self.restart_daemon()
        else:
            self.close_window()

    def restart_daemon(self):
        try:
            subprocess.run(["systemctl", "--user", "restart", "dictate-daemon"], check=True, timeout=5)
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Sucesso"
            )
            dialog.format_secondary_text("Daemon do Whisper reiniciado com sucesso!")
            dialog.get_style_context().add_class("settings-dialog")
            dialog.run()
            dialog.destroy()
        except Exception as e:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Erro ao reiniciar Daemon"
            )
            dialog.format_secondary_text(f"Não foi possível reiniciar o daemon via systemd:\n{e}")
            dialog.get_style_context().add_class("settings-dialog")
            dialog.run()
            dialog.destroy()

        self.close_window()

    def close_window(self):
        self.destroy()
        Gtk.main_quit()
