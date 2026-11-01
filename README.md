# OrgGraph Analytics

Explore organizations and their relationships through an interactive knowledge graph, inspect the original evidence, compare Cypher with graph retrieval, and process the same extraction records with HDFS and Spark.

The browser interface includes a graph explorer, entity directory, source document library and uploads, analytics, evaluation reports, questions and JSON export. It works without a model or paid API.

## Start locally

Requires Python 3.11+. Run from the repository folder:

```powershell
python -m pip install ".[pdf]"
python scripts/init_workspace.py
python -m orgkg serve --open-browser
```

Open http://localhost:8080. On Windows, `DEMARRER_INTERFACE.cmd` also initializes missing sample data and opens the web interface. The older Tkinter interface remains available through `python -m orgkg gui`.

Initialization preserves an existing graph and credentials. A new workspace contains **14 entities, 11 facts and 6 documents**: four synthetic documents and two short, attributed historical corporate excerpts. Atlas Industries and its relationships are fictional. See [sources and scope](docs/DATA_SOURCES.md).

## Docker and the complete data pipeline

Requires Docker Desktop with Linux containers and internet access for the initial image downloads. Initialize the workspace first. The generated `.env` contains a random local Neo4j password; preserve it when reusing a Neo4j data volume.

```powershell
python scripts/prepare_gds.py
 docker compose --profile bigdata up -d --build neo4j api namenode datanode
 docker compose run --rm api load-neo4j
```

The Docker dashboard is at http://localhost:8081 (`API_PORT` in `.env`), Neo4j Browser at http://localhost:7474 and HDFS at http://localhost:9870. All published ports bind to this computer only. The Neo4j image includes the SHA-256 checked, version-pinned GDS plugin; it does not download plugins during startup. Spark runs on demand.

Run the actual end-to-end acceptance:

```powershell
python scripts/verify_pipeline.py --api-port 8081
```

This builds the images, ingests samples into an isolated run directory, uploads raw data and extraction records to HDFS, runs Spark, downloads and validates its exports, checks equality with the local graph, loads Neo4j, verifies the API snapshot and code fingerprint, compares retrieval with Cypher, runs GDS, and proves that invalid input cannot replace a valid curated export. The report is `output/pipeline_validation.json`. It activates its sample snapshot; restore your main workspace afterward:

```powershell
python scripts/verify_services.py
python -m orgkg gds
```

These commands use `.env`. `verify_services.py` restores `data/graph.json` into Neo4j and checks the dashboard API at `API_PORT`.

For the Docker Desktop socket startup error, see [the reversible recovery procedure](docs/DOCKER_TROUBLESHOOTING.md). A factory reset is unnecessary for the error encountered on this workstation.

## Local AI

The default question mode displays retrieved facts and their evidence. Optional generation and extraction use an OpenAI-compatible endpoint; no API key is required for local Ollama.

On Windows:

```powershell
python scripts/start_local_ai.py
```

The helper downloads the official CPU runtime (about 28 MB compressed), starts it on localhost, downloads Qwen2.5:1.5b (about 986 MB), and configures `.env`. Restart the API afterward (`docker compose up -d --build api` for Docker). The first CPU response may be slow. The optional Compose `ai` profile provides an alternative Ollama server; set `DOCKER_LLM_BASE_URL=http://ollama:11434/v1` when using it, and pull the model into that server.

LLM output is validated against the entity/relation contract and verbatim evidence. Invalid extraction does not publish a partial graph. Answers without valid fact citations fall back explicitly to retrieved facts. Valid citation identifiers alone do not prove semantic accuracy: review the evidence. The installed 1.5b model failed our extraction acceptance on the two real excerpts; keep rule extraction as the default. Local AI is experimental, and a stronger model can be selected with LOCAL_AI_MODEL. A larger model download was stopped after network failures. No extraction-quality claim is made for this model.

## Documents and commands

Upload TXT, HTML, JSON with a `text` field, DOCX or text-based PDF through the Source documents view. PDF reading requires the optional dependency above; scanned pages require an external OCR step. The default rule extractor supports a limited set of explicit French/English patterns. Fixture mode handles only the controlled bracket syntax in the synthetic samples. Select LLM mode explicitly for broader text extraction.

```powershell
python -m orgkg ingest --source data/reference --mode rules --append
python -m orgkg analytics
python -m orgkg ask "Which organizations partner with Atlas Industries?"
python -m orgkg ask "What did Microsoft acquire?" --mode llm
python -m orgkg evaluate-extraction --mode rules
python -m orgkg evaluate-extraction --mode llm
python -m orgkg benchmark
python -m orgkg --backend neo4j compare
```

Without `--append`, ingestion replaces the local corpus after all records validate. Alias mappings are explicit in `config/aliases.json`. Sources, content hashes, passage offsets and verbatim evidence are retained. Failed attempts preserve the last valid graph/export.

## Validation and limits

```powershell
python scripts/check_local.py
python scripts/verify_llm.py
```

The first command runs the local regression suite without Docker. The second runs actual local inference and requires valid extraction plus exact expected relations on the tiny reference corpus. It records failures honestly. Reports are in `output/`; see [validation](docs/VALIDATION.md), [architecture](docs/ARCHITECTURE.md) and [realization plan](docs/PLAN_REALISATION.md).

HDFS/Spark processing is implemented and exercised, but the supplied corpus is small. The API materializes a graph snapshot in memory, retrieval matches entity names/aliases and traverses up to three hops, and the current benchmark measures retrieved facts rather than generated-answer correctness. This is a reproducible project demonstrator, not evidence of production-scale performance or financial-grade company intelligence.

Set `API_TOKEN` if access protection is needed. The dashboard Connection button accepts it in memory; it is not saved in browser storage. This single-user service has no multi-user roles or production deployment configuration. `.env`, local runtime/model weights, generated data and reports are excluded from Git.
