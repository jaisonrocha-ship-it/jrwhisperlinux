"""Correções do overlay viram regra do dicionário ("Paulo" → "Pablo") e termo do vocabulário.

Filtro: só grafia de uma palavra (não troca de palavra inteira). Nome próprio, sigla ou palavra rara
aprende na 1ª correção; palavra comum ("mais" → "mas") só na 2ª igual, porque a regra vale para
todo ditado futuro.
"""
import difflib
import re

from .config import load_config, save_config

# Palavras frequentes do português: errar uma regra aqui estraga muitos textos.
COMMON = set("""
a o as os um uma uns umas de da do das dos em na no nas nos por pra para pelo pela com sem sob sobre
e ou mas mais menos que se não sim já só até também muito muita muitos muitas pouco bem mal
eu tu ele ela nós vós eles elas você vocês me te lhe nos vos lhes meu minha seu sua nosso nossa
isso isto aquilo esse essa este esta aquele aquela aqui ali lá agora hoje ontem amanhã depois antes
ser é era foi são estar está estão estava ter tem têm tinha ir vai vou fazer faz fez ver vi dar dá
quando como onde porque porquê qual quais quem quanto cada todo toda todos todas outro outra mesmo
há vez vezes ano anos dia dias coisa tudo nada nunca sempre ainda então aí mesma assim
""".split())
VOCAB_LIMIT = 60  # termos no vocabulário (initial_prompt): demais vira alucinação


def _word(s):
    """Palavra sem a pontuação colada ("Pablo," → "Pablo"); None se não for uma palavra só."""
    s = s.strip().strip(".,;:!?\"'“”()")
    return s if s and " " not in s else None


def candidate(old, new):
    """Correção de grafia de uma palavra? Devolve (velho, novo) limpos ou None."""
    old, new = _word(old), _word(new)
    if not old or not new or old.lower() == new.lower():  # só maiúscula: formatação resolve
        return None
    if difflib.SequenceMatcher(None, old.lower(), new.lower()).ratio() < 0.5:
        return None  # troca de palavra, não grafia
    return old, new


def needs_confirmation(old, new):
    """Palavra comum em minúscula só vira regra na 2ª correção igual."""
    return new == new.lower() and not any(c.isdigit() for c in new) and old.lower() in COMMON


def _add_vocab(prompt, term):
    terms = [t.strip() for t in re.split(r"[,:]", prompt)]
    if any(t.lower() == term.lower() for t in terms) or len(terms) >= VOCAB_LIMIT:
        return prompt
    return f"{prompt.rstrip(' ,.')}, {term}" if prompt.strip() else f"Termos: {term}"


def apply(config, pairs):
    """Grava as correções no config (dict, alterado no lugar). Devolve (aprendidas, pendentes)."""
    overrides = dict(config.get("word_overrides") or {})
    counts = dict(config.get("learn_counts") or {})
    learned, pending = [], []
    for old, new in pairs:
        key = f"{old.lower()}→{new}"
        counts[key] = counts.get(key, 0) + 1
        if needs_confirmation(old, new) and counts[key] < 2:
            pending.append(new)
            continue
        overrides[old.lower()] = new
        counts.pop(key, None)
        if not new.islower():  # nome próprio/sigla ajuda o Whisper a acertar de primeira
            config["initial_prompt"] = _add_vocab(config.get("initial_prompt", ""), new)
        learned.append(new)
    config["word_overrides"], config["learn_counts"] = overrides, counts
    return learned, pending


def learn(pairs):
    """Relê o config do disco (os Ajustes podem ter mudado algo) e salva com as correções."""
    if not pairs:
        return [], []
    config = load_config()
    result = apply(config, pairs)
    save_config(config)
    return result
