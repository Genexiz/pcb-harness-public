"""Prepare exact-MPN local core assets; structural fit is not circuit approval."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from pcb_harness.circuit.assets import electrical_pad, load_part_assets
from pcb_harness.circuit.bundle import read_json, resolve_local, sha256, validate_document
from pcb_harness.circuit.sexpr import Atom, children, child, dump_sexpr, parse_sexpr, walk
from pcb_harness.circuit.symbols import flatten_symbol
from pcb_harness.circuit.writer import output_path
from pcb_harness.orchestration.stm32_feasibility import validate_design

NAMESPACE = "STM32Target"
LICENSE = "CC-BY-SA-4.0 with KiCad library exception; collection review pending in NOTICE.md"
# Calibrated templates are geometry inputs, never substitute manufacturer parts.
POLICY = {
    "U1": ("STM32F103C8T6", "MCU_ST_STM32F1:STM32F103C8Tx", "Package_QFP:LQFP-48_7x7mm_P0.5mm"),
    "U2/U3": ("MCP2518FD-E/SL", "Interface_CAN_LIN:MCP2517FD-xSL", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm"),
    "U4/U5": ("MCP2562FD-E/SN", "Interface_CAN_LIN:MCP2562-E-SN", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"),
    "U6": ("THVD1450DR", "Interface_UART:THVD1450D", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"),
    "U7": ("MAX3232IDR", "Interface_UART:MAX3232", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm"),
    "U8": ("TPS62162DSGR", "Regulator_Switching:TPS62162DSG", "Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm_ThermalVias"),
}
PART_DETAILS = {
    "U1": ("LQFP48 7x7mm pitch0.5", "stm32-ds", "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf"),
    "U2/U3": ("SOIC14 3.9mm body", "mcp2518fd", "https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/External-CAN-FD-Controller-with-SPI-Interface-DS20006027B.pdf"),
    "U4/U5": ("SOIC8", "can-phy", "https://ww1.microchip.com/downloads/en/DeviceDoc/20005284A.pdf"),
    "U6": ("SOIC8", "rs485", "https://www.ti.com/lit/ds/symlink/thvd1450.pdf"),
    "U7": ("SOIC16", "rs232", "https://www.ti.com/lit/ds/symlink/max3232.pdf"),
    "U8": ("WSON8 2x2mm exposed pad", "buck", "https://www.ti.com/lit/ds/symlink/tps62160.pdf"),
    "M1": ("module two headers and RJ45", "wiz550io", "https://docs.wiznet.io/Product/ioModule/wiz550io"),
}
BLOCKERS = ["PINOUT_PACKAGE_REVIEW", "LICENSE_REVIEW", "MODULE_ASSET", "SUPPORT_BOM", "FULL_FIRMWARE",
            "POWER_THERMAL", "CIRCUIT_NATIVE", "MECHANICAL", "ERRATA", "FABRICATION", "SOURCE_INTEGRITY"]
SUPPORT = ["MCU bypass/bulk and VDDA network", "8MHz HSE crystal and qualified load capacitors",
           "two40MHz CAN crystals and qualified load capacitors", "regulator inductor and biased input/output capacitors",
           "USB-C receptacle, CC resistors, ESD, pullup/disconnect and unpowered-safe VBUS sense",
           "boot/reset/SWD controls and connector", "UART/I2C/SPI headers, pullups and unpowered IO protection",
           "RS232 charge-pump/bypass capacitors and connector", "RS485 termination/bias/protection and connector",
           "two CAN termination/protection networks and connectors", "WIZ550io sockets and body/header envelope",
           "external5V input/protection, test points, LEDs and mounting holes"]


def asset_paths(record):
    paths = []
    for key, folder, extension in (("library_id", "symbols", ".kicad_sym"),
                                    ("candidate_footprint", "footprints", ".kicad_mod")):
        value = record[key]
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]+:[A-Za-z0-9_.+-]+", value):
            raise ValueError("unsafe source asset identifier")
        namespace, name = value.split(":")
        paths.append(f"{folder}/{namespace}{extension}" if folder == "symbols"
                     else f"{folder}/{namespace}.pretty/{name}{extension}")
    return paths


def inspect_inputs(inputs, library_root):
    candidate, design, sources = (read_json(inputs / name) for name in ("candidates.json", "design.json", "sources.json"))
    validate_design(design)
    if (type(candidate["schema_version"]) is not int or candidate["schema_version"] != 1
            or candidate.get("human_confirmed") is not False
            or candidate.get("layout_allowed") is not False):
        raise ValueError("unapproved core candidate state")
    records = {r["ref"]: r for r in candidate["parts"]}
    parts = {p["ref"]: p for p in design["parts"]}
    if (len(records) != len(candidate["parts"]) or set(records) != set(POLICY)
            or len(parts) != len(design["parts"]) or set(parts) != set(POLICY) | {"M1"}
            or parts["M1"]["mpn"] != "WIZ550io v1.2"):
        raise ValueError("core inventory coverage mismatch")
    docs = {d["id"]: d for d in sources["documents"]}
    if sources["schema_version"] != 1 or len(docs) != len(sources["documents"]):
        raise ValueError("invalid source identifiers")
    for ref, (package, document_id, url) in PART_DETAILS.items():
        if ((parts[ref]["package"], parts[ref]["source_id"]) != (package, document_id)
                or docs.get(document_id, {}).get("url") != url):
            raise ValueError(f"uncalibrated package or publisher document: {ref}")
    blobs, libraries, inspected = {}, {}, []
    for ref, record in records.items():
        expected = POLICY[ref]
        if (record["mpn"], record["library_id"], record["candidate_footprint"]) != expected or parts[ref]["mpn"] != expected[0]:
            raise ValueError(f"uncalibrated core part/template/package: {ref}")
        if record.get("status") != "candidate-not-accepted":
            raise ValueError("candidate acceptance is not established by this producer")
        if type(record["non_electrical_shapes"]) is not int or record["non_electrical_shapes"] < 0:
            raise ValueError("invalid non-electrical shape count")
        symbol_path, footprint_path = asset_paths(record)
        for path, field in ((symbol_path, "library_sha256"), (footprint_path, "footprint_sha256")):
            if path not in blobs:
                blobs[path] = resolve_local(library_root, path).read_bytes()
            if hashlib.sha256(blobs[path]).hexdigest() != record[field]:
                raise ValueError(f"source asset hash drift: {ref}/{field}")
    # Read every source before the first flatten call; capture cannot mix live versions.
    for ref, record in records.items():
        symbol_path, footprint_path = asset_paths(record)
        if symbol_path not in libraries:
            libraries[symbol_path] = parse_sexpr(blobs[symbol_path].decode("utf-8"))
        name = record["library_id"].split(":")[1]
        standalone = flatten_symbol(libraries[symbol_path], name, "Inspection")
        pins = [{"number": str(child(p, "number")[1]), "name": str(child(p, "name")[1]), "type": str(p[1])}
                for p in walk(standalone, "pin")]
        footprint = parse_sexpr(blobs[footprint_path].decode("utf-8"))
        if footprint[0] != "footprint" or footprint[1] != record["candidate_footprint"].split(":")[1]:
            raise ValueError("source footprint identity mismatch")
        pads = [str(p[1]) for p in children(footprint, "pad") if electrical_pad(p)]
        if (pins != record["symbol_pins"] or pads != record["electrical_pad_numbers"]
                or len(children(footprint, "pad")) - len(pads) != record["non_electrical_shapes"]
                or {p["number"] for p in pins} != set(pads)):
            raise ValueError(f"candidate pin/pad snapshot drift: {ref}")
        doc = docs.get(parts[ref]["source_id"])
        if doc is None or not doc["url"].startswith("https://"):
            raise ValueError("missing publisher source link")
        inspected.append((ref, record, parts[ref], libraries[symbol_path], footprint, pins, doc))
    return candidate, design, blobs, inspected


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def exact_names(record):
    name = record["mpn"].replace("/", "_")
    return name, name + "_" + record["candidate_footprint"].split(":")[1]


def exact_symbol(record, library, doc):
    name, footprint_name = exact_names(record)
    return flatten_symbol(library, record["library_id"].split(":")[1], name,
                          {"Value": record["mpn"], "Footprint": NAMESPACE + ":" + footprint_name, "Datasheet": doc["url"],
                           "Description": f"Exact-MPN structural candidate {record['mpn']}; electrical review pending",
                           "ki_fp_filters": footprint_name})


def exact_footprint(record, footprint):
    footprint = deepcopy(footprint)
    footprint[1] = exact_names(record)[1]
    for prop in children(footprint, "property"):
        if prop[1] == "Value":
            prop[2] = record["mpn"]
    return footprint


def exact_part(ref, record, source_part, pins, output):
    name, footprint_name = exact_names(record)
    footprint_path = f"assets/{NAMESPACE}.pretty/{footprint_name}.kicad_mod"
    pin_records = [{"id": "p" + p["number"], **p, "operating_range_v": None,
                    "operating_fact_id": None, "absolute_maximum_fact_id": None} for p in pins]
    return {"id": name, "mpn": record["mpn"], "manufacturer": "STMicroelectronics" if ref == "U1"
            else "Microchip" if ref in ("U2/U3", "U4/U5") else "Texas Instruments",
            "package": source_part["package"], "revision": "candidate-source-snapshot", "lifecycle": "unknown",
            "symbol_id": NAMESPACE + ":" + name, "footprint_id": NAMESPACE + ":" + footprint_name,
            "symbol": {"path": f"assets/{NAMESPACE}.kicad_sym", "sha256": "0" * 64, "license": LICENSE},
            "footprint": {"path": footprint_path, "sha256": sha256(resolve_local(output, footprint_path)), "license": LICENSE},
            "pins": pin_records, "pin_map": [{"pin_id": p["id"], "symbol_pin": p["number"], "pads": [p["number"]]} for p in pin_records],
            "fact_ids": [], "required_fact_ids": [name + ":pinout", name + ":package"],
            "errata_fact_ids": [name + ":errata"] if ref == "U1" else []}


def exact_bom(design, inspected):
    instances = []
    for ref, record, source_part, *_ in inspected:
        for instance_ref in ref.split("/"):
            instances.append({"ref": instance_ref, "part_id": exact_names(record)[0], "mpn": record["mpn"],
                              "package": source_part["package"], "quantity": 1, "asset_status": "structurally-prepared-unconfirmed"})
    module = next(p for p in design["parts"] if p["ref"] == "M1")
    instances.append({"ref": "M1", "part_id": None, "mpn": module["mpn"], "package": module["package"],
                      "quantity": 1, "asset_status": "unavailable"})
    return {"schema_version": 1, "scope": "core inventory only; support BOM incomplete", "instances": instances}


def preparation_report():
    return {"schema_version": 1, "milestone": "M4", "scope": "exact core structural asset preparation",
            "structural_assets_passed": True, "prepared_part_types": 6, "prepared_ic_instances": 8,
            "accepted_real_target_assets": 0, "human_confirmed": False, "layout_allowed": False,
            "release_eligible": False, "milestone_complete": False, "blockers": list(BLOCKERS),
            "pinout_package_status": "unconfirmed", "license_status": "redistribution-review-pending",
            "module_status": "unavailable", "support_bom_status": "incomplete",
            "limits": "Pinned geometry and exact selected MPN labels only; not a complete circuit or source-reviewed electrical identity"}


def prepare_core_assets(candidate_path, library_root, output):
    candidate_path = Path(candidate_path).absolute()
    source_parent = candidate_path.parent
    output = output_path(source_parent, output)
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    inputs.mkdir()
    for source, name in ((candidate_path, "candidates.json"),
                         (resolve_local(source_parent, "design.json"), "design.json"),
                         (resolve_local(source_parent, "sources.json"), "sources.json")):
        source = resolve_local(source.parent, source.name)
        (inputs / name).write_bytes(source.read_bytes())
    # Freeze every source before constructing any assets, so later edits cannot mix versions.
    candidate, design, blobs, _ = inspect_inputs(inputs, library_root)
    captured = inputs / "libraries"
    for relative, raw in blobs.items():
        path = resolve_local(captured, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    _, _, _, inspected = inspect_inputs(inputs, captured)
    assets = output / "assets"
    assets.mkdir()
    footprint_root = assets / (NAMESPACE + ".pretty")
    footprint_root.mkdir()
    generated, symbols = [], []
    for ref, record, source_part, library, footprint, pins, doc in inspected:
        name, footprint_name = exact_names(record)
        symbols.append(exact_symbol(record, library, doc))
        footprint = exact_footprint(record, footprint)
        footprint_path = footprint_root / (footprint_name + ".kicad_mod")
        footprint_path.write_text(dump_sexpr(footprint) + "\n")
        generated.append(exact_part(ref, record, source_part, pins, output))
    library_path = assets / (NAMESPACE + ".kicad_sym")
    library_path.write_text(dump_sexpr([Atom("kicad_symbol_lib"), [Atom("version"), 20250114],
                                     [Atom("generator"), "pcb_harness_core_assets"], *symbols]) + "\n")
    for part in generated:
        part["symbol"]["sha256"] = sha256(library_path)
    parts = {"schema_version": 1, "parts": generated}
    validate_document("parts", parts)
    for part in generated:
        load_part_assets(part, output)
    write_json(output / "parts.json", parts)
    bom = exact_bom(design, inspected)
    write_json(output / "core-bom.json", bom)
    write_json(output / "support-requirements.json", {"schema_version": 1, "status": "incomplete", "required_categories": SUPPORT})
    (output / "NOTICE.md").write_text("# Local KiCad-derived asset collection\n\n"
        "Attribution: KiCad library contributors. Original bytes and their hashes are retained under inputs/libraries.\n"
        "License: CC-BY-SA-4.0 with KiCad library exception: https://www.kicad.org/libraries/license/\n"
        "Legal code: https://creativecommons.org/licenses/by-sa/4.0/legalcode.en\n\n"
        "Changes: flatten inheritance, rename symbols/footprints, replace Value/Footprint/Datasheet/Description/filter properties.\n"
        "Templates are not substitute MPNs. Electrical pin/package mapping remains unconfirmed.\n"
        "This collection is local, not a publication package. Retain upstream license documents and review attribution before redistribution.\n")
    report = preparation_report()
    write_json(output / "report.json", report)
    hashes = {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob("*")) if p.is_file()}
    write_json(output / "integrity.json", {"schema_version": 1, "artifacts": hashes})
    verify_core_assets(output)
    return report


def verify_core_assets(root):
    root = Path(root)
    manifest = read_json(resolve_local(root, "integrity.json"))
    required = {"parts.json", "core-bom.json", "support-requirements.json", "NOTICE.md", "report.json",
                "inputs/candidates.json", "inputs/design.json", "inputs/sources.json"}
    candidate = read_json(resolve_local(root, "inputs/candidates.json"))
    for record in candidate["parts"]:
        required.update("inputs/libraries/" + p for p in asset_paths(record))
    parts = read_json(resolve_local(root, "parts.json"))
    validate_document("parts", parts)
    for part in parts["parts"]:
        required.update(part[k]["path"] for k in ("symbol", "footprint"))
    if manifest["schema_version"] != 1 or not required <= set(manifest["artifacts"]):
        raise ValueError("incomplete core asset integrity manifest")
    for relative, digest in manifest["artifacts"].items():
        if sha256(resolve_local(root, relative)) != digest:
            raise ValueError(f"core asset hash drift: {relative}")
    _, design, _, inspected = inspect_inputs(root / "inputs", root / "inputs/libraries")
    report = read_json(resolve_local(root, "report.json"))
    if json.dumps(report, sort_keys=True) != json.dumps(preparation_report(), sort_keys=True):
        raise ValueError("core asset preparation cannot approve full-board prerequisites")
    if len(parts["parts"]) != 6 or {p["mpn"] for p in parts["parts"]} != {p[0] for p in POLICY.values()}:
        raise ValueError("prepared core part coverage mismatch")
    part_by_id = {p["id"]: p for p in parts["parts"]}
    if len(part_by_id) != 6:
        raise ValueError("duplicate prepared part identity")
    for ref, record, source_part, library, footprint, pins, doc in inspected:
        expected = exact_part(ref, record, source_part, pins, root)
        expected["symbol"]["sha256"] = sha256(resolve_local(root, expected["symbol"]["path"]))
        part = part_by_id.get(expected["id"])
        if part != expected:
            raise ValueError(f"prepared part differs from captured source identity: {ref}")
        loaded = load_part_assets(part, root)
        if (dump_sexpr(loaded["symbol"]) != dump_sexpr(exact_symbol(record, library, doc))
                or dump_sexpr(loaded["footprint"]) != dump_sexpr(exact_footprint(record, footprint))):
            raise ValueError(f"prepared geometry or symbol properties differ from captured source: {ref}")
    if read_json(resolve_local(root, "core-bom.json")) != exact_bom(design, inspected):
        raise ValueError("prepared core BOM differs from captured inventory")
    if read_json(resolve_local(root, "support-requirements.json")) != {
            "schema_version": 1, "status": "incomplete", "required_categories": SUPPORT}:
        raise ValueError("prepared support requirements differ from unresolved scope")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", default="benchmarks/stm32-communications/core-asset-candidates.json")
    parser.add_argument("--library-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = prepare_core_assets(args.candidates, args.library_root, args.output)
    print(json.dumps({"prepared_part_types": report["prepared_part_types"], "blockers": report["blockers"], "layout_allowed": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
