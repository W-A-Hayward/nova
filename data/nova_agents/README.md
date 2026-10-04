# NOVA agents (LangGraph + Ollama)

## Lancer
```
ollama pull llama3.1
pip install -r requirements.txt
python -m app.seed            # (ré)initialise data/claims.json depuis data/starter/Projet360_NOVA_ETUDIANTS
uvicorn app.server:app --reload
```
Pages (sans LLM, exportables avec `python scripts/export_static.py` → `export/index.html`) : `/brief` | `/memoire` | `/reponses` | `/mise-a-jour` | `/sources` | `/recherche` | `/guide`. Avec Ollama : `/chat` (réponse + preuves citées + affirmations rejetées) | `/ingest`. Mode d'emploi complet pour le jury : `GUIDE.md`.

Variables:
| Variable | Défaut | Rôle |
|---|---|---|
| `NOVA_MODEL` | `llama3.1` | modèle Ollama |
| `NOVA_NUM_CTX` | `8192` | contexte (le défaut d'Ollama, 2048, tronque les faits) |
| `NOVA_NUM_PREDICT` | `1024` | longueur max d'une réponse |
| `NOVA_EVIDENCE_CHARS` | `8000` | budget de preuves par expert |
| `NOVA_VERIFY_LLM` | `1` | agent vérificateur (mettre `0` pour aller plus vite) |
| `NOVA_REVISE` | `1` | une passe de correction des affirmations rejetées |
| `NOVA_SYNTH_TRIES` | `2` | essais de synthèse avant le repli déterministe |

## Architecture
- `kb.py`: base de claims en ajout seulement (identifiants `C001`…), autorité, statut des tickets, calculs financiers en code.
- `corpus.py` / `seed.py`: lisent les fichiers de `data/starter/Projet360_NOVA_ETUDIANTS` (courriel, texte, PDF, Excel, CSV) et en font des claims avec repère (ligne, page, cellule). Les tickets et le registre financier sont extraits de ces fichiers.
- `retrieval.py`: sélection des preuves par question (BM25 + identifiants + état courant), dans un budget.
- `prompts.py`: tous les prompts (système / utilisateur séparés, exemple fictif, format JSON).
- `verify.py`: vérification déterministe (citations, entités, garde-fous) + agent vérificateur LLM.
- `chat_graph.py`: route → experts en parallèle (JSON vérifié, 1 révision) → synthèse ⟲ contrôle → finalisation.
- `ingest_graph.py`: extraction ancrée (citation exacte) → diff → experts touchés (vérifiés) → rapport assemblé par le code → ajout « à valider ».
- `llm.py`: seul point de contact avec Ollama; garde de contexte et JSON validé.

```
chat:   route ──Send──▶ expert×N ──▶ synthesize ⟲ ──▶ finalize
                         │ JSON {affirmations, preuves:[Cxxx]}
                         │ ① contrôle en code  ② agent vérificateur  ③ révision (1×)
                         └ ne transmet QUE les affirmations vérifiées
```

## Atténuation des hallucinations
Chaque mesure répond à une cause observée dans la version de base.

| Cause dans la version de base | Changement | Où |
|---|---|---|
| Base trop mince (27 lignes): les experts comblaient les trous (qui a approuvé, ce qui reste ouvert…) | Le dossier Projet360 est chargé passage par passage (fichier + repère), avec statut des tickets lu dans les fichiers. Les questions du README ne sont pas injectées comme réponses | `corpus.py`, `seed.py` |
| Faits remplacés présentés comme actuels (charte « 15 oct », plan v3, rapport « tout vert », captures historiques) | Drapeau `perime` affiché « ⚠ PÉRIMÉ » dans chaque preuve + garde-fou en code: une affirmation appuyée seulement sur du périmé doit le dire | `seed.py`, `kb.render`, `verify.semantic_guards` |
| Citations au niveau du document (`[S16]`): impossible de vérifier que la phrase est dans la source | Les agents citent des **faits** (`[C012]`), convertis en `[S16]` à l'affichage. On compare la phrase au texte du fait cité | `prompts.py`, `verify.to_display` |
| `check_citations` vérifiait seulement que la source existe | Vérification en code de chaque affirmation: citation fournie à l'agent, montants/dates/heures/identifiants/nombres/prénoms présents dans les faits cités (citation réparée si l'entité est dans un autre fait fourni), « livré ≠ validé » contre le statut réel des tickets, go-live « garanti », proposition ≠ décision, mention « à valider » ajoutée | `verify.check_affirmation` |
| Pas de vérification sémantique | **Agent vérificateur** (LLM) qui juge chaque affirmation contre ses preuves: SUPPORTÉ / PARTIEL / NON SUPPORTÉ / CONTREDIT | `verify.llm_verify` |
| Une erreur d'expert passait telle quelle | **Boucle de révision**: les affirmations rejetées reviennent à l'expert avec la raison; re-vérifiées; sinon retirées (et visibles dans `/chat`) | `chat_graph.expert` |
| La synthèse ne voyait pas les preuves et pouvait broder | Synthèse à partir des seules affirmations vérifiées, puis contrôle phrase par phrase; correction (≤ 2 essais), sinon phrases retirées ou **repli déterministe** (liste des affirmations vérifiées) | `chat_graph.synthesize/finalize` |
| Aucune abstention: le modèle répondait toujours | Sans affirmation vérifiée: réponse « je ne trouve pas » écrite par le code. Les « ce qu'on ne sait pas » contenant des entités inventées sont filtrés | `chat_graph.finalize` |
| Domaine entier envoyé à l'expert (dilution, puis dépassement de contexte avec l'ingestion) | Preuves ciblées: identifiants de la question + état courant + BM25, dans un budget | `retrieval.py` |
| Ollama tronque **silencieusement** le début d'un prompt trop long (règles perdues) | Mesure du prompt; dépassement → erreur, preuves réduites puis nouvel essai | `llm.py`, `chat_graph.expert` |
| Règles et données mélangées dans un seul message | Consignes en message système, données en message utilisateur, exemple *fictif* (format sans faits copiables), graine fixe | `prompts.py`, `llm.py` |
| JSON invalide → `{}` silencieux | Validation de schéma + relance avec l'erreur | `llm.ask_json` |
| Routage raté = expert muet | Mots-clés détectés en code ajoutés au choix du LLM | `chat_graph.route` |
| Confiance non exprimée | Niveau calculé en code (sources distinctes, doublons fusionnés, autorité, « à valider ») | `chat_graph._confiance` |
| Extraction: document tronqué à 6 000 caractères | Découpage en morceaux avec recouvrement | `ingest_graph.chunks` |
| Extraction: claims inventés | Chaque claim doit recopier sa phrase source; citation introuvable ou entité absente du document → rejeté (listé dans le rapport) | `ingest_graph.extract`, `verify.quote_in` |
| Extraction: proposition classée « décision », « déployé » classé « validation » | Type corrigé par règles sur la citation; date inventée → « inconnue » | `ingest_graph.fix_type/fix_date` |
| Injection d'instructions dans un document reçu | Document délimité et déclaré « donnée »; aucune instruction suivie; rien n'est fermé sans validateur | `prompts.EXTRACT_SYSTEM` |
| Rapport d'impacts rédigé librement par un LLM | Rapport **assemblé par le code** à partir d'éléments vérifiés; « Ce qui n'a PAS changé » (conditions de go-live, budget) calculé en code; actions non documentées préfixées « Recommandation » | `ingest_graph.report` |

## Tests
- `python tests/smoke_test.py`: sans Ollama. Un faux LLM **hallucine volontairement** (personne et date inventées, citation inexistante, « SEC-210 validé », montant inventé, proposition classée décision, citation d'extraction fabriquée, injection) et le test vérifie que chaque erreur est attrapée, ainsi que l'abstention, le repli déterministe et l'ajout seulement. **Réinitialise ensuite avec `python -m app.seed`**.
- `python tests/eval_qa.py [--quiet]`: avec Ollama. Q01-Q10 + 4 questions-pièges sans réponse dans le dossier; mesure le rappel des éléments clés, les entités inventées (absentes de toute la base), les contradictions de statut et l'abstention. Résultats dans `tests/eval_results.json`.

## Limites connues
- Les claims reprennent les fichiers du dossier. Chaque passage porte un repère (ligne, page ou cellule). Les captures PNG ne sont pas transcrites: leur contenu visuel reste non lu.
- `ledger` n'est plus un fichier séparé: les montants sont relus dans les PDF de `05_Contrats_et_finances`. Un document financier ajouté ensuite par `/ingest` n'entre pas dans ce calcul.
- Le contrôle d'entités est lexical: il attrape chiffres, dates, identifiants, prénoms et statuts, pas une mauvaise relation entre deux faits exacts; c'est le rôle de l'agent vérificateur, lui-même un modèle 8B faillible.
- La vérification multiplie les appels (jusqu'à ~4 par expert): `NOVA_VERIFY_LLM=0` et `NOVA_REVISE=0` accélèrent au prix d'une vérification en code seulement.
- Un nouveau document reçoit une autorité « inconnue »; rien n'est validé sans humain.
