"""Interface web NOVA.

/brief (1 page) | /memoire | /reponses | /mise-a-jour | /sources (catalogue + recherche) | /source/<fichier> | /guide | /chat | /ingest
Toutes les pages sauf /chat et /ingest sont rendues sans LLM et exportables en HTML statique (scripts/export_static.py):
en mode STATIC, href() produit des liens relatifs vers des fichiers .html au lieu de routes.
"""
import html
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import corpus, evidence, kb, memory, updates

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
ANSWERS = ROOT_DIR / "data" / "answers_baseline.json"
FIXTURES = ROOT_DIR / "tests" / "fixtures"
STATIC = False  # positionné par scripts/export_static.py

app = FastAPI(title="NOVA")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
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
    txt = label or (f"{short(p['fichier'])}, {rep}" if rep and rep != "document" else short(p["fichier"]))
    return (f"<a class=cite href='{href('source/' + p['fichier'], p.get('anchor', ''))}' "
            f"title='{e(p.get('extrait', ''))}'>{e(txt)}</a>")


def cites(ps: list[dict]) -> str:
    return " ".join(cite(p) for p in ps)


FONTS = [("Public Sans", "normal", "100 900", "PublicSans-normal.woff2"), ("Public Sans", "italic", "100 900", "PublicSans-italic.woff2"),
         ("Source Serif 4", "italic", "200 900", "SourceSerif4-italic.woff2")]

# Système visuel. Le sans-serif (Public Sans) porte l'analyse; le serif italique (Source Serif 4) est réservé aux extraits
# cités mot pour mot: on voit d'un coup d'œil ce qui vient du dossier. Les couleurs encodent un statut, jamais un décor:
# sarcelle = acté (décision, validation, état actuel), ambre = ouvert / à confirmer, sang-de-bœuf = contredit / périmé.
CSS = """
:root{--paper:#F5F6F4;--surface:#FFFFFF;--ink:#1C2433;--muted:#5F6B78;--rule:#D6DBE0;--rule-strong:#AEB6BF;
--acte:#0E5C63;--acte-bg:#E3EFEF;--ouvert:#A9550A;--ouvert-bg:#FBF0E4;--passe:#9A2F3A;--passe-bg:#F7E9EA;--link:#0E5C63;--hl:#FFF1C2;
color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#14181D;--surface:#1B2027;--ink:#E6E9EC;--muted:#9AA5B1;
--rule:#2C333C;--rule-strong:#46505B;--acte:#5DBDBF;--acte-bg:#17302F;--ouvert:#E3A04F;--ouvert-bg:#33261A;--passe:#E58A93;--passe-bg:#35202A;
--link:#7FD0D2;--hl:#4A3F17;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#14181D;--surface:#1B2027;--ink:#E6E9EC;--muted:#9AA5B1;--rule:#2C333C;--rule-strong:#46505B;
--acte:#5DBDBF;--acte-bg:#17302F;--ouvert:#E3A04F;--ouvert-bg:#33261A;--passe:#E58A93;--passe-bg:#35202A;--link:#7FD0D2;--hl:#4A3F17;color-scheme:dark}
/* alias utilisés par les pages de chat et d'ajout */
:root{--bg:var(--paper);--fg:var(--ink);--card:var(--surface);--line:var(--rule);--head:var(--acte);--ok:var(--acte);--warn:var(--ouvert);--bad:var(--passe)}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:400 16px/1.55 "Public Sans",system-ui,sans-serif;
-webkit-font-smoothing:antialiased}
a{color:var(--link);text-underline-offset:2px;text-decoration-thickness:1px}a:hover{text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--ouvert);outline-offset:2px;border-radius:2px}
.masthead{background:var(--surface);border-bottom:1px solid var(--rule);padding:14px 20px 0}
.masthead .id{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 14px;max-width:1150px;margin:0 auto}
.masthead .nova{font-weight:800;font-size:22px;letter-spacing:-.02em;color:var(--ink);text-decoration:none}
.masthead .ref{color:var(--muted);font-size:14px}
.masthead nav{display:flex;flex-wrap:wrap;gap:2px 22px;max-width:1150px;margin:10px auto 0}
.masthead nav a{color:var(--muted);text-decoration:none;font-weight:550;font-size:15px;padding:6px 0 9px;border-bottom:3px solid transparent}
.masthead nav a:hover{color:var(--ink)}
.masthead nav a[aria-current=page]{color:var(--ink);border-bottom-color:var(--acte)}
.masthead nav .off{color:var(--muted);font-size:13px;padding:7px 0}
main{padding:22px 20px 48px;max-width:1150px;margin:0 auto}
h1{font-size:30px;line-height:1.15;font-weight:750;letter-spacing:-.015em;margin:4px 0 6px}
h2{font-size:21px;line-height:1.25;font-weight:700;margin:34px 0 10px;padding-top:12px;border-top:2px solid var(--ink)}
h3{font-size:17px;line-height:1.3;font-weight:650;margin:18px 0 6px}
.lede{color:var(--muted);max-width:72ch;margin:0 0 6px}
p,li{max-width:80ch}
table{border-collapse:collapse;width:100%;margin:8px 0 18px;font-size:15px;font-variant-numeric:tabular-nums}
.money,.verdict .v{font-variant-numeric:tabular-nums}
th{font-weight:600;font-size:13px;color:var(--muted);text-align:left;padding:6px 10px;border-bottom:2px solid var(--rule-strong);vertical-align:bottom}
td{padding:8px 10px;border-bottom:1px solid var(--rule);vertical-align:top;text-align:left}
tbody tr:hover td,table tr:hover td{background:color-mix(in srgb,var(--surface) 70%,transparent)}
.scroll{overflow-x:auto}
pre{white-space:pre-wrap;background:var(--surface);border:1px solid var(--rule);padding:12px;border-radius:6px;font-size:14px}
code{font-size:.92em}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:14px 16px;margin:12px 0}
.muted{color:var(--muted)}.small{font-size:14px}.ok{color:var(--acte)}.warn{color:var(--ouvert)}.bad{color:var(--passe)}
/* rôles: plein = acté, contour = en cours, pointillé = passé ou contredit */
.tag{display:inline-block;font-size:12.5px;font-weight:600;line-height:1.5;padding:0 7px;border-radius:3px;border:1px solid var(--rule-strong);
color:var(--muted);white-space:nowrap;vertical-align:1px}
.r-acte{background:var(--acte);border-color:var(--acte);color:var(--surface)}
.r-ouvert{border-color:var(--ouvert);color:var(--ouvert);background:var(--ouvert-bg)}
.r-passe{border:1px dashed var(--passe);color:var(--passe)}
.engagement{background:var(--acte-bg);border-color:var(--acte);color:var(--acte)}.recommandation{border-style:dashed;color:var(--muted)}
/* compatibilité des anciennes classes n-* (chat) */
.n-décision,.n-validation{background:var(--acte);border-color:var(--acte);color:var(--surface)}
.n-proposition,.n-livraison{border-color:var(--ouvert);color:var(--ouvert);background:var(--ouvert-bg)}.n-signal{border:1px dashed var(--passe);color:var(--passe)}
.passe-txt{color:var(--muted);text-decoration:line-through;text-decoration-color:var(--passe)}
tr.passe td{color:var(--muted)}
a.cite{font-size:13px;white-space:nowrap;margin:0 1px 0 3px;color:var(--muted);text-decoration-color:var(--rule-strong)}
.nw{white-space:nowrap}td.num,th.num{text-align:right;white-space:nowrap}
a.cite:hover{color:var(--link)}
.quote,blockquote{font-family:"Source Serif 4",Georgia,serif;font-style:italic;font-size:16.5px;line-height:1.6;color:var(--ink);
border-left:2px solid var(--rule-strong);margin:4px 0 8px;padding:0 0 0 12px}
:target{background:var(--hl);outline:2px solid var(--ouvert);outline-offset:2px}
.lines{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:8px 0}
.lines div{font-size:15px;line-height:1.6;white-space:pre-wrap;padding:0 12px}
.lines span{color:var(--muted);user-select:none;display:inline-block;width:3em;font:12px "Public Sans",sans-serif}
textarea,input[type=text]{width:100%;padding:10px 12px;border:1px solid var(--rule-strong);border-radius:4px;background:var(--surface);color:var(--ink);font:inherit}
input[type=text]{font-size:17px}
button{font:600 15px "Public Sans",sans-serif;padding:9px 18px;margin-top:8px;background:var(--acte);color:var(--surface);border:none;border-radius:4px;cursor:pointer}
button:disabled{opacity:.5}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.toc{position:sticky;top:0;z-index:2;background:var(--paper);border-bottom:1px solid var(--rule);padding:8px 0;margin:0 0 6px;font-size:14px;
display:flex;flex-wrap:wrap;gap:4px 18px}
.toc a{color:var(--muted)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
label{display:block;font-weight:600;margin:0 0 4px}
/* brief: la décision et ses trois conditions d'abord */
.verdict{display:grid;grid-template-columns:minmax(260px,1fr) 1.6fr;gap:0;border:1px solid var(--rule);border-radius:6px;background:var(--surface);
margin:14px 0 8px;overflow:hidden}
.verdict .date{padding:18px 22px;border-right:1px solid var(--rule)}
.verdict .date .k{color:var(--muted);font-size:14px}
.verdict .date .v{font-size:38px;line-height:1.05;font-weight:780;letter-spacing:-.025em;color:var(--acte);margin:4px 0 8px}
.verdict .date .s{color:var(--ouvert);font-weight:600}
.verdict ol{list-style:none;margin:0;padding:0}
.verdict li{display:grid;grid-template-columns:2.6em 1fr auto;gap:2px 10px;align-items:baseline;padding:11px 18px;border-bottom:1px solid var(--rule);max-width:none}
.verdict li:last-child{border-bottom:0}
.verdict li .c{font-weight:780;font-size:18px;color:var(--ouvert)}
.verdict li .l{font-weight:600}.verdict li .w{grid-column:2;color:var(--muted);font-size:14px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:0 36px}
.brief h2{font-size:17px;margin:20px 0 6px;padding-top:8px;border-top:1px solid var(--ink)}.brief p{margin:4px 0}
.money{font-size:24px;font-weight:750;letter-spacing:-.01em}
/* contradictions: ce qui est écarté face à ce qui est retenu */
.duel{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:8px 0}
.duel>div{padding:10px 12px;border-radius:4px}
.duel .ecarte{background:var(--passe-bg);border-left:3px solid var(--passe)}
.duel .retenu{background:var(--acte-bg);border-left:3px solid var(--acte)}
.duel .who{font-size:14px;color:var(--muted)}
.resolution{margin:6px 0 0}.card>h3:first-child,.card>.qnum+h3{margin-top:0}
.qnum{float:left;font-size:30px;font-weight:780;color:var(--rule-strong);width:2.6em;line-height:1.1;letter-spacing:-.02em}
.answer{overflow:hidden}.answer h3{font-size:19px;margin-top:4px}.answer .rep{font-size:17px;max-width:76ch}
.answer details{clear:both;margin-top:8px}
summary{cursor:pointer;font-weight:600;color:var(--acte)}
@media (max-width:760px){.verdict,.cols,.duel{grid-template-columns:1fr}.verdict .date{border-right:0;border-bottom:1px solid var(--rule)}
.qnum{float:none;display:block;width:auto}h1{font-size:25px}}
@media print{.masthead,.noprint,.toc{display:none}main{padding:0;max-width:none}
body{font-size:9.6px;line-height:1.35;background:#fff;color:#000}
.brief h1{font-size:15px;margin:0}.brief h2{font-size:11px;margin:5px 0 2px;padding-top:3px}
.brief td,.brief th{padding:1px 4px;font-size:9px}.brief table{margin:2px 0 4px}
.verdict{margin:4px 0;border-color:#999}.verdict .date{padding:6px 10px}.verdict .date .v{font-size:20px;margin:1px 0 2px}
.verdict li{padding:3px 10px}.verdict li .c{font-size:11px}.verdict li .w{font-size:9px}
.brief p,.brief .small,.brief .lede,.verdict .date .k,.verdict li .l{font-size:9.6px}
.cols{grid-template-columns:1fr 1fr;gap:0 14px}.verdict{grid-template-columns:1fr 1.5fr}.verdict .date{border-right:1px solid #999;border-bottom:0}
.money{font-size:12px}.tag{font-size:8px;padding:0 3px}a{color:#000;text-decoration:none}a.cite{font-size:8px;color:#555}
@page{size:A4;margin:9mm}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

NAV = [("brief", "Brief"), ("memoire", "Mémoire"), ("reponses", "Réponses Q01–Q10"), ("mise-a-jour", "Mise à jour"),
       ("sources", "Sources et recherche"), ("guide", "Mode d'emploi")]


def font_css() -> str:
    base = "static/fonts/" if STATIC else "/static/fonts/"
    return "".join(f"@font-face{{font-family:'{fam}';font-style:{st};font-weight:{w};font-display:swap;src:url({base}{f}) format('woff2')}}"
                   for fam, st, w, f in FONTS)


def page(body: str, title: str = "NOVA", actif: str = "") -> str:
    nav = "".join(f"<a href='{href(r)}'{' aria-current=page' if r == actif else ''}>{t}</a>" for r, t in NAV)
    nav += ("<span class=off>Chat et Ajouter : avec le serveur</span>" if STATIC else
            "".join(f"<a href='{href(r)}'{' aria-current=page' if r == actif else ''}>{t}</a>" for r, t in (("chat", "Chat"), ("ingest", "Ajouter"))))
    return (f"<!doctype html><html lang=fr><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{e(title)}</title><style>{font_css()}{CSS}</style>"
            f"<header class=masthead><div class=id><a class=nova href='{href('brief')}'>NOVA</a>"
            f"<span class=ref>Mémoire du projet, état au 30 septembre 2026 à 9 h (Montréal)</span></div><nav aria-label='Pages'>{nav}</nav></header>"
            f"<main>{body}</main></html>")


def tag(text: str, cls: str = "") -> str:
    return f"<span class='tag {cls}'>{e(text)}</span>"


ROLE_CLASS = {"décision": "r-acte", "validation": "r-acte", "retenu": "r-acte", "proposition": "r-ouvert", "livraison": "r-ouvert",
              "mise à jour": "r-ouvert", "historique": "r-passe", "écarté": "r-passe", "signal": "r-passe", "fait": ""}
STATUT = {"EN VALIDATION": ("En validation", "r-ouvert"), "OUVERT": ("Ouvert", "r-ouvert"), "FERMÉ": ("Fermé", "r-acte"),
          "LEVÉE": ("Levée", "r-acte")}


def role_tag(role: str) -> str:
    return tag(role, ROLE_CLASS.get(role, ""))


def statut_tag(statut: str) -> str:
    lab, cls = STATUT.get(statut, (statut[:1].upper() + statut[1:].lower(), "r-ouvert"))
    return tag(lab, cls)


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
    return f"{n:,}".replace(",", "\u202f") + "\u00a0$"  # espaces insécables: un montant ne se coupe jamais


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
        f"<tr><td>{cite({'fichier': src_file(f['source']), 'extrait': ''}, f['id'])}</td><td class=nw>{e(f['date'])}</td><td class=num><b>{money(F['total'](f))}</b></td>"
        f"<td>{'<br>'.join(('<span class=bad>' if l['ref'] and l['ref'] not in {c['id'] for c in F['approuves']} else '<span>') + e(money(l['montant']) + ' ' + l['desc']) + '</span>' for l in f['lignes'])}</td>"
        f"<td>{tag(f['statut'], 'r-acte' if f['statut'] == 'payée' else 'r-ouvert')}</td></tr>" for f in F["L"]["factures"])
    na = "; ".join(f"{f['id']} : {money(l['montant'])} « {l['desc']} » (réf. {l['ref']} non approuvé)" for f, l in F["non_aut"])
    def prow(first: str, a: dict) -> str:
        return (f"<tr>{first}<td>{a['id']} {e(a['court'])}</td><td>{e(a['echeance_court'])}</td>"
                f"<td>{nature_tag(a['nature'])}</td><td>{cites(a['preuves'][:1])}</td></tr>")
    prio = ""
    for cid in ("C1", "C2", "C3"):
        c = C[cid]
        ids = c["actions"]
        prio += prow(f"<td rowspan={len(ids)}><b>{cid}</b> {e(c['libelle'])}</td><td rowspan={len(ids)}>{statut_tag(c['statut_ticket'])}</td>", A[ids[0]])
        prio += "".join(prow("", A[aid]) for aid in ids[1:])
    prio += "".join(prow(f"<td class=muted>Hors conditions</td><td>{statut_tag('OUVERT')}</td>", A[aid]) for aid in ("A6", "A7"))
    verdict = "".join(
        f"<li><span class=c>{cid}</span><span class=l>{e(C[cid]['libelle'])}</span>{statut_tag(C[cid]['statut_ticket'])}"
        f"<span class=w>Validation : {e(C[cid]['validateur'])}. Échéance à confirmer.</span></li>" for cid in ("C1", "C2", "C3"))
    body = f"""<div class=brief>
<h1>Brief de reprise</h1>
<p class=lede>Ce qu'il faut savoir pour reprendre NOVA. Montants en CAD, hors taxes. Chaque lien gris ouvre la preuve.
{tag('engagement documenté', 'engagement')} : écrit dans le dossier. {tag('recommandation équipe', 'recommandation')} : notre proposition.
<a class=noprint href="{href('memoire')}">Voir la mémoire complète</a></p>

<section class=verdict aria-label="Date de mise en production">
<div class=date><div class=k>Mise en production approuvée</div><div class=v>22 octobre 2026</div>
<div class=s>Conditionnelle : aucune des trois conditions n'est remplie</div>
<p class=small>Proposée par Boréal le 8 septembre {p('01_Courriels/E05_Retard_integration.eml', "il s'agit d'une proposition de notre part")},
approuvée par le comité de direction le 10 septembre {p(memory.M04, 'Donc approuvé. Le 22 devient la date officielle.')},
reconfirmée sous conditions le 26 septembre {p(memory.M06, "c'est conditionnel à ces trois éléments")}.
Pas un go garanti {p('01_Courriels/E09_Rappel_mise_en_production.eml', 'go garanti')}.</p></div>
<ol>{verdict}</ol>
</section>
<p class=small>Le 15 octobre de la charte et du plan v3 est <span class=passe-txt>périmé</span>.
La cause du report, le connecteur INT-101, est <span class=ok>fermée depuis le 17 septembre</span> {p('03_Tickets/INT-101.txt', 'Validé côté intégration. Je ferme.')}.</p>

<div class=cols>
<div><h2>Responsable</h2>
<p><b>Nicolas Perron</b>, chargé de projet depuis le 16 septembre 2026. Il succède à Élodie Caron, en poste depuis le 7 juillet.
{p('01_Courriels/E06_Transition_charge_projet.eml','Nicolas Perron prend officiellement la charge du projet NOVA')} {p('04_Documents_projet/Note_transition_Elodie_16sept.txt', 'Nicolas Perron reprend le rôle de chargé de projet NOVA')}</p>
<h2>Portée de la phase 1</h2>
<p>SSO (uniquement en production), création et suivi de demandes, pièces jointes, workflow de traitement, tableau de suivi, rapports standards {p(memory.CONTRAT, 'Portée incluse')},
plus les rapports avancés et l'export de synthèse de CR-01 {p(memory.CR01, 'Ajout de rapports avancés et export de synthèse.')}. Données de production au Canada Central {p(memory.ADR, 'Canada Central')}.
Hors portée : l'optimisation mobile avancée (CR-04), reportée à la phase 2 {p(memory.PORTEE, 'La phase 1 doit demeurer utilisable sur mobile')}.</p></div>
<div><h2>Budget</h2>
<p><span class=money>{money(F['autorise'])}</span> autorisés : contrat {money(F['L']['contrat'])} {p(memory.CONTRAT, 'Montant maximal initial')}
{''.join(f"+ {c['id']} {money(c['montant'])}, approuvé le {c['date']} " + p(src_file(c['source']), 'APPROUVÉE') for c in F['approuves'])}.
Non autorisé : {'; '.join(f"{c['id']}, {money(c['montant'])}, {c['statut']}" for c in F['non_approuves'])} {p(memory.CR04, 'BROUILLON - APPROBATION REQUISE')}.</p>
<h2>Factures</h2>
<p>Facturé <b>{money(F['facture'])}</b>, payé <b>{money(F['paye'])}</b>, en validation {money(F['facture'] - F['paye'])}.
<span class=bad>{e(na)}</span>. Les Finances retiennent INV-003 {p('01_Courriels/E07_Facture_003_question.eml', "Peux-tu me transmettre l'approbation correspondante?")} ;
CR-04 ne doit pas être facturé {p('01_Courriels/E10_Fonction_mobile.eml', 'ne doit être engagée ou facturée sans nouvelle approbation')}.
{tag('recommandation équipe', 'recommandation')} Ne pas payer les 18 000 $, demander une facture corrigée ou une note de crédit, valider les 36 000 $ du jalon 3.</p></div>
</div>
<table><tr><th>Facture</th><th>Date</th><th class=num>Total</th><th>Lignes</th><th>Statut</th></tr>{fac_rows}</table>

<h2>Priorités : chaque condition et ses actions</h2>
<table><tr><th>Condition</th><th>Statut</th><th>Action et responsable</th><th>Échéance</th><th>Nature</th><th>Preuve</th></tr>{prio}</table>
<p class="small muted">Aucune échéance précise n'est écrite au dossier : toutes sont à confirmer, au plus tard le 22 octobre.
Olivier veut le runbook final « quelques jours avant » {p(memory.M04, 'au moins quelques jours avant')}.</p>
</div>"""
    return page(body, "Brief NOVA", "brief")


@app.get("/memoire", response_class=HTMLResponse)
def memoire_page():
    m = memory.load_memory()
    tl = "".join(f"<tr{' class=passe' if t['nature'] == 'signal' else ''}><td class=nw>{e(t['date'])}{(' <span class=muted>' + e(t['heure']) + '</span>') if t['heure'] else ''}</td>"
                 f"<td>{role_tag(t['nature'])}</td><td>{e(t['acteur'])}</td><td>{e(t['evenement'])}</td>"
                 f"<td>{cites(t['preuves'])}</td></tr>" for t in m["timeline"])

    def step(x, label):
        if not x:
            return f"<td class=muted>—</td>"
        return (f"<td><b>{e(x.get('valeur', '')) or role_tag(label)}</b><br><span class='small muted'>{e(x['qui'])}, {e(x['quand'])}</span><br>{cite(x['preuve'])}</td>")
    dec = "".join(f"<tr><td><b>{e(d['sujet'])}</b></td>"
                  f"<td>{('<span class=passe-txt>' + e(d['remplace']['valeur']) + '</span><br>' + cite(d['remplace']['preuve'])) if d['remplace'] else '<span class=muted>—</span>'}</td>"
                  f"{step(d['proposition'], 'proposition')}{step(d['decision'], 'décision')}{step(d['validation'], 'validation')}</tr>"
                  for d in m["decisions"])
    contra = ""
    for c in m["contradictions"]:
        *ecartes, retenu = c["affirmations"]  # convention de la mémoire: la dernière affirmation est celle retenue
        bloc = lambda a, cls, titre: (f"<div class={cls}><div class=who>{titre}, {e(a['date'])}, {e(a['autorite'])}</div>"
                                      f"<div class={'passe-txt' if cls == 'ecarte' else ''}>{e(a['texte'])}</div>{cite(a['preuve'])}</div>")
        contra += (f"<article class=card><h3>{e(c['sujet'])}</h3><div class=duel>"
                   + "".join(bloc(a, "ecarte", "Écarté") for a in ecartes) + bloc(retenu, "retenu", "Retenu")
                   + f"</div><p class=resolution><b>Pourquoi</b> ({e(c['regle'])}) : {e(c['resolution'])} {cite(c['preuve_resolution'])}</p></article>")
    cond = "".join(f"<tr><td><b>{c['id']}</b> {e(c['libelle'])}</td><td>{e(c['validateur'])}</td>"
                   f"<td>{statut_tag(c['statut_ticket'])}</td><td>{', '.join(c['actions'])}</td></tr>" for c in m["conditions"])
    act = "".join(f"<tr id='{a['id']}'><td class=nw><b>{a['id']}</b>{(' <span class=muted>' + a['condition'] + '</span>') if a.get('condition') else ''}</td><td>{e(a['action'])}"
                  f"{('<br><span class=\"small muted\">' + e(a['note']) + '</span>') if a.get('note') else ''}</td>"
                  f"<td>{e(a['executant'])} <span class=small>({e(a['statut_resp'])})</span></td><td>{e(a.get('validateur') or '—')}</td>"
                  f"<td>{e(a['echeance'])}</td><td>{e(a['statut'])}</td><td>{nature_tag(a['nature'])}</td><td>{cites(a['preuves'])}</td></tr>"
                  for a in m["actions"])
    reg_doc = evidence.by_file()[memory.REGISTRE]
    reg = "".join(f"<tr><td>{cite({'fichier': memory.REGISTRE, 'repere': p['repere'], 'anchor': evidence.anchor(p['repere'])}, p['repere'].split(', ', 1)[1])}</td>"
                  f"<td>{e(p['texte'])}{' ' + tag('ligne périmée : INT-101 fermé le 17 sept', 'r-passe') if 'R-01' in p['texte'] else ''}</td></tr>"
                  for p in reg_doc["passages"])
    ecart = "".join(f"<li><a href='{href('source/' + x['fichier'])}'>{e(Path(x['fichier']).name)}</a> : {e(x['raison'])}</li>" for x in m["sources_ecartees"])
    body = f"""<h1>Mémoire opérationnelle</h1>
<p class=lede>Ce qui s'est passé, ce qui a été décidé, ce qui se contredit et ce qui reste à faire, au {e(m['ref_date'])} (Montréal).
Cette baseline n'est jamais réécrite : les nouvelles informations passent par <a href="{href('mise-a-jour')}">Mise à jour</a>.</p>
<p class=small>Lire les rôles : {role_tag('décision')} {role_tag('validation')} acté ;
{role_tag('proposition')} {role_tag('livraison')} en cours, une livraison n'est pas une validation ;
{role_tag('signal')} affirmation non fiable ou périmée ; {role_tag('fait')} fait.</p>
<nav class=toc aria-label="Sections"><a href="#chrono">Chronologie</a><a href="#decisions">Décisions</a><a href="#contradictions">Contradictions</a>
<a href="#actions">Conditions et actions</a><a href="#registre">Registre des risques</a><a href="#ecartees">Sources écartées</a></nav>
<h2 id=chrono>Chronologie ({len(m['timeline'])} événements)</h2>
<div class=scroll><table><tr><th>Date</th><th>Nature</th><th>Qui</th><th>Événement</th><th>Preuve</th></tr>{tl}</table></div>
<h2 id=decisions>Décisions, de la proposition à la validation</h2>
<div class=scroll><table><tr><th>Sujet</th><th>Remplace</th><th>Proposition</th><th>Décision</th><th>Validation / suite</th></tr>{dec}</table></div>
<h2 id=contradictions>Contradictions résolues ({len(m['contradictions'])})</h2>
<p class=lede>Chaque contradiction est tranchée par l'autorité de la source ou par la date des faits, jamais par la date du fichier.</p>{contra}
<h2 id=actions>Conditions de go-live et actions restantes</h2>
<table><tr><th>Condition (M06, 26 sept)</th><th>Validateur</th><th>Statut au 30 sept</th><th>Actions</th></tr>{cond}</table>
<div class=scroll><table><tr><th>ID</th><th>Action</th><th>Exécutant (statut)</th><th>Validateur</th><th>Échéance</th><th>Statut</th><th>Nature</th><th>Preuves</th></tr>{act}</table></div>
<h2 id=registre>Registre des risques (29 sept), lu cellule par cellule</h2>
<table><tr><th>Cellules</th><th>Contenu</th></tr>{reg}</table>
<h2 id=ecartees>Sources écartées ou non indépendantes</h2><ul>{ecart}</ul>"""
    return page(body, "Mémoire NOVA", "memoire")


@app.get("/reponses", response_class=HTMLResponse)
def reponses_page():
    out = ("<h1>Réponses aux dix questions</h1><p class=lede>État au 30 septembre 2026 à 9 h. Chaque source ouvre le fichier au repère exact ; "
           "les extraits en italique sont cités mot pour mot et vérifiés automatiquement.</p>")
    for qid, q in load_answers().items():
        srcs = ""
        for s in q["sources"]:
            loc = evidence.locate(s["fichier"], s["extrait"]) or {"repere": "?", "anchor": ""}
            indep = "" if s.get("independante", True) else " " + tag("non indépendante : " + s.get("note", "pièce jointe ou doublon"), "r-passe")
            srcs += (f"<li><a href='{href('source/' + s['fichier'], loc['anchor'])}'>{e(short(s['fichier']))}</a>, {e(s['repere'])} "
                     f"<span class='small muted'>({e(loc['repere'])})</span>{indep}<blockquote>{e(s['extrait'])}</blockquote></li>")
        out += (f"<article class='card answer' id={qid}><div class=qnum>{qid}</div><h3>{e(q['question'])}</h3>"
                f"<p class=rep>{e(q['reponse'])}</p><p class=muted><b>Nuance.</b> {e(q['nuance'])}</p>"
                f"<details><summary>Voir les {len(q['sources'])} preuves</summary><ul>{srcs}</ul></details></article>")
    return page(out, "Réponses Q01–Q10", "reponses")


STATUT_MAJ = {"proposé": "r-ouvert", "approuvé": "r-acte", "validé": "r-acte", "signal": "r-passe", "fait": ""}


def champ_label(champ: str) -> str:
    """date_mise_en_production -> « Date de mise en production » ; condition:C2 -> « C2 Fermeture d'ACC-303 »."""
    if champ == "date_mise_en_production":
        return "Date de mise en production"
    m = re.fullmatch(r"condition:(C\d)", champ)
    if m:
        c = next((c for c in memory.load_memory()["conditions"] if c["id"] == m.group(1)), None)
        return f"{m.group(1)} {c['libelle']}" if c else m.group(1)
    return champ


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
            + "".join(f"<tr><td>{c['id']} {e(c['libelle'])}</td><td>{statut_tag(bc[c['id']]['statut_ticket'])}</td><td>{statut_tag(c['statut_ticket'])}"
                      + "".join(f"<br>{e(x['maj'])} : {e(x['texte'])} ({tag(x['statut'])})" for x in c.get("evolution", [])) + "</td></tr>"
                      for c in cur["conditions"]))
    out += f"<h2>État actuel comparé à la baseline</h2><table><tr><th>Élément</th><th>Baseline (30 sept, 09 h)</th><th>Actuel</th></tr>{rows}</table>"
    ba = {a["id"]: a for a in base["actions"]}
    for u in cur["mises_a_jour"]:
        ch = "".join(f"<tr><td><b>{e(champ_label(c['champ']))}</b></td><td>{e(c.get('baseline', ''))}</td><td>{e(c['nouveau'])}</td>"
                     f"<td>{tag(c['statut'], STATUT_MAJ.get(c['statut'], ''))}"
                     f"{(' <span class=small>(déclaré « ' + e(c['statut_demande']) + ' »)</span>') if c['statut_demande'] != c['statut'] else ''}"
                     f"{(' par ' + e(c['par'])) if c.get('par') else ''}</td><td class=quote>« {e(c['preuve'])} »</td></tr>" for c in u["changements"])
        aff = "".join(f"<li><b>{e(a['id'])}</b> {e(ba.get(a['id'], {}).get('action', ''))}<br>→ {e(a['effet'])} <b>{e(a.get('statut', ''))}</b></li>"
                      for a in u.get("actions_touchees", []))
        new = "".join(f"<li><b>{e(a.get('id', ''))}</b> {e(a['action'])} : {e(a.get('executant', 'à confirmer'))}, échéance {e(a.get('echeance', 'à confirmer'))} {nature_tag(a.get('nature', 'recommandation équipe'))}</li>"
                      for a in u.get("nouvelles_actions", []))
        warn = "".join(f"<li>{e(w)}</li>" for w in u["_avertissements"])
        out += f"""<h2>{e(u['id'])} : {e(u['document']['titre'])}</h2>
<p class=muted>Reçu le {e(u['recu_le'])}, fichier <code>{e(u['_fichier'])}</code>. {e(u.get('resume', ''))}</p>
<div class=grid3><div class=card><b>Statut du problème</b><br>{e(u['statut_probleme'])}</div>
<div class=card><b>Décision antérieure (inchangée sans approbation)</b><br>{e(u['decision_anterieure'])}</div>
<div class=card style='border-color:var(--ouvert);background:var(--ouvert-bg)'><b>Nouvelle proposition</b><br>{e(u['nouvelle_proposition'])}</div></div>
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
    return page(render_updates(ups, bool(exercice)), "Mise à jour NOVA", "mise-a-jour")


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
    return f"""<h2 id=recherche class=sr>Recherche</h2>
<p class="small muted">Recherche plein texte, sans IA, dans {len(data)} passages (fichier et repère). Les accents et la casse sont ignorés. Les résultats sont triés par nombre de termes trouvés.</p>
<label class=small for=q>Rechercher dans le dossier</label>
<input type=text id=q placeholder="Par exemple : runbook rollback, INV-003, Canada Central" autofocus>
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
 res.innerHTML=r.map(([s,x])=>`<div class=card><a href="${{x.u}}">${{esc(x.f)}} : ${{esc(x.r)}}</a> <span class="small muted">${{esc(x.d)}}, ${{s}} terme(s) sur ${{terms.length}}</span>`
  +(x.p?` <span class="tag n-signal">${{esc(x.p)}}</span>`:'')+`<div class=small>${{esc(x.t)}}</div></div>`).join('')}}
q.addEventListener('input',run);
const p=new URLSearchParams(location.search).get('q');if(p){{q.value=p;run()}}
</script>"""


@app.get("/sources", response_class=HTMLResponse)
def sources_page():
    rows = ""
    for s in kb.baseline()["sources"]:
        dup = f" (doublon de {s['doublon_de']} : {src_file(s['doublon_de'])})" if s.get("doublon_de") else ""
        cls = "" if s["pertinence"] == "NOVA" else "passe"
        rows += (f"<tr class='{cls}'><td>{s['id']}</td><td><a href='{href('source/' + s['fichier'])}'>{e(s['fichier'])}</a></td><td>{e(s['date'])}</td>"
                 f"<td>{e(kb.AUTORITE.get(s['autorite'], '?'))}</td><td>{e(s['pertinence'])}{e(dup)}</td><td class=warn>{e(s['perime'])}</td></tr>")
    return page(f"""<h1>Sources du dossier</h1>
<p class=lede>Cherchez un mot, une date ou un identifiant dans tous les passages du dossier, ou parcourez les fichiers.
<a href="#catalogue">Aller au catalogue des {len(kb.baseline()['sources'])} fichiers</a></p>
{search_block()}
<h2 id=catalogue>Catalogue des fichiers ({len(kb.baseline()['sources'])})</h2>
<p class="small muted">Autorité, en ordre décroissant : décision formelle et contrat > ticket et compte rendu > courriel > plan, rapport et registre > chat > brouillon. Les doublons et pièces jointes ne comptent pas comme confirmations indépendantes.</p>
<div class=scroll><table><tr><th>ID</th><th>Fichier</th><th>Date</th><th>Autorité</th><th>Pertinence</th><th>Avertissement</th></tr>{rows}</table></div>""", "Sources NOVA", "sources")


def source_html(fichier: str) -> str:
    doc = evidence.by_file().get(fichier)
    if not doc:
        raise HTTPException(404, "source inconnue")
    meta = (f"<p class=lede>Source {doc['id']}, datée du {e(doc['date'])}. Autorité : {e(kb.AUTORITE.get(doc['autorite'], '?'))}. "
            f"Pertinence : {e(doc['pertinence'])}.{(' ' + tag(doc['perime'], 'r-passe')) if doc['perime'] else ''} "
            f"<a href='{href('raw/' + fichier)}'>Ouvrir le fichier original</a></p>")
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
    return page(f"<p class=small><a href='{href('sources')}'>Sources</a> / {e(Path(fichier).parent.name)}</p><h1>{e(doc['name'])}</h1>{meta}{body}", doc["name"], "sources")


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
    return page(md_to_html((ROOT_DIR / "GUIDE.md").read_text(encoding="utf-8")), "Mode d'emploi NOVA", "guide")


# ---------------------------------------------------------------- chat et ingestion (serveur + Ollama)

@app.get("/chat", response_class=HTMLResponse)
def chat_page():
    return page((APP_DIR / "chat_page.html").read_text(encoding="utf-8"), "Chat NOVA", "chat")


# Session de travail en mémoire du processus: la conversation et la dernière analyse d'ajout survivent aux changements
# de page ou d'onglet (et une réponse en cours se termine même si on quitte la page), mais pas à l'arrêt du serveur.
SESSION: dict = {"chat": [], "ingest": None, "saisie": {}}
_session_lock = threading.Lock()


class Saisie(BaseModel):
    cle: str
    valeur: str


@app.get("/api/session/saisie")
def session_saisie():
    return SESSION["saisie"]


@app.put("/api/session/saisie")
def session_saisie_maj(m: Saisie):
    """Texte tapé mais pas encore envoyé (question du chat, texte collé dans Ajouter)."""
    if m.cle in ("chat_question", "ingest_texte"):
        SESSION["saisie"][m.cle] = m.valeur[:200_000]
    return {"ok": True}


@app.get("/api/session/chat")
def session_chat():
    return SESSION["chat"]


@app.delete("/api/session/chat")
def session_chat_effacer():
    with _session_lock:
        SESSION["chat"] = [m for m in SESSION["chat"] if m.get("statut") == "en cours"]  # une réponse en cours n'est pas perdue
    return SESSION["chat"]


@app.post("/api/chat")
def api_chat(q: Q):
    with _session_lock:
        SESSION["chat"].append({"role": "user", "texte": q.question})
        msg = {"role": "assistant", "statut": "en cours", "question": q.question, "debut": time.time()}
        SESSION["chat"].append(msg)
    try:
        j = _chat(q.question)
    except Exception as ex:  # l'échec est conservé dans la conversation (ex.: Ollama arrêté)
        msg.update(statut="erreur", message=f"{type(ex).__name__}: {ex}")
        raise HTTPException(503, msg["message"])
    msg.update(statut="ok", reponse=j)
    return j


def _chat(question: str) -> dict:
    from collections import Counter
    from . import llm
    from .chat_graph import ask  # importé ici: les pages statiques n'ont pas besoin de LangGraph/Ollama
    avant = Counter(llm.USAGE)
    r = ask(question)
    modeles = llm.fournisseurs_depuis(avant)
    preuves = [{**p, "lien": href("source/" + p["fichier"], evidence.anchor(p["repere"]) if p.get("repere") else "") if p.get("fichier") else ""}
               for p in r["preuves"]]
    for sec in r["evolution"]:
        for x in sec["entrees"]:
            src = x["source"]
            x["lien"] = href("mise-a-jour") if x["role"] == "mise à jour" else href("source/" + src["fichier"], src.get("anchor", ""))
    rejetees = [{"sujet": x["sujet"], "texte": a["texte"], "problemes": a["problemes"]} for x in r["experts"] for a in x["retirees"]]
    return {"reponse": r["reponse_courte"], "reponse_complete": r["reponse"], "evolution": r["evolution"], "fils": r["fils"],
            "sujets": r["sujets"], "preuves": preuves, "confiance": r["confiance"], "rejetees": rejetees, "modeles": modeles}


@app.get("/ingest", response_class=HTMLResponse)
def ingest_page():
    return page((APP_DIR / "ingest_page.html").read_text(encoding="utf-8"), "Ajouter NOVA", "ingest")


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
    SESSION["ingest"] = {"statut": "en cours", "nom": dest.name, "debut": time.time()}
    from collections import Counter
    from . import llm
    avant = Counter(llm.USAGE)
    try:  # l'analyse est longue: dans un thread, pour que la page puisse interroger l'état pendant ce temps
        out = await run_in_threadpool(ingest, corpus.read_bytes(dest.name, data), dest.name, f"docs/{dest.name}")
        out["modeles"] = llm.fournisseurs_depuis(avant)
    except Exception as ex:
        SESSION["ingest"] = {"statut": "erreur", "nom": dest.name, "message": f"{type(ex).__name__}: {ex}"}
        raise HTTPException(503, SESSION["ingest"]["message"])
    SESSION["ingest"] = {"statut": "ok", "nom": dest.name, "resultat": out, "brouillon_texte": None, "enregistrement": None}
    return out


class SessionIngest(BaseModel):
    brouillon_texte: str | None = None


@app.get("/api/session/ingest")
def session_ingest():
    return SESSION["ingest"]


@app.put("/api/session/ingest")
def session_ingest_maj(m: SessionIngest):
    """Conserve les corrections faites au brouillon avant enregistrement."""
    if SESSION["ingest"] and SESSION["ingest"].get("statut") == "ok":
        SESSION["ingest"]["brouillon_texte"] = m.brouillon_texte
    return {"ok": True}


@app.delete("/api/session/ingest")
def session_ingest_effacer():
    if not (SESSION["ingest"] and SESSION["ingest"].get("statut") == "en cours"):
        SESSION["ingest"] = None
    return SESSION["ingest"]


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
    res = {"enregistre": f"data/updates/{path.name}", "avertissements": controle["_avertissements"],
           "changements_retenus": len(controle["changements"]), "lien": href("mise-a-jour")}
    if SESSION["ingest"] and SESSION["ingest"].get("statut") == "ok":
        SESSION["ingest"]["enregistrement"] = res
    return res


def verify_norm(s: str) -> str:
    from .verify import norm
    return norm(s)
