from pathlib import Path
import argparse
import json
import shutil
import time
import uuid

from .fixture import fixture_hashes, load_benchmark


def _copy_bundle(source: Path, target: Path, relative_paths: list[str], *, manifest=True):
    target.mkdir(parents=True, exist_ok=False)
    for relative in relative_paths:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
    if manifest:
        shutil.copy2(source / "benchmark.json", target / "benchmark.json")


def prepare_campaign(fixture: Path, campaign: Path, repeats: int = 5) -> list[Path]:
    fixture = Path(fixture).resolve()
    campaign = Path(campaign).resolve()
    if type(repeats) is not int or repeats <= 0:
        raise ValueError("repeats must be a positive integer")
    benchmark = load_benchmark(fixture / "benchmark.json")
    observed = fixture_hashes(fixture)
    if observed != benchmark["sha256"]:
        raise ValueError("fixture hashes do not match benchmark manifest")
    campaign.mkdir(parents=True, exist_ok=False)
    paths = []
    for repeat in range(1, repeats + 1):
        run = campaign / f"run-{repeat}"
        run.mkdir()
        relative_paths = sorted(benchmark["sha256"])
        _copy_bundle(fixture, run / "input", relative_paths)
        _copy_bundle(fixture, run / "project", relative_paths, manifest=False)
        data = {
            "schema_version": 1,
            "run_id": str(uuid.uuid4()),
            "repeat": repeat,
            "fixture": str(fixture),
            "fixture_sha256": benchmark["sha256"],
            "board": "project/" + benchmark["board"],
            "input": "input/" + benchmark["board"],
            "service_directory": "service",
            "transcript": "host-transcript.jsonl",
            "max_actions": 300,
            "max_duration_seconds": 1200,
            "prepared_at": time.time(),
        }
        (run / "manifest.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        paths.append(run)
    return paths


def main():
    parser = argparse.ArgumentParser(description="Prepare isolated M2 routing runs")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    options = parser.parse_args()
    runs = prepare_campaign(options.fixture, options.campaign, options.repeats)
    print(json.dumps({"campaign": str(Path(options.campaign).resolve()),
                      "runs": [str(path) for path in runs]}, indent=2))


if __name__ == "__main__":
    main()
