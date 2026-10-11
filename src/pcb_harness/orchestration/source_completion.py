"""Frozen recovered manufacturer sources and unconfirmed v2 derivatives.

Revision v1 is deliberately calibrated to the recovered originals. Recalibration
requires a new checked observation/page-extraction revision, not rehashing edits.
No PDF parser, network access or provider key is needed by the offline loader.
"""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from pcb_harness.circuit.bundle import read_json, resolve_local, sha256, validate_document
from pcb_harness.circuit.sexpr import child, children, dump_sexpr, parse_sexpr, walk
from pcb_harness.orchestration.core_assets import write_json

REVISION = 'm4-source-completion-v1'
# id: original digest, bytes, physical pages, publisher URL, revision, local name
SOURCES = {
    'stm32-ds': ('1e54ce18e6c34c5b4a78986f26e245e143748c721009fc9af5953795c30686bc', 1965230, 114,
        'https://www.st.com/resource/en/datasheet/stm32f103c8.pdf', 'DS5319 Rev 20', 'stm32-ds.pdf'),
    'stm32-rm': ('4c1b8ac2729cc1f45a4685eea9e91e6139e24e58804fba21e27201dfcc2ad149', 13119424, 1136,
        'https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf', 'RM0008 Rev 21', 'stm32-rm.pdf'),
    'stm32-errata': ('7bcdf58d8b602292d68abb59e181a4f44a038f215d8b01b0167f6d7139285490', 956332, 31,
        'https://www.st.com/resource/en/errata_sheet/es096-stm32f101x8b-stm32f102x8b-and-stm32f103x8b-mediumdensity-device-limitations-stmicroelectronics.pdf', 'ES096 Rev 15', 'stm32-errata.pdf'),
    'rs232': ('484d6bb1c92c5f2e993f1f3835c574bc4c03fea4b4d70a5e690b8d52674acf37', 1783899, 30,
        'https://www.ti.com/lit/ds/symlink/max3232.pdf', 'SLLS410O; package addendum 23-Dec-2025', 'max3232.pdf'),
    'max3232idwr-part': ('6178505d1302d9c6fe18d35f5a2ca8360a6d3958c666e002ce7f89a732679474', 83469, None,
        'https://www.ti.com/product/MAX3232/part-details/MAX3232IDWR', 'manufacturer HTML snapshot 2026-10-10', 'max3232idwr-part.html'),
    'max3232idwr-carrier': ('320eeed439d886745b4c2b4c3a7af56257c410a6e6219971af3626bc5941e5a1', 129296, 2,
        'https://www.ti.com/packaging/docs/carriermaterial/downloadCarrierReport?OPN=MAX3232IDWR', 'manufacturer carrier snapshot 2026-10-10', 'max3232idwr-carrier.pdf'),
}
FILES = {
    'observations-v1.json': '5447f447d46a205be6747d73548700db1fda71de680f2f392a9f08688d0b6b41',
    'page-checks.json': '7144353ef652feb38be0970b51a4639c0308da26cba7749cf37680d5d72305a4',
    'assets/SOIC-16W_7.5x10.3mm_P1.27mm.kicad_mod': '07aa02ced9fcdc61d7c6bb5ea1b86803731041e9e171db91a991c3daa7817383',
}
TITLES = {
    'stm32-ds': 'DS5319 Rev 20',
    'stm32-rm': 'RM0008 Rev 21',
    'stm32-errata': 'ES096 Rev 15',
    'rs232': 'MAX3232 SLLS410O, current TI package addendum',
    'max3232idwr-part': 'MAX3232IDWR exact orderable page',
    'max3232idwr-carrier': 'MAX3232IDWR carrier report',
}
DERIVATIVES = ('documents.json', 'facts.json', 'mcu-source-evidence.json', 'rs232-correction.json', 'report.json')


def _validate_manifest(manifest):
    if (set(manifest) != {'schema_version', 'revision', 'human_confirmed', 'documents'}
            or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1
            or manifest['revision'] != REVISION or manifest['human_confirmed'] is not False):
        raise ValueError('invalid source completion manifest state')
    documents = manifest['documents']
    if not isinstance(documents, list): raise ValueError('invalid source completion inventory')
    by_id = {d['id']: d for d in documents}
    if len(by_id) != len(documents) or set(by_id) != set(SOURCES):
        raise ValueError('incomplete or duplicate recovered source inventory')
    for did, record in by_id.items():
        digest, size, count, url, revision, name = SOURCES[did]
        expected = {'id': did, 'sha256': digest, 'bytes': size, 'page_count': count,
                    'url': url, 'retrieved_url': url, 'revision': revision,
                    'path': 'sources/' + name, 'human_confirmed': False, 'original_publisher_bytes': True}
        if set(record) != set(expected) | {'retrieved_at', 'title'}:
            raise ValueError('unexpected source metadata fields')
        if any(json.dumps(record[k]) != json.dumps(v) for k, v in expected.items()):
            raise ValueError(f'uncalibrated source identity/revision: {did}')
        if record['title'] != TITLES[did]:
            raise ValueError('uncalibrated source title')
        try: datetime.fromisoformat(record['retrieved_at'])
        except (TypeError, ValueError) as error: raise ValueError('invalid retrieval timestamp') from error
    return by_id


def load_source_completion(root):
    """Validate frozen originals/observations and derive source-bound evidence.

    `root` is the captured source-completion directory, including sources/.
    Returns documents/facts compatible with the M3 schemas plus mcu,
    rs232_correction and report. Does not treat any documentary fact as confirmed.
    """
    root = Path(root).absolute()
    records = _validate_manifest(read_json(resolve_local(root, 'source-manifest.json')))
    for did, record in records.items():
        raw = resolve_local(root, record['path']).read_bytes()
        if len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError(f'recovered source bytes drifted: {did}')
        if record['page_count'] is not None and not raw.startswith(b'%PDF-'):
            raise ValueError('recovered PDF format differs')
    for relative, digest in FILES.items():
        if sha256(resolve_local(root, relative)) != digest:
            raise ValueError(f'checked source observation/geometry revision drifted: {relative}')
    observations = read_json(root / 'observations-v1.json')
    checks = read_json(root / 'page-checks.json')['pages']
    for check in checks:
        record = records[check['source_id']]
        if (check['source_sha256'] != record['sha256'] or type(check['physical_pdf_page']) is not int
                or not 1 <= check['physical_pdf_page'] <= record['page_count'] or not check['text']):
            raise ValueError('invalid checked physical PDF page')
    documents = {'schema_version': 1, 'documents': [
        {'id': d['id'], 'title': d['title'], 'revision': d['revision'], 'source_url': d['url'],
         'retrieved_at': datetime.fromisoformat(d['retrieved_at']).date().isoformat(),
         'path': d['path'], 'sha256': d['sha256'], 'license': 'Manufacturer publication; redistribution review pending',
         'redistribution': 'unknown', 'source': 'manufacturer'} for d in records.values()]}
    facts = []
    def fact(ident, did, locator, claim, kind='identity', value=None, units=None, range_=None):
        entry = {'id': ident, 'document_id': did, 'document_sha256': records[did]['sha256'],
                 'locator': locator, 'claim': claim, 'status': 'unconfirmed', 'critical': True,
                 'value': value, 'units': units, 'kind': kind, 'confirmation': None}
        if range_ is not None: entry['range'] = range_
        facts.append(entry)
    mcu = deepcopy(observations['mcu'])
    pin_claim = '; '.join(f'{p["number"]}={p["manufacturer_name"]}' for p in mcu['pins'])
    fact('STM32F103C8T6:pinout', 'stm32-ds', 'Figure 8 PDF p26; Table 5 PDF pp28-33',
         'Authored LQFP48 pin observations: ' + pin_claim)
    fact('STM32F103C8T6:package', 'stm32-ds', 'Section 6.9 PDF pp98-100; ordering scheme PDF p104',
         'STM32F103C8T6 uses 48-pin 7x7mm LQFP, 0.50mm pitch; footprint acceptance remains separate.')
    fact('STM32F103C8T6:flash', 'stm32-ds', 'Table 2 PDF p10; ordering scheme PDF p104',
         'C8 density code selects 64KiB Flash, without assuming clone/overdensity memory.', value=65536, units='bytes')
    fact('STM32F103C8T6:ram', 'stm32-ds', 'Table 2 PDF p10', 'Medium-density C8 has 20KiB SRAM.', value=20480, units='bytes')
    fact('STM32F103C8T6:supply', 'stm32-ds', 'Table 2 PDF p10', 'Device operating supply range; per-pin absolute limits require separate review.', 'operating', range_=[2.0, 3.6], units='V')
    fact('STM32F103C8T6:default-functions', 'stm32-ds', 'Table 5 PDF pp28-33; RM0008 AFIO_MAPR PDF pp177-181',
         'Authored default peripheral mappings: ' + json.dumps(mcu['default_peripheral_functions'], sort_keys=True))
    fact('STM32F103C8T6:dma', 'stm32-rm', 'Section 13.3.7/Figure 50 PDF p281; Table 78 PDF p282',
         'DMA1 requests on each channel are ORed; enable only one at a time. Selected request mapping: ' + json.dumps(mcu['dma_requests'], sort_keys=True))
    fact('STM32F103C8T6:errata', 'stm32-errata', 'Tables 1/2 PDF p1; Table 3 PDF pp2-4',
         'ES096 applies to STM32F103C8. REV_ID 0x2003 aliases markings Y/X/1/2/3. Physical marking and REV_ID remain unknown; full silicon-specific closure is pending.', 'errata')
    for item in mcu['errata']:
        fact('STM32F103C8T6:errata/' + item['id'], 'stm32-errata',
             f'ES096 section {item["id"]}, physical PDF p{item["physical_pdf_page"]}',
             'Authored planned response, implementation not established: ' + item['policy'], 'errata')
    rs = observations['rs232']
    fact('MAX3232IDWR:pinout', 'rs232', 'Figure 5-1/Table 5-1 PDF p3',
         'DW16 top-view manufacturer pins: ' + '; '.join(f'{p["number"]}={p["manufacturer_name"]}' for p in rs['pins']))
    fact('MAX3232IDWR:package', 'rs232', 'Orderable addendum PDF p15; DW0016A outline PDF p24',
         'Exact MAX3232IDWR is SOIC(DW), 16 pins; 7.4-7.6mm body width, 10.1-10.5mm body length, 1.27mm pitch, 2.65mm maximum height.')
    fact('MAX3232IDWR:orderable', 'rs232', 'Package Option Addendum 23-Dec-2025, physical PDF p15',
         'Exact MAX3232IDWR row: Active, SOIC(DW), 16 pins, -40..85C. This snapshot does not establish inventory availability.')
    fact('MAX3232IDWR:carrier', 'max3232idwr-carrier', 'Carrier report physical PDF p1',
         'Exact MAX3232IDWR carrier rows corroborate DW, SOIC,16 pins,SPQ2000.')
    fact('MAX3232IDWR:part-page', 'max3232idwr-part', 'Original HTML meta description lines114/128; ACTIVE_true line146; packaging line1686',
         'Exact MAX3232IDWR manufacturer page states active SOIC(DW),16 pins.')
    fact('MAX3232IDWR:land-pattern', 'rs232', 'DW0016A example board/stencil pattern PDF pp25-26',
         'TI example has 16 pads 2.0x0.6mm, row-center spacing9.3mm and pitch1.27mm. Site-specific mask, paste and assembly qualifications remain pending.')
    correction = {'schema_version': 1, 'revision': REVISION, 'ref': 'U7', 'old_mpn': rs['old_mpn'],
                  'new_mpn': rs['mpn'], 'package': rs['package'], 'package_code': 'DW',
                  'preserved_part_id': 'MAX3232IDR', 'new_footprint_id': 'STM32Target:MAX3232IDWR_DW',
                  'lifecycle_snapshot': 'active', 'human_confirmed': False,
                  'footprint_qualification': rs['footprint_qualification'],
                  'topology_value_patch': {'ref': 'U7', 'value': 'MAX3232IDWR'},
                  'fact_ids': [f['id'] for f in facts if f['id'].startswith('MAX3232IDWR:')]}
    report = {'schema_version': 1, 'revision': REVISION, 'scope': 'hash-bound documentary source completion',
              'original_sources': len(records), 'checked_pdf_pages': len(checks), 'source_bound_facts': len(facts),
              'missing_original_sources': [], 'source_retrieval_complete': True, 'human_confirmed': False,
              'layout_allowed': False, 'release_eligible': False, 'milestone_complete': False,
              'remaining_dependencies': ['critical fact review', 'physical silicon marking and REV_ID',
                  'implemented errata tests', 'assembly land-pattern qualification', 'circuit/electrical acceptance'],
              'limits': 'Publisher bytes/revisions and page extractions are calibrated; observations are authored, not automatic semantic proof or human confirmation.'}
    fact_document = {'schema_version': 1, 'facts': facts}
    validate_document('documents', documents); validate_document('facts', fact_document)
    return {'documents': documents, 'facts': fact_document, 'mcu': mcu,
            'rs232_correction': correction, 'report': report}


def _derivatives(data):
    return dict(zip(DERIVATIVES, (data['documents'], data['facts'], data['mcu'], data['rs232_correction'], data['report'])))


def capture_source_completion(spec_path, repository_root, output):
    """Freeze completion-input.json sources into a fresh local packet directory."""
    spec_path, repository_root, output = map(lambda p: Path(p).absolute(), (spec_path, repository_root, output))
    resolve_local(output.parent, output.name)
    if output.is_relative_to(spec_path.parent): raise ValueError('output overlaps source completion inputs')
    spec = read_json(spec_path)
    if (type(spec.get('schema_version')) is not int or spec['schema_version'] != 1
            or spec.get('revision') != REVISION or spec.get('human_confirmed') is not False):
        raise ValueError('invalid source completion capture state')
    records, blobs = [], {}
    for original in spec['documents']:
        did = original['id']
        if did not in SOURCES: raise ValueError('unexpected original source')
        digest, size, count, url, revision, name = SOURCES[did]
        if (original.get('status') != 'retrieved' or original.get('sha256') != digest
                or original.get('url') != url or original.get('retrieved_url') != url
                or original.get('original_publisher_bytes') is not True or original.get('human_confirmed') is not False):
            raise ValueError('uncalibrated recovered source capture')
        relative = 'sources/' + name
        blobs[relative] = resolve_local(repository_root, original['repository_path']).read_bytes()
        records.append({'id': did, 'sha256': digest, 'bytes': size, 'page_count': count,
            'url': url, 'retrieved_url': url, 'revision': revision, 'path': relative,
            'human_confirmed': False, 'original_publisher_bytes': True,
            'title': original['title'], 'retrieved_at': original['retrieved_at_utc']})
    manifest = {'schema_version': 1, 'revision': REVISION, 'human_confirmed': False, 'documents': records}
    _validate_manifest(manifest)
    file_records = {f['path']: f for f in spec['files']}
    if len(file_records) != len(spec['files']) or set(file_records) != set(FILES): raise ValueError('incomplete checked input inventory')
    for relative, digest in FILES.items():
        record = file_records[relative]
        raw = resolve_local(repository_root, record['repository_path']).read_bytes()
        if record['sha256'] != digest or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('checked input changed before capture')
        blobs[relative] = raw
    for record in records:
        raw = blobs[record['path']]
        if len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError('original source changed before capture')
    output.mkdir(parents=True, exist_ok=False)
    for relative, raw in blobs.items():
        path = resolve_local(output, relative); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    write_json(output / 'source-manifest.json', manifest)
    data = load_source_completion(output)
    for name, derivative in _derivatives(data).items(): write_json(output / name, derivative)
    write_json(output / 'integrity.json', {'schema_version': 1, 'artifacts': {
        str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    verify_source_completion(output)
    return data['report']


def verify_source_completion(root):
    """Reject omitted artifacts or derivative edits, including self-rehashed edits."""
    root = Path(root).absolute()
    data = load_source_completion(root)
    integrity = read_json(resolve_local(root, 'integrity.json'))
    required = {'source-manifest.json', *FILES, *DERIVATIVES,
                *('sources/' + row[5] for row in SOURCES.values())}
    if (set(integrity) != {'schema_version', 'artifacts'} or type(integrity['schema_version']) is not int
            or integrity['schema_version'] != 1 or set(integrity['artifacts']) != required):
        raise ValueError('invalid source completion integrity inventory')
    for relative, digest in integrity['artifacts'].items():
        if sha256(resolve_local(root, relative)) != digest: raise ValueError('source completion artifact drift')
    for name, expected in _derivatives(data).items():
        if json.dumps(read_json(root / name), sort_keys=True) != json.dumps(expected, sort_keys=True):
            raise ValueError(f'source completion derivative drift: {name}')
    return True


def apply_source_completion(root, parts, assets):
    """Return (updated_parts, updated_asset_bytes, evidence) without mutating inputs.

    Preserve U7 part id/symbol id MAX3232IDR for historical topology references;
    replace exact MPN, wide DW geometry, Value/Footprint properties and every
    hash referring to the shared symbol library. Topology/BOM Value must consume
    evidence['rs232_correction']['topology_value_patch'] independently.
    """
    verify_source_completion(root)
    data = load_source_completion(root)
    result, blobs = deepcopy(parts), dict(assets)
    selected = [p for p in result if p['id'] == 'MAX3232IDR']
    if len(selected) != 1 or selected[0]['mpn'] != 'MAX3232IDR': raise ValueError('expected original U7 candidate identity')
    part = selected[0]
    observed = read_json(resolve_local(root, 'observations-v1.json'))['rs232']['pins']
    expected_pins = {p['number']: p['symbol_name'] for p in observed}
    if (len(part['pins']) != 16
            or {p['number']: p['name'] for p in part['pins']} != expected_pins
            or len({p['id'] for p in part['pins']}) != 16):
        raise ValueError('original MAX3232 part pins differ from recovered pinout')
    expected_mapping = {p['id']: (p['number'], [p['number']]) for p in part['pins']}
    if (len(part['pin_map']) != 16 or
            {p['pin_id']: (p['symbol_pin'], p['pads']) for p in part['pin_map']} != expected_mapping):
        raise ValueError('original MAX3232 pin mapping differs from recovered pinout')
    for kind in ('symbol', 'footprint'):
        if hashlib.sha256(blobs[part[kind]['path']]).hexdigest() != part[kind]['sha256']:
            raise ValueError('original candidate assets drifted')
    fp = parse_sexpr(resolve_local(root, next(p for p in FILES if p.startswith('assets/'))).read_text())
    fp[1] = 'MAX3232IDWR_DW'
    for prop in children(fp, 'property'):
        if prop[1] == 'Value': prop[2] = 'MAX3232IDWR_DW'
    # TI's example board geometry (PDF p25); KiCad's input pads are2.05mm long.
    pads = children(fp, 'pad')
    if {str(p[1]) for p in pads} != {str(i) for i in range(1, 17)} or len(pads) != 16:
        raise ValueError('unexpected wide SOIC template pad inventory')
    for pad in pads: child(pad, 'size')[1:] = [2.0, 0.6]
    fp[:] = [item for item in fp if not isinstance(item, list) or item[0] != 'model']
    new_fp = 'assets/STM32Target.pretty/MAX3232IDWR_DW.kicad_mod'
    blobs[new_fp] = (dump_sexpr(fp) + '\n').encode()
    old_fp = part['footprint']['path']
    if not any(p is not part and p['footprint']['path'] == old_fp for p in result): blobs.pop(old_fp, None)
    library_path = part['symbol']['path']; library = parse_sexpr(blobs[library_path].decode())
    symbols = [s for s in children(library, 'symbol') if s[1] == part['symbol_id'].split(':')[1]]
    if len(symbols) != 1: raise ValueError('original U7 symbol not present exactly once')
    symbol_pins = list(walk(symbols[0], 'pin'))
    if (len(symbol_pins) != 16 or
            {str(child(p, 'number')[1]): str(child(p, 'name')[1]) for p in symbol_pins} != expected_pins):
        raise ValueError('original MAX3232 symbol pins differ from recovered pinout')
    for prop in children(symbols[0], 'property'):
        if prop[1] == 'Value': prop[2] = 'MAX3232IDWR'
        elif prop[1] == 'Footprint': prop[2] = 'STM32Target:MAX3232IDWR_DW'
    blobs[library_path] = (dump_sexpr(library) + '\n').encode()
    for p in result:
        if p['symbol']['path'] == library_path: p['symbol']['sha256'] = hashlib.sha256(blobs[library_path]).hexdigest()
    part.update(mpn='MAX3232IDWR', package=data['rs232_correction']['package'],
                revision=REVISION, footprint_id='STM32Target:MAX3232IDWR_DW')
    part['footprint'].update(path=new_fp, sha256=hashlib.sha256(blobs[new_fp]).hexdigest())
    part['fact_ids'] = data['rs232_correction']['fact_ids']
    part['required_fact_ids'] = ['MAX3232IDWR:pinout', 'MAX3232IDWR:package', 'MAX3232IDWR:land-pattern']
    # Human confirmation is absent; remain conservative despite active snapshot.
    part['lifecycle'] = 'unknown'
    return result, blobs, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', default='benchmarks/stm32-communications/source-recovery/completion-input.json')
    parser.add_argument('--repository-root', default='.')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(capture_source_completion(args.spec, args.repository_root, args.output)))
    return 2  # A source evidence packet does not accept M4/release.


if __name__ == '__main__':
    raise SystemExit(main())
