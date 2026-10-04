"""Sélection des preuves pour une question (BM25 lexical, sans dépendance).

Anti-hallucination: donner TOUT le domaine à un modèle 8B noie les faits pertinents (et, la base grandissant
avec l'ingestion, finit par dépasser le contexte -> troncature silencieuse). On envoie plutôt:
- les claims qui partagent un identifiant avec la question (SEC-210, INV-003...) -> toujours inclus;
- le statut des tickets et les décisions du domaine -> toujours inclus (l'« état courant»);
- puis les claims les mieux classés par BM25, dans un budget de caractères.
"""
import math, re, unicodedata
from collections import Counter
from . import kb

STOP = set("""le la les un une des du de d l et ou a au aux en dans sur pour par avec sans que qui quoi quel quelle quels quelles
est sont ete etre a ont il elle ils elles on ce cet cette ces se sa son ses leur leurs nous vous je tu ne pas plus y
comment pourquoi quand combien projet nova""".split())
SYN = {"approb": "approu", "valida": "valide", "accep": "accept", "respon": "respon", "heber": "heber", "rollb": "retour"}


def _norm(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(ch) != "Mn")


def terms(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+(?:-[0-9]+)?", _norm(text)):
        if w in STOP or len(w) < 2:
            continue
        w = w if "-" in w or w.isdigit() else w[:6]  # racinisation grossière par préfixe (français)
        out.append(SYN.get(w[:5], w))
    return out


def bm25(query: str, docs: list[str], k1=1.4, b=0.75) -> list[float]:
    toks = [terms(d) for d in docs]
    N, avg = len(docs), (sum(map(len, toks)) / max(1, len(docs)))
    df = Counter(t for ts in toks for t in set(ts))
    q = set(terms(query))
    scores = []
    for ts in toks:
        tf, dl = Counter(ts), len(ts)
        scores.append(sum(math.log(1 + (N - df[t] + .5) / (df[t] + .5)) * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / avg))
                          for t in q if t in tf))
    return scores


def select_evidence(question: str, sujet: str | None, budget_chars: int = 9000, k_min: int = 8, extra: list[dict] | None = None) -> list[dict]:
    claims = kb.load_claims() + (extra or [])
    if sujet:
        domaine = {sujet, *kb.VOISINS.get(sujet, [])}
        pool = [c for c in claims if set(c["sujets"]) & domaine]
    else:
        pool = claims
    if not pool:
        return []
    q_ids = kb.tokens(question)
    scores = bm25(question, [c["texte"] + " " + c.get("fichier", "") for c in pool])
    must, ranked = [], []
    for c, s in zip(pool, scores):
        own = sujet is None or sujet in c["sujets"]
        if (kb.tokens(c["texte"]) & q_ids) or (own and c.get("origine") in ("ticket", "decision")):
            must.append(c)
        else:
            ranked.append((s * (1.5 if own else 1.0), c))
    ranked.sort(key=lambda x: -x[0])
    chosen, size = [], 0
    for c in must + [c for s, c in ranked if s > 0] + [c for s, c in ranked if s <= 0][: max(0, k_min - len(must))]:
        line = len(c["texte"]) + 120
        if (size + line > budget_chars and len(chosen) >= k_min) or size + line > budget_chars * 1.25:
            break  # plafond dur: jamais de dépassement du contexte (Ollama tronquerait les règles en silence)
        chosen.append(c)
        size += line
    return sorted(chosen, key=lambda c: (c["date"], c["id"]))
