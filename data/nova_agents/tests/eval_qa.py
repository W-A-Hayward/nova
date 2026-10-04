"""Évaluation avec le vrai Ollama: Q01-Q10 de la baseline + questions-pièges sans réponse dans le dossier.

Mesures automatiques (en plus de l'affichage obtenu / référence):
- rappel des éléments clés de la réponse de référence (mots-clés choisis à la main ci-dessous);
- entités inventées: montants / dates / identifiants / personnes absents de TOUTE la base (hallucination nette);
- contradictions de statut (« livré ≠ validé », go-live « garanti »);
- abstention sur les questions-pièges (la bonne réponse est « inconnu », pas une invention).
Usage: python tests/eval_qa.py [--quiet]    -> écrit tests/eval_results.json
"""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import kb, verify
from app.chat_graph import ask

CLES = {  # alternatives séparées par « | » ; comparaison sans accents ni casse
    "Q01": ["22 oct", "condition", "SEC-210", "ACC-303", "runbook|rollback|retour arriere"],
    "Q02": ["INT-101", "17 sept", "propos", "R-01|registre"],
    "Q03": ["8 sept", "10 sept", "propos", "comite"],
    "Q04": ["Nicolas", "16 sept", "Elodie"],
    "Q05": ["204 000|204000", "180 000|180000", "24 000|24000", "CR-04"],
    "Q06": ["18 000|18000", "CR-04", "54 000|54000", "36 000|36000"],
    "Q07": ["Canada Central", "ADR-007", "26 aout|27 aout|migration"],
    "Q08": ["SEC-210", "pas|non", "deploy", "Sophie"],
    "Q09": ["ACC-303", "ACC-301", "ACC-302", "ouvert"],
    "Q10": ["SEC-210", "ACC-303", "rollback|retour arriere", "post-deploiement|validation fonctionnelle|etape 5"],
}
# Raisonnement temporel: la 1re phrase donne l'état actuel; l'historique / les sources contredites sont exposés.
ACTUEL = {"Q01": "22 oct", "Q02": "INT-101|connecteur", "Q03": "10 sept|comite", "Q04": "Nicolas", "Q05": "204", "Q06": "18 000|18000|CR-04",
          "Q07": "Canada Central", "Q08": "pas|non|n'est", "Q09": "pas|non|ACC-303", "Q10": "SEC-210|condition"}
HISTO = {"Q01": "15 oct", "Q02": "R-01|registre", "Q03": "propos", "Q07": "East US", "Q08": "regle|vert", "Q09": "conforme|vert"}
CONSIGNES = [  # exemples de questions des consignes, avec éléments attendus dans la réponse complète
    ("Quelle est la date de livraison actuellement prévue et pourquoi?", ["22 oct", "INT-101|connecteur", "15 oct"]),
    ("Quelles décisions ont été prises concernant le fournisseur?", ["CR-04", "CR-01"]),
    ("Quels engagements ne sont toujours pas complétés?", ["SEC-210", "ACC-303", "runbook", "a confirmer"]),
    ("Existe-t-il des informations contradictoires?", ["Plan projet v3", "Registre", "15 oct"]),
    ("Quels sont les trois principaux risques du projet aujourd'hui?", ["SEC-210", "ACC-303", "runbook|OPS-601"]),
    ("Pourquoi la date a-t-elle été déplacée au 22 octobre?", ["connecteur|INT-101", "propos"]),
    ("Qu'est-ce qui a changé depuis la semaine dernière?", ["CR-04", "2026-09-26", "OPS-601|runbook"]),
    ("Si je devais reprendre le projet demain matin, que devrais-je savoir?", ["Nicolas", "22 oct", "SEC-210", "204 000"]),
]
PIEGES = [
    "Quel est le budget prévu pour la phase 2?",
    "Quelle est la date exacte du re-test de SEC-210 et son résultat?",
    "Qui est le responsable de la protection des données (DPO) du projet NOVA?",
    "Combien a coûté le projet ORION?",
]
ABSTENTION = re.compile(r"je ne trouve pas|inconnu|pas documente|aucune? (date|information|document|montant|budget)|non precise|"
                        r"ne (precise|mentionne|dit) pas|pas d'information|n'est pas (connu|indique)|ce qu'on ne sait pas")


def corpus() -> str:
    return "\n".join(f"{c['date']} {c['texte']}" for c in kb.load_claims()) + "\n" + kb.finance_summary()


def _has(alts: str, text: str) -> bool:
    return any(verify.norm(a) in verify.norm(text) for a in alts.split("|"))


def evaluer(question: str, cles: list[str] | None, qid: str = "") -> dict:
    t0 = time.time()
    r = ask(question)
    courte = r["reponse_courte"].split("\n\nConfiance")[0]  # partie rédigée par le LLM (l'évolution est assemblée par le code)
    n = verify.norm(r["reponse"])
    out = {"question": question, "reponse": r["reponse"], "sujets": r["sujets"], "fils": r.get("fils", []),
           "secondes": round(time.time() - t0, 1),
           "inventes": verify.missing(courte, corpus()), "statut": verify.status_conflicts(courte),
           "rejetees": sum(len(e["retirees"]) for e in r["experts"]), "tentatives_synthese": r["tentatives_synthese"]}
    if cles is not None:
        trouves = [k for k in cles if any(verify.norm(alt) in n for alt in k.split("|"))]
        out["rappel"] = round(len(trouves) / len(cles), 2)
        out["manquants"] = [k for k in cles if k not in trouves]
    else:
        out["abstention"] = bool(ABSTENTION.search(verify.norm(courte)))
    premiere = (verify.sentences(courte) or [""])[0]
    if qid in ACTUEL:
        out["actuel_en_premier"] = _has(ACTUEL[qid], premiere)
    if qid in HISTO:
        out["historique_expose"] = _has(HISTO[qid], r["reponse"].split("Évolution et sources contradictoires")[-1])
    return out


def questions() -> list[tuple[str, str]]:
    from app import corpus
    text = corpus.BRIEF.read_text(encoding="utf-8")
    return re.findall(r"^(Q\d+)\.\s+(.+)$", text, re.M)


if __name__ == "__main__":
    quiet = "--quiet" in sys.argv
    res = []
    for qid, question in questions():
        e = evaluer(question, CLES.get(qid), qid)
        e["id"] = qid
        res.append(e)
        if not quiet:
            print(f"\n=== {qid} {question}\n--- OBTENU ({', '.join(e['sujets'])}):\n{e['reponse']}")
        print(f"[{qid}] rappel={e['rappel']} manquants={e['manquants']} actuel_en_premier={e.get('actuel_en_premier')} "
              f"historique={e.get('historique_expose', '-')} inventés={e['inventes']} statut={e['statut']} rejetées={e['rejetees']} ({e['secondes']} s)")
    for i, (q, cles) in enumerate(CONSIGNES, 1):
        e = evaluer(q, cles)
        e["id"] = f"C{i:02d}"
        res.append(e)
        if not quiet:
            print(f"\n=== CONSIGNE {q}\n{e['reponse']}")
        print(f"[{e['id']}] rappel={e['rappel']} manquants={e['manquants']} fils={e['fils']} inventés={e['inventes']} ({e['secondes']} s)")
    for i, p in enumerate(PIEGES, 1):
        e = evaluer(p, None)
        e["id"] = f"P{i:02d}"
        res.append(e)
        if not quiet:
            print(f"\n=== PIÈGE {p}\n{e['reponse']}")
        print(f"[{e['id']}] abstention={e['abstention']} inventés={e['inventes']}")
    qa = [r for r in res if "rappel" in r]
    pg = [r for r in res if "abstention" in r]
    resume = {"rappel_moyen": round(sum(r["rappel"] for r in qa) / len(qa), 2),
              "reponses_avec_entite_inventee": sum(bool(r["inventes"]) for r in res),
              "reponses_avec_contradiction_de_statut": sum(bool(r["statut"]) for r in res),
              "abstentions_correctes": f"{sum(r['abstention'] and not r['inventes'] for r in pg)}/{len(pg)}",
              "actuel_en_premier": f"{sum(bool(r.get('actuel_en_premier')) for r in qa if 'actuel_en_premier' in r)}/{sum('actuel_en_premier' in r for r in qa)}",
              "historique_expose": f"{sum(bool(r.get('historique_expose')) for r in res if 'historique_expose' in r)}/{sum('historique_expose' in r for r in res)}",
              "secondes_moyennes": round(sum(r["secondes"] for r in res) / len(res), 1)}
    print("\nRÉSUMÉ:", json.dumps(resume, ensure_ascii=False))
    (Path(__file__).parent / "eval_results.json").write_text(json.dumps({"resume": resume, "details": res}, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
