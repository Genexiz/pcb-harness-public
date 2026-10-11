"""Real PNG/pixel checks and native CLI export; no fake rasterizer."""
import importlib
from pathlib import Path
import io
import pytest
from PIL import Image
from pcb_harness.contracts import HarnessError

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures/capability/board.kicad_pcb'
SVG='<svg xmlns="http://www.w3.org/2000/svg" width="60mm" height="20mm" viewBox="10 10 60 20"><rect x="10" y="10" width="60" height="20" fill="#111827"/><rect x="18.5" y="19.5" width="1" height="1" fill="#C83434"/></svg>'


def renderer():
    spec=importlib.util.find_spec('pcb_harness.rendering')
    assert spec,'visual renderer missing'
    return importlib.import_module('pcb_harness.rendering')


def render(tmp_path,**kwargs):
    return renderer().render_svg(SVG,[10,10,70,30],[0,0],'revision-1',
        ['F.Cu','Edge.Cuts'],tmp_path,source='test SVG',test_only=True,**kwargs)


def pixel_for(result,x,y):
    mapping=result['board_to_pixel']
    a,b=mapping['board_origin_mm'];px,py=mapping['pixel_origin'];scale=mapping['pixels_per_mm']
    return (round(px+(x-a)*scale),round(py+(y-b)*scale))


def test_actual_png_contains_pad_at_calibrated_coordinate(tmp_path):
    r=render(tmp_path,width_px=800)
    image=Image.open(io.BytesIO(r['_image_bytes'])).convert('RGB')
    assert image.getpixel(pixel_for(r,19,20))==(200,52,52)
    assert r['revision']=='revision-1' and r['test_only']
    assert r['image']['mime_type']=='image/png' and r['image']['width_px']==800
    assert Path(r['image']['path']).read_bytes()==r['_image_bytes']


def test_region_view_preserves_physical_scale_and_crop_bounds(tmp_path):
    r=render(tmp_path,region_mm=[16,17,24,23],width_px=800)
    assert r['region_mm']==[16,17,24,23]
    image=Image.open(io.BytesIO(r['_image_bytes'])).convert('RGB')
    assert image.getpixel(pixel_for(r,19,20))==(200,52,52)
    origin=r['board_to_pixel']['pixel_origin']
    assert pixel_for(r,16,17)==tuple(origin)


@pytest.mark.parametrize('region',[[24,17,16,23],[16,17,16,23],[0,0,24,23],[16,float('nan'),24,23],[16,17,24],[True,17,24,23]])
def test_invalid_region_refused_without_png(tmp_path,region):
    with pytest.raises(HarnessError):render(tmp_path,region_mm=region)
    assert not (tmp_path/'render.png').exists()


@pytest.mark.parametrize('width',[0,999999,True,1.2])
def test_unbounded_or_invalid_pixel_size_refused(tmp_path,width):
    with pytest.raises(HarnessError):render(tmp_path,width_px=width)


@pytest.mark.parametrize('unsafe',['<image href="file:///etc/passwd"/>','<image href="https://example.com/x.png"/>',
    '<rect fill="url(file:///etc/other.svg)"/>','<script>doSomething()</script>','<style>@import url(https://example.com/style.css);</style>'])
def test_unsafe_external_or_active_svg_refused(tmp_path,unsafe):
    svg=SVG.replace('</svg>',unsafe+'</svg>')
    with pytest.raises(HarnessError):renderer().render_svg(svg,[10,10,70,30],[0,0],'rev',['F.Cu'],tmp_path)
    assert not (tmp_path/'render.png').exists()


def test_actual_native_cli_saved_fixture_export_and_pad_pixel(tmp_path):
    r=renderer().export_saved_board(FIXTURE,[10,10,70,30],'fixture-revision',
        ['F.Cu','B.Cu'],tmp_path/'native',width_px=1000)
    assert r['source']=='saved KiCad board' and 'Edge.Cuts' in r['layers']
    assert r['board_to_svg_offset_mm']==pytest.approx([-10.0,-10.0],abs=0.0002)
    image=Image.open(io.BytesIO(r['_image_bytes'])).convert('RGB')
    assert image.getpixel(pixel_for(r,19,20))==(200,52,52)
    assert (tmp_path/'native/raw.svg').exists()


def test_wrong_native_outline_mapping_is_refused(tmp_path):
    with pytest.raises(HarnessError):renderer().export_saved_board(FIXTURE,[11,10,71,30],
        'wrong-bounds',['F.Cu'],tmp_path/'wrong')
    assert not (tmp_path/'wrong/render.png').exists()
