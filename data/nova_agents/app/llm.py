"""Accès aux LLM. Seul module qui parle à un modèle.

Fournisseurs, dans l'ordre:
1. Gemini (API Google, clé GEMINI_API_KEY dans l'environnement ou data/nova_agents/.env, jamais dans git):
   NOVA_GEMINI_MODELS, essayés l'un après l'autre. Grand contexte: on peut lui envoyer beaucoup plus de preuves.
2. Ollama (local) en secours seulement: si aucune clé, si Gemini est saturé (503), hors quota (429), en erreur ou injoignable.
Un modèle Gemini en échec est mis en pause un moment (disjoncteur) pour ne pas ralentir les appels suivants.

Garde-fous anti-hallucination à ce niveau (communs aux deux fournisseurs):
- température 0 + graine fixe: sorties reproductibles;
- consignes en message *système*, données en message *utilisateur*;
- contrôle du budget de contexte du fournisseur réellement utilisé: Ollama tronque SILENCIEUSEMENT un prompt trop long,
  on mesure et on refuse (ContextOverflow) plutôt que de tronquer; l'appelant réduit alors les preuves;
- JSON validé par schéma, avec relance qui renvoie l'erreur au modèle (au lieu d'un {} silencieux).
"""
import json, logging, os, re, threading, time
from collections import Counter
from pathlib import Path
from typing import Callable

log = logging.getLogger("nova.llm")

MODEL = os.getenv("NOVA_MODEL", "llama3.1")
NUM_CTX = int(os.getenv("NOVA_NUM_CTX", "8192"))
NUM_PREDICT = int(os.getenv("NOVA_NUM_PREDICT", "1024"))
CHARS_PER_TOKEN = 3.0  # estimation prudente pour du français riche en chiffres et identifiants

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODELS = [m.strip() for m in os.getenv("NOVA_GEMINI_MODELS", "gemini-3.5-flash,gemini-flash-lite-latest").split(",") if m.strip()]
GEMINI_CTX_CHARS = int(os.getenv("NOVA_GEMINI_CTX_CHARS", "400000"))  # bien en deçà de la fenêtre: coût et latence restent raisonnables
GEMINI_TIMEOUT = float(os.getenv("NOVA_GEMINI_TIMEOUT", "90"))

_text = _json = None
_pause: dict[str, float] = {}           # modèle Gemini -> pause jusqu'à (timestamp)
_lock = threading.Lock()
USAGE: Counter = Counter()              # appels par fournisseur/modèle (affiché dans le chat)


class ContextOverflow(RuntimeError):
    pass


class GeminiIndisponible(RuntimeError):
    pass


def _env_key() -> str:
    """Clé lue dans l'environnement, sinon dans .env (fichier ignoré par git)."""
    k = os.getenv("GEMINI_API_KEY", "").strip()
    if not k and ENV_FILE.exists():
        m = re.search(r"(?m)^\s*GEMINI_API_KEY\s*=\s*['\"]?([^'\"\s]+)", ENV_FILE.read_text(encoding="utf-8"))
        k = m.group(1) if m else ""
    return k if os.getenv("NOVA_LLM", "auto") != "ollama" else ""


def gemini_actif() -> bool:
    return bool(_env_key()) and any(_pause.get(m, 0) < time.time() for m in GEMINI_MODELS)


def grand_contexte() -> bool:
    """Vrai si le prochain appel ira vraisemblablement à Gemini: on peut envoyer beaucoup plus de contexte."""
    return gemini_actif()


def prompt_budget_chars() -> int:
    """Caractères disponibles pour système + prompt chez le fournisseur qui répondra (réserve faite de la réponse)."""
    return GEMINI_CTX_CHARS if gemini_actif() else int((NUM_CTX - NUM_PREDICT - 200) * CHARS_PER_TOKEN)


# ---------------------------------------------------------------- Gemini
def _gemini(prompt: str, system: str, json_mode: bool, tag: str) -> str:
    import httpx
    key = _env_key()
    if not key:
        raise GeminiIndisponible("aucune clé GEMINI_API_KEY")
    if len(system) + len(prompt) > GEMINI_CTX_CHARS:
        raise ContextOverflow(f"prompt de {len(system) + len(prompt)} car. > budget Gemini {GEMINI_CTX_CHARS}")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "seed": 42, **({"responseMimeType": "application/json"} if json_mode else {})}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    erreurs = []
    for model in GEMINI_MODELS:
        if _pause.get(model, 0) > time.time():
            continue
        for essai in range(2):
            t = time.time()
            try:
                r = httpx.post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": key}, json=body, timeout=GEMINI_TIMEOUT)
            except httpx.HTTPError as ex:
                erreurs.append(f"{model}: {type(ex).__name__}")
                _pause[model] = time.time() + 30
                break
            if r.status_code == 200:
                d = r.json()
                parts = (d.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                texte = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                if texte.strip():
                    with _lock:
                        USAGE[f"gemini:{model}"] += 1
                    log.debug("gemini[%s] %s %.1fs", tag, model, time.time() - t)
                    return texte
                erreurs.append(f"{model}: réponse vide ({(d.get('candidates') or [{}])[0].get('finishReason', '?')})")
                break
            msg = r.text[:160]
            erreurs.append(f"{model}: HTTP {r.status_code}")
            if r.status_code in (401, 403) or (r.status_code == 400 and "API_KEY" in r.text):  # clé refusée: inutile d'insister
                for m in GEMINI_MODELS:
                    _pause[m] = time.time() + 3600
                raise GeminiIndisponible(f"clé refusée ({r.status_code}): {msg}")
            if r.status_code == 429 and essai == 0:
                m = re.search(r'"retryDelay":\s*"(\d+)', r.text)
                attente = int(m.group(1)) if m else 0
                if 0 < attente <= 8:  # quota par minute: une courte attente vaut mieux qu'un repli
                    time.sleep(attente)
                    continue
            _pause[model] = time.time() + (120 if r.status_code == 429 else 30)  # 429 quota, 5xx saturation, 404 modèle retiré...
            break
    raise GeminiIndisponible("; ".join(erreurs) or "tous les modèles Gemini sont en pause")


# ---------------------------------------------------------------- Ollama (secours)
def _clients():
    global _text, _json
    if _text is None:
        from langchain_ollama import ChatOllama
        opts = dict(model=MODEL, temperature=0, seed=42, num_ctx=NUM_CTX, num_predict=NUM_PREDICT)
        _text, _json = ChatOllama(**opts), ChatOllama(**opts, format="json")
    return _text, _json


def _ollama(prompt: str, system: str, json_mode: bool) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    budget = int((NUM_CTX - NUM_PREDICT - 200) * CHARS_PER_TOKEN)
    if len(system) + len(prompt) > budget:
        raise ContextOverflow(f"prompt de {len(system) + len(prompt)} car. > budget Ollama {budget} "
                              f"(augmenter NOVA_NUM_CTX ou réduire les preuves)")
    out = _clients()[1 if json_mode else 0].invoke(([SystemMessage(system)] if system else []) + [HumanMessage(prompt)]).content
    with _lock:
        USAGE[f"ollama:{MODEL}"] += 1
    return out


def _complete(prompt: str, system: str, json_mode: bool, tag: str) -> str:
    """Gemini d'abord; Ollama seulement si Gemini est indisponible. Un prompt trop grand pour Ollama remonte
    en ContextOverflow: l'appelant réduit ses preuves et rappelle (Gemini est alors en pause, donc Ollama)."""
    if _env_key():
        try:
            return _gemini(prompt, system, json_mode, tag)
        except GeminiIndisponible as ex:
            log.warning("llm[%s]: Gemini indisponible (%s), repli sur Ollama", tag, ex)
    return _ollama(prompt, system, json_mode)


# ---------------------------------------------------------------- API utilisée par le reste de l'application
def ask_text(prompt: str, system: str = "", tag: str = "") -> str:
    log.debug("ask_text[%s] %d car.", tag, len(prompt))
    return _complete(prompt, system, False, tag).strip()


def fournisseurs_depuis(avant: Counter) -> dict:
    """Appels faits depuis l'instantané `avant` (ex.: {'gemini:gemini-3.5-flash': 6, 'ollama:llama3.1': 1})."""
    return {k: v - avant.get(k, 0) for k, v in USAGE.items() if v - avant.get(k, 0) > 0}


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
        raw = _complete(p, system, True, tag)
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
