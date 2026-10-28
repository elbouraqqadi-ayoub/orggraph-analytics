"""Immutable, version-scoped payloads for Neo4j schema v2."""
import json

from .core import digest
from .validation import validate_graph

SCHEMA_VERSION = 2


def prepare_snapshot(graph: dict) -> dict:
    validate_graph(graph)
    nodes = [{"id": n["id"], "name": n["name"], "kind": n["kind"],
              "aliases": sorted(set(n["aliases"]))} for n in graph["nodes"]]
    documents = [{k: d[k] for k in ("id", "title", "source_uri", "sha256")} for d in graph["documents"]]
    facts = [{"id": f["id"], "source": f["source"], "target": f["target"], "type": f["type"],
              "supports": sorted([{**{k: s[k] for k in ("document_id", "chunk_id", "evidence")}, "confidence": float(s["confidence"])}
                                  for s in f["supports"]], key=lambda s: json.dumps(s, sort_keys=True))}
             for f in graph["facts"]]
    canonical = {"schema_version": SCHEMA_VERSION,
                 "nodes": sorted(nodes, key=lambda n: n["id"]),
                 "documents": sorted(documents, key=lambda d: d["id"]),
                 "facts": sorted(facts, key=lambda f: f["id"])}
    snapshot = digest(json.dumps(canonical, sort_keys=True, ensure_ascii=False))

    def key(identifier):
        return snapshot + ":" + identifier

    supports = []
    for fact in canonical["facts"]:
        fact.update(key=key(fact["id"]), source_key=key(fact["source"]), target_key=key(fact["target"]))
        for support in fact.pop("supports"):
            supports.append({**support, "fact_key": fact["key"], "document_key": key(support["document_id"])})
    for row in canonical["nodes"] + canonical["documents"]:
        row["key"] = key(row["id"])
    return {**canonical, "id": snapshot, "supports": supports}


def batches(rows, size):
    if type(size) is not int or size < 1:
        raise ValueError("La taille d'un lot doit être un entier positif.")
    for offset in range(0, len(rows), size):
        yield rows[offset:offset + size]
