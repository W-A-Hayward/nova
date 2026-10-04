"""Mises à jour après la baseline: une couche AU-DESSUS de data/memory.json, qui n'est jamais réécrit.

Une mise à jour = un fichier data/updates/Uxx_*.json (rempli à la main, éventuellement aidé par /ingest) qui renvoie
à son document reçu (data/updates/docs/...). L'état actuel = baseline + mises à jour, recalculé à chaque affichage.

Garde-fous en code (critère « mise à jour » du README):
- chaque preuve est un extrait verbatim retrouvé dans le document reçu, sinon le changement est écarté;
- « approuvé » exige une approbation explicite (vocabulaire d'approbation, sans négation) et un approbateur nommé,
  sinon le changement est rétrogradé en « proposé »: une proposition ne remplace jamais une décision;
- une condition de go-live n'est levée que par une validation de SON validateur (Sophie, Mélissa, Olivier);
- tout ce qui n'est pas touché par la mise à jour est listé « inchangé » par le code (rien n'est fermé par défaut).
"""
import copy
import json
import re
from pathlib import Path
from . import corpus, evidence

DATA = Path(__file__).resolve().parent.parent / "data"
UPDATES = DATA / "updates"
STATUTS = ("proposé", "approuvé", "validé", "fait", "signal")


def doc_text(path: Path) -> str:
    return corpus.read_bytes(path.name, path.read_bytes())


def load(folder: Path = UPDATES) -> list[dict]:
    """Fichiers Uxx_*.json triés; les fichiers commençant par « _ » (modèle) sont ignorés."""
    if not folder.is_dir():
        return []
    out = []
    for f in sorted(folder.glob("U*.json")):
        u = json.loads(f.read_text(encoding="utf-8"))
        u["_fichier"] = str(f.relative_to(folder.parent)) if folder.parent in f.parents else f.name
        u["_base"] = str(f.parent)
        out.append(u)
    return out


def _found(extrait: str, texte: str) -> bool:
    return bool(extrait) and evidence.norm(extrait) in evidence.norm(texte)


def check(u: dict) -> dict:
    """Vérifie une mise à jour; renvoie une copie annotée (statut retenu, avertissements)."""
    from .ingest_graph import APPROBATION, NEGATION  # import tardif: ingest_graph -> chat_graph -> fils -> updates
    u = copy.deepcopy(u)
    path = Path(u["_base"]) / u["document"]["fichier"]
    texte = doc_text(path) if path.exists() else ""
    u["_document_texte"] = texte
    u["_avertissements"] = [] if texte else [f"document introuvable: {u['document']['fichier']}"]
    retenus = []
    for ch in u.get("changements", []):
        ch = dict(ch)
        ex = ch.get("preuve", "")
        if not _found(ex, texte):
            u["_avertissements"].append(f"« {ch.get('champ')} » écarté : extrait introuvable dans le document reçu.")
            continue
        demande = ch.get("statut", "proposé") if ch.get("statut") in STATUTS else "proposé"
        ch["statut_demande"] = demande
        if demande in ("approuvé", "validé"):
            explicite = APPROBATION.search(ex) and not NEGATION.search(ex)
            if not (explicite and ch.get("par")):
                ch["statut"] = "proposé"
                u["_avertissements"].append(f"« {ch.get('champ')} » : « {demande} » non démontré par l'extrait "
                                            "(approbation explicite et approbateur requis), retenu comme proposition.")
        retenus.append(ch)
    u["changements"] = retenus
    return u


def apply(baseline: dict, ups: list[dict]) -> dict:
    """État actuel = baseline + mises à jour vérifiées. La baseline passée en argument n'est pas modifiée."""
    cur = copy.deepcopy(baseline)
    cur["mises_a_jour"] = []
    actions = {a["id"]: a for a in cur["actions"]}
    conds = {c["id"]: c for c in cur["conditions"]}
    golive = next(d for d in cur["decisions"] if d["sujet"] == "Date de mise en production")
    cur["date_approuvee"] = {"valeur": golive["decision"]["valeur"], "source": "baseline (M04, 10 sept)", "propositions": []}
    for u in map(check, ups):
        touches = set()
        for ch in u["changements"]:
            champ, statut = ch["champ"], ch["statut"]
            if champ == "date_mise_en_production":
                touches.add("date")
                if statut == "approuvé":
                    cur["date_approuvee"] = {"valeur": ch["nouveau"], "source": f"{u['id']} ({ch['par']})", "propositions": cur["date_approuvee"]["propositions"]}
                else:
                    cur["date_approuvee"]["propositions"].append({"valeur": ch["nouveau"], "par": ch.get("par", "?"), "maj": u["id"]})
            m = re.fullmatch(r"condition:(C\d)", champ)
            if m and m.group(1) in conds:
                c = conds[m.group(1)]
                touches.add(c["id"])
                levee = statut == "validé" and c["validateur"].split()[0].lower() in str(ch.get("par", "")).lower()
                c["statut_ticket"] = "LEVÉE" if levee else c["statut_ticket"]
                c.setdefault("evolution", []).append({"maj": u["id"], "texte": ch["nouveau"], "statut": statut, "levee": levee})
                if statut == "validé" and not levee:
                    u["_avertissements"].append(f"{c['id']} : seule la validation de {c['validateur']} peut lever la condition. Elle reste ouverte.")
        for at in u.get("actions_touchees", []):
            a = actions.get(at["id"])
            if a:
                touches.add(at["id"])
                a.setdefault("evolution", []).append({"maj": u["id"], **{k: v for k, v in at.items() if k != "id"}})
        for na in u.get("nouvelles_actions", []):
            na = {"nature": "recommandation équipe", "echeance": "à confirmer", **na, "origine": u["id"]}
            cur["actions"].append(na)
        u["_inchanges"] = ([f"{c['id']} {c['libelle']} : {c['statut_ticket']} (non levée)" for c in conds.values() if c["id"] not in touches]
                           + ([] if "date" in touches else [f"Date approuvée : {cur['date_approuvee']['valeur']}"])
                           + ["Budget autorisé (204 000 $) et factures : non touchés par cette mise à jour"])
        cur["mises_a_jour"].append(u)
    return cur
