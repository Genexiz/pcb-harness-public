"""Repeatable real-KiCad CLI capability check; does not require API keys."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import uuid
import re
from datetime import datetime, timezone
from verification import run_verification

ROOT = Path(__file__).resolve().parents[2]


from pcb_harness.initial_rules import validate_probe_rules


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cli',type=Path,default=Path('/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'))
    parser.add_argument('--output',type=Path,default=ROOT/'runs/capability/cli')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    run_id=str(uuid.uuid4())
    summary_path=args.output/'summary.json'
    summary_path.write_text(json.dumps({'run_id':run_id,'status':'running',
        'drc':{'passed':False},'erc':{'passed':False},'render':{'passed':False}},indent=2)+'\n')
    fixture=ROOT/'fixtures/capability/board.kicad_pcb'
    try:
        rule_evidence=validate_probe_rules(fixture.with_suffix('.kicad_dru'))
    except (OSError,ValueError) as error:
        summary_path.write_text(json.dumps({'run_id':run_id,'status':'blocked',
            'rules':{'passed':False,'error':str(error)},
            'drc':{'passed':False},'erc':{'passed':False},'render':{'passed':False}},indent=2)+'\n')
        print('rules: FAIL;',error)
        return 1
    results={kind:run_verification(args.cli,kind,fixture if kind=='drc' else fixture.with_suffix('.kicad_sch'),
        args.output/f'{kind}.json') for kind in ('drc','erc')}
    svg=args.output/'board.svg'
    svg.unlink(missing_ok=True)
    command=[str(args.cli),'pcb','export','svg','--layers','F.Cu,B.Cu,Edge.Cuts,F.SilkS,F.Fab',
        '--mode-single','--page-size-mode','2','--exclude-drawing-sheet','-o',str(svg),str(fixture)]
    results['render']={'command':command,'passed':False,'status':'tool_error'}
    try:
        render=subprocess.run(command,capture_output=True,text=True,timeout=60)
        results['render'].update(exit_code=render.returncode,stdout=render.stdout,stderr=render.stderr,
            passed=render.returncode==0 and svg.exists() and svg.stat().st_size>0)
        if results['render']['passed']:results['render']['status']='exported'
    except (OSError,subprocess.TimeoutExpired) as error:
        results['render']['error']=str(error)
    results['runtime']={'python':sys.version,'platform':platform.platform(),
        'timestamp_utc':datetime.now(timezone.utc).isoformat()}
    results['input_hashes']={str(p.relative_to(fixture.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in fixture.parent.rglob('*') if p.is_file() and p.suffix not in ('.lck','.kicad_prl')}
    results['run_id']=run_id
    results['rules']=rule_evidence
    results['status']='finished'
    summary_path.write_text(json.dumps(results,indent=2)+'\n')
    for key in ('drc','erc','render'):
        print(f'{key}: {"PASS" if results[key]["passed"] else "FAIL"}; issues={results[key].get("issue_count","n/a")}')
    print('artifacts:',args.output)
    return 0 if all(results[k]['passed'] for k in ('drc','erc','render')) else 1


if __name__=='__main__': raise SystemExit(main())
