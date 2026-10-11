"""Deterministic single-sheet, caller-positioned KiCad project serialization."""
from copy import deepcopy
from pathlib import Path
import json
import math
import re
import shutil
import textwrap
import uuid

from .assets import electrical_pad, load_part_assets
from .bundle import resolve_local, sha256, referenced_paths
from .review import review_circuit
from .sexpr import Atom, child, children, dump_sexpr
from pcb_harness.fabrication.compiler import compile_rules
from pcb_harness.fabrication.profile import review_profile


def node(key, *values):
    return [Atom(key), *values]


def stable_uuid(circuit_id, object_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"pcb-harness/m3/{circuit_id}/{object_id}"))


def output_path(root, output):
    root, output = Path(root).absolute(), Path(output).absolute()
    if ".." in output.parts or any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("unsafe output path")
    workspace = next((parent for parent in (root, *root.parents) if (parent / "pyproject.toml").is_file()), root.parent)
    if not output.is_relative_to(workspace / "runs"):
        raise ValueError("output must be inside this workspace's runs directory")
    if output.exists():
        raise FileExistsError("refusing existing project output")
    return output


def schematic_tree(bundle, assets, *, outward_labels=False):
    def effects(size=1.27):
        return node('effects',node('font',node('size',size,size)))
    circuit = bundle['circuit']
    parts = {part['id']: part for part in bundle['parts']['parts']}
    uid = lambda key: stable_uuid(circuit['id'], key)
    sheet = uid('sheet')
    symbols = []
    for identifier, part in parts.items():
        symbol = deepcopy(assets[identifier]["symbol"])
        symbol[1] = part["symbol_id"]
        symbols.append(symbol)
    # Caller coordinates are preserved; expand the drawing sheet, never shrink
    # the circuit or quietly clip a large real-target review schematic.
    max_x = max(instance['schematic_position_mm'][0] + 35 for instance in circuit['instances'])
    max_y = max(instance['schematic_position_mm'][1] + 40 for instance in circuit['instances'])
    paper = next((node('paper', name) for name, width, height in
                  [('A4',297,210),('A3',420,297),('A2',594,420),('A1',841,594),('A0',1189,841)]
                  if max_x <= width and max_y <= height), node('paper','User',max_x,max_y))
    sch = node("kicad_sch", node("version", 20250114), node("generator", "pcb_harness_m3"),
        node("uuid", sheet), paper, node("lib_symbols", *symbols))
    endpoint_nets = {(endpoint["instance_id"], endpoint["pin_id"]): net["name"] for net in circuit["nets"] for endpoint in net["endpoints"]}
    if outward_labels:
        # Decorative label wires are real electrical copper in a schematic.
        # Fail before serialization if they could introduce an unintended
        # contact. This is a conservative check, not an automatic wire router.
        wires, pins = [], []
        for instance in circuit['instances']:
            x,y=instance['schematic_position_mm']
            for mapping in parts[instance['part_id']]['pin_map']:
                at=assets[instance['part_id']]['pins'][mapping['symbol_pin']]['at']
                px,py=x+at[0],y-at[1]
                name=endpoint_nets.get((instance['id'],mapping['pin_id']))
                pin_net=name or f"NC:{instance['id']}:{mapping['pin_id']}"
                pins.append((pin_net,px,py,px,py))
                if name:
                    angle=at[2]%360
                    if angle not in (0,90,180,270):raise ValueError('unsupported label wire angle')
                    radians=math.radians(angle)
                    wires.append((name,px,py,round(px-5.08*math.cos(radians),6),round(py+5.08*math.sin(radians),6)))
        for index,a in enumerate(wires):
            for b in wires[index+1:]+pins:
                if a[0]==b[0]:continue
                overlaps=(max(min(a[1],a[3]),min(b[1],b[3])) <= min(max(a[1],a[3]),max(b[1],b[3]))+1e-6
                          and max(min(a[2],a[4]),min(b[2],b[4])) <= min(max(a[2],a[4]),max(b[2],b[4]))+1e-6)
                if overlaps:raise ValueError(f'label wire would contact a different net: {a[0]} / {b[0]}')
    for instance in circuit["instances"]:
        part = parts[instance["part_id"]]
        asset = assets[instance["part_id"]]
        x, y = instance["schematic_position_mm"]
        symbol_id = uid("symbol/" + instance["id"])
        symbol = node("symbol", node("lib_id", part["symbol_id"]), node("at", x, y, 0), node("unit", 1),
            node("in_bom", Atom("yes")), node("on_board", Atom("yes")), node("dnp", Atom("no")), node("uuid", symbol_id))
        props = {"Reference": instance["ref"], "Value": instance["value"], "Footprint": part["footprint_id"]}
        library_props = {prop[1]:prop[2] for prop in children(asset["symbol"],"property")}
        props.update({name:library_props.get(name,"") for name in ("Datasheet","Description")})
        for name, value in props.items():
            original = next((prop for prop in children(asset['symbol'],'property') if prop[1] == name), None)
            at = child(original,'at') if original else ['at',0,0,0]
            prop_effects = deepcopy(child(original,'effects')) if original and children(original,'effects') else effects()
            property_node = node("property", name, value, node("at", x+float(at[1]), y-float(at[2]), 0), prop_effects)
            if name not in ("Reference","Value"):
                property_node.append(node("hide", Atom("yes")))
            symbol.append(property_node)
        labeled = set()
        for mapping in part["pin_map"]:
            symbol.append(node("pin", mapping["symbol_pin"], node("uuid", uid(f"pin/{instance['id']}/{mapping['pin_id']}"))))
            at = asset["pins"][mapping["symbol_pin"]]["at"]
            px, py = x + at[0], y - at[1]
            name = endpoint_nets.get((instance["id"], mapping["pin_id"]))
            if name:
                key = (px,py,name)
                if key in labeled:
                    continue
                labeled.add(key)
                angle = at[2] % 360
                radians = math.radians(angle)
                lx, ly = (round(px-5.08*math.cos(radians),6), round(py+5.08*math.sin(radians),6)) if outward_labels else (px,py)
                if outward_labels:
                    sch.append(node('wire',node('pts',node('xy',px,py),node('xy',lx,ly)),
                                    node('stroke',node('width',0),node('type',Atom('default'))),
                                    node('uuid',uid(f"wire/{instance['id']}/{mapping['pin_id']}"))))
                label_effects = effects(1.0)
                label_effects.append(node('justify',Atom('right' if angle in (0,270) else 'left'),Atom('bottom')))
                sch.append(node("label", name[1:], node("at", lx, ly, 90 if angle in (90,270) else 0), label_effects, node("uuid", uid(f"label/{instance['id']}/{mapping['pin_id']}"))))
            else:
                sch.append(node("no_connect", node("at", px, py), node("uuid", uid(f"nc/{instance['id']}/{mapping['pin_id']}"))))
        symbol.append(node("instances", node("project", "board", node("path", f"/{sheet}", node("reference", instance["ref"]), node("unit", 1)))))
        sch.append(symbol)
        source_note = "\n".join(textwrap.fill(line,width=24) for line in (
            instance["block"],part["mpn"],f"sources: {', '.join(instance['fact_ids'])}"))
        sch.append(node("text", source_note,
            node("at", x, y+10, 0), effects(0.8), node("uuid", uid("note/"+instance["id"]))))
    sch.extend([node('sheet_instances', node('path', '/', node('page', '1'))), node('embedded_fonts', Atom('no'))])
    return sch


def build_review_schematic(bundle, root):
    """Return a visibly marked schematic tree; never admit/export a PCB project.

    Schema and pin/pad consistency are checked. Functional/provenance/native
    failures intentionally remain available for review, not changed to passes.
    """
    from .bundle import validate_document
    for kind in ('parts','circuit'):
        validate_document(kind, bundle[kind])
    assets = {p['id']: load_part_assets(p, root) for p in bundle['parts']['parts']}
    sch = schematic_tree(bundle, assets, outward_labels=True)
    sch.append(node('title_block',node('title','DRAFT - CIRCUIT REVIEW ONLY'),
                    node('comment',1,'Unconfirmed components/sources; layout and fabrication prohibited')))
    return sch


def write_project(bundle, root, checklist, output):
    output = output_path(root, output)
    review = review_circuit(bundle, root, checklist)
    if not review["passed"]:
        raise ValueError(f"circuit review failed: {review['issues']}")
    profile = review_profile(bundle["fabrication"], bundle["facts"])
    if not profile["passed"]:
        raise ValueError(f"fabrication profile failed: {profile['issues']}")
    compiled = compile_rules(bundle["fabrication"], bundle["constraints"])
    circuit = bundle["circuit"]
    board = bundle["requirements"]["board"]
    if board["layers"] != bundle["fabrication"]["layers"] or board["thickness_mm"] != bundle["fabrication"]["thickness_mm"]:
        raise ValueError("board and fabrication stackup differ")
    parts = {part["id"]: part for part in bundle["parts"]["parts"]}
    assets = {identifier: load_part_assets(part, root) for identifier, part in parts.items()}
    for part in parts.values():
        for identifier in (part["symbol_id"], part["footprint_id"]):
            if not re.fullmatch(r"[A-Za-z0-9_]+:[A-Za-z0-9_.+-]+", identifier):
                raise ValueError("unsupported asset library identifier")
    if any(net["net_class"] != "Default" or not re.fullmatch(r"/[A-Za-z0-9_.+-]+", net["name"]) for net in circuit["nets"]):
        raise ValueError("initial writer supports root-sheet named nets and Default class only")
    for instance in circuit["instances"]:
        x, y = instance["bootstrap_position_mm"]
        if not (10 <= x <= 10 + board["width_mm"] and 10 <= y <= 10 + board["height_mm"]):
            raise ValueError("caller bootstrap position outside rectangular board")
    uid = lambda key: stable_uuid(circuit["id"], key)
    sheet = uid("sheet")
    sch = schematic_tree(bundle, assets)
    layers = [(0,"F.Cu","signal"),(2,"B.Cu","signal"),(13,"F.Paste","user"),(15,"B.Paste","user"),
        (5,"F.SilkS","user"),(7,"B.SilkS","user"),(1,"F.Mask","user"),(3,"B.Mask","user"),
        (25,"Edge.Cuts","user"),(31,"F.CrtYd","user"),(29,"B.CrtYd","user"),(35,"F.Fab","user"),(33,"B.Fab","user")]
    if board["layers"] == 4:
        layers[1:1] = [(4,"In1.Cu","signal"),(6,"In2.Cu","signal")]
    pcb = node("kicad_pcb", node("version", 20241229), node("generator", "pcb_harness_m3"),
        node("general", node("thickness", board["thickness_mm"])), node("paper", "A4"),
        node("layers", *[[index, name, Atom(kind)] for index, name, kind in layers]), node("setup", node("pad_to_mask_clearance", 0)), node("net", 0, ""))
    net_numbers = {net["name"]: number for number, net in enumerate(circuit["nets"], 1)}
    endpoint_nets = {(endpoint["instance_id"], endpoint["pin_id"]): net["name"] for net in circuit["nets"] for endpoint in net["endpoints"]}
    no_connect_nets = {}
    for endpoint in circuit["no_connect"]:
        instance = next(instance for instance in circuit["instances"] if instance["id"] == endpoint["instance_id"])
        pin = next(pin for pin in parts[instance["part_id"]]["pins"] if pin["id"] == endpoint["pin_id"])
        pin_name = f"-{pin['name']}" if pin["name"] else ""
        name = f"unconnected-({instance['ref']}{pin_name}-Pad{pin['number']})"
        no_connect_nets[(instance["id"],pin["id"])] = name
        net_numbers[name] = len(net_numbers) + 1
    for name, number in net_numbers.items():
        pcb.append(node("net", number, name))
    pcb.append(node("gr_rect", node("start", 10, 10), node("end", 10 + board["width_mm"], 10 + board["height_mm"]),
        node("stroke", node("width", 0.05), node("type", Atom("default"))), node("fill", Atom("none")), node("layer", "Edge.Cuts"), node("uuid", uid("outline"))))
    def effects(size=1.27):
        return node("effects", node("font", node("size", size, size)))
    for instance in circuit["instances"]:
        part = parts[instance["part_id"]]
        asset = assets[instance["part_id"]]
        symbol_id = uid('symbol/' + instance['id'])
        props = {'Reference': instance['ref'], 'Value': instance['value'], 'Footprint': part['footprint_id']}
        props.update({p[1]:p[2] for p in children(asset['symbol'],'property') if p[1] in ('Datasheet','Description')})
        footprint = deepcopy(asset["footprint"])
        footprint[1] = part["footprint_id"]
        footprint[:] = [entry for entry in footprint if not isinstance(entry,list) or entry[0] not in ("version","generator","at","uuid","path")]
        footprint.extend([node("uuid", uid("footprint/"+instance["id"])), node("at", *instance["bootstrap_position_mm"]), node("path", f"/{sheet}/{symbol_id}")])
        for prop in children(footprint, "property"):
            if prop[1] == "Reference":
                prop[2] = instance["ref"]
            elif prop[1] == "Value":
                prop[2] = instance["value"]
            elif prop[1] in props:
                prop[2] = props[prop[1]]
        for pad in children(footprint, "pad"):
            pad[:] = [entry for entry in pad if not isinstance(entry,list) or entry[0] not in ("net","pinfunction","pintype")]
            if not electrical_pad(pad):
                continue
            mapping = next(mapping for mapping in part["pin_map"] if str(pad[1]) in mapping["pads"])
            pin = next(pin for pin in part["pins"] if pin["id"] == mapping["pin_id"])
            key = (instance["id"],pin["id"])
            name = endpoint_nets.get(key, no_connect_nets.get(key,""))
            pad.extend([node("net", net_numbers.get(name,0), name), node("pinfunction",pin["name"]), node("pintype",pin["type"])])
        pcb.append(footprint)
    # All validation and serialization completes before creating output.
    sch_text, pcb_text = dump_sexpr(sch)+"\n", dump_sexpr(pcb)+"\n"
    output.mkdir(parents=True, exist_ok=False)
    (output / "board.kicad_sch").write_text(sch_text)
    (output / "board.kicad_pcb").write_text(pcb_text)
    (output / "board.kicad_pro").write_text(json.dumps(compiled["settings"],indent=2)+"\n")
    (output / "board.kicad_dru").write_text(compiled["rules"])
    symbol_libs, footprint_libs = {}, {}
    for part in parts.values():
        namespace = part["symbol_id"].split(":")[0]
        target = output / f"{namespace}.kicad_sym"
        if namespace in symbol_libs and symbol_libs[namespace] != part["symbol"]["sha256"]:
            raise ValueError("conflicting symbol library assets")
        shutil.copy2(resolve_local(root, part["symbol"]["path"]), target)
        symbol_libs[namespace] = part["symbol"]["sha256"]
        namespace, name = part["footprint_id"].split(":")
        target = output / f"{namespace}.pretty/{name}.kicad_mod"
        target.parent.mkdir(exist_ok=True)
        if target.exists() and sha256(target) != part["footprint"]["sha256"]:
            raise ValueError("conflicting footprint assets")
        shutil.copy2(resolve_local(root, part["footprint"]["path"]), target)
        footprint_libs[namespace] = True
    for filename, libraries, kind, suffix in (("sym-lib-table",symbol_libs,"symbol",".kicad_sym"),("fp-lib-table",footprint_libs,"footprint",".pretty")):
        table = node("sym_lib_table" if kind=="symbol" else "fp_lib_table", node("version",7))
        for namespace in libraries:
            table.append(node("lib",node("name",namespace),node("type","KiCad"),node("uri",f"${{KIPRJMOD}}/{namespace}{suffix}"),node("options",""),node("descr","M3 audited assets")))
        (output/filename).write_text(dump_sexpr(table)+"\n")
    input_root = output / "inputs"
    input_root.mkdir()
    for kind, data in {**bundle,"checklist":checklist}.items():
        (input_root/f"{kind}.json").write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+"\n")
    for relative in referenced_paths(bundle):
        destination = input_root / relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(resolve_local(root,relative),destination)
    (output/"circuit-review.json").write_text(json.dumps(review,indent=2)+"\n")
    (output/"fabrication-review.json").write_text(json.dumps(profile,indent=2)+"\n")
    (output/"rule-compilation.json").write_text(json.dumps(compiled,indent=2)+"\n")
    hashes = {str(path.relative_to(output)):sha256(path) for path in output.rglob("*") if path.is_file()}
    manifest = {"schema_version":1,"input_sha256":review["input_sha256"],"output_sha256":hashes,
        "board_origin_mm":[10,10],"routed":False,"release_eligible":False}
    (output/"bootstrap-manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    return manifest
