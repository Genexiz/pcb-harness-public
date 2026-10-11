from pathlib import Path
import json

import pytest


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "runs/routing/m2-2026-10-09-r3"


def test_m2_docs_match_local_aggregate_report():
    report_path = CAMPAIGN / "report.json"
    if not report_path.exists():
        pytest.skip("local ignored M2 campaign evidence is unavailable")
    report = json.loads(report_path.read_text())
    progress = (ROOT / "docs/capabilities/m2-progress.md").read_text()
    roadmap = (ROOT / "PCB Harness — Development Roadmap.md").read_text()
    readme = (ROOT / "README.md").read_text()
    mcp = (ROOT / "docs/mcp.md").read_text()

    assert f'{report["passed_runs"]}/5' in progress
    assert ("Gate: PASS" if report["gate_passed"] else "Gate: FAIL") in progress
    assert "Provider tokens: unavailable" in progress
    assert "Provider cost: unavailable" in progress
    assert "m2-2026-10-09-r3" in progress
    for document in (roadmap, readme, mcp):
        assert f'{report["passed_runs"]}/5' in document
        assert "m2-2026-10-09-r3" in document
