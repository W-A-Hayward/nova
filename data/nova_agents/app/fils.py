"""Fils thématiques: l'état actuel d'un sujet et l'évolution des sources qui en parlent, du plus ancien au plus récent.

Principe de vérité (README: « une date de fichier récente ne garantit pas une information exacte »):
  état actuel = le fait DOCUMENTÉ le plus récent, émanant d'une source compétente pour ce fait
  (décision formelle, validateur désigné, ticket), daté par la date du FAIT et non par la date du fichier.
Les sources plus anciennes ou contredites ne sont pas jetées: elles sont exposées avec leur rôle (historique,
proposition, livraison, contredit...) pour montrer l'évolution des décisions et donner du contexte.

Tout est assemblé en code à partir de la mémoire vérifiée (data/memory.json, extraits verbatim) et des mises à jour
(data/updates/): aucun LLM ne décide de ce qui est actuel ou périmé.
"""
import re
from datetime import date, timedelta
from functools import lru_cache
from . import evidence, kb, memory, retrieval, updates

# id, titre, sujet kb, mots-clés (routage + rattachement des événements), état actuel, preuves, inconnu
FILS = [
    ("F01", "Date de mise en production", "gouvernance",
     r"22 octobre|15 octobre|\bdate\b|mise en production|go-live|golive|report|livraison prévue|lancement",
     "Date approuvée : 22 octobre 2026, décidée par le comité de direction le 10 septembre 2026. Le 26 septembre, la cible est "
     "reconfirmée mais conditionnelle à trois éléments (validation sécurité de SEC-210, fermeture de ACC-303, approbation du "
     "runbook incluant le rollback) : ce n'est pas un go garanti. Le 15 octobre est périmé.",
     [(memory.M04, "15:25 Élodie : Donc approuvé. Le 22 devient la date officielle."), (memory.M06, "c'est conditionnel à ces trois éléments"),
      ("01_Courriels/E09_Rappel_mise_en_production.eml", "Merci de ne pas communiquer le 22 comme un go garanti")],
     ["Aucune décision finale de go/no-go n'est documentée au 30 septembre."]),
    ("F02", "Hébergement des données de production", "technique",
     r"canada|east us|héberg|heberg|adr-007|localisation|région|migration vers|architecture",
     "Les données de production doivent être hébergées dans Canada Central (ADR-007, acceptée le 23 juillet 2026), qui remplace "
     "East US de l'architecture v1. La migration a été déclarée terminée par Boréal le 26 août et vérifiée par l'équipe architecture "
     "le 27 août.",
     [(memory.ADR, "L'environnement de production de NOVA sera déployé dans Canada Central."),
      (memory.M03, "déclarée terminée par Boréal et vérifiée par l'équipe architecture")],
     ["Aucune preuve sur l'environnement de production lui-même : NOVA n'est pas encore en production au 30 septembre."]),
    ("F03", "Chargé de projet", "gouvernance",
     r"chargée? de projet|charge du projet|responsable du projet|qui est responsable|transition|qui dirige|gestionnaire",
     "Nicolas Perron est chargé de projet depuis le 16 septembre 2026. Il succède à Élodie Caron, chargée de projet depuis le "
     "7 juillet 2026.",
     [("01_Courriels/E06_Transition_charge_projet.eml", "Nicolas Perron prend officiellement la charge du projet NOVA à compter d'aujourd'hui, 16 septembre."),
      (memory.M01, "Élodie Caron agit comme chargée de projet.")], []),
    ("F04", "Budget, changements et factures", "finance",
     r"cr-0|inv-|factur|budget|montant|coût|cout|contrat|payé|paye|autoris|\$|mobile|phase 2|fournisseur",
     "Montant autorisé : 204 000 $ = contrat 180 000 $ + CR-01 24 000 $ (approuvé le 14 août 2026). CR-04 (18 000 $, optimisation "
     "mobile avancée) est un brouillon jamais approuvé, reporté à la phase 2 le 24 septembre : il ne doit pas être facturé. "
     "INV-003 (54 000 $, en validation) contient une ligne CR-04 de 18 000 $ ; les Finances demandent l'approbation le 23 septembre.",
     [(memory.CONTRAT, "Montant maximal initial 180 000 $"), (memory.CR01, "APPROUVÉE Date de décision 14 août 2026 Autorité Comité de projet"),
      ("01_Courriels/E10_Fonction_mobile.eml", "Aucune dépense liée à CR-04 ne doit être engagée ou facturée sans nouvelle approbation."),
      ("01_Courriels/E07_Facture_003_question.eml", "Peux-tu me transmettre l'approbation correspondante?")],
     ["Aucune réponse documentée de Nicolas Perron aux Finances sur INV-003.", "Aucune facture corrigée ni note de crédit documentée.",
      "Aucun budget de phase 2 n'est documenté."]),
    ("F05", "Sécurité (SEC-210)", "qualite",
     r"sec-210|sécurit|securit|audit|journalis|sophie",
     "SEC-210 n'est pas accepté. Le correctif a été déployé en environnement de validation le 19 septembre (livraison), mais "
     "la validation de la sécurité (Sophie Lambert) n'est pas faite : re-test planifié le 26 septembre, statut EN VALIDATION. "
     "C'est la condition de go-live C1.",
     [(memory.T + "SEC-210.txt", "26 sept 15:40 - Sophie : Re-test planifié. Statut maintenu EN VALIDATION."),
      (memory.M06, "Nous n'avons pas encore donné l'acceptation sécurité de SEC-210."),
      ("01_Courriels/E08_Correctif_journalisation.eml", "Le correctif pour SEC-210 est déployé en validation depuis ce matin.")],
     ["Date et résultat du re-test de SEC-210."]),
    ("F06", "Accessibilité (ACC-301 à ACC-303)", "qualite",
     r"acc-30|accessibilit|clavier|modale|contraste|libellé|label|mélissa|melissa",
     "L'accessibilité n'est pas complétée. ACC-301 (fermé le 15 août) et ACC-302 (fermé le 20 août) sont validés ; ACC-303 "
     "(le bouton Enregistrer de la modale est inatteignable au clavier) reste OUVERT, avec un correctif annoncé pour la prochaine "
     "build le 26 septembre. C'est la condition de go-live C2.",
     [(memory.T + "ACC-303.txt", "26 sept 11:03 - Mélissa : Toujours ouvert. Correctif annoncé pour la prochaine build."),
      (memory.T + "ACC-301.txt", "15 août - Mélissa : Validé avec NVDA et VoiceOver. Fermé."),
      (memory.T + "ACC-302.txt", "20 août - Mélissa : Re-test OK à 5,3:1. Fermé.")],
     ["Date de la prochaine build et du re-test d'ACC-303."]),
    ("F07", "Exploitation et runbook (OPS-601)", "qualite",
     r"ops-601|runbook|rollback|retour arrière|retour arriere|exploitation|olivier",
     "Le runbook n'est pas approuvé. La capture du 25 septembre montre deux étapes manquantes : l'étape 4 (procédure de retour "
     "arrière, TODO) et l'étape 5 (validation fonctionnelle post-déploiement, À compléter). Olivier Côté n'avait toujours pas reçu "
     "la version finale le 29 septembre. C'est la condition de go-live C3.",
     [(memory.T + "OPS-601_runbook.png", "Étape 4. Procédure de retour arrière — TODO"),
      (memory.T + "OPS-601_runbook.png", "Étape 5. Validation fonctionnelle post-déploiement — À compléter"),
      (memory.T + "OPS-601.txt", "29 sept - Olivier : Toujours pas reçu la version finale.")],
     ["Échéance de livraison du runbook final (Olivier veut l'avoir quelques jours avant le go-live)."]),
    ("F08", "Intégration (INT-101) et registre des risques", "technique",
     r"int-101|connecteur|intégration|integration|\br-01\b|registre|cause",
     "INT-101 (connecteur interne, cause du report de date) est fermé depuis le 17 septembre 2026 : 120 recherches sur 120 validées "
     "par Marc Gervais. La ligne R-01 du registre du 29 septembre, encore « Ouvert » avec un suivi au 9 septembre, est périmée.",
     [(memory.T + "INT-101.txt", "17 sept 16:10 - Marc : Validé côté intégration. Je ferme."),
      (memory.REGISTRE, "Statut: Ouvert | Mitigation: Suivi fournisseur hebdomadaire | Commentaire: Suivi au 9 septembre 2026")], []),
    ("F09", "Conditions de go-live", "qualite",
     r"condition|go-live|golive|bloqu|empêch|empech|reste à|reste a|prochaines? (étapes|actions)|engagement|compl[eé]t",
     "Trois conditions de go-live (comité du 26 septembre) : C1 validation sécurité de SEC-210, C2 fermeture de ACC-303, "
     "C3 approbation du runbook incluant le rollback. Au 30 septembre, aucune n'est remplie et aucune échéance n'est documentée.",
     [(memory.M06, "Donc trois conditions concrètes : validation sécurité de SEC-210, fermeture de ACC-303 et approbation du runbook incluant rollback.")],
     ["Aucune échéance documentée pour C1, C2 et C3."]),
    ("F10", "Statut communiqué et rapport de statut", "gouvernance",
     r"communic|rapport de statut|au vert|\bvert\b|alex|statut global|santé du projet",
     "Le statut « au vert » (rapport du 21 septembre, brouillon d'Alex Deschamps) est contredit : SEC-210 est EN VALIDATION et "
     "ACC-303 OUVERT. Le 27 septembre, Nicolas Perron demande de ne pas communiquer le 22 comme un go garanti.",
     [(memory.RAPPORT, "Le rapport a été préparé avant la dernière vérification détaillée de certains tickets."),
      ("01_Courriels/E09_Rappel_mise_en_production.eml", "Merci de ne pas communiquer le 22 comme un go garanti")],
     ["Le dossier ne dit pas si le message d'Alex a été envoyé ou corrigé."]),
    ("F11", "Migration des données et performance", "technique",
     r"data-401|doublon|perf-501|lent|performance|migration de donn|migration des donn",
     "DATA-401 (doublons de migration) est fermé depuis le 9 septembre : 15 000 événements rejoués sans doublon. PERF-501 "
     "(lenteur de la recherche) est fermé depuis le 7 septembre : 620 ms en moyenne sur 50 essais.",
     [(memory.T + "DATA-401.txt", "9 septembre - lot de 15 000 événements rejoué, aucun doublon détecté. Ticket fermé."),
      (memory.T + "PERF-501.txt", "07 sept 09:12 - Support : moyenne observée 620 ms sur 50 essais.")], []),
    ("F13", "Actions restantes et engagements", "gouvernance", r"action|engagement|prochaines? [ée]tapes?|[àa] faire|en suspens",
     "", [], ["Aucune échéance précise n'est documentée : toutes les échéances sont « à confirmer »."]),
    ("F12", "Authentification", "technique", r"\bsso\b|authentific|comptes? locaux",
     "Authentification : SSO uniquement en production (atelier architecture du 23 juillet 2026).",
     [(memory.M02, "SSO seulement en production.")], []),
]
TITRES = {f[0]: f[1] for f in FILS}
SUJET = {f[0]: f[2] for f in FILS}

# Décisions et contradictions de la mémoire -> fils (par sujet)
DECISION_FIL = {"Date de mise en production": ["F01"], "Hébergement des données de production": ["F02"], "Chargé de projet": ["F03"],
                "CR-01 : rapports avancés": ["F04"], "CR-04 : optimisation mobile avancée": ["F04"], "Conditions de go-live": ["F09", "F01"],
                "Authentification": ["F12"]}
CONTRA_FIL = [("Date de mise en production", ["F01"]), ("Plan projet v3", ["F01"]), ("Registre des risques", ["F08"]),
              ("Rapport de statut", ["F10", "F05", "F06"]), ("Communication", ["F10", "F01"]), ("SEC-210", ["F05"]),
              ("Accessibilité", ["F06"]), ("Mobile avancé", ["F04"]), ("Notes personnelles", ["F01"])]
# Rattachement des événements de la chronologie à un fil: plus strict que le routage (évite « date de décision », « reporté à la phase 2 »)
RATTACHE = {
    "F01": r"22 octobre|15 octobre|mise en production|go garanti|go-live|report de date|cause du report|date officielle",
    "F04": r"cr-0|inv-|factur|budget|180 000|mobile|finances",
    "F05": r"sec-210|validation sécurité|acceptation sécurité|journalis|audit",
    "F06": r"acc-30|accessibilit|clavier",
    "F07": r"ops-601|runbook|retour arrière|rollback",
    "F08": r"int-101|connecteur|\br-01\b",
    "F09": r"trois conditions|conditionnel",
    "F10": r"au vert|rapport de statut|communication|go garanti",
}
CHAMP_FIL = {"date_mise_en_production": "F01", "condition:C1": "F05", "condition:C2": "F06", "condition:C3": "F07"}

ROLE_LABEL = {"historique": "HISTORIQUE (remplacé)", "proposition": "PROPOSITION", "décision": "DÉCISION", "validation": "VALIDATION",
              "livraison": "LIVRAISON (≠ validation)", "écarté": "CONTREDIT (écarté)", "retenu": "RETENU", "signal": "SIGNAL (non fiable)",
              "fait": "FAIT", "mise à jour": "MISE À JOUR (à valider)"}
PASSE = {"historique", "écarté", "signal"}  # rôles qui ne décrivent pas l'état actuel

# Intentions de question qui appellent des fils sans mot-clé de sujet
CONTRADICTION_Q = re.compile(r"contradict|incoh[ée]ren|diverg|conflit|se contredi|versions? diff", re.I)
REPRISE_Q = re.compile(r"reprendre|demain matin|devrais-je savoir|dois-je savoir|état du projet|etat du projet|résum|resum|vue d'ensemble|où en est|ou en est", re.I)
RISQUE_Q = re.compile(r"risque|bloquant|inqui[eè]t|menace", re.I)
FENETRE_Q = re.compile(r"semaine derni[eè]re|depuis (la|une) semaine|(\d+|sept|quinze) derniers jours|r[ée]cemment|a chang[ée]|ont chang[ée]|nouveau|du nouveau", re.I)
DEPUIS_Q = re.compile(r"depuis le (\d{1,2})(?:er)? (juillet|août|aout|septembre|octobre)", re.I)
MOIS = {"juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10}


def _claim_index() -> dict[tuple[str, str], dict]:
    return {(c.get("fichier", ""), c.get("repere", "")): c for c in kb.load_claims() if c.get("origine") not in ("ticket", "ingestion")}


def _entry(p: dict, role: str, texte: str, qui: str = "", date_: str = "", heure: str = "", note: str = "", idx=None) -> dict:
    """Une prise de position datée sur le fil, avec sa preuve verbatim et le claim correspondant (citable par le chat)."""
    c = (idx or {}).get((p["fichier"], p.get("repere", "")))
    if not heure and c:  # heure du passage (« 19 sept 10:22 - Boréal : ... », « 10:09 Nicolas : ... ») pour ordonner une même journée
        m = re.match(r"\[[^\]]*\]\s*(?:\d{1,2} \w+\.? )?(\d{1,2}:\d{2})\b", c["texte"])
        heure = m.group(1) if m else ""
    d = date_ or (c or {}).get("date") or evidence.by_file().get(p["fichier"], {}).get("date", "inconnue")
    return {"date": d, "heure": heure, "role": role, "qui": qui, "texte": texte, "note": note, "fichier": p["fichier"],
            "extrait": p.get("extrait", ""), "repere": p.get("repere", ""), "anchor": p.get("anchor", ""), "claim": (c or {}).get("id")}


@lru_cache(maxsize=1)
def _base() -> tuple[dict, ...]:
    m = memory.load_memory()
    idx = _claim_index()
    fils = {fid: {"id": fid, "titre": t, "sujet": s, "regex": re.compile(rx, re.I), "actuel": a, "inconnu": list(inc),
                  "preuves_actuel": [memory._resolve(memory.s(f, x)) for f, x in pr], "entrees": [], "resolutions": []}
            for fid, t, s, rx, a, pr, inc in FILS}

    acts = m["actions"]  # F13: les actions de la mémoire (responsable, échéance, engagement ou recommandation)
    fils["F13"]["actuel"] = " ; ".join(
        f"{a['id']}{(' (' + a['condition'] + ')') if a.get('condition') else ''} {a.get('court') or a['action']} — échéance {a['echeance']} — "
        f"{a['nature']} — statut {a['statut']}" for a in acts) + "."
    fils["F13"]["preuves_actuel"] = [a["preuves"][0] for a in acts]

    def add(fid, e):
        old = next((x for x in fils[fid]["entrees"] if (x["fichier"], x["repere"]) == (e["fichier"], e["repere"])
                    or (x["fichier"] == e["fichier"] and x["date"] == e["date"] and x["role"] == e["role"])), None)
        if old is None:
            fils[fid]["entrees"].append(e)
        elif e["role"] in ("écarté", "retenu", "historique") and old["role"] not in ("écarté", "historique"):
            old.update(role=e["role"], note=e["note"] or old["note"])  # le rôle établi par une contradiction prime

    for c in m["contradictions"]:
        cibles = next((f for k, f in CONTRA_FIL if c["sujet"].startswith(k)), [])
        n = len(c["affirmations"])
        for i, a in enumerate(c["affirmations"]):  # convention de la mémoire: la dernière affirmation est celle retenue
            role = "retenu" if i == n - 1 else ("signal" if "non fiable" in c["regle"] else "écarté")
            for fid in cibles:
                add(fid, _entry(a["preuve"], role, a["texte"], a["autorite"], a["date"] if a["date"] != "inconnue" else "",
                                note="" if role == "retenu" else c["resolution"], idx=idx))
        for fid in cibles:
            fils[fid]["resolutions"].append({"sujet": c["sujet"], "texte": c["resolution"], "regle": c["regle"], "preuve": c["preuve_resolution"]})
    for d in m["decisions"]:
        for fid in DECISION_FIL.get(d["sujet"], []):
            if d["remplace"]:
                add(fid, _entry(d["remplace"]["preuve"], "historique", d["remplace"]["valeur"],
                                note=f"remplacé par : {d['decision']['valeur']} ({d['decision']['quand']})", idx=idx))
            if d["proposition"]:
                x = d["proposition"]
                add(fid, _entry(x["preuve"], "proposition", f"« {x['preuve']['extrait']} »", x["qui"], x["quand"], idx=idx))
            x = d["decision"]
            add(fid, _entry(x["preuve"], "décision", x["valeur"], x["qui"], x["quand"], idx=idx))
            if d["validation"]:
                x = d["validation"]
                add(fid, _entry(x["preuve"], "validation", x["valeur"], x["qui"], x["quand"], idx=idx))
    for t in m["timeline"]:
        blob = t["evenement"] + " " + " ".join(p["extrait"] for p in t["preuves"])
        for fid, f in fils.items():
            if re.search(RATTACHE.get(fid, f["regex"].pattern), blob, re.I):
                for p in t["preuves"][:1]:
                    add(fid, _entry(p, t["nature"], t["evenement"], t["acteur"], t["date"], t["heure"], idx=idx))
    for f in fils.values():
        f["entrees"].sort(key=lambda e: (e["date"] if e["date"][:1].isdigit() else "9999", e["heure"] or "99:99"))
    return tuple(fils.values())


def all_fils() -> list[dict]:
    """Fils de la baseline + effets des mises à jour (data/updates), recalculés à chaque appel."""
    fils = [dict(f, entrees=list(f["entrees"]), resolutions=list(f["resolutions"])) for f in _base()]
    by = {f["id"]: f for f in fils}
    ups = updates.load()
    if ups:
        cur = updates.apply(memory.load_memory(), ups)
        for u in cur["mises_a_jour"]:
            for ch in u["changements"]:
                fid = CHAMP_FIL.get(ch["champ"])
                if not fid:
                    continue
                by[fid]["entrees"].append({"date": u["recu_le"][:10], "heure": u["recu_le"][11:16], "role": "mise à jour",
                                           "qui": ch.get("par", ""), "texte": f"{ch['nouveau']} (statut retenu : {ch['statut']})",
                                           "note": "", "fichier": u["_fichier"], "extrait": ch["preuve"], "repere": u["id"],
                                           "anchor": "", "claim": None, "maj": True})
                if ch["statut"] == "proposé":
                    by[fid]["actuel"] += f" Depuis la baseline ({u['id']}) : nouvelle proposition non approuvée : {ch['nouveau']}."
        if cur["date_approuvee"]["valeur"] != "22 octobre 2026":
            by["F01"]["actuel"] = f"Date approuvée : {cur['date_approuvee']['valeur']} ({cur['date_approuvee']['source']}). " + by["F01"]["actuel"]
    return fils


def get(fid: str) -> dict:
    return next(f for f in all_fils() if f["id"] == fid)


def pseudo_claims(fils: list[dict] | None = None) -> dict[str, dict]:
    """L'état actuel de chaque fil devient un fait citable « Fxx » (texte vérifié, preuves verbatim rattachées)."""
    out = {}
    idx = _claim_index()
    for f in fils or all_fils():
        pc = [p for p in f["preuves_actuel"] if p.get("repere") != "INTROUVABLE"]
        claims = [idx[(p["fichier"], p["repere"])]["id"] for p in pc if (p["fichier"], p["repere"]) in idx]
        srcs = list(dict.fromkeys(idx[(p["fichier"], p["repere"])]["source"] for p in pc if (p["fichier"], p["repere"]) in idx))
        out[f["id"]] = {"id": f["id"], "date": kb.baseline()["baseline_au"][:10], "type": "fait", "origine": "etat_actuel",
                        "texte": f"ÉTAT ACTUEL — {f['titre']} : {f['actuel']}", "source": srcs[0] if srcs else "mémoire NOVA",
                        "sources": srcs, "claims": claims, "fichier": pc[0]["fichier"] if pc else "", "repere": pc[0]["repere"] if pc else "",
                        "autorite": 1, "perime": "", "statut": "baseline", "sujets": [f["sujet"]], "fil": f["id"]}
    return out


def temporal_labels(fils: list[dict]) -> dict[str, str]:
    """claim id -> étiquette temporelle à afficher au modèle (ACTUEL / HISTORIQUE / CONTREDIT...)."""
    out = {}
    for f in fils:
        for e in f["entrees"]:
            if e.get("claim") and e["claim"] not in out:
                lab = ROLE_LABEL.get(e["role"], e["role"].upper())
                out[e["claim"]] = f"[{f['id']} · {lab}{(' — ' + e['note'][:140]) if e['note'] else ''}]"
    return out


def passe_ids(fils: list[dict]) -> set[str]:
    return {e["claim"] for f in fils for e in f["entrees"] if e.get("claim") and e["role"] in PASSE}


ACTIONS_Q = re.compile(r"action|engagement|prochaines? [ée]tapes?|[àa] faire|que faire|reste[ -][àa]|non compl[ée]t|pas (encore )?compl[ée]t|toujours pas|en suspens", re.I)


def intentions(question: str) -> set[str]:
    out = set()
    if CONTRADICTION_Q.search(question):
        out.add("contradictions")
    if fenetre(question):
        out.add("fenetre")
    if ACTIONS_Q.search(question):
        out.add("actions")
    if REPRISE_Q.search(question):
        out.add("reprise")
    if RISQUE_Q.search(question):
        out.add("risques")
    return out


def select(question: str, k: int = 3) -> list[str]:
    """Fils pertinents: mots-clés et identifiants d'abord (précis), intentions générales ensuite, BM25 seulement en dernier recours."""
    fils = all_fils()
    docs = [f"{f['titre']} {f['actuel']} " + " ".join(e["texte"] + " " + e["extrait"] for e in f["entrees"]) for f in fils]
    scores = dict(zip((f["id"] for f in fils), retrieval.bm25(question, docs)))
    ids = kb.tokens(question)
    precis = [f["id"] for f in fils if f["regex"].search(question) or (ids and ids & kb.tokens(f["actuel"]))]
    precis.sort(key=lambda fid: -scores[fid])
    intent = intentions(question)
    choisis = precis[:k]
    if "reprise" in intent:
        choisis = ["F03", "F01", "F09", "F13", "F04"] + choisis
    if "risques" in intent:
        choisis = ["F09", "F05", "F06", "F07", "F04"] + choisis
    if "actions" in intent:
        choisis = ["F13"] + choisis
    if "contradictions" in intent and not precis:
        choisis += [f["id"] for f in fils if f["resolutions"]]
    if "fenetre" in intent:
        a, b = fenetre(question)
        touches = sorted(fils, key=lambda f: -sum(a <= e["date"] <= b for e in f["entrees"]))
        choisis += [f["id"] for f in touches if any(a <= e["date"] <= b for e in f["entrees"])]
    if not choisis:  # aucun mot-clé: BM25, mais seulement les fils nettement pertinents
        best = sorted(scores.items(), key=lambda x: -x[1])
        choisis = [fid for fid, sc in best[:2] if sc > 0 and sc >= 0.6 * best[0][1]]
    return list(dict.fromkeys(choisis))[:6]


def fenetre(question: str) -> tuple[str, str] | None:
    """« Qu'est-ce qui a changé depuis la semaine dernière? » -> (début, fin) relatifs à la date de référence."""
    ref = date.fromisoformat(kb.baseline()["baseline_au"][:10])
    m = DEPUIS_Q.search(question)
    if m:
        return date(ref.year, MOIS[m.group(2).lower()], int(m.group(1))).isoformat(), ref.isoformat()
    if FENETRE_Q.search(question):
        return (ref - timedelta(days=7)).isoformat(), ref.isoformat()
    return None


def _src(e: dict) -> dict:
    return {"fichier": e["fichier"], "repere": e.get("repere", ""), "anchor": e.get("anchor", ""), "extrait": e.get("extrait", ""),
            "court": memory_short(e["fichier"]) + (f", {e['repere']}" if e.get("repere") and e["repere"] != "document" else "")}


def evolution(question: str, choisis: list[str]) -> list[dict]:
    """Sections structurées « évolution » pour la réponse, assemblées par le code selon l'intention de la question.
    Chaque section: {titre, actuel, entrees: [{date, heure, role, label, qui, texte, note, source}]}."""
    intent = intentions(question)
    by = {f["id"]: f for f in all_fils()}
    out = []
    if "fenetre" in intent:
        a, b = fenetre(question)
        ev = [{"date": t["date"], "heure": t["heure"], "role": t["nature"], "label": ROLE_LABEL.get(t["nature"], t["nature"]),
               "qui": t["acteur"], "texte": t["evenement"], "note": "", "source": _src(t["preuves"][0])} for t in evenements(a, b)]
        out.append({"titre": f"Ce qui a changé du {a} au {b} (date de référence : {b})", "actuel": "", "entrees": ev})
    if "contradictions" in intent:
        m = memory.load_memory()
        for c in m["contradictions"]:
            n = len(c["affirmations"])
            ev = [{"date": x["date"], "heure": "", "role": "retenu" if i == n - 1 else "écarté",
                   "label": "RETENU" if i == n - 1 else "CONTREDIT (écarté)", "qui": x["autorite"], "texte": x["texte"],
                   "note": "", "source": _src(x["preuve"])} for i, x in enumerate(c["affirmations"])]
            out.append({"titre": f"Contradiction : {c['sujet']}", "actuel": f"Résolution ({c['regle']}) : {c['resolution']}", "entrees": ev})
    for fid in choisis:
        f = by[fid]
        if ("contradictions" in intent and not f["entrees"]) or (fid == "F13"):
            out.append({"titre": f["titre"], "actuel": f["actuel"], "entrees": []})
            continue
        if "fenetre" in intent or "contradictions" in intent:
            continue  # déjà couvert par la vue chronologique ou par la liste des contradictions
        ev = [{"date": e["date"], "heure": e["heure"], "role": e["role"], "label": ROLE_LABEL.get(e["role"], e["role"]),
               "qui": e["qui"], "texte": e["texte"], "note": e["note"] if e["role"] in PASSE else "", "source": _src(e)}
              for e in f["entrees"]]
        out.append({"titre": f["titre"], "actuel": f["actuel"], "entrees": ev})
    return out


def evolution_text(sections: list[dict]) -> str:
    L = []
    for sec in sections:
        L.append(f"\n▸ {sec['titre']}" + (f"\n  {sec['actuel']}" if sec["actuel"] else ""))
        for e in sec["entrees"]:
            quand = e["date"] + (f" {e['heure']}" if e["heure"] else "")
            L.append(f"  • {quand} · {e['label']} · {(e['qui'] + ' : ') if e['qui'] else ''}{e['texte']} [{e['source']['court']}]"
                     + (f"\n      → {e['note']}" if e["note"] else ""))
    return "\n".join(L).strip("\n")


def evenements(debut: str, fin: str) -> list[dict]:
    m = memory.load_memory()
    return [t for t in m["timeline"] if debut <= t["date"] <= fin]


def memory_short(fichier: str) -> str:
    from .server import short  # même étiquette courte que les pages (M04, E05, SEC-210...)
    return short(fichier)
