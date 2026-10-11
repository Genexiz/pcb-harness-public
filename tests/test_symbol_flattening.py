from copy import deepcopy
import pytest
from pcb_harness.circuit.sexpr import parse_sexpr, children, child, walk


def library():
    return parse_sexpr('''(kicad_symbol_lib (version 20250114) (generator "test-only")
      (symbol "Base" (in_bom yes) (on_board yes)
        (property "Value" "Base" (at 0 1 0))
        (property "Footprint" "Test:Old" (at 0 0 0))
        (symbol "Base_0_1" (rectangle (start -1 -1) (end 1 1)))
        (symbol "Base_1_1" (pin input line (at -2 0 0) (length 1)
          (name "IN") (number "1"))))
      (symbol "Mid" (extends "Base") (property "Value" "Mid" (at 0 2 0)))
      (symbol "Child" (extends "Mid") (property "Value" "Child" (at 0 3 0))))''')


def flatten(*args, **kwargs):
    from pcb_harness.circuit.symbols import flatten_symbol
    return flatten_symbol(*args, **kwargs)


def test_flatten_preserves_geometry_and_nearest_properties_without_mutation():
    source = library()
    original = deepcopy(source)
    result = flatten(source, "Child", "Exact", {"Value": "FULL-MPN", "Footprint": "Test:New"})
    assert source == original
    assert result[1] == "Exact"
    assert not children(result, "extends")
    assert {p[1]: p[2] for p in children(result, "property")} == {"Value": "FULL-MPN", "Footprint": "Test:New"}
    assert child(children(result, "property")[0], "at") == ["at", "0", "3", "0"]
    assert [s[1] for s in children(result, "symbol")] == ["Exact_0_1", "Exact_1_1"]
    assert list(walk(result, "pin")) == list(walk(children(original, "symbol")[0], "pin"))
    assert child(result, "in_bom") == ["in_bom", "yes"]


def test_child_value_wins_without_overrides_and_new_properties_can_be_added():
    result = flatten(library(), "Child", "Exact", {"Datasheet": "https://publisher.test/exact.pdf"})
    assert next(p[2] for p in children(result, "property") if p[1] == "Value") == "Child"
    assert next(p[2] for p in children(result, "property") if p[1] == "Datasheet").endswith("exact.pdf")


@pytest.mark.parametrize("change", ["cycle", "missing", "duplicate-symbol", "duplicate-property", "child-geometry", "bad-unit-prefix", "duplicate-pin", "no-geometry"])
def test_ambiguous_or_malformed_inheritance_fails_closed(change):
    source = library()
    base, mid, leaf = children(source, "symbol")
    if change == "cycle":
        child(mid, "extends")[1] = "Child"
    elif change == "missing":
        child(mid, "extends")[1] = "Absent"
    elif change == "duplicate-symbol":
        source.append(deepcopy(base))
    elif change == "duplicate-property":
        leaf.append(deepcopy(children(leaf, "property")[0]))
    elif change == "child-geometry":
        leaf.append(deepcopy(children(base, "symbol")[0]))
    elif change == "bad-unit-prefix":
        children(base, "symbol")[0][1] = "Other_0_1"
    elif change == "duplicate-pin":
        children(base, "symbol")[1].append(deepcopy(list(walk(base, "pin"))[0]))
    else:
        base[:] = [n for n in base if not isinstance(n, list) or n[0] != "symbol"]
    with pytest.raises(ValueError):
        flatten(source, "Child", "Exact")


@pytest.mark.parametrize("name", ["../escape", "bad:name", "", "has space"])
def test_unsafe_asset_names_rejected(name):
    with pytest.raises(ValueError):
        flatten(library(), "Child", name)


def test_private_symbol_fields_keep_distinct_names_and_values():
    source=library()
    base=children(source,'symbol')[0]
    base.extend([parse_sexpr('(property private "KLC_A" "first" (at 0 0 0))'),
                 parse_sexpr('(property private "KLC_B" "second" (at 0 0 0))')])
    result=flatten(source,'Child','Exact')
    private=[p for p in children(result,'property') if p[1]=='private']
    assert [(p[2],p[3]) for p in private]==[('KLC_A','first'),('KLC_B','second')]
    base.append(deepcopy(base[-1]))
    with pytest.raises(ValueError,match='duplicate symbol property'): flatten(source,'Child','Exact')
