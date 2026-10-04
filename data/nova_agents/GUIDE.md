# NOVA : mode d'emploi

État de référence : **30 septembre 2026, 09 h, Montréal (UTC−4)**. Toutes les réponses sont données à cette date fictive.

## 1. Ouverture

**Sans rien installer (recommandé pour le jury)** : ouvrir `export/index.html` dans un navigateur. L'export est autonome : pages HTML, fichiers du dossier copiés dans `export/raw/`, recherche intégrée. Il ne demande ni Python, ni Ollama, ni connexion.

**Avec le serveur** (nécessaire pour le chat et l'ajout de documents) :
```bash
cd data/nova_agents
pip install -r requirements.txt
python -m app.seed            # (ré)génère data/claims.json depuis le dossier
python -m app.memory          # (ré)génère la baseline data/memory.json
uvicorn app.server:app        # puis http://127.0.0.1:8000 (redirige vers /brief)
python scripts/export_static.py   # régénère export/
```
Le chat demande en plus Ollama : `ollama pull llama3.1`.

## 2. Navigation

| Page | Livrable | Contenu |
|---|---|---|
| Brief | 1 | Une page imprimable : responsable, date approuvée et conditions, portée, budget, factures, priorités (conditions → actions → responsables → échéances). |
| Mémoire | 2 | Chronologie (41 événements typés proposition, décision, validation, livraison ou signal), décisions (proposition → décision → validation), 9 contradictions résolues, conditions de go-live, 10 actions, registre des risques cellule par cellule, sources écartées. |
| Réponses Q01–Q10 | 3 | Réponse, nuance et preuves : fichier, repère humain (horodatage, cellule, page, étape de capture), repère calculé et extrait cité mot pour mot. |
| Mise à jour | 4 | État actuel comparé à la baseline, changements, informations affectées, actions, ce qui n'a pas changé. La baseline reste intacte. |
| Sources | : | Les fichiers du dossier avec autorité, pertinence, doublons et avertissements. |
| Recherche | : | Recherche plein texte sans IA dans tous les passages (fichier et repère). |
| Chat / Ajouter | : | Serveur et Ollama seulement : questions libres vérifiées, aide à l'extraction d'un nouveau document. |

**Retrouver une preuve** : chaque lien ouvre le fichier source au bon endroit (ligne surlignée, page, ligne Excel ou capture avec sa transcription). Exemples : Q10 → `OPS-601_runbook.png` (étapes 4 et 5) ; Q02 → `Registre_Risques_29sept.xlsx`, ligne 2 (R-01 encore « Ouvert »).

**Légende** : `engagement documenté` = quelqu'un s'y est engagé dans le dossier ; `recommandation équipe` = notre proposition, sans trace d'engagement. Échéance « à confirmer » = aucune date écrite au dossier.

## 3. Intégrer la nouvelle information (livrable 4)

1. Déposer le document reçu dans `data/updates/docs/`.
2. Copier `data/updates/_modele.json` en `data/updates/U01_<sujet>.json` et le remplir : statut du problème, décision antérieure, nouvelle proposition, changements (avec un **extrait exact** du document comme preuve), actions touchées, nouvelles actions. `/ingest` (Ollama) peut aider à repérer les extraits.
3. Ouvrir **Mise à jour**, puis régénérer l'export.

Le code applique trois garde-fous :
- un extrait introuvable dans le document écarte le changement ;
- un statut « approuvé » ou « validé » sans approbation explicite et sans approbateur est rétrogradé en « proposé », car une proposition ne remplace jamais une décision ;
- une condition de go-live n'est levée que par son validateur (Sophie pour C1, Mélissa pour C2, Olivier pour C3).

`data/memory.json` et `data/answers_baseline.json` ne sont jamais réécrits, et le tag git `baseline-30sept-09h00` conserve la version initiale. Une démonstration avec un document **fictif** est disponible sur le serveur : `/mise-a-jour?exercice=1` (fichiers dans `tests/fixtures/`, jamais chargés dans `data/`).

## 4. Outils utilisés

- **Python** : FastAPI (pages), pypdf (PDF, repère par page), openpyxl (Excel, repère par cellule), module `email` (courriels, repère par ligne de la vue normalisée).
- **LangGraph et Ollama (llama3.1, local, gratuit)** : seulement pour le chat et l'aide à l'extraction. Les pages livrables n'utilisent aucun LLM.
- **Claude Code (Anthropic)** : assistant de développement. Il a servi à écrire le code, à relire le dossier et à rédiger la première version des réponses, de la mémoire et des transcriptions de captures. Chaque fait a ensuite été vérifié contre le dossier, et les extraits cités sont contrôlés automatiquement (`tests/test_deliverables.py`).
- Aucun service payant, aucune recherche externe pour les faits : tous les faits viennent du dossier.

## 5. Traitements manuels

| Traitement | Où | Contrôle |
|---|---|---|
| Transcription des 8 captures PNG (aucun modèle de vision n'a été utilisé) | `data/manual/captures.json` | Relue contre les images. Les captures historiques sont marquées « ne prouve pas que le défaut reste ouvert » |
| Rédaction de Q01–Q10 | `data/answers_baseline.json` | Chaque extrait est retrouvé dans le fichier cité (test automatique) |
| Chronologie, décisions, contradictions, actions | `app/memory.py` → `data/memory.json` | Idem. Natures et responsables attribués à la main |
| Classement autorité et pertinence des sources | `app/corpus.py` | Règles codées par dossier et par nom de fichier |
| Montants (autorisé, facturé, payé) | calculés par le code depuis les PDF | Test : 204 000 / 186 000 / 132 000 |

## 6. Limites

- Les transcriptions de captures sont manuelles. Une erreur de lecture reste possible, mais l'image originale est affichée à côté.
- Les repères « ligne N » des courriels renvoient à la vue normalisée (De, Date, Objet, corps), pas au fichier `.eml` brut.
- La recherche est lexicale (termes exacts, accents ignorés), pas sémantique.
- Le chat repose sur un modèle 8B local. Les affirmations sont vérifiées en code et par un agent vérificateur, mais il reste faillible : les réponses de référence sont dans **Réponses Q01–Q10**.
- Un document ajouté par `/ingest` reçoit une autorité « inconnue » et le statut « à valider ». Rien n'est validé sans humain.

## 7. Informations incertaines ou manquantes (au 30 septembre)

| Élément | Ce qu'on sait | Ce qui manque |
|---|---|---|
| SEC-210 (C1) | Correctif déployé en **validation** le 19 sept ; re-test « planifié » (26 sept, 15:40) | Date du re-test, résultat, acceptation |
| ACC-303 (C2) | Correctif « annoncé pour la prochaine build » | Date de la build, livraison, re-test |
| Runbook OPS-601 (C3) | Étapes 4 (retour arrière) et 5 (validation post-déploiement) manquantes ; version finale non reçue au 29 sept | Échéance (Olivier veut « quelques jours avant ») |
| INV-003 | Ligne CR-04 de 18 000 $ non autorisée ; Finances en attente (23 sept) | Réponse de Nicolas à Amélie ; facture corrigée ou note de crédit |
| Communication « au vert » d'Alex | Brouillon du 21 sept basé sur le rapport erroné | Envoyée ou corrigée? |
| Plan projet | v3 (12 sept) indique encore le 15 octobre | Version corrigée |
| Registre des risques | R-01 encore « Ouvert » au 29 sept | Mise à jour du registre |
| Canada Central | Migration déclarée par Boréal (26 août) et vérifiée par l'architecture (27 août) | Aucune preuve sur l'environnement de production lui-même (pas encore en production) |
| Ajustements mobiles | Julien : « on a déjà commencé à regarder » (26 sept) | Ces travaux relèvent-ils de CR-04? |
| Vote du 10 sept | Sophie, Marc et Olivier « Non » à l'opposition ; Nicolas « D'accord » | Position transcrite de Mélissa et de Camille |

## 8. Vérifier

```bash
python tests/test_deliverables.py   # sans Ollama : extraits, montants, garde-fous, baseline intacte
python tests/smoke_test.py          # sans Ollama : garde-fous du chat (puis relancer python -m app.seed)
python tests/eval_qa.py --quiet     # avec Ollama : qualité du chat sur Q01–Q10
```
