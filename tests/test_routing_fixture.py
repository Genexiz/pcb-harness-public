from pathlib import Path
import json
import subprocess

from eval.routing_smoke.fixture import fixture_hashes, load_benchmark
from pcb_harness.initial_rules import validate_probe_rules


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "fixtures/routing/tiny"
FIXTURE = FIXTURE_ROOT / "board.kicad_pcb"
CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


def run_drc(board, report):
    result = subprocess.run(
        [str(CLI), "pcb", "drc", "--format", "json", "--severity-all",
         "--schematic-parity", "--exit-code-violations", "-o", str(report), str(board)],
        capture_output=True, text=True, timeout=30,
    )
    return result, json.loads(report.read_text()) if report.exists() else None


def test_tiny_routing_fixture_is_complete_unrouted_and_frozen():
    benchmark = load_benchmark(FIXTURE_ROOT / "benchmark.json")

    assert benchmark["schema_version"] == 1
    assert benchmark["board"] == "board.kicad_pcb"
    assert benchmark["refs"] == ["R1", "R2", "R3"]
    assert benchmark["nets"] == ["/NET_A", "/NET_B"]
    assert benchmark["initial_track_count"] == 0
    assert benchmark["initial_via_count"] == 0
    assert benchmark["min_host_placement_actions"] == 1
    assert fixture_hashes(FIXTURE_ROOT) == benchmark["sha256"]


def test_real_kicad_accepts_geometry_and_parity_but_reports_unconnected_input(tmp_path):
    result, report = run_drc(FIXTURE, tmp_path / "drc.json")

    assert result.returncode == 5, result.stdout + result.stderr
    assert report["violations"] == []
    assert report["schematic_parity"] == []
    assert report["unconnected_items"]


def test_tiny_routing_fixture_uses_the_native_accepted_rule_subset():
    assert validate_probe_rules(FIXTURE.with_suffix(".kicad_dru"))["passed"] is True
