"""Pre-layout feasibility evidence runner. An incomplete real board stays gated."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from pcb_harness.circuit.bundle import read_json, resolve_local, sha256
from pcb_harness.orchestration.firmware_evidence import verify_probe, INPUTS, OUTPUTS
from pcb_harness.orchestration.stm32_feasibility import assess_design
from pcb_harness.orchestration.engineering_evidence import assess_engineering


def checked_path(path):
    path = Path(path).absolute()
    return resolve_local(path.parent, path.name)


def source_format_matches(path, data=None):
    """Check the file envelope, not the truth or revision of its contents."""
    data = path.read_bytes() if data is None else data
    if path.suffix.lower() == ".pdf":
        return data.startswith(b"%PDF-") and b"%%EOF" in data[-4096:]
    if path.suffix.lower() == ".html":
        return b"<html" in data[:4096].lower() or b"<!doctype html" in data[:4096].lower()
    if path.suffix.lower() == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n") and data.endswith(b"IEND\xaeB`\x82")
    return False


def audit_sources(spec_path, source_root, lock_path):
    spec, lock = read_json(checked_path(spec_path)), read_json(checked_path(lock_path))
    if spec["schema_version"] != 1 or lock["schema_version"] != 1:
        raise ValueError("unsupported source manifest version")
    expected = {record["id"]: record for record in spec["documents"]}
    records = {record["id"]: record for record in lock["documents"]}
    if len(expected) != len(spec["documents"]) or len(records) != len(lock["documents"]) or set(expected) != set(records):
        raise ValueError("missing or duplicate source IDs")
    failures, hashes = [], {}
    for did, record in records.items():
        if any(record.get(key) != value for key, value in expected[did].items()):
            raise ValueError(f"source metadata drift: {did}")
        target = resolve_local(source_root, record["path"])
        data = target.read_bytes() if target.is_file() else None
        if (record.get("status") != "retrieved" or data is None
                or hashlib.sha256(data).hexdigest() != record.get("sha256")
                or not source_format_matches(target, data)):
            failures.append(did)
        else:
            hashes[record["path"]] = record["sha256"]
    return {"integrity_passed": not failures, "retrieved_count": len(hashes),
            "required_count": len(expected), "unavailable_or_drifted": failures,
            "hashes": hashes, "human_confirmed": False,
            "limits": "hash-matching local publisher snapshots; retrieval is not electrical review or human confirmation"}


NEXT_EVIDENCE = {
    "FULL_FIRMWARE": "Complete nine-interface test firmware, real cross-build/map, stack/buffer review and bounded CPU/service timing",
    "POWER_THERMAL": "Source-bound operating currents, WIZ550io maximum or validated limit, buck losses/inductor/capacitor/thermal design and external-load limits",
    "CIRCUIT_NATIVE": "Complete BOM, pin-symbol-pad assets and electrical circuit review, native schematic ERC/PCB bootstrap/exact parity",
    "MECHANICAL": "Version-matched WIZ550io header/body/height and exact connectors/mounting/courtyard drawings",
    "ERRATA": "Selected silicon revision, ES096 assessment and implemented I2C/USB workarounds",
    "FABRICATION": "Selected stackup/service and all mandatory fabrication/assembly requirements"}


def _probe_firmware(output):
    """Reconstruct the probe result from the retained copy, including capture failure."""
    fw = output / "firmware"
    firmware = {"capacity_probe_passed": False, "full_firmware_status": "unknown", "error": "no build supplied"}
    if (fw / "capture-error.txt").exists():
        firmware["error"] = (fw / "capture-error.txt").read_text()
    elif fw.exists():
        try:
            firmware = verify_probe(fw / "sources", fw)
        except (ValueError, OSError) as error:
            firmware["error"] = str(error)
    return firmware


def _feasibility_report(output, source_root):
    """Derive every gate from retained inputs; shared by capture and verification."""
    inputs = output / "inputs"
    assessment = assess_design(read_json(inputs / "design.json"), read_json(inputs / "resources.json"))
    sources = audit_sources(inputs / "sources.json", source_root, inputs / "sources.lock.json")
    engineering = (assess_engineering(read_json(inputs / "design.json"), read_json(inputs / "engineering.json"),
                                      sources, read_json(inputs / "sources.lock.json"))
                   if (inputs / "engineering.json").exists() else None)
    firmware = _probe_firmware(output)
    blockers = ["FULL_FIRMWARE", "POWER_THERMAL", "CIRCUIT_NATIVE", "MECHANICAL", "ERRATA", "FABRICATION"]
    full_firmware = None
    complete = output / 'firmware-full'
    if complete.exists():
        from .firmware_complete import verify_complete
        full_firmware = verify_complete(complete / 'sources', complete / 'build')
        if full_firmware['full_firmware_build_passed'] is True:
            blockers.remove('FULL_FIRMWARE')
        if full_firmware['timing_qualified'] is not True:
            blockers.append('FULL_FIRMWARE_TIMING')
    if not sources["integrity_passed"]:
        blockers.append("SOURCE_INTEGRITY")
    if not assessment["resources"]["passed"]:
        blockers.append("RESOURCES")
    if not assessment["scheduling"]["wire_budget_passed"]:
        blockers.append("WIRE_BUDGET")
    if not firmware["capacity_probe_passed"] and not (full_firmware and full_firmware['full_firmware_build_passed'] is True):
        blockers.append("CAPACITY_PROBE")
    if engineering is not None and not engineering["controllers"]["arithmetic_passed"]:
        blockers.append("CONTROLLER_CONFIG")
    report = {"schema_version": 1, "milestone": "M4", "scope": "pre-layout resource feasibility",
              "assessment": assessment, "sources": sources, "firmware": firmware, "engineering": engineering,
              "blockers": blockers, "layout_allowed": False, "release_eligible": False,
              "milestone_complete": False, "next_evidence": NEXT_EVIDENCE}
    if full_firmware is not None:
        report['full_firmware'] = full_firmware
    return report


def run_feasibility(benchmark, checklist_path, source_root, lock_path, firmware_root, output,
                    engineering_path=None, *, full_firmware_root=None, full_firmware_sources=None):
    if (full_firmware_root is None) != (full_firmware_sources is None):
        raise ValueError('full firmware build and sources must be supplied together')
    benchmark, output = checked_path(benchmark), checked_path(output)
    checklist_path, lock_path = checked_path(checklist_path), checked_path(lock_path)
    # Capture inputs before evaluating. The report must describe these exact bytes,
    # even if a person edits the originals while the read-only assessment runs.
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    inputs.mkdir()
    for name, source in (("design.json", resolve_local(benchmark, "design.json")),
                         ("resources.json", checklist_path), ("sources.json", resolve_local(benchmark, "sources.json")),
                         ("sources.lock.json", lock_path)):
        shutil.copyfile(source, inputs / name)
    if engineering_path is not None:
        shutil.copyfile(checked_path(engineering_path), inputs / "engineering.json")
    if firmware_root is not None:
        fw = output / "firmware"
        fw.mkdir()
        (fw / "sources").mkdir()
        try:
            for name in ("build.json", *OUTPUTS):
                shutil.copyfile(resolve_local(firmware_root, name), fw / name)
            for name in INPUTS:
                shutil.copyfile(resolve_local(benchmark / "firmware", name), fw / "sources" / name)
        except (ValueError, OSError) as error:
            (fw / "capture-error.txt").write_text(str(error))
    if full_firmware_root is not None:
        from .firmware_complete import verify_complete, OUTPUTS as FULL_OUTPUTS
        full_firmware_root, full_firmware_sources = map(checked_path, (full_firmware_root, full_firmware_sources))
        verify_complete(full_firmware_sources, full_firmware_root)
        complete = output / 'firmware-full'
        build = complete / 'build'
        build.mkdir(parents=True)
        for name in ('build.json', *FULL_OUTPUTS):
            shutil.copyfile(resolve_local(full_firmware_root, name), build / name)
        source_manifest = read_json(build / 'build.json')['sources']
        for name in source_manifest:
            target = resolve_local(complete / 'sources', name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resolve_local(full_firmware_sources, name), target)
    report = _feasibility_report(output, source_root)
    snapshots = output / "sources"
    snapshots.mkdir()
    for name, digest in report["sources"]["hashes"].items():
        target = resolve_local(snapshots, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = resolve_local(source_root, name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest or not source_format_matches(target, data):
            raise ValueError(f"source changed during evidence capture: {name}")
        target.write_bytes(data)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    artifacts = {str(path.relative_to(output)): sha256(path) for path in sorted(output.rglob("*")) if path.is_file()}
    (output / "integrity.json").write_text(json.dumps({"schema_version": 1, "artifacts": artifacts}, indent=2) + "\n")
    verify_report(output)
    return report


def verify_report(root):
    """Check the exact retained inventory, then rebuild the report from it."""
    root = Path(root).absolute()
    integrity = read_json(resolve_local(root, "integrity.json"))
    required = {"report.json", "inputs/design.json", "inputs/resources.json", "inputs/sources.json", "inputs/sources.lock.json"}
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p != root / "integrity.json"}
    if read_json(resolve_local(root, "report.json")).get("engineering") is not None:
        required.add("inputs/engineering.json")
    if integrity["schema_version"] != 1 or not required <= set(integrity["artifacts"]):
        raise ValueError("incomplete report integrity manifest")
    if actual != set(integrity["artifacts"]):
        raise ValueError("report integrity inventory differs from retained files")
    for name, digest in integrity["artifacts"].items():
        if sha256(resolve_local(root, name)) != digest:
            raise ValueError(f"report hash drift: {name}")
    report = read_json(resolve_local(root, "report.json"))
    if json.dumps(report, sort_keys=True) != json.dumps(_feasibility_report(root, root / "sources"), sort_keys=True):
        raise ValueError("feasibility report differs from reconstructed evidence")
    complete = root / 'firmware-full'
    if complete.exists():
        from .firmware_complete import OUTPUTS as FULL_OUTPUTS
        build_manifest = read_json(complete / 'build/build.json')
        full_required = {'firmware-full/build/' + n for n in ('build.json', *FULL_OUTPUTS)}
        full_required.update('firmware-full/sources/' + n for n in build_manifest['sources'])
        if not full_required <= set(integrity['artifacts']):
            raise ValueError('incomplete full firmware capture')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="benchmarks/stm32-communications")
    parser.add_argument("--checklist", default="checklists/stm32-communications/resources.json")
    parser.add_argument("--sources", required=True)
    parser.add_argument("--source-lock", required=True)
    parser.add_argument("--firmware")
    parser.add_argument('--full-firmware', help='Complete nine-interface ARM build directory')
    parser.add_argument('--full-firmware-sources', help='Matching pinned application and vendor sources')
    parser.add_argument("--engineering", help="Optional source-bound engineering dossier; all complete-board gates remain required")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run_feasibility(args.benchmark, args.checklist, args.sources, args.source_lock, args.firmware, args.output,
                             engineering_path=args.engineering, full_firmware_root=args.full_firmware,
                             full_firmware_sources=args.full_firmware_sources)
    print(json.dumps({"layout_allowed": report["layout_allowed"], "blockers": report["blockers"]}))
    # Successful evidence capture is not a successful pre-layout gate.
    return 0 if report["layout_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
