"""Ingestion d'un document reçu: extraction (LLM + règles) -> analyse d'impact EN CODE contre l'état actuel des fils
-> analyse complémentaire LLM (vérifiée, optionnelle) -> rapport assemblé par le code -> ajout « à valider » + brouillon de mise à jour.

        extract ──> analyse ──Send──> expert_impact x N ──> report ──> commit
          │ LLM: claims avec citation exacte     │ code (app/impact.py): chaque claim rattaché à un fil et comparé à son
          │ règles: 1 phrase signal = 1 claim    │ état actuel -> nouvelle proposition / livraison ≠ validation / retard /
          │ (ancrage garanti, plancher si le     │ validation par le validateur...; actions affectées; actions recommandées;
          │  LLM ne trouve rien)                 │ ce qui n'a PAS changé; brouillon data/updates
Le LLM ne décide pas de ce qui change: il peut seulement ajouter des remarques, vérifiées comme dans le chat.

Anti-hallucination à l'ingestion (inchangé):
- document découpé en morceaux; chaque claim LLM doit citer une phrase exacte du document, sinon il est rejeté;
- montants / dates / identifiants du claim doivent figurer dans le document; type corrigé par règles;
- le document est délimité et traité comme donnée (injection d'instructions ignorée);
- rien n'est fermé ni approuvé: tout est « à valider », et la mise à jour n'est enregistrée qu'après validation humaine.
"""
import operator, os, re
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from . import fils, impact, kb, llm, prompts, retrieval, updates, verify
from .chat_graph import verify_batch, REGLES  # noqa: F401  (REGLES: rétro-compatibilité)

IMPACT_LLM = os.getenv("NOVA_IMPACT_LLM", "1") != "0"  # analyse complémentaire par les experts (lente; le code suffit)
TYPES = ["proposition", "décision", "validation", "fait", "signal"]
CHUNK, OVERLAP = 3500, 300  # Ollama; avec Gemini le document entier part en une fois (voir chunk_size)


def chunk_size() -> int:
    return 150_000 if llm.grand_contexte() else CHUNK
APPROBATION = re.compile(r"approuv|décid|décision|adopt|entérin|retenu|accept|valid|go\b|d'accord|autoris", re.I)
VALIDATION = re.compile(r"validé|validée|accepté|acceptée|fermé|fermée|clos|approuvé|approuvée|signé|re-?test\w* (ok|réussi)", re.I)
PROPOSITION = re.compile(r"propos|suggèr|recommand|brouillon|draft|pourrai|envisag|souhait|demande", re.I)
LIVRAISON = re.compile(r"corrig|déploy|livr|réglé|conforme|implément|mis en place", re.I)
NEGATION = re.compile(r"\b(pas|non|aucun|aucune|jamais)\b|n'|ne\s", re.I)


class State(TypedDict, total=False):
    texte: str
    nom: str
    source: str
    nouveaux: list[dict]
    rejetes: list[dict]
    affectes: list[dict]
    sujets: list[str]
    impacts: Annotated[list[dict], operator.add]
    analyse: dict
    brouillon: dict
    fichier_doc: str
    rapport: str


def chunks(texte: str) -> list[str]:
    CHUNK = chunk_size()
    if len(texte) <= CHUNK:
        return [texte]
    out, i = [], 0
    while i < len(texte):
        j = min(len(texte), i + CHUNK)
        cut = texte.rfind("\n", i + CHUNK // 2, j)
        j = cut if cut > 0 and j < len(texte) else j
        out.append(texte[i:j])
        if j >= len(texte):
            break
        i = max(j - OVERLAP, i + 1)
    return out


def _valid_extract(o):
    if not isinstance(o, dict) or not isinstance(o.get("claims"), list):
        return 'format attendu: {"claims": [...]}'
    for c in o["claims"]:
        if not isinstance(c, dict) or not isinstance(c.get("texte"), str) or not isinstance(c.get("citation"), str):
            return "chaque claim doit avoir « texte » et « citation » (phrase exacte du document)"
    return None


def fix_type(t: str, citation: str) -> tuple[str, str]:
    """Le type proposé par le LLM est corrigé par des règles codées. Renvoie (type, raison si modifié)."""
    t = t if t in TYPES else "fait"
    if t in ("décision", "validation") and PROPOSITION.search(citation) and not VALIDATION.search(citation):
        return "proposition", "la citation exprime une proposition"
    if t == "décision" and (not APPROBATION.search(citation) or NEGATION.search(citation)):
        return "fait", "aucun vocabulaire d'approbation explicite (ou négation) dans la citation"
    if t == "validation" and (not VALIDATION.search(citation) or NEGATION.search(citation)):
        return ("fait" if LIVRAISON.search(citation) else "signal"), "livraison/annonce ≠ validation"
    return t, ""


def fix_date(d: str, citation: str, doc: str) -> str:
    m = re.fullmatch(r"(20\d\d)-(\d\d)-(\d\d)", str(d).strip())
    if not m:
        return "inconnue"
    md = (int(m.group(2)), int(m.group(3)))
    return d if md in verify.entities(citation)["date"] or md in verify.entities(doc)["date"] else "inconnue"


def extract(state: State):
    doc, nouveaux, rejetes, vus = state["texte"], [], [], set()
    parts = chunks(doc)
    for i, part in enumerate(parts, 1):
        out = llm.ask_json(prompts.extract_prompt(state["nom"], part, i, len(parts)), system=prompts.EXTRACT_SYSTEM,
                           tag="extract", validate=_valid_extract, default={"claims": []})
        for c in out.get("claims", []):
            txt, cit = str(c.get("texte", "")).strip(), str(c.get("citation", "")).strip()
            if not txt:
                continue
            if impact.INJECTION.search(cit) or impact.INJECTION.search(txt):
                rejetes.append({"texte": txt, "raison": "instruction adressée au système dans le document (injection) : ignorée"})
                continue
            if not verify.quote_in(cit, doc):
                rejetes.append({"texte": txt, "raison": "citation introuvable dans le document"})
                continue
            manque = verify.missing(txt, doc)
            if manque:
                rejetes.append({"texte": txt, "raison": "absent du document: " + ", ".join(manque)})
                continue
            cle = verify.norm(txt)
            if cle in vus:
                continue
            vus.add(cle)
            typ, raison = fix_type(str(c.get("type", "")), cit)
            sujets = [s for s in c.get("sujets", []) if s in kb.SUJETS] if isinstance(c.get("sujets"), list) else []
            nouveaux.append(dict(id=f"NEW{len(nouveaux) + 1}", date=fix_date(c.get("date", ""), cit, doc), type=typ, texte=txt,
                                 citation=cit, sujets=sujets or kb.detect_sujets(txt + " " + cit), source=state["source"],
                                 fichier=state["nom"], autorite=None, statut="à valider", origine="ingestion", perime="",
                                 correction_type=raison, extraction="LLM",
                                 nuance=impact.classer(cit)[1] if typ == "fait" else ""))
    for ph in impact.instructions(doc):
        if not any(r["texte"] == ph for r in rejetes):
            rejetes.append({"texte": ph, "raison": "instruction adressée au système dans le document (injection) : ignorée"})
    # plancher déterministe: toute phrase signal non couverte par une citation du LLM devient un claim (citation = la phrase)
    for c in impact.claims_deterministes(doc, state["nom"], state["source"]):
        phrase = verify.norm(c["citation"])
        if any(verify.norm(n["citation"]) in phrase or phrase in verify.norm(n["citation"]) for n in nouveaux):
            continue
        c["sujets"] = kb.detect_sujets(c["texte"])
        nouveaux.append({"id": f"NEW{len(nouveaux) + 1}", **c})
    return {"nouveaux": nouveaux, "rejetes": rejetes}


def analyse(state: State):
    """En code: rattachement aux fils, comparaison à l'état actuel, actions touchées et recommandées, brouillon de mise à jour."""
    a = impact.analyser(state["nouveaux"], state["texte"])
    n = len(updates.load()) + 1
    uid = f"U{n:02d}"
    toks = set().union(*(kb.tokens(c["texte"] + " " + c["citation"]) for c in state["nouveaux"])) if state["nouveaux"] else set()
    affectes = [c for c in kb.load_claims() if kb.tokens(c["texte"]) & toks and c.get("origine") != "ticket"][:15]
    return {"analyse": a, "brouillon": impact.brouillon(a, state.get("fichier_doc") or f"docs/{state['nom']}", uid),
            "affectes": affectes, "sujets": sorted({fils.SUJET[f] for f in a["fils"]})}


def fan_out(state: State):
    if not state["nouveaux"] or not IMPACT_LLM or not state["sujets"]:
        return "report"  # rien d'ancré, ou analyse LLM désactivée: le rapport du code suffit
    return [Send("expert_impact", {"sujet": s, "nouveaux": state["nouveaux"], "affectes": state["affectes"],
                                   "fils": state["analyse"]["fils"], "detectes": state["analyse"]["changements"]}) for s in state["sujets"]]


def _valid_impact(o):
    if not isinstance(o, dict):
        return "objet JSON attendu"
    for k in ("changements", "affectes", "actions"):
        if not isinstance(o.get(k, []), list) or any(not isinstance(x, dict) or not isinstance(x.get("texte"), str) for x in o.get(k, [])):
            return f"« {k} » doit être une liste d'objets avec « texte » et « preuves »"
    return None


def expert_impact(p: dict):
    s = p["sujet"]
    requete = " ".join(c["texte"] for c in p["nouveaux"])
    existants = retrieval.select_evidence(requete, s, budget_chars=40000 if llm.grand_contexte() else 6000)
    ids = {c["id"] for c in existants}
    existants += [c for c in p["affectes"] if c["id"] not in ids][:15]
    # état actuel des fils touchés; avec Gemini, de tous les fils (contexte complet du projet)
    etats = list(fils.pseudo_claims(fils.all_fils() if llm.grand_contexte() else [fils.get(f) for f in p.get("fils", [])]).values())
    existants = etats + existants
    allowed = {c["id"]: c for c in p["nouveaux"] + existants}
    calculs = kb.finance_summary() if s == "finance" else "(sans objet)"
    if s == "finance":
        allowed["CALC"] = {"id": "CALC", "texte": calculs, "source": "calcul NOVA", "type": "fait"}
    detectes = "\n".join(f"- {d['titre']} : {d['relation']}" for d in p.get("detectes", [])) or "(aucun)"
    out = llm.ask_json(prompts.impact_prompt(kb.render(p["nouveaux"]), kb.render(existants), calculs, detectes), system=prompts.impact_system(s),
                       tag=f"impact:{s}", validate=_valid_impact, default={"changements": [], "affectes": [], "actions": []})
    res, retirees = {"sujet": s}, []
    for k in ("changements", "affectes", "actions"):
        ok, rej = verify_batch(out.get(k, []), allowed)
        if k == "actions":  # « documentée » seulement si appuyée par un fait EXISTANT (pas par le document non validé)
            for a in ok:
                a["documentee"] = bool(a.get("documentee")) and not any(i.startswith("NEW") for i in a["preuves"])
        res[k] = ok
        retirees += rej
    res["retirees"] = retirees
    return {"impacts": [res]}


def _ligne(a: dict, ids_map: dict) -> str:
    return f"- {a['texte']} [{', '.join(ids_map.get(i, i) for i in a['preuves'])}]"


def report(state: State):
    """Assemblé par le code. Les sections 1 à 4 viennent de l'analyse en code; la section 5 (LLM) n'entre qu'après vérification."""
    src, a, b = state["source"], state["analyse"], state["brouillon"]
    doc = a["doc"]
    claims = {**kb.claims_by_id(), **fils.pseudo_claims()}
    ids_map = {c["id"]: src for c in state["nouveaux"]}
    ids_map.update({i: c["source"] if not i.startswith("F") else f"état actuel {i}" for i, c in claims.items()})
    ids_map["CALC"] = "calcul NOVA"
    L = [f"Rapport d'impacts — « {state['nom']} » (source {src}), reçu de {doc['auteur'] or 'auteur inconnu'} le {doc['date']}.",
         "Tout est « à valider » : l'ingestion ne ferme, n'approuve et ne remplace rien. État de comparaison : "
         f"baseline du {kb.ref_date()}" + (" + mises à jour enregistrées." if updates.load() else "."),
         "", "1. QU'EST-CE QUI VIENT DE CHANGER ?"]
    if not a["changements"]:
        L.append("- Aucun changement détecté sur les sujets suivis (date, conditions de go-live, budget, responsable...).")
    for fid in dict.fromkeys(ch["fil"] for ch in a["changements"]):
        chs = [ch for ch in a["changements"] if ch["fil"] == fid]
        L += [f"▸ {chs[0]['titre']}", f"  Avant (état actuel) : {chs[0]['baseline']}"]
        for ch in chs:
            L += [f"  Reçu : « {ch['citation']} » ({ch['type']}, {ch['par']})", f"  ⇒ {ch['relation']}  [statut retenu : {ch['statut']}]"]
    L += ["", "2. QUELLES INFORMATIONS PRÉCÉDENTES SONT AFFECTÉES ?"]
    L += [f"- {x['id']} {x['action']} (au 30 sept : {x['baseline']}) → {x['effet']}" for x in a["affectes"]] or ["- Aucune action de la mémoire n'est touchée."]
    for fid in a["fils"]:
        f = fils.get(fid)
        derniers = [e for e in f["entrees"] if e["role"] not in fils.PASSE][-2:]
        L += [f"- Fil « {f['titre']} » : positions les plus récentes avant ce document :"]
        L += [f"    {e['date']} · {fils.ROLE_LABEL.get(e['role'], e['role'])} · {e['texte']} [{fils.memory_short(e['fichier'])}]" for e in derniers]
    L += ["", "3. QUELLES ACTIONS DEVRAIENT ÊTRE PRISES ?"]
    L += [f"- {x['action']} — responsable proposé : {x['executant']} — échéance : {x['echeance']} — {x['nature']}" for x in a["actions"]]
    L += [] if a["actions"] else ["- Aucune action nouvelle déduite."]
    L += ["", "4. CE QUI N'A PAS CHANGÉ (calculé par le code)"] + [f"- {x}" for x in a["inchanges"]]
    # remarques LLM: seulement celles qui s'appuient sur le document reçu (NEWx) et n'en répètent pas une autre ni une citation
    from difflib import SequenceMatcher
    deja = [verify.norm(ch["citation"]) for ch in a["changements"]]
    extra = []
    for imp in state["impacts"]:
        for k in ("changements", "affectes", "actions"):
            for x in imp.get(k, []):
                key = verify.norm(re.sub(r"\s*\(information à valider\)", "", x["texte"]))
                if not any(i.startswith("NEW") for i in x["preuves"]) and k != "actions":
                    continue  # reformulation de la baseline: déjà dans « Avant (état actuel) »
                if any(SequenceMatcher(None, key, d).ratio() > 0.75 for d in deja):
                    continue
                deja.append(key)
                extra.append(("" if k != "actions" or x.get("documentee") else "Recommandation : ") + _ligne(x, ids_map)[2:])
    if extra:
        L += ["", "5. ANALYSE COMPLÉMENTAIRE DES EXPERTS (LLM, vérifiée)"] + [f"- {x}" for x in extra]
    L += ["", "Faits extraits du document (à valider)"]
    for c in state["nouveaux"]:
        L.append(f"- {c['type']}{(' / ' + c['nuance']) if c.get('nuance') else ''} ({c['date']}, {c.get('extraction', 'LLM')}) : "
                 f"{c['texte']}" + (f" [type corrigé : {c['correction_type']}]" if c.get("correction_type") else ""))
    if state.get("rejetes"):
        L += ["", "Éléments écartés à l'extraction (non ancrés dans le document)"]
        L += [f"- {r['texte']} — {r['raison']}" for r in state["rejetes"]]
    retirees = len({verify.norm(r["texte"]) for i in state["impacts"] for r in i.get("retirees", [])})
    if retirees:
        L.append(f"\n{retirees} conclusion(s) d'expert écartée(s) par la vérification.")
    L += ["", f"Brouillon de mise à jour {b['id']} prêt : à relire puis enregistrer pour publier l'état actualisé (page Mise à jour)."]
    return {"rapport": "\n".join(L)}


def commit(state: State):
    nouveaux = [{k: v for k, v in c.items() if k not in ("id", "nuance", "extraction")} for c in state["nouveaux"]]
    kb.append_claims(nouveaux)  # ajout seulement, statut « à valider »
    return {}


_g = StateGraph(State)
for n, f in [("extract", extract), ("analyse", analyse), ("expert_impact", expert_impact), ("report", report), ("commit", commit)]:
    _g.add_node(n, f)
_g.add_edge(START, "extract"); _g.add_edge("extract", "analyse")
_g.add_conditional_edges("analyse", fan_out, ["expert_impact", "report"])
_g.add_edge("expert_impact", "report"); _g.add_edge("report", "commit"); _g.add_edge("commit", END)
ingest_app = _g.compile()


def ingest(texte: str, nom: str, fichier_doc: str = "") -> dict:
    n = len([s for s in kb.known_sources() if re.fullmatch(r"N\d+", s)]) + 1
    out = ingest_app.invoke({"texte": texte, "nom": nom, "source": f"N{n:02d}", "impacts": [], "fichier_doc": fichier_doc})
    return {"source": out["source"], "rapport": out["rapport"], "nouveaux": out["nouveaux"], "rejetes": out.get("rejetes", []),
            "affectes": [c["id"] for c in out["affectes"]], "analyse": {k: v for k, v in out["analyse"].items() if k != "doc"},
            "brouillon": out["brouillon"]}
