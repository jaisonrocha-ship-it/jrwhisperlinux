# AGENTS.md — JRWhisperLinux

Instructions for AI coding agents (Claude, Codex, Gemini, Hermes) working on this project.

## Project Identity

- **Name:** JRWhisperLinux
- **Purpose:** macOS-WhisperFlow-style voice dictation for Linux X11
- **Language:** Python 3.12 (system Python with `--system-site-packages` venv)
- **User:** JR (Brazilian Portuguese speaker, Linux Mint 22.3 Cinnamon X11, NVIDIA RTX 4060)

## How to Work on This Project

### 1. ALWAYS read these files first
- `README.md` — overview and quick start
- `docs/architecture.md` — how the system works internally
- `docs/changelog.md` — what changed and why

### 2. Runtime Environment
```bash
# The venv must be created with --system-site-packages for GTK3 access
VENV=~/.local/share/dictation-venv
PYTHON=$VENV/bin/python3

# Run the app
$PYTHON src/dictate --status

# Run tests
$PYTHON dev/jrwhisperlinux/tests/test_calibration.py
$PYTHON dev/jrwhisperlinux/tests/test_daemon.py
```

### 3. Key Constraints
- **GTK3 is required** — the overlay uses PyGObject. The venv MUST have `--system-site-packages`.
- **No PortAudio/sounddevice** for mic capture — use `parec` (PulseAudio CLI). PortAudio device enumeration is unreliable.
- **xclip + xdotool for paste** — uses clipboard (`xclip -selection clipboard` + `ctrl+v`) with fallback to `xdotool type --window`.
- **GPU is active (v2.0+)** — CUDA preloaded via `ctypes.cdll.LoadLibrary` from `/opt/resolve/libs/` to bypass lack of system-wide `libcublas.so.12`.
- **Daemon Mode (v2.5+)** — Keep Whisper model loaded in persistent server to eliminate 2s latency. Client talks via socket Unix `/tmp/dictate_daemon.sock`.
- **Silence detection uses VAD hysteresis** — RMS instantâneo com timer de confirmação (150ms) e gap tolerance (2.5s).

### 4. Code Conventions
- Functions use snake_case, classes PascalCase
- Threading: GTK main thread + AudioCapture thread + DictateThread (processing)
- GLib.idle_add for all GTK updates from background threads
- Config via JSON file, auto-calibrated threshold
- Debug output to `/tmp/dictate_*.{wav,log}`

### 5. Known Pitfalls
- **Don't smooth RMS** — RMS smoothing adds latency. Use instantaneous values with speech confirmation ticks.
- **Don't trust sounddevice device indices** — they change between enumerations. Use PulseAudio device names.
- **CUDA OOM on RTX 4060** — desktop uses 4-5GB. medium model in int8_float16 consumes only ~1GB and is fast (0.58s).
- **os.execv breaks sys.argv** — the venv bootstrap re-executes. Use `[VENV_PYTHON, __file__] + sys.argv[1:]`.
- **Yeti GX mute button** — user's Yeti GX captures near-zero when hardware-muted. Check before debugging "no audio".
- **parec latency (PipeWire)** — use `--latency-msec=30` to avoid 2-second fragment bundling and ensure fast start (70ms).

### 6. Priority Roadmap (v3.0)
1. **Wayland support** — ydotool/wtype instead of xdotool/xclip
2. **Packaging** — .deb or AppImage for easy install

### 7. User Preferences
- PT-BR responses always
- No disclaimers — direct technical communication
- Prefers working code over descriptions
- Values polished UX (macOS-level quality)
