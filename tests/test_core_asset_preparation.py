from copy import deepcopy
import json
from pathlib import Path
import pytest
from pcb_harness.circuit.bundle import read_json, sha256
from pcb_harness.circuit.sexpr import parse_sexpr, dump_sexpr, children, child
from pcb_harness.circuit.assets import load_part_assets

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks/stm32-communications"


@pytest.fixture
def candidate_case(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    libraries = tmp_path / "libraries"
    (libraries / "symbols").mkdir(parents=True)
    candidate = read_json(BENCHMARK / "core-asset-candidates.json")
    for name in ("design.json", "sources.json"):
        (inputs / name).write_bytes((BENCHMARK / name).read_bytes())
    grouped = {}
    for record in candidate["parts"]:
        lib, name = record["library_id"].split(":")
        symbol = parse_sexpr(f'''(symbol "{name}" (in_bom yes) (on_board yes)
          (property "Value" "SYNTHETIC-TEMPLATE" (at 0 2 0))
          (property "Footprint" "Test:Wrong" (at 0 0 0))
          (property "Datasheet" "https://test.invalid/not-manufacturer" (at 0 0 0))
          (symbol "{name}_0_1" (rectangle (start -1 -1) (end 1 1)))
          (symbol "{name}_1_1"
            (pin input line (at -2 0 0) (length 1) (name "IN") (number "1"))
            (pin output line (at 2 0 180) (length 1) (name "OUT") (number "2"))))''')
        grouped.setdefault(lib, []).append(symbol)
        fp_lib, fp_name = record["candidate_footprint"].split(":")
        fp_path = libraries / "footprints" / (fp_lib + ".pretty") / (fp_name + ".kicad_mod")
        fp_path.parent.mkdir(parents=True, exist_ok=True)
        fp_path.write_text(f'''(footprint "{fp_name}" (version 20241229) (generator "synthetic-test-only")
          (pad "1" smd rect (at -1 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask"))
          (pad "2" smd rect (at 1 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask"))
          (pad "1" smd rect (at -1 0) (size 1 1) (layers "B.Cu"))
          (pad "" smd rect (at 0 0) (size 0.4 0.4) (layers "F.Paste")))''')
        record["footprint_sha256"] = sha256(fp_path)
        record["symbol_pins"] = [dict(number="1", name="IN", type="input"), dict(number="2", name="OUT", type="output")]
        record["electrical_pad_numbers"] = ["1", "2", "1"]
        record["non_electrical_shapes"] = 1
    for lib, symbols in grouped.items():
        raw = '(kicad_symbol_lib (version 20250114) (generator "synthetic-test-only") ' + " ".join(dump_sexpr(s) for s in symbols) + ")\n"
        path = libraries / "symbols" / (lib + ".kicad_sym")
        path.write_text(raw)
        for record in candidate["parts"]:
            if record["library_id"].startswith(lib + ":"):
                record["library_sha256"] = sha256(path)
    candidate["scope"] = "synthetic test only; no manufacturer evidence"
    path = inputs / "candidates.json"
    path.write_text(json.dumps(candidate))
    return path, libraries, tmp_path / "runs/prepared"


def prepare(case):
    from pcb_harness.orchestration.core_assets import prepare_core_assets
    return prepare_core_assets(*case)


def test_exact_assets_audit_and_core_bom_never_promote_board(candidate_case):
    from pcb_harness.orchestration.core_assets import verify_core_assets
    report = prepare(candidate_case)
    output = candidate_case[2]
    assert report["structural_assets_passed"]
    assert report["prepared_part_types"] == 6
    assert report["prepared_ic_instances"] == 8
    assert report["accepted_real_target_assets"] == 0
    assert not report["layout_allowed"] and not report["release_eligible"] and not report["milestone_complete"]
    assert {"PINOUT_PACKAGE_REVIEW", "MODULE_ASSET", "SUPPORT_BOM", "FULL_FIRMWARE"} <= set(report["blockers"])
    parts = read_json(output / "parts.json")["parts"]
    for part in parts:
        loaded = load_part_assets(part, output)
        props = {p[1]: p[2] for p in children(loaded["symbol"], "property")}
        assert props["Value"] == part["mpn"]
        assert props["Footprint"] == part["footprint_id"]
        assert loaded["pad_numbers"] == ["1", "2", "1"]
        assert part["required_fact_ids"]
    bom = read_json(output / "core-bom.json")
    assert {p["ref"] for p in bom["instances"]} == {"U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "M1"}
    assert bom["instances"][-1]["asset_status"] == "unavailable"
    assert verify_core_assets(output)


@pytest.mark.parametrize("change", ["symbol-bytes", "footprint-bytes", "pins", "mpn", "ref", "duplicate", "package", "symbol-path", "footprint-path", "confirmation", "boolean-version", "boolean-shape-count"])
def test_drift_unsafe_paths_or_wrong_target_candidates_rejected(candidate_case, change):
    path, root, output = candidate_case
    candidate = read_json(path)
    first = candidate["parts"][0]
    if change == "symbol-bytes":
        lib = first["library_id"].split(":")[0]
        (root / "symbols" / (lib + ".kicad_sym")).write_text("drift")
    elif change == "footprint-bytes":
        lib, name = first["candidate_footprint"].split(":")
        (root / "footprints" / (lib + ".pretty") / (name + ".kicad_mod")).write_text("drift")
    elif change == "pins":
        first["symbol_pins"][0]["name"] = "CHANGED"
    elif change == "mpn":
        first["mpn"] = "UNREVIEWED-PART"
    elif change == "ref":
        first["ref"] = "U9"
    elif change == "duplicate":
        candidate["parts"].append(deepcopy(first))
    elif change == "package":
        first["candidate_footprint"] = "Package_QFP:Wrong"
    elif change == "symbol-path":
        first["library_id"] = "../escape:Bad"
    elif change == "footprint-path":
        first["candidate_footprint"] = "Package_QFP:../escape"
    elif change == "boolean-version":
        candidate["schema_version"] = True
    elif change == "boolean-shape-count":
        first["non_electrical_shapes"] = True
    else:
        candidate["human_confirmed"] = True
    path.write_text(json.dumps(candidate))
    with pytest.raises((ValueError, FileNotFoundError)):
        prepare(candidate_case)
    assert not (output / "report.json").exists()


def test_preparation_uses_captured_library_bytes_when_original_changes(candidate_case, monkeypatch):
    from pcb_harness.orchestration import core_assets
    path, root, output = candidate_case
    original = core_assets.flatten_symbol
    changed = False
    def alter_original(*args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            for p in (root / "symbols").glob("*.kicad_sym"):
                p.write_text("edited after capture")
            path.write_text("{}")
        return original(*args, **kwargs)
    monkeypatch.setattr(core_assets, "flatten_symbol", alter_original)
    assert prepare(candidate_case)["structural_assets_passed"]
    assert core_assets.verify_core_assets(output)


@pytest.mark.parametrize("name", ["parts.json", "core-bom.json", "assets/STM32Target.kicad_sym", "inputs/candidates.json", "NOTICE.md"])
def test_retained_evidence_removal_or_tamper_rejected(candidate_case, name):
    from pcb_harness.orchestration.core_assets import verify_core_assets
    prepare(candidate_case)
    output = candidate_case[2]
    (output / name).write_text("changed")
    with pytest.raises(ValueError):
        verify_core_assets(output)


def test_required_artifact_cannot_be_omitted_from_manifest(candidate_case):
    from pcb_harness.orchestration.core_assets import verify_core_assets
    prepare(candidate_case)
    output = candidate_case[2]
    manifest = read_json(output / "integrity.json")
    manifest["artifacts"].pop("core-bom.json")
    (output / "core-bom.json").unlink()
    (output / "integrity.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_core_assets(output)


def test_reused_output_and_symlinked_library_are_rejected(candidate_case):
    prepare(candidate_case)
    with pytest.raises(FileExistsError):
        prepare(candidate_case)
    path, root, output = candidate_case
    link = root.parent / "linked"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        prepare((path, link, output.with_name("other")))


@pytest.mark.parametrize("change", ["package", "source-id", "source-url"])
def test_design_package_and_document_association_are_calibrated(candidate_case, change):
    path, root, output = candidate_case
    design_path = path.parent / "design.json"
    design = read_json(design_path)
    if change == "package":
        design["parts"][0]["package"] = "BGA100"
    elif change == "source-id":
        design["parts"][0]["source_id"] = "buck"
    else:
        sources_path = path.parent / "sources.json"
        sources = read_json(sources_path)
        sources["documents"][0]["url"] = "https://www.ti.com/lit/ds/symlink/tps62160.pdf"
        sources_path.write_text(json.dumps(sources))
    design_path.write_text(json.dumps(design))
    with pytest.raises(ValueError):
        prepare(candidate_case)
    assert not (output / "report.json").exists()


@pytest.mark.parametrize("change", ["mpn", "package", "bom", "symbol-value", "symbol-datasheet", "footprint-geometry"])
def test_generated_parts_and_bom_must_match_their_captured_sources(candidate_case, change):
    from pcb_harness.orchestration.core_assets import verify_core_assets
    prepare(candidate_case)
    output = candidate_case[2]
    parts = read_json(output / "parts.json")
    first = parts["parts"][0]
    edited = {"parts.json"}
    if change == "mpn":
        other = parts["parts"][1]
        first["mpn"], other["mpn"] = other["mpn"], first["mpn"]
    elif change == "package":
        first["package"] = "BGA100"
    elif change == "bom":
        bom = read_json(output / "core-bom.json")
        bom["instances"][0]["mpn"] = parts["parts"][1]["mpn"]
        (output / "core-bom.json").write_text(json.dumps(bom))
        edited.add("core-bom.json")
    elif change.startswith("symbol-"):
        symbol_path = output / first["symbol"]["path"]
        library = parse_sexpr(symbol_path.read_text())
        symbol = next(s for s in children(library, "symbol") if s[1] == first["id"])
        key = "Value" if change == "symbol-value" else "Datasheet"
        next(p for p in children(symbol, "property") if p[1] == key)[2] = "incorrect-derived-identity"
        symbol_path.write_text(dump_sexpr(library) + "\n")
        for part in parts["parts"]:
            part["symbol"]["sha256"] = sha256(symbol_path)
        edited.add(first["symbol"]["path"])
    else:
        footprint_path = output / first["footprint"]["path"]
        footprint = parse_sexpr(footprint_path.read_text())
        child(children(footprint, "pad")[0], "size")[1] = 9
        footprint_path.write_text(dump_sexpr(footprint) + "\n")
        first["footprint"]["sha256"] = sha256(footprint_path)
        edited.add(first["footprint"]["path"])
    (output / "parts.json").write_text(json.dumps(parts))
    # Simulate an internally consistent hash update, while the captured inputs stay intact.
    manifest = read_json(output / "integrity.json")
    for name in edited:
        manifest["artifacts"][name] = sha256(output / name)
    (output / "integrity.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_core_assets(output)


@pytest.mark.parametrize("change", ["accepted-count", "prepared-count", "blockers", "support-complete", "boolean-report-version", "boolean-accepted-count"])
def test_report_claims_cannot_exceed_the_preparation_scope(candidate_case, change):
    from pcb_harness.orchestration.core_assets import verify_core_assets
    prepare(candidate_case)
    output = candidate_case[2]
    name = "support-requirements.json" if change == "support-complete" else "report.json"
    data = read_json(output / name)
    if change == "accepted-count":
        data["accepted_real_target_assets"] = 6
    elif change == "prepared-count":
        data["prepared_ic_instances"] = 9
    elif change == "blockers":
        data["blockers"] = []
    elif change == "support-complete":
        data["status"] = "complete"
    elif change == "boolean-report-version":
        data["schema_version"] = True
    else:
        data["accepted_real_target_assets"] = False
    (output / name).write_text(json.dumps(data))
    manifest = read_json(output / "integrity.json")
    manifest["artifacts"][name] = sha256(output / name)
    (output / "integrity.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_core_assets(output)


def test_returned_report_mutation_does_not_change_verification_rules(candidate_case, monkeypatch):
    from pcb_harness.orchestration import core_assets
    monkeypatch.setattr(core_assets, "BLOCKERS", list(core_assets.BLOCKERS))
    report = prepare(candidate_case)
    report["blockers"].clear()
    assert core_assets.verify_core_assets(candidate_case[2])
