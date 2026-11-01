# Validation — 1 novembre 2026

## Résultats vérifiés

- 46 tests de régression réussis sous Python 3.12 et 3.14 ; syntaxe JavaScript vérifiée avec Node. Les tests couvrent notamment validation, rollback, snapshots, API, contrôle du jeton, origine des requêtes, import de documents, confinement des originaux, alias, PageRank et repli des réponses sans citations.
- La chaîne réelle Docker HDFS → Spark → export validé → Neo4j → API fonctionne. Le script d'acceptation compare le graphe local et le graphe Spark, vérifie le snapshot servi et l'empreinte du code de l'image. Une entrée invalide est rejetée et le précédent export HDFS reste intact.
- Neo4j 5.26.32 avec Graph Data Science 2.13.14 : PageRank et composantes faibles exécutés. Le plugin est intégré à une image personnalisée avec version et SHA-256 verrouillés.
- Sur les trois questions synthétiques, Cypher et recherche de voisinage retrouvent tous les faits attendus (F1 = 1). Les temps ne prouvent pas la supériorité d'une approche : Cypher implique des appels HTTP alors que la récupération utilise un snapshot déjà en mémoire.
- Extraction par règles : F1 entités et relations = 1 sur les deux courts extraits historiques, quatre entités et deux acquisitions. Les motifs des textes sont explicitement pris en charge. Ce résultat ne se généralise pas à un corpus inconnu.
- Inférence locale réellement exécutée avec Qwen2.5:1.5b : échec de l'acceptation d'extraction. Le modèle a produit une preuve non conforme et une relation incorrecte. Les rapports conservent ces échecs. Le mode LLM est expérimental ; le mode par règles demeure le défaut. Le téléchargement d'un modèle 3b a été interrompu après des erreurs réseau.
- Docker Desktop 29.1.3 redémarré après sauvegarde et recréation de deux répertoires transitoires de sockets. Aucun reset usine, effacement de volumes ou suppression d'images n'a été effectué.

## Reproduire et examiner les preuves

```powershell
python scripts/check_local.py
python scripts/verify_pipeline.py --api-port 8081
python scripts/verify_services.py
python -m orgkg gds
python -m orgkg evaluate-extraction --mode rules
python scripts/verify_llm.py
```

Les rapports JSON détaillés sont générés dans `output/` et exclus de Git : `local_validation.json`, `pipeline_validation.json`, `services_validation.json`, `comparison.json`, `gds.json`, `extraction_rules.json`, `extraction_llm.json` et `llm_validation.json`. Le dernier script retourne un échec si l'extraction du modèle ne satisfait pas la référence ; cela ne doit pas être masqué. `pipeline_validation.json` contient l'empreinte de la version du code effectivement testée.

## Portée

Le graphe principal contient 14 entités, 11 faits et 6 documents. L'acceptation isolée utilise les quatre documents synthétiques, soit 10 entités et 9 faits. Les sources réelles sont des citations historiques courtes, pas une étude de détention actuelle. Il n'y a pas encore d'évaluation humaine indépendante des réponses générées, de corpus représentatif ni de mesure à grande échelle. Le livrable est un démonstrateur fonctionnel et reproductible.
