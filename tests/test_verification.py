"""A parser that ignores parity/ERC sheets or tool errors would fail these tests."""
from pathlib import Path
import importlib.util
import json
import pytest

MODULE = Path(__file__).resolve().parents[1] / "experiments/kicad-ipc/verification.py"


def verifier():
    assert MODULE.exists(), "fail-closed report reader not implemented"
    spec = importlib.util.spec_from_file_location("verification", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def drc():
    return {"$schema": "https://schemas.kicad.org/drc.v1.json",
        "source": "board.kicad_pcb", "kicad_version": "10.0.0",
        "coordinate_units": "mm", "violations": [], "unconnected_items": [],
        "schematic_parity": [], "ignored_checks": [],
        "included_severities": ["error", "warning", "exclusion"]}


def violation(kind="clearance"):
    return {"type": kind, "severity": "error", "description": "fixture violation", "items": []}


def test_complete_clean_report_passes():
    result = verifier().parse_report(drc(), "drc", "board.kicad_pcb", 0)
    assert result["passed"] is True


@pytest.mark.parametrize("section", ["violations", "unconnected_items", "schematic_parity"])
def test_each_drc_failure_section_blocks_pass(section):
    report = drc()
    report[section] = [violation()]
    result = verifier().parse_report(report, "drc", "board.kicad_pcb", 5)
    assert result["passed"] is False
    assert result["issue_count"] == 1


def test_erc_reads_all_sheets():
    report = {k: v for k, v in drc().items()
              if k not in ("violations", "unconnected_items", "schematic_parity")}
    report.update({"$schema": "https://schemas.kicad.org/erc.v1.json", "source": "board.kicad_sch",
        "sheets": [{"violations": []}, {"violations": [violation("pin_to_pin")]}]})
    assert verifier().parse_report(report, "erc", "board.kicad_sch", 5)["passed"] is False


@pytest.mark.parametrize("mutation", ["missing_parity", "unknown_schema", "wrong_source",
    "bad_units", "malformed_section", "unknown_severity", "missing_severities"])
def test_unknown_or_incomplete_reports_fail_closed(mutation):
    report = drc()
    if mutation == "missing_parity": del report["schematic_parity"]
    if mutation == "unknown_schema": report["$schema"] = "drc.v999.json"
    if mutation == "wrong_source": report["source"] = "other.kicad_pcb"
    if mutation == "bad_units": report["coordinate_units"] = "unknown"
    if mutation == "malformed_section": report["violations"] = {}
    if mutation == "unknown_severity": report["violations"] = [{**violation(), "severity": "unknown"}]
    if mutation == "missing_severities": report["included_severities"] = ["error"]
    with pytest.raises(ValueError):
        verifier().parse_report(report, "drc", "board.kicad_pcb", 0)


@pytest.mark.parametrize("exit_code", [-6, 1, 2, 5])
def test_process_failure_never_turns_empty_report_into_pass(exit_code):
    with pytest.raises(ValueError):
        verifier().parse_report(drc(), "drc", "board.kicad_pcb", exit_code)


def test_excluded_violation_still_blocks_clean_pass():
    report = drc()
    report["violations"] = [{**violation(), "severity": "exclusion"}]
    assert verifier().parse_report(report, "drc", "board.kicad_pcb", 0)["passed"] is False


def test_runner_does_not_reuse_old_report_when_executable_fails(tmp_path):
    fake_cli = tmp_path / "fake-cli"
    fake_cli.write_text("#!/bin/sh\nexit 2\n")
    fake_cli.chmod(0o755)
    report_path = tmp_path / "drc.json"
    report_path.write_text(json.dumps(drc()))
    result = verifier().run_verification(fake_cli, "drc", Path("board.kicad_pcb"), report_path)
    assert result["status"] == "tool_error"
    assert result["passed"] is False


def test_wrong_ipc_document_rejected_before_returning_board():
    module = verifier()
    from kipy.proto.common.types import DocumentSpecifier, DocumentType
    doc = DocumentSpecifier(type=DocumentType.DOCTYPE_PCB, board_filename="unrelated.kicad_pcb")
    doc.project.path = "/home/dev/something-else"
    with pytest.raises(ValueError):
        module.select_document([doc], Path("/home/dev/PCB_Harness/fixtures/capability/board.kicad_pcb"))


def test_ambiguous_ipc_document_rejected():
    module = verifier()
    from kipy.proto.common.types import DocumentSpecifier, DocumentType
    expected = Path("/home/dev/PCB_Harness/fixtures/capability/board.kicad_pcb")
    doc = DocumentSpecifier(type=DocumentType.DOCTYPE_PCB, board_filename=str(expected))
    with pytest.raises(ValueError):
        module.select_document([doc, doc], expected)


@pytest.mark.parametrize('key',['clearance','shorting_items','track_width','unconnected_items','schematic_parity'])
def test_ignored_essential_check_is_verification_failure(key):
    report=drc();report['ignored_checks']=[{'key':key,'description':'disabled'}]
    with pytest.raises(ValueError):verifier().parse_report(report,'drc','board.kicad_pcb',0)


def test_known_initial_ignored_checks_are_explicitly_allowed():
    report=drc();report['ignored_checks']=[{'key':'missing_courtyard','description':'default fixture check'}]
    result=verifier().parse_report(report,'drc','board.kicad_pcb',0)
    assert result['passed'] and result['ignored_checks']
