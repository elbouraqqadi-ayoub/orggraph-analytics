"""Contracts shared by local ingestion, Spark and graph publication."""
import json
import re

from .core import KINDS, RELATIONS, digest, entity_id, normalize, validate_extraction


def validate_aliases(mapping):
    if not isinstance(mapping, dict):
        raise ValueError("Les alias doivent être un objet JSON nom:nom canonique.")
    result = {}
    for name, canonical in mapping.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(canonical, str) or not canonical.strip():
            raise ValueError("Chaque alias et nom canonique doit être une chaîne non vide.")
        key = normalize(name)
        if key in result and result[key] != canonical:
            raise ValueError("Deux alias normalisés définissent des noms canoniques contradictoires.")
        result[key] = canonical
    return result


def validate_document(doc):
    if not isinstance(doc, dict):
        raise ValueError("Document invalide.")
    sha = doc.get("sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha) or doc.get("id") != sha[:24]:
        raise ValueError("Identifiant ou empreinte de document invalide.")
    if not isinstance(doc.get("title"), str) or not isinstance(doc.get("source_uri"), str) or not doc["source_uri"].strip():
        raise ValueError("Titre ou provenance de document invalide.")
    return doc


def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("Un enregistrement doit être un objet JSON.")
    document = validate_document(record.get("document"))
    text, start, end = (record.get(k) for k in ("text", "start", "end"))
    if (not isinstance(text, str) or not text.strip()
            or type(start) is not int or type(end) is not int
            or start < 0 or end <= start or end - start != len(text)):
        raise ValueError("Texte ou offsets de passage invalides.")
    if record.get("chunk_id") != digest(document["id"] + ":" + str(start)):
        raise ValueError("Identifiant de passage invalide.")
    return {**record, "extraction": validate_extraction(record.get("extraction"), text)}


def validate_json_line(line):
    """Pure worker function: no Spark dependency, independently testable locally."""
    try:
        record = validate_record(json.loads(line))
        return json.dumps(record, ensure_ascii=False), None, None
    except (ValueError, TypeError, KeyError) as error:
        return None, str(error), line


def validate_graph(graph):
    if not isinstance(graph, dict) or any(not isinstance(graph.get(k), list) for k in ("nodes", "facts", "documents")):
        raise ValueError("Le graphe doit contenir les listes nodes, facts et documents.")

    def unique(rows, label):
        indexed = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
                raise ValueError(f"Identifiant invalide : {label}.")
            if row["id"] in indexed:
                raise ValueError(f"Identifiant dupliqué : {label}.")
            indexed[row["id"]] = row
        return indexed

    nodes = unique(graph["nodes"], "entité")
    documents = unique(graph["documents"], "document")
    facts = unique(graph["facts"], "fait")
    for node in nodes.values():
        name, kind = node.get("name"), node.get("kind")
        if not isinstance(name, str) or not name.strip() or not isinstance(kind, str) or kind not in KINDS:
            raise ValueError("Nom ou type d'entité invalide dans le graphe.")
        if node["id"] != entity_id(name, kind):
            raise ValueError("L'identifiant d'entité ne correspond pas au nom et au type.")
        aliases = node.get("aliases")
        if not isinstance(aliases, list) or any(not isinstance(a, str) or not a.strip() for a in aliases):
            raise ValueError("Alias d'entité invalides.")
    for doc in documents.values():
        validate_document(doc)
    for fact in facts.values():
        source, target, kind = (fact.get(k) for k in ("source", "target", "type"))
        if (not isinstance(source, str) or source not in nodes or not isinstance(target, str)
                or target not in nodes or not isinstance(kind, str) or kind not in RELATIONS):
            raise ValueError("Un fait référence une entité absente ou un type invalide.")
        expected_kind = {"LOCATED_IN": "Location", "OPERATES_IN": "Sector"}.get(kind, "Organization")
        if nodes[source]["kind"] != "Organization" or nodes[target]["kind"] != expected_kind:
            raise ValueError("Les types des extrémités du fait sont incompatibles.")
        if fact["id"] != digest(source + ":" + kind + ":" + target):
            raise ValueError("Identifiant de fait incohérent.")
        supports = fact.get("supports")
        if not isinstance(supports, list) or not supports:
            raise ValueError("Chaque fait doit posséder au moins une preuve.")
        provenances = set()
        for support in supports:
            if not isinstance(support, dict) or not isinstance(support.get("document_id"), str) or support["document_id"] not in documents:
                raise ValueError("La preuve référence un document absent.")
            if (not isinstance(support.get("chunk_id"), str) or not re.fullmatch(r"[0-9a-f]{24}", support["chunk_id"])
                    or not isinstance(support.get("evidence"), str) or not support["evidence"].strip()):
                raise ValueError("Passage ou preuve invalide.")
            confidence = support.get("confidence")
            if type(confidence) not in (float, int) or not 0 <= confidence <= 1:
                raise ValueError("Confiance de preuve invalide.")
            provenance = (support["document_id"], support["chunk_id"], support["evidence"])
            if provenance in provenances:
                raise ValueError("Preuve dupliquée ou scores contradictoires pour une même provenance.")
            provenances.add(provenance)
    return graph
