"""Deterministic data contracts, extraction validation and graph operations."""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections import Counter, deque
from pathlib import Path

RELATIONS = {"PARTNERS_WITH", "SUBSIDIARY_OF", "ACQUIRED", "LOCATED_IN", "OPERATES_IN"}
KINDS = {"Organization", "Location", "Sector"}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def normalize(value: str) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                            if not unicodedata.combining(c)).split())


def entity_id(name: str, kind: str) -> str:
    return digest(kind + ":" + normalize(name))


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("Lecture PDF : installer l'option pip install '.[pdf]'.") from exc
        return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    text = path.read_text(encoding="utf-8")
    if suffix in {".html", ".htm"}:
        text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    elif suffix == ".json":
        obj = json.loads(text)
        if not isinstance(obj, dict) or not isinstance(obj.get("text"), str):
            raise ValueError("Un document JSON doit contenir un champ text.")
        text = obj["text"]
    elif suffix != ".txt":
        raise ValueError(f"Format non pris en charge : {suffix}")
    return " ".join(text.split())


def chunks(text: str, size: int = 2400, overlap: int = 200):
    if not 0 <= overlap < size:
        raise ValueError("Le chevauchement doit être inférieur à la taille du passage.")
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        yield start, end, text[start:end]
        if end == len(text):
            break
        start = end - overlap


def fixture_extract(text: str) -> dict:
    """Controlled syntax for synthetic test documents; this is NOT an LLM."""
    entities, relations = {}, []
    for match in re.finditer(r"\[([^\[\]]+)\]\s+(PARTNERS_WITH|SUBSIDIARY_OF|ACQUIRED|LOCATED_IN|OPERATES_IN)\s+\[([^\[\]]+)\]", text):
        source, kind, target = match.groups()
        target_kind = {"LOCATED_IN": "Location", "OPERATES_IN": "Sector"}.get(kind, "Organization")
        entities[source] = {"name": source, "kind": "Organization"}
        entities[target] = {"name": target, "kind": target_kind}
        relations.append({"source": source, "target": target, "type": kind,
                          "evidence": match.group(), "confidence": 1.0})
    return {"entities": list(entities.values()), "relations": relations}


def validate_extraction(result: dict, text: str) -> dict:
    if not isinstance(result, dict) or not isinstance(result.get("entities"), list) or not isinstance(result.get("relations"), list):
        raise ValueError("Extraction : entities et relations doivent être des listes.")
    entities = {}
    for entity in result["entities"]:
        if not isinstance(entity, dict):
            raise ValueError("Entité invalide.")
        name, kind = entity.get("name"), entity.get("kind")
        if not isinstance(name, str) or not name.strip() or not isinstance(kind, str) or kind not in KINDS:
            raise ValueError("Nom ou type d'entité invalide.")
        if name not in text:
            raise ValueError(f"Entité absente du passage : {name}")
        if name in entities and entities[name]["kind"] != kind:
            raise ValueError("Une entité possède deux types contradictoires.")
        entities[name] = {"name": name, "kind": kind}
    relations = []
    for relation in result["relations"]:
        if not isinstance(relation, dict):
            raise ValueError("Relation invalide.")
        source, target, kind = (relation.get(k) for k in ("source", "target", "type"))
        evidence, confidence = relation.get("evidence"), relation.get("confidence")
        if (not isinstance(source, str) or source not in entities or not isinstance(target, str)
                or target not in entities or not isinstance(kind, str) or kind not in RELATIONS):
            raise ValueError("Relation : référence ou type invalide.")
        if not isinstance(evidence, str) or not evidence.strip() or evidence not in text:
            raise ValueError("Preuve absente du passage.")
        if source not in evidence or target not in evidence:
            raise ValueError("La preuve doit mentionner les deux entités.")
        if isinstance(confidence, bool) or not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1:
            raise ValueError("Confiance invalide.")
        expected = {"LOCATED_IN": "Location", "OPERATES_IN": "Sector"}.get(kind, "Organization")
        if entities[source]["kind"] != "Organization" or entities[target]["kind"] != expected:
            raise ValueError("Types d'entités incompatibles avec la relation.")
        relations.append({"source": source, "target": target, "type": kind,
                          "evidence": evidence, "confidence": confidence})
    return {"entities": list(entities.values()), "relations": relations}


def build_graph(extractions: list[dict], aliases: dict | None = None) -> dict:
    aliases = {normalize(k): v for k, v in (aliases or {}).items()}
    nodes, facts, documents = {}, {}, {}
    for record in extractions:
        doc = record["document"]
        documents[doc["id"]] = doc
        lookup = {}
        for entity in record["extraction"]["entities"]:
            name = aliases.get(normalize(entity["name"]), entity["name"])
            eid = entity_id(name, entity["kind"])
            node = nodes.setdefault(eid, {"id": eid, "name": name, "kind": entity["kind"], "aliases": []})
            if entity["name"] not in node["aliases"]:
                node["aliases"].append(entity["name"])
            lookup[entity["name"]] = eid
        for rel in record["extraction"]["relations"]:
            source, target = lookup[rel["source"]], lookup[rel["target"]]
            fid = digest(source + ":" + rel["type"] + ":" + target)
            fact = facts.setdefault(fid, {"id": fid, "source": source, "target": target,
                                         "type": rel["type"], "supports": []})
            support = {"document_id": doc["id"], "chunk_id": record["chunk_id"],
                       "evidence": rel["evidence"], "confidence": rel["confidence"]}
            if support not in fact["supports"]:
                fact["supports"].append(support)
    return {"nodes": sorted(nodes.values(), key=lambda n: n["id"]),
            "facts": sorted(facts.values(), key=lambda f: f["id"]),
            "documents": sorted(documents.values(), key=lambda d: d["id"])}


def analytics(graph: dict) -> dict:
    degree = Counter()
    adjacency = {n["id"]: set() for n in graph["nodes"]}
    for fact in graph["facts"]:
        a, b = fact["source"], fact["target"]
        degree.update([a, b])
        adjacency[a].add(b)
        adjacency[b].add(a)
    remaining, components = set(adjacency), []
    while remaining:
        queue, component = [min(remaining)], set()
        while queue:
            current = queue.pop()
            if current in component:
                continue
            component.add(current)
            queue.extend(adjacency[current] - component)
        remaining -= component
        components.append(sorted(component))
    ranking = sorted(({**n, "degree": degree[n["id"]]} for n in graph["nodes"]),
                     key=lambda n: (-n["degree"], n["name"]))
    return {"nodes": len(graph["nodes"]), "facts": len(graph["facts"]),
            "documents": len(graph["documents"]), "degree_ranking": ranking,
            "connected_components": components}


def retrieve(graph: dict, question: str, hops: int = 2, limit: int = 40) -> dict:
    if not 1 <= hops <= 3:
        raise ValueError("hops doit être compris entre 1 et 3.")
    query = normalize(question)
    seeds = {n["id"] for n in graph["nodes"]
             if any(re.search(r"(?<!\w)" + re.escape(normalize(name)) + r"(?!\w)", query)
                    for name in [n["name"], *n["aliases"]])}
    visited, frontier, selected = set(seeds), set(seeds), {}
    truncated = False
    for _ in range(hops):
        next_frontier = set()
        for fact in graph["facts"]:
            if fact["source"] in frontier or fact["target"] in frontier:
                if fact["id"] not in selected and len(selected) >= limit:
                    truncated = True
                    continue
                selected[fact["id"]] = fact
                next_frontier.update([fact["source"], fact["target"]])
        frontier = next_frontier - visited
        visited.update(next_frontier)
    return {"seed_ids": sorted(seeds), "facts": list(selected.values()), "truncated": truncated}


def context_rows(graph: dict, facts: list[dict]) -> list[dict]:
    nodes = {n["id"]: n for n in graph["nodes"]}
    docs = {d["id"]: d for d in graph["documents"]}
    return [{"fact_id": f["id"], "source": nodes[f["source"]]["name"],
             "relation": f["type"], "target": nodes[f["target"]]["name"],
             "sources": [{**s, "source_uri": docs[s["document_id"]]["source_uri"]} for s in f["supports"]]}
            for f in facts]
