"""Reproducible Docker acceptance test. No pruning, volume deletion or user-data reset."""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orgkg.pipeline import write_json
from orgkg.services import cypher, load_env
from orgkg.snapshots import prepare_snapshot
from orgkg.version import source_fingerprint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-port", type=int, default=8081)
    args = parser.parse_args()
    os.chdir(ROOT)
    load_env()
    environment = {**os.environ, "API_PORT":str(args.api_port)}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_data = "data/runs/" + run_id
    hdfs = "/orgkg/runs/" + run_id
    report = {"run_id":run_id,"started_at":datetime.now(timezone.utc).isoformat(),"status":"running","steps":[],"source_fingerprint":source_fingerprint()}
    target = ROOT / "output/pipeline_validation.json"

    def step(name, command, failure=False):
        print(name, flush=True)
        started = time.perf_counter()
        result = subprocess.run(command, cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",timeout=1800)
        passed = (result.returncode != 0 and "enregistrements invalides" in result.stdout) if failure else result.returncode == 0
        report["steps"].append({"name":name,"passed":passed,"seconds":time.perf_counter()-started,"exit_code":result.returncode})
        write_json(target, report)
        if not passed:
            print(result.stdout[-10000:])
            raise RuntimeError("Acceptance step failed: " + name)

    def wait(check, name, timeout=300):
        print("Waiting for " + name,flush=True)
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:
                if check():return
            except Exception:
                pass
            time.sleep(2)
        raise TimeoutError(name + " did not become ready")

    def get(url):
        headers={}
        if os.environ.get("API_TOKEN"):headers["Authorization"]="Bearer "+os.environ["API_TOKEN"]
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=5) as response:
            return json.load(response)

    def hdfs_ready():
        bean=get("http://localhost:9870/jmx?qry=Hadoop:service=NameNode,name=NameNodeInfo")["beans"][0]
        return bool(json.loads(bean.get("LiveNodes","{}"))) and not bean.get("Safemode",bean.get("SafeMode",""))

    api=["docker","compose","run","--rm","api"]
    try:
        step("Prepare version-pinned Graph Data Science plugin",[sys.executable,"scripts/prepare_gds.py"])
        step("Build and start services",["docker","compose","--profile","bigdata","up","-d","--build","neo4j","api","namenode","datanode"])
        wait(lambda:bool(cypher("RETURN 1")),"Neo4j")
        wait(hdfs_ready,"HDFS DataNode registration and safe-mode exit")
        step("Ingest isolated synthetic corpus",api+["--data",run_data,"ingest"])
        original=json.loads((ROOT/run_data/"graph.json").read_text(encoding="utf-8"))
        step("Upload originals and validated extractions to HDFS",api+["--data",run_data,"upload-hdfs","--destination",hdfs])
        spark=["docker","compose","--profile","bigdata","run","--rm","spark","--master","local[2]","--driver-memory","512m","/app/spark_jobs/transform.py"]
        step("Transform and validate with Spark",spark+["hdfs://namenode:9000"+hdfs+"/processed/extractions.jsonl","hdfs://namenode:9000"+hdfs+"/curated"])
        step("Download curated partitions through WebHDFS",api+["download-hdfs","--source",hdfs+"/curated","--destination",run_data+"/curated"])
        step("Validate curated graph before import",api+["--data",run_data,"import-spark","--source",run_data+"/curated"])
        curated=json.loads((ROOT/run_data/"graph.json").read_text(encoding="utf-8"))
        assert prepare_snapshot(original)==prepare_snapshot(curated),"Local and Spark graphs differ"
        step("Load immutable Neo4j snapshot",api+["--data",run_data,"load-neo4j"])
        base="http://localhost:"+str(args.api_port)
        wait(lambda:get(base+"/health").get("backend")=="neo4j","API backed by Neo4j")
        actual=get(base+"/graph")
        assert get(base+"/status").get("source_fingerprint")==report["source_fingerprint"],"The running API image is older than the source; rebuild it"
        expected=prepare_snapshot(curated)["id"]
        assert actual.get("snapshot_id")==expected,"API is not serving the expected snapshot"
        step("Compare Cypher and graph retrieval",api+["compare"])
        comparison=json.loads((ROOT/"output/comparison.json").read_text(encoding="utf-8"))
        assert comparison["snapshot"]==expected
        assert all(c["cypher"]["f1"]==c["graphrag"]["f1"]==1 for c in comparison["cases"])
        step("Run Neo4j Graph Data Science algorithms",api+["gds"])
        bad=ROOT/run_data/"bad/processed"
        bad.mkdir(parents=True)
        (bad/"extractions.jsonl").write_text('{"invalid":"record"}\n',encoding="utf-8")
        step("Stage invalid records for a rejection test",api+["--data",run_data+"/bad","upload-hdfs","--destination",hdfs+"/bad"])
        step("Spark rejects invalid input without replacing curated data",spark+["hdfs://namenode:9000"+hdfs+"/bad/processed/extractions.jsonl","hdfs://namenode:9000"+hdfs+"/curated"],failure=True)
        step("Download preserved export",api+["download-hdfs","--source",hdfs+"/curated","--destination",run_data+"/preserved"])
        step("Validate preserved export",api+["--data",run_data+"/preserved_graph","import-spark","--source",run_data+"/preserved"])
        preserved=json.loads((ROOT/run_data/"preserved_graph/graph.json").read_text(encoding="utf-8"))
        assert prepare_snapshot(preserved)==prepare_snapshot(curated)
        report.update(status="passed",snapshot=expected,nodes=len(actual["nodes"]),facts=len(actual["facts"]),api_url=base)
        write_json(ROOT/"output/services_validation.json",{"schema_version":2,"neo4j":"passed","api_neo4j":"passed","comparison":"passed","snapshot":expected})
    except Exception as error:
        report.update(status="failed",error=type(error).__name__+": "+str(error))
        raise
    finally:
        report["finished_at"]=datetime.now(timezone.utc).isoformat()
        write_json(target,report)


if __name__=="__main__":
    main()
