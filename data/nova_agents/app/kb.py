"""Base de connaissances: claims en ajout seulement, règles d'autorité, état courant et calculs financiers en code.

Chaque claim porte un identifiant stable (C001...) que les agents doivent citer: on peut ainsi vérifier en code
que la phrase produite est bien appuyée par le TEXTE du claim cité (et pas seulement que la source existe).
Champs d'un claim: id, date, type, texte, sujets, source, fichier, autorite, statut, origine, perime, citation (ingestion).
"""
import json, re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from . import corpus

DATA = Path(__file__).resolve().parent.parent / "data"
CLAIMS = DATA / "claims.json"

SUJETS = {
    "gouvernance": "gouvernance, échéancier, décisions de comité, responsables, portée, changements (phase 1 / phase 2)",
    "finance": "budget, contrat, demandes de changement (CR), factures, paiements",
    "technique": "architecture, hébergement des données, intégration, migration de données, performance",
    "qualite": "sécurité, accessibilité, exploitation (runbook), conditions de go-live",
}
# Un expert voit aussi les faits des domaines voisins (les faits clés traversent les sujets)
VOISINS = {"gouvernance": ["qualite", "finance"], "finance": ["gouvernance"], "technique": ["gouvernance"], "qualite": ["gouvernance"]}
MOTS = {
    "finance": ["inv-", "facture", "budget", "contrat", "cr-0", "$", "paiement", "montant", "payé", "autorisé"],
    "technique": ["int-101", "data-401", "perf-501", "canada central", "east us", "migration", "architecture", "adr-", "connecteur",
                  "hébergement", "héberg"],
    "qualite": ["sec-210", "acc-", "ops-", "runbook", "rollback", "sécurité", "accessibilité", "go-live", "audit", "retour arrière"],
    "gouvernance": ["comité", "approuv", "date", "22 oct", "15 oct", "portée", "phase", "responsable", "transition", "décision",
                    "chargé de projet", "charge du projet"],
}
# Règle d'autorité codée (pas laissée au LLM)
AUTORITE = {1: "décision formelle / contrat", 2: "ticket / compte rendu / transcript", 3: "courriel",
            4: "plan / rapport / registre (peut être périmé)", 5: "chat", 6: "brouillon / non fiable", None: "inconnue (à confirmer)"}
ORIGINE_LABEL = {"etat_actuel": "état actuel tranché (date du fait + autorité)", "contradiction": "analyse consolidée (baseline)", "action": "registre d'actions (baseline)",
                 "ticket": "statut de ticket (baseline)"}
EXCLUS = {"HORS SUJET", "NON FIABLE", "ANCIEN", "CONSIGNES"}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


@lru_cache(maxsize=1)
def baseline() -> dict:
    """Métadonnées lues dans le dossier Projet360 (date de référence et catalogue de fichiers)."""
    return {"baseline_au": corpus.baseline_au(), "sources": corpus.sources()}


def ref_date() -> str:
    """Date de référence lisible (au lieu d'une date codée en dur dans les prompts)."""
    d = datetime.fromisoformat(baseline()["baseline_au"])
    return f"{d.day} {MOIS[d.month - 1]} {d.year}, {d.hour:02d} h"


def sources() -> dict[str, dict]:
    return {s["id"]: s for s in baseline()["sources"]}


def excluded_sources() -> dict[str, str]:
    """Sources hors sujet / non fiables / anciennes: ne doivent jamais appuyer une réponse."""
    return {s["id"]: s["pertinence"] for s in baseline()["sources"] if s["pertinence"] in EXCLUS}


def canonical_source(sid: str) -> str:
    """Un doublon (même message, autre fichier) n'est pas une confirmation indépendante."""
    s = sources().get(sid)
    if s and s.get("doublon_de"):
        return s["doublon_de"]
    return sid


def detect_sujets(text: str) -> list[str]:
    t = text.lower()
    found = [s for s, ws in MOTS.items() if any(w in t for w in ws)]
    return found or ["gouvernance"]


def load_claims() -> list[dict]:
    return json.loads(CLAIMS.read_text(encoding="utf-8")) if CLAIMS.exists() else []


def claims_by_id() -> dict[str, dict]:
    return {c["id"]: c for c in load_claims()}


def append_claims(new: list[dict]) -> list[str]:
    """Ajout seulement: on ne modifie ni ne supprime jamais un claim existant. Renvoie les identifiants attribués."""
    allc = load_claims()
    n = len(allc)
    for i, c in enumerate(new, 1):
        c["id"] = f"C{n + i:03d}"
        c["ajoute_le"] = datetime.now().isoformat(timespec="seconds")
    CLAIMS.write_text(json.dumps(allc + new, ensure_ascii=False, indent=1), encoding="utf-8")
    return [c["id"] for c in new]


def known_sources() -> set[str]:
    return {s["id"] for s in baseline()["sources"]} | {c["source"] for c in load_claims()}


def claims_for(sujet: str) -> list[dict]:
    return sorted((c for c in load_claims() if sujet in c["sujets"]), key=lambda c: c["date"])


def _autorite_label(c: dict) -> str:
    return ORIGINE_LABEL.get(c.get("origine")) or AUTORITE.get(c.get("autorite"), "inconnue")


def render(claims: list[dict]) -> str:
    """Affiche les claims au modèle: [ID] (source, date du fait, type, autorité) [étiquettes] texte.
    L'étiquette temporelle (ÉTAT ACTUEL / HISTORIQUE / CONTREDIT...) vient des fils (app/fils.py), calculée en code:
    l'ordre de la liste ne vaut jamais statut de vérité."""
    if not claims:
        return "(aucun)"
    out = []
    for c in claims:
        flags = []
        if c.get("etiquette"):
            flags.append(c["etiquette"])
        if c.get("perime"):
            flags.append(f"⚠ PÉRIMÉ/NON FIABLE: {c['perime']}")
        if c.get("statut") == "à valider":
            flags.append("⚠ À VALIDER (non confirmé par une autorité)")
        out.append(f"[{c['id']}] (source {c['source']}, {c.get('date', '?')}, {c['type']}, autorité: {_autorite_label(c)})"
                   f"{' ' + ' '.join(flags) if flags else ''} {c['texte']}")
    return "\n".join(out)


def ledger() -> dict:
    return corpus.ledger()


def finance_summary() -> str:
    """Tous les montants sont calculés ici, jamais par le LLM. Les chiffres viennent des PDF du dossier."""
    L = ledger()
    ok = {c["id"] for c in L["changements"] if c["statut"] == "approuvé"}
    autorise = L["contrat"] + sum(c["montant"] for c in L["changements"] if c["statut"] == "approuvé")
    lignes = [(f, l) for f in L["factures"] for l in f["lignes"]]
    facture = sum(l["montant"] for _, l in lignes)
    non_aut = [(f["id"], l) for f, l in lignes if l["ref"] and l["ref"] not in ok]
    paye = sum(l["montant"] for f, l in lignes if f["statut"] == "payée")
    legitime = facture - sum(l["montant"] for _, l in non_aut)
    out = [f"Contrat initial: {L['contrat']} $ [{L['contrat_source']}]",
           *[f"{c['id']}: {c['montant']} $ {c['statut']} [{c['source']}]" for c in L["changements"]],
           f"AUTORISÉ = contrat + changements approuvés = {autorise} $",
           f"FACTURÉ (toutes factures) = {facture} $", f"PAYÉ = {paye} $"]
    for fid, l in non_aut:
        out.append(f"LIGNE NON AUTORISÉE dans {fid}: {l['desc']} {l['montant']} $ (référence {l['ref']} non approuvée)")
    out.append(f"FACTURÉ LÉGITIME = {legitime} $")
    out.append(f"AUTORISÉ NON ENCORE FACTURÉ (si les lignes non autorisées sont retirées) = {autorise - legitime} $")
    out.append(f"PLAFOND AUTORISÉ DÉPASSÉ PAR LE TOTAL FACTURÉ: {'oui' if facture > autorise else 'non'}")
    for f in L["factures"]:
        out.append(f"{f['id']} ({f['date']}, {f['statut']}) [{f['source']}]: {sum(l['montant'] for l in f['lignes'])} $ = "
                   + " + ".join(f"{l['montant']} $ {l['desc']}" for l in f["lignes"]))
    return "\n".join(out)


ID_RE = re.compile(r"\b[A-Za-z]{1,5}-\d{1,4}\b")


def tokens(text: str) -> set[str]:
    """Identifiants (tickets, factures, CR, risques) et dates repérés dans un texte, pour le diff déterministe."""
    mois = "|".join(MOIS + ["janv", "févr", "avr", "juil", "sept", "oct", "nov", "déc"])
    return ({t.upper() for t in ID_RE.findall(text)}
            | set(re.findall(rf"\d{{1,2}} (?:{mois})\b", text.lower())))


def ticket_status() -> dict[str, dict]:
    """Statut courant de chaque ticket, en code (utilisé par le garde-fou « livré ≠ validé »)."""
    out = {}
    for c in load_claims():
        if c.get("origine") == "ticket":
            out[c["ticket"]] = {"statut": c["statut_ticket"], "claim": c["id"], "source": c["source"]}
    return out


_PRENOMS_IGNORÉS = {"canada", "boreal", "boréal", "projet", "phase", "comite", "comité", "central",
                      "montreal", "montréal", "numerique", "numérique", "organisation", "salon", "chrome",
                      "edge", "kafka", "total", "statut", "date", "bonjour", "merci"}


def roster() -> set[str]:
    """Prénoms des personnes nommées dans le dossier (pour détecter les mauvaises attributions)."""
    noms = set()
    blobs = [s.get("auteur", "") for s in baseline()["sources"]]
    blobs += [d["text"] for d in corpus.documents()]
    for b in blobs:
        for m in re.finditer(r"\b([A-ZÉÈ][a-zéèêëîïôöûüç]+)\s+[A-ZÉÈ][a-zéèêëîïôöûüç]+", b):
            if m.group(1).lower() not in _PRENOMS_IGNORÉS:
                noms.add(m.group(1))
    return noms
