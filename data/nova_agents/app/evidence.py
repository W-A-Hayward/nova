"""Localisation des preuves: un extrait verbatim -> fichier, repère (ligne, page, cellule, image) et ancre HTML.

Les réponses et la mémoire citent un extrait exact du dossier; on le retrouve ici dans le texte extrait par corpus.py.
Un extrait introuvable est une erreur (testée dans tests/test_deliverables.py), pas une preuve.
"""
import re
from functools import lru_cache
from . import corpus


def norm(s: str) -> str:
    """Comparaison tolérante à la mise en forme: gras markdown, apostrophes, espaces et retours de ligne PDF."""
    s = s.replace("*", "").replace("’", "'").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


@lru_cache(maxsize=1)
def by_file() -> dict[str, dict]:
    return {d["fichier"]: d for d in corpus.documents()}


def anchor(repere: str) -> str:
    m = re.match(r"ligne (\d+)", repere)
    if m:
        return f"L{m.group(1)}"
    m = re.match(r"page (\d+)", repere)
    if m:
        return f"p{m.group(1)}"
    m = re.search(r"feuille .*?, ligne (\d+)", repere)
    if m:
        return f"r{m.group(1)}"
    return "doc"


def locate(fichier: str, extrait: str) -> dict | None:
    """Renvoie {repere, anchor} du passage qui contient l'extrait, ou None s'il est introuvable."""
    doc = by_file().get(fichier)
    if not doc or not extrait:
        return None
    x = norm(extrait)
    for p in doc["passages"]:
        if x in norm(p["texte"]):
            return {"repere": p["repere"], "anchor": anchor(p["repere"])}
    if x in norm(doc["text"]):  # extrait à cheval sur deux passages: on remonte à la ligne de début
        lines = doc["text"].splitlines()
        for i in range(len(lines)):
            if norm(" ".join(lines[i:])).startswith(x[:40]):
                return {"repere": f"ligne {i + 1}", "anchor": f"L{i + 1}"}
        return {"repere": "document", "anchor": "doc"}
    return None


def link(fichier: str, extrait: str = "", prefix: str = "/source/") -> str:
    loc = locate(fichier, extrait) if extrait else None
    return f"{prefix}{fichier}" + (f"#{loc['anchor']}" if loc else "")
