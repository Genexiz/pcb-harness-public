"""Real service and SDK boundary enforce frozen write admission."""
import asyncio
import json
import os
import sys
import pytest
from mcp import Client,StdioServerParameters
from pcb_harness.contracts import HarnessError
from pcb_harness.mcp_service import MCPService
from pcb_harness.mcp_server import create_server


def build(tmp_path,**kwargs):
    return MCPService(workspace=tmp_path,run_directory=tmp_path/'runs/test',backend='memory',**kwargs)


def move(service,id='move',revision=None):
    return service.call('execute',name='move_footprint',args={'ref':'R1','dx_mm':2,'dy_mm':0},
        expected_revision=revision or service.call('summary')['revision'],action_id=id)


def test_exhausted_budget_blocks_move_but_allows_reads_and_render(tmp_path):
    service=build(tmp_path,max_actions=1)
    try:
        service.connect();first=move(service)
        assert first['ok'] and first['run_budget']['attempts_used']==1
        assert move(service,'second')['error_code']=='RUN_ACTION_LIMIT'
        assert service.call('get_footprint',ref='R1')['x_mm']==22
        assert service.call('verify')['release_verified'] is False
        assert service.render(['F.Cu'],width_px=600)['ok']
    finally:service.close()


def test_replay_and_stale_rejections_consume_allowance(tmp_path):
    service=build(tmp_path,max_actions=3)
    try:
        service.connect();before=service.call('summary')['revision']
        assert move(service,revision=before)['ok']
        assert move(service,revision=before)['replayed']
        stale=move(service,'stale',revision=before)
        assert stale['error_code']=='STALE_REVISION' and stale['run_budget']['attempts_used']==3
        assert move(service,'fresh')['error_code']=='RUN_ACTION_LIMIT'
    finally:service.close()


def test_rollback_is_counted_and_reconnect_does_not_reset(tmp_path):
    service=build(tmp_path,max_actions=1)
    try:
        service.connect();before=service.call('summary')['revision']
        short=service.call('execute',name='route_track',args={'net':'/NET_A','layer':'F.Cu',
            'points_mm':[[19,20],[21,20]],'width_mm':0.4},expected_revision=before,action_id='short')
        assert short['rolled_back'] and short['run_budget']['attempts_used']==1
        service.disconnect();service.connect()
        assert service.call('summary')['revision']==before
        assert move(service)['error_code']=='RUN_ACTION_LIMIT'
    finally:service.close()


def test_checkpoints_and_disconnected_requests_cannot_evade_counting(tmp_path):
    service=build(tmp_path,max_actions=2)
    try:
        disconnected=service.call('execute',name='move_footprint')
        assert disconnected['error_code']=='SESSION_NOT_CONNECTED' and disconnected['run_budget']['attempts_used']==1
        service.connect();before=service.call('summary')['revision']
        assert service.call('create_checkpoint',name='base',expected_revision=before)['ok']
        assert service.call('restore_checkpoint',name='base',expected_revision=before)['error_code']=='RUN_ACTION_LIMIT'
    finally:service.close()


def test_existing_action_journal_is_not_silently_given_fresh_budget(tmp_path):
    directory=tmp_path/'runs/test';directory.mkdir(parents=True)
    (directory/'actions.jsonl').write_text('{}\n')
    with pytest.raises(HarnessError) as error:build(tmp_path)
    assert error.value.code=='RUN_MIGRATION_REQUIRED'
    # Failed construction releases the lease: subsequent attempt reports same error, not WRITER_BUSY.
    with pytest.raises(HarnessError) as again:build(tmp_path)
    assert again.value.code=='RUN_MIGRATION_REQUIRED'


def test_native_acceptance_failure_is_recorded_without_edit(tmp_path):
    service=MCPService(workspace=tmp_path,run_directory=tmp_path/'runs/test',backend='kicad',max_actions=2)
    from pcb_harness.kernel import Kernel
    from pcb_harness.memory import MemoryBackend
    board=MemoryBackend.fixture();service._kernel=Kernel(board);before=board.revision()
    try:
        result=move(service)
        assert result['error_code']=='NATIVE_ACCEPTANCE_REQUIRED'
        assert result['run_budget']['attempts_used']==1 and board.revision()==before
    finally:service.close()


def test_envelope_evidence_failure_blocks_board_and_keeps_inspection(tmp_path,monkeypatch):
    service=build(tmp_path)
    try:
        service.connect();before=service.call('summary')['revision']
        import pcb_harness.run_envelope as module
        monkeypatch.setattr(module.os,'fsync',lambda fd:(_ for _ in ()).throw(OSError('disk failure')))
        bad=move(service)
        assert bad['error_code']=='RUN_EVIDENCE_REQUIRED' and bad['recovery_required']
        assert service.call('summary')['revision']==before
    finally:service.close()


def test_terminal_evidence_failure_does_not_retry_successful_move(tmp_path,monkeypatch):
    service=build(tmp_path)
    try:
        service.connect()
        import pcb_harness.run_envelope as module
        real_fsync=module.os.fsync
        evidence=service.run_directory/'run.jsonl'
        def fail_last(fd):
            if module.os.fstat(fd).st_ino==evidence.stat().st_ino and '"phase": "finished"' in evidence.read_text():
                raise OSError('terminal write failure')
            return real_fsync(fd)
        monkeypatch.setattr(module.os,'fsync',fail_last)
        result=move(service)
        assert result['error_code']=='RUN_EVIDENCE_REQUIRED' and result['recovery_required']
        assert service.call('get_footprint',ref='R1')['x_mm']==22
        assert not move(service,'new')['ok']
        assert service.call('get_footprint',ref='R1')['x_mm']==22
    finally:service.close()


def test_actual_sdk_invalid_write_consumes_budget_before_dispatch(tmp_path):
    service=build(tmp_path,max_actions=1)
    async def scenario():
        async with Client(create_server(service)) as client:
            await client.call_tool('pcb_connect',{})
            result=await client.call_tool('pcb_execute',{'action':'move_footprint'})
            assert result.is_error and result.structured_content['error_code']=='INVALID_ARGUMENT'
            assert result.structured_content['run_budget']['attempts_used']==1
            before=(await client.call_tool('pcb_summary',{})).structured_content['revision']
            denied=await client.call_tool('pcb_execute',{'action':'move_footprint',
                'args':{'ref':'R1','dx_mm':2,'dy_mm':0},'expected_revision':before,'action_id':'new'})
            assert denied.structured_content['error_code']=='RUN_ACTION_LIMIT'
            assert (await client.call_tool('pcb_get_footprint',{'ref':'R1'})).structured_content['x_mm']==20
    try:asyncio.run(scenario())
    finally:service.close()


@pytest.mark.parametrize('mode',['auto','legacy'])
def test_real_stdio_frozen_budget_without_model_keys(tmp_path,mode):
    env={k:v for k,v in os.environ.items() if 'API_KEY' not in k and 'TOKEN' not in k}
    params=StdioServerParameters(command=sys.executable,args=['-m','pcb_harness.mcp_server',
        '--workspace',str(tmp_path),'--run-directory',str(tmp_path/'runs/test'),
        '--backend','memory','--max-actions','1','--max-duration-seconds','1200'],env=env)
    async def scenario():
        async with Client(params,mode=mode) as client:
            await client.call_tool('pcb_connect',{})
            before=(await client.call_tool('pcb_summary',{})).structured_content['revision']
            arguments={'action':'move_footprint','args':{'ref':'R1','dx_mm':2,'dy_mm':0},
                'expected_revision':before,'action_id':'one'}
            accepted=await client.call_tool('pcb_execute',arguments)
            assert accepted.structured_content['ok']
            denied=await client.call_tool('pcb_execute',{**arguments,'action_id':'two'})
            assert denied.is_error and denied.structured_content['error_code']=='RUN_ACTION_LIMIT'
            assert (await client.call_tool('pcb_status',{})).structured_content['run_budget']['attempts_used']==1
            assert (await client.call_tool('pcb_get_footprint',{'ref':'R1'})).structured_content['x_mm']==22
    asyncio.run(scenario())


def test_expired_run_allows_verification_but_no_new_board_write(tmp_path,monkeypatch):
    import pcb_harness.run_envelope as module
    values={'wall':1000.,'mono':10.}
    monkeypatch.setattr(module,'wall_time',lambda:values['wall'])
    monkeypatch.setattr(module,'monotonic',lambda:values['mono'])
    service=build(tmp_path,max_duration_seconds=60)
    try:
        service.connect();first=move(service)
        assert first['ok']
        values.update(wall=1060.,mono=70.)
        rejected=move(service,'next')
        assert rejected['error_code']=='RUN_TIME_LIMIT'
        assert service.call('get_footprint',ref='R1')['x_mm']==22
        assert service.call('verify')['run_budget']['deadline_reached']
        service.disconnect();service.connect()
        assert move(service,'again')['error_code']=='RUN_TIME_LIMIT'
    finally:service.close()


def test_raw_legacy_argument_array_cannot_evade_admission(tmp_path):
    async def scenario():
        process=await asyncio.create_subprocess_exec(sys.executable,'-m','pcb_harness.mcp_server',
            '--workspace',str(tmp_path),'--run-directory',str(tmp_path/'runs/raw'),
            '--backend','memory','--max-actions','1',stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        async def rpc(id,method,params):
            process.stdin.write((json.dumps({'jsonrpc':'2.0','id':id,'method':method,'params':params})+'\n').encode())
            await process.stdin.drain()
            return json.loads(await asyncio.wait_for(process.stdout.readline(),10))
        try:
            initialized=await rpc(1,'initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'raw-budget-test','version':'1'}})
            assert 'result' in initialized
            process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            await process.stdin.drain()
            invalid=await rpc(2,'tools/call',{'name':'pcb_execute','arguments':[]})
            assert invalid['error']['code']==-32602
            status=await rpc(3,'tools/call',{'name':'pcb_status','arguments':{}})
            data=status['result']['structuredContent']
            assert data['run_budget']['attempts_used']==1 and data['run_budget']['started_at'] is not None
        finally:
            process.stdin.close()
            await asyncio.wait_for(process.wait(),10)
    asyncio.run(scenario())
