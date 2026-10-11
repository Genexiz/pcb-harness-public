"""Recovered originals bind derivatives without approving a physical circuit."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from pcb_harness.circuit.bundle import read_json, sha256
from pcb_harness.circuit.sexpr import child, children, dump_sexpr, parse_sexpr, walk

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'benchmarks/stm32-communications/source-recovery/completion-input.json'


@pytest.fixture
def completed(tmp_path):
    from pcb_harness.orchestration.source_completion import capture_source_completion
    spec = read_json(SPEC)
    if not all((ROOT / d['repository_path']).is_file() for d in spec['documents']):
        pytest.skip('original publisher recovery run required for integration test')
    target = tmp_path / 'completion'
    capture_source_completion(SPEC, ROOT, target)
    return target


def test_recovered_sources_bind_mcu_resources_and_never_confirm(completed):
    from pcb_harness.orchestration.source_completion import load_source_completion
    data = load_source_completion(completed)
    assert len(data['documents']['documents']) == 6
    mcu = data['mcu']
    assert (mcu['flash_bytes'], mcu['ram_bytes']) == (65536, 20480)
    assert mcu['physical_pins']['PA11'] == 32
    assert mcu['dma_requests']['SPI2_RX'] == 4
    assert mcu['dma_requests']['USART1_TX'] == 4
    assert mcu['silicon_marking'] is None and mcu['rev_id'] is None
    assert mcu['rev_id_marking_aliases']['0x2003'] == ['Y', 'X', '1', '2', '3']
    facts = data['facts']['facts']
    assert len(facts) >= 25
    assert all(f['status'] == 'unconfirmed' and f['confirmation'] is None for f in facts)
    assert next(f for f in facts if f['id'] == 'STM32F103C8T6:errata')['document_id'] == 'stm32-errata'
    assert data['report']['human_confirmed'] is False
    assert data['report']['release_eligible'] is False


@pytest.mark.parametrize('change', ['source-bytes', 'source-rehash', 'url', 'duplicate',
                                  'page-checks', 'observation', 'confirmation', 'path',
                                  'missing', 'extra', 'boolean-version', 'title'])
def test_source_or_authored_observation_drift_rejected(completed, change):
    from pcb_harness.orchestration.source_completion import load_source_completion
    manifest_path = completed / 'source-manifest.json'
    manifest = read_json(manifest_path)
    doc = manifest['documents'][0]
    source = completed / doc['path']
    if change in ('source-bytes', 'source-rehash'):
        source.write_bytes(b'%PDF-1.4\nforged\n%%EOF\n')
        if change == 'source-rehash': doc['sha256'] = sha256(source); doc['bytes'] = source.stat().st_size
    elif change == 'url': doc['url'] = doc['retrieved_url'] = 'https://example.invalid/source.pdf'
    elif change == 'duplicate': manifest['documents'].append(deepcopy(doc))
    elif change == 'page-checks': (completed / 'page-checks.json').write_text('{}')
    elif change == 'observation':
        path = completed / 'observations-v1.json'; data = read_json(path)
        data['mcu']['flash_bytes'] = 131072; path.write_text(json.dumps(data))
    elif change == 'confirmation': manifest['human_confirmed'] = True
    elif change == 'path': doc['path'] = '../escaped.pdf'
    elif change == 'missing': source.unlink()
    elif change == 'extra': manifest['confirmed'] = True
    elif change == 'boolean-version': manifest['schema_version'] = True
    elif change == 'title': doc['title'] = 'Fabricated incorrect revision/title'
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        load_source_completion(completed)


@pytest.mark.parametrize('change', ['wrong-url', 'confirmation', 'synthetic-hash'])
def test_untrusted_capture_is_rejected_without_optional_original_downloads(tmp_path, change):
    from pcb_harness.orchestration.source_completion import capture_source_completion
    data = read_json(SPEC)
    first = data['documents'][0]
    if change == 'wrong-url': first['url'] = 'https://example.invalid/not-ST'
    elif change == 'confirmation': first['human_confirmed'] = True
    else: first['sha256'] = '0' * 64
    (tmp_path / 'inputs').mkdir()
    source = tmp_path / 'inputs/input.json'; source.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='uncalibrated recovered source capture'):
        capture_source_completion(source, tmp_path / 'absent', tmp_path / 'out')


def test_max3232_correction_replaces_geometry_and_shared_symbol(completed):
    from pcb_harness.orchestration.source_completion import apply_source_completion
    core = ROOT / 'runs/m4/core-assets-2026-10-10'
    if not (core / 'parts.json').exists(): pytest.skip('retained core packet required')
    original = read_json(core / 'parts.json')['parts']
    assets = {p[k]['path']: (core / p[k]['path']).read_bytes() for p in original for k in ('symbol', 'footprint')}
    before = deepcopy(original)
    parts, result, data = apply_source_completion(completed, original, assets)
    assert original == before
    u7 = next(p for p in parts if p['id'] == 'MAX3232IDR')
    assert u7['mpn'] == 'MAX3232IDWR'
    assert u7['package'] == 'SOIC16 DW 7.5x10.3mm pitch1.27'
    footprint = parse_sexpr(result[u7['footprint']['path']].decode())
    pads = {str(p[1]): p for p in children(footprint, 'pad')}
    assert len(pads) == 16
    assert list(map(float, child(pads['1'], 'at')[1:])) == [-4.65, -4.445]
    assert list(map(float, child(pads['16'], 'at')[1:])) == [4.65, -4.445]
    assert all(list(map(float, child(p, 'size')[1:])) == [2.0, 0.6] for p in pads.values())
    library = parse_sexpr(result[u7['symbol']['path']].decode())
    symbol = next(s for s in children(library, 'symbol') if s[1] == 'MAX3232IDR')
    properties = {p[1]: p[2] for p in children(symbol, 'property')}
    assert properties['Value'] == 'MAX3232IDWR'
    assert properties['Footprint'] == u7['footprint_id']
    assert u7['footprint']['path'] != before[4]['footprint']['path']
    assert all(p['symbol']['sha256'] == u7['symbol']['sha256'] for p in parts)
    assert data['rs232_correction']['new_mpn'] == 'MAX3232IDWR'


def test_capture_and_derivatives_are_independent_of_original_inputs(completed):
    from pcb_harness.orchestration.source_completion import verify_source_completion
    assert verify_source_completion(completed)
    path = completed / 'facts.json'; data = read_json(path)
    data['facts'][0]['claim'] = 'false claim'
    path.write_text(json.dumps(data))
    integrity = read_json(completed / 'integrity.json'); integrity['artifacts']['facts.json'] = sha256(path)
    (completed / 'integrity.json').write_text(json.dumps(integrity))
    with pytest.raises(ValueError): verify_source_completion(completed)


@pytest.mark.parametrize('change', ['part-name', 'duplicate-part-pin', 'pad-mapping',
                                  'symbol-mapping', 'symbol-name', 'duplicate-symbol-pin'])
def test_max3232_pinout_evidence_rejects_incompatible_candidate(completed, change):
    from pcb_harness.orchestration.source_completion import apply_source_completion
    core = ROOT / 'runs/m4/core-assets-2026-10-10'
    if not (core / 'parts.json').exists(): pytest.skip('retained core packet required')
    parts = read_json(core / 'parts.json')['parts']
    assets = {p[k]['path']: (core / p[k]['path']).read_bytes() for p in parts for k in ('symbol', 'footprint')}
    part = next(p for p in parts if p['id'] == 'MAX3232IDR')
    if change == 'part-name':
        part['pins'][0]['name'] = 'GND'
    elif change == 'duplicate-part-pin':
        part['pins'].append(deepcopy(part['pins'][0]))
    elif change == 'pad-mapping':
        part['pin_map'][0]['pads'] = ['16']
    elif change == 'symbol-mapping':
        part['pin_map'][0]['symbol_pin'] = '16'
    else:
        import hashlib
        path = part['symbol']['path']
        library = parse_sexpr(assets[path].decode())
        symbol = next(s for s in children(library, 'symbol') if s[1] == 'MAX3232IDR')
        pin = next(walk(symbol, 'pin'))
        if change == 'symbol-name': child(pin, 'name')[1] = 'GND'
        else:
            unit = next(s for s in children(symbol, 'symbol') if children(s, 'pin'))
            unit.append(deepcopy(pin))
        assets[path] = (dump_sexpr(library) + '\n').encode()
        for candidate in parts:
            if candidate['symbol']['path'] == path:
                candidate['symbol']['sha256'] = hashlib.sha256(assets[path]).hexdigest()
    with pytest.raises(ValueError, match='MAX3232.*pin'):
        apply_source_completion(completed, parts, assets)
