"""Mechanical mating fit must be derived from bound evidence, not a report flag."""
from pathlib import Path
import json
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'runs/m4/completion-2026-10-11-r3/mechanical'


def _rehash(root):
    from pcb_harness.circuit.bundle import sha256
    manifest = json.loads((root / 'integrity.json').read_text())
    manifest['artifacts'] = {n: sha256(root / n) for n in manifest['artifacts']}
    (root / 'integrity.json').write_text(json.dumps(manifest))


@pytest.fixture
def packet(tmp_path):
    if not (PACKET / 'integrity.json').exists():
        pytest.skip('retained mechanical source packet required')
    shutil.copytree(PACKET, tmp_path / 'mechanical')
    return tmp_path / 'mechanical'


def test_retained_mechanical_packet_verifies_unqualified(packet):
    from pcb_harness.orchestration.mechanical_evidence import verify_mechanical
    report = verify_mechanical(packet)
    assert report['mating_fit_qualified'] is False


def test_rehashed_forged_mating_flag_is_rejected(packet):
    from pcb_harness.orchestration.mechanical_evidence import verify_mechanical
    report = json.loads((packet / 'report.json').read_text())
    report['mating_fit_qualified'] = True
    for check in report['checks']:
        check['passed'] = True
    (packet / 'report.json').write_text(json.dumps(report))
    _rehash(packet)
    with pytest.raises(ValueError, match='derived evidence'):
        verify_mechanical(packet)


def test_unconfirmed_measurement_does_not_qualify_fit(packet):
    from pcb_harness.orchestration.mechanical_evidence import verify_mechanical
    evidence = json.loads((packet / 'mechanical-evidence.json').read_text())
    evidence['mating_qualification'] = {
        'module-post-section-insertion': {'kind': 'physical_measurement', 'source_id': 'header',
                                          'locator': 'caliper', 'human_confirmed': False},
        'finished-socket-hole-tolerance': {'kind': 'manufacturer_dimensioned_drawing',
                                           'source_id': 'female-header', 'locator': 'p2'}}
    (packet / 'mechanical-evidence.json').write_text(json.dumps(evidence))
    report = json.loads((packet / 'report.json').read_text())
    for check in report['checks']:
        if check['id'] == 'finished-host-socket-hole-tolerance-qualified':
            check['passed'] = True
    (packet / 'report.json').write_text(json.dumps(report))
    _rehash(packet)
    result = verify_mechanical(packet)
    assert result['mating_fit_qualified'] is False
    assert result['derived_mating_requirements'] == {'module-post-section-insertion': False,
                                                     'finished-socket-hole-tolerance': True}


def test_mechanical_source_drift_is_rejected(packet):
    from pcb_harness.orchestration.mechanical_evidence import verify_mechanical
    target = next((packet / 'runs').rglob('header.pdf'))
    target.write_bytes(target.read_bytes() + b' ')
    with pytest.raises(ValueError, match='source hash'):
        verify_mechanical(packet)
