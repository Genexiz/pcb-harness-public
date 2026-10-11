from pathlib import Path
import json
import pytest
from pcb_harness.circuit.writer import write_project
from pcb_harness.circuit.bootstrap import verify_bootstrap, parse_native_netlist
from pcb_harness.circuit.bundle import sha256

CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


@pytest.mark.parametrize("missing", ["board.kicad_pro", "board.kicad_dru", "circuit-review.json",
    "fabrication-review.json", "rule-compilation.json", "inputs/circuit.json", "sym-lib-table"])
def test_manifest_cannot_omit_required_bootstrap_evidence(valid_bundle, tmp_path, missing):
    bundle, root = valid_bundle
    output = tmp_path / "runs/bootstrap"
    write_project(bundle, root, bundle["checklist"], output)
    manifest_path = output / "bootstrap-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["output_sha256"][missing]
    manifest_path.write_text(json.dumps(manifest))
    result = verify_bootstrap(output / "board.kicad_pcb", CLI)
    assert result["accepted"] is False, result
    assert any("required bootstrap" in failure for failure in result["failures"]), result


@pytest.mark.parametrize("report", ["circuit-review.json", "fabrication-review.json"])
def test_failed_upstream_report_blocks_bootstrap_even_with_updated_hash(valid_bundle, tmp_path, report):
    bundle, root = valid_bundle
    output = tmp_path / "runs/bootstrap"
    write_project(bundle, root, bundle["checklist"], output)
    report_path = output / report
    data = json.loads(report_path.read_text())
    data["passed"] = False
    report_path.write_text(json.dumps(data))
    manifest_path = output / "bootstrap-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["output_sha256"][report] = sha256(report_path)
    manifest_path.write_text(json.dumps(manifest))
    result = verify_bootstrap(output / "board.kicad_pcb", CLI)
    assert result["accepted"] is False, result
    assert any("upstream" in failure for failure in result["failures"]), result


def test_native_evidence_symlink_cannot_write_outside_project(valid_bundle, tmp_path):
    if not CLI.exists():
        pytest.skip("native CLI unavailable")
    bundle, root = valid_bundle
    output = tmp_path / "runs/bootstrap"
    write_project(bundle, root, bundle["checklist"], output)
    outside = tmp_path / "outside"
    outside.mkdir()
    (output / "native").symlink_to(outside, target_is_directory=True)
    result = verify_bootstrap(output / "board.kicad_pcb", CLI)
    assert list(outside.iterdir()) == []
    assert result["accepted"] is False


def test_native_bootstrap_has_clean_erc_parity_and_unrouted_connectivity(valid_bundle, tmp_path):
    if not CLI.exists():
        pytest.skip("native CLI unavailable")
    bundle, root = valid_bundle
    output = tmp_path / "runs/bootstrap"
    write_project(bundle, root, bundle["checklist"], output)
    result = verify_bootstrap(output / "board.kicad_pcb", CLI)
    assert result["accepted"] is True, result
    assert result["erc_clean"] is True
    assert result["parity_clean"] is True
    assert result["zero_unconnected"] is False
    assert result["routed"] is False
    assert result["release_eligible"] is False
    assert result["netlist_matches"] is True


def test_missing_cli_never_reuses_stale_report(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    output = tmp_path / "runs/bootstrap"
    write_project(bundle, root, bundle["checklist"], output)
    (output / "drc.json").write_text('{"violations": []}')
    result = verify_bootstrap(output / "board.kicad_pcb", tmp_path / "no-cli")
    assert result["accepted"] is False


def test_post_write_project_drift_rejected(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    output = tmp_path / "runs/bootstrap"
    write_project(bundle, root, bundle["checklist"], output)
    (output / "board.kicad_pcb").write_text("not a PCB")
    assert verify_bootstrap(output / "board.kicad_pcb", CLI)["accepted"] is False


def test_exported_netlist_endpoints_are_read_independently(tmp_path):
    path = tmp_path / "netlist.xml"
    path.write_text('<export><nets><net name="/NET_A"><node ref="R1" pin="2"/></net></nets></export>')
    assert parse_native_netlist(path) == {"/NET_A": {("R1", "2")}}


def test_native_intentional_no_connect_is_not_a_missing_pin(valid_bundle, tmp_path):
    if not CLI.exists():
        pytest.skip("native CLI unavailable")
    bundle, root = valid_bundle
    endpoint = {"instance_id":"r3","pin_id":"p2"}
    bundle["circuit"]["nets"][1]["endpoints"].remove(endpoint)
    bundle["circuit"]["no_connect"] = [{**endpoint,"reason":"synthetic independent NC probe","fact_id":"fixture"}]
    bundle["checklist"]["no_connect"] = [endpoint]
    del bundle["checklist"]["expected_instances"][2]["pin_nets"]["2"]
    output = tmp_path / "runs/nc"
    write_project(bundle, root, bundle["checklist"], output)
    result = verify_bootstrap(output/"board.kicad_pcb",CLI)
    assert result["accepted"] is True, result


def test_valid_close_caller_positions_keep_two_native_nets(valid_bundle,tmp_path):
    import subprocess
    if not CLI.exists():pytest.skip('native CLI unavailable')
    bundle,root=valid_bundle
    for i,pos in zip(bundle['circuit']['instances'],[[50.8,50.8],[50.8,63.5],[101.6,50.8]]):
        i['schematic_position_mm']=pos
    output=tmp_path/'runs/close-native';write_project(bundle,root,bundle['checklist'],output)
    netlist=output/'netlist.xml'
    result=subprocess.run([str(CLI),'sch','export','netlist','--format','kicadxml','--output',str(netlist),str(output/'board.kicad_sch')],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert parse_native_netlist(netlist)=={'/NET_A':{('R1','1'),('R2','1'),('R3','1')},
                                          '/NET_B':{('R1','2'),('R2','2'),('R3','2')}}
