"""Real native saved-fixture PNGs + actual MCP image delivery; no model API."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from mcp import Client,StdioServerParameters
from pcb_harness.rendering import export_saved_board

ROOT=Path(__file__).resolve().parents[2]
FIXTURE=ROOT/'fixtures/capability/board.kicad_pcb'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'runs'):parser.error('output must be in repository runs/')
    output.mkdir(parents=True,exist_ok=False)
    hashes={str(p.relative_to(FIXTURE.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in FIXTURE.parent.rglob('*') if p.is_file() and p.suffix not in ('.lck','.kicad_prl')}
    revision=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    report={'status':'running','native_source':'immutable saved synthetic fixture; not live editor','input_hashes':hashes}
    def persist():(output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    persist()
    try:
        for name,region in [('board',None),('r1-crop',[16,17,24,23])]:
            result=export_saved_board(FIXTURE,[10,10,70,30],revision,['F.Cu','B.Cu'],output/name,region_mm=region,width_px=1200)
            report[name]={k:v for k,v in result.items() if k!='_image_bytes'};persist()
        after={str(p.relative_to(FIXTURE.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in FIXTURE.parent.rglob('*') if p.is_file() and p.suffix not in ('.lck','.kicad_prl')}
        if after!=hashes:raise RuntimeError('fixture changed during render; discard image evidence')
        async def protocol():
            results=[]
            for mode in ('auto','legacy'):
                params=StdioServerParameters(command=sys.executable,args=['-m','pcb_harness.mcp_server',
                    '--workspace',str(ROOT),'--run-directory',str(output/('demo-'+mode)),'--backend','memory'],
                    env={'PYTHONPATH':str(ROOT/'src')})
                async with Client(params,mode=mode) as client:
                    await client.call_tool('pcb_connect',{})
                    image=await client.call_tool('pcb_render_region',{'region_mm':[16,17,24,23],'layers':['F.Cu'],'width_px':600})
                    if image.is_error or not any(b.type=='image' and b.mime_type=='image/png' for b in image.content):
                        raise RuntimeError('MCP PNG delivery failed')
                    capture=await client.call_tool('pcb_capture_editor',{})
                    if not capture.is_error or any(b.type=='image' for b in capture.content):raise RuntimeError('demo invented screenshot')
                    results.append({'mode':mode,'protocol':client.protocol_version,'image':image.structured_content,
                        'capture_refusal':capture.structured_content})
            return results
        report['mcp']=asyncio.run(protocol());report['status']='passed';persist()
    except Exception as error:report.update(status='failed',error=str(error));persist();raise
    print('Visual acceptance: PASS; actual KiCad saved-fixture board/crop PNGs; modern/legacy MCP ImageContent')
    print(output/'board/render.png');print(output/'r1-crop/render.png')


if __name__=='__main__':main()
