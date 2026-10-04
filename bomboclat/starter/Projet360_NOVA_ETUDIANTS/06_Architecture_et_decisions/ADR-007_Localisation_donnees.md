# ADR-007 - Localisation des données de production

**Date de décision :** 23 juillet 2026  
**Statut :** Acceptée

## Contexte
L'architecture initiale de NOVA utilisait une région américaine. L'équipe sécurité demande que les données de production du projet demeurent au Canada.

## Décision
L'environnement de production de NOVA sera déployé dans **Canada Central**. L'architecture v1 doit être considérée comme remplacée sur ce point.

## Conséquences
- Boréal doit migrer les ressources prévues.
- L'équipe architecture doit publier une version mise à jour du schéma.
- Une validation technique doit confirmer la migration avant les tests de production.
