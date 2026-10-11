from pathlib import Path
from copy import deepcopy
import pytest
from pcb_harness.circuit.writer import write_project
from pcb_harness.circuit.sexpr import parse_sexpr, children, child
from pcb_harness.circuit.bundle import sha256


@pytest.mark.parametrize("shape", [
    '(pad "" smd rect (at 0 0) (size 1 1) (layers "F.Paste") (net 99 "foreign") (pinfunction "old") (pintype "input"))',
    '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Paste") (net 99 "foreign") (pinfunction "old") (pintype "input"))',
    '(pad "" np_thru_hole circle (at 0 0) (size 1 1) (drill 1) (layers "*.Cu" "*.Mask") (net 99 "foreign") (pinfunction "old") (pintype "input"))',
])
def test_writer_keeps_non_electrical_shapes_without_assigning_nets(valid_bundle, tmp_path, shape):
    bundle, root = valid_bundle
    part = bundle["parts"]["parts"][0]
    path = root / part["footprint"]["path"]
    text = path.read_text().rstrip()
    path.write_text(text[:-1] + "\n" + shape + ")\n")
    part["footprint"]["sha256"] = sha256(path)
    output = tmp_path / "runs/non-electrical"
    write_project(bundle, root, bundle["checklist"], output)
    pcb = parse_sexpr((output / "board.kicad_pcb").read_text())
    for footprint in children(pcb, "footprint"):
        pads = children(footprint, "pad")
        assert len(pads) == 3
        assert not children(pads[-1], "net")
        assert not children(pads[-1], "pinfunction")
        assert not children(pads[-1], "pintype")
        assert all(children(pad, "net") for pad in pads[:2])


def test_writer_preserves_duplicate_copper_ownership_with_stencil_apertures(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    part = bundle["parts"]["parts"][0]
    path = root / part["footprint"]["path"]
    text = path.read_text().rstrip()
    additions = '\n(pad "1" smd rect (at 0 0) (size 1 1) (layers "B.Cu"))'
    additions += '\n(pad "" smd rect (at 0 0) (size 0.4 0.4) (layers "F.Paste"))'
    additions += '\n(pad "" smd rect (at 0 1) (size 0.4 0.4) (layers "F.Paste"))'
    path.write_text(text[:-1] + additions + ")\n")
    part["footprint"]["sha256"] = sha256(path)
    output = tmp_path / "runs/duplicate-copper"
    write_project(bundle, root, bundle["checklist"], output)
    pcb = parse_sexpr((output / "board.kicad_pcb").read_text())
    for footprint in children(pcb, "footprint"):
        pads = children(footprint, "pad")
        contacts = [pad for pad in pads if pad[1] == "1"]
        assert len(contacts) == 2
        assert child(contacts[0], "net") == child(contacts[1], "net")
        apertures = [pad for pad in pads if pad[1] == ""]
        assert len(apertures) == 2
        assert all(not children(pad, "net") for pad in apertures)


def test_writer_refuses_failed_upstream_review(circuit_case, tmp_path):
    bundle, root, checklist = circuit_case("wrong_pinout")
    output = tmp_path / "runs/project"
    with pytest.raises(ValueError, match="circuit review"):
        write_project(bundle, root, checklist, output)
    assert not output.exists()


def test_writer_preserves_caller_positions_and_adds_no_copper(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    output = tmp_path / "runs/project"
    write_project(bundle, root, bundle["checklist"], output)
    pcb = parse_sexpr((output / "board.kicad_pcb").read_text())
    assert not any(children(pcb, key) for key in ("segment", "via", "zone"))
    assert [[float(x) for x in child(fp, "at")[1:]] for fp in children(pcb, "footprint")] == [[20,20],[40,20],[60,20]]
    assert children(pcb, "net")[1] == ["net", "1", "/NET_A"]


def test_repeat_serialization_has_stable_native_ids(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    outputs = [tmp_path / "runs/a", tmp_path / "runs/b"]
    for output in outputs:
        write_project(bundle, root, bundle["checklist"], output)
    for filename in ("board.kicad_sch", "board.kicad_pcb"):
        assert (outputs[0] / filename).read_bytes() == (outputs[1] / filename).read_bytes()


def test_writer_refuses_existing_output_without_change(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    output = tmp_path / "runs/project"
    output.mkdir(parents=True)
    (output / "sentinel").write_text("user data")
    with pytest.raises(FileExistsError):
        write_project(bundle, root, bundle["checklist"], output)
    assert (output / "sentinel").read_text() == "user data"


def test_writer_rejects_symlink_and_non_run_output(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    (tmp_path / "runs").symlink_to(tmp_path / "outside")
    for output in (tmp_path / "runs/project", tmp_path / "unscoped"):
        with pytest.raises(ValueError):
            write_project(bundle, root, bundle["checklist"], output)


def test_quoted_values_are_serialized_as_single_properties(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    bundle["circuit"]["instances"][0]["value"] = '1k "quoted" \\ literal'
    output = tmp_path / "runs/escaped"
    write_project(bundle, root, bundle["checklist"], output)
    sch = parse_sexpr((output / "board.kicad_sch").read_text())
    values = [prop[2] for prop in children(children(sch,"symbol")[0],"property") if prop[1]=="Value"]
    assert values == ['1k "quoted" \\ literal']


def test_multiple_local_asset_libraries_written(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    other = deepcopy(bundle["parts"]["parts"][0])
    other.update(id="other",symbol_id="Other:R",footprint_id="Other:Probe_R")
    bundle["parts"]["parts"].append(other)
    bundle["circuit"]["instances"][2]["part_id"] = "other"
    bundle["checklist"]["expected_instances"][2]["footprint_id"] = "Other:Probe_R"
    output = tmp_path / "runs/multi-library"
    write_project(bundle, root, bundle["checklist"], output)
    assert (output / "Other.kicad_sym").is_file()
    assert (output / "Other.pretty/Probe_R.kicad_mod").is_file()
    table = parse_sexpr((output / "sym-lib-table").read_text())
    assert {child(lib,"name")[1] for lib in children(table,"lib")} == {"Harness","Other"}


def test_source_notes_wrap_to_readable_lines(valid_bundle, tmp_path):
    bundle, root = valid_bundle
    output = tmp_path / "runs/notes"
    write_project(bundle, root, bundle["checklist"], output)
    schematic = parse_sexpr((output/"board.kicad_sch").read_text())
    for note in children(schematic,"text"):
        assert len(note[1].splitlines()) >= 3
        assert all(len(line)<=24 for line in note[1].splitlines())


def test_large_schematic_selects_sheet_that_contains_caller_symbols(valid_bundle, tmp_path):
    bundle,root=valid_bundle
    bundle['circuit']['instances'][0]['schematic_position_mm']=[800,450]
    output=tmp_path/'runs/large'
    write_project(bundle,root,bundle['checklist'],output)
    sch=parse_sexpr((output/'board.kicad_sch').read_text())
    assert child(sch,'paper')[1]=='A1'


def test_review_serializer_moves_labels_outward_from_pin_with_wire(valid_bundle,tmp_path):
    from pcb_harness.circuit.writer import build_review_schematic
    bundle,root=valid_bundle
    sch=build_review_schematic(bundle,root)
    assert len(children(sch,'wire'))==6
    assert child(children(sch,'label')[0],'effects')[-1][0]=='justify'


def test_review_serializer_does_not_admit_project_write(valid_bundle,tmp_path):
    from pcb_harness.circuit.writer import build_review_schematic
    bundle,root=valid_bundle
    bundle['circuit']['errata_mitigations']=[]
    bundle['checklist']['required_errata_ids']=['unresolved-real-erratum']
    tree=build_review_schematic(bundle,root)
    assert child(tree,'title_block')[1][1]=='DRAFT - CIRCUIT REVIEW ONLY'
    assert len(children(tree,'symbol'))==3
    with pytest.raises(ValueError,match='circuit review'):
        write_project(bundle,root,bundle['checklist'],tmp_path/'runs/not-admitted')
    assert not (tmp_path/'runs/not-admitted').exists()


def test_stacked_pins_share_one_readable_label_and_keep_all_pin_ids(valid_bundle,tmp_path):
    bundle,root=valid_bundle
    from pcb_harness.circuit.writer import build_review_schematic
    part=bundle['parts']['parts'][0]; p=root/part['symbol']['path'];s=p.read_text()
    # Make pin2 coincide with pin1, as USB-C duplicate supply contacts do.
    s=s.replace('(at 0 -3.81 90)','(at 0 3.81 270)');p.write_text(s);part['symbol']['sha256']=sha256(p)
    for n in bundle['circuit']['nets']:
        n['name']='/ONE_NET'
    sch=build_review_schematic(bundle,root)
    assert len(children(sch,'label'))==3
    assert all(len(children(symbol,'pin'))==2 for symbol in children(sch,'symbol'))


def test_review_label_wires_reject_unintended_contact_before_serialization(valid_bundle):
    from pcb_harness.circuit.writer import build_review_schematic
    bundle,root=valid_bundle
    bundle['circuit']['instances'][0]['schematic_position_mm']=[50.8,50.8]
    bundle['circuit']['instances'][1]['schematic_position_mm']=[50.8,63.5]
    with pytest.raises(ValueError,match='label wire'):build_review_schematic(bundle,root)
