"""Extract only CPU runtime entries from an official, pinned Windows release ZIP.

HTTP range reads avoid downloading CUDA/ROCm libraries. ZipFile checks each entry's
CRC. The entire upstream archive is not downloaded or checksum-verified.
"""
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
VERSION="v0.40.13"


class RemoteZip(io.RawIOBase):
    def __init__(self,url,size):
        self.url,self.size,self.position=url,size,0
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        self.position=offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        if self.position<0:raise ValueError("Negative archive offset")
        return self.position
    def read(self,size=-1):
        size=min(self.size-self.position,size if size>=0 else self.size-self.position)
        if size<=0:return b""
        request=urllib.request.Request(self.url,headers={"Range":f"bytes={self.position}-{self.position+size-1}","User-Agent":"OrgGraph-Setup"})
        with urllib.request.urlopen(request,timeout=180) as response:
            if response.status!=206:
                raise RuntimeError("The official artifact server did not honor range reads; no full-archive fallback is performed.")
            data=response.read(size+1)
        if len(data)>size:raise ValueError("Unexpected archive range length")
        self.position+=len(data)
        return data


def main():
    if sys.platform!="win32":raise RuntimeError("Use the official Ollama installer or Docker profile on non-Windows systems.")
    folder=ROOT/".runtime/ollama"
    folder.mkdir(parents=True,exist_ok=True)
    cached=folder/"manifest.json"
    if cached.exists():
        manifest=json.loads(cached.read_text(encoding="utf-8"))
        valid=manifest.get("version")==VERSION and bool(manifest.get("files"))
        for item in manifest.get("files",[]):
            path=(folder/item["name"]).resolve()
            valid=valid and path.is_relative_to(folder.resolve()) and path.is_file()
            if not valid:break
            valid=hashlib.sha256(path.read_bytes()).hexdigest()==item["sha256"]
            if not valid:break
        if valid:
            print("CPU runtime ready (verified local cache)",flush=True)
            return
    with urllib.request.urlopen("https://api.github.com/repos/ollama/ollama/releases/tags/"+VERSION,timeout=30) as response:
        release=json.load(response)
    asset=next(a for a in release["assets"] if a["name"]=="ollama-windows-amd64.zip")
    manifest={"version":VERSION,"source":asset["browser_download_url"],"files":[]}
    with ZipFile(RemoteZip(asset["browser_download_url"],asset["size"])) as archive:
        blocked=("cuda","cublas","cudart","rocm","vulkan","mlx","hipblas","rocblas")
        selected=[entry for entry in archive.infolist() if not entry.is_dir() and
                  (entry.filename=="ollama.exe" or entry.filename.startswith("lib/ollama/")) and
                  not any(word in entry.filename.lower() for word in blocked)]
        print(json.dumps({"cpu_files":len(selected),"download_mb":round(sum(e.compress_size for e in selected)/1024/1024,1)}),flush=True)
        for entry in selected:
            if entry.file_size>300*1024*1024:raise ValueError("Unexpected CPU artifact size")
            target=(folder/entry.filename).resolve()
            if not target.is_relative_to(folder.resolve()):raise ValueError("Unsafe archive path")
            if not target.exists() or target.stat().st_size!=entry.file_size:
                print("Extracting "+entry.filename,flush=True)
                content=archive.read(entry)
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(content)
            manifest["files"].append({"name":entry.filename,"crc32":entry.CRC,"sha256":hashlib.sha256(target.read_bytes()).hexdigest()})
    if not (folder/"ollama.exe").exists():raise RuntimeError("The official archive did not contain the runtime executable")
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print("CPU runtime ready",flush=True)


if __name__=="__main__":main()
