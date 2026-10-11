from pathlib import Path
import json
import subprocess
import shutil
import re
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/capability/board.kicad_pcb"
CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


def test_fixture_has_real_erc_clean_schematic(tmp_path):
    schematic = FIXTURE.with_suffix(".kicad_sch")
    assert schematic.exists(), "three-resistor schematic fixture not generated"
    report = tmp_path / "erc.json"
    result = subprocess.run([str(CLI), "sch", "erc", "--format", "json",
        "--severity-all", "--exit-code-violations", "-o", str(report),
        str(schematic)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr + result.stdout
    assert all(s["violations"] == [] for s in json.loads(report.read_text())["sheets"])


def test_fixture_has_real_drc_and_schematic_parity(tmp_path):
    assert FIXTURE.exists(), "three-resistor PCB fixture not generated"
    report = tmp_path / "drc.json"
    result = subprocess.run([str(CLI), "pcb", "drc", "--format", "json",
        "--severity-all", "--schematic-parity", "--exit-code-violations",
        "-o", str(report), str(FIXTURE)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr + result.stdout
    data = json.loads(report.read_text())
    assert data["violations"] == []
    assert data["unconnected_items"] == []
    assert data["schematic_parity"] == []


@pytest.mark.parametrize("variant,expected_type", [
    ("short", "shorting_items"), ("clearance", "clearance"),
    ("width", "track_width"), ("open", "unconnected_items"),
    ("parity", "net_conflict")])
def test_known_bad_board_is_rejected_by_real_kicad(tmp_path, variant, expected_type):
    dst = tmp_path / "fixture"
    shutil.copytree(FIXTURE.parent, dst)
    board = dst / FIXTURE.name
    body = board.read_text()
    if variant == "short":
        extra = '(segment (start 19 20) (end 21 20) (width 0.4) (layer "F.Cu") (net 1))'
        body = body.rstrip()[:-1] + extra + ')\n'
    elif variant == "clearance":
        extra = '(segment (start 21 20) (end 19.5 18) (width 0.4) (layer "F.Cu") (net 2))'
        body = body.rstrip()[:-1] + extra + ')\n'
    elif variant == "width":
        body = body.replace('(width 0.4)', '(width 0.1)', 1)
    elif variant == "open":
        body = re.sub(r'^\(segment \(start 19 15\).*\n', '', body, flags=re.MULTILINE)
    elif variant == "parity":
        body = body.replace('(net 1 "/NET_A") (pinfunction', '(net 2 "/NET_B") (pinfunction', 1)
    board.write_text(body)
    report = tmp_path / "bad-drc.json"
    result = subprocess.run([str(CLI), "pcb", "drc", "--format", "json",
        "--severity-all", "--schematic-parity", "--exit-code-violations",
        "-o", str(report), str(board)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 5, result.stdout + result.stderr[-500:]
    data = json.loads(report.read_text())
    if expected_type == "unconnected_items":
        assert data["unconnected_items"]
    else:
        assert expected_type in {v["type"] for section in ("violations", "unconnected_items", "schematic_parity") for v in data[section]}


def test_known_bad_output_conflict_is_rejected_by_real_erc(tmp_path):
    dst = tmp_path / "fixture"
    shutil.copytree(FIXTURE.parent, dst)
    schematic = dst / "board.kicad_sch"
    schematic.write_text(schematic.read_text().replace('(pin passive line', '(pin output line'))
    report = tmp_path / "bad-erc.json"
    result = subprocess.run([str(CLI), "sch", "erc", "--format", "json",
        "--severity-all", "--exit-code-violations", "-o", str(report),
        str(schematic)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 5, result.stdout + result.stderr[-500:]
    issues = [v for s in json.loads(report.read_text())["sheets"] for v in s["violations"]]
    assert any(v["type"] == "pin_to_pin" for v in issues)


def test_custom_width_rule_enforces_without_global_width_floor(tmp_path):
    dst = tmp_path / "fixture"
    shutil.copytree(FIXTURE.parent, dst)
    board = dst / FIXTURE.name
    board.write_text(board.read_text().replace('(width 0.4)', '(width 0.1)', 1))
    project = dst / "board.kicad_pro"
    config = json.loads(project.read_text())
    config["board"]["design_settings"]["rules"]["min_track_width"] = 0.01
    project.write_text(json.dumps(config))
    report = tmp_path / "custom-only.json"
    result = subprocess.run([str(CLI), "pcb", "drc", "--format", "json",
        "--severity-all", "--exit-code-violations", "-o", str(report), str(board)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 5
    assert any(v["type"] == "track_width" and "0.2000 mm" in v["description"]
               for v in json.loads(report.read_text())["violations"])


def test_netclass_default_width_is_not_a_minimum_constraint(tmp_path):
    dst = tmp_path / "fixture"
    shutil.copytree(FIXTURE.parent, dst)
    board = dst / FIXTURE.name
    board.write_text(board.read_text().replace('(width 0.4)', '(width 0.25)', 1))
    report = tmp_path / "above-minimum.json"
    result = subprocess.run([str(CLI), "pcb", "drc", "--format", "json",
        "--severity-all", "--exit-code-violations", "-o", str(report), str(board)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert json.loads(report.read_text())["violations"] == []
