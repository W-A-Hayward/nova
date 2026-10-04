"""Ingestion: extraction ancrée (citation verbatim vérifiée) -> diff (code) -> experts touchés (parallèle, vérifiés)
-> rapport d'impacts ASSEMBLÉ PAR LE CODE à partir des seuls éléments vérifiés -> ajout à la base (« à valider »).

Anti-hallucination à l'ingestion:
- le document est découpé en morceaux (fini la troncature silencieuse à 6000 caractères);
- chaque claim doit citer la phrase exacte du document; une citation introuvable = claim rejeté;
- les montants / dates / identifiants du claim doivent figurer dans le document;
- type corrigé en code: « décision » / « validation » exigent un vocabulaire d'approbation dans la citation;
- le document est délimité et traité comme donnée (injection d'instructions ignorée);
- le rapport n'est plus rédigé librement par un LLM: ses sections sont assemblées à partir d'éléments vérifiés,
  et « Ce qui n'a PAS changé » (conditions de go-live, budget) est calculé par le code.
"""
import operator, re
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from . import kb, llm, prompts, retrieval, verify
from .chat_graph import verify_batch, REGLES  # noqa: F401  (REGLES: rétro-compatibilité)

TYPES = ["proposition", "décision", "validation", "fait", "signal"]
CHUNK, OVERLAP = 3500, 300
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
    rapport: str


def chunks(texte: str) -> list[str]:
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
                                 correction_type=raison))
    return {"nouveaux": nouveaux, "rejetes": rejetes}


def diff(state: State):
    """Déterministe: un claim existant est « affecté » s'il partage un identifiant (ticket, facture, CR, date) avec un nouveau."""
    toks = set().union(*(kb.tokens(c["texte"] + " " + c["citation"]) for c in state["nouveaux"])) if state["nouveaux"] else set()
    affectes = [c for c in kb.load_claims() if kb.tokens(c["texte"]) & toks]
    sujets = sorted({s for c in state["nouveaux"] + affectes for s in c["sujets"]})
    return {"affectes": affectes, "sujets": sujets}


def fan_out(state: State):
    if not state["nouveaux"]:
        return "report"  # rien d'ancré dans le document: pas d'expert, rapport direct
    return [Send("expert_impact", {"sujet": s, "nouveaux": state["nouveaux"], "affectes": state["affectes"]}) for s in state["sujets"]]


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
    existants = retrieval.select_evidence(requete, s, budget_chars=6000)
    ids = {c["id"] for c in existants}
    existants += [c for c in p["affectes"] if c["id"] not in ids][:15]
    allowed = {c["id"]: c for c in p["nouveaux"] + existants}
    calculs = kb.finance_summary() if s == "finance" else "(sans objet)"
    if s == "finance":
        allowed["CALC"] = {"id": "CALC", "texte": calculs, "source": "calcul NOVA", "type": "fait"}
    out = llm.ask_json(prompts.impact_prompt(kb.render(p["nouveaux"]), kb.render(existants), calculs), system=prompts.impact_system(s),
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
    """Assemblé par le code: aucune phrase n'entre dans le rapport sans avoir passé la vérification."""
    src = state["source"]
    ids_map = {c["id"]: src for c in state["nouveaux"]}
    claims = kb.claims_by_id()
    ids_map.update({i: c["source"] for i, c in claims.items()})
    ids_map["CALC"] = "calcul NOVA"
    seen = set()

    def items(k):
        out = []
        for imp in state["impacts"]:
            for a in imp.get(k, []):
                key = verify.norm(a["texte"])
                if key not in seen:
                    seen.add(key)
                    out.append(a)
        return out

    ch, af, ac = items("changements"), items("affectes"), items("actions")
    L = [f"Rapport d'impacts — document « {state['nom']} » (source {src}). Toutes les nouvelles informations sont « à valider »."]
    L += ["", "Ce qui vient de changer"]
    L += [_ligne(a, ids_map) for a in ch] or ["- (aucun changement vérifié)"]
    L += ["", "Nouveaux claims extraits (à valider)"]
    for c in state["nouveaux"]:
        L.append(f"- {c['type']} ({c['date']}): {c['texte']} — « {c['citation'][:160]} »"
                 + (f" [type corrigé: {c['correction_type']}]" if c.get("correction_type") else ""))
    L += ["", "Informations précédentes affectées"]
    L += [_ligne(a, ids_map) for a in af]
    L += [f"- [{c['source']}] {c['texte']}" for c in state["affectes"][:12]] or ([] if af else ["- (aucune)"])
    L += ["", "Actions à prendre"]
    L += ["- " + ("" if a.get("documentee") else "Recommandation: ") + _ligne(a, ids_map)[2:] for a in ac] or ["- (aucune action vérifiée)"]
    L += ["", "Ce qui n'a PAS changé (calculé par le code)"]
    for tid, st in sorted(kb.ticket_status().items()):
        if st["statut"] != "FERMÉ":
            L.append(f"- {tid}: toujours {st['statut']} [{st['source']}] — un nouveau document ne ferme rien sans validation écrite de son validateur.")
    L.append("- Budget: le registre financier (ledger) n'est pas modifié par l'ingestion; les montants autorisés/facturés/payés restent ceux du calcul NOVA.")
    if state.get("rejetes"):
        L += ["", "Éléments écartés à l'extraction (non ancrés dans le document)"]
        L += [f"- {r['texte']} — {r['raison']}" for r in state["rejetes"]]
    retirees = len({verify.norm(r["texte"]) for i in state["impacts"] for r in i.get("retirees", [])})
    if retirees:
        L.append(f"\n{retirees} conclusion(s) d'expert écartée(s) par la vérification.")
    return {"rapport": "\n".join(L)}


def commit(state: State):
    nouveaux = [{k: v for k, v in c.items() if k != "id"} for c in state["nouveaux"]]
    kb.append_claims(nouveaux)  # ajout seulement, statut « à valider »
    return {}


_g = StateGraph(State)
for n, f in [("extract", extract), ("diff", diff), ("expert_impact", expert_impact), ("report", report), ("commit", commit)]:
    _g.add_node(n, f)
_g.add_edge(START, "extract"); _g.add_edge("extract", "diff")
_g.add_conditional_edges("diff", fan_out, ["expert_impact", "report"])
_g.add_edge("expert_impact", "report"); _g.add_edge("report", "commit"); _g.add_edge("commit", END)
ingest_app = _g.compile()


def ingest(texte: str, nom: str) -> dict:
    n = len([s for s in kb.known_sources() if re.fullmatch(r"N\d+", s)]) + 1
    out = ingest_app.invoke({"texte": texte, "nom": nom, "source": f"N{n:02d}", "impacts": []})
    return {"source": out["source"], "rapport": out["rapport"], "nouveaux": out["nouveaux"], "rejetes": out.get("rejetes", []),
            "affectes": [c["id"] for c in out["affectes"]]}
