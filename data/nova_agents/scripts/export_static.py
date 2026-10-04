#!/usr/bin/env python3
"""Export HTML autonome: export/index.html s'ouvre dans un navigateur, sans Python, sans Ollama, sans serveur.

Rend les pages /brief, /memoire, /reponses, /mise-a-jour, /sources (avec la recherche), /guide et une page par fichier source,
et copie les fichiers originaux dans export/raw/ (captures PNG, PDF, xlsx...). Le chat et l'ingestion restent côté serveur.
Usage: python scripts/export_static.py [dossier_de_sortie]
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import corpus, evidence, server  # noqa: E402

server.STATIC = True
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "export"

PAGES = {
    "brief": server.brief_page,
    "memoire": server.memoire_page,
    "reponses": server.reponses_page,
    "mise-a-jour": lambda: server.maj_page(0),
    "sources": server.sources_page,
    "guide": server.guide_page,
}


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for route, fn in PAGES.items():
        (OUT / server.href(route)).write_text(fn(), encoding="utf-8")
    shutil.copytree(ROOT / "app" / "static", OUT / "static")  # polices embarquées: l'export reste lisible hors ligne
    (OUT / "index.html").write_text((OUT / server.href("brief")).read_text(encoding="utf-8"), encoding="utf-8")
    for fichier in evidence.by_file():
        (OUT / server.href("source/" + fichier)).write_text(server.source_html(fichier), encoding="utf-8")
        dest = OUT / "raw" / fichier
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(corpus.ROOT / fichier, dest)
    n = len(list(OUT.glob("*.html")))
    print(f"{n} pages HTML et {len(evidence.by_file())} fichiers sources exportés dans {OUT}. Ouvrir {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
