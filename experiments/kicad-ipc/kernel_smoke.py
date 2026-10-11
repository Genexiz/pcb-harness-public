"""Real IPC+CLI Kernel acceptance on the existing isolated live fixture."""
from pathlib import Path
import argparse
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
    options=parser.parse_args();output=options.output.resolve();output.mkdir(parents=True,exist_ok=True)
    report={'status':'running','actions':[]}
    def persist():(output/'smoke.json').write_text(json.dumps(report,indent=2)+'\n')
    persist()
    try:
        with ScratchIPCBackend(options.project,workspace=ROOT,socket=options.socket,artifacts=output/'artifacts') as backend:
            kernel=Kernel(backend,journal_path=output/'actions.jsonl')
            kernel.create_checkpoint('baseline')
            baseline=backend.revision();report['baseline_revision']=baseline
            report['server_version']=str(backend.server_version)
            report['socket']=options.socket
            report['before_verify']=backend.verify()
            def action(id,name,args,mode='strict',revision=None):
                result=kernel.execute(name,args,expected_revision=revision or backend.revision(),action_id=id,mode=mode)
                report['actions'].append({'name':name,'result':result});persist()
                print(name,result['ok'],result.get('error_code',''),flush=True)
                return result
            short=action('reject-short','route_track',{'net':'/NET_A','layer':'F.Cu','points_mm':[[19,20],[21,20]],'width_mm':0.4})
            if short.get('error_code')!='GEOMETRY_REGRESSION' or backend.revision()!=baseline:
                raise RuntimeError('short was not rejected/restored')
            stale=action('stale','move_footprint',{'ref':'R1','dx_mm':1,'dy_mm':0},revision='stale')
            if stale.get('error_code')!='STALE_REVISION':raise RuntimeError('stale edit accepted')
            part=backend._footprint('R1');part.locked=True;backend.board.update_items(part)
            locked_revision=backend.revision()
            locked=action('locked','move_footprint',{'ref':'R1','dx_mm':1,'dy_mm':0})
            if locked.get('error_code')!='LOCKED_OBJECT' or backend.revision()!=locked_revision:
                raise RuntimeError('locked footprint changed')
            part=backend._footprint('R1');part.locked=False;backend.board.update_items(part)
            if 'flip_footprint' in backend.capabilities():
                flip=action('native-flip','flip_footprint',{'ref':'R1'},'permissive')
                actual=kernel.get_footprint('R1')
                if not flip['ok'] or actual['side']!='back' or {p['number']:p['position_mm'] for p in actual['pads']}!={'1':[21,20],'2':[19,20]}:
                    raise RuntimeError('native flip/pad readback failed')
                front=action('place-front','place_footprint',{'ref':'R1','x_mm':20,'y_mm':20,'rotation_deg':0,'side':'front'},'permissive')
                if not front['ok'] or kernel.get_footprint('R1')['side']!='front':raise RuntimeError('place side failed')
            moved=action('move','move_footprint',{'ref':'R1','dx_mm':3,'dy_mm':-2},'permissive')
            if not moved['ok'] or kernel.get_footprint('R1')['x_mm']!=23:raise RuntimeError('move/readback failed')
            restored=action('restore-position','place_footprint',{'ref':'R1','x_mm':20,'y_mm':20,'rotation_deg':0},'permissive')
            if not restored['ok']:raise RuntimeError('explicit position restore failed')
            args={'net':'/NET_A','layer':'F.Cu','points_mm':[[59,15],[65,15]],'width_mm':0.4}
            route_revision=backend.revision()
            route=action('explicit-route','route_track',args,revision=route_revision)
            if not route['ok']:raise RuntimeError('valid explicit track rejected')
            replay=action('explicit-route','route_track',args,revision=route_revision)
            if not replay['replayed']:raise RuntimeError('duplicate action not replayed')
            resumed=Kernel(backend,journal_path=output/'actions.jsonl')
            if resumed.recovery_required:raise RuntimeError('accepted state not resumable')
            resumed_replay=resumed.execute('route_track',args,expected_revision=route_revision,action_id='explicit-route')
            report['journal_resume_replay']=resumed_replay;persist()
            if not resumed_replay.get('replayed') or not resumed_replay['ok']:raise RuntimeError('resume replay failed')
            deleted=action('delete-route','delete_track',{'id':route['changed_ids'][0]})
            if not deleted['ok']:raise RuntimeError('explicit track delete failed')
            via=action('through-via','add_via',{'net':'/NET_A','x_mm':65,'y_mm':15,'drill_mm':0.3,'dia_mm':0.6,'layers':['F.Cu','B.Cu']})
            if not via['ok'] or not any(v.id.value==via['changed_ids'][0] for v in backend.board.get_vias()):
                raise RuntimeError('through via creation/readback failed')
            zone=action('zone','add_zone',{'net':'/NET_B','layer':'B.Cu','polygon_mm':[[12,12],[68,12],[68,28],[12,28]],'clearance_mm':0.2})
            if not zone['ok'] or not any(z.filled for z in backend.board.get_zones()):raise RuntimeError('zone fill failed')
            refill=action('refill','fill_zones',{})
            if not refill['ok']:raise RuntimeError('explicit refill failed')
            restore=kernel.restore_checkpoint('baseline',expected_revision=backend.revision())
            report['checkpoint_restore']=restore;persist()
            if not restore['ok']:raise RuntimeError('full baseline checkpoint restore failed')
            report['after_verify']=backend.verify()
            report['final_revision']=backend.revision()
            report['restored']=report['final_revision']==baseline
            if report['after_verify']['geometric'] or report['after_verify']['connectivity'] or not report['restored']:
                raise RuntimeError('final board differs from validated baseline')
            report['status']='passed';persist()
            print('Kernel native smoke: PASS; baseline restored; artifacts:',output,flush=True)
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error));persist();raise


if __name__=='__main__':main()
