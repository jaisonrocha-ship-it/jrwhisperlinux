"""Visuais do ditado desenhados em Cairo: Orbe (padrão), Ondas e Barras.

Independentes de janela: o overlay e a pré-visualização das Configurações
chamam set_level/set_bands/set_state, advance(dt) e draw(cr, cx, cy).
A suavização aqui é só visual; a detecção de fala usa o RMS instantâneo.
"""
import math

import cairo
import numpy as np
from .theme import accent_pair, draw_icon, hex_to_rgb

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
    """Esfera de plasma: bolhas de luz se misturando dentro de uma membrana que ondula com a voz."""
    RING = 140   # diâmetro da esfera no tamanho M
    PAD = 46     # espaço do brilho em volta
    BLOBS = (    # raio da órbita, raio da bolha, vel. x, vel. y, fase, mistura início→fim
        (0.34, 0.66, 1.00, 1.30, 0.0, 0.0),
        (0.40, 0.58, -1.20, 0.90, 2.1, 1.0),
        (0.30, 0.52, 0.80, -1.10, 4.0, 0.5),
        (0.42, 0.46, -0.70, -1.50, 1.3, 0.2),
        (0.24, 0.42, 1.50, 0.60, 5.2, 0.8),
    )

    def __init__(self, config):
        super().__init__(config)
        self.angle = 0.0   # fase do plasma

    def size(self):
        d = (self.RING + 2 * self.PAD) * self.scale
        return d, d

    def advance(self, dt):
        super().advance(dt)
        if self.reduce_motion:
            return
        speed = {"transcribing": 2.6, "listening": 0.6 + 2.2 * self.level,
                 "calibrating": 0.5, "error": 0.2}.get(self.state, 0.4)
        self.angle += speed * dt

    def _membrane(self, cr, cx, cy, r, lv):
        """Contorno ondulado: soma de senos no ângulo, amplitude segue a voz."""
        p, amp = self.angle, 0.018 + 0.11 * lv
        n = 72
        for i in range(n + 1):
            th = 2 * math.pi * i / n
            k = 1 + amp * (0.6 * math.sin(3 * th + p * 1.3)
                           + 0.4 * math.sin(2 * th - p * 0.9 + 2.0)
                           + 0.3 * math.sin(5 * th - p * 1.7 + 1.0))
            x, y = cx + r * k * math.cos(th), cy + r * k * math.sin(th)
            cr.line_to(x, y) if i else cr.move_to(x, y)
        cr.close_path()

    def draw(self, cr, cx, cy):
        """Vidro luminoso: corpo translúcido (a tela aparece atrás), plasma por dentro e borda de luz.
        A voz (curva perceptual: fala baixa já mexe) cresce a esfera até +25%, acende o núcleo e a borda."""
        s = self.scale
        lv = self.level ** 0.7
        breathe = 0 if self.reduce_motion else 0.018 * math.sin(self.t * 2.2)
        pulse = 0.0
        if self.state == "transcribing" and not self.reduce_motion:
            pulse = 0.5 + 0.5 * math.sin(self.t * 5.0)
        r = self.RING / 2 * s * (1 + 0.25 * lv + breathe)
        c0, c1 = self.colors
        mid = _lerp(c0, c1, 0.5)
        intensity = self.glow * (0.7 + 0.9 * lv + 0.35 * pulse)
        reach = min(r * 1.6, self.size()[0] / 2)  # o brilho não passa da área do visual

        cr.save()
        cr.set_operator(cairo.OPERATOR_ADD)  # luz soma luz; sem halo escuro (era mancha em fundo claro)
        glow = cairo.RadialGradient(cx, cy, r * 0.85, cx, cy, reach)
        glow.add_color_stop_rgba(0, *mid, 0.42 * intensity)
        glow.add_color_stop_rgba(0.4, *mid, 0.12 * intensity)
        glow.add_color_stop_rgba(1, *mid, 0.0)
        cr.set_source(glow)
        cr.arc(cx, cy, reach, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

        # corpo de vidro fumê: translúcido, mas escuro o bastante para o mic branco ler sobre qualquer fundo
        self._membrane(cr, cx, cy, r, lv)
        body = cairo.RadialGradient(cx, cy - r * 0.3, r * 0.1, cx, cy, r)
        body.add_color_stop_rgba(0, 0.10, 0.07, 0.24, 0.50)
        body.add_color_stop_rgba(1, 0.05, 0.03, 0.14, 0.62)
        cr.set_source(body)
        cr.fill_preserve()

        cr.save()
        cr.clip()
        cr.set_operator(cairo.OPERATOR_ADD)
        p = self.angle
        for orbit, rad, vx, vy, ph, mix in self.BLOBS:
            bx = cx + r * orbit * math.cos(p * vx + ph)
            by = cy + r * orbit * math.sin(p * vy + ph)
            br = r * rad * (1 + 0.4 * lv)
            c = _lerp(c0, c1, mix)
            g = cairo.RadialGradient(bx, by, 0, bx, by, br)
            g.add_color_stop_rgba(0, *c, 0.55 * intensity)
            g.add_color_stop_rgba(0.45, *c, 0.22 * intensity)
            g.add_color_stop_rgba(1, *c, 0.0)
            cr.set_source(g)
            cr.arc(bx, by, br, 0, 2 * math.pi)  # só o disco da bolha, não a área toda
            cr.fill()
        # borda de luz (fresnel): mais forte e larga com a voz
        rim = cairo.RadialGradient(cx, cy, r * (0.6 - 0.1 * lv), cx, cy, r * 1.08)
        rim.add_color_stop_rgba(0, *c1, 0.0)
        rim.add_color_stop_rgba(0.7, *c1, (0.10 + 0.12 * lv) * intensity)
        rim.add_color_stop_rgba(1, *_lerp(c1, (1, 1, 1), 0.35 + 0.3 * lv), 0.8 * intensity)
        cr.set_source(rim)
        cr.arc(cx, cy, r * 1.08, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

        # reflexo de vidro no alto
        hx, hy = cx - r * 0.32, cy - r * 0.48
        spec = cairo.RadialGradient(hx, hy, 0, hx, hy, r * 0.42)
        spec.add_color_stop_rgba(0, 1, 1, 1, 0.22)
        spec.add_color_stop_rgba(1, 1, 1, 1, 0.0)
        cr.set_source(spec)
        cr.arc(hx, hy, r * 0.42, 0, 2 * math.pi)
        cr.fill()

        # ícone central: check no sucesso, mic no resto (sombra leve: lê sobre o plasma claro)
        if self.state == "success":
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            k = 13 * s
            for dy, rgba, width in ((1.2 * s, (0, 0, 0, 0.3), 4.4), (0, (1, 1, 1, 0.95), 3.2)):
                cr.move_to(cx - k, cy + 0.5 + dy)
                cr.line_to(cx - k * 0.3, cy + k * 0.65 + dy)
                cr.line_to(cx + k, cy - k * 0.6 + dy)
                cr.set_source_rgba(*rgba)
                cr.set_line_width(width * s)
                cr.stroke()
        else:
            alpha = 0.55 if self.state in ("transcribing", "calibrating") else 0.95
            draw_icon(cr, "mic", cx, cy + 1.2 * s, 34 * s, (0, 0, 0, 0.3 * alpha), 2.6)
            draw_icon(cr, "mic", cx, cy, 34 * s, (1, 1, 1, alpha), 1.8)


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
