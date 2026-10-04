"""Construit data/claims.json à partir des fichiers de data/starter/Projet360_NOVA_ETUDIANTS.

Chaque passage reprend le texte du fichier, avec son repère (ligne, page, cellule).
Les statuts de tickets et le registre financier sont lus dans les fichiers, pas saisis à part.
Les réponses aux questions du README ne sont pas injectées.
"""
import re
from . import corpus, kb

REF = corpus.baseline_au()[:10]
CUTOFF = corpus.go_live_cutoff()
claims: list[dict] = []


def add(**c):
    c.setdefault("statut", "baseline")
    c.setdefault("perime", "")
    c["sujets"] = c.get("sujets") or kb.detect_sujets(c["texte"] + " " + c.get("fichier", ""))
    claims.append(c)


def _approval(text: str) -> bool:
    """Vrai si le passage énonce une approbation, pas s'il dit qu'elle manque ou qu'elle est refusée."""
    for sent in re.split(r"[.\n]", text):
        if not re.search(r"approuv|acceptée|APPROUVÉE|date officielle", sent, re.I):
            continue
        if re.search(r"\b(pas|non|aucun|aucune|sans)\b|n['’]|ne\s", sent, re.I):
            continue
        return True
    return bool(re.search(r"reportées à la phase", text, re.I))


def classify(doc: dict, text: str) -> tuple[str, str]:
    if doc.get("brouillon") or re.search(r"il s'agit d'une proposition|notre recommandation est de", text, re.I):
        return "proposition", "corpus"
    if doc["autorite"] <= 2 and (_approval(text) or re.search(r"déplac\w+.{0,80}22 octobre", text, re.I)):
        return "décision", "decision"
    if doc["autorite"] == 1 and re.search(r"APPROUVÉE|Acceptée|reportées à la phase", text):
        return "décision", "decision"
    return "fait", "corpus"


def passage_perime(doc: dict, text: str) -> str:
    reasons = [doc["perime"]] if doc.get("perime") else []
    if CUTOFF and doc["date"] not in ("", "inconnue") and doc["date"] < CUTOFF and re.search(r"15 octobre", text, re.I):
        reasons.append(f"cite le 15 octobre comme cible, avant l'approbation du 22 octobre ({CUTOFF})")
    if "Plan_Projet" in doc["name"] and re.search(r"mise en production", text, re.I) and re.search(r"2026-10-15|15 octobre", text, re.I):
        reasons.append("le plan indique encore le 15 octobre 2026 pour la mise en production")
    return "; ".join(dict.fromkeys(reasons))


for doc in corpus.documents():
    if doc["pertinence"] in kb.EXCLUS or doc.get("doublon_de"):
        continue
    for p in doc["passages"]:
        typ, origine = classify(doc, p["texte"])
        add(date=p["date"], type=typ, origine=origine, source=doc["id"], fichier=doc["fichier"],
            autorite=doc["autorite"], perime=passage_perime(doc, p["texte"]), repere=p["repere"],
            texte=f"[{doc['fichier']} | {p['repere']}] {p['texte']}")
    if doc["ticket_id"]:
        raw, statut = corpus.ticket_statut(doc["text"])
        add(date=REF, type="fait", origine="ticket", source=doc["id"], fichier=doc["fichier"],
            autorite=doc["autorite"], ticket=doc["ticket_id"], statut_ticket=statut,
            texte=f"Statut du ticket {doc['ticket_id']} au {REF}: {statut} (fichier {doc['fichier']}, « Statut : {raw} »).")

kb.CLAIMS.write_text("[]", encoding="utf-8")
kb.append_claims(claims)
print(len(claims), "claims écrits dans", kb.CLAIMS, "depuis", corpus.ROOT)
