"""Mémoire structurée de la baseline (30 sept 2026, 09 h): chronologie, décisions, contradictions, actions.

Rédigée à la main à partir du dossier, sans LLM. Chaque élément cite un extrait VERBATIM ({fichier, extrait});
evidence.locate() retrouve le repère (ligne, page, cellule, capture) et tests/test_deliverables.py échoue si un
extrait est introuvable. On distingue partout:
- nature d'un événement: proposition | décision | validation | livraison | fait | signal (affirmation non fiable);
- nature d'une action: « engagement documenté » (quelqu'un s'y est engagé dans le dossier) ou
  « recommandation équipe » (notre proposition, aucune trace d'engagement);
- échéance: une date écrite dans le dossier, sinon « à confirmer ».
"""
import json
from pathlib import Path
from . import evidence, kb

DATA = Path(__file__).resolve().parent.parent / "data"
MEMORY_FILE = DATA / "memory.json"

M01 = "02_Reunions/M01_CR_Demarrage_07juillet.txt"
M02 = "02_Reunions/M02_Transcript_Architecture_23juillet.txt"
M03 = "02_Reunions/M03_CR_Comite_27aout.txt"
M04 = "02_Reunions/M04_Transcript_Comite_direction_10sept.txt"
M05 = "02_Reunions/M05_CR_Suivi_18sept.txt"
M06 = "02_Reunions/M06_Transcript_Comite_26sept.txt"
CHARTE = "04_Documents_projet/Charte_Projet_NOVA_v1.txt"
NOTE = "04_Documents_projet/Note_transition_Elodie_16sept.txt"
PLAN2 = "04_Documents_projet/Plan_Projet_NOVA_v2.xlsx"
PLAN3 = "04_Documents_projet/Plan_Projet_NOVA_v3_12sept.xlsx"
RAPPORT = "04_Documents_projet/Rapport_Statut_21sept.pdf"
REGISTRE = "04_Documents_projet/Registre_Risques_29sept.xlsx"
CONTRAT = "05_Contrats_et_finances/CONTRAT_Boreal_NOVA.pdf"
CR01 = "05_Contrats_et_finances/CR-01_Rapports_avances_APPROUVE.pdf"
CR04 = "05_Contrats_et_finances/CR-04_Optimisation_mobile_BROUILLON.pdf"
INV2 = "05_Contrats_et_finances/INV-002.pdf"
INV3 = "05_Contrats_et_finances/INV-003.pdf"
ADR = "06_Architecture_et_decisions/ADR-007_Localisation_donnees.md"
ARCH1 = "06_Architecture_et_decisions/Architecture_NOVA_v1.pdf"
ARCH2 = "06_Architecture_et_decisions/Architecture_NOVA_v2.pdf"
PORTEE = "06_Architecture_et_decisions/Decision_Portee_Phase2.md"
T = "03_Tickets/"
E = "01_Courriels/"
TEAMS = "07_Conversations_Teams/"
ARCH = "08_Archives_et_documents_connexes/"


def s(fichier: str, extrait: str, **kw) -> dict:
    return {"fichier": fichier, "extrait": extrait, **kw}


TIMELINE = [
    ("2026-07-07", "", "décision", "Comité de démarrage", "Démarrage : Élodie Caron chargée de projet, budget 180 000 $, cible 15 octobre, portée phase 1",
     [s(M01, "Cible de mise en production : 15 octobre 2026."), s(E + "E01_Lancement_NOVA.eml", "je prends le rôle de chargée de projet")]),
    ("2026-07-18", "", "fait", "Boréal", "Architecture v1 : données en East US (landing zone standard de Boréal)",
     [s(ARCH1, "Version initiale préparée avant la décision de localisation des données.")]),
    ("2026-07-22", "14:32", "proposition", "Sophie Lambert", "La sécurité demande que les données de production restent au Canada",
     [s(E + "E02_Question_hebergement.eml", "je veux que les données de production demeurent au Canada")]),
    ("2026-07-23", "09:10", "décision", "Atelier architecture (Élodie, Marc, Sophie, Julien)", "Canada Central retenu, puis formalisé par l'ADR-007 (Acceptée). La v1 devient obsolète pour la localisation",
     [s(M02, "09:10 Élodie : Donc on tranche Canada Central?"), s(ADR, "L'environnement de production de NOVA sera déployé dans Canada Central.")]),
    ("2026-07-23", "09:15", "décision", "Sophie Lambert", "Authentification : SSO uniquement en production",
     [s(M02, "SSO seulement en production.")]),
    ("2026-08-14", "", "décision", "Comité de projet", "CR-01 (rapports avancés, 24 000 $) approuvé",
     [s(CR01, "APPROUVÉE Date de décision 14 août 2026 Autorité Comité de projet")]),
    ("2026-08-15", "", "validation", "Mélissa Gagnon", "ACC-301 (libellés) validé avec NVDA et VoiceOver, puis fermé",
     [s(T + "ACC-301.txt", "15 août - Mélissa : Validé avec NVDA et VoiceOver. Fermé.")]),
    ("2026-08-20", "", "validation", "Mélissa Gagnon", "ACC-302 (contraste) re-testé à 5,3:1, puis fermé",
     [s(T + "ACC-302.txt", "20 août - Mélissa : Re-test OK à 5,3:1. Fermé.")]),
    ("2026-08-20", "15:44", "signal", "Julien Moreau (Boréal)", "Boréal affirme que « tout devrait être conforme ». Mélissa voulait encore repasser les modales au clavier",
     [s(E + "E04_Corrections_accessibilite.eml", "Tout devrait maintenant être conforme de notre côté.")]),
    ("2026-08-26", "09:05", "livraison", "Julien Moreau (Boréal)", "Boréal annonce la migration vers Canada Central complétée (schéma v2 du 25 août en PJ)",
     [s(E + "E03_Confirmation_Canada_Central.eml", "La migration des ressources prévues pour NOVA vers Canada Central est complétée.")]),
    ("2026-08-27", "", "validation", "Comité projet / équipe architecture", "Migration Canada Central vérifiée par l'équipe architecture. Aucun report de date approuvé à ce moment",
     [s(M03, "déclarée terminée par Boréal et vérifiée par l'équipe architecture"), s(M03, "aucun retard officiel de la date du 15 octobre n'est approuvé à ce moment")]),
    ("2026-09-02", "", "fait", "Camille Beaulieu", "DATA-401 ouvert : doublons dans le lot de migration MIG-09-02",
     [s(T + "DATA-401.txt", "Titre : Doublons migration - lot MIG-09-02")]),
    ("2026-09-04", "", "proposition", "Boréal Numérique", "CR-04 (optimisation mobile avancée, 18 000 $) soumis au statut de BROUILLON",
     [s(CR04, "BROUILLON - APPROBATION REQUISE")]),
    ("2026-09-05", "11:18", "fait", "Marc Gervais / Boréal", "INT-101 ouvert : recherches vides en intégration, erreurs 401, jeton de service expiré",
     [s(T + "INT-101.txt", "On voit des 401 sur l'appel vers le service interne.")]),
    ("2026-09-07", "09:12", "validation", "Support", "PERF-501 fermé : 620 ms en moyenne sur 50 essais (6 à 8 s avant le correctif)",
     [s(T + "PERF-501.txt", "07 sept 09:12 - Support : moyenne observée 620 ms sur 50 essais.")]),
    ("2026-09-08", "11:16", "proposition", "Julien Moreau (Boréal)", "Boréal propose de déplacer la mise en production au 22 octobre",
     [s(E + "E05_Retard_integration.eml", "À ce stade, il s'agit d'une proposition de notre part.")]),
    ("2026-09-09", "", "validation", "Camille Beaulieu", "DATA-401 : 15 000 événements rejoués sans doublon, puis fermé",
     [s(T + "DATA-401.txt", "9 septembre - lot de 15 000 événements rejoué, aucun doublon détecté. Ticket fermé.")]),
    ("2026-09-10", "15:25", "décision", "Comité de direction (décision formulée par Élodie Caron)", "Le 22 octobre 2026 devient la date officielle. Ce n'est pas un go automatique",
     [s(M04, "15:25 Élodie : Donc approuvé. Le 22 devient la date officielle."), s(M04, "le 22 n'est pas un go automatique")]),
    ("2026-09-10", "15:40", "décision", "Comité de direction", "Mobile (environ 18 000 $) : aucune décision de dépense",
     [s(M04, "Mobile : aucune décision de dépense.")]),
    ("2026-09-12", "", "signal", "Plan projet v3", "Le plan v3 indique encore le 15 octobre pour la mise en production (non corrigé après la décision du 10 septembre)",
     [s(PLAN3, "Fin planifiée: 2026-10-15 | Note: Cible de planification")]),
    ("2026-09-12", "", "fait", "Sophie Lambert", "SEC-210 ouvert : export CSV mal journalisé (objet et résultat absents), bloquant avant production",
     [s(T + "SEC-210.txt", "Priorité : Bloquante avant production")]),
    ("2026-09-15", "09:18", "fait", "Nicolas Perron", "Nicolas corrige Alex, qui préparait une communication sur le 15 octobre",
     [s(TEAMS + "Teams_15sept_ProjetNOVA.txt", "Le plan projet n'a visiblement pas encore été corrigé.")]),
    ("2026-09-16", "08:35", "décision", "Élodie Caron", "Nicolas Perron prend officiellement la charge du projet",
     [s(E + "E06_Transition_charge_projet.eml", "Nicolas Perron prend officiellement la charge du projet NOVA à compter d'aujourd'hui, 16 septembre.")]),
    ("2026-09-17", "16:10", "validation", "Marc Gervais", "INT-101 validé (120 recherches sur 120) et fermé : la cause du report est résolue",
     [s(T + "INT-101.txt", "17 sept 16:10 - Marc : Validé côté intégration. Je ferme."), s(E + "E12_Resolution_integration.eml", "120/120 recherches ont retourné les résultats attendus.")]),
    ("2026-09-17", "13:14", "fait", "Mélissa Gagnon", "ACC-303 ouvert : le bouton Enregistrer de la modale est inatteignable au clavier",
     [s(T + "ACC-303.txt", "le bouton Enregistrer n'est jamais atteint avec Tab")]),
    ("2026-09-18", "", "fait", "Suivi de livraison", "Le 22 octobre reste la date approuvée. Le runbook n'est pas final et SEC-210 devra être validé après livraison",
     [s(M05, "Le 22 octobre reste la date approuvée."), s(M05, "Exploitation : le runbook n'est pas final.")]),
    ("2026-09-19", "10:20", "livraison", "Julien Moreau (Boréal)", "Correctif SEC-210 déployé en environnement de validation (pas en production)",
     [s(E + "E08_Correctif_journalisation.eml", "Le correctif pour SEC-210 est déployé en validation depuis ce matin.")]),
    ("2026-09-19", "14:05", "fait", "Sophie Lambert", "La sécurité refuse la fermeture tant qu'elle n'a pas fait son propre re-test",
     [s(T + "SEC-210.txt", "Ne pas fermer avant validation sécurité.")]),
    ("2026-09-21", "", "signal", "Rapport de statut", "Le rapport de statut met Sécurité et Accessibilité au VERT. Il a été préparé avant la vérification des tickets",
     [s(RAPPORT, "Le rapport a été préparé avant la dernière vérification détaillée de certains tickets.")]),
    ("2026-09-21", "16:28", "signal", "Alex Deschamps", "Brouillon de communication « NOVA est au vert… sécurité et accessibilité complétées »",
     [s(E + "E11_Communication_statut.eml", "La sécurité et l'accessibilité sont complétées et le projet vise le 22 octobre.")]),
    ("2026-09-22", "", "fait", "Boréal Numérique", "INV-003 émise : 54 000 $, dont 18 000 $ pour CR-04",
     [s(INV3, "Optimisation interface mobile - CR-04 18 000 $")]),
    ("2026-09-22", "13:06", "fait", "Nicolas Perron", "Nicolas rappelle que le package CR-04 (18 000 $) n'est pas approuvé",
     [s(TEAMS + "Teams_22sept_Mobile.txt", "Le package d'optimisation CR-04 à 18k non. Il n'est pas approuvé.")]),
    ("2026-09-23", "10:18", "fait", "Amélie Fortin (Finances)", "Les Finances bloquent INV-003 et demandent l'approbation de CR-04",
     [s(E + "E07_Facture_003_question.eml", "Peux-tu me transmettre l'approbation correspondante?")]),
    ("2026-09-24", "13:42", "décision", "Nicolas Perron", "CR-04 reporté à la phase 2 : aucune dépense ni facturation sans nouvelle approbation",
     [s(E + "E10_Fonction_mobile.eml", "Nous les reportons à la phase 2."), s(PORTEE, "Aucune dépense additionnelle liée à CR-04 ne doit être engagée sans nouvelle approbation.")]),
    ("2026-09-25", "", "fait", "Olivier Côté", "OPS-601 : le runbook (version du 25 septembre) n'est pas prêt. Il manque les étapes 4 (retour arrière) et 5 (validation post-déploiement)",
     [s(T + "OPS-601.txt", "Il manque au minimum la procédure de rollback."), s(T + "OPS-601_runbook.png", "Étape 4. Procédure de retour arrière — TODO")]),
    ("2026-09-26", "10:09", "décision", "Comité de direction (Nicolas Perron)", "La cible du 22 octobre est confirmée, conditionnelle à trois éléments : SEC-210, ACC-303 et le runbook avec rollback",
     [s(M06, "Donc trois conditions concrètes : validation sécurité de SEC-210, fermeture de ACC-303 et approbation du runbook incluant rollback.")]),
    ("2026-09-26", "11:03", "fait", "Mélissa Gagnon", "ACC-303 toujours ouvert. Correctif annoncé pour la prochaine build",
     [s(T + "ACC-303.txt", "Toujours ouvert. Correctif annoncé pour la prochaine build.")]),
    ("2026-09-26", "15:40", "fait", "Sophie Lambert", "SEC-210 : re-test planifié (date non indiquée). Statut maintenu EN VALIDATION",
     [s(T + "SEC-210.txt", "26 sept 15:40 - Sophie : Re-test planifié. Statut maintenu EN VALIDATION.")]),
    ("2026-09-27", "17:02", "fait", "Nicolas Perron", "Rappel : le 22 octobre est conditionnel. Ne pas le communiquer comme un go garanti",
     [s(E + "E09_Rappel_mise_en_production.eml", "Merci de ne pas communiquer le 22 comme un go garanti tant que ces validations ne sont pas terminées.")]),
    ("2026-09-29", "", "signal", "Registre des risques", "Le registre du 29 septembre laisse R-01 (connecteur) « Ouvert », avec un suivi daté du 9 septembre",
     [s(REGISTRE, "Statut: Ouvert | Mitigation: Suivi fournisseur hebdomadaire | Commentaire: Suivi au 9 septembre 2026")]),
    ("2026-09-29", "", "fait", "Olivier Côté", "OPS-601 : version finale du runbook toujours pas reçue",
     [s(T + "OPS-601.txt", "29 sept - Olivier : Toujours pas reçu la version finale.")]),
]

DECISIONS = [
    {"sujet": "Date de mise en production",
     "remplace": {"valeur": "15 octobre 2026", "preuve": s(M01, "Cible de mise en production : 15 octobre 2026.")},
     "proposition": {"qui": "Julien Moreau (Boréal)", "quand": "2026-09-08", "preuve": s(E + "E05_Retard_integration.eml", "Notre recommandation est de déplacer la mise en production au 22 octobre.")},
     "decision": {"qui": "Comité de direction, décision formulée par Élodie Caron (sans opposition)", "quand": "2026-09-10", "valeur": "22 octobre 2026",
                  "preuve": s(M04, "15:25 Élodie : Donc approuvé. Le 22 devient la date officielle.")},
     "validation": {"qui": "Comité de direction (Nicolas Perron)", "quand": "2026-09-26", "valeur": "Cible confirmée, conditionnelle à 3 éléments (pas un go garanti)",
                    "preuve": s(M06, "c'est conditionnel à ces trois éléments")}},
    {"sujet": "Hébergement des données de production",
     "remplace": {"valeur": "East US (architecture v1)", "preuve": s(ARCH1, "East US")},
     "proposition": {"qui": "Sophie Lambert (sécurité)", "quand": "2026-07-22", "preuve": s(E + "E02_Question_hebergement.eml", "je veux que les données de production demeurent au Canada")},
     "decision": {"qui": "Atelier architecture, ADR-007 (Acceptée)", "quand": "2026-07-23", "valeur": "Canada Central",
                  "preuve": s(ADR, "L'environnement de production de NOVA sera déployé dans Canada Central.")},
     "validation": {"qui": "Équipe architecture (déclaration de Boréal le 26 août, vérification le 27 août)", "quand": "2026-08-27", "valeur": "Migration vérifiée",
                    "preuve": s(M03, "déclarée terminée par Boréal et vérifiée par l'équipe architecture")}},
    {"sujet": "Chargé de projet",
     "remplace": {"valeur": "Élodie Caron (depuis le 7 juillet)", "preuve": s(M01, "Élodie Caron agit comme chargée de projet.")},
     "proposition": None,
     "decision": {"qui": "Élodie Caron (transition annoncée)", "quand": "2026-09-16", "valeur": "Nicolas Perron",
                  "preuve": s(NOTE, "À compter d'aujourd'hui, Nicolas Perron reprend le rôle de chargé de projet NOVA.")},
     "validation": None},
    {"sujet": "CR-01 : rapports avancés",
     "remplace": None, "proposition": None,
     "decision": {"qui": "Comité de projet", "quand": "2026-08-14", "valeur": "Approuvé : +24 000 $ (autorisé total 204 000 $)",
                  "preuve": s(CR01, "APPROUVÉE Date de décision 14 août 2026 Autorité Comité de projet")},
     "validation": {"qui": "Facturé sur INV-002 (payée)", "quand": "2026-08-31", "valeur": "Facturé et payé", "preuve": s(INV2, "Rapports avancés - CR-01 24 000 $")}},
    {"sujet": "CR-04 : optimisation mobile avancée",
     "remplace": None,
     "proposition": {"qui": "Boréal Numérique (brouillon)", "quand": "2026-09-04", "preuve": s(CR04, "Montant estimé 18 000 $")},
     "decision": {"qui": "Nicolas Perron, chargé de projet (le comité du 10 septembre n'avait rien approuvé)", "quand": "2026-09-24", "valeur": "Non approuvé, reporté à la phase 2",
                  "preuve": s(PORTEE, "Les optimisations mobiles avancées associées à la demande CR-04 sont reportées à la phase 2.")},
     "validation": {"qui": "Comité de direction (Nicolas Perron)", "quand": "2026-09-26", "valeur": "Rappel : ne pas facturer",
                    "preuve": s(M06, "Facturer du CR-04, non. Il n'est pas approuvé.")}},
    {"sujet": "Conditions de go-live",
     "remplace": None, "proposition": None,
     "decision": {"qui": "Comité de direction (Nicolas Perron; Sophie, Mélissa et Olivier répondent « Oui »)", "quand": "2026-09-26",
                  "valeur": "C1 validation sécurité de SEC-210; C2 fermeture d'ACC-303; C3 approbation du runbook incluant le rollback",
                  "preuve": s(M06, "Donc trois conditions concrètes : validation sécurité de SEC-210, fermeture de ACC-303 et approbation du runbook incluant rollback.")},
     "validation": None},
    {"sujet": "Authentification",
     "remplace": None, "proposition": None,
     "decision": {"qui": "Atelier architecture (Sophie Lambert)", "quand": "2026-07-23", "valeur": "SSO uniquement en production", "preuve": s(M02, "SSO seulement en production.")},
     "validation": None},
]

CONTRADICTIONS = [
    {"sujet": "Date de mise en production : 15 ou 22 octobre",
     "type": "document de référence", "regle": "date et autorité",
     "affirmations": [
         {"date": "2026-07-07", "autorite": "Charte v1 (point de départ, non mise à jour)", "texte": "15 octobre 2026", "preuve": s(CHARTE, "Date cible de mise en production : 15 octobre 2026")},
         {"date": "2026-09-10", "autorite": "Décision du comité de direction", "texte": "22 octobre 2026", "preuve": s(M04, "Le 22 devient la date officielle.")}],
     "resolution": "Le 22 octobre fait foi. C'est une décision formelle, postérieure à la charte, et la charte précise elle-même qu'elle « n'est pas mise à jour automatiquement après chaque décision de comité ».",
     "preuve_resolution": s(CHARTE, "n'est pas mise à jour automatiquement après chaque décision de comité")},
    {"sujet": "Plan projet v3 (12 sept) : mise en production le 15 octobre",
     "type": "plan", "regle": "autorité, puis date",
     "affirmations": [
         {"date": "2026-09-12", "autorite": "Plan projet v3 (outil de planification)", "texte": "P-06 Mise en production : 2026-10-15, « Cible de planification », responsable Nicolas Perron", "preuve": s(PLAN3, "Fin planifiée: 2026-10-15 | Note: Cible de planification")},
         {"date": "2026-09-10", "autorite": "Décision du comité de direction", "texte": "22 octobre approuvé", "preuve": s(M04, "On doit mettre les plans et communications à jour.")}],
     "resolution": "Le plan est plus récent que la décision, mais il ne la remplace pas : c'est un outil de planification que personne n'a corrigé. Nicolas le confirme le 15 septembre, et la note de transition du 16 septembre demande de mettre la date à jour dans tous les plans. Le 22 octobre fait foi.",
     "preuve_resolution": s(TEAMS + "Teams_15sept_ProjetNOVA.txt", "Le plan projet n'a visiblement pas encore été corrigé.")},
    {"sujet": "Registre des risques (29 sept) : R-01 « Ouvert » alors qu'INT-101 est fermé",
     "type": "registre de risques", "regle": "date des faits (pas date du fichier)",
     "affirmations": [
         {"date": "2026-09-29", "autorite": "Registre des risques (fichier daté du 29 septembre)", "texte": "R-01 Retard du connecteur interne : Ouvert, « Suivi au 9 septembre 2026 »", "preuve": s(REGISTRE, "Statut: Ouvert | Mitigation: Suivi fournisseur hebdomadaire | Commentaire: Suivi au 9 septembre 2026")},
         {"date": "2026-09-17", "autorite": "Ticket fermé par le propriétaire du risque, Marc Gervais (+ courriel E12)", "texte": "INT-101 validé et fermé, risque d'échéancier résolu", "preuve": s(E + "E12_Resolution_integration.eml", "Le problème d'intégration qui avait déclenché le risque d'échéancier est considéré résolu.")}],
     "resolution": "Le fichier date du 29 septembre, mais la ligne R-01 décrit l'état au 9 septembre. Le fait le plus récent (fermeture du 17 septembre par Marc Gervais, propriétaire du risque) l'emporte. R-01 est à fermer dans le registre. Une date de fichier récente ne garantit pas une information à jour.",
     "preuve_resolution": s(T + "INT-101.txt", "17 sept 16:10 - Marc : Validé côté intégration. Je ferme.")},
    {"sujet": "Rapport de statut (21 sept) : Sécurité et Accessibilité au VERT",
     "type": "rapport", "regle": "autorité (validateur désigné) et aveu du rapport",
     "affirmations": [
         {"date": "2026-09-21", "autorite": "Rapport de statut (synthèse)", "texte": "Sécurité VERT, Accessibilité VERT, Budget VERT", "preuve": s(RAPPORT, "Sécurité VERT Correctif SEC-210 livré")},
         {"date": "2026-09-26", "autorite": "Validatrices désignées (Sophie Lambert, Mélissa Gagnon), en comité", "texte": "SEC-210 non accepté, ACC-303 bloquant", "preuve": s(M06, "Nous n'avons pas encore donné l'acceptation sécurité de SEC-210.")}],
     "resolution": "Le rapport confond livraison et validation. Il reconnaît d'ailleurs avoir été préparé avant la dernière vérification détaillée des tickets. Les tickets (SEC-210 EN VALIDATION, ACC-303 OUVERT) et les validatrices font foi. Le VERT budget masque la ligne CR-04 non autorisée de INV-003.",
     "preuve_resolution": s(RAPPORT, "Le rapport a été préparé avant la dernière vérification détaillée de certains tickets.")},
    {"sujet": "Communication « NOVA est au vert » (brouillon d'Alex, 21 sept)",
     "type": "courriel", "regle": "source dérivée d'un rapport erroné, contredite par le chargé de projet",
     "affirmations": [
         {"date": "2026-09-21", "autorite": "Brouillon non publié, basé sur le rapport", "texte": "Sécurité et accessibilité complétées", "preuve": s(E + "E11_Communication_statut.eml", "La sécurité et l'accessibilité sont complétées et le projet vise le 22 octobre.")},
         {"date": "2026-09-27", "autorite": "Chargé de projet", "texte": "Le 22 est conditionnel, à ne pas communiquer comme un go garanti", "preuve": s(E + "E09_Rappel_mise_en_production.eml", "Merci de ne pas communiquer le 22 comme un go garanti tant que ces validations ne sont pas terminées.")}],
     "resolution": "La position de Nicolas (27 septembre) fait foi. Le dossier ne dit pas si le message d'Alex a été envoyé ou corrigé : information manquante.",
     "preuve_resolution": s(E + "E11_Communication_statut.eml", "Je me base surtout sur le rapport de statut que j'ai reçu.")},
    {"sujet": "SEC-210 « réglé » (Boréal) ou « en validation » (sécurité)",
     "type": "ticket", "regle": "autorité (validateur) : livré ≠ accepté",
     "affirmations": [
         {"date": "2026-09-19", "autorite": "Fournisseur", "texte": "Fix déployé, « pour nous c'est réglé »", "preuve": s(T + "SEC-210.txt", "Fix déployé sur l'environnement de validation. Pour nous c'est réglé.")},
         {"date": "2026-09-26", "autorite": "Responsable sécurité (validatrice)", "texte": "Re-test planifié, statut maintenu EN VALIDATION", "preuve": s(T + "SEC-210.txt", "Re-test planifié. Statut maintenu EN VALIDATION.")}],
     "resolution": "Seule la sécurité peut accepter. SEC-210 reste EN VALIDATION : le correctif est livré, il n'est pas validé.",
     "preuve_resolution": s(TEAMS + "Teams_19sept_Securite.txt", "« déployé » != « accepté »")},
    {"sujet": "Accessibilité « conforme » (Boréal, 20 août) puis ACC-303 ouvert",
     "type": "courriel", "regle": "date des faits et autorité (QA accessibilité)",
     "affirmations": [
         {"date": "2026-08-20", "autorite": "Fournisseur", "texte": "Tout devrait maintenant être conforme", "preuve": s(E + "E04_Corrections_accessibilite.eml", "Tout devrait maintenant être conforme de notre côté.")},
         {"date": "2026-09-26", "autorite": "Responsable accessibilité", "texte": "ACC-303 bloquant avant production", "preuve": s(M06, "Pour moi c'est un bloquant d'accessibilité avant production.")}],
     "resolution": "Les corrections de libellés et de contraste sont réellement validées (ACC-301 et ACC-302). Le passage clavier sur les modales, demandé dès le 12 août, a révélé ACC-303, toujours ouvert.",
     "preuve_resolution": s(E + "E04_Corrections_accessibilite.eml", "Je veux aussi repasser les modales au clavier dans une prochaine build.")},
    {"sujet": "Mobile avancé inclus dans la portée? (Julien, 22 sept)",
     "type": "conversation", "regle": "autorité (contrat et charte) et décision du 24 sept",
     "affirmations": [
         {"date": "2026-09-22", "autorite": "Fournisseur (Teams)", "texte": "Le mobile avancé serait dans le scope initial", "preuve": s(TEAMS + "Teams_22sept_Mobile.txt", "Je pensais que le mobile était inclus dans le scope initial, au moins l'optimisation avancée.")},
         {"date": "2026-09-24", "autorite": "Décision de portée", "texte": "Reporté à la phase 2, hors phase 1", "preuve": s(PORTEE, "ne font pas partie de la portée approuvée de la phase 1")}],
     "resolution": "La portée du contrat et de la charte ne mentionne pas le mobile avancé, et M01 note qu'il n'a pas été discuté comme livrable. La phase 1 doit seulement rester utilisable sur mobile.",
     "preuve_resolution": s(M01, "L'expérience mobile avancée n'a pas été discutée comme livrable distinct pendant cette rencontre.")},
    {"sujet": "Notes personnelles : « 15 oct encore date? probablement »",
     "type": "note", "regle": "source non fiable (auteur non identifié)",
     "affirmations": [
         {"date": "inconnue", "autorite": "Notes personnelles, auteur non identifié", "texte": "15 octobre probablement", "preuve": s(ARCH + "Notes_personnelles_quelquun.txt", "vérifier si 15 oct encore date? probablement")},
         {"date": "2026-09-10", "autorite": "Décision du comité de direction", "texte": "22 octobre", "preuve": s(M04, "Le 22 devient la date officielle.")}],
     "resolution": "La note est écartée : elle n'est ni officielle ni datée, et son auteur est inconnu.",
     "preuve_resolution": s(ARCH + "Notes_personnelles_quelquun.txt", "Notes personnelles non officielles, auteur non identifié.")},
]

# Sources qui ne comptent pas comme confirmations indépendantes, ou hors projet
SOURCES_ECARTEES = [
    {"fichier": ARCH + "Courriel_archive_17sept.eml", "raison": "Doublon exact d'E12 (même expéditeur, même date, même texte) : ce n'est pas une confirmation indépendante."},
    {"fichier": ARCH2, "raison": "Pièce jointe d'E03 : même source que la déclaration de Boréal."},
    {"fichier": INV3, "raison": "Aussi en pièce jointe d'E07 : compte une seule fois."},
    {"fichier": CR04, "raison": "Aussi en pièce jointe d'E10. C'est un brouillon, ni approbation ni engagement."},
    {"fichier": RAPPORT, "raison": "Aussi en pièce jointe d'E11 : compte une seule fois."},
    {"fichier": ARCH + "INV-778_Projet_ORION.pdf", "raison": "Facture d'un autre projet (ORION) : exclue des calculs NOVA."},
    {"fichier": ARCH + "Plan_NOVA_preliminaire_juin.xlsx", "raison": "Plan préliminaire de juin, remplacé."},
    {"fichier": ARCH + "Invitation_Formation_Excel.txt", "raison": "Hors sujet."},
    {"fichier": ARCH + "Newsletter_Boreal_Septembre.txt", "raison": "Hors sujet."},
]

ACTIONS = [
    {"id": "A1", "court": "Re-test et acceptation sécurité : Sophie Lambert", "echeance_court": "à confirmer (re-test planifié, sans date)", "condition": "C1", "action": "Re-tester SEC-210 (scénario d'export CSV) et prononcer l'acceptation sécurité, ou la refuser",
     "executant": "Sophie Lambert (sécurité)", "validateur": "Sophie Lambert", "statut_resp": "confirmé",
     "echeance": "à confirmer : re-test « planifié » le 26 sept, sans date. Doit précéder le go-live du 22 oct", "nature": "engagement documenté", "statut": "EN VALIDATION",
     "preuves": [s(T + "SEC-210.txt", "26 sept 15:40 - Sophie : Re-test planifié. Statut maintenu EN VALIDATION."), s(M06, "Nous n'avons pas encore donné l'acceptation sécurité de SEC-210.")]},
    {"id": "A2", "court": "Correctif dans la prochaine build : Boréal (Julien Moreau)", "echeance_court": "à confirmer (« prochaine build »)", "condition": "C2", "action": "Livrer le correctif ACC-303 (liste des éléments focusables de la modale) dans la prochaine build",
     "executant": "Boréal (Julien Moreau)", "validateur": "Mélissa Gagnon", "statut_resp": "confirmé",
     "echeance": "à confirmer : « prochaine build », sans date", "nature": "engagement documenté", "statut": "OUVERT",
     "preuves": [s(M06, "On vise le correctif ACC-303 dans la prochaine build."), s(T + "ACC-303.txt", "Le composant modal intercepte le focus avec une liste d'éléments focusables incomplète.")]},
    {"id": "A3", "court": "Re-test clavier et fermeture : Mélissa Gagnon", "echeance_court": "à confirmer (après A2)", "condition": "C2", "action": "Re-tester ACC-303 au clavier (Chrome et Edge), puis fermer le ticket",
     "executant": "Mélissa Gagnon (accessibilité)", "validateur": "Mélissa Gagnon", "statut_resp": "proposé",
     "echeance": "à confirmer : après la livraison de A2", "nature": "recommandation équipe",
     "statut": "OUVERT", "note": "Mélissa a ouvert le ticket et validé ACC-301 et ACC-302. Son rôle de validatrice d'ACC-303 est déduit, il n'est pas écrit.",
     "preuves": [s(T + "ACC-303.txt", "26 sept 11:03 - Mélissa : Toujours ouvert. Correctif annoncé pour la prochaine build.")]},
    {"id": "A4", "court": "Étapes 4 (retour arrière) et 5 (validation post-déploiement) : ops Boréal", "echeance_court": "à confirmer (« quelques jours avant »)", "condition": "C3", "action": "Compléter le runbook : étape 4 (procédure de retour arrière) et étape 5 (validation fonctionnelle post-déploiement), exécutables par une autre personne",
     "executant": "Boréal, équipe ops (relancée par Julien Moreau)", "validateur": "Olivier Côté", "statut_resp": "confirmé",
     "echeance": "à confirmer : Olivier veut le runbook final « au moins quelques jours avant » le go-live", "nature": "engagement documenté", "statut": "OUVERT",
     "preuves": [s(M06, "Pour le runbook je relance notre équipe ops."), s(T + "OPS-601_runbook.png", "Étape 5. Validation fonctionnelle post-déploiement — À compléter"), s(M04, "je veux un runbook final au moins quelques jours avant")]},
    {"id": "A5", "court": "Approbation du runbook (go exploitation) : Olivier Côté", "echeance_court": "à confirmer", "condition": "C3", "action": "Approuver le runbook incluant le rollback (« go exploitation »)",
     "executant": "Olivier Côté (exploitation)", "validateur": "Olivier Côté", "statut_resp": "confirmé",
     "echeance": "à confirmer", "nature": "engagement documenté", "statut": "OUVERT (version finale non reçue au 29 sept)",
     "preuves": [s(M06, "Je ne donnerai pas mon go exploitation tant que je n'ai pas une procédure exécutable."), s(T + "OPS-601.txt", "29 sept - Olivier : Toujours pas reçu la version finale.")]},
    {"id": "A6", "court": "INV-003 : ne pas payer les 18 000 $ de CR-04, réponse à Amélie : Nicolas Perron", "echeance_court": "à confirmer (facture bloquée depuis le 23 sept)", "condition": "", "action": "Répondre à Amélie Fortin : CR-04 n'est pas approuvé. Ne pas payer la ligne de 18 000 $ d'INV-003, demander une facture corrigée ou une note de crédit, et valider le jalon 3 (36 000 $) selon le processus normal",
     "executant": "Nicolas Perron", "validateur": "Amélie Fortin (Finances)", "statut_resp": "proposé",
     "echeance": "à confirmer : INV-003 est bloquée « En validation » depuis le 23 sept", "nature": "recommandation équipe",
     "statut": "OUVERT", "note": "Que CR-04 ne doive pas être facturé est documenté (E10, M06). Le traitement, lui (facture corrigée ou note de crédit), est notre recommandation.",
     "preuves": [s(E + "E07_Facture_003_question.eml", "Peux-tu me transmettre l'approbation correspondante?"), s(E + "E10_Fonction_mobile.eml", "Aucune dépense liée à CR-04 ne doit être engagée ou facturée sans nouvelle approbation.")]},
    {"id": "A7", "court": "Mettre les plans au 22 octobre (v3 : 15 oct) : Nicolas Perron", "echeance_court": "à confirmer (demandé le 10 sept)", "condition": "", "action": "Mettre la date du 22 octobre dans tous les plans (le plan v3 indique encore le 15 octobre)",
     "executant": "Nicolas Perron", "validateur": "", "statut_resp": "confirmé",
     "echeance": "à confirmer : demandé dès le 10 sept, toujours pas fait dans le plan v3", "nature": "engagement documenté", "statut": "OUVERT",
     "preuves": [s(NOTE, "faire mettre à jour la date dans tous les plans (le comité a approuvé le 22 octobre);"), s(M04, "On doit mettre les plans et communications à jour.")]},
    {"id": "A8", "condition": "", "action": "Fermer R-01 dans le registre des risques en citant la fermeture d'INT-101 (17 sept)",
     "executant": "Marc Gervais (propriétaire de R-01)", "validateur": "Nicolas Perron", "statut_resp": "proposé",
     "echeance": "à confirmer", "nature": "recommandation équipe", "statut": "OUVERT",
     "preuves": [s(REGISTRE, "Propriétaire: Marc Gervais | Statut: Ouvert")]},
    {"id": "A9", "condition": "", "action": "Corriger le rapport de statut et toute communication « au vert » : SEC-210 et ACC-303 ne sont pas validés, et le 22 octobre est conditionnel",
     "executant": "Nicolas Perron / Alex Deschamps", "validateur": "Nicolas Perron", "statut_resp": "proposé",
     "echeance": "à confirmer", "nature": "recommandation équipe",
     "statut": "À VÉRIFIER : le dossier ne dit pas si le message d'Alex a été envoyé",
     "preuves": [s(E + "E09_Rappel_mise_en_production.eml", "Merci de ne pas communiquer le 22 comme un go garanti"), s(RAPPORT, "Le rapport a été préparé avant la dernière vérification détaillée de certains tickets.")]},
    {"id": "A10", "condition": "", "action": "Vérifier avec Boréal que les « ajustements » mobiles commencés ne constituent pas des travaux CR-04 facturables",
     "executant": "Nicolas Perron", "validateur": "", "statut_resp": "proposé",
     "echeance": "à confirmer", "nature": "recommandation équipe", "statut": "OUVERT",
     "preuves": [s(M06, "on a déjà commencé à regarder quelques ajustements")]},
]

CONDITIONS = [
    {"id": "C1", "libelle": "Validation sécurité de SEC-210", "validateur": "Sophie Lambert", "ticket": "SEC-210", "actions": ["A1"]},
    {"id": "C2", "libelle": "Fermeture d'ACC-303", "validateur": "Mélissa Gagnon", "ticket": "ACC-303", "actions": ["A2", "A3"]},
    {"id": "C3", "libelle": "Approbation du runbook incluant le rollback", "validateur": "Olivier Côté", "ticket": "OPS-601", "actions": ["A4", "A5"]},
]


def _resolve(src: dict | None) -> dict | None:
    """Ajoute le repère et l'ancre retrouvés dans le dossier; signale un extrait introuvable."""
    if not src:
        return src
    if not src["extrait"]:  # renvoi au fichier entier (sources écartées)
        return {**src, "repere": "document", "anchor": "doc"}
    loc = evidence.locate(src["fichier"], src["extrait"])
    return {**src, "repere": loc["repere"] if loc else "INTROUVABLE", "anchor": loc["anchor"] if loc else ""}


def _walk(o):
    if isinstance(o, dict):
        if "fichier" in o and "extrait" in o:
            return _resolve(o)
        return {k: _walk(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_walk(v) for v in o]
    return o


def build_memory() -> dict:
    timeline = [{"date": d, "heure": h, "nature": n, "acteur": a, "evenement": ev, "preuves": p} for d, h, n, a, ev, p in TIMELINE]
    timeline.sort(key=lambda x: (x["date"], x["heure"] or "99:99"))
    tickets = kb.ticket_status()
    conditions = [{**c, "statut_ticket": tickets.get(c["ticket"], {}).get("statut", "inconnu")} for c in CONDITIONS]
    return _walk({
        "ref_date": kb.ref_date(),
        "baseline_au": kb.baseline()["baseline_au"],
        "timeline": timeline,
        "decisions": DECISIONS,
        "contradictions": CONTRADICTIONS,
        "conditions": conditions,
        "actions": ACTIONS,
        "sources_ecartees": [{**x, "extrait": ""} for x in SOURCES_ECARTEES],
    })


def save_memory():
    """Écrit la baseline (une seule fois). Les mises à jour vont dans data/updates/, jamais ici."""
    memory = build_memory()
    MEMORY_FILE.write_text(json.dumps(memory, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Memory saved to {MEMORY_FILE}")
    return memory


def load_memory() -> dict:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return build_memory()


if __name__ == "__main__":
    save_memory()
