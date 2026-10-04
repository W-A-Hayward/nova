"""Analyse d'impact d'un document reçu, en code: ce qui change par rapport à l'état actuel de chaque fil.

Pourquoi en code: un modèle 8B rate souvent les changements (extraction vide, citation approximative, type erroné).
Ici chaque phrase porteuse d'un signal (date, identifiant, montant, verbe de proposition / décision / livraison /
validation / blocage) devient un candidat dont la citation est la phrase elle-même (donc toujours ancrée), puis est
rattachée à un fil (app/fils.py) et comparée à son état actuel:
  - date: nouvelle date proposée vs date approuvée, décision annoncée (à confirmer), confirmation;
  - conditions de go-live: livraison (≠ validation), validation par le validateur désigné ou par quelqu'un d'autre,
    retard / toujours ouvert;
  - budget: montants, CR, factures.
Les actions sont déduites de règles (proposition -> comité, livraison -> re-test du validateur...), marquées
« recommandation équipe » sauf engagement écrit dans le document. Un brouillon de mise à jour (data/updates) est produit.
"""
import re
from . import fils, memory, updates, verify
from .kb import ID_RE

PROPOSITION = re.compile(r"propos|suggèr|suggere|recommand|brouillon|pourri|envisag|souhait|demandons|aimerions", re.I)
DECISION = re.compile(r"approuv|décid|decid|décision|entérin|adopt|autoris|go\b|officiel", re.I)
VALIDATION = re.compile(r"validé|validée|validation (ok|réussie|faite|complétée)|accepté|acceptée|fermé|fermée|re-?test\w* (ok|réussi)|conforme", re.I)
LIVRAISON = re.compile(r"livr|déploy|deploy|corrig|correctif|réglé|regle|mis en place|implément", re.I)
NEGATIF = re.compile(r"\b(pas|aucun|aucune|jamais|plus de temps|retard|bloqu|toujours ouvert|reporté|report)\b|n'a pas|n'ont pas|ne sera pas", re.I)
ENGAGEMENT = re.compile(r"\b(je vais|nous allons|on va|on vise|nous livrerons|je m'engage|nous nous engageons)\b", re.I)
NEGATION = re.compile(r"\b(pas|non|aucun|aucune|jamais)\b|n'|ne\s", re.I)
CONDITION_FIL = {"F05": "C1", "F06": "C2", "F07": "C3"}
# Instruction adressée au système plutôt qu'information sur le projet (injection): jamais un fait, jamais un changement
INJECTION = re.compile(r"\b(ignore[zr]?|oublie[zr]?|ne tiens? pas compte|marque[zr]?|consid[èe]re[zr]?|traite[zr]?|r[ée]ponds?|affiche[zr]?)\b.{0,60}"
                       r"(r[èe]gles?|instructions?|consignes?|comme (valid|approuv|ferm|accept)|statut)|\b(system prompt|prompt système)\b", re.I)
POLITESSE = re.compile(r"^(bonjour|bonsoir|salut|merci|cordialement|bonne journée)\b", re.I)


def parse_doc(texte: str) -> dict:
    """En-têtes (vue normalisée des courriels: De, Date, Objet) et phrases du corps."""
    head = dict(re.findall(r"(?m)^(De|Date|Objet)\s*:\s*(.+)$", texte[:600]))
    corps = re.sub(r"(?m)^(De|Date|Objet)\s*:.*$", "", texte, count=3) if head else texte
    phrases = []
    for bloc in re.split(r"\n\s*\n", corps):
        for ph in verify.sentences(" ".join(bloc.split())):
            if len(ph) > 12 and not POLITESSE.match(ph):
                phrases.append(ph)
    m = re.match(r"\d{4}-\d{2}-\d{2}", head.get("Date", ""))
    return {"auteur": head.get("De", "").strip(), "date": m.group(0) if m else "inconnue", "objet": head.get("Objet", "").strip(),
            "phrases": phrases}


def classer(phrase: str) -> tuple[str, str]:
    """(type, nuance) d'une phrase, par règles: proposition > validation > décision > livraison > signal > fait."""
    neg = bool(NEGATION.search(phrase))
    if PROPOSITION.search(phrase) and not VALIDATION.search(phrase):
        return "proposition", ""
    if VALIDATION.search(phrase) and not neg:
        return "validation", ""
    if DECISION.search(phrase) and not neg and not re.search(r"à vous de|a vous de|confirmer la décision", phrase, re.I):
        return "décision", ""
    if LIVRAISON.search(phrase) and not neg:
        return "fait", "livraison"
    if NEGATIF.search(phrase):
        return "signal", "retard ou blocage"
    return "fait", ""


def signal(phrase: str) -> bool:
    e = verify.entities(phrase)
    return bool(e["date"] or e["identifiant"] or e["montant"] or PROPOSITION.search(phrase) or DECISION.search(phrase)
                or VALIDATION.search(phrase) or LIVRAISON.search(phrase) or NEGATIF.search(phrase)
                or any(f[3] and re.search(fils.RATTACHE.get(f[0], f[3]), phrase, re.I) for f in fils.FILS))


def claims_deterministes(texte: str, nom: str, source: str) -> list[dict]:
    """Une phrase signal = un claim candidat, citation = la phrase (ancrage garanti), type par règles.
    Les instructions adressées au système (injection) sont exclues: voir instructions()."""
    doc = parse_doc(texte)
    out = []
    for ph in doc["phrases"]:
        if not signal(ph) or INJECTION.search(ph):
            continue
        typ, nuance = classer(ph)
        out.append({"date": doc["date"], "type": typ, "nuance": nuance, "texte": ph, "citation": ph, "sujets": [],
                    "source": source, "fichier": nom, "autorite": None, "statut": "à valider", "origine": "ingestion",
                    "perime": "", "correction_type": "", "extraction": "règles"})
    return out


def instructions(texte: str) -> list[str]:
    """Phrases du document qui donnent des ordres au système: écartées et signalées dans le rapport."""
    return [ph for ph in parse_doc(texte)["phrases"] if INJECTION.search(ph)]


def fils_de(texte: str) -> list[str]:
    out = [fid for fid, *_ in fils.FILS if fid in fils.RATTACHE and re.search(fils.RATTACHE[fid], texte, re.I)]
    if not out:
        out = [f["id"] for f in fils.all_fils() if f["id"] != "F13" and f["regex"].search(texte)][:1]
    return out


def _date_actuelle() -> tuple[str, set]:
    cur = updates.apply(memory.load_memory(), updates.load())["date_approuvee"]["valeur"]
    return cur, verify.entities(cur)["date"]


def analyser(nouveaux: list[dict], texte: str) -> dict:
    """Compare chaque nouveau claim à l'état actuel du fil qu'il touche. Renvoie changements, affectés, actions, brouillon."""
    doc = parse_doc(texte)
    auteur = doc["auteur"] or "auteur inconnu"
    date_cur, date_cur_ent = _date_actuelle()
    m = memory.load_memory()
    conds = {c["id"]: c for c in m["conditions"]}
    acts = {a["id"]: a for a in m["actions"]}
    changements, actions, touches = [], [], {}
    for c in nouveaux:
        blob = c["texte"] + " " + c.get("citation", "")
        typ = c["type"]
        nuance = c.get("nuance") or ("livraison" if typ == "fait" and LIVRAISON.search(blob) and not NEGATION.search(blob) else "")
        for fid in fils_de(blob):
            f = fils.get(fid)
            ch = {"fil": fid, "titre": f["titre"], "baseline": f["actuel"], "nouveau": c["texte"], "citation": c.get("citation", c["texte"]),
                  "type": typ, "par": auteur, "date": c.get("date", doc["date"]), "relation": "", "statut": "", "champ": f["titre"]}
            if fid == "F01":
                ch["champ"] = "date_mise_en_production"
                dates = verify.entities(blob)["date"] - date_cur_ent - {(10, 15)}  # 15 octobre: ancienne cible, pas une nouvelle date
                dates = {d for d in dates if d[0] >= 10}  # une date de mise en production future (octobre ou plus tard)
                if dates:
                    nv = ", ".join(f"{j} {['', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'][mo]}"
                                   for mo, j in sorted(dates))
                    ch["nouveau_valeur"] = nv + " 2026"
                    if typ == "décision":
                        ch["relation"], ch["statut"] = f"décision annoncée de changer la date ({nv}) : à confirmer par le comité de direction", "approuvé"
                    else:
                        ch["relation"], ch["statut"] = f"NOUVELLE PROPOSITION de date ({nv}) ; la date approuvée reste le {date_cur}", "proposé"
                        actions.append(("Soumettre la proposition de report au comité de direction. Ne pas communiquer la nouvelle date "
                                        "avant décision", "Nicolas Perron (chargé de projet)", "avant le " + date_cur, c))
                elif date_cur_ent & verify.entities(blob)["date"]:
                    ch["relation"], ch["statut"] = f"confirme ou mentionne la date du {date_cur}", "fait"
                else:
                    continue
            elif fid in CONDITION_FIL:
                cid = CONDITION_FIL[fid]
                cond = conds[cid]
                ch["champ"] = f"condition:{cid}"
                validateur = cond["validateur"].split()[0].lower()
                par_validateur = validateur in auteur.lower()
                if typ == "validation" and par_validateur:
                    ch["relation"], ch["statut"] = f"validation déclarée par le validateur ({cond['validateur']}) : {cid} levable après vérification humaine", "validé"
                    actions.append((f"Vérifier et consigner la validation écrite de {cond['validateur']}, puis lever {cid}", "Nicolas Perron", "à confirmer", c))
                elif typ == "validation":
                    ch["relation"], ch["statut"] = (f"« validé / fermé » affirmé par {auteur}, qui n'est pas le validateur ({cond['validateur']}) : "
                                                    f"{cid} reste ouverte"), "signal"
                    actions.append((f"Obtenir la confirmation écrite de {cond['validateur']} avant de lever {cid}", "Nicolas Perron", "à confirmer", c))
                elif nuance == "livraison":
                    ch["relation"], ch["statut"] = f"LIVRAISON annoncée (≠ validation) : {cid} reste ouverte jusqu'à la validation de {cond['validateur']}", "fait"
                    actions.append((f"Faire re-tester par {cond['validateur']} ; ne pas lever {cid} avant sa validation écrite",
                                    cond["validateur"], "à confirmer (avant le go-live)", c))
                elif typ == "signal" or NEGATIF.search(blob):
                    ch["relation"], ch["statut"] = f"toujours ouvert / retard : {cid} non remplie", "signal"
                    actions.append((f"Obtenir une échéance ferme pour {cond['libelle'].lower()}", "Nicolas Perron", "à confirmer", c))
                else:
                    ch["relation"], ch["statut"] = "nouvelle information sur une condition de go-live (à qualifier)", "fait"
                for aid in cond["actions"]:
                    touches.setdefault(aid, []).append(ch["relation"])
            elif fid == "F04":
                ids = {x.upper() for x in ID_RE.findall(blob)}
                ch["relation"] = ("information financière nouvelle" + (f" ({', '.join(sorted(ids))})" if ids else "")
                                  + " : aucun montant autorisé ne change sans décision approuvée")
                ch["statut"] = {"proposition": "proposé", "décision": "approuvé", "validation": "validé"}.get(typ, "fait")
                actions.append(("Faire valider par les Finances (Amélie Fortin) avant tout paiement", "Amélie Fortin (Finances)", "à confirmer", c))
                if "INV-003" in ids or "CR-04" in ids:
                    touches.setdefault("A6", []).append(ch["relation"])
            else:
                ch["relation"] = "nouvelle information (à valider)"
                ch["statut"] = {"proposition": "proposé", "décision": "approuvé", "validation": "validé"}.get(typ, "fait")
            if ENGAGEMENT.search(blob):
                ch["engagement"] = True
            changements.append(ch)
    # une information « à qualifier » n'ajoute rien si le même champ a déjà un changement qualifié
    qualifies = {ch["champ"] for ch in changements if "à qualifier" not in ch["relation"]}
    changements = [ch for ch in changements if "à qualifier" not in ch["relation"] or ch["champ"] not in qualifies]
    # actions: une par libellé; engagement documenté seulement si le document s'engage explicitement
    vues, nouvelles = set(), []
    for libelle, resp, ech, c in actions:
        if libelle in vues:
            continue
        vues.add(libelle)
        nouvelles.append({"action": libelle, "executant": resp, "echeance": ech, "statut_resp": "proposé",
                          "nature": "engagement documenté (à valider)" if ENGAGEMENT.search(c.get("citation", "")) else "recommandation équipe",
                          "preuve": c.get("citation", "")})
    affectes = []
    for aid, eff in touches.items():
        eff = [x for x in dict.fromkeys(eff) if "à qualifier" not in x] or list(dict.fromkeys(eff))
        if aid in acts:
            affectes.append({"id": aid, "action": acts[aid].get("court") or acts[aid]["action"], "baseline": acts[aid]["statut"],
                             "effet": " ; ".join(eff)})
    touches_fils = sorted({ch["fil"] for ch in changements})
    inchanges = [f"{c['id']} {c['libelle']} : {c['statut_ticket']} (non levée)" for c in m["conditions"]
                 if f"condition:{c['id']}" not in {ch["champ"] for ch in changements if ch["statut"] == "validé"}]
    if "F01" not in touches_fils or not any(ch["statut"] == "approuvé" for ch in changements if ch["fil"] == "F01"):
        inchanges.append(f"Date approuvée : {date_cur} (aucune nouvelle décision du comité dans ce document)")
    if "F04" not in touches_fils:
        inchanges.append("Budget autorisé (204 000 $) et factures : non touchés")
    return {"doc": doc, "changements": changements, "affectes": affectes, "actions": nouvelles, "inchanges": inchanges,
            "fils": touches_fils}


def brouillon(analyse: dict, fichier_doc: str, uid: str) -> dict:
    """Brouillon de mise à jour (schéma data/updates) à faire valider par un humain avant enregistrement."""
    doc, chs = analyse["doc"], analyse["changements"]
    date_ch = [c for c in chs if c["champ"] == "date_mise_en_production" and c.get("nouveau_valeur")]
    cond_ch = [c for c in chs if c["champ"].startswith("condition:")]
    return {
        "id": uid, "exercice": "EXERCICE" in (doc["objet"] + " ".join(doc["phrases"][:2])).upper(),
        "recu_le": doc["date"] + "T00:00:00-04:00" if doc["date"] != "inconnue" else "",
        "document": {"fichier": fichier_doc, "titre": f"{doc['auteur'] or 'Auteur inconnu'} : {doc['objet'] or fichier_doc}"},
        "resume": " ".join(f"{c['titre']} : {c['relation']}." for c in chs if c["relation"])[:600],
        "statut_probleme": " ".join(f"{c['champ'].split(':')[-1]} : {c['relation']}." for c in cond_ch) or "Aucune condition de go-live touchée.",
        "decision_anterieure": fils.get("F01")["actuel"].split(". Le 15 octobre")[0] + "." if date_ch else
                               "Inchangée : " + fils.get("F01")["actuel"].split(".")[0] + ".",
        "nouvelle_proposition": "; ".join(f"{c['nouveau_valeur']} ({c['statut']}, par {c['par']})" for c in date_ch) or "Aucune.",
        "changements": [{"champ": c["champ"], "baseline": c["baseline"][:160], "nouveau": c.get("nouveau_valeur") or c["nouveau"], "statut": c["statut"] or "fait",
                         "par": c["par"], "preuve": c["citation"]} for c in chs],
        "actions_touchees": [{"id": a["id"], "effet": a["effet"], "statut": "à réévaluer"} for a in analyse["affectes"]],
        "nouvelles_actions": [{"id": f"N{i}", **{k: v for k, v in a.items() if k != "preuve"}} for i, a in enumerate(analyse["actions"], 1)],
    }
