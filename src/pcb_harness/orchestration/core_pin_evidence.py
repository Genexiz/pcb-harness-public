"""Bind authored core pin observations to saved assets; never confirm a circuit."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from pcb_harness.circuit.assets import load_part_assets
from pcb_harness.circuit.bundle import read_json, resolve_local, sha256, validate_document
from pcb_harness.circuit.writer import output_path
from pcb_harness.orchestration.core_assets import (
    POLICY, PART_DETAILS, BLOCKERS, verify_core_assets, write_json,
)
from pcb_harness.orchestration.m4 import checked_path, source_format_matches
from pcb_harness.orchestration.stm32_feasibility import obj, array, TEXT

PACKAGE_CODES = {'U1': 'LQFP48', 'U2/U3': 'SL', 'U4/U5': 'SN', 'U6': 'D', 'U7': 'D', 'U8': 'DSG'}
SCHEMA = obj({
    'schema_version': {'type': 'integer', 'const': 1},
    'status': {'const': 'candidate-observations'}, 'human_confirmed': {'const': False},
    'parts': array(obj({
        'ref': TEXT, 'mpn': TEXT, 'package': TEXT, 'source_id': TEXT, 'source_url': TEXT,
        'source_sha256': {'type': ['string', 'null'], 'pattern': '^[a-f0-9]{64}$'},
        'package_code': TEXT, 'pinout_locator': TEXT, 'package_locator': TEXT, 'notes': TEXT,
        'pins': array(obj({'number': {'type': 'string', 'pattern': '^[1-9][0-9]*$'},
                           'manufacturer_name': TEXT, 'symbol_name': TEXT})),
    })),
})


def source_records(core_root, observations, lock):
    """Admit selected publisher revisions; file bytes are checked separately."""
    errors = list(Draft202012Validator(SCHEMA).iter_errors(observations))
    if errors:
        raise ValueError(f'invalid pin observations: {errors[0].message}')
    if type(lock.get('schema_version')) is not int or lock['schema_version'] != 1:
        raise ValueError('invalid source lock version')
    parts = {p['ref']: p for p in observations['parts']}
    if len(parts) != len(observations['parts']) or set(parts) != set(POLICY):
        raise ValueError('incomplete or duplicate core observation inventory')
    specs = read_json(resolve_local(core_root, 'inputs/sources.json'))['documents']
    expected = {d['id']: d for d in specs}
    records = {d['id']: d for d in lock['documents']}
    if len(records) != len(lock['documents']):
        raise ValueError('duplicate source lock identifiers')
    selected, paths = {}, set()
    for ref, p in parts.items():
        package, did, url = PART_DETAILS[ref]
        if (p['mpn'] != POLICY[ref][0] or p['package'] != package or p['source_id'] != did
                or p['source_url'] != url or p['package_code'] != PACKAGE_CODES[ref]):
            raise ValueError(f'uncalibrated pin/package/source identity: {ref}')
        record = records.get(did)
        if record is None or any(json.dumps(record.get(k), sort_keys=True) != json.dumps(v, sort_keys=True)
                                 for k, v in expected[did].items()):
            raise ValueError(f'source metadata drift: {did}')
        if record.get('status') not in ('retrieved', 'unavailable'):
            raise ValueError('unsupported source retrieval status')
        if record['status'] == 'unavailable':
            if record.get('sha256') is not None or p['source_sha256'] is not None:
                raise ValueError('unavailable original source cannot carry a hash')
        else:
            if record.get('retrieved_url') != url:
                raise ValueError(f'retrieved publisher URL differs from calibrated source: {did}')
            if not p['source_sha256'] or record.get('sha256') != p['source_sha256']:
                raise ValueError(f'observation/source revision mismatch: {did}')
        if Path(record['path']).suffix != '.pdf' or record['path'] in paths:
            raise ValueError('core sources must be distinct PDF paths')
        paths.add(record['path'])
        selected[did] = record
    return parts, selected


def evaluate_packet(root):
    """Reconstruct observations and unconfirmed facts from captured evidence."""
    core = root / 'inputs/core'
    verify_core_assets(core)
    observations = read_json(resolve_local(root, 'inputs/observations.json'))
    lock = read_json(resolve_local(root, 'inputs/sources.lock.json'))
    authored, selected = source_records(core, observations, lock)
    prepared = {p['mpn']: p for p in read_json(resolve_local(core, 'parts.json'))['parts']}
    comparisons, facts, missing = [], [], []
    bound_parts, bound_pins = 0, 0
    for ref in POLICY:
        observation = authored[ref]
        part = prepared[observation['mpn']]
        actual = load_part_assets(part, core)
        aliases = {p['number']: p for p in observation['pins']}
        if len(aliases) != len(observation['pins']) or set(aliases) != set(actual['pins']):
            raise ValueError(f'incomplete or duplicate pin observation mapping: {ref}')
        for number, pin in actual['pins'].items():
            if aliases[number]['symbol_name'] != pin['name']:
                raise ValueError(f'authored alias disagrees with actual symbol: {ref}/{number}')
        record = selected[observation['source_id']]
        sourced = record['status'] == 'retrieved'
        if sourced:
            path = resolve_local(root / 'sources', record['path'])
            data = path.read_bytes()
            if (hashlib.sha256(data).hexdigest() != record['sha256']
                    or not source_format_matches(path, data)):
                raise ValueError(f'original source bytes unavailable or drifted: {record["id"]}')
            bound_parts += 1
            bound_pins += len(aliases)
            claims = {
                'pinout': 'Candidate number/name inventory: ' + '; '.join(
                    f'{p["number"]}={p["manufacturer_name"]}' for p in observation['pins']),
                'package': f'Candidate package code {observation["package_code"]}: {observation["package"]}.',
            }
            for kind, claim in claims.items():
                facts.append({'id': part['id'] + ':' + kind, 'document_id': record['id'],
                    'document_sha256': record['sha256'], 'locator': observation[kind + '_locator'],
                    'claim': f'{part["mpn"]}: {claim} {observation["notes"]}',
                    'status': 'unconfirmed', 'critical': True, 'kind': 'identity',
                    'value': None, 'units': None, 'confirmation': None})
        else:
            missing.append(part['mpn'])
        comparisons.append({**deepcopy(observation),
            'source_status': 'hash-bound-observation' if sourced else 'original-unavailable',
            'symbol_pin_count': len(aliases), 'electrical_pad_shape_count': len(actual['pad_numbers']),
            'numbered_aliases_match': True, 'human_confirmed': False})
    fact_document = {'schema_version': 1, 'facts': facts}
    validate_document('facts', fact_document)
    report = {'schema_version': 1, 'milestone': 'M4', 'scope': 'core candidate pin/package evidence',
        'prepared_part_types': 6, 'source_bound_part_types': bound_parts, 'source_bound_pin_count': bound_pins,
        'unavailable_source_parts': missing, 'unconfirmed_identity_facts': len(facts),
        'accepted_real_target_assets': 0, 'human_confirmed': False, 'layout_allowed': False,
        'release_eligible': False, 'milestone_complete': False, 'blockers': list(BLOCKERS),
        'limits': 'Authored candidate aliases match saved symbols and source hashes; not automated PDF semantic extraction, human confirmation, electrical types, land-pattern qualification or full circuit acceptance.'}
    return {'facts.json': fact_document,
            'pin-comparison.json': {'schema_version': 1, 'parts': comparisons}, 'report.json': report}


def prepare_pin_evidence(core_root, observations_path, source_lock_path, source_root, output):
    core_root, observations_path, source_lock_path, source_root = map(
        checked_path, (core_root, observations_path, source_lock_path, source_root))
    output = output_path(core_root, output)
    if any(output.is_relative_to(p) or p.is_relative_to(output)
           for p in (core_root, observations_path.parent, source_lock_path.parent, source_root)):
        raise ValueError('output must not overlap captured inputs')
    verify_core_assets(core_root)
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / 'inputs'
    inputs.mkdir()
    for source, name in ((observations_path, 'observations.json'), (source_lock_path, 'sources.lock.json')):
        (inputs / name).write_bytes(source.read_bytes())
    # Capture the complete verified preparation, including originals, before deriving anything.
    core_manifest = read_json(resolve_local(core_root, 'integrity.json'))
    for relative in ('integrity.json', *core_manifest['artifacts']):
        data = resolve_local(core_root, relative).read_bytes()
        if relative != 'integrity.json' and hashlib.sha256(data).hexdigest() != core_manifest['artifacts'][relative]:
            raise ValueError('core preparation changed during capture')
        target = resolve_local(inputs / 'core', relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    _, selected = source_records(inputs / 'core', read_json(inputs / 'observations.json'),
                                 read_json(inputs / 'sources.lock.json'))
    for record in selected.values():
        if record['status'] == 'retrieved':
            data = resolve_local(source_root, record['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('publisher source changed during capture')
            target = resolve_local(output / 'sources', record['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    derivatives = evaluate_packet(output)
    for name, data in derivatives.items():
        write_json(output / name, data)
    artifacts = {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}
    write_json(output / 'integrity.json', {'schema_version': 1, 'artifacts': artifacts})
    verify_pin_evidence(output)
    return derivatives['report.json']


def verify_pin_evidence(root):
    root = checked_path(root)
    manifest = read_json(resolve_local(root, 'integrity.json'))
    if type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1:
        raise ValueError('invalid pin evidence integrity version')
    required = {'facts.json', 'pin-comparison.json', 'report.json', 'inputs/observations.json',
                'inputs/sources.lock.json', 'inputs/core/integrity.json'}
    core_manifest = read_json(resolve_local(root, 'inputs/core/integrity.json'))
    required.update('inputs/core/' + p for p in core_manifest['artifacts'])
    _, selected = source_records(root / 'inputs/core', read_json(root / 'inputs/observations.json'),
                                 read_json(root / 'inputs/sources.lock.json'))
    required.update('sources/' + r['path'] for r in selected.values() if r['status'] == 'retrieved')
    if not required <= set(manifest['artifacts']):
        raise ValueError('incomplete pin evidence integrity manifest')
    for relative, digest in manifest['artifacts'].items():
        if sha256(resolve_local(root, relative)) != digest:
            raise ValueError(f'pin evidence hash drift: {relative}')
    for name, expected in evaluate_packet(root).items():
        # JSON serialized equality also rejects Boolean values masquerading as counts.
        if json.dumps(read_json(root / name), sort_keys=True) != json.dumps(expected, sort_keys=True):
            raise ValueError(f'pin evidence derivative differs from captured inputs: {name}')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', required=True)
    parser.add_argument('--observations', default='benchmarks/stm32-communications/core-pin-observations.json')
    parser.add_argument('--source-lock', default='benchmarks/stm32-communications/sources.lock.json')
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = prepare_pin_evidence(args.core, args.observations, args.source_lock, args.source_root, args.output)
    print(json.dumps(report))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
