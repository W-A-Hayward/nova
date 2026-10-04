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
<header><a href="/brief">Brief</a><a href="/memoire">Mémoire</a><a href="/reponses">Réponses Q</a><a href="/chat">Chat</a><a href="/ingest">Ajouter</a></header><main>{body}</main>"""


def table(head, rows):
    return "<table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" + "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows) + "</table>"




@app.get("/chat", response_class=HTMLResponse)
def chat_page():
    return page("""<h2>Chat NOVA</h2>
<style>
#chat-container {
  display: flex;
  flex-direction: column;
  height: 80vh;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}
#messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.message {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  border-radius: 8px;
  max-width: 80%;
}
.user-msg {
  align-self: flex-end;
  background: #183760;
  color: white;
  border-radius: 16px 16px 4px 16px;
}
.assistant-msg {
  align-self: flex-start;
  background: #f0f0f0;
  border-radius: 16px 16px 16px 4px;
}
.msg-text {
  word-wrap: break-word;
}
.msg-meta {
  font-size: 11px;
  opacity: 0.7;
  margin-top: 6px;
}
.assistant-msg .msg-meta {
  color: #666;
}
.user-msg .msg-meta {
  color: rgba(255,255,255,0.8);
}
.msg-sources {
  font-size: 11px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(0,0,0,0.1);
  max-height: 120px;
  overflow-y: auto;
}
.user-msg .msg-sources {
  border-top-color: rgba(255,255,255,0.2);
}
#input-area {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #ddd;
  background: #fafafa;
}
#q {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 20px;
  font-size: 14px;
}
#q:focus {
  outline: none;
  border-color: #183760;
  box-shadow: 0 0 0 2px rgba(24, 55, 96, 0.1);
}
#send-btn {
  padding: 10px 20px;
  background: #183760;
  color: white;
  border: none;
  border-radius: 20px;
  cursor: pointer;
  font-weight: 500;
}
#send-btn:hover {
  background: #0d1f3c;
}
#send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>

<div id="chat-container">
  <div id="messages"></div>
  <div id="input-area">
    <input type="text" id="q" placeholder="Posez votre question...">
    <button id="send-btn">Envoyer</button>
  </div>
</div>

<script>
const messagesDiv = document.getElementById('messages');
const inputField = document.getElementById('q');
const sendBtn = document.getElementById('send-btn');

function addMessage(text, isUser, metadata) {
  metadata = metadata || {};
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message ' + (isUser ? 'user-msg' : 'assistant-msg');

  let html = '<div class="msg-text">' + escapeHtml(text) + '</div>';

  if (metadata.sujets) {
    html += '<div class="msg-meta">Experts: ' + escapeHtml(metadata.sujets.join(', ')) + '</div>';
  }

  if (metadata.sources && metadata.sources.length > 0) {
    html += '<div class="msg-sources"><strong>Preuves citees:</strong>';
    metadata.sources.forEach(s => {
      html += '<div style="margin-top:4px;font-size:10px">[' + escapeHtml(s.source) + '] ' + escapeHtml(s.id) + '</div>';
    });
    html += '</div>';
  }

  if (metadata.rejected && metadata.rejected.length > 0) {
    html += '<div class="msg-sources" style="border-top-color: #c00; color: #9b1c1c"><strong>Affirmations rejetees:</strong>';
    metadata.rejected.slice(0, 3).forEach(r => {
      html += '<div style="margin-top:4px;font-size:10px">[' + escapeHtml(r.sujet) + ']</div>';
    });
    if (metadata.rejected.length > 3) {
      html += '<div style="margin-top:4px;font-size:10px">... et ' + (metadata.rejected.length - 3) + ' autres</div>';
    }
    html += '</div>';
  }

  msgDiv.innerHTML = html;
  messagesDiv.appendChild(msgDiv);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

async function sendMessage() {
  const question = inputField.value.trim();
  if (!question) return;

  addMessage(question, true);
  inputField.value = '';
  sendBtn.disabled = true;
  sendBtn.textContent = 'Envoi...';

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: question})
    });

    if (!r.ok) {
      addMessage('Erreur serveur: ' + r.status + ' ' + r.statusText, false);
      return;
    }

    const j = await r.json();
    addMessage(j.reponse || '(pas de reponse)', false, {
      sujets: j.sujets,
      sources: j.preuves || [],
      rejected: j.rejetees || []
    });
  } catch (err) {
    addMessage('Erreur: ' + err.message, false);
    console.error('Chat error:', err);
  } finally {
    sendBtn.disabled = false;
    sendBtn.textContent = 'Envoyer';
    inputField.focus();
  }
}

sendBtn.addEventListener('click', sendMessage);
inputField.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

addMessage('Bienvenue! Posez vos questions sur le projet NOVA.', false);
</script>
""")

@app.post("/api/chat")
def api_chat(q: Q):
    r = ask(q.question)
    rejetees = [{"sujet": x["sujet"], "texte": a["texte"], "problemes": a["problemes"]} for x in r["experts"] for a in x["retirees"]]
    return {"reponse": r["reponse"], "sujets": r["sujets"], "preuves": r["preuves"], "confiance": r["confiance"], "rejetees": rejetees}


@app.get("/brief", response_class=HTMLResponse)
def brief_page():
    """One-page brief: responsable, date+conditions, portee, budget, factures, priorites."""
    ledger = kb.ledger()
    autorise = ledger["contrat"] + sum(c["montant"] for c in ledger["changements"] if c["statut"] == "approuve")
    facture_total = sum(sum(l["montant"] for l in f["lignes"]) for f in ledger["factures"])
    paye = sum(sum(l["montant"] for l in f["lignes"]) for f in ledger["factures"] if f["statut"] == "payee")
    
    fac_html = "<strong>Factures:</strong><ul>"
    for fac in ledger["factures"]:
        fac_html += f"<li>{fac['id']} ({fac['date']}, {fac['statut']}): {sum(l['montant'] for l in fac['lignes']):,} $</li>"
    fac_html += "</ul>"
    
    brief_html = f"""<h2>BRIEF OPERATIONNEL — NOVA</h2>
<p><strong>Baseline:</strong> 30 sept 2026 09:00</p>

<div class="brief-section"><h3>1. RESPONSABLE</h3>
<p><strong>Nicolas Perron</strong> (depuis 16 sept 2026)</p></div>

<div class="brief-section"><h3>2. DATE APPROUVEE ET CONDITIONS</h3>
<p><strong>Date:</strong> 22 octobre 2026 | <strong>Approbation:</strong> Comite 26 sept<br>
<strong>Conditions obligatoires:</strong>
<ol><li>SEC-210: Validation securite (Sophie Lambert)</li>
<li>ACC-303: Fermeture modale clavier (Melissa Gagnon)</li>
<li>OPS-601: Runbook + rollback (Olivier Cote)</li></ol></p></div>

<div class="brief-section"><h3>3. PORTEE</h3>
<p>SSO, creation/suivi demandes, pieces jointes, workflow, rapports. Mobile utilisable (avancees → Phase 2).</p></div>

<div class="brief-section"><h3>4. BUDGET</h3>
<p><strong>Autorise:</strong> {autorise:,} $ (contrat 180k + CR-01 24k)<br>
<strong>Facture total:</strong> {facture_total:,} $<br>
<strong style="color:#9b1c1c">Probleme:</strong> INV-003 inclut 18k$ CR-04 non approuve</p></div>

<div class="brief-section"><h3>5. SITUATION FACTURES</h3>
{fac_html}<p>Facture total: {facture_total:,} $ | Paye: {paye:,} $</p></div>

<div class="brief-section"><h3>6. PRIORITES</h3>
<table><tr><th>Item</th><th>Responsable</th><th>Statut</th><th>Echéance</th></tr>
<tr><td>SEC-210</td><td>Sophie</td><td>EN VALIDATION</td><td>Avant 22 oct</td></tr>
<tr><td>ACC-303</td><td>Melissa</td><td>OUVERT</td><td>Avant 22 oct</td></tr>
<tr><td>OPS-601</td><td>Olivier</td><td>OUVERT</td><td>Avant 22 oct</td></tr>
<tr><td style="background:#eef2f7">INT-101</td><td>Boreal</td><td>FERME</td><td>17 sept OK</td></tr></table></div>

<p style="font-size:11px;margin-top:20px">Details: /memoire (timeline/decisions) | /reponses (Q01-Q10 sources)</p>"""
    return page(brief_html)

@app.get("/memoire", response_class=HTMLResponse)
def memoire_page():
    """Structured memory with timeline, decisions, contradictions, actions."""
    memory_data = memory.load_memory()

    # Build contradictions HTML with resolution status
    contradictions_html = ""
    for c in memory_data['contradictions']:
        resolved = bool(c.get('resolution'))
        status_label = "✓ RÉSOLUE" if resolved else "⚠ NON RÉSOLUE"
        status_color = "ok" if resolved else "warn"

        sources_html = "<strong>Sources en conflit:</strong><ul>"
        for src in c.get('sources', []):
            sources_html += f"<li><strong>{e(src.get('date', ''))}</strong> — {e(src.get('texte', ''))} <br><em>Source:</em> {e(src.get('source', ''))}, Autorité: {e(src.get('autorité', ''))}</li>"
        sources_html += "</ul>"

        contradictions_html += f"""<div class='card' style='border-left-color: var(--{status_color})'>
<strong style='color: var(--{status_color})'>{status_label}: {e(c['domaine'])}</strong><br>
{sources_html}
<strong>Analyse:</strong> {e(c.get('resolution', 'Contradiction non résolue'))}<br>
<em>Note:</em> {e(c.get('note', ''))}
</div>"""

    return page(f"""<h2>Mémoire opérationnelle NOVA</h2>
<p><strong>Baseline:</strong> {e(memory_data['ref_date'])}</p>

<h3>Chronologie (13 événements clés)</h3>
<table>
<tr><th>Date</th><th>Événement</th><th>Type</th><th>Source</th><th>Détail</th></tr>
{chr(10).join(f"<tr><td>{e(d['date'])}</td><td>{e(d['event'])}</td><td>{e(d['type'])}</td><td>{e(d['source'])}</td><td>{e(d['detail'][:80])}</td></tr>" for d in memory_data['timeline'][:13])}
</table>

<h3>Décisions documentées (5)</h3>
{chr(10).join(f"<div class='card'><strong>🔄 {d['field']}</strong><br><em>État antérieur:</em> <strong>{d['ancien']['valeur']}</strong> ({d['ancien']['source']})<br><em>État nouveau:</em> <strong>{d['nouveau']['valeur']}</strong> ({d['nouveau']['source']})<br><em>Résolution:</em> {d['resolution']}</div>" for d in memory_data['decisions'][:5])}

<h3>Contradictions (résolues et non résolues)</h3>
{contradictions_html}

<h3>Actions en cours (4)</h3>
<table>
<tr><th>Action</th><th>Responsable</th><th>Échéance</th><th>Statut</th></tr>
{chr(10).join(f"<tr><td>{e(a['action'][:40])}</td><td>{e(a['responsable'])}</td><td>{a.get('echéance', 'à confirmer')}</td><td><span class='todo'>{a['statut_courant']}</span></td></tr>" for a in memory_data['actions'][:4])}
</table>

<style>
:root {{
  --ok: #007a1f;
  --warn: #d97706;
}}
</style>

<p style="font-size:12px;margin-top:20px"><em>Tous les éléments sont sourcés avec date et autorité. Les contradictions sont tagées: ✓ RÉSOLUE (raisonnement documenté) ou ⚠ NON RÉSOLUE (en attente). Les recommandations de l'équipe sont clairement séparées des engagements documentés.</em></p>""")


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
