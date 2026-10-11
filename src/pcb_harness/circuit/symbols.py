"""Flatten explicit KiCad inheritance without inferring pins or circuitry."""
from copy import deepcopy
import re
from .sexpr import Atom, children, child, walk


def flatten_symbol(library, name, new_name, properties=None):
    if not library or library[0] != "kicad_symbol_lib":
        raise ValueError("expected KiCad symbol library")
    if not isinstance(new_name, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]+", new_name):
        raise ValueError("unsafe standalone symbol name")
    properties = {} if properties is None else properties
    if not isinstance(properties, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str)
                                              for k, v in properties.items()):
        raise ValueError("symbol property overrides must be strings")
    definitions = children(library, "symbol")
    symbols = {s[1]: s for s in definitions}
    if len(symbols) != len(definitions):
        raise ValueError("duplicate library symbol")
    lineage, visited = [], set()
    while True:
        if name in visited or name not in symbols:
            raise ValueError("missing or cyclic symbol ancestor")
        visited.add(name)
        current = symbols[name]
        lineage.append(current)
        parents = children(current, "extends")
        if not parents:
            break
        if len(parents) != 1 or len(parents[0]) != 2:
            raise ValueError("ambiguous symbol parent")
        name = parents[0][1]
    providers = [s for s in lineage if children(s, "symbol")]
    if len(providers) != 1:
        raise ValueError("ambiguous or missing inherited geometry")
    provider = providers[0]
    units = deepcopy(children(provider, "symbol"))
    names = set()
    for unit in units:
        prefix = str(provider[1])
        suffix = str(unit[1])[len(prefix):] if str(unit[1]).startswith(prefix) else ""
        if not re.fullmatch(r"_[0-9]+_[0-9]+", suffix) or suffix in names:
            raise ValueError("malformed or duplicate symbol unit")
        names.add(suffix)
        unit[1] = new_name + suffix
    numbers = [str(child(pin, "number")[1]) for unit in units for pin in walk(unit, "pin")]
    if not numbers or "" in numbers or len(set(numbers)) != len(numbers):
        raise ValueError("missing or repeated symbol pin")
    props, attributes = {}, {}
    for ancestor in lineage:
        seen = set()
        for prop in children(ancestor, "property"):
            # KiCad private is an unquoted flag before the field name, not
            # a property literally named "private".
            private = isinstance(prop[1], Atom) and prop[1] == 'private'
            key = prop[2] if private else prop[1]
            if key in seen:
                raise ValueError("duplicate symbol property")
            seen.add(key)
            props.setdefault(key, deepcopy(prop))
        seen = set()
        for entry in ancestor[2:]:
            if not isinstance(entry, list) or entry[0] in ("property", "symbol", "extends"):
                continue
            if entry[0] in seen:
                raise ValueError("duplicate symbol attribute")
            seen.add(entry[0])
            attributes.setdefault(entry[0], deepcopy(entry))
    for key, value in properties.items():
        if key not in props:
            props[key] = [Atom("property"), key, value, [Atom("at"), 0, 0, 0],
                          [Atom("effects"), [Atom("font"), [Atom("size"), 1.27, 1.27]], [Atom("hide"), Atom("yes")]]]
        index = 3 if isinstance(props[key][1],Atom) and props[key][1] == 'private' else 2
        props[key][index] = value
    return [Atom("symbol"), new_name, *attributes.values(), *props.values(), *units]
