"""Legendas em Cairo: blocos estáveis, rolagem suave, reler com a roda e o efeito lente.

Usado pelo overlay (legendas ao vivo) e pela pré-visualização dos Ajustes: o que se ajusta é
exatamente o que aparece.

Lente (olho-de-peixe vertical): a linha no foco fica `zoom` vezes maior e as vizinhas encolhem
numa curva gaussiana de largura `reach`; nas bordas a escala cai para `e` < 1, calculado para a
altura total de cada lado do foco não mudar (o cartão não cresce). Com a lente, o foco acompanha
a frase fechada mais nova; a prévia em andamento fica abaixo, pequena, até subir para o foco.
"""
import math
import time

import cairo
from gi.repository import GLib, Pango, PangoCairo

from .visuals import rounded_rect

LENS_POS = {"top": 0.35, "center": 0.5, "bottom": 0.65}
MIN_EDGE = 0.55   # menor escala nas bordas: abaixo disso não dá para ler
RESUME_SECS = 8   # relendo e parado este tempo: volta ao vivo


def lens_edge(zoom, reach, side):
    """Escala nas bordas para que ∫₀^side s(d) dd = side, com s(d) = e + (zoom − e)·exp(−(d/reach)²)."""
    g = reach * math.sqrt(math.pi) / 2 * math.erf(side / reach)
    if side <= g * zoom or side <= g:  # lente maior que o lado: encolhe o mínimo legível
        return MIN_EDGE
    return max(MIN_EDGE, min(1.0, (side - zoom * g) / (side - g)))


def lens_map(d, zoom, reach, edge):
    """(deslocamento desenhado, escala) de uma linha a `d` px do foco."""
    fall = math.exp(-(d / reach) ** 2)
    shift = edge * d + (zoom - edge) * reach * math.sqrt(math.pi) / 2 * math.erf(d / reach)
    return shift, edge + (zoom - edge) * fall


class CaptionView:
    def __init__(self, config, scale=1.0, accent=(0.49, 0.42, 1.0)):
        self.scale = scale
        self.font_px = 14.5 * scale
        self.line_h = self.font_px * 1.45
        self.pad = 12 * scale
        self.accent = accent
        self.lens = bool(config.get("caption_lens"))
        self.zoom = float(config.get("caption_lens_zoom", 1.5)) if self.lens else 1.0
        self.reach = float(config.get("caption_lens_reach", 2)) * self.line_h
        self.focus = LENS_POS.get(config.get("caption_lens_pos", "center"), 0.5)
        self.blocks, self.live = [], ""
        self.scroll = 0.0          # rolagem desenhada (anima até o alvo)
        self.target = self.lo = 0.0
        self.follow = True         # acompanha o mais novo; a roda do mouse pausa para reler
        self.user, self.user_t = 0.0, 0.0
        self._h = {}               # altura de cada bloco já medido (frases fechadas não mudam)

    # ── estado ─────────────────────────────────────────────────────
    def set_text(self, blocks, live):
        self.blocks, self.live = blocks, live

    def advance(self, dt):
        if not self.follow and time.monotonic() - self.user_t > RESUME_SECS:
            self.follow = True
        goal = self.target if self.follow else self.user
        self.scroll += (goal - self.scroll) * (1 - math.exp(-dt * 9))  # desliza, não salta

    def scroll_by(self, step):
        start = self.scroll if self.follow else self.user
        self.user = max(self.lo, min(self.target, start + step * 2 * self.line_h))
        self.follow = self.user >= self.target - 1
        self.user_t = time.monotonic()

    # ── desenho ────────────────────────────────────────────────────
    def _layout(self, cr, text, kind, width):
        lay = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription.from_string("Inter")
        fd.set_absolute_size(self.font_px * Pango.SCALE)
        fd.set_weight(Pango.Weight.MEDIUM if kind == "new" else Pango.Weight.NORMAL)
        lay.set_font_description(fd)
        lay.set_width(int(width * Pango.SCALE))
        lay.set_wrap(Pango.WrapMode.WORD_CHAR)
        lay.set_alignment(Pango.Alignment.CENTER if self.lens else Pango.Alignment.LEFT)
        markup = GLib.markup_escape_text(text)
        lay.set_markup(f"<i>{markup}</i>" if kind == "live" else markup, -1)
        return lay

    def draw(self, cr, x, y, w, h, a=1.0):
        rounded_rect(cr, x, y, w, h, 16 * self.scale)
        cr.set_source_rgba(0.09, 0.09, 0.11, 0.86 * a)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.08 * a)
        cr.set_line_width(1)
        cr.stroke()

        top, inner = y + self.pad, h - 2 * self.pad
        width = (w - 2 * self.pad) / self.zoom  # a linha do foco, aumentada, ainda cabe no cartão
        gap = self.line_h * 0.4
        n = len(self.blocks)
        items = [(t, "new" if i == n - 1 else ("prev" if i == n - 2 else "old")) for i, t in enumerate(self.blocks)]
        if self.live:
            items.append((self.live, "live"))
        if len(self._h) > 400:
            self._h.clear()
        tops, yy = [], 0.0
        for t, kind in items:
            key = (t, kind == "live", kind == "new", int(width))
            if key not in self._h:
                self._h[key] = self._layout(cr, t, kind, width).get_pixel_size()[1]
            tops.append(yy)
            yy += self._h[key] + gap
        total = yy - gap if items else 0.0
        focus_y = self.focus * inner  # relativo ao topo da área de texto
        if self.lens:
            # o foco acompanha a última linha da frase fechada mais nova; a prévia vem por baixo
            last = len(self.blocks) - 1
            anchor = (tops[last] + self._h[(self.blocks[-1], False, True, int(width))] - self.line_h / 2
                      if self.blocks else self.line_h / 2)
            self.target, self.lo = anchor - focus_y, self.line_h / 2 - focus_y
        else:
            self.target = total - inner
            self.lo = min(0.0, self.target)

        cr.save()
        cr.rectangle(x, top, w, inner)
        cr.clip()
        for (t, kind), ty in zip(items, tops):
            key = (t, kind == "live", kind == "new", int(width))
            if ty + self._h[key] < self.scroll - inner or ty > self.scroll + 2 * inner:
                continue  # longe da área visível: nem diagrama
            lay = self._layout(cr, t, kind, width)
            if self.lens:
                self._draw_lens_lines(cr, lay, kind, x, w, top, inner, ty, a)
            else:
                cr.move_to(x + self.pad, top + ty - self.scroll)
                cr.set_source_rgba(1, 1, 1, self._alpha(kind) * a)
                PangoCairo.show_layout(cr, lay)
        cr.restore()
        self._fades(cr, x, y, w, h, top, inner, a)
        if not self.follow:
            self._live_badge(cr, x, y, w, h, a)

    def _alpha(self, kind, fall=None):
        if fall is not None:  # lente: o brilho também cai com a distância do foco
            base = 0.55 if kind == "live" else 1.0
            alpha = base * (0.4 + 0.6 * fall)
            return max(alpha, 0.8) if not self.follow and kind != "live" else alpha
        alpha = {"new": 1.0, "prev": 0.75, "old": 0.5, "live": 0.55}[kind]
        return 0.92 if not self.follow and kind in ("prev", "old") else alpha  # relendo: tudo legível

    def _draw_lens_lines(self, cr, lay, kind, x, w, top, inner, ty, a):
        """Cada linha do bloco no lugar e no tamanho que a lente dá (escala em torno do centro dela)."""
        focus = top + self.focus * inner
        it = lay.get_iter()
        while True:
            line = it.get_line_readonly()
            y0, y1 = (v / Pango.SCALE for v in it.get_line_yrange())
            baseline = it.get_baseline() / Pango.SCALE
            d = top + ty + (y0 + y1) / 2 - self.scroll - focus
            side = (focus - top) if d < 0 else (top + inner - focus)
            shift, sc = lens_map(d, self.zoom, self.reach, lens_edge(self.zoom, self.reach, side))
            cy = focus + shift
            if top - self.line_h * self.zoom < cy < top + inner + self.line_h * self.zoom:
                _ink, logical = line.get_pixel_extents()
                cr.save()
                cr.translate(x + w / 2, cy)
                cr.scale(sc, sc)
                cr.move_to(-logical.width / 2 - logical.x, baseline - (y0 + y1) / 2)
                cr.set_source_rgba(1, 1, 1, self._alpha(kind, math.exp(-(d / self.reach) ** 2)) * a)
                PangoCairo.show_layout_line(cr, line)
                cr.restore()
            if not it.next_line():
                break

    def _fades(self, cr, x, y, w, h, top, inner, a):
        """Linhas que entram/saem somem num degradê (embaixo também, com a lente: a prévia vem de lá)."""
        cr.save()
        rounded_rect(cr, x, y, w, h, 16 * self.scale)
        cr.clip()
        edges = [(y, top + self.line_h * 1.2)]
        if self.lens:
            edges.append((y + h, top + inner - self.line_h * 1.2))
        for start, end in edges:
            g = cairo.LinearGradient(0, start, 0, end)
            g.add_color_stop_rgba(0, 0.09, 0.09, 0.11, 0.86 * a)
            g.add_color_stop_rgba(1, 0.09, 0.09, 0.11, 0.0)
            cr.rectangle(x, min(start, end), w, abs(end - start))
            cr.set_source(g)
            cr.fill()
        cr.restore()

    def _live_badge(self, cr, x, y, w, h, a):
        lay = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription.from_string("Inter")
        fd.set_absolute_size(11 * self.scale * Pango.SCALE)
        fd.set_weight(Pango.Weight.SEMIBOLD)
        lay.set_font_description(fd)
        lay.set_text("↓ ao vivo", -1)
        tw, th = lay.get_pixel_size()
        px, py = 8 * self.scale, 3 * self.scale
        bx, by = x + w - tw - 2 * px - 10 * self.scale, y + h - th - 2 * py - 8 * self.scale
        rounded_rect(cr, bx, by, tw + 2 * px, th + 2 * py, (th + 2 * py) / 2)
        cr.set_source_rgba(*self.accent, 0.9 * a)
        cr.fill()
        cr.move_to(bx + px, by + py)
        cr.set_source_rgba(1, 1, 1, a)
        PangoCairo.show_layout(cr, lay)
