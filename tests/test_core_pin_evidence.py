"""Synthetic inventories test binding/gates; no manufacturer truth is assumed."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from test_core_asset_preparation import candidate_case
from pcb_harness.circuit.bundle import read_json, sha256
from pcb_harness.orchestration.core_assets import prepare_core_assets


def write(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def pin_case(candidate_case):
    candidates, libraries, core = candidate_case
    # The production runner discovers its workspace via pyproject.toml.
    (core.parent.parent / 'pyproject.toml').write_text('# synthetic test workspace\n')
    prepare_core_assets(candidates, libraries, core)
    benchmark = candidates.parent
    observations = read_json(Path(__file__).resolve().parents[1] /
                             'benchmarks/stm32-communications/core-pin-observations.json')
    lock = read_json(benchmark / 'sources.json')
    sources = benchmark / 'sources'
    sources.mkdir()
    core_docs = {p['source_id'] for p in observations['parts']}
    for doc in lock['documents']:
        doc['status'] = 'unavailable'
        if doc['id'] in core_docs and doc['id'] != 'stm32-ds':
            path = sources / doc['path']
            path.write_bytes(b'%PDF-1.4\nsynthetic-envelope-not-a-real-datasheet\n%%EOF\n')
            doc.update(status='retrieved', sha256=sha256(path), retrieved_url=doc['url'])
    docs = {d['id']: d for d in lock['documents']}
    for part in observations['parts']:
        part['source_sha256'] = docs[part['source_id']].get('sha256')
        part['pins'] = [dict(number='1', manufacturer_name='SYNTHETIC-IN', symbol_name='IN'),
                        dict(number='2', manufacturer_name='SYNTHETIC-OUT', symbol_name='OUT')]
        part['notes'] = 'Synthetic observations; not manufacturer pinout evidence.'
    opath, lpath = benchmark / 'observations.json', benchmark / 'sources.lock.json'
    write(opath, observations)
    write(lpath, lock)
    return core, opath, lpath, sources, core.parent / 'pins'


def prepare(case):
    from pcb_harness.orchestration.core_pin_evidence import prepare_pin_evidence
    return prepare_pin_evidence(*case)


def test_candidate_facts_bind_sources_and_never_confirm(pin_case):
    from pcb_harness.orchestration.core_pin_evidence import verify_pin_evidence
    report = prepare(pin_case)
    assert report['source_bound_part_types'] == 5
    assert report['source_bound_pin_count'] == 10
    assert report['unavailable_source_parts'] == ['STM32F103C8T6']
    assert report['accepted_real_target_assets'] == 0
    assert report['layout_allowed'] is False
    assert report['release_eligible'] is False
    facts = read_json(pin_case[-1] / 'facts.json')['facts']
    assert len(facts) == 10
    assert all(f['status'] == 'unconfirmed' and f['confirmation'] is None for f in facts)
    assert not any(f['document_id'] == 'stm32-ds' for f in facts)
    assert verify_pin_evidence(pin_case[-1])


@pytest.mark.parametrize('change', ['missing-part', 'duplicate-part', 'missing-pin', 'duplicate-pin',
                                   'wrong-alias', 'wrong-package', 'wrong-source', 'wrong-url',
                                   'wrong-hash', 'confirmation', 'extra-field', 'boolean-version',
                                   'wrong-package-code'])
def test_observation_admission_rejects_ambiguous_or_unbound_inputs(pin_case, change):
    data = read_json(pin_case[1])
    p = data['parts'][1]
    if change == 'missing-part': data['parts'].pop()
    elif change == 'duplicate-part': data['parts'].append(deepcopy(p))
    elif change == 'missing-pin': p['pins'].pop()
    elif change == 'duplicate-pin': p['pins'].append(deepcopy(p['pins'][0]))
    elif change == 'wrong-alias': p['pins'][0]['symbol_name'] = 'OUT'
    elif change == 'wrong-package': p['package'] = 'VDFN14'
    elif change == 'wrong-source': p['source_id'] = 'buck'
    elif change == 'wrong-url': p['source_url'] = 'https://wrong.invalid/doc'
    elif change == 'wrong-hash': p['source_sha256'] = '0' * 64
    elif change == 'confirmation': data['human_confirmed'] = True
    elif change == 'extra-field': p['confirmed'] = True
    elif change == 'boolean-version': data['schema_version'] = True
    elif change == 'wrong-package-code': p['package_code'] = 'QBB'
    write(pin_case[1], data)
    with pytest.raises((ValueError, OSError)): prepare(pin_case)


@pytest.mark.parametrize('change', ['bytes', 'html', 'missing', 'symlink', 'unavailable-hash', 'lock-url'])
def test_source_integrity_failures_reject(pin_case, change):
    lock = read_json(pin_case[2])
    doc = next(d for d in lock['documents'] if d['id'] == 'mcp2518fd')
    path = pin_case[3] / doc['path']
    if change == 'bytes': path.write_bytes(b'%PDF-1.4\nmodified\n%%EOF')
    elif change == 'html':
        path.write_bytes(b'<html>not PDF</html>')
        doc['sha256'] = sha256(path)
        obs = read_json(pin_case[1]); obs['parts'][1]['source_sha256'] = doc['sha256']; write(pin_case[1], obs)
    elif change == 'missing': path.unlink()
    elif change == 'symlink':
        target = path.with_suffix('.original'); path.rename(target); path.symlink_to(target)
    elif change == 'unavailable-hash':
        next(d for d in lock['documents'] if d['id'] == 'stm32-ds')['sha256'] = '0' * 64
    elif change == 'lock-url': doc['url'] = 'https://wrong.invalid/doc'
    write(pin_case[2], lock)
    with pytest.raises((ValueError, OSError)): prepare(pin_case)


@pytest.mark.parametrize('artifact', ['report.json', 'facts.json', 'pin-comparison.json'])
def test_derived_semantic_drift_rejects_even_with_updated_hash(pin_case, artifact):
    from pcb_harness.orchestration.core_pin_evidence import verify_pin_evidence
    prepare(pin_case)
    root = pin_case[-1]; path = root / artifact; data = read_json(path)
    if artifact == 'report.json': data['accepted_real_target_assets'] = 5
    elif artifact == 'facts.json': data['facts'][0]['claim'] = 'unrelated false claim'
    else: data['parts'][0]['pins'][0]['manufacturer_name'] = 'WRONG'
    write(path, data)
    manifest = read_json(root / 'integrity.json'); manifest['artifacts'][artifact] = sha256(path)
    write(root / 'integrity.json', manifest)
    with pytest.raises(ValueError): verify_pin_evidence(root)


def test_original_edits_do_not_change_frozen_packet(pin_case):
    from pcb_harness.orchestration.core_pin_evidence import verify_pin_evidence
    prepare(pin_case)
    pin_case[1].write_text('{}'); pin_case[2].write_text('{}')
    (pin_case[0] / 'parts.json').write_text('{}')
    for p in pin_case[3].glob('*.pdf'): p.write_bytes(b'changed')
    assert verify_pin_evidence(pin_case[-1])


def test_required_manifest_entries_cannot_be_removed(pin_case):
    from pcb_harness.orchestration.core_pin_evidence import verify_pin_evidence
    prepare(pin_case); root = pin_case[-1]
    manifest = read_json(root / 'integrity.json'); manifest['artifacts'].pop('facts.json')
    (root / 'facts.json').unlink(); write(root / 'integrity.json', manifest)
    with pytest.raises(ValueError): verify_pin_evidence(root)


def test_reused_or_overlapping_output_rejected(pin_case):
    prepare(pin_case)
    with pytest.raises(FileExistsError): prepare(pin_case)
    with pytest.raises(ValueError): prepare((*pin_case[:-1], pin_case[0] / 'nested'))


def test_capture_completes_before_original_inputs_change(pin_case, monkeypatch):
    from pcb_harness.orchestration import core_pin_evidence
    original = core_pin_evidence.evaluate_packet
    changed = False
    def change_originals(root):
        nonlocal changed
        if not changed:
            changed = True
            pin_case[1].write_text('{}')
            pin_case[2].write_text('{}')
            (pin_case[0] / 'parts.json').write_text('{}')
            for path in pin_case[3].glob('*.pdf'): path.write_bytes(b'changed')
        return original(root)
    monkeypatch.setattr(core_pin_evidence, 'evaluate_packet', change_originals)
    assert prepare(pin_case)['source_bound_part_types'] == 5
    assert core_pin_evidence.verify_pin_evidence(pin_case[-1])


@pytest.mark.parametrize('change', ['boolean-count', 'confirmed-fact', 'removed-blocker'])
def test_derived_status_cannot_overstate_scope(pin_case, change):
    from pcb_harness.orchestration.core_pin_evidence import verify_pin_evidence
    prepare(pin_case); root = pin_case[-1]
    name = 'facts.json' if change == 'confirmed-fact' else 'report.json'
    data = read_json(root / name)
    if change == 'boolean-count': data['accepted_real_target_assets'] = False
    elif change == 'removed-blocker': data['blockers'].remove('SUPPORT_BOM')
    else:
        f = data['facts'][0]; f['status'] = 'confirmed'
        f['confirmation'] = {'reviewer': 'invented', 'document_sha256': f['document_sha256']}
    write(root / name, data)
    manifest = read_json(root / 'integrity.json'); manifest['artifacts'][name] = sha256(root / name)
    write(root / 'integrity.json', manifest)
    with pytest.raises(ValueError): verify_pin_evidence(root)


@pytest.mark.parametrize('url', [None, 'https://wrong.invalid/not-publisher.pdf'])
def test_retrieved_source_requires_calibrated_publisher_url(pin_case, url):
    lock = read_json(pin_case[2])
    doc = next(d for d in lock['documents'] if d['id'] == 'mcp2518fd')
    if url is None: doc.pop('retrieved_url')
    else: doc['retrieved_url'] = url
    write(pin_case[2], lock)
    with pytest.raises(ValueError, match='retrieved publisher URL'): prepare(pin_case)


def test_source_confirmation_metadata_is_strictly_boolean(pin_case):
    lock = read_json(pin_case[2])
    next(d for d in lock['documents'] if d['id'] == 'mcp2518fd')['human_confirmed'] = 0
    write(pin_case[2], lock)
    with pytest.raises(ValueError, match='source metadata drift'): prepare(pin_case)
