"""Actual MCP SDK client/server protocol, including a real stdio process."""
import asyncio
import json
import os
from pathlib import Path
import sys
import pytest
from mcp import Client,StdioServerParameters
from pcb_harness.mcp_service import MCPService


def inprocess(tmp_path,scenario):
    from pcb_harness.mcp_server import create_server
    service=MCPService(workspace=tmp_path,run_directory=tmp_path/'runs/mcp/test',backend='memory')
    async def run():
        async with Client(create_server(service)) as client:await scenario(client)
    try:asyncio.run(run())
    finally:service.close()


def payload(result):
    data=result.structured_content
    assert isinstance(data,dict)
    text=next(b.text for b in result.content if b.type=='text')
    assert json.loads(text)==data
    return data


def test_actual_discovery_schemas_and_annotations(tmp_path):
    async def scenario(client):
        tools={t.name:t for t in (await client.list_tools()).tools}
        assert {'pcb_status','pcb_connect','pcb_summary','pcb_execute','pcb_create_checkpoint',
            'pcb_restore_checkpoint','pcb_verify_geometry','pcb_disconnect','pcb_get_footprint',
            'pcb_net_info','pcb_list_unrouted','pcb_render_board','pcb_render_region','pcb_capture_editor'}==set(tools)
        assert tools['pcb_summary'].annotations.read_only_hint is True
        assert tools['pcb_execute'].annotations.read_only_hint is False
        assert {'action','args','expected_revision','action_id'}.issubset(tools['pcb_execute'].input_schema['required'])
        assert 'expected_revision' in tools['pcb_create_checkpoint'].input_schema['required']
        status=payload(await client.call_tool('pcb_status',{}))
        assert status['test_only'] and not status['connected']
        assert 'no model API key' in client.instructions
    inprocess(tmp_path,scenario)


def test_actual_protocol_routes_reads_back_rejects_short_and_replays(tmp_path):
    async def scenario(client):
        disconnected=await client.call_tool('pcb_summary',{})
        assert disconnected.is_error and payload(disconnected)['error_code']=='SESSION_NOT_CONNECTED'
        assert not (await client.call_tool('pcb_connect',{})).is_error
        before=payload(await client.call_tool('pcb_summary',{}))['revision']
        args={'action':'route_track','args':{'net':'/NET_A','layer':'F.Cu',
            'points_mm':[[19,20],[19,15],[39,15],[39,20]],'width_mm':0.4},
            'expected_revision':before,'action_id':'route'}
        good=await client.call_tool('pcb_execute',args)
        assert not good.is_error and payload(good)['ok']
        assert payload(await client.call_tool('pcb_net_info',{'net':'/NET_A'}))['track_length_mm']==30
        assert payload(await client.call_tool('pcb_execute',args))['replayed']
        current=payload(await client.call_tool('pcb_summary',{}))['revision']
        bad=await client.call_tool('pcb_execute',{'action':'route_track','args':{'net':'/NET_A',
            'layer':'F.Cu','points_mm':[[19,20],[21,20]],'width_mm':0.4},'expected_revision':current,'action_id':'short'})
        assert bad.is_error and payload(bad)['error_code']=='GEOMETRY_REGRESSION'
        assert payload(await client.call_tool('pcb_summary',{}))['revision']==current
        malformed=await client.call_tool('pcb_execute',{'action':'move_footprint'})
        assert malformed.is_error
    inprocess(tmp_path,scenario)


def test_protocol_checkpoint_and_legacy_text_content(tmp_path):
    async def scenario(client):
        await client.call_tool('pcb_connect',{})
        before=payload(await client.call_tool('pcb_summary',{}))['revision']
        saved=await client.call_tool('pcb_create_checkpoint',{'name':'baseline','expected_revision':before})
        assert not saved.is_error
        action={'action':'move_footprint','args':{'ref':'R1','dx_mm':2,'dy_mm':0},
            'expected_revision':before,'action_id':'move','mode':'permissive'}
        assert not (await client.call_tool('pcb_execute',action)).is_error
        current=payload(await client.call_tool('pcb_summary',{}))['revision']
        restored=await client.call_tool('pcb_restore_checkpoint',{'name':'baseline','expected_revision':current})
        assert payload(restored)['revision']==before
        verified=payload(await client.call_tool('pcb_verify_geometry',{}))
        assert verified['release_verified'] is False and verified['test_only']
    inprocess(tmp_path,scenario)


@pytest.mark.parametrize('mode',['auto','legacy'])
def test_real_stdio_server_works_without_model_keys(tmp_path,mode):
    env={k:v for k,v in os.environ.items() if 'API_KEY' not in k and 'TOKEN' not in k}
    parameters=StdioServerParameters(command=sys.executable,args=['-m','pcb_harness.mcp_server',
        '--workspace',str(tmp_path),'--run-directory',str(tmp_path/'runs/mcp/stdio'),'--backend','memory'],env=env)
    async def scenario():
        async with Client(parameters,mode=mode) as client:
            assert client.server_info.name=='PCB Harness'
            assert len((await client.list_tools()).tools)==14
            await client.call_tool('pcb_connect',{})
            before=payload(await client.call_tool('pcb_summary',{}))['revision']
            result=await client.call_tool('pcb_execute',{'action':'move_footprint',
                'args':{'ref':'R1','dx_mm':2,'dy_mm':0},'expected_revision':before,'action_id':'move','mode':'permissive'})
            assert not result.is_error and payload(result)['test_only']
            footprint=payload(await client.call_tool('pcb_get_footprint',{'ref':'R1'}))
            assert footprint['x_mm']==22
            visual=await client.call_tool('pcb_render_region',{'region_mm':[16,17,26,23],'width_px':600,'layers':['F.Cu']})
            assert not visual.is_error and any(b.type=='image' for b in visual.content)
            assert payload(visual)['revision']==footprint['revision']
            await client.call_tool('pcb_disconnect',{})
            assert not payload(await client.call_tool('pcb_status',{}))['connected']
    asyncio.run(scenario())


def test_mcp_rejects_unknown_top_level_arguments(tmp_path):
    async def scenario(client):
        await client.call_tool('pcb_connect',{})
        result=await client.call_tool('pcb_summary',{'project':'another-board'})
        assert result.is_error
    inprocess(tmp_path,scenario)


def test_native_verification_annotations_report_artifact_writes(tmp_path):
    from pcb_harness.mcp_server import create_server
    service=MCPService(workspace=tmp_path,run_directory=tmp_path/'runs/mcp/native',backend='kicad')
    async def run():
        async with Client(create_server(service)) as client:
            tools={t.name:t for t in (await client.list_tools()).tools}
            for name in ('pcb_list_unrouted','pcb_verify_geometry'):
                assert tools[name].annotations.read_only_hint is False
                assert tools[name].annotations.destructive_hint is False
            assert tools['pcb_get_footprint'].annotations.read_only_hint is True
    try:asyncio.run(run())
    finally:service.close()


def test_actual_mcp_returns_png_image_and_calibrated_crop_metadata(tmp_path):
    import base64,hashlib,io
    from PIL import Image
    async def scenario(client):
        await client.call_tool('pcb_connect',{})
        full=await client.call_tool('pcb_render_board',{'layers':['F.Cu'],'width_px':600})
        assert not full.is_error
        meta=payload(full)
        block=next(b for b in full.content if b.type=='image')
        png=base64.b64decode(block.data)
        assert block.mime_type=='image/png' and hashlib.sha256(png).hexdigest()==meta['image']['sha256']
        assert Image.open(io.BytesIO(png)).width==600 and meta['test_only']
        region=await client.call_tool('pcb_render_region',{'region_mm':[16,17,24,23],'layers':['F.Cu'],'width_px':600})
        assert not region.is_error and payload(region)['region_mm']==[16,17,24,23]
        assert any(b.type=='image' for b in region.content)
        bad=await client.call_tool('pcb_render_region',{'region_mm':[0,0,500,500]})
        assert bad.is_error and not any(b.type=='image' for b in bad.content)
        capture=await client.call_tool('pcb_capture_editor',{})
        assert capture.is_error and payload(capture)['error_code']=='CAPTURE_UNAVAILABLE'
        assert not any(b.type=='image' for b in capture.content)
    inprocess(tmp_path,scenario)
