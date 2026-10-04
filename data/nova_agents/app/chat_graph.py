"""Chat: fils thématiques (code) -> experts en parallèle (preuves épinglées et étiquetées, JSON, vérification code + LLM,
une révision) -> synthèse courte à partir des seules affirmations vérifiées -> contrôle phrase par phrase
-> finalisation: réponse + évolution et sources contradictoires + inconnus, assemblés par le code.

        route ──Send──> expert x N ──> synthesize ⟲ (≤ NOVA_SYNTH_TRIES) ──> finalize
          │ fils.select (code)  │ faits épinglés: [Fxx] ÉTAT ACTUEL + positions datées du fil (HISTORIQUE, PROPOSITION...)
          │                     │ check_affirmation (code) + llm_verify (agent) -> révision (1x)
          └ sujets = fils       └ ne renvoie que le vérifié

Raisonnement temporel (README: « une date de fichier récente ne garantit pas une information exacte »):
l'état actuel d'un sujet est tranché en code (app/fils.py): fait documenté le plus récent d'une source compétente, daté
par la date du fait. Les positions antérieures ou contredites sont gardées, étiquetées, et exposées sous la réponse
pour montrer l'évolution des décisions.
"""
import operator, os, re
from difflib import SequenceMatcher
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from . import fils, kb, llm, prompts, retrieval, verify

VERIFY_LLM = os.getenv("NOVA_VERIFY_LLM", "1") != "0"   # agent vérificateur (coûte 1 appel par expert)
REVISE = os.getenv("NOVA_REVISE", "1") != "0"           # une passe de correction des affirmations rejetées
SYNTH_TRIES = int(os.getenv("NOVA_SYNTH_TRIES", "2"))
EVIDENCE_CHARS = int(os.getenv("NOVA_EVIDENCE_CHARS", "8000"))
MAX_EXPERTS = int(os.getenv("NOVA_MAX_EXPERTS", "3"))
REGLES = prompts.REGLES  # rétro-compatibilité


class State(TypedDict, total=False):
    question: str
    sujets: list[str]
    fils: list[str]
    reponses: Annotated[list[dict], operator.add]
    brouillon: str
    problemes: list
    tentatives: int
    final: str
    courte: str
    evolution: list[dict]
    preuves: list[dict]
    confiance: str


def all_claims() -> dict[str, dict]:
    """Claims du dossier + états actuels des fils (Fxx), tous citables."""
    return {**kb.claims_by_id(), **fils.pseudo_claims()}


# ------------------------------------------------------------------------------------------------ routage
def route(state: State):
    q = state["question"]
    choisis = fils.select(q)
    if choisis:  # les fils disent quels experts consulter: pas d'appel LLM, pas d'expert hors sujet
        sujets = list(dict.fromkeys(fils.SUJET[f] for f in choisis))[:MAX_EXPERTS]
        return {"fils": choisis, "sujets": sujets}

    def valid(o):
        return None if isinstance(o, dict) and isinstance(o.get("sujets"), list) else 'format attendu: {"sujets": [...]}'
    out = llm.ask_json(prompts.route_prompt(q), system=prompts.ROUTE_SYSTEM, tag="route", validate=valid, default={"sujets": []})
    sujets = [s for s in out.get("sujets", []) if s in kb.SUJETS]
    t = q.lower()  # filet de sécurité: les mots-clés détectés en code s'ajoutent au choix du LLM
    sujets += [s for s, ws in kb.MOTS.items() if any(w in t for w in ws) and s not in sujets]
    return {"fils": [], "sujets": [s for s in kb.SUJETS if s in sujets][:MAX_EXPERTS] or list(kb.SUJETS)[:MAX_EXPERTS]}


def fan_out(state: State):
    return [Send("expert", {"sujet": s, "question": state["question"], "fils": state.get("fils", [])}) for s in state["sujets"]]


# ------------------------------------------------------------------------------------------------ experts
def _valid_expert(o):
    if not isinstance(o, dict) or not isinstance(o.get("affirmations", []), list):
        return 'format attendu: {"hors_domaine": bool, "affirmations": [{"texte": "...", "preuves": ["C0xx"]}], "inconnu": [...]}'
    for a in o.get("affirmations", []):
        if not isinstance(a, dict) or not isinstance(a.get("texte"), str) or not isinstance(a.get("preuves", []), (list, str)):
            return "chaque affirmation doit avoir « texte » (chaîne) et « preuves » (liste d'identifiants Cxxx)"
    return None


def verify_batch(affs: list[dict], allowed: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Code d'abord (gratuit, précis), puis agent vérificateur sur ce qui a passé le code."""
    checked = [verify.check_affirmation(a, allowed) for a in affs if isinstance(a, dict) and str(a.get("texte", "")).strip()]
    ok = [c for c in checked if not c["problemes"]]
    if VERIFY_LLM and ok:
        for c, v in zip(ok, verify.llm_verify(ok, allowed)):
            c["verdict"] = v
            if v and v["verdict"] != "SUPPORTE":
                c["problemes"].append(f"vérificateur: {v['verdict']} — {v['raison']}")
    return [c for c in checked if not c["problemes"]], [c for c in checked if c["problemes"]]


def pinned_evidence(fids: list[str], sujet: str, max_positions: int = 14) -> list[dict]:
    """États actuels des fils choisis + positions datées des fils du domaine de l'expert, avec étiquette temporelle."""
    if not fids:
        return []
    choisis = [fils.get(f) for f in fids]
    pcs = fils.pseudo_claims(choisis)
    labels, passe = fils.temporal_labels(choisis), fils.passe_ids(choisis)
    claims = kb.claims_by_id()
    domaine = {sujet, *kb.VOISINS.get(sujet, [])}
    out = [pcs[f] for f in fids]
    pos = []
    for f in choisis:
        if f["sujet"] not in domaine and len(choisis) > 1:
            continue
        for e in reversed(f["entrees"]):  # du plus récent au plus ancien: l'actuel d'abord si le budget coupe
            c = claims.get(e.get("claim") or "")
            if c and c["id"] not in {p["id"] for p in pos}:
                pos.append({**c, "etiquette": labels.get(c["id"], ""), "passe": c["id"] in passe})
    return out + pos[:max_positions]


def _evidence(question: str, sujet: str, budget: int, fids: list[str]):
    evid = retrieval.select_evidence(question, sujet, budget_chars=budget, pinned=pinned_evidence(fids, sujet))
    allowed = {c["id"]: c for c in evid}
    calculs = "(sans objet)"
    if sujet == "finance" or "finance" in kb.detect_sujets(question):
        calculs = kb.finance_summary()
        allowed["CALC"] = {"id": "CALC", "texte": calculs, "source": "calcul NOVA", "type": "fait", "date": kb.baseline()["baseline_au"][:10]}
    return evid, allowed, calculs


def expert(p: dict):
    s, q = p["sujet"], p["question"]
    system = prompts.expert_system(s)
    budget = min(EVIDENCE_CHARS, llm.prompt_budget_chars() - len(system) - 2500)
    out = None
    for _ in range(3):  # en cas de dépassement de contexte, on réduit les preuves au lieu de laisser Ollama tronquer
        evid, allowed, calculs = _evidence(q, s, budget, p.get("fils", []))
        faits = kb.render(evid)
        try:
            out = llm.ask_json(prompts.expert_prompt(q, faits, calculs), system=system, tag=f"expert:{s}", validate=_valid_expert,
                               default={"hors_domaine": False, "affirmations": [], "inconnu": []})
            break
        except llm.ContextOverflow:
            budget //= 2
    out = out or {"affirmations": [], "inconnu": []}
    affs = out.get("affirmations", [])
    ok, rejet = verify_batch(affs, allowed)
    if rejet and REVISE:
        rev = llm.ask_json(prompts.revision_prompt(q, faits, calculs, rejet), system=system, tag=f"revision:{s}",
                           validate=_valid_expert, default={"affirmations": []})
        ok2, rejet2 = verify_batch(rev.get("affirmations", []), allowed)
        ok += ok2
        for c in rejet:
            c["revision"] = "corrigée" if ok2 else "retirée"
        rejet += rejet2  # on garde la trace de tout ce qui a été rejeté (affiché dans les détails de l'API)
    # « inconnu » est aussi du texte généré: on écarte ce qui contient des entités absentes des preuves
    tout = "\n".join(c["texte"] for c in allowed.values())
    inconnu = [str(x) for x in out.get("inconnu", []) if isinstance(x, str) and x.strip() and not verify.missing(str(x), tout)]
    return {"reponses": [{"sujet": s, "hors_domaine": bool(out.get("hors_domaine")) and not ok, "affirmations": ok,
                          "retirees": rejet, "inconnu": inconnu, "preuves_fournies": sorted(allowed)}]}


# ------------------------------------------------------------------------------------------------ synthèse + contrôle
def _verified(state: State) -> list[dict]:
    """Affirmations vérifiées de tous les experts, sans quasi-doublons, celles qui citent un état actuel [Fxx] d'abord."""
    out = []
    for r in state["reponses"]:
        for a in r["affirmations"]:
            k = verify.norm(a["texte"])
            if any(SequenceMatcher(None, k, verify.norm(b["texte"])).ratio() > 0.8 for b in out):
                continue
            out.append(a)
    return sorted(out, key=lambda a: not any(p.startswith("F") for p in a["preuves"]))


def _allowed_for_synthesis(affs: list[dict]) -> dict[str, dict]:
    claims = all_claims()
    allowed = {i: claims[i] for a in affs for i in a["preuves"] if i in claims}
    if any("CALC" in a["preuves"] for a in affs):
        allowed["CALC"] = {"id": "CALC", "texte": kb.finance_summary(), "source": "calcul NOVA", "type": "fait"}
    return allowed


def synthesize(state: State):
    affs = _verified(state)
    n = state.get("tentatives", 0) + 1
    if not affs:
        return {"brouillon": "", "problemes": [], "tentatives": n}
    draft = llm.ask_text(prompts.synth_prompt(state["question"], affs, state.get("problemes") or None),
                         system=prompts.SYNTH_SYSTEM, tag="synthese")
    draft = re.sub(r"^\s*(la )?r[ée]ponse( finale)?( est)?\s*:\s*", "", draft, flags=re.I)
    return {"brouillon": draft, "problemes": verify.check_prose(draft, _allowed_for_synthesis(affs)), "tentatives": n}


def after_synthesis(state: State) -> str:
    return "synthesize" if state.get("problemes") and state.get("tentatives", 0) < SYNTH_TRIES else "finalize"


def _expand(ids, claims: dict[str, dict]) -> list[str]:
    """Un état actuel [Fxx] renvoie aux claims qui l'établissent."""
    out = []
    for i in ids:
        out += claims[i].get("claims", []) if i.startswith("F") and i in claims else [i]
    return list(dict.fromkeys(out))


def _confiance(affs: list[dict]) -> str:
    claims = all_claims()
    cites = [claims[i] for a in affs for i in _expand(a["preuves"], claims) if i in claims]
    srcs = {kb.canonical_source(c["source"]) for c in cites if re.fullmatch(r"[SN]\d+", c["source"])}
    auts = [c["autorite"] for c in cites if c.get("autorite")]
    a_valider = any(c.get("statut") == "à valider" for c in cites)
    best = min(auts) if auts else None
    niveau = ("Faible" if a_valider or not srcs else
              "Haute" if len(srcs) >= 2 and best is not None and best <= 2 else "Moyenne")
    return (f"Confiance (calculée par le code) : {niveau} — {len(srcs)} source(s) distincte(s), meilleure autorité : "
            f"{kb.AUTORITE.get(best, 'n/a')}{' ; contient des informations à valider' if a_valider else ''}")


def label(cid: str, claims: dict[str, dict]) -> str:
    """Étiquette lisible d'une preuve: « M04 · ligne 23 », « état actuel F01 », « calcul NOVA »."""
    if cid == "CALC":
        return "calcul NOVA"
    if cid.startswith("F"):
        return f"état actuel {cid}"
    c = claims.get(cid)
    if not c:
        return cid
    rep = c.get("repere", "")
    return fils.memory_short(c.get("fichier", "")) + (f" · {rep}" if rep and rep != "document" else "")


def afficher(text: str, claims: dict[str, dict]) -> str:
    def sub(m):
        out = list(dict.fromkeys(label(pid, claims) for pid in verify.CITE_RE.findall(m.group(0).upper())))
        return "[" + " ; ".join(out) + "]" if out else m.group(0)
    return re.sub(r"\[[^\[\]]*\b(?:C\d{3,4}|NEW\d+|CALC|F\d{2})\b[^\[\]]*\]", sub, text)


def finalize(state: State):
    affs = _verified(state)
    claims = all_claims()
    choisis = [fils.get(f) for f in state.get("fils", [])]
    notes = []
    if not affs:
        texte = "Je ne trouve pas d'information vérifiable qui réponde directement à cette question dans le dossier NOVA."
        if choisis:
            texte += " État actuel des sujets liés :\n" + "\n".join(f"- {f['titre']} : {f['actuel']}" for f in choisis if f["actuel"])
    else:
        bad = {s for s, _ in state.get("problemes") or []}
        phrases = verify.sentences(state["brouillon"])
        if not bad and phrases:
            texte = state["brouillon"]
        elif phrases and len(bad) <= 0.3 * len(phrases):
            texte = "\n".join(p for p in phrases if p not in bad)
            notes.append(f"⚠ {len(bad)} phrase(s) retirée(s) de la synthèse car non vérifiables.")
        else:  # repli déterministe: état actuel tranché (code) + les affirmations vérifiées, sans prose générée
            lignes = [f"{f['titre']} : {f['actuel']} [{f['id']}]" for f in choisis if f["actuel"]]
            lignes += [f"- {a['texte']} [{', '.join(a['preuves'])}]" for a in affs if not any(p.startswith("F") for p in a["preuves"])][:4]
            texte = "\n".join(lignes)
            notes.append("⚠ Synthèse rédigée non vérifiable : affichage de l'état actuel tranché et des affirmations vérifiées.")
    texte = afficher(texte, claims)
    inconnu = [x for f in choisis for x in f["inconnu"]]
    inconnu += [x for r in state["reponses"] for x in r["inconnu"]]
    inconnu = list(dict.fromkeys(inconnu))[:6]
    sections = fils.evolution(state["question"], state.get("fils", []))
    conf = _confiance(affs) if affs else "Confiance : aucune affirmation vérifiée"
    retirees = sum(len(r["retirees"]) for r in state["reponses"])
    if retirees:
        notes.append(f"{retirees} affirmation(s) d'expert rejetée(s) par la vérification (corrigées ou retirées).")
    courte = texte + (("\n\nCe qu'on ne sait pas :\n" + "\n".join(f"- {x}" for x in inconnu)) if inconnu else "")
    evo = fils.evolution_text(sections)
    final = (f"Réponse (état au {kb.ref_date()}) :\n{courte}"
             + (f"\n\nÉvolution et sources contradictoires (du plus ancien au plus récent) :\n{evo}" if evo else "")
             + "\n\n" + conf + ("\n" + "\n".join(notes) if notes else ""))
    ids = list(dict.fromkeys(i for a in affs for i in _expand(a["preuves"], claims)))
    preuves = [{"id": i, "source": claims[i]["source"], "fichier": claims[i].get("fichier", ""), "repere": claims[i].get("repere", ""),
                "texte": claims[i]["texte"]} for i in ids if i in claims]
    return {"final": final, "courte": courte + "\n\n" + conf, "evolution": sections, "preuves": preuves, "confiance": conf}


_g = StateGraph(State)
for name, fn in [("route", route), ("expert", expert), ("synthesize", synthesize), ("finalize", finalize)]:
    _g.add_node(name, fn)
_g.add_edge(START, "route")
_g.add_conditional_edges("route", fan_out, ["expert"])
_g.add_edge("expert", "synthesize")
_g.add_conditional_edges("synthesize", after_synthesis, ["synthesize", "finalize"])
_g.add_edge("finalize", END)
chat_app = _g.compile()


def ask(question: str) -> dict:
    out = chat_app.invoke({"question": question, "reponses": [], "tentatives": 0, "problemes": []})
    return {"reponse": out["final"], "reponse_courte": out.get("courte", ""), "evolution": out.get("evolution", []),
            "fils": out.get("fils", []), "sujets": out["sujets"], "experts": out["reponses"], "preuves": out.get("preuves", []),
            "confiance": out.get("confiance", ""), "tentatives_synthese": out.get("tentatives", 0)}
