"""Accès au LLM local (Ollama). Seul module qui parle au modèle.

Garde-fous anti-hallucination à ce niveau:
- température 0 + graine fixe: sorties reproductibles (un écart = un vrai changement, pas du bruit);
- consignes en message *système*, données en message *utilisateur* (le modèle distingue règles et contenu);
- contrôle du budget de contexte: Ollama tronque SILENCIEUSEMENT le début du prompt quand il dépasse
  num_ctx, ce qui fait disparaître les règles et une partie des faits. On mesure et on refuse plutôt que de tronquer;
- JSON validé par schéma, avec relance qui renvoie l'erreur au modèle (au lieu d'un {} silencieux).
"""
import json, logging, os, re
from typing import Callable

log = logging.getLogger("nova.llm")

MODEL = os.getenv("NOVA_MODEL", "llama3.1")
NUM_CTX = int(os.getenv("NOVA_NUM_CTX", "8192"))
NUM_PREDICT = int(os.getenv("NOVA_NUM_PREDICT", "1024"))
CHARS_PER_TOKEN = 3.0  # estimation prudente pour du français riche en chiffres et identifiants

_text = _json = None


def _clients():
    global _text, _json
    if _text is None:
        from langchain_ollama import ChatOllama
        opts = dict(model=MODEL, temperature=0, seed=42, num_ctx=NUM_CTX, num_predict=NUM_PREDICT)
        _text, _json = ChatOllama(**opts), ChatOllama(**opts, format="json")
    return _text, _json


class ContextOverflow(RuntimeError):
    pass


def prompt_budget_chars() -> int:
    """Nombre de caractères disponibles pour système + prompt (réserve faite de la réponse)."""
    return int((NUM_CTX - NUM_PREDICT - 200) * CHARS_PER_TOKEN)


def _messages(prompt: str, system: str):
    from langchain_core.messages import HumanMessage, SystemMessage
    if len(system) + len(prompt) > prompt_budget_chars():
        raise ContextOverflow(f"prompt de {len(system) + len(prompt)} car. > budget {prompt_budget_chars()} "
                              f"(augmenter NOVA_NUM_CTX ou réduire les preuves)")
    return ([SystemMessage(system)] if system else []) + [HumanMessage(prompt)]


def ask_text(prompt: str, system: str = "", tag: str = "") -> str:
    log.debug("ask_text[%s] %d car.", tag, len(prompt))
    return _clients()[0].invoke(_messages(prompt, system)).content.strip()


def _parse(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", raw, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def ask_json(prompt: str, system: str = "", tag: str = "", validate: Callable[[object], str | None] | None = None,
             default=None, retries: int = 2):
    """Appelle le modèle en mode JSON. `validate(obj)` renvoie None si l'objet est valide, sinon un message d'erreur
    qui est renvoyé au modèle pour correction. Après `retries` échecs, renvoie `default` (et journalise)."""
    p = prompt
    for essai in range(retries + 1):
        raw = _clients()[1].invoke(_messages(p, system)).content
        try:
            obj = _parse(raw)
            err = validate(obj) if validate else None
        except (json.JSONDecodeError, ValueError) as ex:
            obj, err = None, f"JSON invalide ({ex})"
        if err is None:
            return obj
        log.warning("ask_json[%s] essai %d rejeté: %s", tag, essai + 1, err)
        p = f"{prompt}\n\nTa réponse précédente était invalide: {err}\nRéponds de nouveau, en JSON valide respectant exactement le format demandé."
    return default
