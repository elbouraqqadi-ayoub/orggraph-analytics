# Plan de réalisation — Entreprises et organisations

Objectif : comparer Graph Analytics et GraphRAG sur un même graphe construit depuis
des documents hétérogènes. Le plan reprend le cahier des charges du dossier.

| Phase | Travail | Livrable | Critère d'acceptation |
|---|---|---|---|
| 1. Cadrage | Choisir les sources et questions métier, budget et volumes | Cas d'usage et périmètre | Sources accessibles, questions vérifiables |
| 2. Conception | Définir entités, relations, provenance et identifiants | Architecture et schéma | Chaque fait peut être justifié |
| 3. Environnement | Configurer Python, Docker, HDFS, Spark, Neo4j | Environnement reproductible | Services disponibles et volumes persistants |
| 4. Collecte | Importer documents et URLs explicitement choisies | Corpus brut et métadonnées | Empreintes et provenance conservées |
| 5. Préparation | Extraire texte, nettoyer, découper | Passages identifiés | Lien document/passage stable |
| 6. Extraction | LLM, JSON, validation des types et preuves | Entités et relations | Comparaison avec annotations indépendantes |
| 7. Résolution | Normaliser et fusionner les alias validés | Entités canoniques | Pas de fusion erronée sur le jeu annoté |
| 8. ETL | Nettoyage et déduplication Spark | Tables et exports normalisés | Intégrité des références et rejets tracés |
| 9. Graphe | Charger Neo4j et activer le snapshot | Graphe commun | Réexécution sans doublons |
| 10. Analytics | Cypher, degré, composantes, puis GDS si utile | Résultats structurés | Réponses contrôlées sur petit graphe |
| 11. GraphRAG | Recherche d'entités, voisinage, contexte, génération | Réponses sourcées | Absence d'invention vérifiée humainement |
| 12. Benchmark | Référence indépendante, questions multi-sauts et sans réponse | Rapport comparatif | Même graphe et protocole documenté |
| 13. Intégration | API, interface, contrôles d'accès et journaux | Démonstrateur | Parcours complet et reprise testés |
| 14. Livraison | Rapport, installation et soutenance | Dossier final | Expériences reproductibles |

## Modèle initial

- Organization : entreprise ou organisation, nom et alias.
- Location : lieu explicitement cité.
- Sector : secteur d'activité explicitement cité.
- PARTNERS_WITH : partenariat explicite.
- SUBSIDIARY_OF : filiale vers maison mère.
- ACQUIRED : acquéreur vers cible ; un fait historique n'implique pas une détention actuelle.
- LOCATED_IN : organisation vers lieu.
- OPERATES_IN : organisation vers secteur.
- Fact : assertion identifiée, reliée au sujet, à l'objet et aux preuves.
- Document : identifiant de contenu, source et titre.

Ne pas déduire automatiquement une filiale depuis une acquisition. Le modèle initial
ne gère pas les périodes de validité, les pourcentages de détention ou les contradictions :
ajouter ces champs avant une étude temporelle ou une analyse financière réelle.

## Calendrier indicatif

Semaines 1–2 : cadrage, architecture et environnement. Semaines 3–4 : collecte,
préparation, extraction et annotation. Semaines 5–6 : résolution, Spark et Neo4j.
Semaines 7–8 : analyses et GraphRAG. Semaine 9 : intégration. Semaines 10–11 :
évaluation, corrections et performance. Semaine 12 : rapport et soutenance.

## Protocole d'évaluation final

1. Choisir un corpus réel autorisé et conserver un instantané des documents.
2. Annoter indépendamment un échantillon d'entités et de relations, y compris les alias.
3. Séparer développement et évaluation finale ; ne pas ajuster les instructions sur le jeu final.
4. Mesurer précision, rappel et F1 de l'extraction, puis les erreurs de fusion.
5. Préparer les mêmes intentions de questions pour Cypher et GraphRAG ; indiquer la
   préparation manuelle de Cypher et toute traduction automatique de la question.
6. Geler le graphe, les paramètres, le modèle, les instructions et le nombre de sauts.
7. Mesurer la requête Cypher, la récupération GraphRAG, la génération et le total
   séparément ; répéter les mesures pour estimer leur variabilité.
8. Noter exactitude, complétude et justification des réponses dans human_scoring.csv.
9. Comparer avant/après résolution d'entités et avec/sans provenance.
10. Rapporter les limites : petit corpus, questions sélectionnées, absence de preuves,
    coût, résultats contradictoires et réponses non vérifiables.

Le jeu synthétique fourni sert uniquement au contrôle du pipeline et de la recherche.
