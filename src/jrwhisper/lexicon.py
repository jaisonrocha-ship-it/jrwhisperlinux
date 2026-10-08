"""Léxico de logística: jargão do glossário que você usa (e que os livros de porto/comex usam).

Jargão = termo do glossário fora dos dicionários comuns do sistema (pt/en): "stowage", "demurrage",
"laytime" entram; "navio", "frete" o Whisper já acerta. Seus textos (e-mails enviados, ditados) pesam mais
que os livros. A nota "Léxico de logística.md" é a fonte de verdade: risque um termo (~~termo~~) para
tirá-lo (continua riscado ao recriar); acrescente os seus em "Meus termos"; ajuste "Traduções".

Usos: vocabulário do Whisper (termos mais usados), pistas para a IA corrigir palavras parecidas
("demorage" → "demurrage") e traduções PT↔EN certas no modo Inglês e nas legendas.
"""
import collections
import difflib
import glob
import json
import math
import os
import re
import time
import unicodedata

from . import history, style

DICTS = [f"/usr/share/dict/{n}" for n in ("brazilian", "portuguese", "american-english", "british-english")]
BOOK_KEYS = ("logist", "port", "freight", "trade", "incoterm", "container", "maritime", "supply", "export",
             "berth", "terminal", "box", "cltd", "novaes", "stopford", "carriers", "shipping", "comex")
BOOK_SKIP = ("naval", "ship-design", "ships-and-science", "strength", "nutrition", "exercise", "hypertrophy",
             "physiology", "sport", "treino", "citius")
DOMAINS = ("shipping", "aduana", "supplychain")  # várias palavras: "geral"/"economia" trazem frase comum
MAX_TERMS = 300
BOOK_MIN = 20          # termo só dos livros precisa aparecer isto para entrar (tira ruído)
WHISPER_CHARS = 300    # termos no prompt do Whisper (o prompt todo tem ~224 tokens; o começo é cortado)
HINTS_MAX = 8

# Traduções curadas (as do glossário são palavra-por-palavra e erradas: "ore carrier" → "ore transportador").
TRANSLATIONS = [
    ("estufagem", "stuffing"), ("desova", "devanning"), ("armador", "shipowner"), ("transportador", "carrier"),
    ("afretador", "charterer"), ("afretamento", "chartering"), ("contrato de afretamento", "charter party"),
    ("afretamento por viagem", "voyage charter"), ("afretamento por tempo", "time charter"),
    ("conhecimento de embarque", "bill of lading"), ("sobre-estadia", "demurrage"), ("sobrestadia", "demurrage"),
    ("estadia", "laytime"), ("prêmio de despacho", "despatch"), ("detenção de contêiner", "container detention"),
    ("tempo livre", "free time"), ("despachante aduaneiro", "customs broker"),
    ("desembaraço aduaneiro", "customs clearance"), ("recinto alfandegado", "bonded warehouse"),
    ("entreposto aduaneiro", "customs bonded warehouse"), ("porto seco", "dry port"),
    ("terminal retroportuário", "off-dock terminal"), ("zona primária", "primary customs zone"),
    ("atracação", "berthing"), ("desatracação", "unberthing"), ("berço", "berth"),
    ("janela de atracação", "berthing window"), ("fundeadouro", "anchorage"), ("fundeio", "anchorage"),
    ("praticagem", "pilotage"), ("rebocador", "tugboat"), ("calado", "draft"), ("calado aéreo", "air draft"),
    ("porão", "hold"), ("escotilha", "hatch"), ("convés", "deck"), ("peação", "lashing"), ("escoramento", "shoring"),
    ("madeira de estiva", "dunnage"), ("estiva", "stevedoring"), ("estivador", "stevedore"),
    ("estivagem", "stowage"), ("plano de estivagem", "stowage plan"), ("plano de carga", "stowage plan"),
    ("carga solta", "breakbulk cargo"), ("carga geral", "general cargo"), ("granel sólido", "dry bulk"),
    ("granel líquido", "liquid bulk"), ("carga de projeto", "project cargo"), ("carga pesada", "heavy lift cargo"),
    ("bobina de aço", "steel coil"), ("vergalhão", "rebar"), ("chapa grossa", "heavy plate"),
    ("contêiner refrigerado", "reefer container"), ("navio porta-contêiner", "container ship"),
    ("navio graneleiro", "bulk carrier"), ("navio de carga geral", "general cargo ship"), ("cabotagem", "cabotage"),
    ("transbordo", "transshipment"), ("frete marítimo", "ocean freight"), ("frete morto", "dead freight"),
    ("taxa de movimentação no terminal", "terminal handling charge"), ("armazenagem", "storage"),
    ("armazém", "warehouse"), ("pátio", "yard"), ("vistoria", "survey"), ("vistoria de calado", "draft survey"),
    ("romaneio", "packing list"), ("lista de embalagem", "packing list"), ("fatura comercial", "commercial invoice"),
    ("certificado de origem", "certificate of origin"), ("licença de importação", "import license"),
    ("declaração de importação", "import declaration"), ("carta de nomeação", "nomination letter"),
    ("agente marítimo", "shipping agent"), ("agente de cargas", "freight forwarder"),
    ("operador portuário", "port operator"), ("operador logístico", "logistics provider"),
    ("proposta comercial", "commercial proposal"), ("cotação", "quotation"), ("prazo de entrega", "lead time"),
    ("avaria", "damage"), ("avaria grossa", "general average"), ("seguro de carga", "cargo insurance"),
    ("carta de crédito", "letter of credit"), ("rodotrem", "road train"), ("bitrem", "B-double truck"),
    ("carreta", "semi-trailer"), ("semirreboque", "semi-trailer"), ("caminhão", "truck"),
]


def _fold(s):
    """minúsculas sem acento: "Peação" e "peacao" batem."""
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def _common_words():
    words = set()
    for path in DICTS:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                words.update(_fold(w.strip()) for w in f)  # sem acento, como os termos: "preço" = "preco"
        except OSError:
            pass
    return words


def book_dirs(root):
    """Livros de porto/comex/supply chain da pasta de livros (sem arquitetura naval, saúde, treino)."""
    root = os.path.expanduser(root or "")
    if not os.path.isdir(root):
        return []
    return sorted(os.path.join(root, d) for d in os.listdir(root)
                  if any(k in d.lower() for k in BOOK_KEYS) and not any(k in d.lower() for k in BOOK_SKIP))


def _my_texts(config):
    texts = [b for src in config.get("style_sources") or [] if src.get("enabled", True)
             for _d, b in style.sent_messages(src["path"], src.get("filter", "sent") == "sent", src.get("subdirs", True))]
    try:
        texts += [r.get("text", "") for r in history.load(limit=5000)]
    except OSError:
        pass
    return "\n".join(texts)


def build(config):
    """[(termo, sigla, usos seus, ocorrências nos livros)] do mais relevante ao menos (sem LLM, segundos)."""
    with open(os.path.expanduser(config.get("lexicon_glossary") or ""), encoding="utf-8") as f:
        glossary = json.load(f)["terms"]
    common = _common_words()
    mine_raw = _my_texts(config)
    mine = _fold(mine_raw)
    mine_words = collections.Counter(re.findall(r"[a-z][a-z0-9/-]+", mine))
    books = collections.Counter()
    for d in book_dirs(config.get("lexicon_books")):
        for path in glob.glob(os.path.join(d, "**", "*.md"), recursive=True):
            with open(path, encoding="utf-8", errors="ignore") as f:
                books.update(re.findall(r"[a-z][a-z0-9/-]+", _fold(f.read())))
    found = {}
    for t in glossary:
        term, sigla = t.get("termo", "").strip(), t.get("sigla", "").strip()
        key = _fold(term)
        if not key or len(term) > 40:
            continue
        if " " in key:  # ponytail: frase só nos seus textos; procurar 5 mil frases nos livros levaria minutos
            if t.get("domain") not in DOMAINS or all(w in common for w in key.split()) \
                    or all(w[:1].isupper() for w in term.split()):
                continue  # frase comum ("come to") ou nome próprio ("Brooklyn Bridge") não é jargão
            n_mine, n_books = len(re.findall(rf"\b{re.escape(key)}\b", mine)), 0
        else:
            if len(key) < 4 or key in common:  # jargão = fora do dicionário comum
                continue
            n_mine, n_books = mine_words[key], books[key]
        if sigla and sigla.isupper() and 2 <= len(sigla) <= 6 and _fold(sigla) not in common:
            n_sigla = len(re.findall(rf"\b{re.escape(sigla)}\b", mine_raw))  # sigla só conta em MAIÚSCULA
            if n_sigla and not n_mine:  # você usa a sigla, não o nome: "PSC" é Port State Control, não
                term, key, n_books = sigla, _fold(sigla), 0  # "polar stratospheric cloud" do glossário
            n_mine += n_sigla
        if n_mine or n_books >= BOOK_MIN:
            score = 10 * n_mine + math.log1p(n_books)
            if score > found.get(key, (0,))[0]:
                found[key] = (score, term, sigla, n_mine, n_books)
    ranked = sorted(found.values(), key=lambda x: -x[0])[:MAX_TERMS]
    return [(term, sigla, n_mine, n_books) for _s, term, sigla, n_mine, n_books in ranked]


NOTE_HEAD = ("---\ntags: [lexico, jrwhisper]\n---\n# Léxico de logística\n\n"
             "O JRWhisper relê esta nota a cada ditado. Para tirar um termo, risque: `~~termo~~` (continua fora ao "
             "recriar). Acrescente os seus em \"Meus termos\" e ajuste as \"Traduções\". \"Recriar léxico\" "
             "(Ajustes → Texto) só refaz o bloco automático.\n\n")


def _row(cells):
    return "| " + " | ".join(cells) + " |"


def note_text(terms, struck=()):
    """Bloco automático (tabela de termos) + seções suas, para a 1ª criação."""
    struck = {_fold(s) for s in struck}
    rows = [_row([f"~~{t}~~" if _fold(t) in struck else t, s, str(m) if m else "", str(b) if b else ""])
            for t, s, m, b in terms]
    auto = (f"## Termos\n*Gerado em {time.strftime('%d/%m/%Y')} · {len(terms)} termos do glossário que aparecem "
            f"nos seus textos ou nos livros de porto/comex*\n\n"
            + _row(["Termo", "Sigla", "Seus textos", "Livros"]) + "\n" + _row(["---"] * 4) + "\n" + "\n".join(rows))
    return auto


def own_sections():
    return ("\n## Meus termos\n" + _row(["Termo", "Sigla"]) + "\n" + _row(["---"] * 2) + "\n\n"
            "## Traduções\n" + _row(["Português", "Inglês"]) + "\n" + _row(["---"] * 2) + "\n"
            + "\n".join(_row([pt, en]) for pt, en in TRANSLATIONS) + "\n")


def _tables(text):
    """{título da seção: [[célula, …], …]} das tabelas Markdown da nota."""
    out, section = {}, ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("|") and not re.match(r"^\|[\s|:-]+\|$", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.setdefault(section, []).append(cells)
    return {k: v[1:] for k, v in out.items()}  # sem o cabeçalho


def write(config, terms):
    """Recria a tabela automática preservando os riscados e as suas seções."""
    path = os.path.expanduser(config["lexicon_note"])
    struck = []
    if os.path.exists(path):
        rows = _tables(open(path, encoding="utf-8").read()).get("Termos", [])
        struck = [r[0].strip("~") for r in rows if r and r[0].startswith("~~")]
    new = not os.path.exists(path)
    style.write_note(path, note_text(terms, struck))
    if new:  # 1ª vez: cabeçalho e seções suas no lugar do cabeçalho do estilo
        text = open(path, encoding="utf-8").read()
        text = text.replace(style.NOTE_HEAD, NOTE_HEAD).replace(style.NOTE_TAIL, own_sections())
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return path


_cache = {"path": None, "mtime": 0, "lex": None}


def load(config):
    """{"terms": [(termo, sigla, usos seus)], "pt_en": {pt: en}} da nota (sem riscados); None se desligado."""
    path = os.path.expanduser(config.get("lexicon_note") or "")
    if not (config.get("lexicon_enabled", True) and path and os.path.exists(path)):
        return None
    mtime = os.path.getmtime(path)
    if _cache["path"] != path or _cache["mtime"] != mtime:
        tables = _tables(open(path, encoding="utf-8").read())
        terms = [(r[0], r[1] if len(r) > 1 else "", int(r[2]) if len(r) > 2 and r[2].isdigit() else 0)
                 for r in tables.get("Termos", []) if r and r[0] and not r[0].startswith("~~")]
        mine = [(r[0], r[1] if len(r) > 1 else "", 10**6) for r in tables.get("Meus termos", []) if r and r[0]]
        pt_en = {r[0]: r[1] for r in tables.get("Traduções", []) if len(r) > 1 and r[0] and r[1]}
        _cache.update(path=path, mtime=mtime, lex={"terms": mine + terms, "pt_en": pt_en})
    return _cache["lex"]


def whisper_terms(lex, base_prompt=""):
    """Os termos mais usados por você que cabem em WHISPER_CHARS e ainda não estão no vocabulário."""
    have, out, size = _fold(base_prompt), [], 0
    for term, sigla, n_mine in sorted(lex["terms"], key=lambda x: -x[2]):
        if not n_mine:
            break  # só dos livros não vai para o Whisper: é pista para a IA
        for w in filter(None, (term, sigla)):
            if not re.search(rf"\b{re.escape(_fold(w))}\b", have) and size + len(w) + 2 <= WHISPER_CHARS:
                out.append(w)
                size += len(w) + 2
                have += " " + _fold(w)
    return out


def hints(lex, text):
    """Termos do léxico parecidos (mas não iguais) com palavras do ditado: "demorage" → demurrage."""
    words = re.findall(r"[a-z][a-z0-9-]{3,}", _fold(text))
    grams = words + [f"{a} {b}" for a, b in zip(words, words[1:])]
    present = set(grams)
    by_first = collections.defaultdict(list)
    for term, _s, _n in lex["terms"]:
        by_first[_fold(term)[:1]].append((term, _fold(term)))
    out = []
    for g in grams:
        for term, key in by_first.get(g[:1], ()):  # ponytail: mesma 1ª letra; erro na 1ª letra escapa
            if key not in present and abs(len(key) - len(g)) <= 3 and term not in out \
                    and difflib.SequenceMatcher(None, g, key).ratio() >= 0.75:  # "danage" ~ dunnage: 0,77
                out.append(term)
        if len(out) >= HINTS_MAX:
            break
    return out


def translations(lex, text, target="en"):
    """[(origem, destino)] dos termos presentes no texto: PT→EN (modo Inglês) ou EN→PT (legendas em pt)."""
    pairs = lex["pt_en"].items() if target == "en" else [(en, pt) for pt, en in lex["pt_en"].items()]
    folded = _fold(text)
    found = []
    for src, dst in sorted(pairs, key=lambda p: -len(p[0])):  # "plano de estivagem" antes de "estivagem"
        pattern = r"\b" + r"\s+".join(re.escape(w) + r"(?:e?s)?" for w in _fold(src).split()) + r"\b"
        if re.search(pattern, folded) and all(_fold(src) not in _fold(f[0]) for f in found):
            found.append((src, dst))
    return found


def ai_guidance(config, text, mode):
    """Texto extra para a IA: pistas de termos e, no modo Inglês, as traduções. None se nada a dizer."""
    lex = load(config)
    if not lex:
        return None
    parts = []
    keep = [pt for pt, _en in translations(lex, text, "en")] + [
        t for t, _s, _n in lex["terms"] if re.search(rf"\b{re.escape(_fold(t))}\b", _fold(text))]
    if keep:  # o modelo local trocava "peação" (certo) por "instalação"
        parts.append("Termos técnicos corretos neste ditado (mantenha como estão): " + ", ".join(keep) + ".")
    found = hints(lex, text)
    if found:
        parts.append("Termos técnicos que podem ter sido mal transcritos neste ditado (use a grafia certa se for o "
                     "caso; não force): " + ", ".join(found) + ".")
    if mode and (mode.get("id") == "ingles" or "inglês" in mode.get("prompt", "").lower()):
        pairs = translations(lex, text, "en")
        if pairs:
            parts.append("Traduza estes termos assim: " + "; ".join(f"{a} → {b}" for a, b in pairs) + ".")
    return "\n".join(parts) or None
