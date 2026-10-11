from pathlib import Path
import json
import shutil

import pytest

from eval.routing_smoke.prepare import prepare_campaign
from eval.routing_smoke.score import score_campaign, score_run
from eval.routing_smoke.session import HOST_DISCLOSURE
from pcb_harness.native_reports import parse_report


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/routing/tiny"


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


class EvidenceFactory:
    def __init__(self, root):
        self.root = root
        self.counter = 0

    def _populate(self, run, *, placement_actions=1, route_actions=2, attempts=None,
                  elapsed=35, native=True, change=None):
        manifest = json.loads((run / "manifest.json").read_text())
        project = (run / manifest["board"]).resolve()
        evidence = run / "service/native/verify-final"
        evidence.mkdir(parents=True)
        issue = {"type": "clearance", "severity": "error", "description": "bad", "items": []}
        unconnected = {"type": "unconnected_items", "severity": "error", "description": "open", "items": []}
        parity = {"type": "net_conflict", "severity": "error", "description": "parity", "items": []}
        drc = {
            "$schema": "https://schemas.kicad.org/drc.v1.json",
            "source": "board.kicad_pcb",
            "kicad_version": "10.0.6",
            "coordinate_units": "mm",
            "included_severities": ["error", "warning", "exclusion"],
            "ignored_checks": [{"key": "missing_courtyard", "description": "fixture"}],
            "violations": [issue] if change == "geometric_issue" else [],
            "unconnected_items": [unconnected] if change == "unconnected" else [],
            "schematic_parity": [parity] if change == "parity_issue" else [],
        }
        (evidence / "drc.json").write_text(json.dumps(drc) + "\n")
        for relative in manifest["fixture_sha256"]:
            target = evidence / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project.parent / relative, target)
        exit_code = 5 if any(drc[key] for key in
            ("violations", "unconnected_items", "schematic_parity")) else 0
        native_result = {**parse_report(drc, "drc", project.name, exit_code),
            "exit_code": exit_code, "command": ["kicad-cli", "pcb", "drc",
                "--format", "json", "--severity-all", "--exit-code-violations",
                "--schematic-parity", "-o", str(evidence / "drc.json"),
                str(evidence / project.name)]}
        (evidence / "result.json").write_text(json.dumps(native_result))

        actions = [("pcb_create_checkpoint", {"name": "baseline", "expected_revision": "r0"})]
        for number in range(placement_actions):
            actions.append(("pcb_execute", {
                "action": "move_footprint", "args": {"ref": "R1", "dx_mm": 0, "dy_mm": 0},
                "expected_revision": f"r{number}", "action_id": f"place-{number}", "mode": "strict",
            }))
        for number in range(route_actions):
            actions.append(("pcb_execute", {
                "action": "route_track", "args": {"net": "/NET_A", "layer": "F.Cu",
                    "points_mm": [[19, 20], [19, 15]], "width_mm": 0.4},
                "expected_revision": f"p{number}", "action_id": f"route-{number}", "mode": "strict",
            }))
        if attempts is not None:
            while len(actions) < attempts:
                number = len(actions)
                actions.append(("pcb_execute", {
                    "action": "route_track", "args": {"net": "/NET_A", "layer": "F.Cu",
                        "points_mm": [[19, 20], [19, 15]], "width_mm": 0.4},
                    "expected_revision": f"x{number}", "action_id": f"extra-{number}", "mode": "strict",
                }))

        budget = {"max_actions": 300, "max_duration_seconds": 1200,
            "attempts_used": len(actions), "attempts_remaining": max(0, 300 - len(actions)),
            "started_at": 1000, "elapsed_seconds": elapsed,
            "deadline_reached": elapsed >= 1200, "evidence_error": None}
        backend = "kicad" if native else "memory"
        transcript = []
        def add(tool, arguments, result, is_error=False):
            transcript.append({"schema_version": 1, "sequence": len(transcript) + 1,
                "tool": tool, "arguments": arguments, "result": result,
                "is_error": is_error, "host": HOST_DISCLOSURE, "recorded_at": 1000 + len(transcript)})
        add("pcb_connect", {}, {"ok": True, "backend": backend,
            "native_editing_enabled": native, "recovery_required": False,
            "project": str(project) if native else None, "run_budget": budget})
        add("pcb_summary", {}, {"ok": True, "backend": backend,
            "server_version": "10.0.6 (10.0.6)" if native else None,
            "recovery_required": False, "run_budget": budget})
        for index, (tool, arguments) in enumerate(actions, start=1):
            add(tool, arguments, {"ok": True, "backend": backend, "revision": f"r{index}",
                "replayed": False, "rolled_back": False,
                "recovery_required": change == "recovery_required",
                "run_budget": {**budget, "attempts_used": index,
                    "attempts_remaining": max(0, 300 - index)}})
        add("pcb_verify_geometry", {}, {"ok": True, "backend": backend,
            "revision": f"r{len(actions)}",
            "geometric": [issue] if change == "geometric_issue" else [],
            "connectivity": [unconnected] if change == "unconnected" else [],
            "ignored_checks": drc["ignored_checks"], "evidence": str(evidence),
            "recovery_required": change == "recovery_required", "run_budget": budget})
        add("pcb_summary", {}, {"ok": True, "backend": backend,
            "revision": f"r{len(actions)}",
            "server_version": "10.0.6 (10.0.6)" if native else None,
            "recovery_required": change == "recovery_required", "run_budget": budget})
        if change == "stale_final_verification":
            verification = transcript.pop(-2)
            transcript.insert(2, verification)
            for sequence, row in enumerate(transcript, start=1):
                row["sequence"] = sequence
        jsonl(run / "host-transcript.jsonl", transcript)

        ledger = [{"phase": "config", "schema_version": 1,
            "identity": {"workspace": str(ROOT), "backend": "kicad", "project": str(project)},
            "max_actions": 300, "max_duration_seconds": 1200}]
        for index, (tool, arguments) in enumerate(actions, start=1):
            operation = {"pcb_create_checkpoint": "create_checkpoint",
                         "pcb_restore_checkpoint": "restore_checkpoint"}.get(tool, "execute")
            ledger.append({"phase": "started", "attempt": index, "operation": operation,
                "action_id": arguments.get("action_id"), "wall_time": 1000 + index,
                "elapsed_seconds": min(elapsed, index), "monotonic_time": index,
                "boot_id": "00000000-0000-0000-0000-000000000001"})
            ledger.append({"phase": "finished", "attempt": index,
                "wall_time": 1000 + index + 0.5,
                "elapsed_seconds": elapsed if index == len(actions) else min(elapsed, index + 0.5),
                "clock_error": None, "ok": True, "error_code": None,
                "replayed": False, "rolled_back": False,
                "recovery_required": change == "uncertain_write" and index == 1,
                "revision": f"r{index}"})
        jsonl(run / "service/run.jsonl", ledger)

        if change == "missing_transcript":
            (run / "host-transcript.jsonl").unlink()
        elif change == "corrupt_budget":
            with (run / "service/run.jsonl").open("a") as stream:
                stream.write("{broken\n")
        elif change == "fixture_hash_mismatch":
            board = run / "input/board.kicad_pcb"
            board.write_text(board.read_text() + "\n")
        return run

    def __call__(self, *, clean=True, placement_actions=1, route_actions=2,
                 attempts=4, elapsed=35, native=True, change=None):
        self.counter += 1
        campaign = self.root / f"single-{self.counter}"
        run = prepare_campaign(FIXTURE, campaign, repeats=1)[0]
        if not clean and change is None:
            change = "geometric_issue"
        if change == "no_placement":
            placement_actions = 0
        if change == "no_route":
            route_actions = 0
            attempts = None
        if change == "memory_backend":
            native = False
        if change == "over_300_attempts":
            attempts = 301
        if change == "over_1200_seconds":
            elapsed = 1201
        return self._populate(run, placement_actions=placement_actions,
            route_actions=route_actions, attempts=attempts, elapsed=elapsed,
            native=native, change=change)

    def campaign(self, outcomes):
        self.counter += 1
        campaign = self.root / f"campaign-{self.counter}"
        runs = prepare_campaign(FIXTURE, campaign, repeats=len(outcomes))
        for run, passed in zip(runs, outcomes):
            self._populate(run, change=None if passed else "unconnected")
        return campaign


@pytest.fixture
def evidence_factory(tmp_path):
    return EvidenceFactory(tmp_path)


def test_run_pass_requires_native_clean_route_placement_and_envelope(evidence_factory):
    run = evidence_factory(clean=True, placement_actions=1, route_actions=2,
                           attempts=4, elapsed=35, native=True)
    score = score_run(run)
    assert score["passed"] is True
    assert score["mandatory_drc_clean"] is True
    assert score["zero_unconnected"] is True
    assert score["circuit_parity_clean"] is True
    assert score["attempts_used"] == 4
    assert score["elapsed_seconds"] == 35


@pytest.mark.parametrize("change", [
    "missing_transcript", "corrupt_budget", "fixture_hash_mismatch", "no_placement",
    "no_route", "memory_backend", "geometric_issue", "unconnected", "parity_issue",
    "over_300_attempts", "over_1200_seconds", "recovery_required", "uncertain_write",
])
def test_run_fails_closed_for_missing_or_out_of_gate_evidence(evidence_factory, change):
    score = score_run(evidence_factory(change=change))
    assert score["passed"] is False
    assert score["failures"]


def test_campaign_keeps_all_failures_and_requires_three_of_five(evidence_factory):
    campaign = evidence_factory.campaign([True, True, True, False, False])
    report = score_campaign(campaign)
    assert report["gate_passed"] is True
    assert report["passed_runs"] == 3
    assert len(report["runs"]) == 5
    assert sum(not run["passed"] for run in report["runs"]) == 2
    assert json.loads((campaign / "report.json").read_text()) == report


def test_pre_write_verification_cannot_set_final_clean_criteria(evidence_factory):
    score = score_run(evidence_factory(change="stale_final_verification"))
    assert score["passed"] is False
    assert score["mandatory_drc_clean"] is False
    assert score["zero_unconnected"] is False
    assert score["circuit_parity_clean"] is False


def test_campaign_rejects_wrong_repeat_count(evidence_factory):
    campaign = evidence_factory.campaign([True, True, True, False])
    report = score_campaign(campaign)
    assert report["gate_passed"] is False
    assert report["passed_runs"] == 3
    assert len(report["runs"]) == 4
    assert report["runs"][-1]["passed"] is False
    assert report["failures"] == ["expected 5 runs; found 4"]
    assert report["missing_runs"] == ["run-5"]
    assert report["unexpected_runs"] == []


@pytest.mark.parametrize("relative", ["board.kicad_pcb", "board.kicad_sch", "board.kicad_dru"])
def test_final_project_drift_fails_scoring(evidence_factory, relative):
    run = evidence_factory()
    (run / "project" / relative).write_text("changed after verification\n")
    assert score_run(run)["passed"] is False


@pytest.mark.parametrize("change", ["missing_result", "bad_exit", "wrong_command", "missing_snapshot"])
def test_native_evidence_requires_real_execution_and_bound_snapshot(evidence_factory, change):
    run = evidence_factory()
    evidence = run / "service/native/verify-final"
    if change == "missing_result":
        (evidence / "result.json").unlink()
    elif change == "missing_snapshot":
        (evidence / "board.kicad_pcb").unlink()
    else:
        result = json.loads((evidence / "result.json").read_text())
        if change == "bad_exit":
            result["exit_code"] = 2
        else:
            result["command"].remove("--schematic-parity")
        (evidence / "result.json").write_text(json.dumps(result))
    assert score_run(run)["passed"] is False


@pytest.mark.parametrize("change", ["outcome", "action_id", "operation", "revision"])
def test_contradictory_ledger_and_transcript_fail_closed(evidence_factory, change):
    run = evidence_factory()
    ledger_path = run / "service/run.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    if change == "outcome":
        rows[4].update(ok=False, rolled_back=True, error_code="STALE_REVISION")
    elif change == "action_id":
        rows[3]["action_id"] = "different-host-action"
    elif change == "operation":
        rows[3]["operation"] = "restore_checkpoint"
    else:
        rows[4]["revision"] = "different-revision"
    jsonl(ledger_path, rows)
    assert score_run(run)["passed"] is False


@pytest.mark.parametrize("change", ["missing_clock", "clock_error", "boot_changed", "wall_backward", "mono_backward"])
def test_incomplete_or_invalid_clock_evidence_fails_closed(evidence_factory, change):
    run = evidence_factory()
    ledger_path = run / "service/run.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    if change == "missing_clock":
        for row in rows[1:]:
            for key in ("wall_time", "monotonic_time", "boot_id", "clock_error"):
                row.pop(key, None)
    elif change == "clock_error":
        rows[2]["clock_error"] = "wall clock moved backward"
    elif change == "boot_changed":
        rows[3]["boot_id"] = "00000000-0000-0000-0000-000000000002"
    elif change == "wall_backward":
        rows[3]["wall_time"] = 0
    else:
        rows[3]["monotonic_time"] = 0
    jsonl(ledger_path, rows)
    assert score_run(run)["passed"] is False


def test_consistent_rejected_attempt_is_retained_without_discarding_later_success(evidence_factory):
    run = evidence_factory(attempts=5)
    ledger_path = run / "service/run.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    rows[10].update(ok=False, error_code="STALE_REVISION", revision=None)
    jsonl(ledger_path, rows)
    transcript_path = run / "host-transcript.jsonl"
    calls = [json.loads(line) for line in transcript_path.read_text().splitlines()]
    calls[6]["result"].update(ok=False, error_code="STALE_REVISION", revision=None)
    calls[6]["is_error"] = True
    # Final verification describes the last successful accepted action.
    for call in calls[-2:]:
        call["result"]["revision"] = "r4"
    jsonl(transcript_path, calls)
    score = score_run(run)
    assert score["passed"] is True
    assert score["attempts_used"] == 5
    assert score["action_failure_codes"] == ["STALE_REVISION"]


def test_campaign_rejects_unexpected_run_names_but_keeps_results(evidence_factory):
    campaign = evidence_factory.campaign([True] * 5)
    (campaign / "run-5").rename(campaign / "run-6")
    report = score_campaign(campaign)
    assert report["gate_passed"] is False
    assert len(report["runs"]) == 5
    assert any("run-5" in failure and "run-6" in failure for failure in report["failures"])
