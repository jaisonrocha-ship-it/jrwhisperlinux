"""Do texto transcrito ao texto colado: perfil → modo de IA → formatação → IA → atalhos → regras.

Atalhos de texto entram depois da formatação e da IA: a expansão sai exatamente como foi escrita.
"""
from dataclasses import dataclass, field

from . import ai, history, lexicon, style
from .config import _debug_log
from .profiles import effective_config, match_profile
from .textproc import apply_case_rules, apply_snippets, format_transcript


@dataclass
class Result:
    text: str
    mode: dict = None
    profile: dict = None
    ai_error: str = None
    config: dict = field(default_factory=dict)
    provider: str = None  # IA que respondeu (ollama | nvidia | deepseek)


def choose_mode(config, text, forced_mode=None, profile=None):
    """Prioridade: prefixo de voz > atalho (--mode) > perfil do app > modo padrão. Devolve (modo, texto)."""
    if not config.get("ai_enabled"):
        return None, text
    if config.get("ai_voice_prefix", True):
        mode, rest = ai.detect_voice_mode(config, text)
        if mode:
            return mode, rest
    for mode_id in (forced_mode, (profile or {}).get("ai_mode"), config.get("ai_default_mode")):
        if mode_id:
            mode = ai.find_mode(config, mode_id)
            if mode:
                return mode, text
    return None, text


def _style(config, mode):
    """E-mail: a nota de estilo + as 3 últimas vezes em que você corrigiu um e-mail da IA (do histórico)."""
    if not style.is_email_mode(mode):
        return None
    parts = [style.guide(config)]
    if config.get("history_enabled"):
        try:
            fixed = [r for r in history.load(limit=300) if r.get("ai_text") and r.get("mode") == mode["name"]][:3]
        except OSError:
            fixed = []
        if fixed:
            parts.append("Como o usuário corrigiu e-mails reescritos antes (siga o \"Depois\"):\n" + "\n".join(
                f"Antes: {r['ai_text'][:400]}\nDepois: {r['text'][:400]}" for r in fixed))
    return "\n\n".join(p for p in parts if p) or None


def process(config, raw, wm_class=None, forced_mode=None, on_status=None, context=None):
    """context: bloco de texto do campo em foco (context.Context.prompt()), só para a IA."""
    profile = match_profile(config, wm_class)
    cfg = effective_config(config, profile)
    if profile:
        _debug_log(f"Perfil: {profile.get('name')} ({wm_class})")
    mode, text = choose_mode(cfg, raw, forced_mode, profile)
    if cfg.get("enable_formatting", True):
        text = format_transcript(text, cfg)
    error = provider = None
    if mode and text.strip():
        if on_status:
            on_status(f"Reescrevendo · {mode['name']}…")
        try:
            text = ai.rewrite(cfg, text, mode, context=context or None, style=_style(cfg, mode),
                              terms=lexicon.ai_guidance(cfg, text, mode))
            provider = ai.last_provider
        except ai.AIError as e:
            error = str(e)
            _debug_log(f"IA falhou ({mode['id']}): {e}; colando o original")
    text = apply_snippets(text, cfg.get("snippets"))
    text = apply_case_rules(text, cfg)
    return Result(text=text, mode=mode, profile=profile, ai_error=error, config=cfg, provider=provider)
