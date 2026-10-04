# NOVA — Guide d'utilisation pour le jury

## Lancement rapide
```bash
cd data/nova_agents
.venv/bin/python -m app.seed        # (optionnel: régénère claims.json)
.venv/bin/python -m app.memory      # (optionnel: régénère memory.json)
uvicorn app.server:app --reload
```
Puis ouvrir http://127.0.0.1:8000

## Navigation

| Page | URL | Contenu |
|------|-----|---------|
| **Brief** | `/brief` | Une page — responsable, date + 3 conditions, portée, budget, priorités. À imprimer. |
| **Mémoire** | `/memoire` | Chronologie (13 événements), décisions (5), contradictions résolues (2), actions (4). |
| **Réponses Q** | `/reponses` | Q01–Q10 avec réponses figées, nuance, et sources (3+ par réponse, ≥2 croisées). |
| **Chat** | `/chat` | Questions libres → agents experts → LLM + vérification. Affiche preuves et rejets. |
| **Ajouter données** | `/ingest` | Upload PDF/eml/txt/xlsx/csv pour intégration, avec rapport d'impacts. |
| **Rapport** | `/` | Tableau complet: décisions, budget, factures, tickets, sources, ajouts. |

## Outils utilisés

### Backtend
- **LangGraph** 0.2+ : orchestration agents (route → experts → synthèse → finalize)
- **FastAPI** 0.110+ : interface web
- **Ollama** (llama3.1 par défaut) : modèle local, pas d'API cloud
- **pypdf** 4.0 : extraction PDF
- **openpyxl** 3.1 : lecture Excel (cellules, commentaires)

### Traitement corpus
- **eml** (courriel) : parsed avec Python email, repère par ligne
- **txt/md** : split par atomes (horodatage, puces, champs) → repère ligne
- **pdf** : lecture pages, repère page
- **xlsx** : cellules non-vides, repère "feuille X, cellule Y"
- **csv** : lignes, repère ligne
- **png** : **traitement manuel** (préprocessing une seule fois, stocké `data/manual/captures.json`)

### Claims
- 412 claims baseline (`data/claims.json`, append-only)
- 8 captures PNG avec transcription manuelle (OPS-601 runbook, SEC-210 audit, ACC-303 modal)
- Sujets: gouvernance, finance, technique, qualité
- Autorité codée: 1 (contrat) → 6 (brouillon) + « inconnue »
- Drapeaux: périmé, à valider, brouillon, hors sujet

## Traitements manuels

### 1. **Captures PNG** (Q10, ACC, SEC, INT, PERF)
- Vision model non disponible à la time de préprocessing
- **Solution:** Transcription manuelle dans `data/manual/captures.json`
- Contenu: OPS-601 (runbook étapes 4-5 manquantes), SEC-210 (audit log champs ABSENT), ACC-303 (modal clavier non accessible)
- Limites: pas de reconnaissance de formes, résumés factuels

### 2. **Commentaires cellule Excel** (plans, registre)
- Openpyxl avec `read_only=True` ignorerait les commentaires
- **Solution:** Lecture pas en read_only (nécessite plus de mémoire, déjà inclus)

### 3. **Réponses Q01–Q10**
- Figées dans `data/answers_baseline.json` (ne changent pas avec le chat LLM)
- Validées manuellement contre les sources (fichier, repère précis)
- Nuance distinguée (proposition vs décision, livré vs validé, recommandation vs engagement)
- 2+ sources croisées pour Q01, Q03, Q05, Q06, Q07, Q10

### 4. **Mémoire structurée**
- Construite manuellement depuis le corpus (`app/memory.py`, sortie `data/memory.json`)
- Aucun LLM, aucune hallucination possible
- Distinctions explicites: proposition (8 sept) vs approbation (10 sept vs 26 sept), livré vs validé

## Limites connues

### Techniques
1. **PNG** : Contenu visuel non transcrit automatiquement. Manuelle, une seule fois.
2. **Modèle LLM** : llama3.1 8B est faillible; vérification en code + agent vérificateur réduit les erreurs. Voir `/chat` affirmations rejetées.
3. **Entités** : Contrôle lexical (chiffres, dates, noms) détecte les inventions basiques, pas les mauvaises relations entre deux faits exacts.
4. **Recherche** : BM25 + identifiants; pas de fusion sémantique (ex. « plan » et « planning » sont des termes séparés).
5. **Ingestion** : Un document ajouté après la baseline reçoit l'autorité « inconnue ». Aucune information n'est validée sans humain.

### Métier
1. **Baseline figée** : État au 30 sept 2026 09:00 Montréal. Arrivée information = `/ingest` + diff vs baseline, jamais fermeture sans approbation écrite.
2. **Mémoire manuelle** : Actions et contradictions codées; nouvelles entrées demandent mise à jour JSON.
3. **Excel commentaires** : Lisibles dans `data/starter/Projet360_NOVA_ETUDIANTS/04_Documents_projet/*.xlsx` directement.

## Vérification de la solution

### Test rapide (2 min)
```bash
# Vérifier que la baseline charge
.venv/bin/python -c "from app import kb, memory; print(f'{len(kb.load_claims())} claims, {len(memory.load_memory()[\"timeline\"])} timeline events')"

# Ouvrir le navigateur
open http://127.0.0.1:8000/brief
open http://127.0.0.1:8000/reponses
```

### Relecture Q01–Q10 (15 min)
Cliquer sur chaque question dans `/reponses`, ouvrir la première preuve (fichier + repère) dans le dossier `data/starter/Projet360_NOVA_ETUDIANTS/`. Vérifier la citation.

### Simulation événement (10 min)
Coller un email fictif dans `/ingest` → rapport d'impacts et claims « à valider ». Baseline (`data/memory.json`) reste inchangée.

## Fichiers clés

- **Corpus** : `data/starter/Projet360_NOVA_ETUDIANTS/` (81 fichiers)
- **Claims** : `data/claims.json` (412 lignes, append-only)
- **Mémoire** : `data/memory.json` (figée au 30 sept)
- **Réponses** : `data/answers_baseline.json` (Q01–Q10 + sources)
- **Captures** : `data/manual/captures.json` (8 PNG transcrites)
- **Code** : `app/{corpus,seed,memory,kb,chat_graph,ingest_graph,server}.py`

## Incertitudes documentées

| Élément | État | Notes |
|---------|------|-------|
| SEC-210 validation | EN VALIDATION | Fix livré 19 sept, validation sécurité attendue, pas complétée au 30 sept |
| ACC-303 | OUVERT | Bloquant accessibilité, condition go-live, échéance inconnue (avant 22 oct) |
| OPS-601 | OUVERT | Étapes 4-5 manquantes, délai à confirmer |
| INV-003 | CONTESTABLE | 18k$ CR-04 non autorisé, ligne à retirer |
| CR-04 budget | REPORTÉ | Phase 2, pas de dépense autorisée sans nouvelle approbation |
| Contacts phase 2 | À confirmer | Aucune plan phase 2 approuvé dans le dossier |

## Questions complémentaires (jury)

Si une réponse manque ou semble inexacte :
1. Vérifier `/brief` ou `/reponses` (sources cliquables)
2. Consulter `/memoire` (chronologie)
3. Chercher dans `/chat` (agents + preuves visibles)
4. Inspecter `data/starter/Projet360_NOVA_ETUDIANTS/` directement (fichiers source)

---

**Dernière mise à jour :** 30 sept 2026 09:00 Montréal (baseline)
**Outils :** LangGraph, FastAPI, Ollama, openpyxl, pypdf
**Responsable données :** Nicolas Perron
