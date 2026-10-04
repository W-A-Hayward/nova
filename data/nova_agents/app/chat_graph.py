"""Chat: routage -> experts en parallèle (preuves ciblées, JSON, vérification code + LLM, une révision)
-> synthèse à partir des seules affirmations vérifiées -> contrôle phrase par phrase (boucle de correction)
-> finalisation (repli déterministe si la prose reste non vérifiable).

        route ──Send──> expert x N ──> synthesize ⟲ (≤ NOVA_SYNTH_TRIES) ──> finalize
                         │ génère JSON {affirmations, preuves}
                         │ check_affirmation (code)  ─┐
                         │ llm_verify (agent)        ─┼─> rejetées -> révision (1x) -> re-vérification
                         └ ne renvoie que le vérifié ─┘
"""
import operator, os, re
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from . import kb, llm, prompts, retrieval, verify

VERIFY_LLM = os.getenv("NOVA_VERIFY_LLM", "1") != "0"   # agent vérificateur (coûte 1 appel par expert)
REVISE = os.getenv("NOVA_REVISE", "1") != "0"           # une passe de correction des affirmations rejetées
SYNTH_TRIES = int(os.getenv("NOVA_SYNTH_TRIES", "2"))
EVIDENCE_CHARS = int(os.getenv("NOVA_EVIDENCE_CHARS", "8000"))
REGLES = prompts.REGLES  # rétro-compatibilité


class State(TypedDict, total=False):
    question: str
    sujets: list[str]
    reponses: Annotated[list[dict], operator.add]
    brouillon: str
    problemes: list
    tentatives: int
    final: str
    preuves: list[dict]
    confiance: str


# ------------------------------------------------------------------------------------------------ routage
def route(state: State):
    def valid(o):
        return None if isinstance(o, dict) and isinstance(o.get("sujets"), list) else 'format attendu: {"sujets": [...]}'
    out = llm.ask_json(prompts.route_prompt(state["question"]), system=prompts.ROUTE_SYSTEM, tag="route", validate=valid,
                       default={"sujets": []})
    sujets = [s for s in out.get("sujets", []) if s in kb.SUJETS]
    # filet de sécurité: les mots-clés détectés en code s'ajoutent au choix du LLM (un mauvais routage = un expert muet)
    t = state["question"].lower()
    sujets += [s for s, ws in kb.MOTS.items() if any(w in t for w in ws) and s not in sujets]
    return {"sujets": [s for s in kb.SUJETS if s in sujets] or list(kb.SUJETS)}


def fan_out(state: State):
    return [Send("expert", {"sujet": s, "question": state["question"]}) for s in state["sujets"]]


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


def _evidence(question: str, sujet: str, budget: int):
    evid = retrieval.select_evidence(question, sujet, budget_chars=budget)
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
        evid, allowed, calculs = _evidence(q, s, budget)
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
    seen, out = set(), []
    for r in state["reponses"]:
        for a in r["affirmations"]:
            k = verify.norm(a["texte"])
            if k not in seen:
                seen.add(k)
                out.append(a)
    return out


def _allowed_for_synthesis(affs: list[dict]) -> dict[str, dict]:
    claims = kb.claims_by_id()
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
    return {"brouillon": draft, "problemes": verify.check_prose(draft, _allowed_for_synthesis(affs)), "tentatives": n}


def after_synthesis(state: State) -> str:
    return "synthesize" if state.get("problemes") and state.get("tentatives", 0) < SYNTH_TRIES else "finalize"


def _confiance(affs: list[dict]) -> str:
    claims = kb.claims_by_id()
    cites = [claims[i] for a in affs for i in a["preuves"] if i in claims]
    srcs = {kb.canonical_source(c["source"]) for c in cites if re.fullmatch(r"[SN]\d+", c["source"])}
    auts = [c["autorite"] for c in cites if c.get("autorite")]
    a_valider = any(c.get("statut") == "à valider" for c in cites)
    best = min(auts) if auts else None
    niveau = ("Faible" if a_valider or not srcs else
              "Haute" if len(srcs) >= 2 and best is not None and best <= 2 else "Moyenne")
    return (f"Confiance (calculée par le code): {niveau} — {len(srcs)} source(s) distincte(s), meilleure autorité: "
            f"{kb.AUTORITE.get(best, 'n/a')}{'; contient des informations à valider' if a_valider else ''}")


def finalize(state: State):
    affs = _verified(state)
    claims = kb.claims_by_id()
    notes = []
    if not affs:
        texte = ("Je ne trouve pas d'information vérifiable dans la base NOVA pour répondre à cette question. "
                 "Rien n'est affirmé plutôt que de risquer une réponse inventée.")
    else:
        bad = {s for s, _ in state.get("problemes") or []}
        phrases = verify.sentences(state["brouillon"])
        if not bad:
            texte = state["brouillon"]
        elif len(bad) <= 0.3 * len(phrases):
            texte = "\n".join(p for p in phrases if p not in bad)
            notes.append(f"⚠ {len(bad)} phrase(s) retirée(s) de la synthèse car non vérifiables.")
        else:  # repli déterministe: on affiche les affirmations vérifiées telles quelles
            texte = "\n".join(f"- {a['texte']} [{', '.join(a['preuves'])}]" for a in affs)
            notes.append("⚠ Synthèse rédigée non vérifiable: affichage direct des affirmations vérifiées.")
    texte = verify.to_display(texte, claims)
    inconnu = list(dict.fromkeys(x for r in state["reponses"] for x in r["inconnu"]))
    if inconnu:
        texte += "\n\nCe qu'on ne sait pas:\n" + "\n".join(f"- {x}" for x in inconnu)
    retirees = sum(len(r["retirees"]) for r in state["reponses"])
    if retirees:
        notes.append(f"{retirees} affirmation(s) d'expert rejetée(s) par la vérification (corrigées ou retirées).")
    conf = _confiance(affs) if affs else "Confiance: aucune preuve"
    preuves = [{"id": i, "source": claims[i]["source"], "fichier": claims[i].get("fichier", ""), "texte": claims[i]["texte"]}
               for i in dict.fromkeys(i for a in affs for i in a["preuves"]) if i in claims]
    final = texte + "\n\n" + conf + ("\n" + "\n".join(notes) if notes else "")
    return {"final": final, "preuves": preuves, "confiance": conf}


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
    return {"reponse": out["final"], "sujets": out["sujets"], "experts": out["reponses"], "preuves": out.get("preuves", []),
            "confiance": out.get("confiance", ""), "tentatives_synthese": out.get("tentatives", 0)}
