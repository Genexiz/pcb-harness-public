"""Durable admission, deadline and evidence failures; no board backend doubles."""
import json
import pytest
from pcb_harness.contracts import HarnessError

IDENTITY={'backend':'memory','project':None,'workspace':'test'}


def make(tmp_path,**kwargs):
    from pcb_harness.run_envelope import RunEnvelope
    return RunEnvelope(tmp_path/'run.jsonl',IDENTITY,**kwargs)


def complete(run,operation='execute',result=None):
    attempt=run.admit(operation)
    run.finish(attempt,result or {'ok':True})
    return attempt


def code(call,expected):
    with pytest.raises(HarnessError) as error:call()
    assert error.value.code==expected


def test_rejected_attempt_uses_budget_and_cannot_refund(tmp_path):
    run=make(tmp_path,max_actions=2)
    assert run.status()['started_at'] is None
    complete(run,result={'ok':False,'error_code':'STALE_REVISION'})
    complete(run)
    code(lambda:run.admit('execute'),'RUN_ACTION_LIMIT')
    assert run.status()['attempts_used']==2 and run.status()['attempts_remaining']==0
    outcomes=[json.loads(x) for x in (tmp_path/'run.jsonl').read_text().splitlines() if json.loads(x)['phase']=='finished']
    assert outcomes[0]['error_code']=='STALE_REVISION' and outcomes[1]['ok']


def test_reopen_keeps_used_attempts(tmp_path):
    complete(make(tmp_path,max_actions=2))
    resumed=make(tmp_path,max_actions=2)
    assert resumed.status()['attempts_used']==1
    complete(resumed)
    code(lambda:make(tmp_path,max_actions=2).admit('execute'),'RUN_ACTION_LIMIT')


@pytest.mark.parametrize('changes',[{'max_actions':3},{'max_duration_seconds':50}])
def test_limits_are_frozen_before_first_action(tmp_path,changes):
    make(tmp_path,max_actions=2,max_duration_seconds=60)
    code(lambda:make(tmp_path,**({'max_actions':2,'max_duration_seconds':60}|changes)),'RUN_CONFIG_CONFLICT')


def test_foreign_identity_cannot_reuse_run(tmp_path):
    from pcb_harness.run_envelope import RunEnvelope
    make(tmp_path)
    code(lambda:RunEnvelope(tmp_path/'run.jsonl',{'backend':'kicad'}),'RUN_CONFIG_CONFLICT')


@pytest.mark.parametrize('kwargs',[{'max_actions':0},{'max_actions':True},{'max_actions':1.5},
    {'max_duration_seconds':0},{'max_duration_seconds':True},{'max_duration_seconds':float('nan')},
    {'max_duration_seconds':float('inf')}])
def test_invalid_limits_do_not_create_evidence(tmp_path,kwargs):
    code(lambda:make(tmp_path,**kwargs),'INVALID_ARGUMENT')
    assert not (tmp_path/'run.jsonl').exists()


@pytest.fixture
def clock(monkeypatch):
    import pcb_harness.run_envelope as module
    values={'wall':1000.,'mono':10.}
    monkeypatch.setattr(module,'wall_time',lambda:values['wall'])
    monkeypatch.setattr(module,'monotonic',lambda:values['mono'])
    return values


def test_clock_starts_on_first_write_and_exact_deadline_blocks(tmp_path,clock):
    run=make(tmp_path,max_duration_seconds=60)
    clock.update(wall=9000.,mono=80.)
    assert run.status()['elapsed_seconds']==0
    complete(run)
    clock.update(wall=9060.,mono=140.)
    code(lambda:run.admit('execute'),'RUN_TIME_LIMIT')
    assert run.status()['elapsed_seconds']==60


def test_reopen_counts_disconnect_downtime(tmp_path,clock):
    complete(make(tmp_path,max_duration_seconds=60))
    clock.update(wall=1061.,mono=1.)
    resumed=make(tmp_path,max_duration_seconds=60)
    code(lambda:resumed.admit('execute'),'RUN_TIME_LIMIT')


def test_monotonic_elapsed_prevents_wall_clock_extension(tmp_path,clock):
    run=make(tmp_path,max_duration_seconds=60);complete(run)
    clock.update(wall=1001.,mono=71.)
    code(lambda:run.admit('execute'),'RUN_TIME_LIMIT')


def test_backward_clock_fails_closed_across_restart(tmp_path,clock):
    complete(make(tmp_path))
    clock.update(wall=999.,mono=20.)
    resumed=make(tmp_path)
    code(lambda:resumed.admit('execute'),'RUN_CLOCK_ROLLBACK')


def test_action_crossing_deadline_still_finishes_and_next_is_blocked(tmp_path,clock):
    run=make(tmp_path,max_duration_seconds=60)
    attempt=run.admit('execute')
    clock.update(wall=1061.,mono=71.)
    run.finish(attempt,{'ok':False,'error_code':'GEOMETRY_REGRESSION','rolled_back':True})
    code(lambda:run.admit('execute'),'RUN_TIME_LIMIT')
    resumed=make(tmp_path,max_duration_seconds=60)
    assert resumed.status()['evidence_error'] is None and resumed.status()['attempts_used']==1


def test_unfinished_attempt_blocks_reopen_without_refund(tmp_path):
    run=make(tmp_path);run.admit('execute')
    resumed=make(tmp_path)
    assert resumed.status()['attempts_used']==1
    code(lambda:resumed.admit('execute'),'RUN_EVIDENCE_REQUIRED')


@pytest.mark.parametrize('tail',['{broken',json.dumps({'phase':'finished','attempt':7,'ok':True}),
    json.dumps({'phase':'mystery'})])
def test_corrupt_ledger_does_not_restart_budget(tmp_path,tail):
    complete(make(tmp_path))
    with (tmp_path/'run.jsonl').open('a') as stream:stream.write(tail+'\n')
    resumed=make(tmp_path)
    code(lambda:resumed.admit('execute'),'RUN_EVIDENCE_REQUIRED')


def test_failed_admission_evidence_never_returns_permission(tmp_path,monkeypatch):
    import pcb_harness.run_envelope as module
    run=make(tmp_path)
    monkeypatch.setattr(module.os,'fsync',lambda fd:(_ for _ in ()).throw(OSError('disk failure')))
    code(lambda:run.admit('execute'),'RUN_EVIDENCE_REQUIRED')
    code(lambda:run.admit('execute'),'RUN_EVIDENCE_REQUIRED')


def test_failed_terminal_evidence_latches(tmp_path,monkeypatch):
    import pcb_harness.run_envelope as module
    run=make(tmp_path);attempt=run.admit('execute')
    monkeypatch.setattr(module.os,'fsync',lambda fd:(_ for _ in ()).throw(OSError('disk failure')))
    code(lambda:run.finish(attempt,{'ok':True}),'RUN_EVIDENCE_REQUIRED')
    code(lambda:run.admit('execute'),'RUN_EVIDENCE_REQUIRED')


def test_reopen_keeps_monotonic_elapsed_when_wall_clock_lags(tmp_path,clock):
    run=make(tmp_path,max_duration_seconds=60)
    attempt=run.admit('execute')
    clock.update(wall=1001.,mono=71.)
    run.finish(attempt,{'ok':True})
    clock.update(mono=2.)
    resumed=make(tmp_path,max_duration_seconds=60)
    code(lambda:resumed.admit('execute'),'RUN_TIME_LIMIT')


def test_runtime_truncation_blocks_admission(tmp_path):
    run=make(tmp_path);complete(run)
    (tmp_path/'run.jsonl').write_text('')
    code(lambda:run.admit('execute'),'RUN_EVIDENCE_REQUIRED')


def test_idle_elapsed_survives_process_reopen_without_another_write(tmp_path,clock):
    run=make(tmp_path,max_duration_seconds=60);complete(run)
    clock.update(wall=1001.,mono=71.)
    assert run.status()['deadline_reached']
    resumed=make(tmp_path,max_duration_seconds=60)
    code(lambda:resumed.admit('execute'),'RUN_TIME_LIMIT')


def test_terminal_fsync_failure_blocks_reopen_even_if_json_row_is_complete(tmp_path,monkeypatch):
    import pcb_harness.run_envelope as module
    run=make(tmp_path);attempt=run.admit('execute')
    real=module.os.fsync
    def fail_outcome(fd):
        if module.os.fstat(fd).st_ino==run.path.stat().st_ino and '"phase": "finished"' in run.path.read_text():
            raise OSError('outcome fsync failed after write')
        return real(fd)
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'fsync',fail_outcome)
        code(lambda:run.finish(attempt,{'ok':True}),'RUN_EVIDENCE_REQUIRED')
    resumed=make(tmp_path)
    code(lambda:resumed.admit('execute'),'RUN_EVIDENCE_REQUIRED')


def test_unknown_or_changed_boot_epoch_blocks_restart_writes(tmp_path,monkeypatch,clock):
    import pcb_harness.run_envelope as module
    monkeypatch.setattr(module,'boot_identity',lambda:'boot-one')
    complete(make(tmp_path))
    monkeypatch.setattr(module,'boot_identity',lambda:'boot-two')
    resumed=make(tmp_path)
    code(lambda:resumed.admit('execute'),'RUN_CLOCK_ROLLBACK')
    assert resumed.status()['attempts_used']==1


def test_clock_failure_during_action_is_retained_after_restart(tmp_path,clock):
    run=make(tmp_path);attempt=run.admit('execute')
    clock.update(wall=999.,mono=11.)
    run.finish(attempt,{'ok':True})
    clock.update(wall=1001.,mono=12.)
    resumed=make(tmp_path)
    code(lambda:resumed.admit('execute'),'RUN_CLOCK_ROLLBACK')


def test_failed_marker_removal_durability_recreates_stop_marker(tmp_path,monkeypatch):
    import stat
    import pcb_harness.run_envelope as module
    run=make(tmp_path);attempt=run.admit('execute')
    real=module.os.fsync
    def fail_directory(fd):
        if stat.S_ISDIR(module.os.fstat(fd).st_mode):raise OSError('directory fsync failure')
        return real(fd)
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'fsync',fail_directory)
        code(lambda:run.finish(attempt,{'ok':True}),'RUN_EVIDENCE_REQUIRED')
    code(lambda:make(tmp_path).admit('execute'),'RUN_EVIDENCE_REQUIRED')
