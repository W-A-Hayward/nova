"""Vérification des réponses: d'abord en code (déterministe), ensuite par un agent vérificateur (LLM).

Contrôles déterministes (aucun appel au modèle):
1. citations: chaque identifiant cité existe ET faisait partie des preuves fournies à l'agent;
2. ancrage des entités: montants, dates, heures, identifiants (SEC-210, INV-003), nombres et prénoms présents
   dans l'affirmation doivent figurer dans le texte des preuves CITÉES. Si l'entité existe dans une autre preuve
   fournie, la citation est réparée automatiquement; sinon l'affirmation est rejetée;
3. garde-fou « livré ≠ validé »: dire qu'un ticket non fermé est validé/fermé/accepté est une contradiction;
4. garde-fou « fait périmé »: une affirmation qui ne s'appuie que sur des faits remplacés doit le dire;
5. garde-fou « proposition ≠ décision »: une proposition ne peut pas être présentée comme approuvée;
6. information « à valider » (ingérée, non confirmée): annotée automatiquement.
"""
import re, unicodedata
from difflib import SequenceMatcher
from . import kb, llm

MOIS = {"janv": 1, "janvier": 1, "fevr": 2, "fev": 2, "fevrier": 2, "mars": 3, "avr": 4, "avril": 4, "mai": 5, "juin": 6,
        "juil": 7, "juillet": 7, "aout": 8, "sept": 9, "septembre": 9, "oct": 10, "octobre": 10, "nov": 11, "novembre": 11,
        "dec": 12, "decembre": 12}
_MOIS_RE = "|".join(sorted(MOIS, key=len, reverse=True))
CITE_RE = re.compile(r"\b(C\d{3,4}|NEW\d+|CALC|S\d{2}|N\d{2})\b")


def norm(s: str) -> str:
    s = s.replace(" ", " ").replace(" ", " ").replace("’", "'")
    s = "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s)


# ---------------------------------------------------------------- extraction d'entités
def _amounts(t: str) -> set[int]:
    out = set()
    for m in re.finditer(r"(\d{1,3}(?:[ .]\d{3})+|\d+)(?:,\d+)?\s*(k)?\s*(?:\$|cad\b|dollars?\b)", t):
        v = int(re.sub(r"[ .]", "", m.group(1)))
        out.add(v * 1000 if m.group(2) else v)
    return out


def _dates(t: str) -> set[tuple[int, int]]:
    out = set()
    for m in re.finditer(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t):
        out.add((int(m.group(2)), int(m.group(3))))
    for m in re.finditer(rf"\b(1er|\d{{1,2}})\s+({_MOIS_RE})\b\.?", t):
        d = 1 if m.group(1) == "1er" else int(m.group(1))
        if 1 <= d <= 31:
            out.add((MOIS[m.group(2)], d))
    return out


def _strip_dates_times_ids(t: str) -> str:
    t = re.sub(r"\b20\d\d-\d\d-\d\d(t[\d:+-]+)?\b", " ", t)
    t = re.sub(rf"\b(1er|\d{{1,2}})\s+({_MOIS_RE})\b", " ", t)
    t = re.sub(r"\b\d{1,2}\s?[:h]\s?\d{2}\b", " ", t)
    return kb.ID_RE.sub(" ", t)


CITATION_TOKEN = re.compile(r"\b(?:C\d{3,4}|NEW\d+|CALC|S\d{2}|N\d{2}|[DKAQ]\d{1,2})\b")


def entities(text: str) -> dict[str, set]:
    text = CITATION_TOKEN.sub(" ", text)  # les identifiants de citation ne sont pas des faits
    t = norm(text)
    rest = _strip_dates_times_ids(t)
    nums = set()
    for m in re.finditer(r"\d{1,3}(?:[ .]\d{3})+(?!\d)|\d+(?:,\d+)?", rest):
        v = re.sub(r"[ .]", "", m.group(0)).replace(",", ".")
        try:
            if float(v) >= 10:
                nums.add(v)
        except ValueError:
            pass
    return {
        "montant": _amounts(t),
        "date": _dates(t),
        "heure": {f"{int(a):02d}:{b}" for a, b in re.findall(r"\b([01]?\d|2[0-3])\s?[:h]\s?([0-5]\d)\b", t)},
        "identifiant": {x.upper() for x in kb.ID_RE.findall(text)},
        "nombre": nums,
        "personne": {n for n in kb.roster() if re.search(rf"\b{re.escape(norm(n))}\b", t)},
    }


def missing(text: str, evidence: str) -> list[str]:
    """Entités de `text` absentes de `evidence` (les nombres peuvent aussi correspondre à un montant)."""
    a, e = entities(text), entities(evidence)
    e_nums = e["nombre"] | {str(v) for v in e["montant"]}
    out = []
    a_amounts = {str(v) for v in a["montant"]}
    for k, vals in a.items():
        pool = e_nums if k == "nombre" else e[k]
        for v in sorted(vals, key=str):
            if k == "nombre" and v in a_amounts:
                continue  # déjà compté comme montant
            if v not in pool:
                out.append(f"{k} {v[1]}/{v[0]}" if k == "date" else f"{k} {v}")
    return out


# ---------------------------------------------------------------- garde-fous sémantiques codés
CLOSURE = re.compile(r"\b(fermee?s?|clos|cloture|validee?s?|acceptee?s?|approuvee?s?|completee?s?|resolue?s?|reglee?s?|conformes?|"
                     r"terminee?s?|au vert|levee?s?|satisfaite?s?|finalisee?s?|complete)\b")
NEG = re.compile(r"\b(pas|non|ne|n'|aucune?|jamais|toujours|reste|restent|encore|attente|sans|avant|doit|doivent|devra|devront|"
                 r"conditionn\w*|si|tant|ni|bloquant|ouvert|planifie|prevu|a valider|a confirmer|en validation)\b|!=|≠|n'")
HISTO = re.compile(r"initial|ancien|remplac|deplac|auparavant|perime|n'est plus|obsolete|a l'origine|d'abord|precedent|historique|"
                   r"brouillon|non mise? a jour|non fiable|jusqu|depuis|avant|charte|origine")
APPROVAL = re.compile(r"\b(approuv\w*|decid\w*|valid\w*|accept\w*|enterin\w*|adopt\w*)\b")
GARANTI = re.compile(r"\b(garanti\w*|definiti\w*|assure\w*|certain\w*|automatique\w*|confirme sans reserve)\b")
KEYWORD_TICKET = {"runbook": "OPS-601", "rollback": "OPS-601", "retour arriere": "OPS-601", "securite": "SEC-210", "accessibilite": "ACC-303"}


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r"[.;\n•]|,\s(?:mais|alors que|tandis que|car)\b|\bmais\b", norm(text)) if c.strip()]


def status_conflicts(text: str, tickets: dict[str, dict] | None = None) -> list[str]:
    tickets = kb.ticket_status() if tickets is None else tickets
    out = []
    for cl in _clauses(text):
        ids = {x.upper() for x in kb.ID_RE.findall(cl)}
        if not ids:
            ids = {t for k, t in KEYWORD_TICKET.items() if k in cl}
        for tid in ids:
            st = tickets.get(tid, {}).get("statut")
            if st and st != "FERMÉ" and CLOSURE.search(cl) and not NEG.search(cl):
                out.append(f"contredit le statut de {tid} ({st} au {kb.ref_date()}): « livré/corrigé ≠ validé »")
        if re.search(r"go-live|mise en production|22 oct", cl) and GARANTI.search(cl) and not NEG.search(cl):
            out.append("présente la mise en production comme garantie alors qu'elle est conditionnelle")
    return out


def semantic_guards(text: str, cited: list[dict]) -> list[str]:
    probs = status_conflicts(text)
    real = [c for c in cited if c.get("id") != "CALC"]
    t = norm(text)
    if real and all(c.get("perime") for c in real) and not HISTO.search(t):
        probs.append("s'appuie uniquement sur des faits périmés/remplacés sans le signaler (« initialement », « remplacé »...)")
    if real and all(c.get("type") == "proposition" for c in real) and APPROVAL.search(t) and not NEG.search(t) and "propos" not in t:
        probs.append("présente une proposition comme une décision/approbation")
    return probs


# ---------------------------------------------------------------- vérification d'une affirmation structurée
def normalize_ids(preuves, allowed: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Garde les identifiants connus; un [Sxx] cité est traduit en claims fournis de cette source."""
    ok, bad = [], []
    for p in preuves if isinstance(preuves, list) else [preuves]:
        for pid in CITE_RE.findall(str(p).upper()) or [str(p)]:
            if pid in allowed:
                ok.append(pid)
            elif re.fullmatch(r"S\d{2}|N\d{2}", pid) and any(c["source"] == pid for c in allowed.values()):
                ok += [i for i, c in allowed.items() if c["source"] == pid]
            else:
                bad.append(pid)
    return list(dict.fromkeys(ok)), bad


def _evidence_text(ids: list[str], allowed: dict[str, dict]) -> str:
    # la date du claim fait partie de la preuve (elle est affichée au modèle dans render())
    # la date de référence du dossier est toujours un fait connu (« au 30 septembre »)
    return kb.baseline()["baseline_au"][:10] + "\n" + "\n".join(f"{allowed[i].get('date', '')} {allowed[i]['texte']}" for i in ids if i in allowed)


def check_affirmation(aff: dict, allowed: dict[str, dict]) -> dict:
    """Renvoie {texte, preuves, problemes, reparations}. `allowed` = preuves fournies à l'agent (id -> claim;
    « CALC » -> bloc de calculs financiers)."""
    texte = str(aff.get("texte", "")).strip()
    ids, bad = normalize_ids(aff.get("preuves", []), allowed)
    rep = [f"citation inexistante retirée: {b}" for b in bad]
    probs = []
    if not texte:
        return {"texte": "", "preuves": [], "problemes": ["affirmation vide"], "reparations": rep}
    # réparation des citations: une entité absente des preuves citées mais présente dans une autre preuve fournie
    for m in missing(texte, _evidence_text(ids, allowed)):
        for cid, c in allowed.items():
            if cid not in ids and m not in missing(texte, _evidence_text([cid], allowed)):
                ids.append(cid)
                rep.append(f"citation ajoutée {cid} (contient {m})")
                break
    reste = missing(texte, _evidence_text(ids, allowed))
    if not ids:
        probs.append("aucune preuve valide citée")
    if reste:
        probs.append("non trouvé dans les preuves: " + ", ".join(reste))
    probs += semantic_guards(texte, [allowed[i] for i in ids])
    if any(allowed[i].get("statut") == "à valider" for i in ids) and "valider" not in norm(texte):
        texte += " (information à valider)"
        rep.append("mention « à valider » ajoutée")
    return {**aff, "texte": texte, "preuves": ids, "problemes": probs, "reparations": rep}


# ---------------------------------------------------------------- agent vérificateur (LLM, implication textuelle)
VERIF_SYSTEM = """Tu es un vérificateur factuel strict. Pour chaque affirmation, compare-la UNIQUEMENT aux preuves données.
- SUPPORTE: tout ce que dit l'affirmation est explicitement dans les preuves (reformulation permise).
- PARTIEL: une partie est appuyée, mais un détail (personne, date, statut, montant, lien de cause) ne l'est pas.
- NON_SUPPORTE: les preuves ne disent pas cela.
- CONTREDIT: les preuves disent le contraire (ex.: « validé » alors que les preuves disent « déployé » ou « en validation »;
  « décidé » alors que les preuves disent « proposé »; un fait marqué PÉRIMÉ présenté comme actuel).
Sois sévère: en cas de doute, ne réponds pas SUPPORTE. N'utilise aucune connaissance extérieure."""
VERDICTS = {"SUPPORTE", "PARTIEL", "NON_SUPPORTE", "CONTREDIT"}


def llm_verify(items: list[dict], allowed: dict[str, dict]) -> list[dict | None]:
    """items: [{texte, preuves}] -> [{verdict, raison}] (None si le vérificateur n'a pas pu répondre)."""
    if not items:
        return []
    blocs = []
    for i, a in enumerate(items):
        preuves = "\n".join(kb.render([allowed[p]]) if p != "CALC" else "[CALC] " + allowed[p]["texte"] for p in a["preuves"] if p in allowed)
        blocs.append(f"#{i} AFFIRMATION: {a['texte']}\nPREUVES:\n{preuves}")

    def valid(o):
        v = o.get("verdicts") if isinstance(o, dict) else None
        if not isinstance(v, list) or len(v) != len(items):
            return f"il faut une liste « verdicts » de {len(items)} éléments"
        if any(not isinstance(x, dict) or str(x.get("verdict", "")).upper() not in VERDICTS for x in v):
            return f"chaque verdict doit être l'un de {sorted(VERDICTS)}"
        return None

    out = llm.ask_json("\n\n".join(blocs) + '\n\nRéponds en JSON: {"verdicts": [{"i": 0, "verdict": "SUPPORTE|PARTIEL|NON_SUPPORTE|CONTREDIT", '
                       '"raison": "courte"}]} (un élément par affirmation, dans l\'ordre).',
                       system=VERIF_SYSTEM, tag="verify", validate=valid, default=None)
    if not out:
        return [None] * len(items)
    return [{"verdict": str(v["verdict"]).upper(), "raison": str(v.get("raison", ""))} for v in out["verdicts"]]


# ---------------------------------------------------------------- vérification d'un texte libre (synthèse, rapport)
def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÉÈÀ«(\-•*\d])|\n+", text) if s.strip()]


def check_prose(text: str, allowed: dict[str, dict]) -> list[tuple[str, list[str]]]:
    """Vérifie chaque phrase: citations connues, entités présentes dans les preuves citées, garde-fous."""
    bad = []
    for s in sentences(text):
        ids, unknown = normalize_ids(CITE_RE.findall(s.upper()), allowed) if CITE_RE.search(s.upper()) else ([], [])
        probs = [f"citation inconnue: {u}" for u in unknown]
        ents = missing(s, "")  # entités factuelles de la phrase
        if ents and not ids:
            # une phrase factuelle sans citation est tolérée seulement si tout est dans les preuves fournies
            reste = missing(s, _evidence_text(list(allowed), allowed))
            probs += ["fait non cité et introuvable: " + ", ".join(reste)] if reste else []
        elif ids:
            reste = missing(s, _evidence_text(ids, allowed))
            if reste:
                autre = missing(s, _evidence_text(list(allowed), allowed))
                probs.append(("non trouvé dans les preuves citées: " if not autre else "inventé (absent de toutes les preuves): ")
                             + ", ".join(autre or reste))
        probs += status_conflicts(s)
        if probs:
            bad.append((s, probs))
    return bad


def quote_in(quote: str, doc: str, seuil: float = 0.85) -> bool:
    """La citation (verbatim) provient-elle vraiment du document? Égalité normalisée, sinon plus longue sous-chaîne."""
    q, d = norm(quote).strip(" «»\"'"), norm(doc)
    if len(q) < 12:
        return False
    if q in d:
        return True
    m = SequenceMatcher(None, d, q, autojunk=False).find_longest_match(0, len(d), 0, len(q))
    return m.size / len(q) >= seuil


def to_display(text: str, claims: dict[str, dict]) -> str:
    """Remplace les identifiants de claims par les sources lisibles: [C012, C015] -> [S16, S18]."""
    def sub(m):
        out = []
        for pid in CITE_RE.findall(m.group(0).upper()):
            src = "calcul NOVA" if pid == "CALC" else claims.get(pid, {}).get("source", pid)
            if src not in out:
                out.append(src)
        return "[" + ", ".join(out) + "]" if out else m.group(0)
    return re.sub(r"\[[^\[\]]*\b(?:C\d{3,4}|NEW\d+|CALC)\b[^\[\]]*\]", sub, text)
