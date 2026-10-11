"""Real Kernel/Memory state through the service; no mocked MCP calls."""
import json
from pathlib import Path
import pytest
from pcb_harness.contracts import HarnessError


def build(tmp_path,**kwargs):
    from pcb_harness.mcp_service import MCPService
    return MCPService(workspace=tmp_path,run_directory=tmp_path/'runs/mcp/test',backend='memory',**kwargs)


@pytest.fixture
def service(tmp_path):
    s=build(tmp_path)
    try:yield s
    finally:s.close()


def route(service,id='route',revision=None,points=None):
    return service.call('execute',name='route_track',args={'net':'/NET_A','layer':'F.Cu',
        'points_mm':points or [[19,20],[19,15],[39,15],[39,20]],'width_mm':0.4},
        expected_revision=revision or service.call('summary')['revision'],action_id=id)


def test_disconnected_service_is_explicit_and_does_not_route(service):
    assert service.status()['connected'] is False
    result=service.call('summary')
    assert result['error_code']=='SESSION_NOT_CONNECTED' and result['test_only']


def test_real_memory_route_readback_and_repeat_id(service):
    assert service.connect()['ok']
    before=service.call('summary')['revision'];first=route(service,revision=before)
    assert first['ok'] and first['test_only'] and len(first['changed_ids'])==3
    assert service.call('net_info',net='/NET_A')['track_length_mm']==30
    again=route(service,revision=before)
    assert again['replayed'] and service.call('summary')['track_count']==3


def test_short_rolls_back_through_service(service):
    service.connect();before=service.call('summary')['revision']
    result=route(service,points=[[19,20],[21,20]])
    assert result['error_code']=='GEOMETRY_REGRESSION' and result['rolled_back']
    assert service.call('summary')['revision']==before


def test_service_checkpoint_requires_fresh_revision(service):
    service.connect();before=service.call('summary')['revision']
    bad=service.call('create_checkpoint',name='baseline',expected_revision='old')
    assert bad['error_code']=='STALE_REVISION'
    assert service.call('create_checkpoint',name='baseline',expected_revision=before)['ok']
    route(service)
    restored=service.call('restore_checkpoint',name='baseline',expected_revision=service.call('summary')['revision'])
    assert restored['ok'] and restored['revision']==before


def test_same_process_reconnect_does_not_reset_board_or_journal(service):
    service.connect();route(service);revision=service.call('summary')['revision']
    service.disconnect();assert service.connect()['ok']
    assert service.call('summary')['revision']==revision
    assert route(service)['replayed']


def test_uncertain_journal_cannot_be_cleared_by_reconnect(service):
    service.connect();service.disconnect()
    with (service.run_directory/'actions.jsonl').open('a') as stream:
        stream.write(json.dumps({'phase':'started','action_id':'lost'})+'\n')
    result=service.connect()
    assert result['recovery_required']
    assert route(service)['error_code']=='RECOVERY_REQUIRED'
    service.disconnect();assert service.connect()['recovery_required']


def test_missing_native_project_never_falls_back_to_memory(tmp_path):
    from pcb_harness.mcp_service import MCPService
    s=MCPService(workspace=tmp_path,run_directory=tmp_path/'runs/mcp/native',backend='kicad')
    try:
        result=s.connect()
        assert not result['ok'] and result['error_code']=='INVALID_PROJECT'
        assert s.status()['backend']=='kicad' and not s.status()['test_only']
        assert not s.status()['native_editing_enabled']
    finally:s.close()


def test_two_services_cannot_own_one_run_journal(tmp_path):
    s=build(tmp_path)
    try:
        with pytest.raises(HarnessError) as error:build(tmp_path)
        assert error.value.code=='WRITER_BUSY'
    finally:s.close()
    fresh=build(tmp_path);fresh.close()


@pytest.mark.parametrize('location',['outside','runs_root'])
def test_unsafe_run_directory_is_rejected_before_creation(tmp_path,location):
    from pcb_harness.mcp_service import MCPService
    path=tmp_path/'outside' if location=='outside' else tmp_path/'runs'
    with pytest.raises(HarnessError) as error:MCPService(workspace=tmp_path,run_directory=path,backend='memory')
    assert error.value.code=='UNSAFE_ARTIFACTS' and not path.exists()


def test_bad_query_and_arguments_are_structured_errors(service):
    service.connect()
    assert service.call('get_footprint',ref='missing')['error_code']=='UNKNOWN_REF'
    assert service.call('summary',arbitrary_path='/tmp')['error_code']=='INVALID_ARGUMENT'
    assert service.call('reset_recovery')['error_code']=='UNKNOWN_OPERATION'


@pytest.mark.parametrize('operation,arguments',[
    ('execute',{'name':'move_footprint','args':{'ref':'R1','dx_mm':1,'dy_mm':0},'expected_revision':'current','action_id':'a'}),
    ('create_checkpoint',{'name':'baseline','expected_revision':'current'}),
    ('restore_checkpoint',{'name':'baseline','expected_revision':'current'})])
def test_native_gate_blocks_mutations_even_when_queries_can_connect(tmp_path,operation,arguments):
    from pcb_harness.mcp_service import MCPService
    from pcb_harness.kernel import Kernel
    from pcb_harness.memory import MemoryBackend
    s=MCPService(workspace=tmp_path,run_directory=tmp_path/'runs/mcp/native',backend='kicad')
    # Stand in for connected native query state; keep real Kernel mutation logic.
    b=MemoryBackend.fixture();s._kernel=Kernel(b);before=b.revision()
    try:
        result=s.call(operation,**arguments)
        assert result['error_code']=='NATIVE_ACCEPTANCE_REQUIRED'
        assert not result['test_only'] and b.revision()==before and not s._kernel.checkpoints
    finally:s.close()


def test_summary_exposes_only_backend_supported_actions(service):
    service.connect();result=service.call('summary')
    assert 'route_track' in result['capabilities'] and 'add_zone' not in result['capabilities']


def test_disconnect_status_retains_uncertain_recovery_requirement(service):
    service.connect();service.disconnect()
    with (service.run_directory/'actions.jsonl').open('a') as stream:
        stream.write(json.dumps({'phase':'started','action_id':'lost'})+'\n')
    assert service.connect()['recovery_required']
    assert service.disconnect()['recovery_required']
    assert service.status()['recovery_required']


def test_memory_render_is_labelled_revision_bound_and_does_not_edit(service):
    service.connect();before=service.call('summary')['revision']
    r=service.render(['F.Cu'],width_px=600)
    assert r['ok'] and r['test_only'] and r['revision']==before
    assert r['source']=='Memory demo' and r['_image_bytes'].startswith(b'\x89PNG')
    assert service.call('summary')['revision']==before
    capture=service.capture_editor()
    assert not capture['ok'] and capture['error_code']=='CAPTURE_UNAVAILABLE'
    assert '_image_bytes' not in capture


def test_bad_layers_or_crop_do_not_produce_success_image(service):
    service.connect()
    assert not service.render(['Wrong.Cu'])['ok']
    assert not service.render(['F.Cu'],region_mm=[0,0,500,500])['ok']


def test_render_changed_revision_returns_error_not_stale_image(service,monkeypatch):
    from pcb_harness import rendering
    service.connect();original=rendering.render_svg
    def render_then_external_edit(*args,**kwargs):
        result=original(*args,**kwargs)
        service._kernel.backend.footprints['R1']['x_mm']=23
        return result
    monkeypatch.setattr(rendering,'render_svg',render_then_external_edit)
    r=service.render(['F.Cu'])
    assert not r['ok'] and r['error_code']=='CONCURRENT_EDIT'
    assert '_image_bytes' not in r


@pytest.mark.parametrize('version,enabled',[('10.0.0',False),('10.0.6',True),('10.0.6-rc1',False),('10.0.6-12-gdeadbeef',False),('10.0.7',False),('11.0.0',False)])
def test_native_gate_matches_exact_acceptance_version_and_connected_instance(tmp_path,version,enabled):
    from pcb_harness.mcp_service import MCPService
    from pcb_harness.kernel import Kernel
    from pcb_harness.memory import MemoryBackend
    from kipy.kicad import KiCadVersion
    s=MCPService(workspace=tmp_path,run_directory=tmp_path/'runs/native-gate',backend='kicad')
    b=MemoryBackend.fixture();b.kind='kicad-ipc-scratch';b.server_version=KiCadVersion.from_git_describe(version)
    s._kernel=Kernel(b);s._native=b
    try:
        assert s.status()['native_editing_enabled'] is enabled
        revision=b.revision()
        action=s.call('execute',name='move_footprint',args={'ref':'R1','dx_mm':2,'dy_mm':0},expected_revision=revision,action_id='move')
        assert action['ok'] is enabled
        if enabled:assert b.get_footprint('R1')['x_mm']==22
        else:assert action['error_code']=='NATIVE_ACCEPTANCE_REQUIRED' and b.revision()==revision
    finally:s._native=None;s.close()


def test_native_version_on_a_foreign_kernel_cannot_unlock_writes(tmp_path):
    from pcb_harness.mcp_service import MCPService
    from pcb_harness.kernel import Kernel
    from pcb_harness.memory import MemoryBackend
    from kipy.kicad import KiCadVersion
    s=MCPService(workspace=tmp_path,run_directory=tmp_path/'runs/native-gate',backend='kicad')
    kernel_board=MemoryBackend.fixture();foreign=MemoryBackend.fixture()
    foreign.kind='kicad-ipc-scratch';foreign.server_version=KiCadVersion.from_git_describe('10.0.6')
    s._kernel=Kernel(kernel_board);s._native=foreign
    try:assert s.status()['native_editing_enabled'] is False
    finally:s._native=None;s.close()
