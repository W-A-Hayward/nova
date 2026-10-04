"""Test sans Ollama du raisonnement temporel du chat (app/fils.py + chat_graph).

Vérifie: état actuel tranché par date du fait + autorité (pas par date de fichier), positions passées gardées et
étiquetées (historique, contredit, proposition...), garde-fou « historique présenté comme actuel », sélection des fils
pour les questions des consignes, vues « contradictions » et « ce qui a changé », prise en compte des mises à jour.
Usage: python tests/test_chat_reasoning.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import fils, kb, llm, updates, verify  # noqa: E402

CL = kb.claims_by_id()
role = lambda fid, mot: [e for e in fils.get(fid)["entrees"] if mot in e["fichier"]]

# ------------------------------------------------------------------ 1) l'ordre n'est plus un statut de vérité
rendu = kb.render(list(CL.values())[:5])
assert "VÉRITÉ ACTUELLE" not in rendu, "le premier fait de la liste ne doit plus être déclaré « vérité actuelle »"
print("1) rendu sans marqueur positionnel OK")

# ------------------------------------------------------------------ 2) fils: actuel tranché, passé gardé et étiqueté
for f in fils.all_fils():
    assert f["actuel"], f["id"]
    assert all(p["repere"] != "INTROUVABLE" for p in f["preuves_actuel"]), f["id"]
    dates = [e["date"] for e in f["entrees"] if e["date"][:1].isdigit()]
    assert dates == sorted(dates), f"{f['id']}: chronologie non ordonnée"
assert "22 octobre 2026" in fils.get("F01")["actuel"] and "10 septembre" in fils.get("F01")["actuel"]
assert [e["role"] for e in role("F01", "M01_")] == ["historique"]                       # 15 octobre remplacé
assert [e["role"] for e in role("F01", "Plan_Projet_NOVA_v3")] == ["écarté"]            # plan PLUS RÉCENT que la décision, mais écarté
assert [e["role"] for e in role("F01", "Notes_personnelles")] == ["signal"]             # source non fiable
assert "retenu" in [e["role"] for e in role("F01", "M04_")]
plan, dec = role("F01", "Plan_Projet_NOVA_v3")[0], role("F01", "M04_")[0]
assert plan["date"] > dec["date"], "piège du README: le document le plus récent n'est pas l'état actuel"
reg = role("F08", "Registre_Risques")[0]
assert reg["role"] == "écarté" and reg["date"] == "2026-09-29" and "INT-101" in fils.get("F08")["actuel"]
assert {e["role"] for e in role("F05", "E08_")} == {"livraison"} and "écarté" in [e["role"] for e in role("F05", "SEC-210.txt")]
assert "Étape 4" in fils.pseudo_claims()["F07"]["texte"] or "étape 4" in fils.pseudo_claims()["F07"]["texte"]
print("2) fils: état actuel, historique, contredit (plan v3, registre R-01), livraison ≠ validation OK")

# ------------------------------------------------------------------ 3) sélection des fils et intentions (questions des consignes)
attendu = {
    "Quelle est la date de livraison actuellement prévue et pourquoi?": "F01",
    "La sécurité est-elle acceptée?": "F05",
    "Où les données de production doivent-elles être hébergées?": "F02",
    "Quel problème présente INV-003?": "F04",
    "Qui est responsable du projet et depuis quand?": "F03",
    "Quelles sont les trois conditions de go-live?": "F09",
    "Le runbook est-il prêt?": "F07",
    "Quels engagements ne sont toujours pas complétés?": "F13",
    "Quelles décisions ont été prises concernant le fournisseur?": "F04",
}
for q, fid in attendu.items():
    assert fils.select(q)[:1] == [fid], (q, fils.select(q))
assert set(fils.select("Si je devais reprendre le projet demain matin, que devrais-je savoir?")) >= {"F01", "F03", "F09", "F13"}
assert set(fils.select("Quels sont les trois principaux risques du projet aujourd'hui?")) >= {"F05", "F06", "F07"}
contra = fils.evolution("Existe-t-il des informations contradictoires?", fils.select("Existe-t-il des informations contradictoires?"))
assert sum(s["titre"].startswith("Contradiction") for s in contra) == 9
assert any("Plan projet v3" in s["titre"] for s in contra) and any("Registre des risques" in s["titre"] for s in contra)
q = "Qu'est-ce qui a changé depuis la semaine dernière?"
assert fils.fenetre(q) == ("2026-09-23", "2026-09-30")
vue = fils.evolution(q, fils.select(q))[0]
assert vue["entrees"] and all("2026-09-23" <= e["date"] <= "2026-09-30" for e in vue["entrees"])
assert fils.fenetre("Qu'est-ce qui a changé depuis le 15 septembre?") == ("2026-09-15", "2026-09-30")
print("3) sélection des fils, vues contradictions et « ce qui a changé » OK")

# ------------------------------------------------------------------ 4) garde-fou: une position passée présentée comme actuelle
from app.chat_graph import pinned_evidence  # noqa: E402

pins = pinned_evidence(["F01"], "gouvernance")
assert pins[0]["id"] == "F01" and pins[0]["origine"] == "etat_actuel"
m01 = next(p for p in pins if p.get("fichier", "").endswith("M01_CR_Demarrage_07juillet.txt"))
assert "HISTORIQUE" in m01["etiquette"] and m01["passe"]
assert "HISTORIQUE" in kb.render([m01])
allowed = {p["id"]: p for p in pins}
r = verify.check_affirmation({"texte": "La date de mise en production est le 15 octobre 2026.", "preuves": [m01["id"]]}, allowed)
assert any("périmés" in x for x in r["problemes"]), r
r = verify.check_affirmation({"texte": "Initialement, la mise en production était prévue le 15 octobre 2026.", "preuves": [m01["id"]]}, allowed)
assert not r["problemes"], r
r = verify.check_affirmation({"texte": "La date approuvée est le 22 octobre 2026.", "preuves": ["F01"]}, allowed)
assert not r["problemes"], r
print("4) faits épinglés et garde-fou « historique présenté comme actuel » OK")

# ------------------------------------------------------------------ 5) chat complet avec un faux LLM
M01 = m01["id"]


def fake_json(prompt, system="", tag="", validate=None, default=None, retries=2):
    if tag.startswith("expert"):
        assert "[F01]" in prompt and "HISTORIQUE" in prompt, "l'expert doit voir l'état actuel et les positions étiquetées"
        return {"hors_domaine": False, "affirmations": [
            {"texte": "La date de mise en production est le 15 octobre 2026.", "preuves": [M01]},
            {"texte": "La date approuvée est le 22 octobre 2026, conditionnelle à trois éléments.", "preuves": ["F01"]},
            {"texte": "La date approuvée est le 22 octobre 2026, conditionnelle à trois éléments!", "preuves": ["F01"]}], "inconnu": []}
    if tag == "verify":
        return {"verdicts": [{"i": i, "verdict": "SUPPORTE", "raison": ""} for i in range(prompt.count("AFFIRMATION:"))]}
    return default if not tag.startswith("revision") else {"affirmations": []}


llm.ask_json = fake_json
llm.ask_text = lambda prompt, system="", tag="": "La réponse finale est : La date approuvée est le 22 octobre 2026, conditionnelle à trois éléments [F01]."
from app.chat_graph import ask  # noqa: E402

r = ask("Quelle est la date de mise en production actuellement prévue?")
assert r["fils"] == ["F01"] and r["sujets"] == ["gouvernance"]
assert r["reponse_courte"].startswith("La date approuvée est le 22 octobre 2026"), r["reponse_courte"]   # préambule retiré
assert "[état actuel F01]" in r["reponse_courte"] and "15 octobre" not in r["reponse_courte"]
assert r["reponse"].index("Réponse (état au") < r["reponse"].index("Évolution et sources contradictoires")
evo = r["evolution"][0]["entrees"]
assert [e["role"] for e in evo if "M01_" in e["source"]["fichier"]] == ["historique"]
assert sum(len(e["affirmations"]) for e in r["experts"]) == 2   # le quasi-doublon reste dans l'expert...
assert r["reponse_courte"].count("22 octobre") == 1             # ... mais n'est pas répété dans la réponse
assert any(p["fichier"].endswith("M04_Transcript_Comite_direction_10sept.txt") for p in r["preuves"]), "Fxx renvoie à ses preuves"
print("5) chat: état actuel d'abord, historique rejeté comme actuel mais exposé dans l'évolution OK")

# ------------------------------------------------------------------ 6) une mise à jour s'ajoute au fil sans remplacer la décision
_load = updates.load
updates.load = lambda folder=None: _load(ROOT / "tests" / "fixtures")
try:
    f01 = fils.get("F01")
    assert any(e["role"] == "mise à jour" and "29 octobre" in e["texte"] for e in f01["entrees"])
    assert f01["actuel"].startswith("Date approuvée : 22 octobre 2026") and "proposition non approuvée : 29 octobre" in f01["actuel"]
    assert any(e["role"] == "mise à jour" for e in fils.get("F06")["entrees"])
finally:
    updates.load = _load
assert not any(e["role"] == "mise à jour" for e in fils.get("F01")["entrees"])
print("6) mise à jour: nouvelle proposition dans le fil, décision antérieure conservée OK")
print("TOUS LES TESTS DU RAISONNEMENT DU CHAT OK")
