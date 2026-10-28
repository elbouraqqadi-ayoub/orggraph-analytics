"""Run after Docker services start; failures are explicit and never marked passed."""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orgkg.comparison import compare
from orgkg.core import analytics
from orgkg.pipeline import write_json
from orgkg.services import load_env, load_neo4j, read_neo4j


def main():
    import os
    load_env(str(ROOT / ".env"))
    graph = json.loads((ROOT / "data/graph.json").read_text(encoding="utf-8"))
    snapshot = load_neo4j(graph)
    assert load_neo4j(graph) == snapshot, "Snapshot non stable"
    restored = read_neo4j()
    assert {f["id"] for f in restored["facts"]} == {f["id"] for f in graph["facts"]}
    result = compare(ROOT / "evaluation/questions.json", ROOT / "output/comparison.json")
    assert all(c["cypher"]["f1"] == c["graphrag"]["f1"] == 1 for c in result["cases"])
    token = os.environ.get("API_TOKEN")
    headers = {"Authorization": "Bearer " + token} if token else {}
    request = urllib.request.Request("http://localhost:8080/ask", data=json.dumps({"question": "Atlas Industries"}).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=30) as response:
        answer = json.load(response)
    assert len(answer["context"]) == 6
    validation = {"neo4j": "passed", "api_neo4j": "passed", "comparison": "passed", "snapshot": snapshot,
                  "nodes": len(restored["nodes"]), "facts": len(restored["facts"])}
    write_json(ROOT / "output/services_validation.json", validation)
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
