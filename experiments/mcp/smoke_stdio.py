"""Reproducible SDK STDIO proof on explicit Memory demo; never edits KiCad."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from mcp import Client,StdioServerParameters

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'runs'):parser.error('output must be under repository runs/')
    output.mkdir(parents=True,exist_ok=False)
    report={'status':'running','scope':'SDK STDIO client; Memory demo only, not KiCad or subscribed-host routing',
        'model_api_keys':False,'modes':[]}
    def persist():(output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    persist()
    async def run():
        for mode in ('auto','legacy'):
            parameters=StdioServerParameters(command=sys.executable,args=['-m','pcb_harness.mcp_server',
                '--workspace',str(ROOT),'--run-directory',str(output/mode),'--backend','memory'],
                env={'PYTHONPATH':str(ROOT/'src')})
            async with Client(parameters,mode=mode) as client:
                entry={'mode':mode,'protocol_version':client.protocol_version,
                    'server':client.server_info.model_dump(mode='json'),
                    'tools':[t.name for t in (await client.list_tools()).tools]}
                if len(entry['tools'])!=14:raise RuntimeError('tool discovery mismatch')
                await client.call_tool('pcb_connect',{})
                before=(await client.call_tool('pcb_summary',{})).structured_content['revision']
                intent={'action':'move_footprint','args':{'ref':'R1','dx_mm':2,'dy_mm':0},
                    'expected_revision':before,'action_id':'move','mode':'permissive'}
                result=await client.call_tool('pcb_execute',intent)
                entry['move']=result.structured_content
                actual=(await client.call_tool('pcb_get_footprint',{'ref':'R1'})).structured_content
                if result.is_error or actual['x_mm']!=22:raise RuntimeError('move/readback failed')
                repeated=await client.call_tool('pcb_execute',intent)
                if not repeated.structured_content['replayed']:raise RuntimeError('replay not reconciled')
                bad=await client.call_tool('pcb_execute',{**intent,'action_id':'stale'})
                entry['stale']=bad.structured_content
                if not bad.is_error or bad.structured_content['error_code']!='STALE_REVISION':
                    raise RuntimeError('stale action accepted')
                report['modes'].append(entry);persist()
        report['status']='passed';persist()
    try:asyncio.run(run())
    except Exception as error:report.update(status='failed',error=str(error));persist();raise
    print('MCP STDIO: PASS; modern + legacy, 14 tools, real demo mutation/replay/stale rejection')


if __name__=='__main__':main()
