"""Fixture-only SVG coordinate/layer/crop calibration against IPC geometry.

Native colors/path forms are observed KiCad 10.0.0 output, not a general renderer
contract. The crop is a Harness SVG viewBox; IPC remains the geometry authority.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {'svg': 'http://www.w3.org/2000/svg'}
COLORS = {'F.Cu': '#C83434', 'B.Cu': '#4D7FC4', 'Edge.Cuts': '#D0D2CD'}


def points(path):
    numbers = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', path)]
    return list(zip(numbers[::2], numbers[1::2]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--svg', type=Path, required=True)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    tree = ET.parse(args.svg)
    root = tree.getroot()
    geometry = json.loads(args.geometry.read_text())
    if any(node.get('transform') not in (None, 'translate(0 0) scale(1 1)') for node in root.iter()):
        raise ValueError('unrecognized SVG transform; calibration refused')
    groups = root.findall('svg:g', NS)
    def paths(color, stroke=False):
        property_name = 'stroke:' if stroke else 'fill:'
        token = property_name + color + ';'
        result = []
        for group in groups:
            for path in group.findall('svg:path', NS):
                own_style = path.get('style', '')
                effective = own_style if property_name in own_style else group.get('style', '')
                if token in effective:
                    result.append(path)
        return result
    outlines = paths(COLORS['Edge.Cuts'], stroke=True)
    if len(outlines) != 1:
        raise ValueError('expected one native rectangular outline')
    outline = points(outlines[0].get('d', ''))
    offset = [outline[0][0] - 10, outline[0][1] - 10]
    def mapped(xy):
        return tuple(round(xy[i] + offset[i], 4) for i in (0, 1))
    expected_outline = [mapped(p) for p in [(10,10),(70,10),(70,30),(10,30)]]
    if outline != expected_outline:
        raise ValueError('outline units/orientation mismatch')
    copper_paths = paths(COLORS['F.Cu'])
    pad_centers = []
    for path in copper_paths:
        vertices = points(path.get('d', ''))
        if len(vertices) != 4:
            raise ValueError('expected rectangular fixture pad')
        pad_centers.append(tuple(round(sum(p[i] for p in vertices) / 4, 4) for i in (0,1)))
    expected_pads = [mapped(p['xy_mm']) for f in geometry['footprints'] for p in f['pads']]
    if sorted(pad_centers) != sorted(expected_pads):
        raise ValueError('SVG pad centers disagree with IPC')
    native_layers = {'F.Cu': 3, 'B.Cu': 34}
    for layer, native_id in native_layers.items():
        observed = sorted(tuple(points(p.get('d', ''))) for p in paths(COLORS[layer], stroke=True))
        expected = sorted((mapped(t['start_mm']), mapped(t['end_mm']))
            for t in geometry['tracks'] if t['layer'] == native_id)
        if observed != expected:
            raise ValueError(f'{layer} track endpoints disagree with IPC')
    # Crop around R1, retaining the native scene and physical scale.
    crop = [16, 17, 24, 23]
    x, y = mapped(crop[:2])
    root.set('viewBox', f'{x} {y} 8 6')
    root.set('width', '8mm')
    root.set('height', '6mm')
    ET.register_namespace('', NS['svg'])
    tree.write(output/'r1-crop.svg', encoding='utf-8', xml_declaration=True)
    report = {'status':'passed', 'scope':'KiCad 10.0.0 rectangular M0 fixture only',
        'svg_sha256':hashlib.sha256(args.svg.read_bytes()).hexdigest(),
        'geometry_sha256':hashlib.sha256(args.geometry.read_bytes()).hexdigest(),
        'board_to_svg_offset_mm':offset, 'axis':'x right, y down; 1 SVG unit = 1 mm',
        'checked_pads':len(expected_pads), 'checked_tracks':len(geometry['tracks']),
        'layers':COLORS, 'crop_board_mm':crop, 'crop_svg_viewbox':[x,y,8,6],
        'limitation':'no arbitrary shapes, rotations, raster pixel calibration or net overlay'}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('SVG calibration: PASS; six pad centers, eight tracks, outline and R1 crop')


if __name__ == '__main__':
    main()
