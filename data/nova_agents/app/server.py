"""Interface web: / rapport | /brief | /memoire | /reponses | /chat | /ingest"""
import html
import json
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from . import corpus, kb, memory
from .chat_graph import ask
from .ingest_graph import ingest

app = FastAPI(title="NOVA")

def load_answers():
    """Load frozen Q01-Q10 answers."""
    answers_file = Path(__file__).resolve().parent.parent / "data" / "answers_baseline.json"
    if answers_file.exists():
        return json.loads(answers_file.read_text(encoding="utf-8"))
    return {}
e = html.escape
CSS = """body{font:15px/1.45 system-ui,sans-serif;margin:0;color:#1b1b1b;background:#f9f9f9}
header{background:#183760;padding:10px 20px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}
header a{color:#fff;margin-right:16px;text-decoration:none;font-weight:600}header a:hover{opacity:0.8}
main{padding:14px 20px;max-width:1100px;margin:0 auto}
table{border-collapse:collapse;width:100%;margin-bottom:14px;background:#fff}
td,th{border:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}
th{background:#eef2f7;font-weight:600}
pre{white-space:pre-wrap;background:#f6f7f9;padding:10px;border-radius:6px;overflow-x:auto}
textarea,input[type=text]{width:100%;padding:8px;box-sizing:border-box;border:1px solid #ddd;border-radius:4px}
button{padding:8px 16px;margin-top:8px;background:#183760;color:#fff;border:none;border-radius:4px;cursor:pointer}
button:hover{background:#0d1f3c}
.warn{color:#9b1c1c}.ok{color:#007a1f}.todo{color:#d97706}
.card{background:#fff;padding:12px;margin:8px 0;border-left:4px solid #183760;border-radius:4px}
.brief-section{page-break-inside:avoid;margin-bottom:16px}
@media print{body{max-width:100%}header{background:#183760;color:#fff}main{padding:0}}"""


def page(body: str) -> str:
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>NOVA</title><style>{CSS}</style>
<header><a href="/">Rapport</a><a href="/brief">Brief</a><a href="/memoire">Mémoire</a><a href="/reponses">Réponses Q</a><a href="/chat">Chat</a><a href="/ingest">Ajouter</a></header><main>{body}</main>"""


def table(head, rows):
    return "<table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" + "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows) + "</table>"


@app.get("/", response_class=HTMLResponse)
def rapport():
    ledger = kb.ledger()
    claims = kb.load_claims()
    docs = [d for d in corpus.documents() if d["pertinence"] not in kb.EXCLUS and not d.get("doublon_de")]
    b = ("<h2>Rapport du projet NOVA</h2><p>Dossier lu dans Projet360_NOVA_ETUDIANTS, référence "
         + e(kb.ref_date()) + ". Les lignes « à valider » viennent de fichiers ajoutés ensuite.</p>")
    b += "<h3>Décisions</h3>" + table(["Date", "Décision", "Source", "Fichier", "Statut", "Avertissement"],
                                      [(c["date"], c["texte"], c["source"], c.get("fichier", ""), c.get("statut"), c.get("perime", ""))
                                       for c in claims if c["type"] == "décision" and c.get("origine") in ("decision", "ingestion")])
    b += "<h3>Budget (calculé par le code, à partir des PDF)</h3><pre>" + e(kb.finance_summary()) + "</pre>"
    b += "<h3>Factures</h3>" + table(["Facture", "Date", "Statut", "Total", "Lignes"],
                                     [(f["id"], f["date"], f["statut"], sum(l["montant"] for l in f["lignes"]),
                                       " | ".join(f"{l['desc']} {l['montant']}" for l in f["lignes"])) for f in ledger["factures"]])
    b += "<h3>Statut des tickets (au " + e(kb.ref_date()) + ")</h3>" + table(
        ["Ticket", "Statut", "Source"], [(t, v["statut"], v["source"]) for t, v in sorted(kb.ticket_status().items())])
    b += "<h3>Sources du dossier</h3>" + table(
        ["ID", "Fichier", "Date", "Autorité", "Avertissement"],
        [(d["id"], d["fichier"], d["date"], kb.AUTORITE.get(d["autorite"], ""), d.get("perime", "")) for d in docs])
    b += "<h3>Ajouts depuis l'ingestion</h3>" + table(
        ["Date", "Type", "Texte", "Source", "Fichier"],
        [(c["date"], c["type"], c["texte"], c["source"], c.get("fichier", "")) for c in claims if c.get("origine") == "ingestion"])
    return page(b)


@app.get("/chat", response_class=HTMLResponse)
def chat_page():
    return page("""<h2>Chat</h2><input type=text id=q placeholder="Ex: Quelle est la date de production approuvée et pourquoi?" onkeydown="if(event.key=='Enter')go()">
<button onclick=go()>Demander</button><p id=meta></p><pre id=a></pre>
<details><summary>Preuves citées (faits de la base)</summary><pre id=p></pre></details>
<details><summary>Affirmations rejetées par la vérification</summary><pre id=x class=warn></pre></details>
<script>async function go(){a.textContent='...';meta.textContent='';p.textContent='';x.textContent='';
const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q.value})});const j=await r.json();
a.textContent=j.reponse;meta.textContent='Experts consultés: '+j.sujets.join(', ');
p.textContent=j.preuves.map(c=>'['+c.source+'] '+c.id+' — '+c.texte).join('\n')||'(aucune)';
x.textContent=j.rejetees.map(c=>'['+c.sujet+'] « '+c.texte+' » — '+c.problemes.join('; ')).join('\n')||'(aucune)'}</script>""")


class Q(BaseModel):
    question: str


@app.post("/api/chat")
def api_chat(q: Q):
    r = ask(q.question)
    rejetees = [{"sujet": x["sujet"], "texte": a["texte"], "problemes": a["problemes"]} for x in r["experts"] for a in x["retirees"]]
    return {"reponse": r["reponse"], "sujets": r["sujets"], "preuves": r["preuves"], "confiance": r["confiance"], "rejetees": rejetees}


@app.get("/brief", response_class=HTMLResponse)
def brief_page():
    """One-page operational brief (printable)."""
    memory_data = memory.load_memory()
    ledger = kb.ledger()
    autorise = ledger["contrat"] + sum(c["montant"] for c in ledger["changements"] if c["statut"] == "approuvé")
    facture = sum(sum(l["montant"] for l in f["lignes"]) for f in ledger["factures"])

    return page(f"""<h2 style="page-break-after:avoid">BRIEF NOVA — 30 septembre 2026 09h00</h2>
<div class="brief-section"><h3>1. Responsable et échéance</h3>
<p><strong>Responsable:</strong> Nicolas Perron (depuis 16 sept 2026)<br>
<strong>Date approuvée:</strong> 22 octobre 2026<br>
<strong>Réserves:</strong> Trois conditions de go-live (validation SEC-210, ACC-303, runbook).</p>
</div>

<div class="brief-section"><h3>2. Portée (Phase 1)</h3>
<p>SSO, création/suivi demandes, pièces jointes, workflow, tableau suivi, rapports standards.
Mobile: utilisable mais optimisations avancées (CR-04) reportées à phase 2.</p>
</div>

<div class="brief-section"><h3>3. Budget</h3>
<p>Autorisé: {autorise:,} $ (contrat 180k + CR-01 approuvé 24k)<br>
Facturé: {facture:,} $<br>
<strong>Problème:</strong> INV-003 inclut 18k$ CR-04 (non approuvé, phase 2) → doit être retiré.</p>
</div>

<div class="brief-section"><h3>4. Priorités immédiates (conditions go-live)</h3>
<ol>
<li><span class="todo">SEC-210</span> — Validation sécurité (audit log). Fix livré 19 sept, validation = <strong>Sophie Lambert</strong>, échéance: avant 22 oct.</li>
<li><span class="todo">ACC-303</span> — Modale clavier. Bloquant accessibilité, fermeture = <strong>Mélissa Gagnon/Boréal</strong>, échéance: avant 22 oct.</li>
<li><span class="todo">OPS-601</span> — Runbook complet (rollback + validation post-deploy). Olivier Côté demande procédure exécutable, échéance: avant 22 oct.</li>
</ol>
</div>

<div class="brief-section"><h3>5. État des risques</h3>
<p>INT-101 (connecteur) = fermé 17 sept ✓. Trois risques actifs bloquent go-live. Aucun autre problème technique identifié au 29 sept.</p>
</div>

<p style="font-size:12px;margin-top:20px;border-top:1px solid #ddd;padding-top:10px">
Baseline 30 sept 09:00 Montréal (UTC-04:00). Pour détails: /memoire (timeline/décisions/contradictions) et /reponses (Q01-Q10).
</p>""")


@app.get("/memoire", response_class=HTMLResponse)
def memoire_page():
    """Structured memory with timeline, decisions, contradictions, actions."""
    memory_data = memory.load_memory()
    return page(f"""<h2>Mémoire opérationnelle NOVA</h2>
<p><strong>Baseline:</strong> {e(memory_data['ref_date'])}</p>

<h3>Chronologie (13 événements clés)</h3>
<table>
<tr><th>Date</th><th>Événement</th><th>Type</th><th>Source</th><th>Détail</th></tr>
{chr(10).join(f"<tr><td>{e(d['date'])}</td><td>{e(d['event'])}</td><td>{e(d['type'])}</td><td>{e(d['source'])}</td><td>{e(d['detail'][:80])}</td></tr>" for d in memory_data['timeline'][:13])}
</table>

<h3>Décisions documentées (5)</h3>
{chr(10).join(f"<div class='card'><strong>{d['field']}</strong><br>
<em>Ancien:</em> {d['ancien']['valeur']} ({d['ancien']['source']})<br>
<em>Nouveau:</em> {d['nouveau']['valeur']} ({d['nouveau']['source']})<br>
<em>Résolution:</em> {d['resolution']}</div>" for d in memory_data['decisions'][:5])}

<h3>Contradictions résolues (2)</h3>
{chr(10).join(f"<div class='card'><strong>{c['domaine']}</strong><br>{c['resolution']}<br><em>Note:</em> {c['note']}</div>" for c in memory_data['contradictions'])}

<h3>Actions en cours (4)</h3>
<table>
<tr><th>Action</th><th>Responsable</th><th>Échéance</th><th>Statut</th></tr>
{chr(10).join(f"<tr><td>{e(a['action'][:40])}</td><td>{e(a['responsable'])}</td><td>{a['echéance']}</td><td><span class='todo'>{a['statut_courant']}</span></td></tr>" for a in memory_data['actions'][:4])}
</table>

<p style="font-size:12px;margin-top:20px"><em>Tous les éléments sont sourcés. Les recommandations de l'équipe sont clairement distinguées des engagements documentés.</em></p>""")


@app.get("/reponses", response_class=HTMLResponse)
def reponses_page():
    """Q01–Q10 answers with sources."""
    answers = load_answers()
    html_content = "<h2>Réponses aux 10 questions — Baseline 30 sept 2026</h2>"
    for qid in ["Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07", "Q08", "Q09", "Q10"]:
        if qid in answers:
            q = answers[qid]
            html_content += f"""<div class="card" style="border-left-color:#007a1f">
<h3>{qid}: {e(q['question'][:80])}</h3>
<p><strong>Réponse:</strong> {e(q['reponse'][:200])}</p>
<p><em>Nuance:</em> {e(q['nuance'])}</p>
<details><summary>Preuves citées ({len(q['sources'])} sources)</summary>
<ul>
{chr(10).join(f"<li><strong>{s['fichier']}</strong> ({e(s['repere'])}): {e(s['detail'][:100])}</li>" for s in q['sources'])}
</ul>
</details>
</div>"""
    return page(html_content)


@app.get("/ingest", response_class=HTMLResponse)
def ingest_page():
    return page("""<h2>Ajouter des données</h2><form id=f><p><input type=file name=fichier></p><p>ou coller du texte:</p><textarea name=texte rows=8></textarea>
<button type=submit>Analyser et ajouter</button></form><h3>Rapport d'impacts</h3><pre id=r></pre>
<script>f.onsubmit=async ev=>{ev.preventDefault();r.textContent='Analyse en cours...';const x=await fetch('/api/ingest',{method:'POST',body:new FormData(f)});const j=await x.json();r.textContent=j.rapport+'\\n\\n— '+j.nouveaux.length+' claim(s) ajouté(s) (statut: à valider), '+j.rejetes.length+' écarté(s), source '+j.source}</script>""")


@app.post("/api/ingest")
async def api_ingest(fichier: UploadFile | None = File(None), texte: str = Form("")):
    nom, contenu = "texte_colle", texte
    if fichier is not None and fichier.filename:
        nom, data = fichier.filename, await fichier.read()
        contenu = corpus.read_bytes(nom, data)
    return ingest(contenu, nom)
