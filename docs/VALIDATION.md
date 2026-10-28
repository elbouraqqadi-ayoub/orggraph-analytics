# Validation — 28 octobre 2026

## Vérifications locales effectuées

### Corrections de robustesse — version actuelle

- 36 tests locaux réussis sous Python 3.12 et Python Windows 3.14 : les 14 tests initiaux et 22
  régressions couvrant la préservation des exports, les échecs sur un passage tardif,
  le rollback de publication, les références invalides, les contrats partagés Spark,
  les snapshots v2, les écritures par lots, l'activation différée et le cache.
- API HTTP locale : les statuts 400, 500 et 503 sont testés séparément ; les détails
  internes des erreurs ne sont pas renvoyés au client.
- Le code des workers et la publication de dossiers sont testés hors Spark.
  L'exécution du job Spark complet et les requêtes du nouveau schéma Neo4j
  nécessitent encore des tests sur les services réels.
- Aucun test, téléchargement, démarrage ou arrêt Docker n'a été lancé pour ces
  corrections, conformément à la demande de réaliser ces essais plus tard.
- Le mode sans LLM est conservé.

### Historique de la première version

- Python Windows 3.14 et runtime Python 3.12 : tests exécutés avec succès.
- 14 tests automatisés : pipeline, résolution d'alias, réexécution, validation des
  preuves/types, découpage, recherche multi-sauts et ponctuation, API HTTP réelle
  locale avec authentification et requêtes invalides, appels LLM simulés,
  erreurs Neo4j simulées, activation/idempotence des snapshots, contrat de
  comparaison, collecte HTTP locale et redirection WebHDFS simulée.
- Corpus de démonstration : 4 documents, 10 entités, 9 relations.
- Benchmark synthétique : F1 moyen des faits récupérés = 1,0 sur trois cas.
- Compilation des modules Python et du traitement Spark : réussie.
- Tkinter : import disponible ; inspection visuelle de la fenêtre non effectuée.
- Docker Compose : configuration complète, profil bigdata compris, validée.
- Docker Desktop : démarré ; version du moteur vérifiée : 29.1.3.

Les tests simulés valident les contrats et la gestion des erreurs. Ils ne démontrent
pas le fonctionnement d'un fournisseur LLM ni la compatibilité d'un serveur Neo4j réel.

## Intégration externe

Les images Neo4j, Hadoop et Spark ont été téléchargées et le conteneur de l'API a
été construit. Les journaux confirment le démarrage de Neo4j ; les conteneurs
NameNode et DataNode ont été démarrés. Leur validation fonctionnelle complète
reste à faire. Docker a renvoyé des erreurs internes HTTP 500 lors de l'attente
de disponibilité des conteneurs. Le démarrage supplémentaire de l'API Docker
n'a pas été autorisé ; aucun test de bout en bout Docker n'est déclaré réussi.

Les anciens rapports ne valident pas les corrections du schéma v2.
Les fichiers `output/services_validation.json` et `output/comparison.json` sont
produits par le script ci-dessous. Seul `services_validation.json` confirme la
réussite complète des vérifications Neo4j, comparaison et API :

```powershell
python -X utf8 scripts/verify_services.py
```

Ne pas interpréter l'absence de rapport comme une réussite.

Le choix utilisateur est de **conserver la démonstration sans LLM pour le moment**.
Aucun fournisseur externe ni modèle local n'a été activé.

## Évaluation à effectuer sur des données réelles

- Choisir et documenter les sources autorisées.
- Configurer un fournisseur LLM et tester ses capacités JSON et ses coûts.
- Annoter un échantillon indépendant pour l'extraction et la résolution.
- Définir des questions métier et des réponses de référence indépendantes.
- Mesurer séparément recherche, génération, qualité des réponses et coût.
- Vérifier humainement les preuves, les réponses et les contradictions.
- Tester la montée en charge sur une infrastructure adaptée.

Le jeu synthétique ne permet pas de conclure à une supériorité de GraphRAG.
