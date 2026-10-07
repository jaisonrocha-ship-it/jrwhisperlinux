from gi.repository import Gtk


SETTINGS_CSS = """
        window {
            background-color: #121214;
            color: #E2E2E6;
            font-family: 'Inter', sans-serif;
        }
        
        #settings-header {
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding-bottom: 12px;
        }
        
        #settings-sidebar list {
            background-color: #18181C;
            border: none;
            padding-top: 10px;
        }
        #settings-sidebar row {
            padding: 10px 12px;
            margin: 2px 6px;
            border-radius: 6px;
            color: rgba(255, 255, 255, 0.7);
            font-weight: 500;
            font-size: 13px;
            transition: all 0.15s ease;
        }
        #settings-sidebar row:hover {
            background-color: rgba(255, 255, 255, 0.05);
            color: #FFFFFF;
        }
        #settings-sidebar row:selected {
            background-color: rgba(100, 220, 255, 0.12);
            color: #64DCFF;
            font-weight: bold;
        }
        
        separator {
            background-color: rgba(255, 255, 255, 0.08);
        }
        
        label {
            font-size: 13px;
            color: rgba(255, 255, 255, 0.85);
            font-weight: 500;
        }
        
        entry, textview text {
            background-color: #1C1C20;
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 13px;
        }
        entry:focus, textview text:focus {
            border-color: #64DCFF;
        }
        
        combobox {
            background-color: #1C1C20;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 6px;
            color: #FFFFFF;
            padding: 2px 6px;
        }
        combobox button {
            background: transparent;
            border: none;
            color: #FFFFFF;
        }
        
        treeview {
            background-color: #1C1C20;
            color: #E2E2E6;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 6px;
        }
        treeview header button {
            background-color: #18181C;
            color: #FFFFFF;
            font-weight: bold;
            border-bottom: 1px solid rgba(255, 255, 255, 0.12);
        }
        
        button {
            background-color: #1C1C20;
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 6px;
            padding: 6px 16px;
            font-weight: 500;
            font-size: 13px;
            transition: all 0.15s ease;
        }
        button:hover {
            background-color: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.2);
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #007aff, #0056b3);
            border: none;
            color: #FFFFFF;
            font-weight: 600;
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, #1a8aff, #0066d6);
            box-shadow: 0 2px 8px rgba(0, 122, 255, 0.4);
        }
        
        .btn-secondary {
            background-color: transparent;
            border-color: rgba(255, 255, 255, 0.15);
            color: rgba(255, 255, 255, 0.85);
        }
        
        messagedialog {
            background-color: #18181C;
            color: #FFFFFF;
        }
        messagedialog label {
            color: #FFFFFF;
        }
        button:disabled {
            opacity: 0.4;
        }
        progressbar trough {
            background-color: rgba(255, 255, 255, 0.08);
            border: none;
            border-radius: 3px;
            min-height: 6px;
        }
        progressbar progress {
            background: linear-gradient(90deg, #007aff, #64DCFF);
            border: none;
            border-radius: 3px;
            min-height: 6px;
        }
"""

_settings_css_applied = False


def apply_settings_css(screen):
    global _settings_css_applied
    if _settings_css_applied:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(SETTINGS_CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _settings_css_applied = True
