"""Fail-closed M0 report and document identity checks; not a full Kernel."""
from pathlib import Path
import json
import subprocess

# Explicitly audited initial fixture defaults. Extra/unknown ignored checks fail
# closed; a general profile-specific check policy belongs to the rule compiler.
ALLOWED_IGNORED={
    'drc':{'missing_courtyard','track_not_centered_on_via','tuning_profile_track_geometries',
        'footprint_filters_mismatch','footprint_type_mismatch'},
    'erc':{'single_global_label','four_way_junction','simulation_model_issue','footprint_filter'}}


def select_document(documents, expected_path):
    expected = Path(expected_path).resolve()
    matches = []
    for document in documents:
        if not document.board_filename:
            continue
        candidate = Path(document.board_filename)
        if not candidate.is_absolute():
            if not document.project.path:
                continue
            candidate = Path(document.project.path) / candidate
        if candidate.resolve() == expected:
            matches.append(document)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one scratch document {expected}; found {len(matches)}")
    return matches[0]


def parse_report(report, kind, expected_source, exit_code):
    if kind not in ("drc", "erc") or not isinstance(report, dict):
        raise ValueError("unknown verification kind/report")
    if report.get("$schema") != f"https://schemas.kicad.org/{kind}.v1.json":
        raise ValueError("unsupported report schema")
    if report.get("source") != Path(expected_source).name:
        raise ValueError("report source mismatch")
    if report.get("coordinate_units") not in ("mm", "in", "mils"):
        raise ValueError("unsupported report coordinate units")
    if not isinstance(report.get("kicad_version"), str) or not report["kicad_version"]:
        raise ValueError("report has no KiCad version")
    severities = report.get("included_severities")
    if not isinstance(severities, list) or not {"error", "warning", "exclusion"}.issubset(severities):
        raise ValueError("report omitted required severities")
    if not isinstance(report.get("ignored_checks"), list):
        raise ValueError("report has no ignored-checks list")
    for check in report['ignored_checks']:
        if not isinstance(check,dict) or check.get('key') not in ALLOWED_IGNORED[kind]:
            raise ValueError('essential/unknown DRC/ERC check was disabled')
    if kind == "drc":
        sections = [report.get(key) for key in ("violations", "unconnected_items", "schematic_parity")]
    else:
        sheets = report.get("sheets")
        if not isinstance(sheets, list) or not sheets or any(not isinstance(s, dict) for s in sheets):
            raise ValueError("ERC sheets missing or malformed")
        sections = [sheet.get("violations") for sheet in sheets]
    if any(not isinstance(section, list) for section in sections):
        raise ValueError("report section missing or malformed")
    issues = [issue for section in sections for issue in section]
    for issue in issues:
        if not isinstance(issue, dict) or issue.get("severity") not in ("error", "warning", "exclusion"):
            raise ValueError("malformed or unknown-severity violation")
        if not isinstance(issue.get("type"), str) or not issue["type"]:
            raise ValueError("violation type missing")
    if exit_code not in (0, 5) or (exit_code == 5 and not issues):
        raise ValueError(f"process failed/inconsistent report: exit {exit_code}")
    return {"status": "verified", "passed": exit_code == 0 and not issues,
        "issue_count": len(issues), "issues": issues,
        "ignored_checks": report["ignored_checks"], "kicad_version": report["kicad_version"],
        "coordinate_units": report["coordinate_units"]}


def run_verification(cli, kind, input_file, report_path, *, parity=True, refill=False):
    input_file, report_path = Path(input_file), Path(report_path)
    if kind not in ("drc", "erc"):
        raise ValueError("unknown verification kind")
    if report_path.suffix != ".json" or report_path.resolve() == input_file.resolve():
        raise ValueError("report must be a separate JSON artifact")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)
    args = [str(cli), "pcb" if kind == "drc" else "sch", kind,
        "--format", "json", "--severity-all", "--exit-code-violations"]
    if kind == "drc" and parity:
        args.append("--schematic-parity")
    if kind == "drc" and refill:
        args.append("--refill-zones")
    args.extend(["-o", str(report_path), str(input_file)])
    evidence = {"command": args, "status": "tool_error", "passed": False}
    try:
        process = subprocess.run(args, capture_output=True, text=True, timeout=60)
        evidence.update(exit_code=process.returncode, stdout=process.stdout, stderr=process.stderr)
        report = json.loads(report_path.read_text())
        evidence.update(parse_report(report, kind, input_file.name, process.returncode))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        evidence["error"] = str(error)
    return evidence
