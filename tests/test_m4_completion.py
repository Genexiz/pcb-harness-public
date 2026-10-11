"""Whole-packet evidence must survive forged status labels and missing inputs."""
from pathlib import Path
import json
import shutil
import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'runs/m4/completion-2026-10-11-r3'


def test_incomplete_completion_packet_is_rejected(tmp_path):
    from pcb_harness.orchestration.m4_completion import assess_completion
    (tmp_path / 'report.json').write_text(json.dumps({'layout_allowed': True}))
    with pytest.raises((ValueError, OSError)):
        assess_completion(tmp_path)


@pytest.fixture
def complete_packet(tmp_path):
    if not (PACKET / 'completion-integrity.json').exists():
        pytest.skip('retained original-source integration packet required')
    shutil.copytree(PACKET, tmp_path / 'packet')
    return tmp_path / 'packet'


def test_forged_completion_status_is_rejected_even_when_rehashed(complete_packet):
    from pcb_harness.orchestration.m4_completion import verify_completion
    from pcb_harness.circuit.bundle import read_json, sha256
    p = complete_packet / 'report.json'
    d = read_json(p)
    d.update(layout_allowed=True, milestone_complete=True, blockers=[])
    p.write_text(json.dumps(d))
    m = read_json(complete_packet / 'completion-integrity.json')
    m['artifacts']['report.json'] = sha256(p)
    (complete_packet / 'completion-integrity.json').write_text(json.dumps(m))
    with pytest.raises(ValueError, match='reconstructed'):
        verify_completion(complete_packet)


def test_complete_packet_cannot_omit_nested_source_evidence(complete_packet):
    from pcb_harness.orchestration.m4_completion import verify_completion
    from pcb_harness.circuit.bundle import read_json
    p = complete_packet / 'completion-integrity.json'
    m = read_json(p)
    name = next(n for n in m['artifacts'] if n.startswith('circuit/inputs/source-completion/sources/'))
    del m['artifacts'][name]
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='inventory'):
        verify_completion(complete_packet)


@pytest.fixture
def unsealed_packet(tmp_path):
    if not (PACKET / 'independent-review.json').exists():
        pytest.skip('retained original-source integration packet required')
    shutil.copytree(PACKET, tmp_path / 'packet')
    for name in ('completion-integrity.json', 'report.json'):
        (tmp_path / 'packet' / name).unlink(missing_ok=True)
    return tmp_path / 'packet'


def test_sub_packet_blockers_and_untracked_facts_propagate(unsealed_packet):
    from pcb_harness.orchestration.m4_completion import assess_completion
    report = assess_completion(unsealed_packet)
    assert {'CIRCUIT:POWER_THERMAL', 'CIRCUIT:SILICON_ERRATA', 'CIRCUIT:USB_UNPOWERED_ATTACH_INJECTION',
            'FEASIBILITY:ERRATA'} <= set(report['prelayout_blockers'])
    assert 'REQUIRED_FACT_RECORDS' not in report['prelayout_blockers']
    assert report['untracked_required_facts'] == []
    assert {'MCP2518FD-E_SL:sdo-high-z', 'WIZ550io_v1_2_candidate:pinout', 'C_100N:qualification'} <= set(
        report['pending_critical_confirmation'])
    assert report['release_blockers'] == ['CRITICAL_FACT_CONFIRMATION', 'LICENSE_REVIEW']
    assert report['layout_allowed'] is False and report['release_eligible'] is False


def test_forged_circuit_report_cannot_drop_producer_blockers(unsealed_packet):
    from pcb_harness.orchestration.m4_completion import propagated
    from pcb_harness.orchestration.stm32_circuit import BLOCKERS
    assert 'CIRCUIT:POWER_THERMAL' in propagated('circuit', sorted(set(BLOCKERS)))
    assert propagated('feasibility', ['UNKNOWN_NEW']) == ['FEASIBILITY:UNKNOWN_NEW']


@pytest.mark.parametrize('mutate', ['omit_unresolved_key', 'drop_findings', 'unbound_feasibility',
                                    'claim_no_unresolved', 'malformed_status'])
def test_independent_review_record_is_validated(unsealed_packet, mutate):
    from pcb_harness.orchestration.m4_completion import assess_completion
    p = unsealed_packet / 'independent-review.json'
    review = json.loads(p.read_text())
    if mutate == 'omit_unresolved_key':
        review = {'circuit_sha256': review['circuit_sha256']}
    elif mutate == 'drop_findings':
        del review['findings']
    elif mutate == 'unbound_feasibility':
        review['packet_sha256']['feasibility/integrity.json'] = '0' * 64
    elif mutate == 'claim_no_unresolved':
        review['findings'][0]['status'] = 'open'
        del review['findings'][0]['resolution']
        review['important_unresolved'] = []
    else:
        review['findings'][0]['status'] = 'done'
    p.write_text(json.dumps(review))
    with pytest.raises(ValueError, match='review'):
        assess_completion(unsealed_packet)


def test_open_important_finding_blocks_prelayout(unsealed_packet):
    from pcb_harness.orchestration.m4_completion import assess_completion
    p = unsealed_packet / 'independent-review.json'
    review = json.loads(p.read_text())
    review['findings'][0]['status'] = 'open'
    p.write_text(json.dumps(review))
    assert 'INDEPENDENT_REVIEW_FINDINGS' in assess_completion(unsealed_packet)['prelayout_blockers']


def test_forged_mechanical_flag_is_rejected_by_completion(unsealed_packet):
    from pcb_harness.orchestration.m4_completion import assess_completion
    from pcb_harness.circuit.bundle import sha256
    mech = unsealed_packet / 'mechanical'
    report = json.loads((mech / 'report.json').read_text())
    report['mating_fit_qualified'] = True
    (mech / 'report.json').write_text(json.dumps(report))
    manifest = json.loads((mech / 'integrity.json').read_text())
    manifest['artifacts']['report.json'] = sha256(mech / 'report.json')
    (mech / 'integrity.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='review|mechanical'):
        assess_completion(unsealed_packet)


def test_circuit_facts_require_bound_sdo_source(tmp_path):
    from pcb_harness.orchestration.m4_completion import circuit_facts
    with pytest.raises(ValueError, match='SDO'):
        circuit_facts(tmp_path, [{'id': 'MCP2518FD-E_SL', 'required_fact_ids': ['MCP2518FD-E_SL:sdo-high-z']}], {})


def test_native_erc_rerun_binds_retained_report(unsealed_packet):
    from pcb_harness.orchestration.native_candidate import rerun_erc, CLI
    if not CLI.exists():
        pytest.skip('KiCad 10.0.6 CLI required')
    circuit = unsealed_packet / 'circuit'
    result = rerun_erc(circuit)
    assert result['violation_count'] == 0 and result['matches_retained_report'] is True
    report = json.loads((circuit / 'native/erc.json').read_text())
    report['sheets'][0].setdefault('violations', []).append(
        {'type': 'pin_not_driven', 'severity': 'error', 'description': 'forged', 'items': []})
    (circuit / 'native/erc.json').write_text(json.dumps(report))
    with pytest.raises(ValueError, match='re-run'):
        rerun_erc(circuit)


def _bindings_inputs(packet):
    def load(p):
        return json.loads((packet / p).read_text())
    return dict(design=load('feasibility/inputs/design.json'), engineering=load('feasibility/inputs/engineering.json'),
                circuit=load('circuit/circuit.json'), parts=load('circuit/parts.json')['parts'],
                module_mpn=load('mechanical/mechanical-evidence.json')['module']['mpn'],
                board_c=(packet / 'feasibility/firmware-full/sources/board.c').read_text())


def test_cross_packet_bindings_hold_for_retained_packet(unsealed_packet):
    from pcb_harness.orchestration.m4_completion import cross_bindings
    result = cross_bindings(**_bindings_inputs(unsealed_packet))
    assert result['mcu_pins_checked'] == 45 and result['firmware_gpio_pins'] == 25


@pytest.mark.parametrize('mutate', ['design_id', 'pin_net', 'mpn', 'module', 'firmware_pin'])
def test_cross_packet_revision_mismatch_fails(unsealed_packet, mutate):
    from pcb_harness.orchestration.m4_completion import cross_bindings
    args = _bindings_inputs(unsealed_packet)
    if mutate == 'design_id':
        args['engineering']['design_id'] = 'other-revision'
    elif mutate == 'pin_net':
        next(p for p in args['design']['pins'] if p['signal'] == 'ETH_CS')['number'] = 26
    elif mutate == 'mpn':
        next(p for p in args['design']['parts'] if p['mpn'] == 'MCP2518FD-E/SL')['mpn'] = 'MCP2517FD-H/SL'
    elif mutate == 'module':
        args['module_mpn'] = 'WIZ550io v1.1'
    else:
        args['board_c'] = args['board_c'].replace('gpio(GPIOC,GPIO_PIN_13,GPIO_MODE_INPUT);', '')
    with pytest.raises(ValueError, match='cross-packet'):
        cross_bindings(**args)
