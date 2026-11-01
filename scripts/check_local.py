"""Run the local suite and save an auditable report; never launches Docker."""
import argparse
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from orgkg.pipeline import write_json
from orgkg.version import source_fingerprint


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--node")
    args=parser.parse_args()
    import os
    os.chdir(ROOT)
    started=time.perf_counter()
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests"))
    javascript=None
    if args.node:
        javascript=subprocess.run([args.node,"--check","orgkg/web/app.js"],check=False).returncode==0
    report={"status":"passed" if result.wasSuccessful() and javascript is not False else "failed",
            "python":sys.version.split()[0],"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
            "skipped":len(result.skipped),"javascript_syntax":javascript,"seconds":time.perf_counter()-started,
            "source_fingerprint":source_fingerprint()}
    write_json(ROOT/"output/local_validation.json",report)
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report["status"]=="passed" else 1)


if __name__=="__main__":main()
