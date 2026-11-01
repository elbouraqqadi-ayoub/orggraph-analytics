"""Local operator diagnostic: show query error codes without printing credentials."""
import base64
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from orgkg import services
from orgkg.errors import BackendError

services.load_env(str(ROOT/".env"))
original=services.cypher


def diagnostic(statement,parameters=None):
    print(statement.splitlines()[0],flush=True)
    try:
        return original(statement,parameters)
    except BackendError:
        auth=base64.b64encode((os.environ.get("NEO4J_USER","neo4j")+":"+os.environ["NEO4J_PASSWORD"]).encode()).decode()
        result=services.request_json(os.environ.get("NEO4J_HTTP_URL","http://localhost:7474").rstrip("/")+"/db/neo4j/tx/commit",{"statements":[{"statement":statement,"parameters":parameters or {}}]}, {"Authorization":"Basic "+auth})
        print(result.get("errors"),flush=True)
        raise


if __name__=="__main__":
    services.cypher=diagnostic
    result=services.gds_analytics()
    print({"gds_version":result["version"],"nodes":len(result["pagerank"])})
