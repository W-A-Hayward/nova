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

class Q(BaseModel):
    question: str

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
    """Comprehensive brief: introduction, context, governance, scope, budget, priorities, navigation."""
    ledger = kb.ledger()
    autorise = ledger["contrat"] + sum(c["montant"] for c in ledger["changements"] if c["statut"] == "approuve")
    facture_total = sum(sum(l["montant"] for l in f["lignes"]) for f in ledger["factures"])
    paye = sum(sum(l["montant"] for l in f["lignes"]) for f in ledger["factures"] if f["statut"] == "payee")

    fac_html = "<strong>État des factures:</strong><ul>"
    for fac in ledger["factures"]:
        fac_html += f"<li><strong>{fac['id']}</strong> ({fac['date']}) — <strong>{sum(l['montant'] for l in fac['lignes']):,} $</strong> — <span class='{'ok' if fac['statut'] == 'payee' else 'todo'}'>{fac['statut']}</span></li>"
    fac_html += "</ul>"

    brief_html = f"""<h2>NOVA — GUIDE DE PROJET</h2>
<p style="font-size:13px;color:#666"><strong>État au:</strong> 30 septembre 2026, 09:00 Montréal | <strong>Responsable:</strong> Nicolas Perron</p>

<hr style="margin:20px 0;border:none;border-top:1px solid #ddd">

<div class="brief-section">
<h3>📋 QU'EST-CE QUE NOVA?</h3>
<p>NOVA est un <strong>système de gestion de demandes</strong> pour administrer et suivre les demandes de service en interne. Il remplace les processus manuels par un workflow automatisé intégrant:</p>
<ul style="margin-top:8px">
<li><strong>Single Sign-On (SSO):</strong> Authentification simplifiée via identité organisationnelle</li>
<li><strong>Création et suivi de demandes:</strong> Interface intuitif pour soumettre et suivre les demandes en temps réel</li>
<li><strong>Gestion des pièces jointes:</strong> Support des fichiers et documents pour chaque demande</li>
<li><strong>Workflow automatisé:</strong> Routage intelligent vers les bons responsables et escalade</li>
<li><strong>Rapports et analyses:</strong> Tableaux de bord pour suivre les métriques (temps moyen de réponse, volume, tendances)</li>
<li><strong>Accessibilité mobile:</strong> Interface utilisable sur téléphone (phase 2: fonctionnalités avancées)</li>
</ul>
<p style="margin-top:8px;font-size:13px;color:#666"><em>Lancement prévu:</em> <strong>22 octobre 2026</strong> | <em>Partenaire technique:</em> <strong>Boréal</strong> | <em>Budget approuvé:</em> <strong>{autorise:,} $</strong></p>
</div>

<div class="brief-section">
<h3>📊 STATUT GLOBAL DU PROJET</h3>
<table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px">
<tr style="background:#eef2f7">
<th style="text-align:left;padding:10px;border:1px solid #ddd">Domaine</th>
<th style="text-align:left;padding:10px;border:1px solid #ddd">État</th>
<th style="text-align:left;padding:10px;border:1px solid #ddd">Détail</th>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><strong>Développement</strong></td>
<td style="padding:10px;border:1px solid #ddd"><span class="ok">✓ LIVRÉ</span></td>
<td style="padding:10px;border:1px solid #ddd">Tous les modules en production (SSO, demandes, pièces jointes, workflow, rapports). INT-101 fermé 17 sept.</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><strong>Sécurité</strong></td>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">⚠ EN VALIDATION</span></td>
<td style="padding:10px;border:1px solid #ddd">Fix audit (SEC-210) livré 19 sept, <strong>validation sécurité requise avant go-live</strong> — Sophie Lambert</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><strong>Accessibilité</strong></td>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">⚠ OUVERT</span></td>
<td style="padding:10px;border:1px solid #ddd">Modale clavier (ACC-303) non accessible au clavier — <strong>condition go-live</strong> — Mélissa Gagnon</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><strong>Opérations</strong></td>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">⚠ OUVERT</span></td>
<td style="padding:10px;border:1px solid #ddd">Runbook incomplet (étapes 4-5 manquantes) — <strong>condition go-live</strong> — Olivier Côté</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><strong>Finances</strong></td>
<td style="padding:10px;border:1px solid #ddd"><span class="warn">⚠ LITIGE</span></td>
<td style="padding:10px;border:1px solid #ddd">Facture INV-003 inclut 18k$ (CR-04) non approuvé — ligne à contester</td>
</tr>
</table>
</div>

<div class="brief-section">
<h3>👤 1. RESPONSABLE DE PROJET</h3>
<p><strong>Nicolas Perron</strong></p>
<p style="font-size:13px;color:#666">Depuis le <strong>16 septembre 2026</strong> — Transition officielle d'Élodie Caron. Nicolas supervise la ligne d'arrivée: validation des conditions go-live, résolution des tickets bloquants, et coordination avec les équipes (Boréal, sécurité, opérations).</p>
<p style="margin-top:8px"><strong>Rôle:</strong> Approbations, escalade comité, liaison avec Boréal</p>
</div>

<div class="brief-section">
<h3>📅 2. DATE APPROUVÉE ET CONDITIONS</h3>
<p><strong>Date cible:</strong> 22 octobre 2026</p>
<p style="margin-top:8px;font-size:13px;color:#666">Initialement prévue 15 octobre 2026, reportée à 22 octobre par décision du comité le 10 septembre, en raison du retard du connecteur d'intégration (INT-101). Le comité a approuvé cette date le <strong>26 septembre</strong> sous réserve de <strong>3 conditions obligatoires</strong>.</p>

<p style="margin-top:12px"><strong>3 CONDITIONS OBLIGATOIRES POUR LE GO-LIVE:</strong></p>
<table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px">
<tr style="background:#eef2f7">
<th style="text-align:left;padding:10px;border:1px solid #ddd">Condition</th>
<th style="text-align:left;padding:10px;border:1px solid #ddd">Description détaillée</th>
<th style="text-align:left;padding:10px;border:1px solid #ddd">Responsable</th>
<th style="text-align:left;padding:10px;border:1px solid #ddd">Statut</th>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">SEC-210</span></td>
<td style="padding:10px;border:1px solid #ddd">Validation sécurité de la journalisation d'audit pour les exports administrateur. Le correctif a été livré en production le 19 septembre, mais la validation formelle n'a pas encore eu lieu au 30 septembre.</td>
<td style="padding:10px;border:1px solid #ddd">Sophie Lambert (Sécurité)</td>
<td style="padding:10px;border:1px solid #ddd">EN VALIDATION</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">ACC-303</span></td>
<td style="padding:10px;border:1px solid #ddd">Accessibilité clavier de la modale de saisie (WCAG). Le bouton Enregistrer n'est pas accessible au clavier — bloquant avant production. Impact: utilisateurs de technologie d'assistance.</td>
<td style="padding:10px;border:1px solid #ddd">Mélissa Gagnon (Boréal)</td>
<td style="padding:10px;border:1px solid #ddd">OUVERT</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">OPS-601</span></td>
<td style="padding:10px;border:1px solid #ddd">Runbook opérationnel complet avec procédure de rollback et validation post-déploiement. Actuellement manquent étapes 4 et 5. Olivier demande une procédure exécutable, pas juste un document théorique.</td>
<td style="padding:10px;border:1px solid #ddd">Olivier Côté (Opérations)</td>
<td style="padding:10px;border:1px solid #ddd">OUVERT</td>
</tr>
</table>
</div>

<div class="brief-section">
<h3>🎯 3. PORTÉE DU PROJET</h3>
<p><strong>Phase 1 (22 oct 2026):</strong></p>
<ul>
<li>Single Sign-On (SSO) avec annuaire organisationnel</li>
<li>Création et suivi des demandes (workflow intégré)</li>
<li>Gestion des pièces jointes (stockage sécurisé, limite 50 MB/demande)</li>
<li>Workflow automatisé avec escalade et notifications</li>
<li>Rapports de base (volume, délais moyens, tableau de bord responsables)</li>
<li><strong>Interface mobile minimale:</strong> affichage et mise à jour basique des demandes</li>
</ul>

<p style="margin-top:12px;padding:10px;background:#f0f7ff;border-left:4px solid #183760"><strong>Phase 2 (Après 22 oct, pas approuvée):</strong> Fonctionnalités avancées mobiles (recherche avancée, filtres, notifications push), intégration calendrier, analytics avancées. Budget CR-04 (24k$) reporté phase 2 sans engagement.</p>
</div>

<div class="brief-section">
<h3>💰 4. BUDGET</h3>
<p><strong>Budget autorisé:</strong> <strong style="font-size:16px">{autorise:,} $</strong></p>
<ul style="margin-top:8px;font-size:13px">
<li><strong>Contrat Boréal (base):</strong> 180 000 $</li>
<li><strong>Modification CR-01 (approuvée):</strong> +24 000 $</li>
<li><strong>Total autorisé:</strong> 204 000 $</li>
</ul>

<p style="margin-top:12px;padding:10px;background:#fff9e6;border-left:4px solid #d97706"><strong>⚠ ALERTE BUDGET:</strong> Facture INV-003 inclut 18 000 $ pour CR-04 (mobile avancé), <strong>non approuvé en phase 1</strong>. CR-04 a été reporté à phase 2 le 24 septembre. Cette ligne doit être contestée ou retirée avant paiement.</p>

<p style="margin-top:12px"><strong>Factures totales facturées:</strong> {facture_total:,} $</p>
<p style="font-size:13px;margin-top:4px">Déboursé (payé): {paye:,} $ | En attente: {facture_total - paye:,} $</p>
</div>

<div class="brief-section">
<h3>📑 5. SITUATION DES FACTURES</h3>
{fac_html}
<p style="margin-top:8px;font-size:13px"><strong>Résumé:</strong> {facture_total:,} $ facturés, {paye:,} $ payés, {facture_total - paye:,} $ en attente de traitement.</p>
<p style="margin-top:8px;padding:10px;background:#fff0f0;border-left:4px solid #d97706"><strong>Action requise:</strong> INV-003 contient ligne disputée (CR-04 18k$). Valider avec Boréal avant paiement.</p>
</div>

<div class="brief-section">
<h3>🚨 6. PRIORITÉS IMMÉDIATES (Avant 22 oct)</h3>
<p style="font-size:13px;margin-bottom:8px;color:#666">Les 3 éléments suivants sont <strong>conditions obligatoires du go-live</strong>. Le statut au 30 septembre 2026 montre deux bloquants ouverst.</p>
<table style="width:100%;border-collapse:collapse;font-size:13px">
<tr style="background:#eef2f7"><th style="text-align:left;padding:10px;border:1px solid #ddd">Ticket</th><th style="text-align:left;padding:10px;border:1px solid #ddd">Description complète</th><th style="text-align:left;padding:10px;border:1px solid #ddd">Responsable</th><th style="text-align:left;padding:10px;border:1px solid #ddd">Statut</th><th style="text-align:left;padding:10px;border:1px solid #ddd">Délai</th></tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">SEC-210</span></td>
<td style="padding:10px;border:1px solid #ddd"><strong>Validation sécurité — audit logging</strong><br/>Fix livré 19 sept pour journalisation d'audit des exports administrateur. Évaluation sécurité en cours depuis le 19 sept.</td>
<td style="padding:10px;border:1px solid #ddd">Sophie Lambert</td>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">EN VALIDATION</span></td>
<td style="padding:10px;border:1px solid #ddd">Avant 22 oct</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">ACC-303</span></td>
<td style="padding:10px;border:1px solid #ddd"><strong>Accessibilité clavier — modale</strong><br/>Le composant modal de saisie de demande n'est pas accessible au clavier (bouton Enregistrer manquant de tabulation). WCAG AA requis. Bloquant avant production.</td>
<td style="padding:10px;border:1px solid #ddd">Mélissa Gagnon</td>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">OUVERT</span></td>
<td style="padding:10px;border:1px solid #ddd">Avant 22 oct</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">OPS-601</span></td>
<td style="padding:10px;border:1px solid #ddd"><strong>Runbook opérationnel complet</strong><br/>Procédure de déploiement, rollback et validation post-go-live. Étapes 4 (TODO) et 5 (À compléter) manquantes. Olivier exige procédure testée et exécutable, pas document théorique.</td>
<td style="padding:10px;border:1px solid #ddd">Olivier Côté</td>
<td style="padding:10px;border:1px solid #ddd"><span class="todo">OUVERT</span></td>
<td style="padding:10px;border:1px solid #ddd">Avant 22 oct</td>
</tr>
<tr style="background:#f9f9f9">
<td style="padding:10px;border:1px solid #ddd"><span class="ok">INT-101</span></td>
<td style="padding:10px;border:1px solid #ddd"><strong>Intégration avec connecteur interne</strong><br/>Connecteur de synchronisation avec systèmes internes. Était le principal blocage du report de 15 à 22 oct. Validé et fermé 17 sept.</td>
<td style="padding:10px;border:1px solid #ddd">Boréal</td>
<td style="padding:10px;border:1px solid #ddd"><span class="ok">✓ FERMÉ</span></td>
<td style="padding:10px;border:1px solid #ddd">17 sept ✓</td>
</tr>
</table>
</div>

<div class="brief-section">
<h3>🗺️ 7. COMMENT NAVIGUER DANS CE GUIDE</h3>
<p style="font-size:13px;margin-bottom:8px">Vous êtes sur le <strong>/brief</strong> — une vue d'ensemble pour nouveau venu. Voici comment explorer les détails:</p>
<table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px">
<tr style="background:#eef2f7">
<th style="text-align:left;padding:10px;border:1px solid #ddd">Page</th>
<th style="text-align:left;padding:10px;border:1px solid #ddd">Contenu</th>
<th style="text-align:left;padding:10px;border:1px solid #ddd">Quand consulter</th>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><strong><a href="/memoire" style="color:#183760;text-decoration:none">/mémoire</a></strong></td>
<td style="padding:10px;border:1px solid #ddd">Chronologie complète (13 événements), 5 décisions documentées, contradictions résolues, 4 actions en cours avec preuves sourcées</td>
<td style="padding:10px;border:1px solid #ddd">Comprendre l'évolution du projet, d'où viennent les décisions, qui a dit quoi et quand</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><strong><a href="/reponses" style="color:#183760;text-decoration:none">/réponses</a></strong></td>
<td style="padding:10px;border:1px solid #ddd">10 questions clés (Q01–Q10) avec réponses figées, nuances et sources croisées (≥2 preuves par question)</td>
<td style="padding:10px;border:1px solid #ddd">Obtenir réponses aux questions administratives/métier avec preuves exactes (contrat, budget, conditions, équipes, etc.)</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><strong><a href="/chat" style="color:#183760;text-decoration:none">/chat</a></strong></td>
<td style="padding:10px;border:1px solid #ddd">Questions libres → réponses avec preuves citées, affirmations rejetées si sans support, experts consultés</td>
<td style="padding:10px;border:1px solid #ddd">Poser des questions ad hoc; système répond avec preuves visibles et indique ce qui est incertain</td>
</tr>
<tr>
<td style="padding:10px;border:1px solid #ddd"><strong><a href="/ingest" style="color:#183760;text-decoration:none">/ingest</a></strong></td>
<td style="padding:10px;border:1px solid #ddd">Ajouter de la documentation (PDF, email, texte, Excel) avec rapport d'impacts automatisé</td>
<td style="padding:10px;border:1px solid #ddd">Intégrer de nouveaux faits/tickets/décisions et voir qui est impacté</td>
</tr>
</table>
</div>

<div class="brief-section">
<h3>❓ 8. QUESTIONS FRÉQUENTES</h3>

<p style="margin:12px 0;font-weight:600">Q: Pourquoi le project a-t-il été reporté de 15 à 22 octobre?</p>
<p style="margin:0 0 12px 20px;font-size:13px">R: Le connecteur d'intégration interne (INT-101) n'était pas livré à temps. INT-101 a été fermé le 17 sept, levant le blocage.</p>

<p style="margin:12px 0;font-weight:600">Q: Quelles sont les 3 conditions for go-live?</p>
<p style="margin:0 0 12px 20px;font-size:13px">R: (1) Validation sécurité SEC-210 (Sophie Lambert, EN VALIDATION), (2) Accessibilité ACC-303 (Mélissa Gagnon, OUVERT), (3) Runbook complet OPS-601 (Olivier Côté, OUVERT).</p>

<p style="margin:12px 0;font-weight:600">Q: Quel est le problème avec la facture INV-003?</p>
<p style="margin:0 0 12px 20px;font-size:13px">R: INV-003 inclut 18 000 $ pour CR-04 (mobile avancé), qui a été reporté à phase 2 le 24 sept et n'a pas d'approbation. Cette ligne doit être contestée avant paiement.</p>

<p style="margin:12px 0;font-weight:600">Q: Comment trouver une source précise pour une affirmation?</p>
<p style="margin:0 0 12px 20px;font-size:13px">R: Allez dans <strong>/reponses</strong> pour les 10 questions clés (sources affichées), ou utilisez <strong>/chat</strong> et cliquez « Preuves citées » pour chaque réponse.</p>

<p style="margin:12px 0;font-weight:600">Q: Qui a autorisé CR-04 (24k$ mobile avancé)?</p>
<p style="margin:0 0 12px 20px;font-size:13px">R: Proposé par Boréal, mais reporté à phase 2 par décision le 24 sept (aucune approbation pour phase 1). Voir <strong>/reponses Q03</strong>.</p>
</div>

<div class="brief-section" style="background:#f9f9f9;padding:12px;border-radius:4px;margin-top:20px">
<p style="font-size:12px;margin:0;color:#666"><strong>Mises à jour:</strong> Ce guide reflète l'état du 30 septembre 2026, 09:00 Montréal. Pour ajouter des informations après cette date, utilisez <strong><a href="/ingest" style="color:#183760">/ingest</a></strong>.</p>
</div>
"""
    return page(brief_html)

def build_elements_table(memory_data: dict) -> str:
    """Build HTML table rows for all project elements (tickets, decisions, actions, risks)."""
    rows = []
    tickets = kb.ticket_status()

    # Add all tickets
    for ticket_id, ticket_info in sorted(tickets.items()):
        statut = ticket_info.get('statut', 'INCONNU')
        rows.append({
            'element': ticket_id,
            'type': 'Ticket',
            'statut': statut,
            'responsable': '',
            'date': ''
        })

    # Add decisions
    for d in memory_data.get('decisions', []):
        rows.append({
            'element': d['field'],
            'type': 'Décision',
            'statut': 'Approuvé' if d.get('nouveau') else 'Proposal',
            'responsable': '',
            'date': d.get('ancien', {}).get('date', '')
        })

    # Add actions
    for a in memory_data.get('actions', []):
        rows.append({
            'element': a['action'],
            'type': 'Action',
            'statut': a.get('statut_courant', 'À faire'),
            'responsable': a.get('responsable', 'À confirmer'),
            'date': a.get('echéance', 'À confirmer')
        })

    # Add risks (R-01, R-02, etc. from memory timeline)
    for event in memory_data.get('timeline', []):
        if 'risque' in event.get('source', '').lower() or 'registre' in event.get('source', '').lower():
            rows.append({
                'element': event['event'],
                'type': 'Risque',
                'statut': event.get('type', 'Fact'),
                'responsable': '',
                'date': event['date']
            })

    # Generate table rows HTML
    html = ""
    for row in rows:
        html += f"""<tr><td style='padding:8px;border:1px solid #ddd'>{e(row['element'])}</td><td style='padding:8px;border:1px solid #ddd'>{e(row['type'])}</td><td style='padding:8px;border:1px solid #ddd'>{e(row['statut'])}</td><td style='padding:8px;border:1px solid #ddd'>{e(row['responsable'])}</td><td style='padding:8px;border:1px solid #ddd'>{e(row['date'])}</td></tr>"""

    return html


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

<h3>Chronologie complète</h3>
<table style="width:100%;border-collapse:collapse">
<tr style="background:#eef2f7"><th style="text-align:left;padding:8px;border:1px solid #ddd">Date</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Événement</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Type</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Source</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Détail</th></tr>
{chr(10).join(f"<tr><td style='padding:8px;border:1px solid #ddd;white-space:nowrap'>{e(d['date'])}</td><td style='padding:8px;border:1px solid #ddd'>{e(d['event'])}</td><td style='padding:8px;border:1px solid #ddd'>{e(d['type'])}</td><td style='padding:8px;border:1px solid #ddd'>{e(d['source'])}</td><td style='padding:8px;border:1px solid #ddd;word-wrap:break-word'>{e(d['detail'])}</td></tr>" for d in memory_data['timeline'])}
</table>

<h3>Décisions documentées (5)</h3>
{chr(10).join(f"<div class='card' style='word-wrap:break-word'><strong style='display:block;margin-bottom:8px'>🔄 {e(d['field'])}</strong><div style='font-size:13px'><em>État antérieur:</em> <strong>{e(d['ancien']['valeur'])}</strong> ({e(d['ancien']['source'])})<br><em>État nouveau:</em> <strong>{e(d['nouveau']['valeur'])}</strong> ({e(d['nouveau']['source'])})<br><em>Résolution:</em> {e(d['resolution'])}</div></div>" for d in memory_data['decisions'][:5])}

<h3>Contradictions (résolues et non résolues)</h3>
{contradictions_html}

<h3>Actions en cours (4)</h3>
<table style="width:100%;border-collapse:collapse">
<tr style="background:#eef2f7"><th style="text-align:left;padding:8px;border:1px solid #ddd">Action</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Responsable</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Échéance</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Statut</th></tr>
{chr(10).join(f"<tr><td style='padding:8px;border:1px solid #ddd;word-wrap:break-word'>{e(a['action'])}</td><td style='padding:8px;border:1px solid #ddd'>{e(a['responsable'])}</td><td style='padding:8px;border:1px solid #ddd'>{e(a.get('echéance', 'à confirmer'))}</td><td style='padding:8px;border:1px solid #ddd'><span class='todo'>{e(a['statut_courant'])}</span></td></tr>" for a in memory_data['actions'][:4])}
</table>

<style>
:root {{
  --ok: #007a1f;
  --warn: #d97706;
}}
.card {{
  word-wrap: break-word;
  overflow-wrap: break-word;
}}
</style>

<h3>Registre complet du projet</h3>
<table style="width:100%;border-collapse:collapse;font-size:13px">
<tr style="background:#eef2f7"><th style="text-align:left;padding:8px;border:1px solid #ddd">Élément</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Type</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Statut</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Responsable</th><th style="text-align:left;padding:8px;border:1px solid #ddd">Échéance / Date</th></tr>
{build_elements_table(memory_data)}
</table>

<p style="font-size:12px;margin-top:20px"><em>Tous les éléments sont sourcés avec date et autorité. Les contradictions sont tagées: ✓ RÉSOLUE (raisonnement documenté) ou ⚠ NON RÉSOLUE (en attente). Les recommandations de l'équipe sont clairement séparées des engagements documentés.</em></p>""")


@app.get("/reponses", response_class=HTMLResponse)
def reponses_page():
    """Q01–Q10 answers with sources."""
    answers = load_answers()
    html_content = "<h2>Réponses aux 10 questions — Baseline 30 sept 2026</h2><style>.answer-card { word-wrap: break-word; overflow-wrap: break-word; } .answer-card ul li { word-wrap: break-word; overflow-wrap: break-word; }</style>"
    for qid in ["Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07", "Q08", "Q09", "Q10"]:
        if qid in answers:
            q = answers[qid]
            html_content += f"""<div class="card answer-card" style="border-left-color:#007a1f">
<h3>{qid}: {e(q['question'])}</h3>
<p><strong>Réponse:</strong> {e(q['reponse'])}</p>
<p><em>Nuance:</em> {e(q['nuance'])}</p>
<details><summary>Preuves citées ({len(q['sources'])} sources)</summary>
<ul>
{chr(10).join(f"<li><strong>{s['fichier']}</strong> ({e(s['repere'])}): {e(s['detail'])}</li>" for s in q['sources'])}
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
