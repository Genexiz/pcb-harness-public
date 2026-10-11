"""Fetch official documents into a new local run directory, never human-confirm facts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import ssl
import urllib.request

def fetch_sources(output, cafile=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    spec = json.loads(Path(__file__).with_name("sources.json").read_text())
    def fetch(document):
        record = dict(document)
        try:
            request = urllib.request.Request(document["url"], headers={"User-Agent": "PCB-Harness-M4/0.1"})
            with urllib.request.urlopen(request, timeout=90, context=ssl.create_default_context(cafile=cafile)) as response:
                data = response.read(25 * 1024 * 1024 + 1)
                record["retrieved_url"] = response.geturl()
            if len(data) > 25 * 1024 * 1024 or not data:
                raise ValueError("empty or oversized source")
            if document["path"].endswith(".pdf") and not data.startswith(b"%PDF"):
                raise ValueError("publisher did not return PDF")
            (output / document["path"]).write_bytes(data)
            record.update(status="retrieved", sha256=hashlib.sha256(data).hexdigest())
        except Exception as error:
            record.update(status="unavailable", error=str(error))
        return record
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(fetch, spec["documents"]))
    (output / "retrieval.json").write_text(json.dumps({"schema_version": 1, "documents": records}, indent=2) + "\n")
    print(json.dumps({d["id"]: d["status"] for d in records}))
    return records

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--cafile", help="Optional system CA bundle; certificate verification remains enabled")
    args = parser.parse_args()
    fetch_sources(args.output, args.cafile)
