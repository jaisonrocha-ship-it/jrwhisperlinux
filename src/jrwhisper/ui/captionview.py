"""Legendas em Cairo: blocos estáveis, rolagem suave, reler com a roda e o efeito lente.

Usado pelo overlay (legendas ao vivo) e pela pré-visualização dos Ajustes: o que se ajusta é
exatamente o que aparece.

Foco estável: a frase fechada mais nova fica `zoom` vezes maior numa faixa fixa do cartão; as
anteriores sobem em tamanho normal, esmaecendo com a idade; a prévia em andamento vem logo abaixo,
em itálico. O tamanho de cada frase só muda numa transição curta no tempo, quando uma frase nova
fecha (a anterior encolhe, a nova entra com fade), nunca conforme a posição da rolagem: o texto
que você está lendo não cresce nem encolhe enquanto anda.
"""
import math
import time

import cairo
from gi.repository import GLib, Pango, PangoCairo

from .visuals import CARD, CARD_ALPHA, rounded_rect

LENS_POS = {"top": 0.35, "center": 0.5, "bottom": 0.65}
RESUME_SECS = 8   # relendo e parado este tempo: volta ao vivo
SWAP = 14         # rapidez da troca de foco (≈0,2 s)


class CaptionView:
    def __init__(self, config, scale=1.0, accent=(0.49, 0.42, 1.0)):
        self.scale = scale
        self.font_px = 14.5 * scale
        self.line_h = self.font_px * 1.45
        self.pad = 12 * scale
        self.accent = accent
        self.lens = bool(config.get("caption_lens", True))
        self.zoom = float(config.get("caption_lens_zoom", 1.5)) if self.lens else 1.0
        self.focus = LENS_POS.get(config.get("caption_lens_pos", "center"), 0.5)
        self.blocks, self.live = [], ""
        self.scroll = 0.0          # rolagem desenhada (anima até o alvo)
        self.target = self.lo = 0.0
        self.follow = True         # acompanha o mais novo; a roda do mouse pausa para reler
        self.user, self.user_t = 0.0, 0.0
        self._h = {}               # altura de cada bloco já medido (frases fechadas não mudam)
        self._anim = {}            # frase → [escala, alfa] animados (foco estável)

    # ── estado ─────────────────────────────────────────────────────
    def set_text(self, blocks, live):
        self.blocks, self.live = blocks, live

    def advance(self, dt):
        if not self.follow and time.monotonic() - self.user_t > RESUME_SECS:
            self.follow = True
        goal = self.target if self.follow else self.user
        self.scroll += (goal - self.scroll) * (1 - math.exp(-dt * 12))  # desliza, não salta
        if self.lens:
            k = 1 - math.exp(-dt * SWAP)
            last = len(self.blocks) - 1
            for i, t in enumerate(self.blocks):
                st = self._anim.setdefault(t, [self.zoom if i == last else 1.0, 0.0])  # nova: já no tamanho, some → aparece
                st[0] += ((self.zoom if i == last else 1.0) - st[0]) * k
                st[1] += (1.0 - st[1]) * k
            if len(self._anim) > 400:
                self._anim = {t: self._anim[t] for t in self.blocks if t in self._anim}

    def _state(self, t, focus):
        return self._anim.get(t) or [self.zoom if focus else 1.0, 1.0]

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
        cr.set_source_rgba(*CARD, CARD_ALPHA * a)
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
        tops, scales, yy = [], [], 0.0
        for t, kind in items:
            key = (t, kind == "live", kind == "new", int(width))
            if key not in self._h:
                self._h[key] = self._layout(cr, t, kind, width).get_pixel_size()[1]
            sc = self._state(t, kind == "new")[0] if (self.lens and kind != "live") else 1.0
            tops.append(yy)
            scales.append(sc)
            yy += self._h[key] * sc + gap * (1.6 if (self.lens and kind == "new") else 1.0)
        total = yy - gap if items else 0.0
        focus_y = self.focus * inner  # relativo ao topo da área de texto
        if self.lens:
            # o centro da frase em foco fica na faixa fixa; a prévia vem por baixo
            last = len(self.blocks) - 1
            anchor = (tops[last] + self._h[(self.blocks[-1], False, True, int(width))] * scales[last] / 2
                      if self.blocks else self.line_h / 2)
            self.target, self.lo = anchor - focus_y, self.line_h / 2 - focus_y
        else:
            self.target = total - inner
            self.lo = min(0.0, self.target)

        cr.save()
        cr.rectangle(x, top, w, inner)
        cr.clip()
        n_items = len(items)
        for idx, ((t, kind), ty, sc) in enumerate(zip(items, tops, scales)):
            key = (t, kind == "live", kind == "new", int(width))
            if ty + self._h[key] * sc < self.scroll - inner or ty > self.scroll + 2 * inner:
                continue  # longe da área visível: nem diagrama
            lay = self._layout(cr, t, kind, width)
            if self.lens:
                age = (n_items - 1 - idx) - (1 if self.live else 0)  # 0 = foco, 1 = anterior…
                fade = self._state(t, kind == "new")[1] if kind != "live" else 1.0
                cr.save()
                cr.translate(x + w / 2, top + ty - self.scroll)
                cr.scale(sc, sc)
                cr.move_to(-width / 2, 0)
                cr.set_source_rgba(1, 1, 1, self._focus_alpha(kind, age) * fade * a)
                PangoCairo.show_layout(cr, lay)
                cr.restore()
            else:
                cr.move_to(x + self.pad, top + ty - self.scroll)
                cr.set_source_rgba(1, 1, 1, self._alpha(kind) * a)
                PangoCairo.show_layout(cr, lay)
        cr.restore()
        self._fades(cr, x, y, w, h, top, inner, a)
        if not self.follow:
            self._live_badge(cr, x, y, w, h, a)

    def _alpha(self, kind):
        alpha = {"new": 1.0, "prev": 0.75, "old": 0.5, "live": 0.55}[kind]
        return 0.92 if not self.follow and kind in ("prev", "old") else alpha  # relendo: tudo legível

    def _focus_alpha(self, kind, age):
        """Foco estável: o foco inteiro; as anteriores esmaecem com a idade; a prévia legível, em itálico."""
        if kind == "live":
            return 0.62
        if kind == "new":
            return 1.0
        alpha = max(0.32, 0.78 - 0.16 * (age - 1))
        return max(alpha, 0.85) if not self.follow else alpha  # relendo: tudo legível

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
            g.add_color_stop_rgba(0, *CARD, CARD_ALPHA * a)
            g.add_color_stop_rgba(1, *CARD, 0.0)
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
