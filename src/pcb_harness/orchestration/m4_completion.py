"""Reconstruct one integrated M4 packet, including concrete unclosed gates.

This producer stops at pre-layout review. It does not accept caller-authored
pass flags as a substitute for a routed board or a verified service bound.
"""
import argparse
import json
import re
from pathlib import Path

from pcb_harness.circuit.bundle import read_json, resolve_local, sha256, validate_document
from pcb_harness.fabrication.profile import review_profile
from .m4 import audit_sources, verify_report
from .stm32_feasibility import assess_design
from .stm32_circuit import verify_review, BLOCKERS as CIRCUIT_BLOCKERS
from .mechanical_evidence import verify_mechanical
from .candidate_models import sdo_fact, SDO_SHA
from .native_candidate import native_claims, rerun_erc, CLI
from .source_completion import load_source_completion
from .support_qualification import verify_support
from .firmware_complete import verify_complete


# Sub-packet blockers are closed here only by a named, reconstructed completion
# check. Every other sub-packet blocker propagates; unknown names fail closed.
SUPERSEDED = {
    'circuit': {'ST_ORIGINAL_SOURCES': 'SOURCE_INTEGRITY',
                'FULL_FIRMWARE_TIMING': 'AGGREGATE_CPU_IRQ_SERVICE_BOUND',
                'MODULE_REVISION_SOCKET_MECHANICS': 'WIZ550IO_SOCKET_MATING_FIT',
                'INDEPENDENT_FUNCTIONAL_CIRCUIT_REVIEW': 'INDEPENDENT_REVIEW_FINDINGS',
                'FABRICATION_SERVICE_PROFILE': 'FABRICATION_PROFILE',
                'EXACT_SUPPORT_MPN_QUALIFICATION': 'verify_support',
                'NATIVE_ACCEPTED_BOOTSTRAP': 'NATIVE_BOOTSTRAP_PLACEMENT_ROUTING_DRC_EXPORT'},
    'feasibility': {'CIRCUIT_NATIVE': 'SCHEMATIC_ERC_NETLIST',
                    'MECHANICAL': 'WIZ550IO_SOCKET_MATING_FIT',
                    'FABRICATION': 'FABRICATION_PROFILE',
                    'FULL_FIRMWARE_TIMING': 'AGGREGATE_CPU_IRQ_SERVICE_BOUND',
                    'FULL_FIRMWARE': 'FULL_FIRMWARE_CAPACITY',
                    'CAPACITY_PROBE': 'FULL_FIRMWARE_CAPACITY',
                    'SOURCE_INTEGRITY': 'SOURCE_INTEGRITY',
                    'RESOURCES': 'PIN_PERIPHERAL_RESOURCES',
                    'WIRE_BUDGET': 'SPI_WIRE_BUDGET'},
}
RELEASE_ONLY = {'CRITICAL_FACT_CONFIRMATION', 'LICENSE_REVIEW'}
SEVERITIES = {'Critical', 'Important', 'Minor'}
STATUSES = {'open', 'fixed', 'declined'}
REVIEWED_PACKETS = ('circuit/integrity.json', 'feasibility/integrity.json',
                    'mechanical/integrity.json', 'fabrication/sources.json',
                    'fabrication/fabrication.json', 'fabrication/facts.json')


def review_record(root, circuit):
    """Validate the independent review and derive unresolved findings."""
    review = read_json(resolve_local(root, 'independent-review.json'))
    if (review.get('schema_version') != 1 or not review.get('reviewer') or not review.get('scope')
            or not isinstance(review.get('findings'), list)
            or not isinstance(review.get('declined_to_certify'), list)):
        raise ValueError('independent review record is incomplete')
    if review.get('circuit_sha256') != sha256(circuit / 'circuit.json'):
        raise ValueError('independent review circuit binding differs')
    bound = {name: sha256(resolve_local(root, name)) for name in REVIEWED_PACKETS}
    if review.get('packet_sha256') != bound:
        raise ValueError('independent review sub-packet binding differs')
    ids = [f.get('id') for f in review['findings']]
    if len(set(ids)) != len(ids) or any(
            not f.get('id') or f.get('severity') not in SEVERITIES or f.get('status') not in STATUSES
            or not f.get('summary') or (f['status'] != 'open' and not f.get('resolution'))
            for f in review['findings']):
        raise ValueError('independent review finding is malformed')
    unresolved = [f['id'] for f in review['findings']
                  if f['severity'] in {'Critical', 'Important'} and f['status'] != 'fixed']
    if 'important_unresolved' in review and review['important_unresolved'] != unresolved:
        raise ValueError('independent review unresolved list differs from findings')
    return dict(review, important_unresolved=unresolved)


def circuit_facts(circuit, parts, support):
    """Records for required facts introduced by circuit integration itself."""
    facts, required = [], {i for p in parts for i in p.get('required_fact_ids', [])}
    if 'MCP2518FD-E_SL:sdo-high-z' in required:
        source = Path(circuit) / 'inputs/pins/sources/mcp2518fd.pdf'
        if not source.is_file() or sha256(source) != SDO_SHA:
            raise ValueError('SDO fact source is not the calibrated DS20006027B bytes')
        facts.append(sdo_fact())
    module = next((p for p in parts if p['id'] == 'WIZ550io_v1_2_candidate'), None)
    if module is not None:
        cad = read_json(Path(circuit) / 'inputs/module-source.json')
        if sha256(Path(circuit) / 'inputs/wiz550io.lbr') != cad['sha256']:
            raise ValueError('WIZ550io CAD source hash differs')
        pins = '; '.join(f"{p['number']}={p['name']}" for p in module['pins'])
        doc = support['engineering_analysis']['module_source']
        common = {'status': 'unconfirmed', 'critical': True, 'value': None, 'units': None,
                  'kind': 'identity', 'confirmation': None}
        facts.append({'id': module['id'] + ':pinout', 'document_id': cad['id'], 'document_sha256': cad['sha256'],
                      'locator': cad['archive_member'] + ' symbol/package pins (v1.1 CAD for v1.2 module)',
                      'claim': f"{module['mpn']} header pins: {pins}", **common})
        facts.append({'id': module['id'] + ':qualification', 'document_id': 'wiz550io',
                      'document_sha256': doc['sha256'], 'locator': doc['locator'],
                      'claim': (f"{module['mpn']}: VDD {doc['manufacturer_supply_min_v']}-{doc['manufacturer_supply_max_v']} V, "
                                f"normal current typ {doc['manufacturer_normal_current_typ_a']} A, no published maximum; "
                                'v1.2 revision match to v1.1 CAD unconfirmed'), **common})
    return facts


# Declared net names that intentionally differ from the design signal name.
# None means the pin is deliberately unconnected (HSE bypass leaves PD1 open).
NET_ALIASES = {'RESET': '/NRST', 'USB_VBUS_SENSE': '/VBUS_PRESENT_N', 'USB_DM': '/USB_DM_MCU',
               'USB_DP': '/USB_DP_MCU', 'HSE_OUT': None}
FIRMWARE_FUNCTIONS = ('gpio', 'USART', 'SPI', 'I2C')


def cross_bindings(design, engineering, circuit, parts, module_mpn, board_c):
    """Fail unless every sub-packet describes the same design revision."""
    def fail(message):
        raise ValueError('cross-packet revision mismatch: ' + message)
    if engineering.get('design_id') != design['id']:
        fail('engineering dossier design_id')
    mpns = {p['mpn'] for p in parts}
    missing = [p['mpn'] for p in design['parts'] if p['mpn'] not in mpns]
    if missing:
        fail('design parts absent from circuit: ' + ', '.join(missing))
    module = [p['mpn'] for p in parts if p['mpn'].startswith('WIZ550io')]
    if module != [module_mpn]:
        fail('mechanical module revision')
    mcu = [p for p in parts if p['mpn'] == design['mcu']]
    mcu_refs = [i['id'] for i in circuit['instances'] if mcu and i['part_id'] == mcu[0]['id']]
    if len(mcu) != 1 or len(mcu_refs) != 1:
        fail('MCU instance')
    names = {q['number']: q['name'] for q in mcu[0]['pins']}
    nets = {e['pin_id'][1:]: n['name'] for n in circuit['nets'] for e in n['endpoints']
            if e['instance_id'] == mcu_refs[0]}
    for pin in design['pins']:
        number = str(pin['number'])
        if names.get(number) not in (pin['pin'], pin['pin'].rstrip('0123456789')):
            fail(f"MCU pin {number} name")
        if pin['function'] == 'power':
            expected = '/GND' if pin['pin'].startswith('VSS') else '/3V3'
        elif pin['function'] == 'reserved':
            expected = None
        else:
            expected = NET_ALIASES.get(pin['signal'], '/' + pin['signal'])
        if nets.get(number) != expected:
            fail(f"{pin['signal']} on pin {number} is {nets.get(number)}, design expects {expected}")
    configured = {(port, int(n)) for port, group in re.findall(r'\bgpio\(GPIO([A-C]),([^,]+),', board_c)
                  for n in re.findall(r'GPIO_PIN_(\d+)', group)}
    wanted = {(p['pin'][1], int(p['pin'][2:])) for p in design['pins']
              if p['function'].startswith(FIRMWARE_FUNCTIONS)}
    if configured != wanted:
        fail('firmware GPIO configuration differs from design pins: '
             + str(sorted(configured ^ wanted)))
    return {'design_id': design['id'], 'circuit_id': circuit['id'], 'circuit_revision': circuit['revision'],
            'mcu_pins_checked': len(design['pins']), 'firmware_gpio_pins': len(configured),
            'net_aliases': NET_ALIASES}


def propagated(kind, names):
    out = []
    for name in names:
        if name in RELEASE_ONLY or name in SUPERSEDED[kind]:
            continue
        out.append(f'{kind.upper()}:{name}')
    return out


def assess_completion(root):
    root = Path(root).absolute()
    circuit, feasibility = root / 'circuit', root / 'feasibility'
    verify_review(circuit)
    verify_report(feasibility)
    native = native_claims(circuit, CLI)
    # Binds the retained ERC report to these schematic bytes by an actual run.
    erc_rerun = rerun_erc(circuit, CLI)
    source = load_source_completion(circuit / 'inputs/source-completion')
    support = verify_support(circuit / 'inputs/support-completion')
    assessment = assess_design(read_json(feasibility / 'inputs/design.json'),
                               read_json(feasibility / 'inputs/resources.json'))
    sources = audit_sources(feasibility / 'inputs/sources.json', feasibility / 'sources',
                            feasibility / 'inputs/sources.lock.json')
    firmware = verify_complete(feasibility / 'firmware-full/sources',
                               feasibility / 'firmware-full/build')
    fabrication = root / 'fabrication'
    manifest = read_json(resolve_local(fabrication, 'sources.json'))
    for doc in manifest['documents']:
        if sha256(resolve_local(fabrication, doc['path'])) != doc['sha256']:
            raise ValueError('fabrication source drift')
    facts = read_json(resolve_local(fabrication, 'facts.json'))
    validate_document('facts', facts)
    profile = review_profile(read_json(resolve_local(fabrication, 'fabrication.json')), facts)
    doc_map = {d['id']: d for d in manifest['documents']}
    if len(doc_map) != len(manifest['documents']):
        raise ValueError('duplicate fabrication source')
    for fact in facts['facts']:
        if doc_map.get(fact['document_id'], {}).get('sha256') != fact['document_sha256']:
            raise ValueError('fabrication fact is not bound to captured source')
    prelayout = []
    if not sources['integrity_passed']:
        prelayout.append('SOURCE_INTEGRITY')
    if not assessment['resources']['passed']:
        prelayout.append('PIN_PERIPHERAL_RESOURCES')
    if not assessment['scheduling']['wire_budget_passed']:
        prelayout.append('SPI_WIRE_BUDGET')
    if not (native['erc_clean'] and native['netlist_matches']):
        prelayout.append('SCHEMATIC_ERC_NETLIST')
    if not firmware['full_firmware_build_passed']:
        prelayout.append('FULL_FIRMWARE_CAPACITY')
    if not firmware['timing_qualified']:
        prelayout.append('AGGREGATE_CPU_IRQ_SERVICE_BOUND')
    if not profile['passed']:
        prelayout.append('FABRICATION_PROFILE')
    selected_limits = support['engineering_analysis']['current_limits']
    if any(selected_limits[n].get('guaranteed_at_selected_voltage') is not True
           for n in ('wiz_branch', 'system_input')):
        prelayout.append('SELECTED_VOLTAGE_CURRENT_LIMIT_QUALIFICATION')
    bindings = cross_bindings(read_json(feasibility / 'inputs/design.json'),
                              read_json(feasibility / 'inputs/engineering.json'),
                              read_json(circuit / 'circuit.json'), read_json(circuit / 'parts.json')['parts'],
                              read_json(resolve_local(root, 'mechanical/mechanical-evidence.json'))['module']['mpn'],
                              resolve_local(feasibility, 'firmware-full/sources/board.c').read_text())
    review = review_record(root, circuit)
    if review['important_unresolved']:
        prelayout.append('INDEPENDENT_REVIEW_FINDINGS')
    mechanical = verify_mechanical(root / 'mechanical')
    if mechanical['mating_fit_qualified'] is not True:
        prelayout.append('WIZ550IO_SOCKET_MATING_FIT')
    # A forged circuit report cannot drop the producer's static blockers.
    circuit_blockers = sorted(set(read_json(circuit / 'report.json')['blockers'])
                              | set(CIRCUIT_BLOCKERS) - {'ST_ORIGINAL_SOURCES'})
    feasibility_blockers = read_json(feasibility / 'report.json')['blockers']
    prelayout += propagated('circuit', circuit_blockers) + propagated('feasibility', feasibility_blockers)
    parts = read_json(circuit / 'parts.json')['parts']
    all_facts = (read_json(circuit / 'inputs/pins/facts.json')['facts'] + source['facts']['facts']
                 + facts['facts'] + support['facts'] + circuit_facts(circuit, parts, support))
    validate_document('facts', {'schema_version': 1, 'facts': all_facts})
    recorded = {f['id'] for f in all_facts}
    required = sorted({i for p in parts for i in p.get('required_fact_ids', [])})
    untracked = [i for i in required if i not in recorded]
    if untracked:
        prelayout.append('REQUIRED_FACT_RECORDS')
    # None of these pre-layout artifacts is a routed-board acceptance packet.
    # Do not inspect or grant acceptance to a casually added PCB filename.
    if (root / 'board.kicad_pcb').exists():
        raise ValueError('routed-board evidence requires the native release producer')
    blockers = prelayout + ['NATIVE_BOOTSTRAP_PLACEMENT_ROUTING_DRC_EXPORT']
    pending_facts = sorted({f['id'] for f in all_facts if f['critical'] and f['status'] != 'confirmed'})
    release_blockers = sorted({n for n in circuit_blockers + feasibility_blockers if n in RELEASE_ONLY})
    return {'schema_version': 1, 'milestone': 'M4',
            'scope': 'integrated original sources, exact support, circuit, full firmware and pre-layout assessment',
            'sources': sources, 'resources': assessment['resources'],
            'wire_budget': assessment['scheduling'], 'firmware': firmware,
            'circuit': {k: native[k] for k in ('erc_clean', 'erc_violation_count', 'netlist_matches',
                                             'native_component_count', 'topology_net_count')}
                       | {'erc_rerun': erc_rerun},
            'support': {'selected_part_types': len(support['catalog']['parts']),
                        'source_count': len(support['sources_verified']),
                        'engineering_analysis': support['engineering_analysis']},
            'fabrication': profile, 'mechanical': mechanical, 'independent_review': review,
            'cross_packet_bindings': bindings,
            'prelayout_blockers': prelayout, 'blockers': blockers,
            'prelayout_allowed': not prelayout,
            'layout_allowed': not prelayout and 'NATIVE_BOOTSTRAP_PLACEMENT_ROUTING_DRC_EXPORT' not in blockers,
            'milestone_complete': not blockers,
            'release_eligible': not blockers and not pending_facts and not release_blockers,
            'pending_critical_confirmation': pending_facts,
            'release_blockers': release_blockers,
            'required_fact_ids': len(required), 'untracked_required_facts': untracked,
            'hardware_tested': firmware['hardware_tested'],
            'limits': 'Source models and host tests are retained separately from physical validation. '
                      'Human confirmation is a release obligation; unknown static timing and mating fit close pre-layout.'}


def inventory(root):
    root = Path(root)
    return {str(p.relative_to(root)): sha256(resolve_local(root, str(p.relative_to(root))))
            for p in sorted(root.rglob('*'))
            if p.is_file() and p != root / 'completion-integrity.json'}


def write_completion(root):
    root = Path(root)
    if (root / 'completion-integrity.json').exists():
        raise FileExistsError('completion packet already sealed')
    report = assess_completion(root)
    (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    (root / 'completion-integrity.json').write_text(json.dumps(
        {'schema_version': 1, 'artifacts': inventory(root)}, indent=2) + '\n')
    verify_completion(root)
    return report


def verify_completion(root):
    root = Path(root)
    manifest = read_json(resolve_local(root, 'completion-integrity.json'))
    if manifest.get('schema_version') != 1 or manifest['artifacts'] != inventory(root):
        raise ValueError('completion packet inventory or hashes differ')
    if read_json(resolve_local(root, 'report.json')) != assess_completion(root):
        raise ValueError('completion report differs from reconstructed evidence')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify_completion(args.packet)
        return 0
    report = write_completion(args.packet)
    print(json.dumps({'layout_allowed': report['layout_allowed'], 'blockers': report['blockers']}))
    return 0 if report['milestone_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
