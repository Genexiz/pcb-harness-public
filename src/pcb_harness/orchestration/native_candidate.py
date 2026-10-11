"""Reconstruct native candidate evidence; failed ERC is never normalized away."""
from collections import Counter
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from pcb_harness.circuit.bootstrap import parse_native_netlist
from pcb_harness.circuit.bundle import read_json,resolve_local,sha256
from pcb_harness.native_reports import parse_report

REQUIRED={'native/erc.json','native/netlist.xml','native/svg/board.svg'}
CLI=Path('/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')


def native_claims(root,cli):
    root=Path(root).absolute();cli=Path(cli).absolute()
    circuit=read_json(resolve_local(root,'circuit.json'))
    expected={n['name']:{(p['instance_id'],p['pin_id'][1:]) for p in n['endpoints']} for n in circuit['nets']}
    actual=parse_native_netlist(resolve_local(root,'native/netlist.xml'))
    extras={n:p for n,p in actual.items() if n not in expected}
    nc={(p['instance_id'],p['pin_id'][1:]) for p in circuit['no_connect']}
    document=ET.parse(resolve_local(root,'native/netlist.xml')).getroot()
    refs=[comp.get('ref') for comp in document.findall('./components/comp')]
    matches=(all(actual.get(n)==p for n,p in expected.items())
             and all(n.startswith('unconnected-') and len(p)==1 for n,p in extras.items())
             and {next(iter(p)) for p in extras.values() if len(p)==1}==nc
             and set(refs)=={i['ref'] for i in circuit['instances']} and len(refs)==len(set(refs)))
    report=read_json(resolve_local(root,'native/erc.json'))
    issues=[v for sheet in report.get('sheets',[]) for v in sheet.get('violations',[])]
    exit_code=5 if issues else 0
    parsed=parse_report(report,'erc',root/'board.kicad_sch',exit_code)
    if parsed['kicad_version']!='10.0.6':raise ValueError('exact KiCad10.0.6 native evidence required')
    counts=dict(Counter(v['type'] for v in parsed['issues']))
    artifacts={str(p.relative_to(root)):sha256(resolve_local(root,str(p.relative_to(root))))
               for p in resolve_local(root,'native').rglob('*') if p.is_file()}
    if not REQUIRED<=set(artifacts):raise ValueError('missing required native artifacts')
    return {'schema_version':1,'kicad_version':'10.0.6','cli_path':str(cli),'cli_sha256':sha256(cli),
            'schematic_sha256':sha256(resolve_local(root,'board.kicad_sch')),
            'input_integrity_sha256':sha256(resolve_local(root,'integrity.json')),
            'topology_net_count':len(expected),'native_net_count':len(actual),'explicit_nc_count':len(nc),
            'native_component_count':len(refs),'netlist_matches':matches,'erc_clean':parsed['passed'],
            'erc_violation_count':parsed['issue_count'],'erc_types':counts,'erc_exit_code':exit_code,
            'native_library_warnings':sum(counts.get(n,0) for n in ['lib_symbol_issues','footprint_link_issues']),
            'endpoint_off_grid_warnings':counts.get('endpoint_off_grid',0),
            'layout_allowed':False,'release_eligible':False,'artifacts':artifacts}


def write_native_summary(root,cli=CLI):
    """Create once after raw exports AND visual assets are final, never overwrite."""
    from pcb_harness.orchestration.stm32_circuit import _verify_review_inputs
    root=Path(root).absolute();_verify_review_inputs(root)
    path=resolve_local(root,'native-summary.json')
    if path.exists():raise FileExistsError('refusing existing native summary')
    summary=native_claims(root,cli)
    path.write_text(json.dumps(summary,indent=2)+'\n')
    verify_native_review(root)
    return summary


def verify_native_review(root):
    root=Path(root).absolute();summary=read_json(resolve_local(root,'native-summary.json'))
    if not isinstance(summary,dict) or not isinstance(summary.get('cli_path'),str):raise ValueError('invalid native summary')
    # Includes every native artifact, not only a caller-selected hash subset.
    expected=native_claims(root,summary['cli_path'])
    if json.dumps(summary,sort_keys=True)!=json.dumps(expected,sort_keys=True):
        raise ValueError('native summary/artifacts differ from reconstructed claims')
    if not expected['netlist_matches']:raise ValueError('native netlist differs from candidate endpoints')
    return True


def _erc_issues(report):
    """Order-independent violation identity, excluding dates and absolute paths."""
    return sorted(json.dumps({'type': v.get('type'), 'severity': v.get('severity'),
                              'description': v.get('description'),
                              'items': sorted(i.get('description', '') for i in v.get('items', []))},
                             sort_keys=True)
                  for sheet in report.get('sheets', []) for v in sheet.get('violations', []))


def rerun_erc(root, cli=CLI):
    """Re-run native ERC on a copy of the retained schematic; bind it to the report.

    The retained erc.json names its source only by file name. This run proves
    the stated violations are what KiCad reports for these exact schematic bytes.
    """
    root, cli = Path(root).absolute(), Path(cli).absolute()
    retained = read_json(resolve_local(root, 'native/erc.json'))
    with tempfile.TemporaryDirectory() as work:
        copy = Path(work) / 'circuit'
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns('native', 'native-summary.json'))
        out = Path(work) / 'erc.json'
        result = subprocess.run([str(cli), 'sch', 'erc', '--format', 'json', '--severity-all', '--exit-code-violations',
                                 '-o', str(out), str(copy / 'board.kicad_sch')],
                                capture_output=True, text=True, timeout=300)
        if not out.is_file():
            raise ValueError('native ERC re-run produced no report: ' + result.stderr.strip())
        fresh = json.loads(out.read_text())
    parse_report(fresh, 'erc', copy / 'board.kicad_sch', result.returncode)
    keys = ('kicad_version', 'included_severities', 'ignored_checks', 'coordinate_units', 'source')
    if any(fresh.get(k) != retained.get(k) for k in keys) or _erc_issues(fresh) != _erc_issues(retained):
        raise ValueError('retained ERC report differs from native re-run on the retained schematic')
    return {'schematic_sha256': sha256(resolve_local(root, 'board.kicad_sch')),
            'kicad_version': fresh['kicad_version'], 'violation_count': len(_erc_issues(fresh)),
            'matches_retained_report': True}
