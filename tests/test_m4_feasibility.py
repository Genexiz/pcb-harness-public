from pathlib import Path
import json
import shutil
import pytest
from pcb_harness.circuit.bundle import read_json, sha256

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks/stm32-communications"
CHECKLIST = ROOT / "checklists/stm32-communications/resources.json"


def synthetic_sources(tmp_path):
    spec = read_json(BENCHMARK / "sources.json")
    source_root = tmp_path / "sources"
    source_root.mkdir()
    lock = {"schema_version": 1, "documents": []}
    for record in spec["documents"]:
        target = source_root / record["path"]
        if target.suffix == ".png":
            target.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic envelope only\x00\x00\x00\x00IEND\xaeB`\x82")
        else:
            target.write_bytes(b"<html>synthetic integrity fixture</html>" if target.suffix == ".html"
                               else b"%PDF-1.4 synthetic integrity fixture, not manufacturer evidence\n%%EOF\n")
        lock["documents"].append({**record, "status": "retrieved", "sha256": sha256(target)})
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock))
    return source_root, lock_path


def test_hash_matching_sources_never_promote_incomplete_board_to_layout(tmp_path):
    from pcb_harness.orchestration.m4 import run_feasibility, verify_report
    source_root, lock = synthetic_sources(tmp_path)
    output = tmp_path / "report"
    report = run_feasibility(BENCHMARK, CHECKLIST, source_root, lock, None, output)
    assert report["sources"]["integrity_passed"]
    assert report["assessment"]["resources"]["passed"]
    assert report["layout_allowed"] is False
    assert report["release_eligible"] is False
    assert report["milestone_complete"] is False
    assert {"FULL_FIRMWARE", "POWER_THERMAL", "CIRCUIT_NATIVE", "MECHANICAL", "ERRATA"} <= set(report["blockers"])
    assert verify_report(output)
    (output / "report.json").write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        verify_report(output)


def test_missing_or_tampered_document_closes_source_gate(tmp_path):
    from pcb_harness.orchestration.m4 import audit_sources
    source_root, lock = synthetic_sources(tmp_path)
    (source_root / "stm32-ds.pdf").write_bytes(b"wrong revision")
    result = audit_sources(BENCHMARK / "sources.json", source_root, lock)
    assert not result["integrity_passed"]
    assert "stm32-ds" in result["unavailable_or_drifted"]


def test_matching_hash_does_not_turn_publisher_html_into_a_pdf(tmp_path):
    from pcb_harness.orchestration.m4 import audit_sources
    source_root, lock = synthetic_sources(tmp_path)
    target = source_root / "stm32-ds.pdf"
    target.write_bytes(b"<html>Access denied, not a datasheet</html>")
    data = read_json(lock)
    data["documents"][0]["sha256"] = sha256(target)
    lock.write_text(json.dumps(data))
    result = audit_sources(BENCHMARK / "sources.json", source_root, lock)
    assert not result["integrity_passed"]
    assert "stm32-ds" in result["unavailable_or_drifted"]


def test_source_hash_and_format_are_checked_on_the_same_bytes(tmp_path, monkeypatch):
    from pcb_harness.orchestration import m4
    source_root, lock = synthetic_sources(tmp_path)
    target = source_root / "stm32-ds.pdf"
    invalid = b"<html>Publisher error, not a PDF</html>"
    target.write_bytes(invalid)
    manifest = read_json(lock)
    manifest["documents"][0]["sha256"] = sha256(target)
    lock.write_text(json.dumps(manifest))
    original = m4.source_format_matches

    def replace_during_format_check(path, data=None):
        if Path(path) != target:
            return original(path) if data is None else original(path, data)
        target.write_bytes(b"%PDF-1.4 transient replacement\n%%EOF\n")
        try:
            return original(path) if data is None else original(path, data)
        finally:
            target.write_bytes(invalid)

    monkeypatch.setattr(m4, "source_format_matches", replace_during_format_check)
    output = tmp_path / "report"
    report = m4.run_feasibility(BENCHMARK, CHECKLIST, source_root, lock, None, output)
    assert not report["sources"]["integrity_passed"]
    assert "stm32-ds" in report["sources"]["unavailable_or_drifted"]
    assert not (output / "sources/stm32-ds.pdf").exists()
    assert m4.verify_report(output)


@pytest.mark.parametrize("name,data", [
    ("source.pdf", b"%PDF-1.4 incomplete download"),
    ("source.html", b"publisher gateway error"),
    ("source.png", b"\x89PNG\r\n\x1a\ntruncated image"),
    ("source.bin", b"unknown document format"),
])
def test_partial_or_unknown_source_envelopes_are_rejected(tmp_path, name, data):
    from pcb_harness.orchestration.m4 import source_format_matches
    target = tmp_path / name
    target.write_bytes(data)
    assert not source_format_matches(target)


def test_source_manifest_omissions_and_duplicate_ids_are_not_accepted(tmp_path):
    from pcb_harness.orchestration.m4 import audit_sources
    source_root, lock = synthetic_sources(tmp_path)
    data = read_json(lock)
    data["documents"][-1] = data["documents"][0]
    lock.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        audit_sources(BENCHMARK / "sources.json", source_root, lock)


def test_run_directory_reuse_is_rejected(tmp_path):
    from pcb_harness.orchestration.m4 import run_feasibility
    source_root, lock = synthetic_sources(tmp_path)
    output = tmp_path / "report"
    output.mkdir()
    with pytest.raises(FileExistsError):
        run_feasibility(BENCHMARK, CHECKLIST, source_root, lock, None, output)


def test_engineering_dossier_is_captured_before_assessment(tmp_path, monkeypatch):
    from pcb_harness.orchestration import m4
    from test_stm32_engineering import evidence
    source_root, lock = synthetic_sources(tmp_path)
    dossier = tmp_path / "engineering.json"
    dossier.write_text(json.dumps(evidence()[1]))
    original = m4.assess_design

    def mutate_original_after_capture(design, checklist):
        dossier.write_text("{}")
        return original(design, checklist)

    monkeypatch.setattr(m4, "assess_design", mutate_original_after_capture)
    output = tmp_path / "report"
    report = m4.run_feasibility(BENCHMARK, CHECKLIST, source_root, lock, None, output,
                                engineering_path=dossier)
    assert report["engineering"]["controllers"]["devices"][1]["ram_used_bytes"] == 1280
    assert not report["layout_allowed"]
    assert "CONTROLLER_CONFIG" in report["blockers"]  # synthetic source ID cannot bind
    assert read_json(output / "inputs/engineering.json")["design_id"] != ""
    assert m4.verify_report(output)


def test_engineering_snapshot_is_required_even_if_removed_from_integrity_list(tmp_path):
    from pcb_harness.orchestration.m4 import run_feasibility, verify_report
    from test_stm32_engineering import evidence
    source_root, lock = synthetic_sources(tmp_path)
    dossier = tmp_path / "engineering.json"
    dossier.write_text(json.dumps(evidence()[1]))
    output = tmp_path / "report"
    run_feasibility(BENCHMARK, CHECKLIST, source_root, lock, None, output, engineering_path=dossier)
    integrity = read_json(output / "integrity.json")
    integrity["artifacts"].pop("inputs/engineering.json")
    (output / "integrity.json").write_text(json.dumps(integrity))
    (output / "inputs/engineering.json").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        verify_report(output)


def test_symlink_output_parent_is_rejected_before_write(tmp_path):
    from pcb_harness.orchestration.m4 import run_feasibility
    source_root, lock = synthetic_sources(tmp_path)
    destination = tmp_path / "destination"
    destination.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        run_feasibility(BENCHMARK, CHECKLIST, source_root, lock, None, alias / "report")
    assert not (destination / "report").exists()


def test_assessment_uses_immutable_input_snapshot_when_original_changes(tmp_path, monkeypatch):
    from pcb_harness.orchestration import m4
    source_root, lock = synthetic_sources(tmp_path)
    benchmark = tmp_path / "benchmark"
    shutil.copytree(BENCHMARK, benchmark)
    original = m4.assess_design

    def change_original_after_assessment(design, checklist):
        result = original(design, checklist)
        changed = read_json(benchmark / "design.json")
        changed["package"] = "LQFP64"
        (benchmark / "design.json").write_text(json.dumps(changed))
        return result

    monkeypatch.setattr(m4, "assess_design", change_original_after_assessment)
    output = tmp_path / "report"
    report = m4.run_feasibility(benchmark, CHECKLIST, source_root, lock, None, output)
    snapshot = read_json(output / "inputs/design.json")
    assert snapshot["package"] == "LQFP48"
    assert report["assessment"] == original(snapshot, read_json(output / "inputs/resources.json"))
    assert m4.verify_report(output)


def test_report_uses_verification_result_of_the_captured_build(tmp_path, monkeypatch):
    from pcb_harness.orchestration import m4
    from pcb_harness.orchestration.firmware_evidence import build_probe, verify_probe
    compiler = ROOT / "runs/m4/toolchain/arm-gnu-toolchain-13.2.Rel1-darwin-arm64-arm-none-eabi/bin/arm-none-eabi-gcc"
    if not compiler.is_file():
        pytest.skip("Arm GNU compiler unavailable")
    source_root, lock = synthetic_sources(tmp_path)
    build = tmp_path / "build"
    build_probe(BENCHMARK / "firmware", build, compiler)
    original_copy = shutil.copyfile

    def replace_build_metadata_before_capture(source, destination):
        if Path(source) == build / "build.json":
            data = read_json(source)
            data["compiler_version"] = "replacement valid build provenance\n"
            Path(source).write_text(json.dumps(data))
        return original_copy(source, destination)

    monkeypatch.setattr(m4.shutil, "copyfile", replace_build_metadata_before_capture)
    output = tmp_path / "report"
    report = m4.run_feasibility(BENCHMARK, CHECKLIST, source_root, lock, build, output)
    captured = verify_probe(output / "firmware/sources", output / "firmware")
    assert report["firmware"] == captured


def test_full_driver_build_is_captured_and_reverified_without_promoting_timing(tmp_path):
    from pcb_harness.orchestration.m4 import run_feasibility, verify_report
    from pcb_harness.orchestration.firmware_complete import build_complete
    fw=BENCHMARK/'firmware-full'
    compiler=ROOT/'runs/m4/toolchain/arm-gnu-toolchain-13.2.Rel1-darwin-arm64-arm-none-eabi/bin/arm-none-eabi-gcc'
    if not compiler.is_file():pytest.skip('retained ARM toolchain required for full build integration')
    build=tmp_path/'full-build'; build_complete(fw,build,compiler)
    source_root,lock=synthetic_sources(tmp_path);out=tmp_path/'report'
    r=run_feasibility(BENCHMARK,CHECKLIST,source_root,lock,None,out,
                      full_firmware_root=build,full_firmware_sources=fw)
    assert r['full_firmware']['full_firmware_build_passed'] is True
    assert r['full_firmware']['usage']['flash_bytes']<=65536
    assert 'FULL_FIRMWARE' not in r['blockers']
    assert 'CAPACITY_PROBE' not in r['blockers']
    assert 'FULL_FIRMWARE_TIMING' in r['blockers']
    assert not r['layout_allowed'] and not r['milestone_complete']
    assert verify_report(out)
    elf=out/'firmware-full/build/full.elf';elf.write_bytes(elf.read_bytes()+b'drift')
    manifest=read_json(out/'integrity.json');manifest['artifacts']['firmware-full/build/full.elf']=sha256(elf)
    (out/'integrity.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='hash drift'):verify_report(out)


@pytest.mark.parametrize('extra', [False, True])
def test_rehashed_forged_feasibility_gate_is_rejected(tmp_path, extra):
    from pcb_harness.orchestration.m4 import run_feasibility, verify_report
    source_root, lock = synthetic_sources(tmp_path)
    output = tmp_path / "report"
    run_feasibility(BENCHMARK, CHECKLIST, source_root, lock, None, output)
    if extra:
        (output / 'unlisted.json').write_text('{}')
        with pytest.raises(ValueError, match='inventory'):
            verify_report(output)
        return
    report = read_json(output / 'report.json')
    report.update(blockers=[], layout_allowed=True, milestone_complete=True)
    (output / 'report.json').write_text(json.dumps(report))
    manifest = read_json(output / 'integrity.json')
    manifest['artifacts']['report.json'] = sha256(output / 'report.json')
    (output / 'integrity.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='reconstructed'):
        verify_report(output)
