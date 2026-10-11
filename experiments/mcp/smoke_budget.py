"""Frozen-budget acceptance through real STDIO, without model calls or KiCad edits."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import Client,StdioServerParameters

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output.resolve()
    if not output.is_relative_to(ROOT/'runs'):parser.error('output must be under repository runs/')
    output.mkdir(parents=True,exist_ok=False)
    report={'status':'running','scope':'actual SDK STDIO + Memory only; no native or subscribed-host routing proof',
        'model_api_keys':False,'host_model':'unavailable','tokens':'unavailable','model_cost':'unavailable','modes':[]}
    def persist():(output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    persist()
    async def run():
        env={k:v for k,v in os.environ.items() if 'API_KEY' not in k and 'TOKEN' not in k}
        for mode in ('auto','legacy'):
            directory=output/mode
            parameters=StdioServerParameters(command=sys.executable,args=['-m','pcb_harness.mcp_server',
                '--workspace',str(ROOT),'--run-directory',str(directory),'--backend','memory',
                '--max-actions','6','--max-duration-seconds','1200'],env=env)
            async with Client(parameters,mode=mode) as client:
                entry={'mode':mode,'protocol_version':client.protocol_version,'results':[]}
                async def call(name,arguments):
                    result=await client.call_tool(name,arguments)
                    entry['results'].append({'tool':name,'data':result.structured_content})
                    return result
                async def revision():return (await call('pcb_summary',{})).structured_content['revision']
                await call('pcb_connect',{});before=await revision()
                invalid=await call('pcb_execute',{'action':'move_footprint'})
                if invalid.structured_content['error_code']!='INVALID_ARGUMENT':raise RuntimeError('schema rejection lost')
                saved=await call('pcb_create_checkpoint',{'name':'base','expected_revision':before})
                if saved.is_error:raise RuntimeError('checkpoint failed')
                intent={'action':'move_footprint','args':{'ref':'R1','dx_mm':2,'dy_mm':0},
                    'expected_revision':before,'action_id':'move'}
                accepted=await call('pcb_execute',intent)
                if accepted.is_error:raise RuntimeError('movement failed')
                replay=await call('pcb_execute',intent)
                if not replay.structured_content['replayed']:raise RuntimeError('replay lost')
                stale=await call('pcb_execute',{**intent,'action_id':'stale'})
                if stale.structured_content['error_code']!='STALE_REVISION':raise RuntimeError('stale rejection lost')
                restored=await call('pcb_restore_checkpoint',{'name':'base','expected_revision':await revision()})
                if restored.is_error or restored.structured_content['revision']!=before:raise RuntimeError('restore failed')
                denied=await call('pcb_execute',{**intent,'action_id':'exhausted'})
                if denied.structured_content['error_code']!='RUN_ACTION_LIMIT':raise RuntimeError('budget did not stop')
                await call('pcb_disconnect',{});await call('pcb_connect',{})
                status=(await call('pcb_status',{})).structured_content
                if status['run_budget']['attempts_used']!=6:raise RuntimeError('reconnect reset count')
                footprint=(await call('pcb_get_footprint',{'ref':'R1'})).structured_content
                if footprint['x_mm']!=20:raise RuntimeError('baseline was not retained')
                verification=await call('pcb_verify_geometry',{})
                if verification.is_error or verification.structured_content['release_verified']:raise RuntimeError('verification unavailable after exhaustion')
                image=await call('pcb_render_board',{'width_px':600,'layers':['F.Cu']})
                if image.is_error or not any(b.type=='image' for b in image.content):raise RuntimeError('inspection image unavailable')
                entry['inspection_image']=True
            rows=[json.loads(x) for x in (directory/'run.jsonl').read_text().splitlines()]
            started=[x for x in rows if x['phase']=='started'];finished=[x for x in rows if x['phase']=='finished']
            if len(started)!=6 or len(finished)!=6:raise RuntimeError('durable attempt evidence mismatch')
            entry['durable_attempts']=len(started)
            entry['outcomes']=finished
            report['modes'].append(entry);persist()
        report['status']='passed';persist()
    try:asyncio.run(run())
    except Exception as error:report.update(status='failed',error=str(error));persist();raise
    print('MCP budget: PASS; modern + legacy, invalid/replay/stale/checkpoint requests counted, exhausted writes blocked, inspection retained')


if __name__=='__main__':main()
