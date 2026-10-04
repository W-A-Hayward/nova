"""Interface web NOVA.

/brief (1 page) | /memoire | /reponses | /mise-a-jour | /sources (catalogue + recherche) | /source/<fichier> | /guide | /chat | /ingest
Toutes les pages sauf /chat et /ingest sont rendues sans LLM et exportables en HTML statique (scripts/export_static.py):
en mode STATIC, href() produit des liens relatifs vers des fichiers .html au lieu de routes.
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from . import corpus, evidence, kb, memory, updates

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
ANSWERS = ROOT_DIR / "data" / "answers_baseline.json"
FIXTURES = ROOT_DIR / "tests" / "fixtures"
STATIC = False  # positionné par scripts/export_static.py

app = FastAPI(title="NOVA")
e = html.escape


class Q(BaseModel):
    question: str


# ---------------------------------------------------------------- liens et mise en page

def href(route: str, anchor: str = "") -> str:
    a = f"#{anchor}" if anchor else ""
    if STATIC:
        if route.startswith("raw/"):
            return route + a
        return (route.replace("/", "__") or "index") + ".html" + a
    return "/" + quote(route) + a


def short(fichier: str) -> str:
    """M04_Transcript_... -> M04 ; ACC-303_focus.png -> ACC-303_focus.png ; autres -> nom du fichier."""
    name = Path(fichier).name
    m = re.match(r"([EM]\d\d|[A-Z]+-\d+)(?=[_.])", name)
    if m and not name.endswith(".png"):
        return m.group(1)
    if name.endswith(".png"):
        return name
    parts = Path(name).stem.split("_")
    v = next((i for i, x in enumerate(parts) if re.fullmatch(r"v\d+", x)), None)  # garder la version (v1, v3...)
    return "_".join(parts[:v + 1] if v is not None else parts[:2])


def cite(p: dict, label: str = "") -> str:
    """Lien vers la preuve: fichier + repère, l'extrait verbatim en infobulle."""
    rep = p.get("repere") or ""
    if not rep and p.get("extrait"):
        loc = evidence.locate(p["fichier"], p["extrait"])
        rep, p = (loc["repere"], {**p, "anchor": loc["anchor"]}) if loc else ("", p)
    txt = label or (f"{short(p['fichier'])} · {rep}" if rep and rep != "document" else short(p["fichier"]))
    return (f"<a class=cite href='{href('source/' + p['fichier'], p.get('anchor', ''))}' "
            f"title='{e(p.get('extrait', ''))}'>{e(txt)}</a>")


def cites(ps: list[dict]) -> str:
    return " ".join(cite(p) for p in ps)


CSS = """
:root{--bg:#f7f8fa;--fg:#1b1f24;--muted:#5b6470;--card:#fff;--line:#d9dee5;--head:#183760;--headfg:#fff;--th:#eef2f7;
--ok:#0b7a32;--warn:#a15c00;--bad:#b42318;--link:#1d4f91;--hl:#fff3b0;--prop:#6b3fa0;--dec:#0b5cad;--val:#0b7a32;--sig:#b42318}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111418;--fg:#e6e9ee;--muted:#9aa4b1;--card:#1a1f26;--line:#2d343e;
--head:#0f2747;--th:#222a35;--ok:#4cc27a;--warn:#e0a54b;--bad:#f07167;--link:#8cb8ff;--hl:#4a4215;--prop:#b794f4;--dec:#6cb2ff;--val:#4cc27a;--sig:#f07167}}
:root[data-theme="dark"]{--bg:#111418;--fg:#e6e9ee;--muted:#9aa4b1;--card:#1a1f26;--line:#2d343e;--head:#0f2747;--th:#222a35;
--ok:#4cc27a;--warn:#e0a54b;--bad:#f07167;--link:#8cb8ff;--hl:#4a4215;--prop:#b794f4;--dec:#6cb2ff;--val:#4cc27a;--sig:#f07167}
*{box-sizing:border-box}body{font:15px/1.5 system-ui,sans-serif;margin:0;color:var(--fg);background:var(--bg)}
a{color:var(--link)}header{background:var(--head);padding:8px 16px;display:flex;flex-wrap:wrap;gap:4px 14px}
header a{color:var(--headfg);text-decoration:none;font-weight:600}header a:hover{text-decoration:underline}
header .off{color:#aab;font-weight:400}
main{padding:14px 16px;max-width:1150px;margin:0 auto}
h1{font-size:22px;margin:6px 0}h2{font-size:18px;margin:22px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}h3{font-size:15px;margin:14px 0 6px}
table{border-collapse:collapse;width:100%;margin:6px 0 14px;background:var(--card)}
td,th{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{background:var(--th);font-weight:600}
.scroll{overflow-x:auto}pre{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);padding:10px;border-radius:6px}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--head);border-radius:6px;padding:10px 12px;margin:10px 0}
.muted{color:var(--muted)}.small{font-size:13px}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.tag{display:inline-block;font-size:11px;font-weight:700;padding:1px 6px;border-radius:9px;border:1px solid currentColor;white-space:nowrap}
.n-proposition{color:var(--prop)}.n-décision{color:var(--dec)}.n-validation{color:var(--val)}.n-livraison{color:var(--warn)}.n-signal{color:var(--sig)}.n-fait{color:var(--muted)}
.engagement{color:var(--dec)}.recommandation{color:var(--prop)}
a.cite{font-size:12px;white-space:nowrap;margin-right:6px}
.quote{border-left:3px solid var(--line);padding-left:8px;color:var(--muted);font-style:italic}
:target{background:var(--hl);outline:2px solid var(--warn)}
.lines div{font:13px/1.45 ui-monospace,monospace;white-space:pre-wrap;padding:0 6px}.lines span{color:var(--muted);user-select:none;display:inline-block;width:3.2em}
textarea,input[type=text]{width:100%;padding:8px;border:1px solid var(--line);border-radius:4px;background:var(--card);color:var(--fg)}
button{padding:8px 16px;margin-top:8px;background:var(--head);color:#fff;border:none;border-radius:4px;cursor:pointer}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}
.brief td,.brief th{padding:4px 6px;font-size:13px}.brief p{margin:4px 0}.brief h1{font-size:19px}.brief h2{font-size:15px;margin:10px 0 4px}
@media print{header,.noprint{display:none}main{padding:0;max-width:none}body{font-size:10px;line-height:1.35;background:#fff;color:#000}
.brief td,.brief th{padding:1px 4px;font-size:9.5px}.brief h1{font-size:15px;margin:0}.brief h2{font-size:11.5px;margin:5px 0 2px;padding-bottom:1px}
.brief table{margin:3px 0 5px}.tag{font-size:8.5px;padding:0 4px}a{color:#000;text-decoration:none}a.cite{font-size:8.5px;color:#444}
@page{size:A4;margin:10mm}}
"""

NAV = [("brief", "Brief"), ("memoire", "Mémoire"), ("reponses", "Réponses Q01–Q10"), ("mise-a-jour", "Mise à jour"),
       ("sources", "Sources et recherche"), ("guide", "Mode d'emploi")]


def page(body: str, title: str = "NOVA") -> str:
    nav = "".join(f"<a href='{href(r)}'>{t}</a>" for r, t in NAV)
    nav += ("<span class=off>Chat et Ajouter : serveur seulement</span>" if STATIC
            else f"<a href='{href('chat')}'>Chat</a><a href='{href('ingest')}'>Ajouter</a>")
    return (f"<!doctype html><html lang=fr><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{e(title)}</title><style>{CSS}</style><header>{nav}</header><main>{body}</main></html>")


def tag(text: str, cls: str = "") -> str:
    return f"<span class='tag {cls}'>{e(text)}</span>"


def nature_tag(n: str) -> str:
    return tag(n, "engagement" if n.startswith("engagement") else "recommandation" if n.startswith("recommandation") else "")


# ---------------------------------------------------------------- données

def load_answers() -> dict:
    return json.loads(ANSWERS.read_text(encoding="utf-8")) if ANSWERS.exists() else {}


def finances() -> dict:
    """Montants calculés depuis les PDF (kb.ledger), jamais saisis à la main."""
    L = kb.ledger()
    approuves = [c for c in L["changements"] if c["statut"] == "approuvé"]
    autorise = L["contrat"] + sum(c["montant"] for c in approuves)
    ok_refs = {c["id"] for c in approuves}
    total = lambda f: sum(l["montant"] for l in f["lignes"])
    facture = sum(total(f) for f in L["factures"])
    paye = sum(total(f) for f in L["factures"] if f["statut"] == "payée")
    non_aut = [(f, l) for f in L["factures"] for l in f["lignes"] if l["ref"] and l["ref"] not in ok_refs]
    return {"L": L, "autorise": autorise, "facture": facture, "paye": paye, "non_aut": non_aut, "total": total,
            "approuves": approuves, "non_approuves": [c for c in L["changements"] if c["statut"] != "approuvé"]}


def money(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " $"


def src_file(sid: str) -> str:
    return kb.sources().get(sid, {}).get("fichier", "")


# ---------------------------------------------------------------- pages

@app.get("/")
def root():
    return RedirectResponse("/brief")


@app.get("/brief", response_class=HTMLResponse)
def brief_page():
    m = memory.load_memory()
    F = finances()
    A = {a["id"]: a for a in m["actions"]}
    C = {c["id"]: c for c in m["conditions"]}
    p = lambda f, x: cite({"fichier": f, "extrait": x})
    fac_rows = "".join(
        f"<tr><td>{cite({'fichier': src_file(f['source']), 'extrait': ''}, f['id'])}</td><td>{e(f['date'])}</td><td>{money(F['total'](f))}</td>"
        f"<td>{e(' + '.join(money(l['montant']) + ' ' + l['desc'] for l in f['lignes']))}</td>"
        f"<td class={'ok' if f['statut'] == 'payée' else 'warn'}>{e(f['statut'])}</td></tr>" for f in F["L"]["factures"])
    na = "; ".join(f"{f['id']} : {money(l['montant'])} « {l['desc']} » (réf. {l['ref']} non approuvé)" for f, l in F["non_aut"])
    def prow(first: str, a: dict) -> str:
        return (f"<tr>{first}<td>{a['id']} {e(a['court'])}</td><td>{e(a['echeance_court'])}</td>"
                f"<td>{nature_tag(a['nature'])}</td><td>{cites(a['preuves'][:1])}</td></tr>")
    prio = ""
    for cid in ("C1", "C2", "C3"):
        c = C[cid]
        ids = c["actions"]
        prio += prow(f"<td rowspan={len(ids)}><b>{cid}</b> {e(c['libelle'])}</td><td rowspan={len(ids)} class=warn>{e(c['statut_ticket'])}</td>", A[ids[0]])
        prio += "".join(prow("", A[aid]) for aid in ids[1:])
    prio += "".join(prow("<td>Hors conditions</td><td class=warn>OUVERT</td>", A[aid]) for aid in ("A6", "A7"))
    body = f"""<div class=brief>
<h1>Brief de reprise : NOVA</h1>
<p class="muted small">État au <b>30 septembre 2026, 09 h (Montréal, UTC−4)</b>. Les montants sont en CAD hors taxes. {tag('engagement documenté', 'engagement')} = écrit dans le dossier ;
{tag('recommandation équipe', 'recommandation')} = notre proposition. Chaque lien ouvre la preuve. <a class=noprint href="{href('memoire')}">Mémoire complète →</a></p>

<h2>1. Responsable</h2>
<p><b>Nicolas Perron</b>, chargé de projet <b>depuis le 16 septembre 2026</b>, succède à Élodie Caron (en poste depuis le 7 juillet).
{p('01_Courriels/E06_Transition_charge_projet.eml','Nicolas Perron prend officiellement la charge du projet NOVA')} {p('04_Documents_projet/Note_transition_Elodie_16sept.txt', 'Nicolas Perron reprend le rôle de chargé de projet NOVA')}</p>

<h2>2. Date approuvée et conditions</h2>
<p><b>22 octobre 2026</b>. Proposée par Boréal le 8 septembre {p('01_Courriels/E05_Retard_integration.eml', "il s'agit d'une proposition de notre part")},
<b>approuvée par le comité de direction le 10 septembre</b> {p(memory.M04, 'Donc approuvé. Le 22 devient la date officielle.')},
cible reconfirmée le 26 septembre et <b>conditionnelle</b> à 3 conditions {p(memory.M06, "c'est conditionnel à ces trois éléments")} :
<b>C1</b> validation sécurité de SEC-210 · <b>C2</b> fermeture d'ACC-303 · <b>C3</b> approbation du runbook incluant le rollback.
Ce n'est pas un go garanti {p('01_Courriels/E09_Rappel_mise_en_production.eml', 'go garanti')}. Le 15 octobre (charte, plan v3) est <span class=bad>périmé</span>.
Cause du report : connecteur INT-101, <span class=ok>fermé le 17 septembre</span> {p('03_Tickets/INT-101.txt', 'Validé côté intégration. Je ferme.')}.</p>

<h2>3. Portée (phase 1)</h2>
<p>SSO (uniquement en production), création et suivi de demandes, pièces jointes, workflow de traitement, tableau de suivi, rapports standards {p(memory.CONTRAT, 'Portée incluse')},
plus les rapports avancés et l'export de synthèse (CR-01) {p(memory.CR01, 'Ajout de rapports avancés et export de synthèse.')}. Données de production au <b>Canada Central</b> (ADR-007) {p(memory.ADR, 'Canada Central')}.
<b>Hors portée :</b> l'optimisation mobile avancée (CR-04) est reportée à la phase 2. La phase 1 doit seulement rester utilisable sur mobile {p(memory.PORTEE, 'La phase 1 doit demeurer utilisable sur mobile')}.</p>

<h2>4. Budget</h2>
<p><b>Autorisé : {money(F['autorise'])}</b> = contrat {money(F['L']['contrat'])} {p(memory.CONTRAT, 'Montant maximal initial')}
{''.join(f"+ {c['id']} {money(c['montant'])} (approuvé le {c['date']}) " + p(src_file(c['source']), 'APPROUVÉE') for c in F['approuves'])}.
Non autorisé : {'; '.join(f"{c['id']} {money(c['montant'])} ({c['statut']})" for c in F['non_approuves'])} {p(memory.CR04, 'BROUILLON - APPROBATION REQUISE')}.</p>

<h2>5. Situation des factures</h2>
<table><tr><th>Facture</th><th>Date</th><th>Total</th><th>Lignes</th><th>Statut</th></tr>{fac_rows}</table>
<p><b>Facturé {money(F['facture'])}</b> · <b>payé {money(F['paye'])}</b> · en validation {money(F['facture'] - F['paye'])}.
<span class=bad>Problème : {e(na)}</span>. Les Finances (Amélie Fortin) retiennent INV-003 {p('01_Courriels/E07_Facture_003_question.eml', "Peux-tu me transmettre l'approbation correspondante?")}.
La facturation de CR-04 est interdite sans nouvelle approbation {p('01_Courriels/E10_Fonction_mobile.eml', 'ne doit être engagée ou facturée sans nouvelle approbation')}.
{tag('recommandation équipe', 'recommandation')} Ne pas payer les 18 000 $, demander une facture corrigée ou une note de crédit, et valider les 36 000 $ du jalon 3.</p>

<h2>6. Priorités : conditions de go-live → actions</h2>
<table><tr><th>Condition</th><th>Statut</th><th>Action : responsable</th><th>Échéance</th><th>Nature</th><th>Preuve</th></tr>{prio}</table>
<p class="small muted">Aucune échéance précise n'est écrite au dossier : toutes sont « à confirmer », bornées par le go-live du 22 octobre.
Olivier veut le runbook final « quelques jours avant » {p(memory.M04, 'au moins quelques jours avant')}.</p>
</div>"""
    return page(body, "Brief NOVA")


@app.get("/memoire", response_class=HTMLResponse)
def memoire_page():
    m = memory.load_memory()
    tl = "".join(f"<tr><td style='white-space:nowrap'>{e(t['date'])}{(' ' + e(t['heure'])) if t['heure'] else ''}</td>"
                 f"<td>{tag(t['nature'], 'n-' + t['nature'])}</td><td>{e(t['acteur'])}</td><td>{e(t['evenement'])}</td>"
                 f"<td>{cites(t['preuves'])}</td></tr>" for t in m["timeline"])

    def step(x, label):
        if not x:
            return f"<td class=muted>—</td>"
        return (f"<td><b>{e(x.get('valeur', ''))}</b><br><span class=small>{e(x['qui'])}, {e(x['quand'])}</span><br>{cite(x['preuve'])}</td>")
    dec = "".join(f"<tr><td><b>{e(d['sujet'])}</b></td>"
                  f"<td>{(e(d['remplace']['valeur']) + '<br>' + cite(d['remplace']['preuve'])) if d['remplace'] else '—'}</td>"
                  f"{step(d['proposition'], 'proposition')}{step(d['decision'], 'décision')}{step(d['validation'], 'validation')}</tr>"
                  for d in m["decisions"])
    contra = ""
    for c in m["contradictions"]:
        aff = "".join(f"<li><b>{e(a['date'])}</b> · {e(a['autorite'])} : « {e(a['texte'])} » {cite(a['preuve'])}</li>" for a in c["affirmations"])
        contra += (f"<div class=card><b>{e(c['sujet'])}</b> {tag(c['type'])} {tag('règle : ' + c['regle'])}<ul>{aff}</ul>"
                   f"<b class=ok>Résolution :</b> {e(c['resolution'])} {cite(c['preuve_resolution'])}</div>")
    cond = "".join(f"<tr><td><b>{c['id']}</b> {e(c['libelle'])}</td><td>{e(c['validateur'])}</td>"
                   f"<td class=warn>{e(c['statut_ticket'])}</td><td>{', '.join(c['actions'])}</td></tr>" for c in m["conditions"])
    act = "".join(f"<tr id='{a['id']}'><td><b>{a['id']}</b>{(' · ' + a['condition']) if a.get('condition') else ''}</td><td>{e(a['action'])}"
                  f"{('<br><span class=\"small muted\">' + e(a['note']) + '</span>') if a.get('note') else ''}</td>"
                  f"<td>{e(a['executant'])} <span class=small>({e(a['statut_resp'])})</span></td><td>{e(a.get('validateur') or '—')}</td>"
                  f"<td>{e(a['echeance'])}</td><td>{e(a['statut'])}</td><td>{nature_tag(a['nature'])}</td><td>{cites(a['preuves'])}</td></tr>"
                  for a in m["actions"])
    reg_doc = evidence.by_file()[memory.REGISTRE]
    reg = "".join(f"<tr><td>{cite({'fichier': memory.REGISTRE, 'repere': p['repere'], 'anchor': evidence.anchor(p['repere'])}, p['repere'].split(', ', 1)[1])}</td>"
                  f"<td>{e(p['texte'])}{' <span class=bad>⚠ ligne périmée : INT-101 fermé le 17 sept</span>' if 'R-01' in p['texte'] else ''}</td></tr>"
                  for p in reg_doc["passages"])
    ecart = "".join(f"<li>{cite(x, Path(x['fichier']).name)} : {e(x['raison'])}</li>" for x in m["sources_ecartees"])
    body = f"""<h1>Mémoire opérationnelle : NOVA</h1>
<p class=muted>Baseline : {e(m['ref_date'])} (Montréal). Ce fichier n'est jamais réécrit. Les nouvelles informations passent par <a href="{href('mise-a-jour')}">Mise à jour</a>.
Natures : {tag('proposition', 'n-proposition')} {tag('décision', 'n-décision')} {tag('validation', 'n-validation')} {tag('livraison', 'n-livraison')} (livré ≠ validé)
{tag('signal', 'n-signal')} (affirmation non fiable ou périmée) {tag('fait', 'n-fait')}.</p>
<p class=small>Aller à : <a href="#chrono">Chronologie</a> · <a href="#decisions">Décisions</a> · <a href="#contradictions">Contradictions</a> ·
<a href="#actions">Conditions et actions</a> · <a href="#registre">Registre des risques</a> · <a href="#ecartees">Sources écartées</a></p>
<h2 id=chrono>Chronologie ({len(m['timeline'])} événements)</h2>
<div class=scroll><table><tr><th>Date</th><th>Nature</th><th>Qui</th><th>Événement</th><th>Preuve</th></tr>{tl}</table></div>
<h2 id=decisions>Décisions : proposition → décision → validation</h2>
<div class=scroll><table><tr><th>Sujet</th><th>Remplace</th><th>Proposition</th><th>Décision</th><th>Validation / suite</th></tr>{dec}</table></div>
<h2 id=contradictions>Contradictions résolues ({len(m['contradictions'])})</h2>
<p class="small muted">Chaque contradiction est tranchée par l'autorité de la source ou par la date des faits. La date du fichier ne suffit pas.</p>{contra}
<h2 id=actions>Conditions de go-live et actions restantes</h2>
<table><tr><th>Condition (M06, 26 sept)</th><th>Validateur</th><th>Statut au 30 sept</th><th>Actions</th></tr>{cond}</table>
<div class=scroll><table><tr><th>ID</th><th>Action</th><th>Exécutant (statut)</th><th>Validateur</th><th>Échéance</th><th>Statut</th><th>Nature</th><th>Preuves</th></tr>{act}</table></div>
<h2 id=registre>Registre des risques (29 sept), lu cellule par cellule</h2>
<table><tr><th>Cellules</th><th>Contenu</th></tr>{reg}</table>
<h2 id=ecartees>Sources écartées ou non indépendantes</h2><ul>{ecart}</ul>"""
    return page(body, "Mémoire NOVA")


@app.get("/reponses", response_class=HTMLResponse)
def reponses_page():
    out = "<h1>Réponses Q01–Q10 (baseline du 30 sept 2026, 09 h)</h1><p class=muted>Chaque source ouvre le fichier au repère exact. L'extrait est cité mot pour mot et vérifié par tests/test_deliverables.py.</p>"
    for qid, q in load_answers().items():
        srcs = ""
        for s in q["sources"]:
            loc = evidence.locate(s["fichier"], s["extrait"]) or {"repere": "?", "anchor": ""}
            indep = "" if s.get("independante", True) else " " + tag("non indépendante : " + s.get("note", "pièce jointe ou doublon"), "n-signal")
            srcs += (f"<li><a href='{href('source/' + s['fichier'], loc['anchor'])}'>{e(s['fichier'])}</a> : <b>{e(s['repere'])}</b> "
                     f"<span class='small muted'>({e(loc['repere'])})</span>{indep}<div class=quote>« {e(s['extrait'])} »</div></li>")
        out += (f"<div class=card id={qid}><h3>{qid}. {e(q['question'])}</h3><p><b>Réponse :</b> {e(q['reponse'])}</p>"
                f"<p><b>Nuance :</b> {e(q['nuance'])}</p><details open><summary>Preuves ({len(q['sources'])})</summary><ul>{srcs}</ul></details></div>")
    return page(out, "Réponses Q01–Q10")


def render_updates(ups: list[dict], exercice: bool = False) -> str:
    base = memory.load_memory()
    cur = updates.apply(base, ups)
    out = "<h1>Mise à jour après la baseline</h1>"
    if exercice:
        out += "<div class=card style='border-left-color:var(--bad)'><b class=bad>EXERCICE FICTIF</b> : démonstration avec un document inventé (tests/fixtures). Il ne fait pas partie du dossier NOVA.</div>"
    if not cur["mises_a_jour"]:
        out += (f"<p>Aucune nouvelle information n'a été intégrée : l'état actuel est la <a href='{href('memoire')}'>baseline du 30 septembre</a>.</p>"
                "<p class='small muted'>Procédure : déposer le document dans <code>data/updates/docs/</code>, copier <code>data/updates/_modele.json</code> en "
                "<code>U01_&lt;sujet&gt;.json</code>, citer des extraits exacts. La page recalcule l'état sans toucher la baseline."
                + ("" if STATIC else f" Démonstration : <a href='/mise-a-jour?exercice=1'>exercice fictif</a>.") + "</p>")
        return out
    d = cur["date_approuvee"]
    props = "".join(f"<li>{tag('proposition', 'n-proposition')} {e(p['valeur'])} par {e(p['par'])} ({e(p['maj'])}) : <b>non approuvée</b></li>" for p in d["propositions"])
    bc = {c["id"]: c for c in base["conditions"]}
    rows = (f"<tr><td>Date de mise en production approuvée</td><td>22 octobre 2026</td><td><b>{e(d['valeur'])}</b> ({e(d['source'])})<ul>{props}</ul></td></tr>"
            + "".join(f"<tr><td>{c['id']} {e(c['libelle'])}</td><td>{e(bc[c['id']]['statut_ticket'])}</td><td><b>{e(c['statut_ticket'])}</b>"
                      + "".join(f"<br>{e(x['maj'])} : {e(x['texte'])} ({tag(x['statut'])})" for x in c.get("evolution", [])) + "</td></tr>"
                      for c in cur["conditions"]))
    out += f"<h2>État actuel vs baseline</h2><table><tr><th>Élément</th><th>Baseline (30 sept, 09 h)</th><th>Actuel</th></tr>{rows}</table>"
    ba = {a["id"]: a for a in base["actions"]}
    for u in cur["mises_a_jour"]:
        ch = "".join(f"<tr><td>{e(c['champ'])}</td><td>{e(c.get('baseline', ''))}</td><td>{e(c['nouveau'])}</td>"
                     f"<td>{tag(c['statut'], 'n-' + ('proposition' if c['statut'] == 'proposé' else 'décision'))}"
                     f"{(' <span class=small>(déclaré « ' + e(c['statut_demande']) + ' »)</span>') if c['statut_demande'] != c['statut'] else ''}"
                     f"{(' par ' + e(c['par'])) if c.get('par') else ''}</td><td class=quote>« {e(c['preuve'])} »</td></tr>" for c in u["changements"])
        aff = "".join(f"<li><b>{e(a['id'])}</b> {e(ba.get(a['id'], {}).get('action', ''))}<br>→ {e(a['effet'])} <b>{e(a.get('statut', ''))}</b></li>"
                      for a in u.get("actions_touchees", []))
        new = "".join(f"<li><b>{e(a.get('id', ''))}</b> {e(a['action'])} : {e(a.get('executant', 'à confirmer'))}, échéance {e(a.get('echeance', 'à confirmer'))} {nature_tag(a.get('nature', 'recommandation équipe'))}</li>"
                      for a in u.get("nouvelles_actions", []))
        warn = "".join(f"<li>{e(w)}</li>" for w in u["_avertissements"])
        out += f"""<h2>{e(u['id'])} : {e(u['document']['titre'])}</h2>
<p class=muted>Reçu le {e(u['recu_le'])} · fichier <code>{e(u['_fichier'])}</code>. {e(u.get('resume', ''))}</p>
<div class=grid3><div class=card><b>Statut du problème</b><br>{e(u['statut_probleme'])}</div>
<div class=card><b>Décision antérieure (inchangée sans approbation)</b><br>{e(u['decision_anterieure'])}</div>
<div class=card style='border-left-color:var(--prop)'><b>Nouvelle proposition</b><br>{e(u['nouvelle_proposition'])}</div></div>
<h3>Qu'est-ce qui vient de changer?</h3><div class=scroll><table><tr><th>Champ</th><th>Baseline</th><th>Nouveau</th><th>Statut retenu</th><th>Preuve (document reçu)</th></tr>{ch}</table></div>
<h3>Quelles informations précédentes sont affectées?</h3><ul>{aff or '<li>aucune</li>'}</ul>
<h3>Quelles actions devraient être prises?</h3><ul>{new or '<li>aucune nouvelle action</li>'}</ul>
<h3>Ce qui n'a PAS changé (calculé par le code)</h3><ul>{''.join(f'<li>{e(x)}</li>' for x in u['_inchanges'])}</ul>
{('<h3 class=warn>Contrôles appliqués par le code</h3><ul>' + warn + '</ul>') if warn else ''}
<details><summary>Document reçu</summary><pre>{e(u['_document_texte'])}</pre></details>"""
    return out


@app.get("/mise-a-jour", response_class=HTMLResponse)
def maj_page(exercice: int = 0):
    ups = updates.load(FIXTURES) if exercice and not STATIC else updates.load()
    return page(render_updates(ups, bool(exercice)), "Mise à jour NOVA")


def search_block() -> str:
    """Recherche plein texte côté navigateur (sans IA, fonctionne aussi dans l'export statique)."""
    data = []
    for c in kb.load_claims():
        if not c.get("fichier") or c.get("origine") == "ingestion":
            continue
        rep = c.get("repere", "")
        data.append({"f": c["fichier"], "r": rep, "t": re.sub(r"^\[[^\]]*\]\s*", "", c["texte"]), "d": c.get("date", ""),
                     "p": c.get("perime", ""), "u": href("source/" + c["fichier"], evidence.anchor(rep) if rep else "")})
    js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<h2 id=recherche>Rechercher dans le dossier</h2>
<p class="small muted">Recherche plein texte, sans IA, dans {len(data)} passages (fichier et repère). Les accents et la casse sont ignorés. Les résultats sont triés par nombre de termes trouvés.</p>
<input type=text id=q placeholder="ex. : runbook rollback · INV-003 · Canada Central · approuvé 22 octobre" autofocus>
<p id=n class="small muted"></p><div id=res></div>
<script>
const D={js};
const N=s=>s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
D.forEach(x=>x.n=N(x.t+' '+x.f));
const esc=s=>s.replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function run(){{const terms=N(q.value).split(/\\s+/).filter(w=>w.length>1);
 if(!terms.length){{res.innerHTML='';n.textContent='';return}}
 const r=D.map(x=>[terms.filter(t=>x.n.includes(t)).length,x]).filter(a=>a[0]>0).sort((a,b)=>b[0]-a[0]).slice(0,40);
 n.textContent=r.length+' résultat(s) affiché(s)';
 res.innerHTML=r.map(([s,x])=>`<div class=card><a href="${{x.u}}">${{esc(x.f)}} : ${{esc(x.r)}}</a> <span class="small muted">${{esc(x.d)}} · ${{s}}/${{terms.length}} termes</span>`
  +(x.p?` <span class="tag n-signal">${{esc(x.p)}}</span>`:'')+`<div class=small>${{esc(x.t)}}</div></div>`).join('')}}
q.addEventListener('input',run);
const p=new URLSearchParams(location.search).get('q');if(p){{q.value=p;run()}}
</script>"""


@app.get("/sources", response_class=HTMLResponse)
def sources_page():
    rows = ""
    for s in kb.baseline()["sources"]:
        dup = f" (doublon de {s['doublon_de']} : {src_file(s['doublon_de'])})" if s.get("doublon_de") else ""
        cls = "" if s["pertinence"] == "NOVA" else "muted"
        rows += (f"<tr class={cls}><td>{s['id']}</td><td><a href='{href('source/' + s['fichier'])}'>{e(s['fichier'])}</a></td><td>{e(s['date'])}</td>"
                 f"<td>{e(kb.AUTORITE.get(s['autorite'], '?'))}</td><td>{e(s['pertinence'])}{e(dup)}</td><td class=warn>{e(s['perime'])}</td></tr>")
    return page(f"""<h1>Sources du dossier</h1>
<p class=small>Aller à : <a href="#recherche">Recherche</a> · <a href="#catalogue">Catalogue des {len(kb.baseline()['sources'])} fichiers</a></p>
{search_block()}
<h2 id=catalogue>Catalogue des fichiers ({len(kb.baseline()['sources'])})</h2>
<p class="small muted">Autorité, en ordre décroissant : décision formelle et contrat > ticket et compte rendu > courriel > plan, rapport et registre > chat > brouillon. Les doublons et pièces jointes ne comptent pas comme confirmations indépendantes.</p>
<div class=scroll><table><tr><th>ID</th><th>Fichier</th><th>Date</th><th>Autorité</th><th>Pertinence</th><th>Avertissement</th></tr>{rows}</table></div>""", "Sources NOVA")


def source_html(fichier: str) -> str:
    doc = evidence.by_file().get(fichier)
    if not doc:
        raise HTTPException(404, "source inconnue")
    meta = (f"<p class=muted>{doc['id']} · date {e(doc['date'])} · autorité : {e(kb.AUTORITE.get(doc['autorite'], '?'))} · {e(doc['pertinence'])}"
            f"{(' · <span class=warn>' + e(doc['perime']) + '</span>') if doc['perime'] else ''}"
            f" · <a href='{href('raw/' + fichier)}'>fichier original</a></p>")
    k = doc["kind"]
    if k == "png":
        body = (f"<img src='{href('raw/' + fichier)}' alt='{e(doc['name'])}' style='max-width:100%;border:1px solid var(--line)'>"
                f"<h3 id=doc>Transcription manuelle (data/manual/captures.json)</h3><pre>{e(doc['text'])}</pre>")
    elif k == "pdf":
        body = "<div id=doc>" + "".join(f"<h3 id='{evidence.anchor(p['repere'])}'>{e(p['repere'])}</h3><pre>{e(p['texte'])}</pre>" for p in doc["passages"]) + "</div>"
    elif k == "xlsx":
        body = "<table id=doc><tr><th>Repère</th><th>Contenu</th></tr>" + "".join(
            f"<tr id='{evidence.anchor(p['repere'])}'><td>{e(p['repere'])}</td><td>{e(p['texte'])}</td></tr>" for p in doc["passages"]) + "</table>"
    else:
        note = "<p class='small muted'>Vue normalisée du courriel (De, Date, Objet, corps, pièces jointes). Les numéros de ligne sont les repères cités.</p>" if k == "eml" else ""
        body = note + "<div class=lines id=doc>" + "".join(
            f"<div id=L{i}><span>{i}</span>{e(line)}</div>" for i, line in enumerate(doc["text"].splitlines(), 1)) + "</div>"
    return page(f"<h1>{e(fichier)}</h1>{meta}{body}", doc["name"])


@app.get("/source/{fichier:path}", response_class=HTMLResponse)
def source_page(fichier: str):
    return source_html(fichier)


@app.get("/raw/{fichier:path}")
def raw_file(fichier: str):
    path = (corpus.ROOT / fichier).resolve()
    if corpus.ROOT.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/recherche")
def recherche_redirect(q: str = ""):
    """Ancienne page: la recherche fait maintenant partie de /sources."""
    return RedirectResponse("/sources" + (f"?q={quote(q)}" if q else "") + "#recherche")


def md_to_html(md: str) -> str:
    """Rendu Markdown minimal (titres, listes, tableaux, code, gras, liens) pour GUIDE.md, sans dépendance."""
    def inline(s):
        s = e(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
        return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<a href='\2'>\1</a>", s)
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + e("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
            continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.fullmatch(r"[|\s:-]+", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            out.append("<div class=scroll><table>" + "".join(
                "<tr>" + "".join(f"<{'th' if n == 0 else 'td'}>{inline(c)}</{'th' if n == 0 else 'td'}>" for c in r) + "</tr>"
                for n, r in enumerate(rows)) + "</table></div>")
            continue
        m = re.match(r"(#{1,4}) (.*)", ln)
        if m:
            out.append(f"<h{len(m.group(1))}>{inline(m.group(2))}</h{len(m.group(1))}>")
        elif re.match(r"\s*([-*]|\d+\.) ", ln):
            items = []
            while i < len(lines) and re.match(r"\s*([-*]|\d+\.) ", lines[i]):
                items.append("<li>" + inline(re.sub(r"\s*([-*]|\d+\.) ", "", lines[i], count=1)) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


@app.get("/guide", response_class=HTMLResponse)
def guide_page():
    return page(md_to_html((ROOT_DIR / "GUIDE.md").read_text(encoding="utf-8")), "Mode d'emploi NOVA")


# ---------------------------------------------------------------- chat et ingestion (serveur + Ollama)

@app.get("/chat", response_class=HTMLResponse)
def chat_page():
    return page((APP_DIR / "chat_page.html").read_text(encoding="utf-8"), "Chat NOVA")


@app.post("/api/chat")
def api_chat(q: Q):
    from .chat_graph import ask  # importé ici: les pages statiques n'ont pas besoin de LangGraph/Ollama
    r = ask(q.question)
    preuves = [{**p, "lien": href("source/" + p["fichier"], evidence.anchor(p["repere"]) if p.get("repere") else "") if p.get("fichier") else ""}
               for p in r["preuves"]]
    for sec in r["evolution"]:
        for x in sec["entrees"]:
            src = x["source"]
            x["lien"] = href("mise-a-jour") if x["role"] == "mise à jour" else href("source/" + src["fichier"], src.get("anchor", ""))
    rejetees = [{"sujet": x["sujet"], "texte": a["texte"], "problemes": a["problemes"]} for x in r["experts"] for a in x["retirees"]]
    return {"reponse": r["reponse_courte"], "reponse_complete": r["reponse"], "evolution": r["evolution"], "fils": r["fils"],
            "sujets": r["sujets"], "preuves": preuves, "confiance": r["confiance"], "rejetees": rejetees}


@app.get("/ingest", response_class=HTMLResponse)
def ingest_page():
    return page((APP_DIR / "ingest_page.html").read_text(encoding="utf-8"), "Ajouter NOVA")


def _safe_name(nom: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(nom).name).strip("._") or "document.txt"


@app.post("/api/ingest")
async def api_ingest(fichier: UploadFile | None = File(None), texte: str = Form("")):
    """Analyse un document reçu. Le document est conservé dans data/updates/docs/ (preuve de la future mise à jour);
    rien n'est publié tant que le brouillon n'est pas enregistré par /api/updates."""
    from .ingest_graph import ingest
    docs = updates.UPDATES / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    if fichier is not None and fichier.filename:
        nom, data = _safe_name(fichier.filename), await fichier.read()
    else:
        nom, data = f"texte_colle_{len(list(docs.glob('texte_colle_*'))) + 1}.txt", texte.encode("utf-8")
    dest = docs / nom
    if dest.exists() and dest.read_bytes() != data:
        dest = docs / f"{dest.stem}_{len(list(docs.glob(dest.stem + '*'))) + 1}{dest.suffix}"
    dest.write_bytes(data)
    return ingest(corpus.read_bytes(dest.name, data), dest.name, fichier_doc=f"docs/{dest.name}")


class Brouillon(BaseModel):
    brouillon: dict


@app.post("/api/updates")
def api_updates(b: Brouillon):
    """Enregistre un brouillon relu comme mise à jour data/updates/Uxx_*.json, après les garde-fous de updates.check."""
    u = dict(b.brouillon)
    if not re.fullmatch(r"U\d{2}", str(u.get("id", ""))) or not str(u.get("document", {}).get("fichier", "")).startswith("docs/"):
        raise HTTPException(400, "brouillon invalide (id Uxx et document dans docs/ requis)")
    if any(updates.UPDATES.glob(f"{u['id']}_*.json")):
        raise HTTPException(409, f"{u['id']} existe déjà")
    controle = updates.check({**u, "_base": str(updates.UPDATES), "_fichier": ""})
    slug = re.sub(r"[^a-z0-9]+", "_", verify_norm(u["document"].get("titre", "maj")))[:40].strip("_") or "maj"
    path = updates.UPDATES / f"{u['id']}_{slug}.json"
    path.write_text(json.dumps(u, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"enregistre": f"data/updates/{path.name}", "avertissements": controle["_avertissements"],
            "changements_retenus": len(controle["changements"]), "lien": href("mise-a-jour")}


def verify_norm(s: str) -> str:
    from .verify import norm
    return norm(s)
