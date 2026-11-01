"""Actual local-model acceptance and extraction evaluation. Never fabricates success."""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from orgkg.dashboard import model_status
from orgkg.evaluation import evaluate_extraction
from orgkg.pipeline import answer,write_json
from orgkg.services import load_env


def main():
    os.chdir(ROOT)
    load_env()
    status=model_status()
    if not status["ready"]:
        raise RuntimeError("The configured local model is not ready. Start Ollama and pull the model first.")
    report={"model":status["model"],"started_at":time.time(),"status":"running","answers":[]}
    try:
        report["extraction"]=evaluate_extraction(Path("data/reference"),Path("evaluation/extraction_gold.json"),"llm")
        write_json(ROOT/"output/extraction_llm.json",report["extraction"])
        graph=json.loads((ROOT/"data/graph.json").read_text(encoding="utf-8"))
        for question in ["Which organizations partner with Atlas Industries?","Which group is Nova Logistics a subsidiary of?","What do you know about Unknown Example Corp?"]:
            response=answer(graph,question,"llm",2)
            allowed={row["fact_id"] for row in response["context"]}
            cited=set(re.findall(r"\[([0-9a-f]{24})\]",response["answer"]))
            report["answers"].append({**response,"citation_ids_valid":cited.issubset(allowed),"cited_facts":sorted(cited)})
            write_json(ROOT/"output/llm_validation.json",report)
        assert all(a["citation_ids_valid"] for a in report["answers"]),"Model cited facts outside the retrieved graph"
        assert all(not c["errors"] for c in report["extraction"]["cases"]),"Local model failed extraction validation"
        assert report["extraction"]["relation_metrics"]["f1"] == 1,"Local model missed reference facts"
        report["status"]="passed"
        report["scope"]="Actual local inference, schema-checked extraction and citation-ID checks; factual completeness still requires review."
    except Exception as error:
        report.update(status="failed",error=type(error).__name__+": "+str(error))
        raise
    finally:
        report["finished_at"]=time.time()
        write_json(ROOT/"output/llm_validation.json",report)
    print(json.dumps({"status":report["status"],"model":report["model"],"relation_f1":report["extraction"]["relation_metrics"]["f1"]},indent=2))


if __name__=="__main__":main()
