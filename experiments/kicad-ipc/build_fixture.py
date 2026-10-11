"""Disposable M0 native-file fixture, not a production schematic writer.

Three parallel passive resistors; pin 1=NET_A, pin 2=NET_B.
All placement/routes below are explicit probe inputs, not algorithmic routing.
Run only when the fixture is closed in KiCad; refuses existing output.
"""
from pathlib import Path
import json
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fixtures/capability"


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "pcb-harness/m0/" + name))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if any(OUT.iterdir()):
        raise FileExistsError(f'refusing to overwrite any existing fixture artifact: {OUT}')
    (OUT / "Harness.pretty").mkdir(exist_ok=True)
    symbol = '''(symbol "R"
      (pin_names (offset 0)) (in_bom yes) (on_board yes)
      (property "Reference" "R" (at 2 0 90) (effects (font (size 1.27 1.27))))
      (property "Value" "R" (at 0 0 90) (effects (font (size 1.27 1.27))))
      (property "Footprint" "Harness:Probe_R" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "M0 passive resistor fixture" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "R_0_1" (rectangle (start -1 -2.54) (end 1 2.54)
        (stroke (width 0.254) (type default)) (fill (type none))))
      (symbol "R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27)
          (name "" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 0 -3.81 90) (length 1.27)
          (name "" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      ))'''
    (OUT / "Harness.kicad_sym").write_text(
        '(kicad_symbol_lib (version 20250114) (generator "pcb_harness_m0")\n' + symbol + ')\n')
    (OUT / "sym-lib-table").write_text(
        '(sym_lib_table (version 7) (lib (name "Harness") (type "KiCad") '
        '(uri "${KIPRJMOD}/Harness.kicad_sym") (options "") (descr "M0 fixture")))\n')
    (OUT / "fp-lib-table").write_text(
        '(fp_lib_table (version 7) (lib (name "Harness") (type "KiCad") '
        '(uri "${KIPRJMOD}/Harness.pretty") (options "") (descr "M0 fixture")))\n')
    sheet = uid("sheet")
    embedded_symbol = symbol.replace('(symbol "R"', '(symbol "Harness:R"', 1)
    sch = [f'(kicad_sch (version 20250114) (generator "pcb_harness_m0") '
           f'(uuid "{sheet}") (paper "A4") '
           f'(lib_symbols {embedded_symbol})']
    for i, x in enumerate([50.8, 81.28, 111.76], start=1):
        sch.append(f'''(symbol (lib_id "Harness:R") (at {x} 50.8 0) (unit 1)
          (in_bom yes) (on_board yes) (dnp no) (uuid "{uid(f'symbol-{i}')}")
          (property "Reference" "R{i}" (at {x+3} 49 0) (effects (font (size 1.27 1.27))))
          (property "Value" "1k" (at {x+3} 51 0) (effects (font (size 1.27 1.27))))
          (property "Footprint" "Harness:Probe_R" (at {x} 50 0) (effects (font (size 1.27 1.27)) (hide yes)))
          (property "Datasheet" "" (at {x} 50 0) (effects (font (size 1.27 1.27)) (hide yes)))
          (property "Description" "M0 passive resistor fixture" (at {x} 50 0) (effects (font (size 1.27 1.27)) (hide yes)))
          (pin "1" (uuid "{uid(f'pin-{i}-1')}")) (pin "2" (uuid "{uid(f'pin-{i}-2')}"))
          (instances (project "board" (path "/{sheet}" (reference "R{i}") (unit 1)))))''')
        for net, y in [("NET_A", 46.99), ("NET_B", 54.61)]:
            sch.append(f'(label "{net}" (at {x} {y} 0) '
                       f'(effects (font (size 1.27 1.27)) (justify left bottom)) '
                       f'(uuid "{uid(f"label-{i}-{net}")}"))')
    sch.append('(sheet_instances (path "/" (page "1"))) (embedded_fonts no))')
    (OUT / "board.kicad_sch").write_text('\n'.join(sch) + '\n')
    common_fp = '''(property "Reference" "REF**" (at 0 -2 0) (layer "F.SilkS")
        (effects (font (size 1 1) (thickness 0.15))))
      (property "Value" "Probe_R" (at 0 2 0) (layer "F.Fab")
        (effects (font (size 1 1) (thickness 0.15))))
      (property "Description" "M0 passive resistor fixture" (at 0 0 0) (layer "F.Fab")
        (hide yes) (effects (font (size 1 1) (thickness 0.15))))
      (attr smd)
      (fp_rect (start -2 -1.4) (end 2 1.4) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))
      (fp_rect (start -0.4 -0.5) (end 0.4 0.5) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))
      (pad "1" smd rect (at -1 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask"))
      (pad "2" smd rect (at 1 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask"))'''
    (OUT / "Harness.pretty/Probe_R.kicad_mod").write_text(
        '(footprint "Probe_R" (version 20241229) (generator "pcb_harness_m0") '
        '(layer "F.Cu")\n' + common_fp + ')\n')
    pcb = ['''(kicad_pcb (version 20241229) (generator "pcb_harness_m0")
      (general (thickness 1.6)) (paper "A4")
      (layers (0 "F.Cu" signal) (2 "B.Cu" signal)
        (13 "F.Paste" user) (15 "B.Paste" user)
        (5 "F.SilkS" user "F.Silkscreen") (7 "B.SilkS" user "B.Silkscreen")
        (1 "F.Mask" user) (3 "B.Mask" user)
        (25 "Edge.Cuts" user) (31 "F.CrtYd" user "F.Courtyard") (29 "B.CrtYd" user "B.Courtyard")
        (35 "F.Fab" user) (33 "B.Fab" user))
      (setup (pad_to_mask_clearance 0))
      (net 0 "") (net 1 "NET_A") (net 2 "NET_B")
      (gr_rect (start 10 10) (end 70 30) (stroke (width 0.05) (type default))
        (fill none) (layer "Edge.Cuts") (uuid "''' + uid("outline") + '"))']
    for i, x in enumerate([20, 40, 60], start=1):
        fp = common_fp.replace('"REF**"', f'"R{i}"').replace('"Probe_R"', '"1k"')
        fp = fp.replace('(layers "F.Cu" "F.Paste" "F.Mask"))',
            '(layers "F.Cu" "F.Paste" "F.Mask") (net 1 "NET_A") (pinfunction "") (pintype "passive"))', 1)
        last_pad = '(pad "2" smd rect (at 1 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask"))'
        fp = fp.replace(last_pad, last_pad[:-1] + ' (net 2 "NET_B") (pinfunction "") (pintype "passive"))')
        pcb.append(f'(footprint "Harness:Probe_R" (layer "F.Cu") '
                   f'(uuid "{uid(f"footprint-{i}")}") (at {x} 20) '
                   f'(path "/{sheet}/{uid(f"symbol-{i}")}") {fp})')
    def track(name, a, b, layer, net):
        return (f'(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                f'(width 0.4) (layer "{layer}") (net {net}) (uuid "{uid(name)}"))')
    for i, x in enumerate([20, 40, 60], start=1):
        pcb.append(track(f'a-{i}', (x-1,20), (x-1,15), 'F.Cu', 1))
        pcb.append(track(f'b-{i}', (x+1,20), (x+1,25), 'F.Cu', 2))
        pcb.append(f'(via (at {x+1} 25) (size 0.6) (drill 0.3) '
                   f'(layers "F.Cu" "B.Cu") (net 2) (uuid "{uid(f"via-{i}")}"))')
    pcb.append(track('a-bus', (19,15), (59,15), 'F.Cu', 1))
    pcb.append(track('b-bus', (21,25), (61,25), 'B.Cu', 2))
    pcb.append(')')
    board_text = '\n'.join(pcb).replace('"NET_A"', '"/NET_A"').replace('"NET_B"', '"/NET_B"')
    (OUT / "board.kicad_pcb").write_text(board_text + '\n')
    project = {"meta": {"filename": "board.kicad_pro", "version": 1},
        "board": {"design_settings": {"rules": {
            "min_clearance": 0.2, "min_track_width": 0.2,
            "min_through_hole_diameter": 0.2, "min_via_diameter": 0.5,
            "min_copper_edge_clearance": 0.5}}},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.2,
            "track_width": 0.4, "via_diameter": 0.6, "via_drill": 0.3}], "version": 4}}
    (OUT / "board.kicad_pro").write_text(json.dumps(project, indent=2) + '\n')
    (OUT / "board.kicad_dru").write_text('''(version 1)
(rule "M0 minimum routing width"
  (condition "A.Type == 'Track'") (constraint track_width (min 0.2mm)))
''')
    print(OUT)


if __name__ == '__main__':
    main()
