from pathlib import Path
import importlib.util
import pytest


def module():
    assert importlib.util.find_spec('pcb_harness.ipc'), 'real KiCad adapter not implemented'
    from pcb_harness import ipc
    return ipc


def test_adapter_rejects_project_outside_run_directory_before_connecting(tmp_path):
    from pcb_harness.contracts import HarnessError
    with pytest.raises(HarnessError,match='run directory'):
        module().ScratchIPCBackend(tmp_path/'user-board.kicad_pcb',workspace=tmp_path)


def test_adapter_rejects_missing_project_bundle_before_connecting(tmp_path):
    from pcb_harness.contracts import HarnessError
    path=tmp_path/'runs/live/board.kicad_pcb';path.parent.mkdir(parents=True);path.write_text('incomplete')
    with pytest.raises(HarnessError,match='project bundle'):
        module().ScratchIPCBackend(path,workspace=tmp_path)


def test_report_connectivity_is_separated_from_geometric_regressions():
    issues=[{'type':'clearance','severity':'error','description':'gap','items':[{'uuid':'a'},{'uuid':'b'}]},
        {'type':'unconnected_items','severity':'error','description':'open','items':[{'uuid':'c'}]},
        {'type':'track_dangling','severity':'warning','description':'partial','items':[{'uuid':'d'}]}]
    result=module().classify_issues(issues)
    assert [v['type'] for v in result['geometric']]==['clearance']
    assert len(result['connectivity'])==2


def test_unknown_rule_types_are_never_silently_treated_as_connectivity():
    issue={'type':'new_unknown_drc','severity':'error','description':'unrecognized','items':[]}
    assert module().classify_issues([issue])['geometric'][0]['type']=='new_unknown_drc'


def test_location_evidence_is_preserved_for_violation_deltas():
    a={'type':'clearance','severity':'error','description':'gap','items':[{'uuid':'a','pos':{'x':1,'y':2}}]}
    b={**a,'items':[{'uuid':'a','pos':{'x':3,'y':4}}]}
    result=module().classify_issues([a,b])['geometric']
    assert result[0]!=result[1]


def test_foreign_checkpoint_rejected_before_any_native_write(tmp_path):
    from pcb_harness.contracts import HarnessError
    adapter=module().ScratchIPCBackend.__new__(module().ScratchIPCBackend)
    adapter.path=tmp_path/'runs/second/board.kicad_pcb'
    token={'project_path':str(tmp_path/'runs/first/board.kicad_pcb')}
    with pytest.raises(HarnessError,match='originating project'):
        adapter.restore(token,expected_current='some-revision')


@pytest.mark.parametrize('version,want',[
    ('9.0.8',False),('10.0.0',False),('10.0.5',False),('10.0.6',True),('10.0.7',True),('11.0.0',False)])
def test_native_flip_capability_requires_verified_major_and_minimum_patch(version,want):
    from kipy.kicad import KiCadVersion
    available=getattr(module(),'supports_native_flip',None)
    assert callable(available),'per-method server capability gate missing'
    assert available(KiCadVersion.from_git_describe(version)) is want


def test_place_side_change_uses_advertised_native_flip_capability():
    from pcb_harness.contracts import validate_action
    from pcb_harness.memory import MemoryBackend
    class NativeFlipContract(MemoryBackend):
        def capabilities(self):return super().capabilities()|{'flip_footprint'}
    b=NativeFlipContract.fixture()
    validated=validate_action(b,'place_footprint',{'ref':'R1','x_mm':20,'y_mm':20,'side':'back'})
    assert validated['side']=='back'


def test_explicit_flip_intent_checks_lock_before_native_mutation():
    from pcb_harness.contracts import validate_action,HarnessError
    from pcb_harness.memory import MemoryBackend
    class NativeFlipContract(MemoryBackend):
        def capabilities(self):return super().capabilities()|{'flip_footprint'}
    b=NativeFlipContract.fixture()
    assert validate_action(b,'flip_footprint',{'ref':'R1'})=={'ref':'R1'}
    b.footprints['R1']['locked']=True
    with pytest.raises(HarnessError) as error:validate_action(b,'flip_footprint',{'ref':'R1'})
    assert error.value.code=='LOCKED_OBJECT'
