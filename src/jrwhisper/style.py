"""Seu estilo de escrita, estudado dos e-mails enviados que estão no Obsidian (item 14).

As fontes são pastas do vault (style_sources). Exports de e-mail têm uma conversa por nota:
"### data · remetente · assunto", "De: … · Para: …", "Pasta: …" e o corpo; só conta o que está em pasta de
enviados. O corpo é limpo (histórico citado, encaminhamento, assinatura) e a IA local estuda em lotes;
o resumo vira a nota "Meu estilo de escrita.md". A nota é a fonte de verdade: você edita, o app relê
a cada e-mail ditado. "Reestudar" só refaz o bloco entre os marcadores AUTO.
"""
import glob
import json
import os
import re
import subprocess
import time

from . import ai
from .config import _debug_log

AUTO_START, AUTO_END = "<!-- jrwhisper:auto -->", "<!-- /jrwhisper:auto -->"
PER_SOURCE = 60      # e-mails mais recentes por fonte
WORDS_MAX = 220      # palavras por e-mail no lote (o começo é onde está o seu jeito: saudação, abertura)
BATCH = 8            # e-mails por chamada da IA local (~3 mil tokens)
HOT_C, COOL_C = 83, 75  # estudo longo: acima de 83 °C a GPU descansa até 75 °C (máx. 90 s) antes do próximo lote
STYLE_MAX = 2500     # caracteres da nota que vão para a IA a cada e-mail ditado
CUT = re.compile(r"^\s*(>|Em .{5,120}escreveu:|On .{5,120}wrote:|El .{5,120}escribió:|De:\s|From:\s|Enviado:\s|"
                 r"Sent:\s|-{3,}\s*(Original|Mensagem original|Forwarded)|_{10,}|Enviado do meu|Sent from my)",
                 re.I | re.M)
CLOSING = re.compile(r"^\s*(atenciosamente|att\.?|abs\.?|abraços?|obrigad[oa]|grato|cordialmente|saudações|"
                     r"best regards|regards|kind regards|thanks|saludos|un saludo)\b[^\n]{0,25}$", re.I | re.M)
# só linha curta: "Obrigado pelo retorno, segue a proposta…" no começo do e-mail não é despedida


def sent_messages(folder, only_sent=True, subdirs=True):
    """[(data, corpo limpo)] das notas da pasta, mais recentes primeiro."""
    pattern = os.path.join(os.path.expanduser(folder), "**" if subdirs else "", "*.md")
    out = []
    for path in glob.glob(pattern, recursive=subdirs):
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        if not only_sent:  # nota inteira (textos seus): sem o frontmatter
            body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip()
            if len(body.split()) >= 5:
                out.append((time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path))), body))
            continue
        for msg in re.split(r"^### ", text, flags=re.M)[1:]:
            folder_line = re.search(r"^Pasta: (.*)$", msg, re.M)
            if not folder_line or "enviad" not in folder_line.group(1).lower():
                continue
            body = clean(msg[folder_line.end():])
            if len(body.split()) >= 5:
                out.append((msg[:10], body))
    seen, unique = set(), []
    for date, body in sorted(out, reverse=True):
        if body not in seen:
            seen.add(body)
            unique.append((date, body))
    return unique


def clean(body):
    """Só o que você escreveu: corta histórico citado/encaminhado e a assinatura (fica a despedida).

    O export põe o corpo inteiro como citação ("> " em toda linha): essa camada sai antes; o histórico
    da conversa vem dentro dela como texto ("Em … escreveu:", "De: …"). "(sem texto)" e afins são vazios."""
    if all(line.startswith(">") for line in body.strip("\n").splitlines()):
        body = re.sub(r"^> ?", "", body.strip("\n"), flags=re.M)
    if re.fullmatch(r"\s*\([^)]{0,60}\)\s*", body):
        return ""
    m = CUT.search(body)
    if m:
        body = body[:m.start()]
    m = CLOSING.search(body)
    if m:
        body = body[:m.end()]
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def preview(sources):
    """[(fonte, nº de e-mails, nº de palavras)] para conferir pasta e filtro antes de estudar."""
    rows = []
    for src in sources:
        if src.get("enabled", True):
            msgs = sent_messages(src["path"], src.get("filter", "sent") == "sent", src.get("subdirs", True))
            rows.append((src, len(msgs), sum(len(b.split()) for _d, b in msgs)))
    return rows


BATCH_PROMPT = ("Abaixo há e-mails escritos e enviados pela mesma pessoa, separados por ===. Descreva COMO ela "
                "escreve, com exemplos curtos tirados dos textos: saudação e abertura, despedida, tamanho das frases "
                "e parágrafos, grau de formalidade, como pede e como confirma coisas, expressões e termos recorrentes, "
                "pontuação, uso de listas, idiomas usados. Não resuma o conteúdo nem cite nomes de clientes, valores "
                "ou dados. Responda em português, em tópicos curtos.")
REDUCE_PROMPT = ("Abaixo há anotações sobre o estilo de e-mail de uma pessoa, feitas em lotes. Junte tudo num guia "
                 "para escrever e-mails como ela. Responda só com JSON neste formato: {\"regras\": [8 a 12 regras "
                 "práticas e concretas, das mais marcantes para as menos, cada uma uma frase curta falando com a "
                 "pessoa, ex.: \"Abra com Bom dia ou Boa tarde e o primeiro nome.\"], \"expressoes\": [8 a 15 "
                 "expressões típicas dela, literais e genéricas, de 1 a 8 palavras]}. Em português. Nunca inclua "
                 "nomes de pessoas, empresas, terminais, lugares, valores, quantidades ou datas.")


def study(config, sources, on_progress=print):
    """Estuda as fontes com a IA local e devolve o bloco de estilo (Markdown). Levanta ai.AIError."""
    msgs = []
    for src in sources:
        if src.get("enabled", True):
            msgs += sent_messages(src["path"], src.get("filter", "sent") == "sent", src.get("subdirs", True))[:PER_SOURCE]
    if not msgs:
        raise ai.AIError("nenhum texto encontrado nas fontes")
    local = dict(config, ai_provider="ollama")
    notes = []
    batches = [msgs[i:i + BATCH] for i in range(0, len(msgs), BATCH)]
    for n, batch in enumerate(batches, 1):
        _cool_down(on_progress)
        on_progress(f"Lendo seus e-mails · lote {n} de {len(batches)}")
        text = "\n===\n".join(" ".join(body.split()[:WORDS_MAX]) for _d, body in batch)
        t0 = time.perf_counter()
        try:  # num_predict: sem teto, o modelo às vezes entra em repetição e não termina
            notes.append(ai.complete(local, BATCH_PROMPT, text, timeout=120, system="Você analisa estilo de escrita.",
                                     options={"num_ctx": 8192, "num_predict": 500}))
            _debug_log(f"Estilo: lote {n}/{len(batches)} em {time.perf_counter() - t0:.1f} s")
        except ai.AIError as e:  # um lote ruim não derruba o estudo
            _debug_log(f"Estilo: lote {n}/{len(batches)} pulado ({e})")
    if len(notes) < len(batches) / 2:
        raise ai.AIError(f"só {len(notes)} de {len(batches)} lotes deram certo")
    _cool_down(on_progress)
    on_progress("Escrevendo o resumo do seu estilo")
    raw = ai.complete(local, REDUCE_PROMPT, "\n\n---\n\n".join(notes), timeout=240,
                      system="Você escreve guias de estilo objetivos.", options={"num_ctx": 8192, "num_predict": 1200},
                      fmt="json")
    guide = render(raw)
    srcs = ", ".join(os.path.basename(s["path"].rstrip("/")) for s in sources if s.get("enabled", True))
    head = (f"*Estudado em {time.strftime('%d/%m/%Y')} · {len(msgs)} textos enviados ({srcs}) · "
            f"{config.get('ai_ollama_model', 'qwen2.5')} local*")
    return f"## E-mail\n{head}\n\n{guide.strip()}\n"


def _scrub(text):
    """Tira o que identifica clientes: nome no meio de citação vira [nome]; trecho com número sai."""
    def quote(m):
        words = m.group(1).split()
        if any(c.isdigit() for c in m.group(1)) or len(words) > 12:
            return "“…”"
        return "“" + " ".join(w if i == 0 or not re.match(r"[A-ZÀ-Ý][a-zà-ÿ]", w) else
                              "[nome]" + w[len(w.rstrip(".,;:!?")):] for i, w in enumerate(words)) + "”"
    return re.sub(r"[\"“”]([^\"“”]{1,200})[\"“”]", quote, text)


def _generic(expr):
    """Expressão sem número e sem nome próprio no meio (siglas curtas como BL passam)."""
    words = expr.split()
    return (expr and not any(c.isdigit() for c in expr)
            and not any(re.match(r"[A-ZÀ-Ý][a-zà-ÿ]", w) for w in words[1:]))


def render(raw):
    """JSON da IA → Markdown da nota, já sem dados de clientes."""
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise ai.AIError(f"resumo do estilo veio fora do formato ({e})") from e
    rules = [_scrub(str(r).strip()) for r in data.get("regras", []) if str(r).strip()][:12]
    exprs = list(dict.fromkeys(str(e).strip().strip("\"“”") for e in data.get("expressoes", [])))
    exprs = [e for e in exprs if _generic(e)][:15]
    if not rules:
        raise ai.AIError("resumo do estilo sem regras")
    out = "### Regras\n" + "\n".join(f"- {r}" for r in rules)
    if exprs:
        out += "\n\n### Expressões que você usa\n" + "\n".join(f"- “{e}”" for e in exprs)
    return out


def _gpu_temp():
    try:
        return int(subprocess.check_output(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                                           timeout=2).split()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 0


def _cool_down(on_progress):
    temp = _gpu_temp()
    if temp < HOT_C:
        return
    on_progress(f"Placa de vídeo a {temp} °C · esfriando")
    _debug_log(f"Estilo: GPU a {temp} °C, pausa")
    end = time.time() + 90
    while time.time() < end and _gpu_temp() > COOL_C:
        time.sleep(3)


NOTE_HEAD = ("---\ntags: [estilo, jrwhisper]\n---\n# Meu estilo de escrita\n\n"
             "O JRWhisper relê esta nota a cada e-mail ditado: edite à vontade. \"Reestudar meu estilo\" "
             "(Ajustes → Inteligência) só refaz o bloco automático; o resto é seu.\n\n")
NOTE_TAIL = "\n## Minhas regras\n- (escreva aqui o que deve valer sempre, mesmo que os e-mails digam outra coisa)\n"


def write_note(path, block):
    """Grava o bloco automático na nota; preserva tudo fora dos marcadores."""
    path = os.path.expanduser(path)
    auto = f"{AUTO_START}\n{block.strip()}\n{AUTO_END}"
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        if AUTO_START in text and AUTO_END in text:
            text = re.sub(re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END), lambda _m: auto, text, flags=re.S)
        else:
            text = f"{text.rstrip()}\n\n{auto}\n"
    else:
        text = NOTE_HEAD + auto + "\n" + NOTE_TAIL
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


_cache = {"path": None, "mtime": 0, "text": ""}


def guide(config):
    """Texto da nota para a IA (sem frontmatter, marcadores e a explicação do topo). Relido se a nota mudar."""
    path = os.path.expanduser(config.get("style_note") or "")
    if not (config.get("style_enabled", True) and path and os.path.exists(path)):
        return ""
    mtime = os.path.getmtime(path)
    if _cache["path"] != path or _cache["mtime"] != mtime:
        text = open(path, encoding="utf-8").read()
        text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        text = "\n".join(line for line in text.splitlines()
                         if not line.startswith("O JRWhisper relê") and "(escreva aqui" not in line)
        _cache.update(path=path, mtime=mtime, text=re.sub(r"\n{3,}", "\n\n", text).strip()[:STYLE_MAX])
    return _cache["text"]


def is_email_mode(mode):
    return bool(mode) and (mode.get("id", "").startswith("email") or "e-mail" in mode.get("name", "").lower())
