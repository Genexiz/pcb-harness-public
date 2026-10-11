"""Behavioral tests on a real limited Memory backend, not mocked API calls."""
from pathlib import Path
import importlib.util
import pytest


def setup_kernel(tmp_path=None):
    assert importlib.util.find_spec('pcb_harness.kernel'), 'Kernel not implemented'
    from pcb_harness.kernel import Kernel
    from pcb_harness.memory import MemoryBackend
    backend=MemoryBackend.fixture()
    return Kernel(backend,journal_path=tmp_path/'actions.jsonl' if tmp_path else None),backend


def execute(kernel,name,args,*,mode='strict',action_id='action-1',revision=None):
    return kernel.execute(name,args,expected_revision=revision or kernel.summary()['revision'],
        action_id=action_id,mode=mode)


def route_args(points=None,width=0.4,net='/NET_A',layer='F.Cu'):
    return {'net':net,'layer':layer,'points_mm':points or [[19,20],[19,15],[39,15],[39,20]],'width_mm':width}


def test_explicit_polyline_commits_despite_partial_unrouted_state():
    k,b=setup_kernel();old=k.summary()['revision']
    result=execute(k,'route_track',route_args())
    assert result['ok'] is True and result['revision']!=old
    assert len(result['changed_ids'])==3
    assert k.summary()['unrouted_count']>0


def test_new_short_is_rejected_and_baseline_restored():
    k,b=setup_kernel();before=k.summary()
    result=execute(k,'route_track',route_args([[19,20],[21,20]]))
    assert result['ok'] is False and result['error_code']=='GEOMETRY_REGRESSION'
    assert any(v['type']=='shorting_items' for v in result['drc_delta']['added'])
    assert k.summary()==before


def test_permissive_short_commits_and_reports_actual_violation():
    k,b=setup_kernel()
    result=execute(k,'route_track',route_args([[19,20],[21,20]]),mode='permissive')
    assert result['ok'] is True
    assert result['drc_delta']['added']
    assert k.summary()['geometric_issue_count']>0


def test_too_narrow_track_is_rejected_by_verification():
    k,b=setup_kernel();before=k.summary()['revision']
    result=execute(k,'route_track',route_args(width=0.1))
    assert result['error_code']=='GEOMETRY_REGRESSION'
    assert any(v['type']=='track_width' for v in result['drc_delta']['added'])
    assert k.summary()['revision']==before


def test_stale_revision_stops_before_edit():
    k,b=setup_kernel();before=k.summary()
    result=execute(k,'route_track',route_args(),revision='outdated')
    assert result['error_code']=='STALE_REVISION'
    assert k.summary()==before


def test_locked_footprint_stops_before_edit():
    k,b=setup_kernel();b.footprints['R1']['locked']=True;before=k.summary()
    result=execute(k,'place_footprint',{'ref':'R1','x_mm':25,'y_mm':20,'rotation_deg':90})
    assert result['error_code']=='LOCKED_OBJECT'
    assert k.summary()==before


def test_relative_move_and_rotation_are_explicit_intent_helpers():
    k,b=setup_kernel()
    assert execute(k,'move_footprint',{'ref':'R1','dx_mm':3,'dy_mm':-2},mode='permissive')['ok']
    assert execute(k,'rotate_footprint',{'ref':'R1','deg':90},mode='permissive',action_id='rotate')['ok']
    f=k.get_footprint('R1')
    assert f['x_mm']==23 and f['y_mm']==18 and f['rotation_deg']==90
    assert {p['number']:p['position_mm'] for p in f['pads']}=={'1':[23,19],'2':[23,17]}


@pytest.mark.parametrize('case,error',[('unknown_net','UNKNOWN_NET'),('unknown_layer','UNKNOWN_LAYER'),
    ('outside','OUT_OF_BOARD'),('nan','INVALID_ARGUMENT'),('infinity','INVALID_ARGUMENT'),
    ('boolean','INVALID_ARGUMENT'),('one_point','INVALID_ARGUMENT'),('zero_segment','INVALID_ARGUMENT'),
    ('negative_width','INVALID_ARGUMENT')])
def test_invalid_geometry_and_references_do_not_mutate(case,error):
    k,b=setup_kernel();before=k.summary()
    args=route_args()
    if case=='unknown_net':args['net']='missing'
    if case=='unknown_layer':args['layer']='F.SilkS'
    if case=='outside':args['points_mm']=[[19,20],[100,100]]
    if case=='nan':args['width_mm']=float('nan')
    if case=='infinity':args['points_mm']=[[19,20],[float('inf'),15]]
    if case=='boolean':args['width_mm']=True
    if case=='one_point':args['points_mm']=[[19,20]]
    if case=='zero_segment':args['points_mm']=[[19,20],[19,20]]
    if case=='negative_width':args['width_mm']=-1
    result=execute(k,'route_track',args)
    assert result['error_code']==error
    assert k.summary()==before


def test_repeated_action_id_cannot_route_twice(tmp_path):
    k,b=setup_kernel(tmp_path);revision=k.summary()['revision'];args=route_args()
    first=execute(k,'route_track',args,revision=revision)
    count=len(b.tracks)
    replay=execute(k,'route_track',args,revision=revision)
    assert first['ok'] and replay['ok'] and replay['replayed']
    assert len(b.tracks)==count


def test_reusing_action_id_for_different_intent_is_rejected():
    k,b=setup_kernel();execute(k,'route_track',route_args())
    result=execute(k,'route_track',route_args(width=0.5))
    assert result['error_code']=='ACTION_ID_CONFLICT'


def test_delete_restores_connectivity_issue_without_new_geometry_issue():
    k,b=setup_kernel();r=execute(k,'route_track',route_args())
    result=execute(k,'delete_track',{'id':r['changed_ids'][0]},action_id='delete')
    assert result['ok'] and not result['drc_delta']['added']


def test_via_layers_and_dimensions_are_validated():
    k,b=setup_kernel();before=k.summary()
    result=execute(k,'add_via',{'net':'/NET_A','x_mm':19,'y_mm':15,
        'drill_mm':0.8,'dia_mm':0.6,'layers':['F.Cu','B.Cu']})
    assert result['error_code']=='INVALID_ARGUMENT' and k.summary()==before


def test_unsupported_capability_is_explicit():
    k,b=setup_kernel()
    result=execute(k,'flip_footprint',{'ref':'R1'})
    assert result['error_code']=='UNSUPPORTED_CAPABILITY'


def test_restart_replays_completed_action_without_applying_again(tmp_path):
    k,b=setup_kernel(tmp_path);revision=k.summary()['revision'];args=route_args()
    first=execute(k,'route_track',args,revision=revision)
    from pcb_harness.kernel import Kernel
    resumed=Kernel(b,journal_path=tmp_path/'actions.jsonl')
    result=execute(resumed,'route_track',args,revision=revision)
    assert result['replayed'] and result['changed_ids']==first['changed_ids']
    assert len(b.tracks)==3


def test_unfinished_journal_blocks_new_writes(tmp_path):
    import json
    path=tmp_path/'actions.jsonl'
    path.write_text(json.dumps({'phase':'started','action_id':'lost-reply','intent':{'name':'route_track','args':route_args()},'expected_revision':'old'})+'\n')
    k,b=setup_kernel(tmp_path)
    result=execute(k,'route_track',route_args(),action_id='new')
    assert result['error_code']=='RECOVERY_REQUIRED'
    assert len(b.tracks)==0


@pytest.mark.parametrize('field,value',[('name',[]),('layer',[]),('points_mm','not-points'),('args',None)])
def test_malformed_tool_arguments_return_errors_without_crashing(field,value):
    k,b=setup_kernel();before=k.summary();args=route_args();name='route_track'
    if field=='name':name=value
    elif field=='args':args=value
    else:args[field]=value
    result=execute(k,name,args)
    assert result['ok'] is False
    assert k.summary()==before


def test_via_to_other_net_track_short_is_rejected():
    k,b=setup_kernel();execute(k,'route_track',route_args())
    before=k.summary()
    result=execute(k,'add_via',{'net':'/NET_B','x_mm':19,'y_mm':15,
        'drill_mm':0.3,'dia_mm':0.6,'layers':['F.Cu','B.Cu']},action_id='via')
    assert result['error_code']=='GEOMETRY_REGRESSION'
    assert k.summary()==before


def test_track_edge_clearance_uses_width_not_only_centerline():
    k,b=setup_kernel();before=k.summary()
    result=execute(k,'route_track',route_args([[10.1,12],[10.1,18]]))
    assert result['error_code']=='GEOMETRY_REGRESSION'
    assert any(v['type']=='copper_edge_clearance' for v in result['drc_delta']['added'])
    assert k.summary()==before


def test_simultaneous_intents_with_same_revision_cannot_both_commit():
    from concurrent.futures import ThreadPoolExecutor
    import time
    from pcb_harness.memory import MemoryBackend
    from pcb_harness.kernel import Kernel
    class SlowBackend(MemoryBackend):
        def apply(self,name,args):
            time.sleep(0.02)
            return super().apply(name,args)
    b=SlowBackend.fixture();k=Kernel(b);revision=k.summary()['revision']
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(execute,k,'route_track',route_args(),revision=revision,action_id=str(i)) for i in range(2)]
        results=[f.result() for f in futures]
    assert sum(r['ok'] for r in results)==1
    assert any(r.get('error_code')=='STALE_REVISION' for r in results)


def test_named_checkpoint_restores_earlier_state_after_multiple_actions(tmp_path):
    k,b=setup_kernel(tmp_path);baseline=k.summary()
    create=getattr(k,'create_checkpoint',None)
    assert callable(create),'named project checkpoints missing'
    create('before-routing')
    execute(k,'route_track',route_args())
    execute(k,'move_footprint',{'ref':'R3','dx_mm':2,'dy_mm':0},mode='permissive',action_id='move')
    result=k.restore_checkpoint('before-routing',expected_revision=k.summary()['revision'])
    assert result['ok'] and k.summary()==baseline


def test_named_checkpoint_is_available_after_restart(tmp_path):
    k,b=setup_kernel(tmp_path)
    create=getattr(k,'create_checkpoint',None)
    assert callable(create),'persisted checkpoint missing'
    baseline=k.summary();create('baseline');execute(k,'route_track',route_args())
    from pcb_harness.kernel import Kernel
    resumed=Kernel(b,journal_path=tmp_path/'actions.jsonl')
    result=resumed.restore_checkpoint('baseline',expected_revision=resumed.summary()['revision'])
    assert result['ok'] and resumed.summary()==baseline


def test_checkpoint_restore_rejects_stale_revision():
    k,b=setup_kernel()
    create=getattr(k,'create_checkpoint',None)
    assert callable(create),'checkpoint restore missing'
    create('baseline');execute(k,'route_track',route_args());before=k.summary()
    result=k.restore_checkpoint('baseline',expected_revision='old')
    assert result['error_code']=='STALE_REVISION' and k.summary()==before


def test_courtyard_overlap_is_rejected_even_when_pad_nets_match():
    k,b=setup_kernel();before=k.summary()
    result=execute(k,'place_footprint',{'ref':'R2','x_mm':20,'y_mm':20,'rotation_deg':0})
    assert result['error_code']=='GEOMETRY_REGRESSION'
    assert any(v['type']=='courtyards_overlap' for v in result['drc_delta']['added'])
    assert k.summary()==before


def test_through_vias_join_copper_on_both_layers():
    k,b=setup_kernel()
    for i,(points,layer) in enumerate([([[19,20],[19,18]],'F.Cu'),([[19,18],[39,18]],'B.Cu'),([[39,18],[39,20]],'F.Cu')]):
        assert execute(k,'route_track',route_args(points,layer=layer),action_id=f'route-{i}')['ok']
    for x in [19,39]:
        assert execute(k,'add_via',{'net':'/NET_A','x_mm':x,'y_mm':18,'drill_mm':0.3,
            'dia_mm':0.6,'layers':['F.Cu','B.Cu']},action_id=f'via-{x}')['ok']
    issue=next(v for v in b.verify()['connectivity'] if v['net']=='/NET_A')
    assert issue['groups']==2  # R1 and R2 joined; R3 still open


def test_backend_disconnect_before_action_returns_structured_error():
    from pcb_harness.memory import MemoryBackend
    from pcb_harness.kernel import Kernel
    class Disconnected(MemoryBackend):
        def revision(self):raise OSError('socket closed')
    k=Kernel(Disconnected.fixture())
    result=k.execute('route_track',route_args(),expected_revision='old',action_id='attempt')
    assert result['ok'] is False and result['error_code']=='BACKEND_UNAVAILABLE'


def test_net_query_exposes_exact_pad_positions_and_length_without_planning_routes():
    k,b=setup_kernel()
    query=getattr(k,'net_info',None)
    assert callable(query),'net geometry query missing'
    info=query('/NET_A')
    assert {(p['ref'],p['position_mm'][0]) for p in info['pads']}=={('R1',19),('R2',39),('R3',59)}
    execute(k,'route_track',route_args())
    assert k.net_info('/NET_A')['track_length_mm']==30


def test_unrouted_query_reports_current_connectivity_findings():
    k,b=setup_kernel()
    query=getattr(k,'list_unrouted',None)
    assert callable(query),'connectivity query missing'
    assert {v['net'] for v in query()['items']}=={'/NET_A','/NET_B'}
    assert query()['revision']==k.summary()['revision']


def test_foreign_project_journal_blocks_replay_and_writes(tmp_path):
    k,b=setup_kernel(tmp_path);execute(k,'route_track',route_args())
    from pcb_harness.memory import MemoryBackend
    from pcb_harness.kernel import Kernel
    other=MemoryBackend.fixture();foreign=Kernel(other,journal_path=tmp_path/'actions.jsonl')
    result=execute(foreign,'route_track',route_args())
    assert result['error_code']=='RECOVERY_REQUIRED' and result['recovery_required']
    assert len(other.tracks)==0


def test_restart_with_lost_completed_state_requires_recovery(tmp_path):
    k,b=setup_kernel(tmp_path);token=b.checkpoint();execute(k,'route_track',route_args())
    b.restore(token,expected_current=b.revision())  # represents reopened pre-action state
    from pcb_harness.kernel import Kernel
    resumed=Kernel(b,journal_path=tmp_path/'actions.jsonl')
    result=execute(resumed,'route_track',route_args())
    assert result['error_code']=='RECOVERY_REQUIRED' and len(b.tracks)==0


@pytest.mark.parametrize('failure',['journal','readback'])
def test_restore_evidence_failure_latches_recovery_and_blocks_next_action(tmp_path,failure):
    k,b=setup_kernel(tmp_path);k.create_checkpoint('before');execute(k,'route_track',route_args())
    if failure=='journal':
        append=k._append
        def fail_finished(row):
            if row['phase']=='finished' and row['action_id'].startswith('restore-'):raise OSError('disk full')
            append(row)
        k._append=fail_finished
    else:
        restore=b.restore;revision=b.revision;state={'restored':False}
        def restore_then_disconnect(*args,**kwargs):
            restore(*args,**kwargs);state['restored']=True
        def failed_revision():
            if state['restored']:raise OSError('readback disconnected')
            return revision()
        b.restore=restore_then_disconnect;b.revision=failed_revision
    result=k.restore_checkpoint('before',expected_revision=k.summary()['revision'])
    assert result['ok'] is False and result['recovery_required']
    if failure=='readback':b.revision=revision
    next_result=execute(k,'route_track',route_args(),action_id='new')
    assert next_result['error_code']=='RECOVERY_REQUIRED' and next_result['recovery_required']
    assert len(b.tracks)==0


def test_replay_of_action_invalidated_by_later_restore_is_not_current_success():
    k,b=setup_kernel();k.create_checkpoint('before');execute(k,'route_track',route_args())
    k.restore_checkpoint('before',expected_revision=k.summary()['revision'])
    result=execute(k,'route_track',route_args())
    assert result['ok'] is False and result['error_code']=='ACTION_RESULT_STALE'
    assert len(b.tracks)==0


def test_violation_delta_preserves_duplicate_findings():
    from pcb_harness.kernel import violation_map
    issue={'type':'clearance','ids':['a','b'],'description':'gap'}
    assert sum(violation_map([issue,issue]).values())==2


def test_footprint_query_includes_current_revision():
    k,b=setup_kernel()
    assert k.get_footprint('R1')['revision']==k.summary()['revision']


def test_front_request_for_existing_back_footprint_does_not_pretend_to_flip():
    k,b=setup_kernel();b.footprints['R1']['side']='back';before=k.summary()
    result=execute(k,'place_footprint',{'ref':'R1','x_mm':20,'y_mm':20,'side':'front'})
    assert result['error_code']=='UNSUPPORTED_CAPABILITY' and k.summary()==before


@pytest.mark.parametrize('failure',['journal','readback'])
def test_checkpoint_creation_evidence_failure_blocks_future_writes(tmp_path,failure):
    from pcb_harness.contracts import HarnessError
    k,b=setup_kernel(tmp_path)
    if failure=='journal':
        original=k._append
        def fail_checkpoint(row):
            if row['phase']=='checkpoint':raise OSError('disk full')
            original(row)
        k._append=fail_checkpoint
    else:
        original_revision=b.revision
        original_checkpoint=b.checkpoint
        state={'checkpointed':False}
        def checkpoint_then_disconnect(**kwargs):
            token=original_checkpoint(**kwargs);state['checkpointed']=True;return token
        def failed_readback():
            if state['checkpointed']:raise OSError('checkpoint readback lost')
            return original_revision()
        b.checkpoint=checkpoint_then_disconnect;b.revision=failed_readback
    with pytest.raises(HarnessError) as error:k.create_checkpoint('baseline')
    assert error.value.code=='RECOVERY_REQUIRED'
    if failure=='readback':b.revision=original_revision
    assert k.recovery_required
    assert execute(k,'route_track',route_args())['error_code']=='RECOVERY_REQUIRED'
    assert len(b.tracks)==0


@pytest.mark.parametrize('points,accepted',[([[19,20],[19,15],[39,15],[39,20]],True),([[19,20],[21,20]],False)])
def test_action_result_carries_before_and_after_revision(points,accepted):
    k,b=setup_kernel();before=k.summary()['revision']
    result=execute(k,'route_track',route_args(points))
    assert result['ok'] is accepted
    assert result['before_revision']==before
    assert result['revision']==k.summary()['revision']
    assert (result['revision']!=before) is accepted


def test_named_checkpoint_rejects_stale_revision_before_saving():
    from pcb_harness.contracts import HarnessError
    k,b=setup_kernel();before=k.summary()['revision']
    with pytest.raises(HarnessError) as error:k.create_checkpoint('stale',expected_revision='old')
    assert error.value.code=='STALE_REVISION'
    assert not k.checkpoints and k.summary()['revision']==before


def test_geometry_verification_query_has_revision_and_no_release_claim():
    k,b=setup_kernel();before=k.summary()['revision']
    result=k.verify()
    assert result['revision']==before and result['release_verified'] is False
    assert result['connectivity'] and not result['geometric']


def test_checkpoint_rejects_external_edit_between_revision_check_and_capture(tmp_path):
    from pcb_harness.contracts import HarnessError
    from pcb_harness.kernel import Kernel
    from pcb_harness.memory import MemoryBackend
    class EditedDuringCapture(MemoryBackend):
        def checkpoint(self,**kwargs):
            self.footprints['R1']['x_mm']=23
            return super().checkpoint()  # external writer moves before the actual capture
    b=EditedDuringCapture.fixture();k=Kernel(b,journal_path=tmp_path/'actions.jsonl')
    before=b.revision()
    with pytest.raises(HarnessError) as error:k.create_checkpoint('baseline',expected_revision=before)
    assert error.value.code=='RECOVERY_REQUIRED'
    assert not k.checkpoints and b.get_footprint('R1')['x_mm']==23
    assert k.recovery_required


def test_action_does_not_apply_against_a_foreign_checkpoint_baseline():
    from pcb_harness.kernel import Kernel
    from pcb_harness.memory import MemoryBackend
    class EditedDuringCapture(MemoryBackend):
        def checkpoint(self,**kwargs):
            self.footprints['R3']['x_mm']=63
            return super().checkpoint()
    b=EditedDuringCapture.fixture();k=Kernel(b)
    result=k.execute('move_footprint',{'ref':'R1','dx_mm':2,'dy_mm':0},
        expected_revision=b.revision(),action_id='move',mode='permissive')
    assert not result['ok'] and result['recovery_required']
    assert b.get_footprint('R1')['x_mm']==20 and b.get_footprint('R3')['x_mm']==63
