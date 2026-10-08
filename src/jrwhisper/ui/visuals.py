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
# Superfície de vidro escuro de tudo que o overlay desenha (caixa de texto, legendas, pílula, status):
# um tom só, opaco o bastante para o texto de trás não atravessar a leitura em fundo claro.
CARD = (0.09, 0.09, 0.11)
CARD_ALPHA = 0.95

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

    def gradient_faded(self, x0, x1, alpha=1.0):
        """Horizontal início → fim, com as pontas transparentes: a luz some antes da borda."""
        g = cairo.LinearGradient(x0, 0, x1, 0)
        c0, c1 = self.colors
        g.add_color_stop_rgba(0.0, *c0, 0.0)
        g.add_color_stop_rgba(0.18, *c0, alpha * 0.8)
        g.add_color_stop_rgba(0.5, *_lerp(c0, c1, 0.5), alpha)
        g.add_color_stop_rgba(0.82, *c1, alpha)
        g.add_color_stop_rgba(1.0, *c1, 0.0)
        return g

    def gradient_mirrored(self, x0, x1):
        """Centro na cor inicial, as duas pontas na final: barras espelhadas com cor simétrica."""
        g = cairo.LinearGradient(x0, 0, x1, 0)
        c0, c1 = self.colors
        for stop, c in ((0.0, c1), (0.5, c0), (1.0, c1)):
            g.add_color_stop_rgba(stop, *c, 1.0)
        return g

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
    """Pílula com fitas de luz: cada fita segue uma faixa do espectro (graves embaixo, agudos em cima)
    e as pontas somem no escuro. Sem espectro (prévia dos Ajustes), seguem o nível."""
    W, H = 380, 64
    WAVES = (  # freq, fase, faixa do espectro (início, fim de 32), alfa
        (0.016, 0.0, (0, 8), 0.95),
        (0.024, 1.9, (8, 16), 0.65),
        (0.011, -1.3, (16, 24), 0.5),
        (0.032, 3.1, (24, 32), 0.4),
    )

    def __init__(self, config):
        super().__init__(config)
        self.bands = None
        self.amps = np.zeros(len(self.WAVES))

    def size(self):
        return self.W * self.scale, self.H * self.scale

    def set_bands(self, bands):
        self.bands = np.asarray(bands, dtype=float)

    def advance(self, dt):
        super().advance(dt)
        lv = self.level ** 0.75
        if self.bands is not None and len(self.bands) >= 32 and self.state == "listening":
            # faixa forte = fita alta; o nível geral segura o conjunto (silêncio não vira ruído)
            target = np.array([self.bands[a:b].mean() for _f, _p, (a, b), _a in self.WAVES]) ** 1.5 * (0.4 + 0.6 * lv) * 1.6
        else:
            target = np.full(len(self.WAVES), lv) * np.array([1.0, 0.7, 0.55, 0.35])
        k_up, k_down = 1 - math.exp(-dt * 20), 1 - math.exp(-dt * 7)
        self.amps += (np.clip(target, 0, 1) - self.amps) * np.where(target > self.amps, k_up, k_down)

    def draw(self, cr, cx, cy):
        w, h = self.size()
        x0, y0 = cx - w / 2, cy - h / 2
        _pill(cr, x0, y0, w, h)
        cr.save()
        rounded_rect(cr, x0, y0, w, h, h / 2)
        cr.clip()
        speed = 0 if self.reduce_motion else (5.5 if self.state == "transcribing" else 3.2)
        floor = 0.22 if self.state == "transcribing" else 0.07
        pad = h * 0.45
        span = w - 2 * pad
        step = 4
        xs = np.arange(0, span + step, step)
        env = np.sin(np.pi * np.clip(xs / span, 0, 1)) ** 1.6
        cr.set_operator(cairo.OPERATOR_ADD)
        for n, (freq, phase, _band, alpha) in enumerate(self.WAVES):
            amp = h * 0.42 * max(self.amps[n], floor * (1.0 - 0.15 * n))
            ys = cy + amp * env * np.sin(xs * freq / self.scale + self.t * speed * (1 + 0.15 * n) + phase)
            cr.move_to(x0 + pad, ys[0])
            for x, y in zip(xs[1:], ys[1:]):
                cr.line_to(x0 + pad + x, y)
            path = cr.copy_path()
            cr.line_to(x0 + pad + span, cy)
            cr.line_to(x0 + pad, cy)
            cr.close_path()
            cr.set_source(self.gradient_faded(x0 + pad, x0 + w - pad, alpha * 0.20))
            cr.fill()
            for width, a in ((6.0, 0.20), (1.6, 1.0)):  # brilho largo + fio nítido
                cr.append_path(path)
                cr.set_line_width(width * self.scale)
                cr.set_source(self.gradient_faded(x0 + pad, x0 + w - pad, alpha * a))
                cr.stroke()
        cr.restore()


class BarsVisual(Visual):
    """Pílula com barras espelhadas (estilo Gravador de Voz): graves no centro, agudos para as pontas,
    crescendo para cima e para baixo da linha média; o pico de cada barra cai devagar."""
    W, H = 380, 64
    N = 32          # bandas recebidas
    SIDE = 16       # barras de cada lado do centro

    def __init__(self, config):
        super().__init__(config)
        self.bands = np.zeros(self.N)
        self.shown = np.zeros(self.SIDE)
        self.peaks = np.zeros(self.SIDE)
        self.peak_v = np.zeros(self.SIDE)

    def size(self):
        return self.W * self.scale, self.H * self.scale

    def set_bands(self, bands):
        self.bands = np.asarray(bands, dtype=float)[: self.N]

    def advance(self, dt):
        super().advance(dt)
        b = np.zeros(self.N)
        b[: len(self.bands)] = self.bands
        target = b.reshape(self.SIDE, -1).max(axis=1)  # 32 bandas → 16 (pares)
        if self.state == "transcribing" and not self.reduce_motion:
            i = np.arange(self.SIDE)
            target = 0.22 + 0.18 * np.sin(i * 0.6 - self.t * 6)  # varredura do centro para fora
        up = target > self.shown
        k_up, k_down = 1 - math.exp(-dt * 30), 1 - math.exp(-dt * 8)
        self.shown += (target - self.shown) * np.where(up, k_up, k_down)
        # pico: sobe junto, segura e cai com gravidade
        hit = self.shown >= self.peaks
        self.peak_v = np.where(hit, 0.0, self.peak_v + 2.2 * dt)
        self.peaks = np.where(hit, self.shown, np.maximum(self.shown, self.peaks - self.peak_v * dt))

    def draw(self, cr, cx, cy):
        w, h = self.size()
        x0, y0 = cx - w / 2, cy - h / 2
        _pill(cr, x0, y0, w, h)
        pad = h * 0.45
        gap = (w / 2 - pad) / self.SIDE
        bw = gap * 0.58
        max_h = h * 0.36           # meia altura: cresce para os dois lados da linha média
        grad = self.gradient_mirrored(x0 + pad, x0 + w - pad)
        s = self.scale
        show_peaks = self.state == "listening"
        peaks = []
        for i in range(self.SIDE):  # todas as barras num caminho só: um preenchimento por quadro
            v, pk = self.shown[i], self.peaks[i]
            bh = max(1.5 * s, v * max_h)
            for side in (-1, 1):  # centro = graves; espelhado para as duas pontas
                x = cx + side * (i * gap + gap / 2) - bw / 2
                rounded_rect(cr, x, cy - bh, bw, 2 * bh, bw / 2)
                if show_peaks and pk > v + 0.04:
                    peaks.append((x, pk * max_h + 2.5 * s))
        cr.set_source(grad)
        cr.fill()
        for x, py in peaks:  # marcadores de pico, acima e abaixo, também num preenchimento
            rounded_rect(cr, x, cy - py - 1.2 * s, bw, 2 * s, s)
            rounded_rect(cr, x, cy + py - 0.8 * s, bw, 2 * s, s)
        cr.set_source_rgba(1, 1, 1, 0.5)
        cr.fill()


def card(cr, x, y, w, h, r, a=1.0):
    """Cartão de vidro do overlay: sombra curta (destaca sobre página escura e cheia de texto),
    fundo CARD e borda fina. Deixa o contorno no path para quem quiser traçar por cima."""
    rounded_rect(cr, x - 2.5, y - 0.5, w + 5, h + 5, r + 2.5)  # sombra curta: uma camada, barata
    cr.set_source_rgba(0, 0, 0, 0.22 * a)
    cr.fill()
    rounded_rect(cr, x, y, w, h, r)
    cr.set_source_rgba(*CARD, CARD_ALPHA * a)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 0.13 * a)
    cr.set_line_width(1)
    cr.stroke_preserve()


def _pill(cr, x, y, w, h):
    card(cr, x, y, w, h, h / 2)
    cr.new_path()


VISUALS = {"orb": OrbVisual, "waves": WaveVisual, "bars": BarsVisual}
VISUAL_LABELS = {"orb": "Orbe", "waves": "Ondas", "bars": "Barras"}


def make_visual(config):
    return VISUALS.get(config.get("overlay_style", "orb"), OrbVisual)(config)
