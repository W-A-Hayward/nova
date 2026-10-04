"""Interface web: /  rapport (généré du code, sans LLM) | /chat (avec preuves et rejets visibles) | /ingest"""
import html
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from . import corpus, kb
from .chat_graph import ask
from .ingest_graph import ingest

app = FastAPI(title="NOVA")
e = html.escape
CSS = """body{font:15px/1.45 system-ui,sans-serif;margin:0;color:#1b1b1b}header{background:#183760;padding:10px 20px}header a{color:#fff;margin-right:16px;text-decoration:none;font-weight:600}
main{padding:14px 20px;max-width:1100px}table{border-collapse:collapse;width:100%;margin-bottom:14px}td,th{border:1px solid #ccc;padding:5px 7px;text-align:left;vertical-align:top}th{background:#eef2f7}
pre{white-space:pre-wrap;background:#f6f7f9;padding:10px;border-radius:6px}textarea,input[type=text]{width:100%;padding:8px;box-sizing:border-box}button{padding:8px 16px;margin-top:8px}.warn{color:#9b1c1c}"""


def page(body: str) -> str:
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>NOVA</title><style>{CSS}</style>
<header><a href="/">Rapport</a><a href="/chat">Chat</a><a href="/ingest">Ajouter des données</a></header><main>{body}</main>"""


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
