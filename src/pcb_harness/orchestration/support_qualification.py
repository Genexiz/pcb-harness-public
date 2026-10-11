"""Source-bound exact support BOM and corrective topology qualification."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json

from pcb_harness.circuit.bundle import read_json, resolve_local
from pcb_harness.circuit.sexpr import parse_sexpr, children, walk


DATA = 'benchmarks/stm32-communications/support-qualified'


def verify_support_sources(catalog, sources, root):
    """Reject unavailable, altered, escaping or non-PDF manufacturer evidence."""
    documents = sources['documents']
    by_id = {d['id']: d for d in documents}
    if len(by_id) != len(documents):
        raise ValueError('duplicate support source')
    required = {s for p in catalog['parts'].values() for s in p['source_ids']}
    required.update(a['source_id'] for a in catalog['assembly_accessories'])
    for source_id in required:
        doc = by_id.get(source_id)
        if doc is None or doc.get('status') != 'retrieved':
            raise ValueError('unavailable support source: ' + source_id)
        raw = resolve_local(Path(root), doc['path']).read_bytes()
        if not raw.startswith(b'%PDF') or sha256(raw).hexdigest() != doc['sha256']:
            raise ValueError('support source hash differs: ' + source_id)
    return sorted(required)


def verify_pin_semantics(catalog):
    """Bind safety-critical pin numbers to the reviewed manufacturer pinout."""
    required = {
        'MISO_BUFFER': {'1':'OE_N','2':'A','3':'GND','4':'Y','5':'VCC'},
        'USB_MUX': {'1':'SEL','2':'S1A','3':'S1B','4':'D1','5':'S2A','6':'S2B',
                    '7':'D2','8':'GND','9':'D3','10':'S3B','11':'S3A','12':'D4',
                    '13':'S4B','14':'S4A','15':'EN_N','16':'VDD'},
        'BRANCH_LIMIT': {'1':'IN','2':'GND','3':'EN','4':'FAULT_N','5':'ILIM','6':'OUT'},
        'INPUT_EFUSE': {'1':'EN_UVLO','2':'OVLO','3':'AUXOFF','4':'FAULT_N','5':'IN',
                        '6':'OUT','7':'DVDT','8':'GND','9':'ILM','10':'ITIMER'},
        'I2C_BUFFER': {'1':'EN','2':'SCLOUT','3':'SCLIN','4':'GND','5':'READY',
                       '6':'SDAIN','7':'SDAOUT','8':'VCC'},
        'HEADER_BUFFER': {'1':'1OE_N','2':'1A','3':'1Y','4':'2OE_N','5':'2A','6':'2Y',
                          '7':'GND','8':'3Y','9':'3A','10':'3OE_N','11':'4Y','12':'4A',
                          '13':'4OE_N','14':'VCC'},
        'OSC_8': {'1':'EN','2':'GND','3':'OUT','4':'VDD'},
        'OSC_20': {'1':'EN','2':'GND','3':'OUT','4':'VDD'},
        'USB_TVS': {'1':'K1','2':'K2','3':'CA'},
        'CAN_TVS': {'1':'K1','2':'K2','3':'CC'},
        'RS485_TVS': {'1':'lineA','2':'lineB','3':'GND'},
        'NPN_SENSE': {'1':'B','2':'E','3':'C'},
    }
    for name, pins in required.items():
        if catalog['parts'][name]['pin_functions'] != pins:
            raise ValueError('support pin semantics differ: ' + name)


def verify_support_bom(topology, catalog, bom):
    """Tie purchasing rows to every qualified support instance, exactly once."""
    instances = {p['ref']:p for p in topology['instances'] if p['part_id'] in catalog['parts']}
    rows = {p['ref']:p for p in bom['items']}
    if len(rows) != len(bom['items']) or set(rows) != set(instances):
        raise ValueError('support BOM reference inventory differs')
    for ref, instance in instances.items():
        spec = catalog['parts'][instance['part_id']]
        expected = {key:instance[key] for key in ('part_id', 'value', 'block')}
        expected.update(mpn=spec['mpn'], procurement=spec['procurement'])
        if any(rows[ref].get(key) != value for key, value in expected.items()):
            raise ValueError('support BOM instance differs: ' + ref)
    if bom['accessories'] != catalog['assembly_accessories']:
        raise ValueError('support BOM accessories differ')


def verify_support_connections(topology):
    """Check retained base nets on which USB isolation and rail analysis depend."""
    instances = {p['ref']:p for p in topology['instances']}
    required = {
        'Q1': {'1':'VBUS_BASE','2':'GND','3':'VBUS_PRESENT_N'},
        'R9': {'1':'USB_VBUS','2':'VBUS_BASE'},
        'R10': {'1':'VBUS_BASE','2':'GND'},
        'R11': {'1':'VBUS_PRESENT_N','2':'3V3'},
        'R24': {'1':'I2C_SCL','2':'3V3'},
        'R25': {'1':'I2C_SDA','2':'3V3'},
        'C11': {'1':'5V','2':'GND'},
        'C12': {'1':'3V3','2':'GND'},
        'L1': {'1':'BUCK_SW','2':'3V3'},
    }
    for ref, pins in required.items():
        if instances.get(ref, {}).get('pins') != pins:
            raise ValueError('support electrical connection differs: ' + ref)


def support_facts(catalog, sources, assets):
    """Derive one pinout and one qualification fact per support type.

    Claims restate the source-reviewed catalog bound to its primary retrieved
    document. PCB features without a purchased part bind to their frozen
    footprint bytes. Every record stays unconfirmed: this producer never
    supplies human review.
    """
    documents = {d['id']: d for d in sources['documents']}
    facts = []
    for part_id, spec in sorted(catalog['parts'].items()):
        if spec['source_ids']:
            doc = documents.get(spec['source_ids'][0])
            if doc is None or doc.get('status') != 'retrieved':
                raise ValueError('unavailable support fact source: ' + part_id)
            document_id, digest = doc['id'], doc['sha256']
            pages = ', '.join(map(str, spec.get('evidence_pages', []))) or 'unspecified'
            locator = f'pages {pages}; supporting sources: ' + ', '.join(spec['source_ids'])
            kind = 'identity'
        else:
            ns, name = spec['footprint_template'].split(':')
            raw = assets.get(f'footprints/{ns}.pretty/{name}.kicad_mod')
            if raw is None:
                raise ValueError('unavailable support fact source: ' + part_id)
            document_id, digest = 'kicad-footprint:' + spec['footprint_template'], sha256(raw).hexdigest()
            locator, kind = 'frozen footprint ' + spec['footprint_template'], 'engineering_choice'
        pins = '; '.join(f'{n}={f}' for n, f in sorted(spec['pin_functions'].items(), key=lambda i: i[0]))
        common = {'document_id': document_id, 'document_sha256': digest, 'locator': locator,
                  'status': 'unconfirmed', 'critical': True, 'value': None, 'units': None,
                  'kind': kind, 'confirmation': None}
        facts.append({'id': part_id + ':pinout',
                      'claim': f"{spec['mpn']} ({spec['manufacturer']}) on {spec['footprint_template']}: {pins}",
                      **common})
        ratings = json.dumps(spec.get('ratings', {}), sort_keys=True)
        facts.append({'id': part_id + ':qualification',
                      'claim': f"{spec['mpn']} ({spec['manufacturer']}, {spec['procurement']}): {spec['note']} ratings {ratings}",
                      **common})
    return facts


def qualify_current_limits(engineering, sources, root):
    """Derive selected-voltage limit applicability from bound source conditions.

    A limit characterized at another input voltage is an extrapolation model.
    It becomes a guarantee only when the datasheet test condition equals the
    selected input, or a retrieved, hash-bound vendor applicability document
    names the selected input. An authored True without that evidence fails.
    """
    result = deepcopy(engineering)
    documents = {d['id']: d for d in sources['documents']}
    for name, limit in result.get('current_limits', {}).items():
        if 'guaranteed_at_selected_voltage' not in limit:
            continue
        selected = limit.get('selected_input_nominal_v')
        derived = selected is not None and limit.get('datasheet_test_input_v') == selected
        applicability = limit.get('vendor_applicability')
        if applicability is not None:
            doc = documents.get(applicability.get('document_id'))
            if doc is None or doc.get('status') != 'retrieved':
                raise ValueError('unavailable current-limit applicability source: ' + name)
            raw = resolve_local(Path(root), doc['path']).read_bytes()
            if not raw.startswith(b'%PDF') or sha256(raw).hexdigest() != doc['sha256']:
                raise ValueError('current-limit applicability source hash differs: ' + name)
            derived = derived or (applicability.get('selected_input_v') == selected
                                  and bool(applicability.get('locator')))
        if limit['guaranteed_at_selected_voltage'] is True and not derived:
            raise ValueError('authored current-limit guarantee lacks selected-voltage evidence: ' + name)
        limit['guaranteed_at_selected_voltage'] = derived
    return result


def qualify_support(topology, root):
    """Return a new topology, BOM and checklist delta; grant no approval flags.

    Source review is an engineering evidence producer. It never purports to
    confirm hardware operation, assembly rights or a human-reviewed checklist.
    Parent integration must freeze the returned topology and independently
    review the source pin/package assertions before admitting layout.
    """
    root = Path(root)
    catalog = read_json(resolve_local(root, DATA + '/catalog.json'))
    sources = read_json(resolve_local(root, DATA + '/sources.json'))
    patch = read_json(resolve_local(root, DATA + '/topology-patch.json'))
    bom = read_json(resolve_local(root, DATA + '/bom.json'))
    authored = read_json(resolve_local(root, DATA + '/integrity.json'))['artifacts']
    engineering = (read_json(resolve_local(root, DATA + '/engineering-analysis.json'))
                   if 'engineering-analysis.json' in authored else {})
    if engineering.get('module_source'):
        doc = engineering['module_source']
        if sha256(resolve_local(root, doc['path']).read_bytes()).hexdigest() != doc['sha256']:
            raise ValueError('support module engineering source hash differs')
    verified = verify_support_sources(catalog, sources, root)
    engineering = qualify_current_limits(engineering, sources, root)
    verify_pin_semantics(catalog)
    assets = support_asset_bytes(root)
    facts = support_facts(catalog, sources, assets)
    if topology['id'] != patch['base_id']:
        raise ValueError('support topology identity differs')
    result = deepcopy(topology)
    original = {p['ref']: p for p in result['instances']}
    if len(original) != len(result['instances']):
        raise ValueError('duplicate topology reference')
    if any(p['ref'] in original for p in patch['add_instances']):
        raise ValueError('support reference conflict')
    if original.get('R26', {}).get('pins') != {'1':'EXTERNAL_SPI_CS','2':'3V3'}:
        raise ValueError('external SPI CS pullup differs')
    if not set(patch['remove_refs']).issubset(original):
        raise ValueError('support removed reference absent')
    for ref, change in patch['update_instances'].items():
        if ref not in original:
            raise ValueError('support update reference absent: ' + ref)
        if ref in {'U1', 'U2', 'U3'}:
            original[ref]['pins'].update(deepcopy(change['pins']))
        else:
            original[ref].update(deepcopy(change))
    result['instances'] = [p for p in result['instances'] if p['ref'] not in patch['remove_refs']]
    result['instances'].extend(deepcopy(patch['add_instances']))
    result['support_types'] = deepcopy(catalog['parts'])
    for p in result['instances']:
        if p['part_id'] in catalog['parts']:
            spec = catalog['parts'][p['part_id']]
            if set(p['pins']) != set(spec['pin_functions']):
                raise ValueError('support assigned pin set differs: ' + p['ref'])
    verify_support_connections(result)
    verify_support_bom(result, catalog, bom)
    delta = {
        'remove_refs': patch['remove_refs'],
        'required_refs': [p['ref'] for p in result['instances']],
        'pin_nets': {p['ref']:p['pins'] for p in result['instances']
                     if p['ref'] in patch['update_instances'] or p['ref'] in {a['ref'] for a in patch['add_instances']}},
        'values': {p['ref']:p['value'] for p in result['instances'] if p['part_id'] in catalog['parts']},
        'no_connect': {p['ref']:[n for n, net in p['pins'].items() if net is None]
                       for p in result['instances']},
    }
    return {'topology':result,'bom':bom,'catalog':catalog,'sources_verified':verified,
            'checks_delta':delta,'firmware_requirements':patch['firmware_requirements'],
            'engineering_analysis':engineering, 'facts':facts,
            'hardware_verified':False,'human_confirmation_granted':False,
            'layout_authorization_granted':False}


def support_asset_bytes(root):
    """Return frozen library overlay bytes keyed relative to a library root.

    All symbols have one unit and exact manufacturer pin numbers. RPW is an
    unusual ten-land package with compound pins; it has no extra exposed pad.
    The keyed SMT SWD land pattern physically omits contact seven.
    """
    root = Path(root)
    data = resolve_local(root, DATA)
    manifest = read_json(resolve_local(data, 'integrity.json'))['artifacts']
    required = {'catalog.json', 'bom.json', 'topology-patch.json', 'sources.json',
                'engineering-analysis.json', 'base-topology.json',
                'library/symbols/SupportQualified.kicad_sym'}
    if not required <= set(manifest):
        raise ValueError('support authoring inventory incomplete')
    for rel, expected in manifest.items():
        raw = resolve_local(data, rel).read_bytes()
        if sha256(raw).hexdigest() != expected:
            raise ValueError('support authoring integrity differs: ' + rel)
    assets = {rel.removeprefix('library/'):resolve_local(data, rel).read_bytes()
              for rel in manifest if rel.startswith('library/')}
    catalog = read_json(resolve_local(data, 'catalog.json'))['parts']
    library = parse_sexpr(assets['symbols/SupportQualified.kicad_sym'].decode())
    symbols = {s[1]:s for s in children(library, 'symbol')}
    for name, spec in catalog.items():
        if any('hide' in prop[1:] for prop in children(symbols[name], 'property')):
            raise ValueError('support native property syntax differs: ' + name)
        symbol_numbers = {str(p[1]) for node in walk(symbols[name], 'pin')
                          for p in children(node, 'number')}
        ns, footprint = spec['footprint_template'].split(':')
        tree = parse_sexpr(assets[f'footprints/{ns}.pretty/{footprint}.kicad_mod'].decode())
        pad_numbers = {str(p[1]) for p in children(tree, 'pad') if str(p[1])}
        if symbol_numbers != set(spec['pin_functions']) or pad_numbers != symbol_numbers:
            raise ValueError('support asset pin or pad set differs: ' + name)
    return assets


def capture_support(topology, root, output):
    """Freeze the repository-shaped source subset for parent review capture."""
    root, output = Path(root), Path(output)
    if output.exists():
        raise FileExistsError('support capture output exists')
    result = qualify_support(topology, root)
    data = resolve_local(root, DATA)
    authored = read_json(resolve_local(data, 'integrity.json'))['artifacts']
    paths = [DATA + '/' + rel for rel in authored]
    paths.append(DATA + '/integrity.json')
    documents = read_json(resolve_local(data, 'sources.json'))['documents']
    applicability = {limit['vendor_applicability']['document_id']
                     for limit in result['engineering_analysis'].get('current_limits', {}).values()
                     if 'vendor_applicability' in limit}
    paths.extend(d['path'] for d in documents
                 if d['id'] in result['sources_verified'] or d['id'] in applicability)
    if result['engineering_analysis'].get('module_source'):
        paths.append(result['engineering_analysis']['module_source']['path'])
    output.mkdir(parents=True)
    for relative in paths:
        raw = resolve_local(root, relative).read_bytes()
        target = resolve_local(output, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for relative, document in [('base-topology.json', topology),
                               ('qualified-topology.json', result['topology'])]:
        resolve_local(output, relative).write_text(json.dumps(document, indent=2) + '\n')
    manifest = {str(p.relative_to(output)):sha256(p.read_bytes()).hexdigest()
                for p in output.rglob('*') if p.is_file()}
    resolve_local(output, 'integrity.json').write_text(json.dumps(
        {'schema_version':1,'artifacts':manifest}, indent=2) + '\n')
    return verify_support(output)


def verify_support(packet):
    """Reproduce a captured qualification instead of trusting a status label."""
    packet = Path(packet)
    manifest = read_json(resolve_local(packet, 'integrity.json'))['artifacts']
    actual = {str(p.relative_to(packet)) for p in packet.rglob('*')
              if p.is_file() and p != packet / 'integrity.json'}
    if actual != set(manifest):
        raise ValueError('support packet integrity inventory differs')
    for rel, expected in manifest.items():
        if sha256(resolve_local(packet, rel).read_bytes()).hexdigest() != expected:
            raise ValueError('support packet integrity differs: ' + rel)
    result = qualify_support(read_json(resolve_local(packet, 'base-topology.json')), packet)
    if result['topology'] != read_json(resolve_local(packet, 'qualified-topology.json')):
        raise ValueError('support captured topology differs')
    return result
