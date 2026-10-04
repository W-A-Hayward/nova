# NOVA : mémoire opérationnelle de projet

Réponse au défi 24 h « Projet 360 » : reprendre le projet fictif NOVA, dont l'information est dispersée (courriels, comptes rendus, tickets, contrats, factures, plans, captures), et en faire une mémoire fiable. Une autre personne doit pouvoir y comprendre l'état du projet, retrouver chaque preuve et intégrer une nouvelle information sans effacer l'historique.

Toutes les réponses sont données **au 30 septembre 2026 à 9 h (Montréal)**, la date fictive du dossier. Consignes : `data/nova_agents/data/starter/README.txt` et `consignes.pdf`.

## Démarrage

**Sans rien installer** : ouvrir `data/nova_agents/export/index.html` dans un navigateur. L'export est autonome : pages HTML, fichiers sources, polices et recherche. Il fonctionne hors ligne.

**Avec le serveur**, nécessaire pour le chat et l'ajout de documents :
```bash
cd data/nova_agents
pip install -r requirements.txt
ollama pull llama3.1                 # chat et aide à l'extraction seulement
python -m app.seed                   # (ré)génère data/claims.json depuis le dossier
uvicorn app.server:app               # http://127.0.0.1:8000
python scripts/export_static.py      # régénère export/
```
Le mode d'emploi pour le jury (navigation, traitements manuels, limites, informations incertaines) est dans `data/nova_agents/GUIDE.md`. Il est aussi disponible sous la page « Mode d'emploi ».

## Les livrables et où les trouver

| Livrable du README | Page | Source |
|---|---|---|
| 1. Brief de reprise d'une page | Brief | `app/server.py` (`brief_page`). Montants calculés depuis les PDF ; s'imprime sur une page A4 |
| 2. Mémoire : chronologie, décisions, contradictions, sources, actions | Mémoire | `app/memory.py` → `data/memory.json` |
| 3. Q01–Q10 avec fichier et repère précis | Réponses Q01–Q10 | `data/answers_baseline.json` (extraits cités mot pour mot) |
| 4. État actualisé après la nouvelle information, baseline conservée | Ajouter → Mise à jour | `app/impact.py`, `app/updates.py`, `data/updates/` |
| 5. Mode d'emploi | Mode d'emploi | `data/nova_agents/GUIDE.md` |

À cela s'ajoutent les pages **Sources et recherche** (catalogue des 63 fichiers avec autorité, doublons et avertissements, plus une recherche plein texte sans IA) et **Chat** (questions libres, réponses vérifiées).

## Comment NOVA raisonne

**État actuel = le fait documenté le plus récent, émanant d'une source compétente, daté par la date du fait et non par celle du fichier.**

C'est ce que demande le README : « une date de fichier récente ne garantit pas une information exacte ». Deux exemples dans le dossier :
- le plan v3 (12 sept) est plus récent que la décision du comité (10 sept), mais il n'a pas été corrigé ;
- le registre des risques du 29 sept garde une ligne R-01 qui décrit l'état au 9 sept.

- **Preuves vérifiables.** Chaque affirmation des pages cite un extrait exact, retrouvé en code dans le fichier (`app/evidence.py`). Chaque lien ouvre la source à la ligne, la page, la cellule ou la capture concernée. Un extrait introuvable fait échouer les tests.
- **Fils thématiques** (`app/fils.py`). Treize sujets, dont la date, l'hébergement, le responsable, le budget, chacune des trois conditions de go-live, les actions… Chaque fil a un état actuel tranché en code et la liste datée de toutes les sources qui en parlent, avec leur rôle : historique, proposition, décision, livraison (qui n'est pas une validation), validation, contredit (avec la raison), non fiable, mise à jour reçue.
- **Chat** (`app/chat_graph.py`). Les experts LLM reçoivent l'état actuel en tête, puis les positions étiquetées. Une position passée présentée comme actuelle est rejetée en code, puis un agent vérificateur relit chaque affirmation. La réponse donne l'état actuel, puis une section « Évolution et sources contradictoires » assemblée par le code. Les questions générales ont leur vue dédiée : contradictions, « qu'est-ce qui a changé depuis… », engagements, risques, reprise.
- **Nouvelle information** (`app/impact.py`, `app/ingest_graph.py`). Chaque phrase d'un document reçu qui porte un signal (date, ticket, montant, proposition, livraison, validation, retard) est rattachée à un fil, puis comparée à son état actuel. Le rapport répond aux trois questions de la consigne : ce qui vient de changer, ce qui est affecté, les actions à prendre. Il ajoute ce qui n'a pas changé. Un brouillon de mise à jour est proposé. Une fois relu et enregistré, il devient `data/updates/Uxx_*.json`, sans jamais réécrire la baseline.
- **Garde-fous en code**, indépendants du LLM :
  - une proposition ne remplace jamais une décision ;
  - une condition de go-live n'est levée que par son validateur désigné ;
  - une instruction glissée dans un document (« ignorez les règles… ») est écartée ;
  - les montants autorisé, facturé et payé sont calculés, jamais générés.

## Structure

```
README.md
data/nova_agents/
  app/          serveur FastAPI et logique (corpus, evidence, memory, fils, chat_graph, impact, ingest_graph, updates, verify, llm…)
  app/static/   polices embarquées (Public Sans, Source Serif 4)
  data/starter/ dossier fourni (consignes + Projet360_NOVA_ETUDIANTS, 63 fichiers)
  data/         claims.json (passages avec repère), memory.json (baseline), answers_baseline.json, manual/captures.json, updates/
  export/       version HTML autonome pour le jury
  scripts/      export_static.py
  tests/        tests sans Ollama + évaluation avec Ollama
  GUIDE.md      mode d'emploi
```

## Tests

| Commande (dans `data/nova_agents`) | Ollama | Vérifie |
|---|---|---|
| `python tests/test_deliverables.py` | non | extraits retrouvés dans le dossier, faits clés de Q01–Q10, montants, brief d'une page, contradictions dans un plan et un registre, échéances, garde-fous de mise à jour, baseline intacte, liens de l'export |
| `python tests/test_chat_reasoning.py` | non | état actuel tranché par date du fait et autorité, positions passées étiquetées, sélection des fils, vues contradictions et « ce qui a changé » |
| `python tests/test_impact.py` | non | détection des changements d'un document reçu avec un LLM muet : proposition, livraison, validation par le bon validateur, décision, facture, injection |
| `python tests/smoke_test.py` | non | un faux LLM qui hallucine volontairement : chaque erreur doit être attrapée (relancer ensuite `python -m app.seed`) |
| `python tests/eval_qa.py [--quiet]` | oui | Q01–Q10, questions des consignes et questions-pièges : rappel, état actuel en premier, historique exposé, entités inventées, abstention |

## Variables

| Variable | Défaut | Rôle |
|---|---|---|
| `NOVA_MODEL` | `llama3.1` | modèle Ollama |
| `NOVA_NUM_CTX` | `8192` | contexte (le défaut d'Ollama, 2048, tronque les faits) |
| `NOVA_NUM_PREDICT` | `1024` | longueur maximale d'une réponse |
| `NOVA_EVIDENCE_CHARS` | `8000` | budget de preuves par expert |
| `NOVA_MAX_EXPERTS` | `3` | experts consultés par question |
| `NOVA_VERIFY_LLM` | `1` | agent vérificateur (`0` pour aller plus vite) |
| `NOVA_REVISE` | `1` | une passe de correction des affirmations rejetées |
| `NOVA_SYNTH_TRIES` | `2` | essais de synthèse avant le repli déterministe |
| `NOVA_IMPACT_LLM` | `1` | remarques LLM complémentaires dans le rapport d'impacts (`0` : analyse en code seulement) |

## Outils et limites

**Outils.**
- Python, FastAPI, pypdf, openpyxl.
- LangGraph et Ollama (llama3.1, local et gratuit), seulement pour le chat et l'aide à l'extraction.
- Claude Code pour le développement, la relecture du dossier et une première rédaction des réponses et de la mémoire. Chaque fait a ensuite été vérifié contre le dossier, et les tests contrôlent les extraits.

**Traitements manuels.**
- Transcription des 8 captures PNG (`data/manual/captures.json`).
- Rédaction de Q01–Q10 et de la mémoire.

**Limites.**
- La prose du chat dépend d'un modèle 8B : l'état actuel et l'évolution sont fiables (tranchés par le code), la formulation l'est moins. Les réponses de référence sont sur la page Réponses Q01–Q10.
- La recherche est lexicale.
- Les repères « ligne N » des courriels renvoient à leur vue normalisée.
- La session du chat et de la page Ajouter vit dans la mémoire du serveur. Elle est commune aux navigateurs connectés et effacée à l'arrêt.

Les informations incertaines ou manquantes au 30 septembre sont listées dans `GUIDE.md`.
