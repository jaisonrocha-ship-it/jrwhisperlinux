import re

# Frases que o Whisper "ouve" em ruído/silêncio (legendas de vídeo do treino). Só valem como texto inteiro.
HALLUCINATIONS = re.compile(
    r"(notifica[çc][õo]es de novos v[íi]deos|inscreva-se|ative o sininho|obrigad[oa] por assistir"
    r"|legendas? (pela|por|da) comunidade|amara\.org|at[ée] o pr[óo]ximo v[íi]deo)", re.IGNORECASE)


def is_hallucination(text):
    """Texto curto que é só uma frase-fantasma conhecida (ditado de verdade passa)."""
    return bool(text) and len(text.split()) <= 15 and bool(HALLUCINATIONS.search(text))


def format_transcript(text: str, config) -> str:
    if not text:
        return ""

    if config.get("voice_commands", True):
        # O Whisper costuma pontuar o próprio comando ("Olá vírgula, tudo", "Nova linha."):
        # pontuação falada engole a pontuação vizinha; quebras de linha só a seguinte.
        for cmd, out in (("novo parágrafo", "\n\n"), ("nova linha", "\n")):
            text = re.sub(rf"[ \t]*\b{cmd}\b[.,;:!?]?[ \t]*", out, text, flags=re.IGNORECASE)
        for cmd, out in (("ponto de interrogação", "?"), ("ponto de exclamação", "!"), ("ponto e vírgula", ";"),
                         ("dois pontos", ":"), ("ponto final", "."), ("vírgula", ",")):
            text = re.sub(rf"[ \t]*[.,;:!?]?[ \t]*\b{cmd}\b[.,;:!?]?", out, text, flags=re.IGNORECASE)

    if config.get("remove_fillers", True):
        text = re.sub(r"\b(humm|hmm|er|ahn|éh|eh|uh)\b", "", text, flags=re.IGNORECASE)

    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'[ \t]+([.,!?;:])', r'\1', text)
    # Sobras de comando/hesitação: ",," "..", "!!" (reticências ficam)
    text = re.sub(r'([,;:])[,;:.]+', r'\1', text)
    text = re.sub(r'(?<!\.)\.\.(?!\.)', '.', text)
    text = re.sub(r'([!?])\1+|([!?])\.', lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r'\n ', '\n', text)
    text = re.sub(r' \n', '\n', text)

    word_overrides = config.get("word_overrides", {})
    if word_overrides:
        for wrong, right in word_overrides.items():
            pattern = rf"\b{re.escape(wrong)}\b"
            text = re.sub(pattern, right, text, flags=re.IGNORECASE)

    text = text.strip()
    if text:
        def _capitalize_after_sentence(match):
            punc = match.group(1)
            space = match.group(2)
            char = match.group(3)
            return punc + space + char.upper()

        text = re.sub(r'([.!?])(\s+)([a-zà-ú])', _capitalize_after_sentence, text)

        lines = text.split('\n')
        capitalized_lines = []
        for line in lines:
            if not line.strip():
                capitalized_lines.append("")
                continue
            l_strip = line.strip()
            l_cap = l_strip[0].upper() + l_strip[1:]
            capitalized_lines.append(l_cap)
        text = '\n'.join(capitalized_lines)

        if text and text[-1] not in ".!?;:\n":
            text += "."

    for _ in range(3):
        match = re.search(r'([^.!?]+[.!?]\s*)\1{2,}\s*$', text, flags=re.IGNORECASE)
        if match:
            repeated = match.group(1).strip()

            if repeated.lower().rstrip('.!? ') in ["o que significa isso", "obrigado por assistir", "muito obrigado", "legenda por"]:
                text = text[:match.start()].strip()
            else:
                text = text[:match.start()].strip() + " " + match.group(1).strip()

    return text.strip()


def apply_snippets(text, snippets):
    """Troca gatilhos falados pela expansão ("minha assinatura" → bloco de texto).

    Gatilhos mais longos primeiro, para "meu e-mail pessoal" vencer "meu e-mail".
    A pontuação que o Whisper põe logo após o gatilho é absorvida.
    """
    for trigger in sorted(snippets or {}, key=len, reverse=True):
        pattern = rf"(?<!\w){re.escape(trigger)}(?!\w)[.,;:!?]?"
        text = re.sub(pattern, lambda _m, exp=snippets[trigger]: exp, text, flags=re.IGNORECASE)
    return text


def apply_case_rules(text, config):
    """Regras do perfil que valem mesmo sem formatação (ex.: terminal: minúscula, sem ponto final)."""
    if not text:
        return text
    if not config.get("capitalize", True) and not (len(text) > 1 and text[1].isupper()):
        text = text[0].lower() + text[1:]  # preserva siglas ("API key")
    if not config.get("final_period", True):
        text = re.sub(r"(?<!\.)\.\s*$", "", text)
    return text
