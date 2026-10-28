# Plateforme Knowledge Graph — Entreprises et organisations

Première version exécutable du projet : collecte explicite, extraction structurée,
résolution d'alias, graphe commun, analyse et recherche avec génération LLM optionnelle.
Le corpus fourni est **entièrement synthétique** ; ses entreprises et relations ne
constituent pas des informations réelles.

Configuration retenue : **démonstration sans LLM**. Les options LLM ci-dessous
restent disponibles pour une activation ultérieure.

## Démarrage local, sans Docker ni clé LLM

Prérequis : Python 3.11 ou supérieur. Exécuter depuis ce dossier :

```powershell
python -X utf8 -m orgkg ingest
python -X utf8 -m orgkg analytics
python -X utf8 -m orgkg ask "Quels liens autour de Atlas Industries ?"
python -X utf8 -m orgkg gui
```

L'interface native présente les entités, les relations, les preuves documentaires et
un champ de question. Elle nécessite Tkinter (généralement inclus dans Python Windows).
Le premier traitement doit produire **4 documents, 10 entités et 9 relations**.
Vous pouvez aussi double-cliquer sur `DEMARRER_INTERFACE.cmd` ; il prépare le
corpus de démonstration seulement si aucun graphe local n'existe déjà.
`Atlas Ind.` est fusionné avec `Atlas Industries` ; la relation commune conserve ses
deux preuves. Le graphe local est dans `data/graph.json`.

Le mode `fixture` analyse uniquement la syntaxe contrôlée `[A] PARTNERS_WITH [B]`
du corpus de démonstration. Il ne remplace pas l'extraction LLM sur des textes libres.
Le mode de réponse `extractive` affiche les faits retrouvés ; il n'effectue pas de
raisonnement en langage naturel.

L'ingestion publie le nouveau graphe uniquement si **tous les documents réussissent**.
En cas d'échec, `data/graph.json` et l'export d'extractions précédents sont conservés ;
le détail est écrit dans `data/processed/last_attempt.json` (`published: false`) et
la commande retourne le code 2. Les passages d'un document partiellement traité
ne sont pas conservés dans les résultats à publier. Les copies brutes restent
disponibles pour diagnostiquer les erreurs. La publication locale prévoit un seul
processus d'ingestion à la fois.

## Tests et évaluation locale

```powershell
python -X utf8 -m unittest discover -s tests -v
python -X utf8 -m orgkg benchmark
# Ou : powershell -ExecutionPolicy Bypass -File scripts/demo.ps1 -Gui
```

Résultats dans `output/benchmark.json`. Les trois questions fournies vérifient la
recherche à un saut, à deux sauts et l'absence d'information. Ce petit jeu est un
test de fonctionnement, pas une preuve scientifique de performance GraphRAG.
Le F1 affiché mesure **les faits récupérés**, pas la qualité d'une réponse générée.

## Documents réels et extraction LLM

1. Copier `.env.example` vers `.env` et configurer `LLM_BASE_URL`, `LLM_MODEL` et,
   si nécessaire, `LLM_API_KEY`. Le service doit accepter `/chat/completions`,
   `response_format: json_object` et renvoyer `choices[0].message.content`.
2. Déposer les documents TXT UTF-8, HTML, JSON (`{"text":"..."}`) ou PDF dans
   `data/incoming`. Pour PDF : `python -m pip install ".[pdf]"`. OCR et Word ne
   sont pas implémentés.
3. Exécuter :

```powershell
python -X utf8 -m orgkg ingest --source data/incoming --mode llm
python -X utf8 -m orgkg ask "Quels partenariats concernent NOM COMPLET ?" --mode llm
```

Collecte ponctuelle d'une URL explicitement choisie :

```powershell
python -X utf8 -m orgkg collect https://votre-source.example/rapport.html
```

Remplacer cette URL d'exemple par une source autorisée. Aucun parcours récursif,
email ou accès à une base externe n'est activé. La collecte conserve l'URL finale
dans un fichier `.meta`. La limite est de 10 Mo par document.

Le dictionnaire `config/aliases.json` contient les fusions explicites. Sur des
données réelles, le remplacer par un dictionnaire validé pour le domaine. Aucun
rapprochement flou automatique n'est effectué. Une preuve textuelle présente ne
garantit pas à elle seule la vérité d'un fait : une annotation humaine reste nécessaire.

**Le mode LLM envoie les passages et/ou le contexte au fournisseur configuré.**
Les coûts ne sont estimés que si les tarifs sont renseignés et le fournisseur renvoie
les compteurs de tokens. Les valeurs nulles signifient « non mesuré ».

## Neo4j et API avec Docker

Prérequis : Docker Desktop démarré en mode conteneurs Linux.

```powershell
# Un fichier .env local a déjà été préparé avec un mot de passe aléatoire.
# Pour une nouvelle installation uniquement : Copy-Item .env.example .env
# Modifier NEO4J_PASSWORD dans .env (au moins 8 caractères).
docker compose config --quiet
docker compose up -d --build neo4j api
docker compose run --rm api ingest
docker compose run --rm api load-neo4j
docker compose run --rm api --backend neo4j analytics
docker compose run --rm api --backend neo4j ask "Quels liens autour de Atlas Industries ?"
docker compose run --rm api compare
# Avec un LLM configuré : docker compose run --rm api compare --mode llm
```

Neo4j Browser : http://localhost:7474. API : http://localhost:8080.
La comparaison écrit `output/comparison.json` : faits récupérés, précision/rappel,
latence Cypher (aller-retour HTTP compris), récupération et génération GraphRAG.
Les deux approches partagent l'identification lexicale des entités et le voisinage
attendu. La recherche GraphRAG charge le snapshot en mémoire : cette mesure ne
démontre pas une supériorité de performance sur une requête Neo4j distante.
L'API utilise **le snapshot actif de Neo4j** ; la même fonction de recherche et
d'analyse peut fonctionner sur l'export local avec `--backend local`.
Le chargement crée des nœuds Entity, Fact et Document, des relations typées et
leurs preuves. Dans le schéma v2, les labels réels sont `EntityVersion`,
`FactVersion` et `DocumentVersion` : chaque version possède une clé propre au
snapshot. Les propriétés et les preuves d'un ancien snapshot ne sont pas modifiées
par un nouvel import. Les écritures utilisent des lots de 500 lignes ; le snapshot
est activé uniquement après leur réussite. Il n'efface pas les snapshots précédents. Les requêtes doivent filtrer
le snapshot actif ; exemples dans `graph/queries.cypher`.

**Mise à jour depuis la première version, lors des prochains essais Docker :**

```powershell
docker compose build api
docker compose run --rm api load-neo4j
docker compose up -d api
python -X utf8 scripts/verify_services.py
```

Le graphe local existant reste utilisable. Les anciens snapshots Neo4j sont conservés,
mais leur schéma doit être réimporté avant d'utiliser le nouveau lecteur. Aucune
migration ni reconstruction d'image n'est exécutée automatiquement.

Si le LLM tourne sur Windows et l'API dans Docker, utiliser
`http://host.docker.internal:11434/v1` pour `LLM_BASE_URL`, au lieu de localhost.

API locale sans Docker :

```powershell
python -X utf8 -m orgkg serve
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod -Method Post -Uri http://localhost:8080/ask -ContentType application/json -Body '{"question":"Quels liens autour de Atlas Industries ?","mode":"extractive","hops":2}'
```

Routes : `GET /`, `GET /health`, `GET /graph`, `GET /analytics`, `POST /ask`.
L'API distingue les requêtes invalides (400), les problèmes de configuration (500)
et les indisponibilités du backend (503). Elle conserve le graphe en cache : le
fichier local est relu après remplacement et Neo4j est relu après changement de
snapshot actif. L'identifiant actif est vérifié à chaque requête Neo4j.
Si `API_TOKEN` est configuré, joindre `Authorization: Bearer VOTRE_TOKEN`.
Les ports Docker sont publiés uniquement sur localhost. Ce serveur de développement
n'est pas un déploiement multi-utilisateur de production. Les journaux HTTP sont
écrits sur stderr ; les durées sont incluses dans les réponses et rapports.

## HDFS et Spark

Le profil `bigdata` ajoute un NameNode, un DataNode et un traitement Spark en mode
`local[2]`. Il permet de valider les contrats de données ; il ne constitue pas un
cluster de calcul distribué multi-machines.

```powershell
docker compose --profile bigdata up -d namenode datanode
# Attendre qu'un DataNode soit enregistré sur http://localhost:9870.
docker compose run --rm api upload-hdfs
docker compose --profile bigdata run --rm spark
# Récupérer les sorties Spark dans le volume monté :
docker compose --profile bigdata run --rm --entrypoint /bin/bash spark -lc 'mkdir -p /app/data/curated && /opt/spark/bin/spark-class org.apache.hadoop.fs.FsShell -get -f hdfs://namenode:9000/orgkg/curated/nodes /app/data/curated/ && /opt/spark/bin/spark-class org.apache.hadoop.fs.FsShell -get -f hdfs://namenode:9000/orgkg/curated/facts /app/data/curated/ && /opt/spark/bin/spark-class org.apache.hadoop.fs.FsShell -get -f hdfs://namenode:9000/orgkg/curated/documents /app/data/curated/'
docker compose run --rm api import-spark
docker compose run --rm api load-neo4j
```

Le téléversement WebHDFS s'exécute **dans le conteneur API** pour résoudre le nom du
DataNode lors de la redirection. Spark écrit les tables Parquet, les relations
rejetées et les exports JSON réutilisés pour charger Neo4j. Le worker Spark utilise
les mêmes validations de documents, passages, entités, types et preuves que Python.
Un enregistrement invalide bloque la publication ; les erreurs sont écrites sous
`curated_validation/<identifiant>/rejected`. Les relations sont jointes aux entités
du même passage ; les références sont aussi vérifiées avant l'import du graphe.

Les sorties sont préparées dans un dossier temporaire, puis publiées par renommage.
Le dossier précédent reste conservé sous `curated_previous_<identifiant>` et est
restauré si la publication échoue. Importer les exports seulement après le succès
du job, sans import concurrent pendant les renommages. Les sauvegardes et les
répertoires de préparation abandonnés nécessitent un nettoyage manuel ultérieur.
Le code partagé `orgkg` est monté dans le conteneur Spark via `PYTHONPATH=/app` ;
un futur cluster multi-machines devra distribuer ce package à ses workers.
HDFS est configuré pour une démonstration locale,
sans authentification Hadoop.

## État et prochaines validations

Voir `docs/PLAN_REALISATION.md` pour les phases et `docs/VALIDATION.md` pour les
vérifications réellement effectuées. L'intégration Docker/HDFS/Spark/Neo4j et les
appels à un vrai LLM nécessitent une exécution dans l'environnement configuré.

La contribution scientifique à terminer sur un corpus réel : annotation indépendante,
mesures d'extraction/résolution, questions Cypher et GraphRAG comparables, évaluation
humaine des réponses, latences et coûts. Le degré et les composantes connexes sont
calculés localement ; le plugin Neo4j GDS n'est pas installé.

## Références techniques

- Neo4j : https://neo4j.com/docs/python-manual/current/query-simple/
- Images Apache Spark : https://hub.docker.com/r/apache/spark/tags
- Images Apache Hadoop : https://hub.docker.com/r/apache/hadoop/tags
