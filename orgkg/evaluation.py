"""Extraction scoring against manually specified, separate gold annotations."""
import json
import time
from pathlib import Path

from .core import chunks, normalize, read_document, rules_extract, validate_extraction
from .services import extract_llm


def prf(predicted, expected):
    true_positives = len(predicted & expected)
    precision = true_positives / len(predicted) if predicted else float(not expected)
    recall = true_positives / len(expected) if expected else float(not predicted)
    return {"precision": precision, "recall": recall,
            "f1": 2*precision*recall/(precision+recall) if precision+recall else 0,
            "expected": len(expected), "predicted": len(predicted), "true_positives": true_positives}


def evaluate_extraction(corpus: Path, gold_path: Path, mode="rules"):
    if mode not in {"rules", "llm"}:
        raise ValueError("Choose rules or llm extraction.")
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    predicted_entities, expected_entities, predicted_relations, expected_relations = set(),set(),set(),set()
    cases = []
    for case in gold:
        filename = case["file"]
        if Path(filename).name != filename or "/" in filename or "\\" in filename:
            raise ValueError("Gold filenames must stay inside the corpus directory.")
        expected_entities.update((filename,normalize(name),kind) for name,kind in case["entities"])
        expected_relations.update((filename,normalize(a),kind,normalize(b)) for a,kind,b in case["relations"])
        started = time.perf_counter()
        errors, metadata, entities, relations = [], [], set(), set()
        try:
            text = read_document(corpus / filename)
            for _,_,passage in chunks(text):
                result, meta = extract_llm(passage) if mode == "llm" else (rules_extract(passage), {"model":"bilingual-rules-v1"})
                metadata.append(meta)
                result = validate_extraction(result, passage)
                entities.update((filename,normalize(e["name"]),e["kind"]) for e in result["entities"])
                relations.update((filename,normalize(r["source"]),r["type"],normalize(r["target"])) for r in result["relations"])
        except Exception as error:
            errors.append(type(error).__name__ + ": " + str(error))
            entities, relations = set(), set()
        predicted_entities.update(entities)
        predicted_relations.update(relations)
        cases.append({"file":filename,"seconds":time.perf_counter()-started,"errors":errors,"metadata":metadata,
                      "entities":sorted(entities),"relations":sorted(relations)})
    return {"mode":mode,"scope":"Two short historical corporate excerpts; not a representative general extraction benchmark.",
            "entity_metrics":prf(predicted_entities,expected_entities),"relation_metrics":prf(predicted_relations,expected_relations),"cases":cases}
