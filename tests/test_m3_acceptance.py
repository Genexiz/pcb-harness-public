from pathlib import Path
import json
import pytest
from eval.circuit_smoke.run import run_acceptance,verify_acceptance_report

CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


def test_acceptance_preserves_all_known_bad_results(valid_bundle, tmp_path):
    if not CLI.exists():
        pytest.skip("native CLI unavailable")
    bundle, root = valid_bundle
    result = run_acceptance(root, root/"checklist.json", tmp_path/"runs/m3",CLI)
    assert result["gate_passed"] is True, result
    assert set(result["circuit_negatives"]) == {"wrong_pinout","wrong_footprint","missing_interface",
        "voltage_mismatch","ignored_errata","duplicate_ref","no_connect_mismatch","native_usb_can_concurrent"}
    assert all(case["rejected"] for case in result["circuit_negatives"].values())
    assert len(result["fabrication_negatives"]) == 8
    assert result["release_eligible"] is False
    assert json.loads((tmp_path/"runs/m3/report.json").read_text())["gate_passed"] is True
    assert verify_acceptance_report(tmp_path/"runs/m3") is True
    (tmp_path/"runs/m3/report.json").write_text('{"gate_passed":false}')
    assert verify_acceptance_report(tmp_path/"runs/m3") is False


def test_failed_native_positive_preserves_negative_evidence(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    result = run_acceptance(root,root/"checklist.json",tmp_path/"runs/failed",tmp_path/"missing-cli")
    assert result["gate_passed"] is False
    assert len(result["circuit_negatives"]) == 8
    assert result["failures"]


def test_acceptance_refuses_existing_run_without_overwrite(valid_bundle,tmp_path):
    bundle,root=valid_bundle
    output=tmp_path/"runs/existing"
    output.mkdir(parents=True)
    (output/"sentinel").write_text("retained")
    with pytest.raises(FileExistsError):
        run_acceptance(root,root/"checklist.json",output,CLI)
    assert (output/"sentinel").read_text()=="retained"


def test_tampered_source_cannot_pass_acceptance(valid_bundle,tmp_path):
    bundle,root=valid_bundle
    (root/"sources/fixture-design.md").write_text("unreviewed replacement")
    report=run_acceptance(root,root/"checklist.json",tmp_path/"runs/tampered",tmp_path/"no-cli")
    assert report["implementation_gate"] is False
    assert report["gate_passed"] is False


def test_accepted_negative_closes_specific_gate(valid_bundle,tmp_path,monkeypatch):
    from eval.circuit_smoke import run
    original=run.review_circuit
    def wrong_verifier(bundle,root,checklist):
        result=original(bundle,root,checklist)
        if any(issue["code"]=="PINOUT_MISMATCH" for issue in result["issues"]):
            result["passed"]=True
        return result
    monkeypatch.setattr(run,"review_circuit",wrong_verifier)
    bundle,root=valid_bundle
    report=run_acceptance(root,root/"checklist.json",tmp_path/"runs/bad-verifier",tmp_path/"no-cli")
    assert report["circuit_negative_gate"] is False
    assert report["circuit_negatives"]["wrong_pinout"]["rejected"] is False
