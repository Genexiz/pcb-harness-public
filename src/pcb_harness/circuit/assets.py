"""Audit actual symbol pins and physical footprint pads against part declarations."""
from collections import Counter
from .bundle import resolve_local, sha256, validate_document
from .sexpr import parse_sexpr, children, child, walk


def electrical_pad(pad):
    """Copper contacts need pin ownership; stencil openings and NPTH do not."""
    return pad[2] != "np_thru_hole" and any(
        str(layer).endswith(".Cu") for layer in child(pad, "layers")[1:])


def load_part_assets(part, root):
    validate_document("parts", {"schema_version": 1, "parts": [part]})
    trees = {}
    for kind in ("symbol", "footprint"):
        path = resolve_local(root, part[kind]["path"])
        if sha256(path) != part[kind]["sha256"]:
            raise ValueError(f"{kind} asset hash mismatch")
        trees[kind] = parse_sexpr(path.read_text())
    library = trees["symbol"]
    symbols = [symbol for symbol in children(library, "symbol")
        if symbol[1] == part["symbol_id"].split(":")[-1]]
    footprint = trees["footprint"]
    if library[0] != "kicad_symbol_lib" or len(symbols) != 1:
        raise ValueError("symbol asset identity mismatch")
    if footprint[0] != "footprint" or footprint[1] != part["footprint_id"].split(":")[-1]:
        raise ValueError("footprint asset identity mismatch")
    pins = {}
    for pin in walk(symbols[0], "pin"):
        number = str(child(pin, "number")[1])
        if number in pins:
            raise ValueError("unsupported repeated symbol pin number")
        pins[number] = {"type": str(pin[1]), "name": str(child(pin, "name")[1]),
            "at": [float(value) for value in child(pin, "at")[1:]]}
    pads = [str(pad[1]) for pad in children(footprint, "pad") if electrical_pad(pad)]
    if "" in pads:
        raise ValueError("unnumbered electrical copper pad")
    declared = {pin["id"]: pin for pin in part["pins"]}
    mappings = part["pin_map"]
    if (len(declared) != len(part["pins"])
            or Counter(mapping["pin_id"] for mapping in mappings) != Counter(declared.keys())
            or Counter(mapping["symbol_pin"] for mapping in mappings) != Counter(pins.keys())
            or Counter(pad for mapping in mappings for pad in mapping["pads"]) != Counter(set(pads))):
        raise ValueError("incomplete pin/symbol/pad mapping")
    for mapping in mappings:
        pin = declared[mapping["pin_id"]]
        actual = pins[mapping["symbol_pin"]]
        if pin["number"] != mapping["symbol_pin"] or pin["type"] != actual["type"] or pin["name"] != actual["name"]:
            raise ValueError("declared pin differs from actual symbol")
    return {"symbol": symbols[0], "footprint": footprint, "pins": pins, "pad_numbers": pads}
