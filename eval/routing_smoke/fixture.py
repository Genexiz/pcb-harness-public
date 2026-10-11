from pathlib import Path
import hashlib
import json


REQUIRED_FIELDS = {
    "schema_version", "board", "refs", "nets", "initial_track_count",
    "initial_via_count", "min_host_placement_actions", "sha256",
}


def load_benchmark(path: Path) -> dict:
    data = json.loads(Path(path).read_text())
    if set(data) != REQUIRED_FIELDS or data["schema_version"] != 1:
        raise ValueError("unsupported routing benchmark manifest")
    return data


def fixture_hashes(root: Path) -> dict[str, str]:
    root = Path(root)
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.name != "benchmark.json"
        and (
            path.suffix in {".kicad_pcb", ".kicad_pro", ".kicad_dru", ".kicad_sch",
                            ".kicad_sym", ".kicad_mod"}
            or path.name in {"fp-lib-table", "sym-lib-table"}
        )
    )
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }
