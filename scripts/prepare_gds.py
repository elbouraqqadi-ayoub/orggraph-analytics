"""Prepare a version-pinned GDS jar on the host, avoiding container proxy issues."""
import hashlib
import json
import urllib.request
from pathlib import Path
from zipfile import is_zipfile

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    lock=json.loads((ROOT/"docker/gds.lock.json").read_text())
    folder=ROOT/".runtime/neo4j"
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/("neo4j-graph-data-science-"+lock["version"]+".jar")
    if not target.exists():
        print("Downloading GDS "+lock["version"]+" from its official publisher",flush=True)
        temporary=target.with_suffix(".download")
        with urllib.request.urlopen(lock["url"],timeout=180) as response, temporary.open("wb") as output:
            while chunk:=response.read(1024*1024):output.write(chunk)
        if not is_zipfile(temporary):
            raise ValueError("The GDS download is not a valid jar archive.")
        actual=hashlib.sha256(temporary.read_bytes()).hexdigest()
        if lock.get("sha256") and actual!=lock["sha256"]:
            raise ValueError("The GDS artifact checksum does not match its lock file.")
        temporary.replace(target)
    actual=hashlib.sha256(target.read_bytes()).hexdigest()
    if lock.get("sha256") and actual!=lock["sha256"]:
        raise ValueError("The installed GDS artifact checksum does not match.")
    print(json.dumps({"gds_version":lock["version"],"sha256":actual,"ready":True}))
    return target


if __name__=="__main__":prepare()
