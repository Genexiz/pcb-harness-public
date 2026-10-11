from copy import deepcopy
from pathlib import Path
import argparse
import json
import shutil

from pcb_harness.circuit.bundle import load_bundle,read_json,resolve_local,sha256,bundle_hashes
from pcb_harness.circuit.review import review_circuit
from pcb_harness.circuit.writer import write_project,output_path
from pcb_harness.circuit.bootstrap import verify_bootstrap
from pcb_harness.fabrication.profile import review_profile
from pcb_harness.fabrication.compiler import compile_rules
from pcb_harness.native_reports import run_verification
from .cases import CIRCUIT_CODES,FABRICATION_RULES,circuit_negative,bad_geometry

ROOT=Path(__file__).resolve().parents[2]


def save(path,data):
    Path(path).write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+"\n")


def artifact_hashes(root):
    return {str(path.relative_to(root)):sha256(resolve_local(root,str(path.relative_to(root))))
        for path in sorted(root.rglob("*")) if path.is_file() and path.name!="integrity.json"}


def verify_acceptance_report(output):
    output=Path(output).absolute()
    try:
        expected=read_json(resolve_local(output,"integrity.json"))["sha256"]
        return artifact_hashes(output)==expected
    except (OSError,ValueError,KeyError):
        return False


def native_probe(bundle,output,cli,variant):
    shutil.copytree(ROOT/"fixtures/capability",output)
    profile=deepcopy(bundle["fabrication"])
    if variant=="hole_clearance":
        profile.update(layers=4,copper_oz=[1,0.5,0.5,1])
        next(item for item in profile["categories"] if item["id"]=="clearance")["design_target"]=0.01
    compiled=compile_rules(profile,{"schema_version":1,"constraints":[]})
    compiled["settings"]["board"]["design_settings"]["rules"]={"min_clearance":0.01,"min_track_width":0.01,
        "min_through_hole_diameter":0.01,"min_via_diameter":0.01,"min_copper_edge_clearance":0.01}
    save(output/"profile.json",profile)
    save(output/"compilation.json",compiled)
    save(output/"board.kicad_pro",compiled["settings"])
    (output/"board.kicad_dru").write_text(compiled["rules"])
    board=output/"board.kicad_pcb"
    board.write_text(bad_geometry(board.read_text(),variant))
    result=run_verification(cli,"drc",board,output/"drc.json")
    save(output/"result.json",result)
    if variant=="positive":
        return {"accepted":result.get("passed") is True,"native":result}
    rule=FABRICATION_RULES[variant]
    rejected=(result.get("status")=="verified" and result.get("passed") is False
        and any(f"M3 {rule}" in issue["description"] for issue in result.get("issues",[])))
    return {"rejected":rejected,"expected_rule":rule,"native":result}


def run_acceptance(bundle_root,checklist_path,output,cli):
    bundle_root=Path(bundle_root).absolute()
    output=output_path(bundle_root,output)
    bundle=load_bundle(bundle_root)
    checklist_path=Path(checklist_path).absolute()
    checklist=read_json(resolve_local(checklist_path.parent,checklist_path.name))
    source_hashes=bundle_hashes(bundle_root)
    oracle_hash=sha256(checklist_path)
    output.mkdir(parents=True,exist_ok=False)
    source=output/"source-input"
    source.mkdir()
    for relative in source_hashes:
        destination=source/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(resolve_local(bundle_root,relative),destination)
    save(output/"independent-checklist.json",checklist)
    save(output/"input-manifest.json",{"schema_version":1,"bundle_sha256":source_hashes,"checklist_sha256":oracle_hash,
        "native_cli":str(cli),"native_version":"10.0.6","synthetic":True})
    report={"schema_version":1,"implementation_gate":False,"native_bootstrap_gate":False,
        "circuit_negative_gate":False,"fabrication_negative_gate":False,"gate_passed":False,
        "release_eligible":False,"circuit_negatives":{},"fabrication_negatives":{},"failures":[]}
    review=review_circuit(bundle,bundle_root,checklist)
    profile=review_profile(bundle["fabrication"],bundle["facts"])
    save(output/"circuit-review.json",review)
    save(output/"fabrication-review.json",profile)
    report["implementation_gate"]=review["passed"] and profile["passed"]
    report["release_blockers"]={"facts":review["unknowns"],"fabrication":profile["unknowns"],"synthetic_evidence":True,
        "real_target":"M4 part/package/pin/power/firmware feasibility not established"}
    try:
        write_project(bundle,bundle_root,checklist,output/"positive")
        positive=verify_bootstrap(output/"positive/board.kicad_pcb",cli)
        report["positive_bootstrap"]=positive
        report["native_bootstrap_gate"]=positive["accepted"]
    except (OSError,ValueError) as error:
        report["positive_bootstrap"]={"accepted":False,"error":str(error)}
    for variant,expected_code in CIRCUIT_CODES.items():
        case_root=output/"circuit-negatives"/variant
        case_root.mkdir(parents=True,exist_ok=False)
        try:
            case,oracle=circuit_negative(bundle,checklist,variant)
            save(case_root/"bundle.json",case)
            save(case_root/"checklist.json",oracle)
            result=review_circuit(case,bundle_root,oracle)
            rejected=not result["passed"] and expected_code in {issue["code"] for issue in result["issues"]}
            report["circuit_negatives"][variant]={"rejected":rejected,"expected_code":expected_code,"review":result}
        except (OSError,ValueError,KeyError) as error:
            report["circuit_negatives"][variant]={"rejected":False,"error":str(error)}
        save(case_root/"result.json",report["circuit_negatives"][variant])
    report["circuit_negative_gate"]=len(report["circuit_negatives"])==8 and all(case["rejected"] for case in report["circuit_negatives"].values())
    try:
        report["fabrication_positive"]=native_probe(bundle,output/"fabrication-positive",cli,"positive")
    except (OSError,ValueError) as error:
        report["fabrication_positive"]={"accepted":False,"error":str(error)}
    for variant in FABRICATION_RULES:
        try:
            report["fabrication_negatives"][variant]=native_probe(bundle,output/"fabrication-negatives"/variant,cli,variant)
        except (OSError,ValueError) as error:
            report["fabrication_negatives"][variant]={"rejected":False,"error":str(error)}
    report["fabrication_negative_gate"]=report["fabrication_positive"]["accepted"] and len(report["fabrication_negatives"])==8 and all(case["rejected"] for case in report["fabrication_negatives"].values())
    if bundle_hashes(bundle_root)!=source_hashes or sha256(checklist_path)!=oracle_hash:
        report["failures"].append("input/oracle changed during acceptance")
    for gate in ("implementation_gate","native_bootstrap_gate","circuit_negative_gate","fabrication_negative_gate"):
        if not report[gate]:
            report["failures"].append(f"failed {gate}")
    report["gate_passed"]=not report["failures"]
    save(output/"report.json",report)
    save(output/"integrity.json",{"schema_version":1,"sha256":artifact_hashes(output)})
    return report


def main():
    parser=argparse.ArgumentParser(description="Run retained synthetic M3 circuit/native acceptance")
    for name in ("bundle","checklist","output","cli"):
        parser.add_argument(f"--{name}",type=Path,required=True)
    options=parser.parse_args()
    report=run_acceptance(options.bundle,options.checklist,options.output,options.cli)
    print(json.dumps({key:report[key] for key in ("gate_passed","implementation_gate","native_bootstrap_gate","circuit_negative_gate","fabrication_negative_gate","release_eligible","failures")},indent=2))
    raise SystemExit(0 if report["gate_passed"] else 1)


if __name__=="__main__":
    main()
