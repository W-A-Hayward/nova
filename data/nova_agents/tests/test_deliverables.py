"""Test sans Ollama des livrables du README (data/starter/README.txt).

Vérifie que ce que voit le jury est ancré dans le dossier et cohérent avec les règles de lecture:
extraits cités retrouvés mot pour mot, montants calculés, transcription du runbook, contradictions dans un plan
et un registre, actions avec échéance « à confirmer », garde-fous de la mise à jour, baseline intacte, export autonome.
Usage: python tests/test_deliverables.py
"""
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import evidence, kb, memory, updates  # noqa: E402

DATA = ROOT / "data"
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
BASE_FILES = [DATA / "memory.json", DATA / "answers_baseline.json"]
before = {p: digest(p) for p in BASE_FILES}

# ------------------------------------------------------------------ 1) chaque preuve existe et l'extrait est dans le fichier
answers = json.loads((DATA / "answers_baseline.json").read_text(encoding="utf-8"))
assert sorted(answers) == [f"Q{i:02d}" for i in range(1, 11)]
for qid, q in answers.items():
    assert q["reponse"] and q["nuance"] and len(q["sources"]) >= 2, qid
    assert len({s["fichier"] for s in q["sources"]}) >= 2, f"{qid}: au moins deux fichiers distincts"
    for s in q["sources"]:
        assert evidence.locate(s["fichier"], s["extrait"]), f"{qid}: extrait introuvable dans {s['fichier']}: {s['extrait']}"
        assert s["repere"] and s["repere"] != "document", f"{qid}: repère humain imprécis"


def walk(o):
    if isinstance(o, dict):
        if "fichier" in o and "extrait" in o:
            yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


mem = memory.build_memory()
refs = list(walk(mem))
assert len(refs) > 100, len(refs)
for r in refs:
    assert r["repere"] != "INTROUVABLE", f"mémoire: extrait introuvable dans {r['fichier']}: {r['extrait']}"
assert json.loads((DATA / "memory.json").read_text(encoding="utf-8")) == json.loads(json.dumps(mem, ensure_ascii=False)), \
    "data/memory.json n'est pas à jour: python -m app.memory"
print(f"1) {sum(len(q['sources']) for q in answers.values())} preuves Q et {len(refs)} preuves de mémoire retrouvées dans le dossier OK")

# ------------------------------------------------------------------ 2) faits clés (erreurs corrigées)
txt = lambda q: (answers[q]["reponse"] + " " + answers[q]["nuance"])
assert "10 septembre" in txt("Q01") and "22 octobre" in txt("Q01")
assert "Julien Moreau" in txt("Q03") and "8 septembre" in txt("Q03") and "10 septembre" in txt("Q03")
assert "R-01" in txt("Q02") and "Ouvert" in txt("Q02")
assert "26 août" in txt("Q07") and "M03" in txt("Q07") and "2026-08-09" not in txt("Q07")
assert "environnement de validation" in txt("Q08") and "en production" not in answers["Q08"]["reponse"].replace("pas en production", "")
assert "204 000" in txt("Q05") and "18 000" in txt("Q06")
assert "retour arrière" in txt("Q10") and "Validation fonctionnelle post-déploiement" in txt("Q10")
runbook = next(c for c in kb.load_claims() if c["fichier"].endswith("OPS-601_runbook.png"))["texte"]
assert "Procédure de retour arrière — TODO" in runbook and "Validation fonctionnelle post-déploiement — À compléter" in runbook
assert "Vérifier INT-101" not in runbook, "ancienne transcription inventée"
print("2) faits clés Q01–Q10 et transcription du runbook OK")

# ------------------------------------------------------------------ 3) mémoire: contradictions, actions, natures
types = {c["type"] for c in mem["contradictions"]}
assert {"plan", "registre de risques"} <= types, types
assert all(c["resolution"] and len(c["affirmations"]) >= 2 for c in mem["contradictions"])
assert {"proposition", "décision", "validation", "livraison", "signal"} <= {t["nature"] for t in mem["timeline"]}
for a in mem["actions"]:
    assert a["echeance"] and (re.search(r"\d", a["echeance"]) or "à confirmer" in a["echeance"]), a["id"]
    assert a["nature"] in ("engagement documenté", "recommandation équipe"), a["id"]
    assert a["executant"] and a["preuves"], a["id"]
assert {c["id"] for c in mem["conditions"]} == {"C1", "C2", "C3"} and all(c["actions"] for c in mem["conditions"])
assert [c["statut_ticket"] for c in mem["conditions"]] == ["EN VALIDATION", "OUVERT", "OUVERT"]
print("3) mémoire: contradictions plan/registre, natures, actions et échéances OK")

# ------------------------------------------------------------------ 4) pages: brief d'une page, montants, rien d'inventé
from fastapi.testclient import TestClient  # noqa: E402
from app import server  # noqa: E402

c = TestClient(server.app)
brief = c.get("/brief").text.replace("\u202f", " ").replace("\u00a0", " ")  # montants affichés avec espaces insécables
for m in ("204 000 $", "186 000 $", "132 000 $", "18 000 $", "Nicolas Perron", "16 septembre 2026", "22 octobre 2026"):
    assert m in brief, m
for bad in ("50 MB", "24k$", "notifications push", "Tous les modules en production", "livré en production"):
    assert bad not in brief, bad
texte_brief = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<style>.*?</style>", "", brief))  # sans le CSS embarqué
assert len(texte_brief.split()) < 900, "le brief doit tenir sur une page"
for route in ("/", "/memoire", "/reponses", "/mise-a-jour", "/sources", "/guide", "/chat", "/ingest",
              "/source/03_Tickets/OPS-601_runbook.png", "/raw/03_Tickets/OPS-601_runbook.png"):
    assert c.get(route).status_code == 200, route
assert c.get("/raw/../app/server.py").status_code == 404
srcs = c.get("/sources").text
assert "id=recherche" in srcs and "id=catalogue" in srcs and "const D=" in srcs, "recherche intégrée à /sources"
r = c.get("/recherche?q=INV-003", follow_redirects=False)
assert r.status_code in (302, 307) and r.headers["location"].startswith("/sources?q=INV-003")
print("4) pages et brief OK")

# ------------------------------------------------------------------ 5) mise à jour: garde-fous et baseline intacte
updates.UPDATES = Path(tempfile.mkdtemp()) / "updates"  # isolé: les mises à jour réelles de data/updates/ ne comptent pas ici
cur = updates.apply(memory.load_memory(), updates.load(ROOT / "tests" / "fixtures"))
u = cur["mises_a_jour"][0]
assert cur["date_approuvee"]["valeur"] == "22 octobre 2026", "une proposition du fournisseur ne remplace pas la décision"
assert cur["date_approuvee"]["propositions"][0]["valeur"] == "29 octobre 2026"
assert [x["statut_ticket"] for x in cur["conditions"]] == ["EN VALIDATION", "OUVERT", "OUVERT"], "aucune condition fermée"
assert any("retenu comme proposition" in w for w in u["_avertissements"])
assert any(x.startswith("C1") for x in u["_inchanges"])
html = c.get("/mise-a-jour?exercice=1").text
assert "EXERCICE FICTIF" in html and "Ce qui n'a PAS changé" in html
with tempfile.TemporaryDirectory() as d:  # un extrait inventé est écarté
    bad = json.loads((ROOT / "tests/fixtures/U01_exercice.json").read_text(encoding="utf-8"))
    bad["changements"] = [{"champ": "condition:C1", "nouveau": "SEC-210 accepté", "statut": "validé", "par": "Sophie Lambert",
                           "preuve": "Sophie : SEC-210 est accepté."}]
    (Path(d) / "docs").mkdir()
    (Path(d) / "docs" / "EXERCICE_E13_Report_ACC303.eml").write_bytes((ROOT / "tests/fixtures/docs/EXERCICE_E13_Report_ACC303.eml").read_bytes())
    (Path(d) / "U01_x.json").write_text(json.dumps(bad), encoding="utf-8")
    cur = updates.apply(memory.load_memory(), updates.load(Path(d)))
    assert cur["conditions"][0]["statut_ticket"] == "EN VALIDATION" and not cur["mises_a_jour"][0]["changements"]
assert {p: digest(p) for p in BASE_FILES} == before, "la baseline a été modifiée"
print("5) mise à jour: proposition ≠ décision, conditions non fermées, extrait inventé écarté, baseline intacte OK")

# ------------------------------------------------------------------ 6) export autonome
import subprocess  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_static.py"), d], check=True, capture_output=True)
    out = Path(d)
    broken = []
    for f in out.glob("*.html"):
        for h in re.findall(r"href=['\"]([^'\"#$][^'\"]*)['\"]", f.read_text(encoding="utf-8")):
            if not h.startswith("http") and not (out / h.split("#")[0]).exists():
                broken.append((f.name, h))
    assert not broken, broken[:5]
    assert (out / "index.html").exists() and (out / "raw" / "03_Tickets" / "OPS-601_runbook.png").exists()
print("6) export statique: liens valides OK")
print("TOUS LES TESTS DES LIVRABLES OK")
