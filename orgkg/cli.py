from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import analytics
from .pipeline import answer, benchmark, run_pipeline
from .services import load_env, load_neo4j, read_neo4j, upload_hdfs
from .errors import BackendError, ConfigurationError


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Plateforme de graphes : entreprises et organisations")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--backend", choices=["local", "neo4j"], default="local")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--source", type=Path, default=Path("data/samples"))
    ingest.add_argument("--mode", choices=["fixture", "llm"], default="fixture")
    ingest.add_argument("--aliases", type=Path, default=Path("config/aliases.json"))
    commands.add_parser("analytics")
    commands.add_parser("gui")
    collect = commands.add_parser("collect")
    collect.add_argument("urls", nargs="+")
    collect.add_argument("--destination", type=Path, default=Path("data/incoming"))
    curated = commands.add_parser("import-spark")
    curated.add_argument("--source", type=Path, default=Path("data/curated"))
    query = commands.add_parser("ask")
    query.add_argument("question")
    query.add_argument("--mode", choices=["extractive", "llm"], default="extractive")
    query.add_argument("--hops", type=int, default=2)
    commands.add_parser("load-neo4j")
    commands.add_parser("upload-hdfs")
    bench = commands.add_parser("benchmark")
    bench.add_argument("--cases", type=Path, default=Path("evaluation/questions.json"))
    bench.add_argument("--mode", choices=["extractive", "llm"], default="extractive")
    comparison = commands.add_parser("compare")
    comparison.add_argument("--cases", type=Path, default=Path("evaluation/questions.json"))
    comparison.add_argument("--mode", choices=["extractive", "llm"], default="extractive")
    server = commands.add_parser("serve")
    server.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    try:
        if args.command == "ingest":
            result = run_pipeline(args.source, args.data, args.mode, args.aliases)
        elif args.command == "collect":
            from .collect import collect
            result = collect(args.urls, args.destination)
        elif args.command == "import-spark":
            from .pipeline import import_spark
            result = analytics(import_spark(args.source, args.data))
        elif args.command == "gui":
            from .gui import launch
            launch(args.data, args.backend)
            return
        elif args.command == "compare":
            from .comparison import compare
            result = compare(args.cases, Path("output/comparison.json"), args.mode)
        elif args.command == "serve":
            from .server import serve
            serve(args.data, args.port, args.backend)
            return
        elif args.command == "upload-hdfs":
            files = sorted((args.data / "raw").glob("*")) + sorted((args.data / "processed").glob("*.jsonl"))
            if not files:
                raise ValueError("Exécuter ingest avant upload-hdfs.")
            for file in files:
                upload_hdfs(file, "/orgkg/" + file.parent.name + "/" + file.name)
            result = {"uploaded_files": len(files)}
        else:
            graph = read_neo4j() if args.backend == "neo4j" else json.loads((args.data / "graph.json").read_text(encoding="utf-8"))
            if args.command == "analytics":
                result = analytics(graph)
            elif args.command == "ask":
                result = answer(graph, args.question, args.mode, args.hops)
            elif args.command == "load-neo4j":
                result = {"snapshot": load_neo4j(graph)}
            else:
                result = benchmark(graph, args.cases, Path("output/benchmark.json"), args.mode)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "ingest" and result["errors"]:
            raise SystemExit(2)
    except (ValueError, OSError, KeyError, TypeError, BackendError, ConfigurationError) as error:
        parser.exit(1, "Erreur : " + str(error) + "\n")


if __name__ == "__main__":
    main()
