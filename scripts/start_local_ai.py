"""Start/reuse local CPU inference, configure local URLs, and pull a model once."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from prepare_native_ollama import main as prepare_cpu


def ready():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/version",timeout=2) as response:
            return bool(json.load(response).get("version"))
    except (OSError,ValueError):return False


def main():
    os.chdir(ROOT)
    executable=ROOT/".runtime/ollama/ollama.exe"
    if not executable.exists():prepare_cpu()
    env={**os.environ,"OLLAMA_HOST":"127.0.0.1:11434","OLLAMA_MODELS":str(ROOT/".runtime/models"),
         "OLLAMA_TMPDIR":str(ROOT/".runtime/tmp"),"OLLAMA_NUM_PARALLEL":"1","OLLAMA_MAX_LOADED_MODELS":"1",
         "OLLAMA_CONTEXT_LENGTH":"8192","OLLAMA_NO_CLOUD":"1","OLLAMA_KEEP_ALIVE":"2m"}
    (ROOT/".runtime/models").mkdir(parents=True,exist_ok=True)
    (ROOT/".runtime/tmp").mkdir(parents=True,exist_ok=True)
    if not ready():
        with (ROOT/".runtime/ollama/stdout.log").open("ab") as stdout,(ROOT/".runtime/ollama/server.log").open("ab") as stderr:
            process=subprocess.Popen([str(executable),"serve"],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                                     creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        (ROOT/".runtime/ollama/server.pid").write_text(str(process.pid))
        deadline=time.monotonic()+30
        while time.monotonic()<deadline and not ready():time.sleep(.5)
        if not ready():raise RuntimeError("Local inference did not start; inspect .runtime/ollama/server.log")
    model=os.environ.get("LOCAL_AI_MODEL","qwen2.5:1.5b")
    dotenv=ROOT/".env"
    text=dotenv.read_text(encoding="utf-8") if dotenv.exists() else (ROOT/".env.example").read_text(encoding="utf-8")
    if not dotenv.exists():
        import secrets
        text=text.replace("change-this-local-password",secrets.token_urlsafe(24))
    values={"LLM_MODEL":model,"LLM_BASE_URL":"http://127.0.0.1:11434/v1","DOCKER_LLM_BASE_URL":"http://host.docker.internal:11434/v1"}
    lines=text.splitlines()
    for key,value in values.items():
        lines=[line for line in lines if not line.startswith(key+"=")]
        lines.append(key+"="+value)
    dotenv.write_text("\n".join(lines)+"\n",encoding="utf-8")
    subprocess.run([str(executable),"pull",model],env=env,check=True,timeout=1800)
    print("Local AI ready. Restart the API to load the updated .env configuration.")


if __name__=="__main__":main()
