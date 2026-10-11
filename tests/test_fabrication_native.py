from pathlib import Path
from copy import deepcopy
import json
import shutil
import pytest
from pcb_harness.fabrication.compiler import compile_rules
from pcb_harness.native_reports import run_verification

ROOT = Path(__file__).resolve().parents[1]
CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


@pytest.mark.parametrize("order", ["generic_last", "generic_first", "weaker_net_last"])
def test_overlapping_width_rules_enforce_strictest_minimum(profile_case, tmp_path, order):
    if not CLI.exists():
        pytest.skip("native KiCad CLI is unavailable")
    profile, facts, constraints = profile_case()
    generic = constraints["constraints"][0]
    strict = {**deepcopy(generic), "id": "power-width", "scope": "net:/NET_A", "value": 0.8}
    weak = {**deepcopy(strict), "id": "weak-power-width", "value": 0.3}
    constraints["constraints"] = {
        "generic_last": [strict, generic], "generic_first": [generic, strict],
        "weaker_net_last": [strict, weak, generic],
    }[order]
    output = tmp_path / "native"
    shutil.copytree(ROOT / "fixtures/capability", output)
    compiled = compile_rules(profile, constraints)
    (output / "board.kicad_pro").write_text(json.dumps(compiled["settings"]))
    (output / "board.kicad_dru").write_text(compiled["rules"])
    board = output / "board.kicad_pcb"
    result = run_verification(CLI, "drc", board, output / "narrow-drc.json")
    assert result["status"] == "verified", result
    assert any(issue["type"] == "track_width" and "0.8000" in issue["description"]
        for issue in result["issues"]), result
    board.write_text(board.read_text().replace("(width 0.4)", "(width 0.8)"))
    result = run_verification(CLI, "drc", board, output / "wide-drc.json")
    assert not any(issue["type"] == "track_width" for issue in result["issues"]), result


@pytest.mark.parametrize("variant,rule", [("positive", None), ("width", "track_width"),
    ("clearance", "clearance"), ("drill", "via_drill"), ("diameter", "via_diameter"),
    ("annular", "annular_ring"), ("hole_clearance", "inner_drill_clearance"),
    ("hole_spacing", "hole_to_hole"), ("edge", "copper_edge")])
def test_compiled_rules_enforced_by_native_cli(profile_case, tmp_path, variant, rule):
    if not CLI.exists():
        pytest.skip("native KiCad CLI is unavailable")
    output = tmp_path / "native"
    shutil.copytree(ROOT / "fixtures/capability", output)
    profile, facts, constraints = profile_case()
    constraints["constraints"] = []
    if variant == "hole_clearance":
        # Isolate drill-to-inner-copper from the earlier annular-copper test.
        next(category for category in profile["categories"] if category["id"] == "clearance")["design_target"] = 0.01
    compiled = compile_rules(profile, constraints)
    config = compiled["settings"]
    # Custom constraints must still work when broad project minima are relaxed.
    config["board"]["design_settings"]["rules"] = {"min_clearance": 0.01, "min_track_width": 0.01,
        "min_through_hole_diameter": 0.01, "min_via_diameter": 0.01, "min_copper_edge_clearance": 0.01}
    (output / "board.kicad_pro").write_text(json.dumps(config))
    (output / "board.kicad_dru").write_text(compiled["rules"])
    board = output / "board.kicad_pcb"
    text = board.read_text()
    extra = ""
    if variant == "width":
        text = text.replace("(width 0.4)", "(width 0.1)", 1)
    elif variant == "clearance":
        extra = '(segment (start 21 20) (end 19.5 18) (width 0.4) (layer "F.Cu") (net 2))'
    elif variant == "drill":
        text = text.replace("(drill 0.3)", "(drill 0.2)", 1)
    elif variant == "diameter":
        text = text.replace("(size 0.6)", "(size 0.5)", 1)
    elif variant == "annular":
        text = text.replace("(drill 0.3)", "(drill 0.4)", 1)
    elif variant == "hole_clearance":
        text = text.replace('(2 "B.Cu" signal)', '(4 "In1.Cu" signal) (6 "In2.Cu" signal) (2 "B.Cu" signal)')
        extra = '(segment (start 21.5 24) (end 21.5 26) (width 0.2) (layer "In1.Cu") (net 1))'
    elif variant == "hole_spacing":
        extra = '(via (at 21.5 25) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 2))'
    elif variant == "edge":
        extra = '(segment (start 10.3 12) (end 10.3 16) (width 0.4) (layer "F.Cu") (net 1))'
    board.write_text(text.rstrip()[:-1] + extra + ')\n')
    result = run_verification(CLI, "drc", board, output / "native-drc.json")
    assert result["status"] == "verified", result
    if rule is None:
        assert result["passed"] is True, result
    else:
        assert result["passed"] is False
        assert any(f"M3 {rule}" in issue["description"] for issue in result["issues"]), result
