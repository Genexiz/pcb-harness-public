import importlib.util
from copy import deepcopy
from pathlib import Path
import json
import subprocess
import shutil
from hashlib import sha256

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'benchmarks/stm32-communications/support-qualified'
SOURCES_PRESENT = all((ROOT / d['path']).is_file()
                      for d in json.loads((DATA / 'sources.json').read_text())['documents']
                      if d.get('status') == 'retrieved')
needs_sources = pytest.mark.skipif(not SOURCES_PRESENT,
                                   reason='retained manufacturer support sources (ignored runs/) unavailable')


def candidate():
    return json.loads((DATA / 'base-topology.json').read_text())


def test_support_qualification_producer_exists():
    assert importlib.util.find_spec('pcb_harness.orchestration.support_qualification') is not None


@needs_sources
def test_patch_preserves_core_and_confirmation_and_isolates_shared_miso():
    from pcb_harness.orchestration import support_qualification as support
    original = candidate()
    before = deepcopy(original)
    result = support.qualify_support(original, ROOT)
    assert original == before
    top = result['topology']
    items = {p['ref']: p for p in top['instances']}
    assert top['human_confirmed'] is original['human_confirmed']
    assert top['layout_allowed'] is original['layout_allowed']
    assert top['interfaces'] == original['interfaces']
    assert items['U10']['pins'] == {'1':'EXTERNAL_SPI_CS','2':'EXTERNAL_SPI_MISO_PORT','3':'GND','4':'SHARED_MISO','5':'3V3'}
    assert items['J10']['pins']['2'] == 'EXTERNAL_SPI_MISO_PORT'
    assert items['U9']['pins']['15'] == 'VBUS_PRESENT_N'
    assert 'Q2' not in items
    assert items['R12']['pins']['1'] == '3V3'
    assert items['Y1']['pins']['3'] == 'HSE_IN'
    assert items['U1']['pins']['6'] is None
    assert items['U2']['pins']['5'] is None
    assert result['bom']['items']
    assert not result['hardware_verified']


@needs_sources
def test_source_tamper_is_rejected(tmp_path):
    from pcb_harness.orchestration import support_qualification as support
    catalog = json.loads((DATA / 'catalog.json').read_text())
    sources = json.loads((DATA / 'sources.json').read_text())
    sources['documents'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='source hash'):
        support.verify_support_sources(catalog, sources, ROOT)


def test_part_package_substitution_is_rejected():
    from pcb_harness.orchestration import support_qualification as support
    catalog = json.loads((DATA / 'catalog.json').read_text())
    catalog['parts']['MISO_BUFFER']['pin_functions']['1'] = 'VCC'
    with pytest.raises(ValueError, match='pin semantics'):
        support.verify_pin_semantics(catalog)


@needs_sources
def test_conflicting_added_reference_is_rejected():
    from pcb_harness.orchestration import support_qualification as support
    top = candidate()
    top['instances'].append({'ref':'U9','part_id':'something','pins':{}})
    with pytest.raises(ValueError, match='reference conflict'):
        support.qualify_support(top, ROOT)


@needs_sources
def test_missing_shared_cs_pullup_is_rejected():
    from pcb_harness.orchestration import support_qualification as support
    top = candidate()
    for p in top['instances']:
        if p['ref'] == 'R26':
            p['pins']['2'] = 'GND'
    with pytest.raises(ValueError, match='CS pullup'):
        support.qualify_support(top, ROOT)


@needs_sources
def test_capture_freezes_sources_assets_and_rejects_later_tamper(tmp_path):
    from pcb_harness.orchestration import support_qualification as support
    packet = tmp_path / 'packet'
    report = support.capture_support(candidate(), ROOT, packet)
    checked = support.verify_support(packet)
    assert checked['topology'] == report['topology']
    assert (packet / report['engineering_analysis']['module_source']['path']).is_file()
    source = next(packet.glob('runs/m4/support-qualification-*/sources/*.pdf'))
    source.write_bytes(b'%PDF altered')
    with pytest.raises(ValueError, match='integrity'):
        support.verify_support(packet)


def test_exact_asset_pin_sets_and_efuse_lands_match_catalog():
    from pcb_harness.orchestration import support_qualification as support
    from pcb_harness.circuit.sexpr import parse_sexpr, children, child
    assets = support.support_asset_bytes(ROOT)
    assert 'symbols/SupportQualified.kicad_sym' in assets
    lib = parse_sexpr(assets['symbols/SupportQualified.kicad_sym'].decode())
    symbols = {s[1]:s for s in children(lib, 'symbol')}
    assert 'INPUT_EFUSE' in symbols
    fp = parse_sexpr(assets['footprints/SupportQualified.pretty/TPS25947_RPW0010A.kicad_mod'].decode())
    pad5 = [p for p in children(fp,'pad') if p[1]=='5']
    assert len(pad5) == 1
    assert [float(v) for v in child(pad5[0],'size')[1:]] == [.3,2.4]


@needs_sources
def test_rail_bound_includes_current_limit_tolerance_and_forward_drop():
    from pcb_harness.orchestration import support_qualification as support
    analysis = support.qualify_support(candidate(), ROOT)['engineering_analysis']
    expected = 3.3 * .965 - (.575 / .99) * .045 - .0169
    assert analysis['wiz_rail']['worst_static_min_v'] == pytest.approx(expected)
    assert expected > analysis['wiz_rail']['wiz_required_min_v']
    assert analysis['current_limits']['wiz_branch']['design_min_a'] > .420
    assert analysis['thermal']['buck']['efficiency_is_guaranteed'] is False


def test_native_kicad_loads_source_reviewed_support_library(tmp_path):
    cli = Path('/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
    if not cli.exists():
        pytest.skip('native KiCad unavailable')
    result = subprocess.run([str(cli),'sym','export','svg','-o',str(tmp_path / 'svg'),
                             str(DATA / 'library/symbols/SupportQualified.kicad_sym')],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert list((tmp_path / 'svg').glob('*.svg'))


def test_verifier_rejects_rehashed_library_with_bare_property_hide(tmp_path):
    from pcb_harness.orchestration import support_qualification as support
    copied = tmp_path / support.DATA
    shutil.copytree(DATA, copied)
    library = copied / 'library/symbols/SupportQualified.kicad_sym'
    library.write_text(library.read_text().replace('(hide yes)', 'hide', 1))
    manifest = json.loads((copied / 'integrity.json').read_text())
    manifest['artifacts']['library/symbols/SupportQualified.kicad_sym'] = sha256(library.read_bytes()).hexdigest()
    (copied / 'integrity.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='native property syntax'):
        support.support_asset_bytes(tmp_path)


def rehash_packet_file(packet, relative):
    data_rel = 'benchmarks/stm32-communications/support-qualified'
    inner = packet / data_rel / 'integrity.json'
    manifest = json.loads(inner.read_text())
    manifest['artifacts'][relative] = sha256((packet / data_rel / relative).read_bytes()).hexdigest()
    inner.write_text(json.dumps(manifest))
    outer = packet / 'integrity.json'
    manifest = json.loads(outer.read_text())
    for rel in [data_rel + '/' + relative, data_rel + '/integrity.json']:
        manifest['artifacts'][rel] = sha256((packet / rel).read_bytes()).hexdigest()
    outer.write_text(json.dumps(manifest))


@needs_sources
@pytest.mark.parametrize('change', ['missing', 'wrong_mpn', 'wrong_value', 'duplicate'])
def test_rehashed_support_bom_must_match_qualified_instances(tmp_path, change):
    from pcb_harness.orchestration import support_qualification as support
    packet = tmp_path / 'packet'
    support.capture_support(candidate(), ROOT, packet)
    file = packet / support.DATA / 'bom.json'
    bom = json.loads(file.read_text())
    if change == 'missing':
        bom['items'].pop()
    elif change == 'duplicate':
        bom['items'].append(deepcopy(bom['items'][0]))
    else:
        bom['items'][0]['mpn' if change == 'wrong_mpn' else 'value'] = 'incorrect'
    file.write_text(json.dumps(bom))
    rehash_packet_file(packet, 'bom.json')
    with pytest.raises(ValueError, match='support BOM'):
        support.verify_support(packet)


def test_incomplete_authoring_manifest_cannot_drop_engineering_analysis(tmp_path):
    from pcb_harness.orchestration import support_qualification as support
    copied = tmp_path / support.DATA
    shutil.copytree(DATA, copied)
    manifest = json.loads((copied / 'integrity.json').read_text())
    del manifest['artifacts']['engineering-analysis.json']
    (copied / 'integrity.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='support authoring inventory'):
        support.support_asset_bytes(tmp_path)


@needs_sources
def test_vbus_isolation_rejects_base_sense_transistor_rewiring():
    from pcb_harness.orchestration import support_qualification as support
    top = candidate()
    next(p for p in top['instances'] if p['ref'] == 'Q1')['pins']['2'] = '3V3'
    with pytest.raises(ValueError, match='support electrical connection'):
        support.qualify_support(top, ROOT)


@needs_sources
def test_current_limits_disclose_datasheet_test_voltage_at_selected_rails():
    from pcb_harness.orchestration import support_qualification as support
    analysis = support.qualify_support(candidate(), ROOT)['engineering_analysis']
    for key, rail in [('wiz_branch', 3.3), ('system_input', 5.0)]:
        bound = analysis['current_limits'][key]
        assert bound['datasheet_test_input_v'] == 12
        assert bound['selected_input_nominal_v'] == rail
        assert bound['guaranteed_at_selected_voltage'] is False
        assert 'guaranteed_data_min_a' not in bound


def test_selected_voltage_current_limit_guarantee_is_derived_not_authored(tmp_path):
    from hashlib import sha256 as digest
    from pcb_harness.orchestration.support_qualification import qualify_current_limits
    limit = {'part': 'TPS259470ARPWR', 'datasheet_test_input_v': 12, 'selected_input_nominal_v': 3.3,
             'guaranteed_at_selected_voltage': True}
    with pytest.raises(ValueError, match='current-limit guarantee'):
        qualify_current_limits({'current_limits': {'wiz_branch': dict(limit)}}, {'documents': []}, tmp_path)
    limit['guaranteed_at_selected_voltage'] = False
    derived = qualify_current_limits({'current_limits': {'wiz_branch': dict(limit)}}, {'documents': []}, tmp_path)
    assert derived['current_limits']['wiz_branch']['guaranteed_at_selected_voltage'] is False
    same = dict(limit, datasheet_test_input_v=3.3)
    derived = qualify_current_limits({'current_limits': {'wiz_branch': same}}, {'documents': []}, tmp_path)
    assert derived['current_limits']['wiz_branch']['guaranteed_at_selected_voltage'] is True
    raw = b'%PDF-1.7 vendor applicability %%EOF'
    (tmp_path / 'vendor.pdf').write_bytes(raw)
    docs = {'documents': [{'id': 'vendor', 'path': 'vendor.pdf', 'status': 'retrieved',
                           'sha256': digest(raw).hexdigest()}]}
    applied = dict(limit, vendor_applicability={'document_id': 'vendor', 'selected_input_v': 3.3,
                                                'locator': 'letter p1'})
    derived = qualify_current_limits({'current_limits': {'wiz_branch': applied}}, docs, tmp_path)
    assert derived['current_limits']['wiz_branch']['guaranteed_at_selected_voltage'] is True
    (tmp_path / 'vendor.pdf').write_bytes(raw + b' ')
    with pytest.raises(ValueError, match='applicability source hash'):
        qualify_current_limits({'current_limits': {'wiz_branch': applied}}, docs, tmp_path)
    wrong = dict(limit, vendor_applicability={'document_id': 'vendor', 'selected_input_v': 5.0, 'locator': 'p1'})
    (tmp_path / 'vendor.pdf').write_bytes(raw)
    assert qualify_current_limits({'current_limits': {'wiz_branch': wrong}}, docs, tmp_path)[
        'current_limits']['wiz_branch']['guaranteed_at_selected_voltage'] is False


def test_support_facts_are_derived_bound_and_unconfirmed():
    from pcb_harness.orchestration.support_qualification import support_facts
    from pcb_harness.circuit.bundle import validate_document
    catalog = {'parts': {
        'R_X': {'mpn': 'R1', 'manufacturer': 'V', 'procurement': 'component', 'source_ids': ['ds', 'land'],
                'evidence_pages': [1, 3], 'pin_functions': {'1': 'terminal', '2': 'terminal'},
                'footprint_template': 'Resistor_SMD:R_0603', 'note': 'n', 'ratings': {'ohm': 10}},
        'TP': {'mpn': 'TP', 'manufacturer': 'PCB', 'procurement': 'pcb_feature', 'source_ids': [],
               'evidence_pages': [], 'pin_functions': {'1': 'pad'}, 'footprint_template': 'TestPoint:TP',
               'note': 'pad'}}}
    sources = {'documents': [{'id': 'ds', 'sha256': 'a' * 64, 'status': 'retrieved'},
                             {'id': 'land', 'sha256': 'b' * 64, 'status': 'retrieved'}]}
    assets = {'footprints/TestPoint.pretty/TP.kicad_mod': b'(footprint)'}
    facts = support_facts(catalog, sources, assets)
    validate_document('facts', {'schema_version': 1, 'facts': facts})
    by_id = {f['id']: f for f in facts}
    assert set(by_id) == {'R_X:pinout', 'R_X:qualification', 'TP:pinout', 'TP:qualification'}
    assert by_id['R_X:pinout']['document_sha256'] == 'a' * 64 and '1=terminal' in by_id['R_X:pinout']['claim']
    assert by_id['TP:pinout']['document_id'] == 'kicad-footprint:TestPoint:TP'
    assert all(f['status'] == 'unconfirmed' and f['confirmation'] is None and f['critical'] for f in facts)
    sources['documents'][0]['status'] = 'unavailable'
    with pytest.raises(ValueError, match='fact source'):
        support_facts(catalog, sources, assets)
