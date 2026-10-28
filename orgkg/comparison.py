"""Shared-snapshot Cypher versus GraphRAG retrieval/generation benchmark."""
import json
import time
from pathlib import Path

from .core import digest, entity_id, retrieve
from .pipeline import answer, write_json
from .services import cypher, read_neo4j


def compare(cases_path: Path, output: Path, mode="extractive"):
    graph = read_neo4j()
    snapshot = graph["snapshot_id"]
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    results = []
    allowed = "PARTNERS_WITH|SUBSIDIARY_OF|ACQUIRED|LOCATED_IN|OPERATES_IN"
    for case in cases:
        hops = case.get("hops", 2)
        if not isinstance(hops, int) or not 1 <= hops <= 3:
            raise ValueError("Nombre de sauts invalide.")
        seeds = retrieve(graph, case["question"], hops)["seed_ids"]
        # Both approaches use the same lexical entity linker and question scope.
        statement = f"""MATCH (s:Snapshot {{id:$snapshot}})-[:HAS_ENTITY]->(seed:EntityVersion)
        WHERE seed.id IN $seeds
        MATCH p=(seed)-[:{allowed}*0..{hops-1}]-(n:EntityVersion)
        WHERE all(rel IN relationships(p) WHERE EXISTS {{
          MATCH (s)-[:HAS_FACT]->(pf:FactVersion) WHERE pf.id=rel.fact_id AND rel.snapshot_id=$snapshot }})
        MATCH (n)-[r:{allowed}]-(other:EntityVersion)
        MATCH (s)-[:HAS_FACT]->(f:FactVersion) WHERE f.id=r.fact_id AND r.snapshot_id=$snapshot
        RETURN DISTINCT f.id AS fact_id ORDER BY fact_id"""
        start = time.perf_counter()
        result = cypher(statement, {"snapshot": snapshot, "seeds": seeds})
        cypher_seconds = time.perf_counter() - start
        direct_ids = {r["row"][0] for r in result[0]["data"]}
        response = answer(graph, case["question"], mode, hops)
        rag_ids = {r["fact_id"] for r in response["context"]}
        expected = {digest(entity_id(s, "Organization") + ":" + rel + ":" + entity_id(t, kind))
                    for s, rel, t, kind in case["expected_facts"]}

        def score(actual):
            tp = len(actual & expected)
            p = tp / len(actual) if actual else float(not expected)
            r = tp / len(expected) if expected else float(not actual)
            return {"precision": p, "recall": r, "f1": 2*p*r/(p+r) if p+r else 0}

        results.append({"id": case["id"], "question": case["question"],
                        "cypher": {"query": statement, "fact_ids": sorted(direct_ids),
                                   "roundtrip_seconds": cypher_seconds, **score(direct_ids)},
                        "graphrag": {"fact_ids": sorted(rag_ids), "total_seconds": response["total_seconds"],
                                     "retrieval_seconds": response["retrieval_seconds"], **score(rag_ids),
                                     "response": response}})
    report = {"snapshot": snapshot, "mode": mode,
              "protocol": "Shared graph, lexical entity linker and bounded undirected neighborhood. Cypher includes HTTP roundtrip; GraphRAG retrieval uses a materialized snapshot. Answer quality requires human scoring.",
              "cases": results}
    write_json(output, report)
    return report
