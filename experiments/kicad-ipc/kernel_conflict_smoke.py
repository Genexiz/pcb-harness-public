"""Native M1 external saved-settings conflict; never silently restores over it."""
from pathlib import Path
import argparse
import hashlib
import json
import uuid
from pcb_harness.ipc import ScratchIPCBackend
from pcb_harness.kernel import Kernel

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--socket',default='ipc:///tmp/kicad/api.sock')
    parser.add_argument('--project',type=Path,default=ROOT/'runs/capability/live/board.kicad_pcb')
    parser.add_argument('--output',type=Path,default=ROOT/'runs/kernel'/str(uuid.uuid4()))
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    report={'status':'running'}
    def persist():(output/'conflict.json').write_text(json.dumps(report,indent=2)+'\n')
    persist()
    with ScratchIPCBackend(args.project,workspace=ROOT,socket=args.socket,artifacts=output/'artifacts') as backend:
        kernel=Kernel(backend,journal_path=output/'actions.jsonl')
        kernel.create_checkpoint('baseline');baseline=backend.revision()
        project=backend.path.with_suffix('.kicad_pro');original=project.read_bytes()
        config=json.loads(original)
        config['board']['design_settings']['rules']['min_clearance']=0.31
        changed=(json.dumps(config,indent=2)+'\n').encode()
        report['original_settings_sha256']=hashlib.sha256(original).hexdigest()
        report['external_settings_sha256']=hashlib.sha256(changed).hexdigest()
        persist()
        project.write_bytes(changed)
        result=kernel.restore_checkpoint('baseline',expected_revision=backend.revision())
        report['restore']=result
        report['external_edit_preserved']=project.read_bytes()==changed
        blocked=kernel.execute('move_footprint',{'ref':'R1','dx_mm':1,'dy_mm':0},
            expected_revision=backend.revision(),action_id='after-conflict')
        report['subsequent_write']=blocked;persist()
        if result.get('ok') or not result.get('recovery_required') or not report['external_edit_preserved']:
            raise RuntimeError('external settings conflict not safely rejected; retain scratch/evidence')
        if blocked.get('error_code')!='RECOVERY_REQUIRED':raise RuntimeError('next write not blocked')
        # Explicitly remove this probe's own change only while its bytes match.
        if project.read_bytes()!=changed:raise RuntimeError('third-party edit; refuse probe cleanup')
        project.write_bytes(original)
        backend.board.revert()
        report['probe_cleanup_restored']=backend.revision()==baseline
        if not report['probe_cleanup_restored']:raise RuntimeError('explicit probe cleanup failed')
        report['status']='passed';persist()
    print('Native settings conflict: PASS; edit preserved, next write blocked, own probe cleanup verified')


if __name__=='__main__':main()
