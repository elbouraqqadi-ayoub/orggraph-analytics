"""Initialize only missing local state; existing credentials and graphs are preserved."""
import json
import os
import secrets
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from orgkg.pipeline import run_pipeline


def main():
    os.chdir(ROOT)
    if not (ROOT/".env").exists():
        text=(ROOT/".env.example").read_text(encoding="utf-8").replace("change-this-local-password",secrets.token_urlsafe(24))
        (ROOT/".env").write_text(text,encoding="utf-8")
    if not (ROOT/"data/graph.json").exists():
        for source,mode,append in [("data/samples","fixture",False),("data/reference","rules",True)]:
            report=run_pipeline(Path(source),Path("data"),mode,Path("config/aliases.json"),append)
            if not report["published"]:raise RuntimeError("Workspace initialization failed: "+json.dumps(report["errors"]))
    graph=json.loads((ROOT/"data/graph.json").read_text(encoding="utf-8"))
    print(json.dumps({"ready":True,"entities":len(graph["nodes"]),"relationships":len(graph["facts"]),"documents":len(graph["documents"])}))


if __name__=="__main__":main()
