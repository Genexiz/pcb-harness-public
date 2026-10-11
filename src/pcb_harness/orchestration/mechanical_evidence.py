"""Verify the WIZ550io/socket mechanical packet; derive mating fit from evidence.

The report is authored engineering summary. Its mating-fit result is accepted
only when it equals the value derived from hash-bound qualification records:
a dimensioned manufacturer drawing or a human-confirmed physical measurement
for both the module post/insertion and the finished host socket hole.
"""
from pathlib import Path

from pcb_harness.circuit.bundle import read_json, resolve_local, sha256

FILES = {'mechanical-evidence.json', 'report.json', 'source-manifest.json', 'validation.json'}
MATING = {'module-post-section-insertion': 'actual-module-post-section-and-insertion-qualified',
          'finished-socket-hole-tolerance': 'finished-host-socket-hole-tolerance-qualified'}
KINDS = {'manufacturer_dimensioned_drawing', 'physical_measurement'}


def mating_fit(evidence, documents):
    """Return per-requirement qualification; absent or unbound records stay False."""
    records = evidence.get('mating_qualification', {})
    result = {}
    for requirement in MATING:
        record = records.get(requirement)
        ok = (isinstance(record, dict) and record.get('kind') in KINDS
              and record.get('source_id') in documents and bool(record.get('locator')))
        if ok and record['kind'] == 'physical_measurement':
            ok = record.get('human_confirmed') is True
        result[requirement] = ok
    return result


def verify_mechanical(root, source_root=None):
    root = Path(root).absolute()
    source_root = root if source_root is None else Path(source_root).absolute()
    integrity = read_json(resolve_local(root, 'integrity.json'))
    if integrity.get('schema_version') != 1 or set(integrity.get('artifacts', {})) != FILES:
        raise ValueError('mechanical packet inventory differs')
    for name, digest in integrity['artifacts'].items():
        if sha256(resolve_local(root, name)) != digest:
            raise ValueError('mechanical packet hash differs: ' + name)
    bound = {**integrity.get('source_artifacts', {}), **integrity.get('derived_artifacts', {})}
    for name, digest in bound.items():
        if sha256(resolve_local(source_root, name)) != digest:
            raise ValueError('mechanical source hash differs: ' + name)
    manifest = read_json(resolve_local(root, 'source-manifest.json'))
    documents = {d['id']: d for d in manifest['documents']}
    if len(documents) != len(manifest['documents']):
        raise ValueError('duplicate mechanical source')
    for doc in documents.values():
        if integrity.get('source_artifacts', {}).get(doc['repository_path']) != doc['sha256']:
            raise ValueError('mechanical source is not bound to a retained artifact: ' + doc['id'])
    evidence = read_json(resolve_local(root, 'mechanical-evidence.json'))
    report = read_json(resolve_local(root, 'report.json'))
    if report.get('source_sha256') != {i: d['sha256'] for i, d in documents.items()}:
        raise ValueError('mechanical report source binding differs')
    if (evidence.get('revision') != report.get('revision')
            or report.get('human_confirmed') is not False or evidence.get('human_confirmed') is not False):
        raise ValueError('mechanical report identity or confirmation status differs')
    fit = mating_fit(evidence, documents)
    checks = {c['id']: c['passed'] for c in report.get('checks', [])}
    for requirement, check in MATING.items():
        if checks.get(check) is not fit[requirement]:
            raise ValueError('mechanical mating check differs from derived evidence: ' + check)
    qualified = all(fit.values())
    if report.get('mating_fit_qualified') is not qualified:
        raise ValueError('mechanical mating fit differs from derived evidence')
    if report.get('layout_allowed') is not False or report.get('release_eligible') is not False:
        raise ValueError('mechanical packet cannot grant layout or release')
    return dict(report, mating_fit_qualified=qualified, derived_mating_requirements=fit)
