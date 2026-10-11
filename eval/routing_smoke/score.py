from pathlib import Path
import argparse
import json
import math
import uuid

from pcb_harness.native_reports import ALLOWED_IGNORED, parse_report
from .fixture import fixture_hashes, load_benchmark
from .session import HOST_DISCLOSURE


MANIFEST_FIELDS = {
    "schema_version", "run_id", "repeat", "fixture", "fixture_sha256", "board",
    "input", "service_directory", "transcript", "max_actions",
    "max_duration_seconds", "prepared_at",
}
TRANSCRIPT_FIELDS = {
    "schema_version", "sequence", "tool", "arguments", "result", "is_error",
    "host", "recorded_at",
}
WRITE_TOOLS = {"pcb_execute", "pcb_create_checkpoint", "pcb_restore_checkpoint"}
PLACEMENT_ACTIONS = {"place_footprint", "move_footprint", "rotate_footprint", "flip_footprint"}
STARTED_FIELDS = {"phase", "attempt", "operation", "action_id", "wall_time",
    "elapsed_seconds", "monotonic_time", "boot_id"}
FINISHED_FIELDS = {"phase", "attempt", "wall_time", "elapsed_seconds", "clock_error",
    "ok", "error_code", "replayed", "rolled_back", "recovery_required", "revision"}


def _read_json(path: Path):
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain an object")
    return data


def _read_jsonl(path: Path):
    text = path.read_text()
    if not text.endswith("\n"):
        raise ValueError(f"{path.name} is incomplete")
    rows = [json.loads(line) for line in text.splitlines()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path.name} has no complete object rows")
    return rows


def _finite_number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _latest(rows, tool):
    matches = [row for row in rows if row["tool"] == tool]
    if not matches:
        raise ValueError(f"missing {tool}")
    return matches[-1]


def _parse_transcript(path: Path):
    rows = _read_jsonl(path)
    for sequence, row in enumerate(rows, start=1):
        if set(row) != TRANSCRIPT_FIELDS or row["schema_version"] != 1:
            raise ValueError("unsupported transcript row")
        if row["sequence"] != sequence:
            raise ValueError("transcript sequence is not contiguous")
        if not isinstance(row["tool"], str) or not isinstance(row["arguments"], dict):
            raise ValueError("malformed transcript command")
        if not isinstance(row["result"], dict) or type(row["is_error"]) is not bool:
            raise ValueError("malformed transcript result")
        if row["host"] != HOST_DISCLOSURE:
            raise ValueError("host disclosure changed or is incomplete")
        _finite_number(row["recorded_at"], "recorded_at")
    return rows


def _parse_ledger(path: Path, project: Path):
    rows = _read_jsonl(path)
    config = rows[0]
    if (config.get("phase") != "config" or config.get("schema_version") != 1
            or config.get("max_actions") != 300
            or config.get("max_duration_seconds") != 1200):
        raise ValueError("run envelope config is not the frozen M2 envelope")
    identity = config.get("identity")
    if (not isinstance(identity, dict) or identity.get("backend") != "kicad"
            or Path(identity.get("project", "")).resolve() != project):
        raise ValueError("run envelope project identity mismatch")
    pending = None
    attempts = 0
    elapsed = 0.0
    outcomes = []
    admissions = []
    last_wall = None
    last_mono = None
    boot = None
    first_wall = None
    first_mono = None
    for row in rows[1:]:
        phase = row.get("phase")
        attempt = row.get("attempt")
        if phase == "started":
            if set(row) != STARTED_FIELDS:
                raise ValueError("incomplete admission clock/identity evidence")
            if pending is not None or type(attempt) is not int or attempt != attempts + 1:
                raise ValueError("nonsequential or overlapping admission")
            if row.get("operation") not in {"execute", "create_checkpoint", "restore_checkpoint"}:
                raise ValueError("unknown admitted operation")
            pending = attempt
            attempts = attempt
            mono = _finite_number(row["monotonic_time"], "monotonic_time")
            current_boot = str(uuid.UUID(row["boot_id"]))
            if last_mono is not None and (mono < last_mono or current_boot != boot):
                raise ValueError("run monotonic/boot evidence changed epoch")
            if first_mono is None:
                first_mono = mono
            last_mono, boot = mono, current_boot
            if row["action_id"] is not None and not isinstance(row["action_id"], str):
                raise ValueError("invalid admission action ID")
            admissions.append(row)
        elif phase == "finished":
            if set(row) != FINISHED_FIELDS or row["clock_error"] is not None:
                raise ValueError("incomplete or invalid outcome clock evidence")
            if pending is None or attempt != pending or type(row.get("ok")) is not bool:
                raise ValueError("unmatched run outcome")
            for key in ("replayed", "rolled_back", "recovery_required"):
                if type(row.get(key)) is not bool:
                    raise ValueError("run outcome omitted boolean evidence")
            for key in ("error_code", "revision"):
                if row[key] is not None and not isinstance(row[key], str):
                    raise ValueError("invalid outcome error/revision evidence")
            outcomes.append({key: row.get(key) for key in (
                "attempt", "ok", "error_code", "replayed", "rolled_back",
                "recovery_required", "revision")})
            pending = None
        else:
            raise ValueError("unknown run evidence phase")
        current = _finite_number(row.get("elapsed_seconds"), "elapsed_seconds")
        wall = _finite_number(row["wall_time"], "wall_time")
        if last_wall is not None and wall < last_wall:
            raise ValueError("run wall clock evidence moved backward")
        if first_wall is None:
            first_wall = wall
        if current < elapsed or current < 0:
            raise ValueError("run elapsed evidence moved backward")
        last_wall = wall
        elapsed = max(current, wall - first_wall, last_mono - first_mono)
    if pending is not None or len(outcomes) != attempts:
        raise ValueError("run has unfinished write evidence")
    if path.with_name(path.name + ".pending").exists():
        raise ValueError("run has unresolved durability marker")
    return attempts, elapsed, outcomes, admissions


def _raw_drc(path: Path, run: Path, project: Path, required_files: set[str]):
    evidence = path.resolve()
    native_root = (run / "service/native").resolve()
    if not evidence.is_relative_to(native_root) or evidence.is_symlink():
        raise ValueError("final verification evidence is outside this native run")
    report = _read_json(evidence / "drc.json")
    project_hashes = fixture_hashes(project.parent)
    if not required_files.issubset(project_hashes):
        raise ValueError("final project is missing required benchmark dependencies")
    if project_hashes != fixture_hashes(evidence):
        raise ValueError("final project differs from verified native snapshot")
    if not (evidence / project.name).is_file():
        raise ValueError("verified native board snapshot is missing")
    result = _read_json(evidence / "result.json")
    command = result.get("command")
    expected_args = ["pcb", "drc", "--format", "json", "--severity-all",
        "--exit-code-violations", "--schematic-parity", "-o",
        str(evidence / "drc.json"), str(evidence / project.name)]
    if (not isinstance(command, list) or len(command) != len(expected_args) + 1
            or not isinstance(command[0], str)
            or Path(command[0]).name != "kicad-cli" or command[1:] != expected_args):
        raise ValueError("native DRC execution command does not match snapshot/parity checks")
    parsed = parse_report(report, "drc", project.name, result.get("exit_code"))
    if result.get("status") != "verified" or any(result.get(key) != value for key, value in parsed.items()):
        raise ValueError("native execution result contradicts raw DRC report")
    if report.get("kicad_version") != "10.0.6":
        raise ValueError("raw DRC was not produced by exact KiCad 10.0.6")
    ignored = report.get("ignored_checks")
    if any(check.get("key") not in ALLOWED_IGNORED["drc"] for check in ignored):
        raise ValueError("raw DRC disabled an essential or unknown check")
    return report, parsed


def score_run(path: Path) -> dict:
    run = Path(path).resolve()
    score = {
        "schema_version": 1,
        "run": run.name,
        "run_id": None,
        "passed": False,
        "mandatory_drc_clean": False,
        "zero_unconnected": False,
        "circuit_parity_clean": False,
        "native_backend": False,
        "placement_actions": 0,
        "route_actions": 0,
        "attempts_used": 0,
        "elapsed_seconds": 0.0,
        "action_outcomes": [],
        "action_failure_codes": [],
        "failures": [],
    }
    try:
        manifest = _read_json(run / "manifest.json")
        if set(manifest) != MANIFEST_FIELDS or manifest.get("schema_version") != 1:
            raise ValueError("unsupported run manifest")
        score["run_id"] = manifest.get("run_id")
        if (not isinstance(score["run_id"], str) or not score["run_id"]
                or manifest.get("max_actions") != 300
                or manifest.get("max_duration_seconds") != 1200):
            raise ValueError("run manifest does not freeze the M2 envelope")
        input_board = (run / manifest["input"]).resolve()
        input_root = input_board.parent
        project = (run / manifest["board"]).resolve()
        if (not input_board.is_relative_to(run / "input") or not input_board.is_file()
                or not project.is_relative_to(run / "project") or not project.is_file()):
            raise ValueError("run input/project path escaped its isolated bundle")
        benchmark = load_benchmark(input_root / "benchmark.json")
        if benchmark["sha256"] != manifest["fixture_sha256"]:
            raise ValueError("run manifest and input benchmark hashes differ")
        if fixture_hashes(input_root) != manifest["fixture_sha256"]:
            raise ValueError("immutable input fixture hashes changed")

        transcript_path = (run / manifest["transcript"]).resolve()
        if not transcript_path.is_relative_to(run):
            raise ValueError("transcript path escaped run")
        transcript = _parse_transcript(transcript_path)
        writes = [row for row in transcript if row["tool"] in WRITE_TOOLS]
        last_write_sequence = max((row["sequence"] for row in writes), default=0)
        connect = _latest(transcript, "pcb_connect")["result"]
        summary_row = _latest(transcript, "pcb_summary")
        summary = summary_row["result"]
        final_verify_row = _latest(transcript, "pcb_verify_geometry")
        final_verify = final_verify_row["result"]
        score["native_backend"] = bool(
            connect.get("ok") and connect.get("backend") == "kicad"
            and connect.get("native_editing_enabled") is True
            and Path(connect.get("project", "")).resolve() == project
            and summary.get("backend") == "kicad"
            and summary.get("server_version") == "10.0.6 (10.0.6)"
            and final_verify.get("backend") == "kicad"
        )
        if not score["native_backend"]:
            score["failures"].append("exact native KiCad 10.0.6 backend was not proven")
        final_evidence_after_writes = (
            summary_row["sequence"] > last_write_sequence
            and final_verify_row["sequence"] > last_write_sequence
        )
        if not final_evidence_after_writes:
            score["failures"].append("final native summary/verification did not follow all writes")

        accepted = [row for row in writes if row["tool"] == "pcb_execute"
            and row["result"].get("ok") is True
            and row["result"].get("replayed") is not True
            and row["result"].get("rolled_back") is not True
            and row["result"].get("recovery_required") is not True]
        score["placement_actions"] = sum(
            row["arguments"].get("action") in PLACEMENT_ACTIONS for row in accepted)
        score["route_actions"] = sum(
            row["arguments"].get("action") == "route_track" for row in accepted)
        if score["placement_actions"] < benchmark["min_host_placement_actions"]:
            score["failures"].append("no accepted host-specified placement action")
        if score["route_actions"] < 1:
            score["failures"].append("no accepted host-specified route action")

        service = (run / manifest["service_directory"]).resolve()
        if not service.is_relative_to(run):
            raise ValueError("service path escaped run")
        attempts, ledger_elapsed, outcomes, admissions = _parse_ledger(service / "run.jsonl", project)
        score["attempts_used"] = attempts
        score["action_outcomes"] = outcomes
        score["action_failure_codes"] = [row["error_code"] for row in outcomes if row["error_code"]]
        if attempts != len(writes):
            score["failures"].append("host write calls and durable admissions differ")
        for call, admission, outcome in zip(writes, admissions, outcomes):
            operation = {"pcb_execute": "execute", "pcb_create_checkpoint": "create_checkpoint",
                "pcb_restore_checkpoint": "restore_checkpoint"}[call["tool"]]
            result = call["result"]
            if (admission["operation"] != operation
                    or admission["action_id"] != call["arguments"].get("action_id")
                    or result.get("run_budget", {}).get("attempts_used") != outcome["attempt"]
                    or any(result.get(key, False) != outcome[key] for key in
                        ("ok", "replayed", "rolled_back", "recovery_required"))
                    or any(result.get(key) != outcome[key] for key in ("error_code", "revision"))):
                raise ValueError("host call/result contradicts durable admission/outcome")
        if attempts > manifest["max_actions"]:
            score["failures"].append("run exceeded 300 admitted attempts")
        if any(row["recovery_required"] for row in outcomes):
            score["failures"].append("run contains an uncertain/recovery-required write")

        budget_elapsed = []
        budget_errors = []
        for row in transcript:
            budget = row["result"].get("run_budget")
            if budget is None:
                continue
            if not isinstance(budget, dict):
                raise ValueError("malformed run budget in transcript")
            if budget.get("max_actions") != 300 or budget.get("max_duration_seconds") != 1200:
                raise ValueError("transcript run budget differs from frozen envelope")
            budget_elapsed.append(_finite_number(budget.get("elapsed_seconds"), "budget elapsed"))
            if budget.get("evidence_error"):
                budget_errors.append(str(budget["evidence_error"]))
        if not budget_elapsed:
            raise ValueError("transcript has no run budget evidence")
        score["elapsed_seconds"] = max([ledger_elapsed, *budget_elapsed])
        if score["elapsed_seconds"] > manifest["max_duration_seconds"]:
            score["failures"].append("run exceeded 1200 elapsed seconds")
        if budget_errors:
            score["failures"].append("run budget evidence error: " + "; ".join(sorted(set(budget_errors))))
        if (connect.get("recovery_required") or summary.get("recovery_required")
                or final_verify.get("recovery_required")):
            score["failures"].append("final native state requires recovery")

        if (summary.get("ok") is not True or summary_row["is_error"]
                or final_verify_row["is_error"] or summary.get("revision") != final_verify.get("revision")):
            raise ValueError("final summary and verification revisions/results differ")
        successful_revisions = [outcome["revision"] for outcome in outcomes
            if outcome["ok"] and not outcome["rolled_back"] and not outcome["replayed"]]
        if successful_revisions and final_verify.get("revision") != successful_revisions[-1]:
            raise ValueError("final verification revision differs from last accepted write")
        report, parsed = _raw_drc(Path(final_verify.get("evidence", "")), run, project,
            set(benchmark["sha256"]))
        score["mandatory_drc_clean"] = (
            final_evidence_after_writes
            and final_verify.get("ok") is True
            and final_verify.get("geometric") == []
            and report["violations"] == []
            and parsed["status"] == "verified"
        )
        score["zero_unconnected"] = (
            final_evidence_after_writes
            and final_verify.get("connectivity") == []
            and report["unconnected_items"] == [])
        score["circuit_parity_clean"] = (
            final_evidence_after_writes and report["schematic_parity"] == [])
        if not score["mandatory_drc_clean"]:
            score["failures"].append("mandatory geometric DRC is not clean")
        if not score["zero_unconnected"]:
            score["failures"].append("unconnected items remain")
        if not score["circuit_parity_clean"]:
            score["failures"].append("schematic parity is not clean")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        score["failures"].append(f"evidence error: {error}")
    score["passed"] = not score["failures"]
    (run / "score.json").write_text(json.dumps(score, indent=2, sort_keys=True) + "\n")
    return score


def _run_number(path: Path):
    try:
        return int(path.name.removeprefix("run-"))
    except ValueError:
        return 10**9


def score_campaign(path: Path, expected_runs: int = 5) -> dict:
    campaign = Path(path).resolve()
    runs = sorted((entry for entry in campaign.glob("run-*") if entry.is_dir()), key=_run_number)
    scored = [score_run(run) for run in runs]
    passed = sum(bool(run["passed"]) for run in scored)
    expected_names = {f"run-{n}" for n in range(1, expected_runs + 1)}
    observed_names = {run.name for run in runs}
    failures = []
    if len(runs) != expected_runs:
        failures.append(f"expected {expected_runs} runs; found {len(runs)}")
    elif {run.name for run in runs} != {f"run-{n}" for n in range(1, expected_runs + 1)}:
        failures.append("unexpected run names; expected " + ", ".join(
            f"run-{n}" for n in range(1, expected_runs + 1)) + "; found " + ", ".join(run.name for run in runs))
    if not failures and passed < 3:
        failures.append(f"only {passed}/{expected_runs} runs passed")
    report = {"schema_version": 1, "gate_passed": not failures,
        "passed_runs": passed, "required_runs": 3, "total_runs": expected_runs,
        "missing_runs": sorted(expected_names - observed_names),
        "unexpected_runs": sorted(observed_names - expected_names),
        "failures": failures, "runs": scored}
    (campaign / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description="Score the fail-closed M2 routing campaign")
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--expected-runs", type=int, default=5)
    options = parser.parse_args()
    print(json.dumps(score_campaign(options.campaign, options.expected_runs), indent=2))


if __name__ == "__main__":
    main()
