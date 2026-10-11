"""Real native STDIO acceptance; caller-selected paths and exact final restore."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from mcp import Client,StdioServerParameters
ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--socket',default='ipc:///tmp/kicad/api.sock');options=p.parse_args()
    output=options.output.resolve()
    if not output.is_relative_to(ROOT/'runs'):p.error('output must be under repository runs')
    output.mkdir(parents=True,exist_ok=False)
    report={'status':'running','scope':'real KiCad + SDK STDIO, not autonomous routing or fabrication release','steps':[],'model_api_keys':False}
    def persist():(output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    persist()
    async def scenario():
        env={k:v for k,v in os.environ.items() if 'API_KEY' not in k and 'TOKEN' not in k}
        params=StdioServerParameters(command=sys.executable,args=['-m','pcb_harness.mcp_server','--workspace',str(ROOT),
            '--run-directory',str(output/'service'),'--project',str(ROOT/'runs/capability/live/board.kicad_pcb'),
            '--socket',options.socket,'--max-actions','10','--max-duration-seconds','1200'],env=env)
        async with Client(params) as client:
            report['protocol']=client.protocol_version
            async def call(name,args):
                reply=await client.call_tool(name,args);data=reply.structured_content
                report['steps'].append({'tool':name,'result':data});persist();return data
            connected=await call('pcb_connect',{})
            if not connected.get('ok') or not connected['native_editing_enabled']:raise RuntimeError('verified native backend not connected')
            before=await call('pcb_summary',{});before_revision=before['revision']
            cp=await call('pcb_create_checkpoint',{'name':'baseline','expected_revision':before_revision})
            if not cp['ok']:raise RuntimeError('checkpoint failed')
            baseline=cp['revision'];report['baseline_revision']=baseline
            intent={'action':'move_footprint','args':{'ref':'R1','dx_mm':3,'dy_mm':-2},
                'expected_revision':baseline,'action_id':'move','mode':'permissive'}
            moved=await call('pcb_execute',intent)
            if not moved['ok']:raise RuntimeError('move failed; retain evidence for reconciliation')
            part=await call('pcb_get_footprint',{'ref':'R1'})
            if part['x_mm']!=23 or part['y_mm']!=18:raise RuntimeError('readback failed')
            replay=await call('pcb_execute',intent)
            if not replay['ok'] or not replay['replayed']:raise RuntimeError('replay failed')
            restored=await call('pcb_restore_checkpoint',{'name':'baseline','expected_revision':moved['revision']})
            if not restored['ok'] or restored['revision']!=baseline:raise RuntimeError('baseline restore failed')
            short=await call('pcb_execute',{'action':'route_track','args':{'net':'/NET_A','layer':'F.Cu',
                'points_mm':[[19,20],[21,20]],'width_mm':0.4},'expected_revision':baseline,'action_id':'short'})
            if short.get('error_code')!='GEOMETRY_REGRESSION' or not short.get('rolled_back') or short['revision']!=baseline:
                raise RuntimeError('short rollback failed')
            await call('pcb_disconnect',{});connected=await call('pcb_connect',{})
            if not connected['ok']:raise RuntimeError('reconnect journal not reconciled')
            verified=await call('pcb_verify_geometry',{})
            if not verified['ok'] or verified['geometric'] or verified['connectivity'] or verified['revision']!=baseline:
                raise RuntimeError('final native verification failed')
            report['restored']=True;report['status']='passed';persist()
    try:asyncio.run(scenario())
    except Exception as error:report.update(status='failed',error=str(error));persist();raise
    print('Native MCP STDIO: PASS; actual move/replay/restore/short rollback/reconnect; final DRC/connectivity clean')


if __name__=='__main__':main()
