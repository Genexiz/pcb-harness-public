import pytest
from pcb_harness.circuit.assets import load_part_assets
from pcb_harness.circuit.sexpr import parse_sexpr, dump_sexpr
from pcb_harness.circuit.bundle import sha256


def test_actual_symbol_and_pad_numbers_audited(valid_bundle):
    bundle, root = valid_bundle
    assets = load_part_assets(bundle["parts"]["parts"][0], root)
    assert set(assets["pins"]) == {"1", "2"}
    assert assets["pad_numbers"] == ["1", "2"]


@pytest.mark.parametrize("change", ["hash", "missing_pad", "omitted_pin", "wrong_package", "unknown_type"])
def test_corrupt_or_incomplete_asset_identity_rejected(valid_bundle, change):
    bundle, root = valid_bundle
    part = bundle["parts"]["parts"][0]
    if change == "hash":
        part["footprint"]["sha256"] = "0" * 64
    elif change == "missing_pad":
        part["pin_map"][0]["pads"] = ["99"]
    elif change == "omitted_pin":
        part["pin_map"].pop()
    elif change == "wrong_package":
        part["footprint_id"] = "Harness:Other"
    else:
        part["pins"][0]["type"] = "magic"
    with pytest.raises(ValueError):
        load_part_assets(part, root)


def test_duplicate_physical_pads_with_same_number_are_preserved(valid_bundle):
    bundle, root = valid_bundle
    part = bundle["parts"]["parts"][0]
    path = root / part["footprint"]["path"]
    text = path.read_text().rstrip()
    path.write_text(text[:-1] + '\n(pad "1" smd rect (at -2 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask")))\n')
    part["footprint"]["sha256"] = sha256(path)
    assert load_part_assets(part, root)["pad_numbers"] == ["1", "2", "1"]


@pytest.mark.parametrize("shape", [
    '(pad "" smd rect (at 0 0) (size 1 1) (layers "F.Paste"))',
    '(pad "" np_thru_hole circle (at 0 0) (size 1 1) (drill 1) (layers "*.Cu" "*.Mask"))',
])
def test_non_electrical_pad_shapes_do_not_require_a_logical_pin(valid_bundle, shape):
    bundle, root = valid_bundle
    part = bundle["parts"]["parts"][0]
    path = root / part["footprint"]["path"]
    text = path.read_text().rstrip()
    path.write_text(text[:-1] + "\n" + shape + ")\n")
    part["footprint"]["sha256"] = sha256(path)
    assets = load_part_assets(part, root)
    assert assets["pad_numbers"] == ["1", "2"]
    assert len([n for n in assets["footprint"] if isinstance(n, list) and n[0] == "pad"]) == 3


@pytest.mark.parametrize("number", ["", "99"])
def test_unnumbered_or_unmapped_copper_pad_is_still_rejected(valid_bundle, number):
    bundle, root = valid_bundle
    part = bundle["parts"]["parts"][0]
    path = root / part["footprint"]["path"]
    text = path.read_text().rstrip()
    path.write_text(text[:-1] + f'\n(pad "{number}" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))\n')
    part["footprint"]["sha256"] = sha256(path)
    with pytest.raises(ValueError):
        load_part_assets(part, root)


@pytest.mark.parametrize("pads", [["1", "2"], ["1", "1"]])
def test_physical_pad_has_one_logical_owner(valid_bundle, pads):
    bundle, root = valid_bundle
    part = bundle["parts"]["parts"][0]
    part["pin_map"][0]["pads"] = pads
    with pytest.raises(ValueError, match="mapping"):
        load_part_assets(part, root)


def test_quoted_strings_round_trip():
    node = parse_sexpr('(root "quotes \\" and \\\\ slash" "line\\nnext")')
    assert parse_sexpr(dump_sexpr(node)) == node
    assert node[2] == "line\nnext"


@pytest.mark.parametrize("text", ['(root "truncated)', '(root', '(root))', '(root) (other)'])
def test_malformed_sexpr_rejected(text):
    with pytest.raises(ValueError):
        parse_sexpr(text)
