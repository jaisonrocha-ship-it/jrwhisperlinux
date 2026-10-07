"""Visuais do ditado desenhados em Cairo: Orbe (padrão), Ondas e Barras.

Independentes de janela: o overlay e a pré-visualização das Configurações
chamam set_level/set_bands/set_state, advance(dt) e draw(cr, cx, cy).
A suavização aqui é só visual; a detecção de fala usa o RMS instantâneo.
"""
import math

import cairo
import numpy as np
from gi.repository import Gdk, GdkPixbuf

from .theme import ICONS, accent_pair, hex_to_rgb

SIZE_SCALE = {"s": 0.8, "m": 1.0, "l": 1.25}

# estado → cores (início, fim) quando não seguem o acento
STATE_COLORS = {
    "calibrating": ("#FFC83C", "#FF9F0A"),
    "success": ("#30D158", "#2EC8FF"),
    "error": ("#FF6B5E", "#FF375F"),
}


def spectrum_bands(samples, sr=16000, n_bands=32, fmin=90.0, fmax=7000.0):
    """Bandas logarítmicas 0..1 dos últimos ~64 ms (-90 dBFS → 0, -30 dBFS → 1)."""
    if len(samples) < 256:
        return np.zeros(n_bands)
    x = np.asarray(samples[-1024:], dtype=np.float32)
    x = x * np.hanning(len(x))
    mag = np.abs(np.fft.rfft(x)) / len(x)
    freqs = np.fft.rfftfreq(len(x), 1.0 / sr)
    edges = np.geomspace(fmin, fmax, n_bands + 1)
    out = np.empty(n_bands)
    for i in range(n_bands):
        m = (freqs >= edges[i]) & (freqs < edges[i + 1])
        out[i] = mag[m].max() if m.any() else mag[np.argmin(np.abs(freqs - edges[i]))]
    db = 20 * np.log10(out + 1e-9)
    return np.clip((db + 90.0) / 60.0, 0.0, 1.0)


def _lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _icon_pixbuf(name, size, color="#FFFFFF", stroke=2.0):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
    loader.set_size(size, size)
    loader.write(svg.encode())
    loader.close()
    return loader.get_pixbuf()


def rounded_rect(cr, x, y, w, h, r):
    r = max(0.0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class Visual:
    """Base: nível suavizado, estado e cores com transição."""

    def __init__(self, config):
        self.scale = SIZE_SCALE.get(config.get("overlay_size", "m"), 1.0)
        self.glow = float(config.get("overlay_glow", 0.8))
        self.reduce_motion = bool(config.get("reduce_motion", False))
        self.accent = tuple(hex_to_rgb(c) for c in accent_pair(config))
        self.colors = self.accent
        self.level = 0.0
        self.target = 0.0
        self.t = 0.0
        self.state = "waiting"
        self.state_t = 0.0

    def set_level(self, level):
        self.target = float(np.clip(level, 0.0, 1.0))

    def set_bands(self, bands):
        pass

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.state_t = 0.0

    def _target_colors(self):
        pair = STATE_COLORS.get(self.state)
        if pair:
            return tuple(hex_to_rgb(c) for c in pair)
        if self.state == "transcribing":
            return (self.accent[1], self.accent[0])
        return self.accent

    def advance(self, dt):
        self.t += dt
        self.state_t += dt
        k = 1 - math.exp(-dt * (18 if self.target > self.level else 7))  # sobe rápido, desce suave
        self.level += (self.target - self.level) * k
        tc = self._target_colors()
        kc = 1 - math.exp(-dt * 6)
        self.colors = (_lerp(self.colors[0], tc[0], kc), _lerp(self.colors[1], tc[1], kc))

    def gradient(self, x0, y0, x1, y1, alpha=1.0, a0=0.6):
        g = cairo.LinearGradient(x0, y0, x1, y1)
        c0, c1 = self.colors
        mid = _lerp(c0, c1, 0.5)
        g.add_color_stop_rgba(0.0, *c0, alpha * a0)
        g.add_color_stop_rgba(0.5, *mid, alpha * (a0 + 1) / 2)
        g.add_color_stop_rgba(1.0, *c1, alpha)
        return g


class OrbVisual(Visual):
    """Anel luminoso com o mic no centro (referência: orbe índigo/violeta)."""
    RING = 140   # diâmetro do anel no tamanho M
    PAD = 46     # espaço do brilho em volta

    def __init__(self, config):
        super().__init__(config)
        self.angle = 0.0
        self.mic = _icon_pixbuf("mic", int(34 * self.scale), stroke=1.8)
        self.check = None

    def size(self):
        d = (self.RING + 2 * self.PAD) * self.scale
        return d, d

    def advance(self, dt):
        super().advance(dt)
        if self.reduce_motion:
            return
        speed = {"transcribing": 3.2, "listening": 0.7 + 2.6 * self.level,
                 "calibrating": 0.5, "error": 0.2}.get(self.state, 0.45)
        self.angle += speed * dt

    def draw(self, cr, cx, cy):
        s = self.scale
        breathe = 0 if self.reduce_motion else 0.018 * math.sin(self.t * 2.2)
        pulse = 0.0
        if self.state == "transcribing" and not self.reduce_motion:
            pulse = 0.5 + 0.5 * math.sin(self.t * 5.0)
        r = self.RING / 2 * s * (1 + 0.10 * self.level + breathe)
        ring_w = 7 * s * (1 + 0.45 * self.level)
        a = self.angle
        dx, dy = r * math.cos(a), r * math.sin(a)

        # fundo escuro: contraste sobre qualquer desktop (o brilho aditivo precisa dele)
        halo = cairo.RadialGradient(cx, cy, r * 0.4, cx, cy, r * 1.7)
        halo.add_color_stop_rgba(0, 0.07, 0.05, 0.20, 0.92)
        halo.add_color_stop_rgba(0.55, 0.06, 0.04, 0.17, 0.72)
        halo.add_color_stop_rgba(1, 0.05, 0.04, 0.15, 0.0)
        cr.set_source(halo)
        cr.arc(cx, cy, r * 1.7, 0, 2 * math.pi)
        cr.fill()
        # miolo sólido: o desktop não pode aparecer através do orbe
        core = cairo.RadialGradient(cx, cy - r * 0.3, r * 0.1, cx, cy, r)
        core.add_color_stop_rgba(0, 0.11, 0.08, 0.27, 0.97)
        core.add_color_stop_rgba(1, 0.06, 0.04, 0.16, 0.97)
        cr.set_source(core)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill()

        cr.save()
        cr.set_operator(cairo.OPERATOR_ADD)  # neon: as camadas somam luz
        intensity = self.glow * (0.7 + 0.7 * self.level + 0.4 * pulse)
        passes = 12
        for k in range(passes, 0, -1):
            f = k / passes
            cr.set_line_width(ring_w + f * 44 * s)
            cr.set_source(self.gradient(cx - dx, cy - dy, cx + dx, cy + dy,
                                        alpha=0.11 * intensity * (1 - f) ** 1.6, a0=0.45))
            cr.arc(cx, cy, r, 0, 2 * math.pi)
            cr.stroke()

        # anel secundário girando ao contrário, dá profundidade
        r2 = r * (0.955 - 0.03 * self.level)
        b = -a * 1.4 + 1.2
        cr.set_line_width(ring_w * 0.7)
        cr.set_source(self.gradient(cx + r2 * math.cos(b), cy + r2 * math.sin(b),
                                    cx - r2 * math.cos(b), cy - r2 * math.sin(b), alpha=0.35, a0=0.05))
        cr.arc(cx, cy, r2, 0, 2 * math.pi)
        cr.stroke()

        # anel principal: base fina + meia-lua mais grossa e brilhante do lado "quente"
        cr.set_line_width(ring_w * 0.55)
        cr.set_source(self.gradient(cx - dx, cy - dy, cx + dx, cy + dy, alpha=0.85, a0=0.55))
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        cr.set_line_width(ring_w)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source(self.gradient(cx - dx, cy - dy, cx + dx, cy + dy, alpha=0.9, a0=0.0))
        cr.arc(cx, cy, r, a - 1.7, a + 1.7)
        cr.stroke()
        # núcleo branco no ponto mais quente
        cr.set_line_width(ring_w * 0.35)
        cr.set_source_rgba(1, 1, 1, 0.35 + 0.35 * self.level)
        cr.arc(cx, cy, r, a - 0.55, a + 0.55)
        cr.stroke()
        cr.restore()

        # disco interno de vidro
        inner = r - ring_w * 1.6
        disc = cairo.RadialGradient(cx, cy - inner * 0.35, inner * 0.05, cx, cy, inner * 0.62)
        disc.add_color_stop_rgba(0, 1, 1, 1, 0.12)
        disc.add_color_stop_rgba(1, 1, 1, 1, 0.04)
        cr.set_source(disc)
        cr.arc(cx, cy, inner * 0.62, 0, 2 * math.pi)
        cr.fill()

        # ícone central: check no sucesso, mic no resto
        if self.state == "success":
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.set_line_width(3.2 * s)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            k = 13 * s
            cr.move_to(cx - k, cy + 0.5)
            cr.line_to(cx - k * 0.3, cy + k * 0.65)
            cr.line_to(cx + k, cy - k * 0.6)
            cr.stroke()
        else:
            alpha = 0.55 if self.state in ("transcribing", "calibrating") else 0.95
            w, h = self.mic.get_width(), self.mic.get_height()
            Gdk.cairo_set_source_pixbuf(cr, self.mic, cx - w / 2, cy - h / 2)
            cr.paint_with_alpha(alpha)


class WaveVisual(Visual):
    """Pílula com ondas fluidas (referência: ondas estilo Siri)."""
    W, H = 380, 64
    WAVES = (  # freq, fase, amplitude relativa, alfa
        (0.016, 0.0, 1.0, 0.95),
        (0.024, 1.9, 0.7, 0.6),
        (0.011, -1.3, 0.55, 0.45),
        (0.032, 3.1, 0.35, 0.35),
    )

    def size(self):
        return self.W * self.scale, self.H * self.scale

    def draw(self, cr, cx, cy):
        w, h = self.size()
        x0, y0 = cx - w / 2, cy - h / 2
        _pill(cr, x0, y0, w, h)
        cr.save()
        rounded_rect(cr, x0, y0, w, h, h / 2)
        cr.clip()
        speed = 0 if self.reduce_motion else (5.5 if self.state == "transcribing" else 3.2)
        floor = 0.22 if self.state == "transcribing" else 0.07
        amp = h * 0.40 * max(self.level ** 0.75, floor)
        pad = h * 0.45
        span = w - 2 * pad
        cr.set_operator(cairo.OPERATOR_ADD)
        for n, (freq, phase, rel, alpha) in enumerate(self.WAVES):
            path = []
            for i in range(0, int(span) + 1, 3):
                env = math.sin(math.pi * i / span) ** 1.6
                y = cy + amp * rel * env * math.sin(i * freq / self.scale + self.t * speed * (1 + 0.15 * n) + phase)
                path.append((x0 + pad + i, y))

            def trace():
                cr.move_to(*path[0])
                for p in path[1:]:
                    cr.line_to(*p)
            trace()
            cr.line_to(path[-1][0], cy)
            cr.line_to(path[0][0], cy)
            cr.close_path()
            cr.set_source(self.gradient(x0, 0, x0 + w, 0, alpha=alpha * 0.22, a0=0.7))
            cr.fill()
            for width, a in ((6.0, 0.18), (1.8, 1.0)):  # brilho largo + linha nítida
                trace()
                cr.set_line_width(width * self.scale)
                cr.set_source(self.gradient(x0, 0, x0 + w, 0, alpha=alpha * a, a0=0.75))
                cr.stroke()
        cr.restore()


class BarsVisual(Visual):
    """Pílula com barras de espectro e reflexo (referência: barras ciano → azul)."""
    W, H = 380, 64
    N = 32

    def __init__(self, config):
        super().__init__(config)
        self.bands = np.zeros(self.N)
        self.shown = np.zeros(self.N)

    def size(self):
        return self.W * self.scale, self.H * self.scale

    def set_bands(self, bands):
        self.bands = np.asarray(bands, dtype=float)[: self.N]

    def advance(self, dt):
        super().advance(dt)
        target = self.bands
        if self.state == "transcribing" and not self.reduce_motion:
            i = np.arange(self.N)
            target = 0.25 + 0.2 * np.sin(i * 0.5 - self.t * 6)  # varredura enquanto transcreve
        up = target > self.shown
        k_up, k_down = 1 - math.exp(-dt * 30), 1 - math.exp(-dt * 6)
        self.shown += (target - self.shown) * np.where(up, k_up, k_down)

    def draw(self, cr, cx, cy):
        w, h = self.size()
        x0, y0 = cx - w / 2, cy - h / 2
        _pill(cr, x0, y0, w, h)
        pad = h * 0.45
        span = w - 2 * pad
        gap = span / self.N
        bw = gap * 0.62
        base = y0 + h * 0.66
        max_h = h * 0.50
        grad = self.gradient(x0 + pad, 0, x0 + w - pad, 0, alpha=1.0, a0=0.95)
        for i, v in enumerate(self.shown):
            bh = max(2.0 * self.scale, v * max_h)
            x = x0 + pad + i * gap + (gap - bw) / 2
            rounded_rect(cr, x, base - bh, bw, bh, bw / 2)
            cr.set_source(grad)
            cr.fill()
            # reflexo: espelhado, curto e desvanecendo
            rh = bh * 0.38
            refl = cairo.LinearGradient(0, base + 1, 0, base + 1 + rh)
            c = _lerp(self.colors[0], self.colors[1], i / self.N)
            refl.add_color_stop_rgba(0, *c, 0.32)
            refl.add_color_stop_rgba(1, *c, 0.0)
            cr.rectangle(x, base + 1.5 * self.scale, bw, rh)
            cr.set_source(refl)
            cr.fill()


def _pill(cr, x, y, w, h):
    rounded_rect(cr, x, y, w, h, h / 2)
    cr.set_source_rgba(0.09, 0.09, 0.11, 0.84)
    cr.fill_preserve()
    hl = cairo.LinearGradient(0, y, 0, y + h)
    hl.add_color_stop_rgba(0, 1, 1, 1, 0.14)
    hl.add_color_stop_rgba(0.5, 1, 1, 1, 0.03)
    hl.add_color_stop_rgba(1, 1, 1, 1, 0.06)
    cr.set_source(hl)
    cr.set_line_width(1.0)
    cr.stroke()


VISUALS = {"orb": OrbVisual, "waves": WaveVisual, "bars": BarsVisual}
VISUAL_LABELS = {"orb": "Orbe", "waves": "Ondas", "bars": "Barras"}


def make_visual(config):
    return VISUALS.get(config.get("overlay_style", "orb"), OrbVisual)(config)
