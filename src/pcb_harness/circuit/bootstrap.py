"""Saved-copy native acceptance; an unrouted bootstrap is never release-ready."""
from pathlib import Path
import json
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET
from .bundle import KINDS, read_json, resolve_local, sha256, load_bundle, referenced_paths
from .review import review_circuit
from pcb_harness.fabrication.profile import review_profile
from pcb_harness.fabrication.compiler import compile_rules
from pcb_harness.native_reports import run_verification


def parse_native_netlist(path):
    document = ET.parse(path).getroot()
    nets = document.find("nets")
    if document.tag != "export" or nets is None:
        raise ValueError("malformed native netlist")
    result = {}
    for net in nets.findall("net"):
        name = net.get("name")
        if not name or name in result:
            raise ValueError("missing/duplicate net name")
        endpoints = [(endpoint.get("ref"),endpoint.get("pin")) for endpoint in net.findall("node")]
        if any(not ref or not pin for ref,pin in endpoints) or len(set(endpoints)) != len(endpoints):
            raise ValueError("incomplete/duplicate net endpoints")
        result[name] = set(endpoints)
    return result


def verify_bootstrap(project, cli):
    project, cli = Path(project).absolute(), Path(cli)
    root = project.parent
    result = {"schema_version":1,"accepted":False,"erc_clean":False,"parity_clean":False,
        "geometric_clean":False,"zero_unconnected":False,"routed":False,"release_eligible":False,
        "netlist_matches":False,"failures":[],"commands":[]}
    try:
        manifest = read_json(resolve_local(root,"bootstrap-manifest.json"))
        if manifest["schema_version"] != 1 or project.name != "board.kicad_pcb":
            raise ValueError("unsupported bootstrap identity")
        required = {"board.kicad_pcb", "board.kicad_sch", "board.kicad_pro", "board.kicad_dru",
            "sym-lib-table", "fp-lib-table", "circuit-review.json", "fabrication-review.json", "rule-compilation.json"}
        required.update(f"inputs/{kind}.json" for kind in KINDS)
        if not required.issubset(manifest["output_sha256"]):
            raise ValueError("required bootstrap evidence missing from manifest")
        bundle = load_bundle(root/"inputs")
        required.update(f"inputs/{relative}" for relative in referenced_paths(bundle))
        for part in bundle["parts"]["parts"]:
            required.add(f"{part['symbol_id'].split(':')[0]}.kicad_sym")
            namespace, name = part["footprint_id"].split(":")
            required.add(f"{namespace}.pretty/{name}.kicad_mod")
        if not required.issubset(manifest["output_sha256"]):
            raise ValueError("required bootstrap asset evidence missing from manifest")
        for relative,digest in manifest["output_sha256"].items():
            if sha256(resolve_local(root,relative)) != digest:
                raise ValueError(f"bootstrap output drift: {relative}")
        stored_review = read_json(resolve_local(root,"circuit-review.json"))
        stored_profile = read_json(resolve_local(root,"fabrication-review.json"))
        review = review_circuit(bundle,root/"inputs",bundle["checklist"])
        profile = review_profile(bundle["fabrication"],bundle["facts"])
        if any(report.get("passed") is not True for report in (stored_review,stored_profile,review,profile)):
            raise ValueError("upstream circuit/fabrication review failed")
        semantic_hash = review["input_sha256"]["semantic_bundle"]
        if (manifest["input_sha256"].get("semantic_bundle") != semantic_hash
                or stored_review["input_sha256"].get("semantic_bundle") != semantic_hash):
            raise ValueError("upstream review does not bind bootstrap inputs")
        compiled = compile_rules(bundle["fabrication"],bundle["constraints"])
        if (read_json(resolve_local(root,"rule-compilation.json")) != compiled
                or read_json(resolve_local(root,"board.kicad_pro")) != compiled["settings"]
                or resolve_local(root,"board.kicad_dru").read_text() != compiled["rules"]):
            raise ValueError("upstream rule compilation differs from bootstrap project")
        version = subprocess.run([str(cli),"version"],capture_output=True,text=True,timeout=5)
        result["commands"].append({"command":[str(cli),"version"],"exit_code":version.returncode,"stdout":version.stdout,"stderr":version.stderr})
        if version.returncode != 0 or version.stdout.strip() != "10.0.6":
            raise ValueError("exact stable KiCad 10.0.6 required")
        evidence = resolve_local(root,f"native/bootstrap-{uuid.uuid4()}")
        snapshot = evidence/"snapshot"
        snapshot.mkdir(parents=True,exist_ok=False)
        for relative in manifest["output_sha256"]:
            destination = snapshot/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(resolve_local(root,relative),destination)
        result["evidence"] = str(evidence)
        erc = run_verification(cli,"erc",snapshot/"board.kicad_sch",evidence/"erc.json")
        drc = run_verification(cli,"drc",snapshot/"board.kicad_pcb",evidence/"drc.json")
        result["erc"] = erc
        result["drc"] = drc
        (evidence/"erc-result.json").write_text(json.dumps(erc,indent=2))
        (evidence/"drc-result.json").write_text(json.dumps(drc,indent=2))
        result["erc_clean"] = erc.get("passed") is True
        if drc.get("status") != "verified":
            raise ValueError("native DRC failed")
        report = read_json(evidence/"drc.json")
        result["parity_clean"] = report["schematic_parity"] == []
        result["geometric_clean"] = report["violations"] == []
        result["zero_unconnected"] = report["unconnected_items"] == []
        for args in (["sch","export","netlist","--format","kicadxml","-o",str(evidence/"netlist.xml"),str(snapshot/"board.kicad_sch")],
                ["sch","export","svg","-o",str(evidence/"svg"),str(snapshot/"board.kicad_sch")]):
            process = subprocess.run([str(cli),*args],capture_output=True,text=True,timeout=60)
            result["commands"].append({"command":[str(cli),*args],"exit_code":process.returncode,"stdout":process.stdout,"stderr":process.stderr})
            if process.returncode != 0:
                raise ValueError("native schematic export failed")
        refs = {instance["id"]:instance["ref"] for instance in bundle["circuit"]["instances"]}
        parts = {part["id"]:part for part in bundle["parts"]["parts"]}
        instances = {instance["id"]:instance for instance in bundle["circuit"]["instances"]}
        expected = {net["name"]:{(refs[endpoint["instance_id"]],next(pin["number"] for pin in parts[instances[endpoint["instance_id"]]["part_id"]]["pins"] if pin["id"]==endpoint["pin_id"])) for endpoint in net["endpoints"]} for net in bundle["circuit"]["nets"]}
        observed = parse_native_netlist(evidence/"netlist.xml")
        expected_nc = {(refs[endpoint["instance_id"]],next(pin["number"] for pin in parts[instances[endpoint["instance_id"]]["part_id"]]["pins"] if pin["id"]==endpoint["pin_id"])) for endpoint in bundle["circuit"]["no_connect"]}
        observed_nc = set()
        xml_nets = ET.parse(evidence/"netlist.xml").getroot().find("nets")
        for net in xml_nets.findall("net"):
            endpoints = observed[net.get("name")]
            if (len(endpoints)==1 and endpoints.issubset(expected_nc)
                    and net.get("name").startswith("unconnected-(")
                    and all("+no_connect" in endpoint.get("pintype","") for endpoint in net.findall("node"))):
                observed_nc.update(endpoints)
                del observed[net.get("name")]
        result["netlist_matches"] = observed == expected and observed_nc == expected_nc
        if not any((evidence/"svg").glob("*.svg")):
            raise ValueError("native SVG artifact missing")
        for relative,digest in manifest["output_sha256"].items():
            if sha256(resolve_local(root,relative)) != digest or sha256(resolve_local(snapshot,relative)) != digest:
                raise ValueError("project or verified snapshot changed during native checks")
        result["accepted"] = all(result[key] for key in ("erc_clean","parity_clean","geometric_clean","netlist_matches"))
        if not result["accepted"]:
            result["failures"].append("ERC, geometry, parity, or exported netlist failed")
    except (OSError,ValueError,KeyError,TypeError,ET.ParseError,subprocess.SubprocessError) as error:
        result["failures"].append(str(error))
    if "evidence" in result:
        (Path(result["evidence"])/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    return result
