from pathlib import Path
import importlib.util
import json
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]


def load(name):
    path=ROOT/f'experiments/kicad-ipc/{name}.py'
    assert path.exists(), f'{name} safety helper missing'
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_missing_cli_replaces_previous_pass_summary(tmp_path, monkeypatch):
    (tmp_path/'summary.json').write_text(json.dumps({'drc':{'passed':True},'render':{'passed':True}}))
    monkeypatch.setattr(sys,'argv',['verify_fixture','--cli',str(tmp_path/'missing-cli'),'--output',str(tmp_path)])
    assert load('verify_fixture').main()==1
    result=json.loads((tmp_path/'summary.json').read_text())
    assert result['render']['passed'] is False
    assert result['drc']['passed'] is False
    assert result['run_id']


@pytest.mark.parametrize('kind',['outline','settings'])
def test_restore_guard_rejects_external_change(kind):
    module=load('safety')
    expected='full board including original outline'
    observed=expected+' modified outline' if kind=='outline' else expected
    expected_files={'board.kicad_pro':'hash1','board.kicad_dru':'hash2'}
    observed_files={**expected_files,'board.kicad_pro':'changed'} if kind=='settings' else expected_files
    with pytest.raises(ValueError):
        module.require_unchanged(expected,observed,expected_files,observed_files)


def test_restore_guard_accepts_complete_unchanged_state():
    load('safety').require_unchanged('full board','full board',{'rule':'hash'},{'rule':'hash'})


def test_busy_zone_poll_has_real_deadline():
    def busy():
        from kipy.errors import ApiError
        from kipy.proto.common import ApiStatusCode
        raise ApiError('busy',code=ApiStatusCode.AS_BUSY)
    with pytest.raises(TimeoutError):
        load('safety').wait_until_ready(busy,timeout=0.01,interval=0.001)


def test_successful_zone_poll_returns():
    load('safety').wait_until_ready(lambda:None,timeout=0.01,interval=0.001)


def test_fixture_builder_refuses_partial_existing_bundle(tmp_path):
    marker=tmp_path/'board.kicad_sch';marker.write_text('existing schematic')
    module=load('build_fixture');module.OUT=tmp_path
    with pytest.raises(FileExistsError):module.main()
    assert marker.read_text()=='existing schematic'


def test_malformed_rules_are_rejected_before_fixture_verification(tmp_path):
    rules=tmp_path/'board.kicad_dru';rules.write_text('invalid garbage')
    module=load('verify_fixture')
    validate=getattr(module,'validate_probe_rules',None)
    assert callable(validate), 'native CLI ignores malformed rules; preflight validation missing'
    with pytest.raises(ValueError):validate(rules)


def test_unitless_rules_are_rejected_before_fixture_verification(tmp_path):
    rules=tmp_path/'board.kicad_dru'
    rules.write_text('(version 1)\n(rule "M0 minimum routing width" '
        '(condition "A.Type == \'Track\'") (constraint track_width (min 0.2)))')
    module=load('verify_fixture')
    validate=getattr(module,'validate_probe_rules',None)
    assert callable(validate), 'unitless custom thresholds must be rejected'
    with pytest.raises(ValueError):validate(rules)


def test_operation_persists_uncertainty_before_mutation_and_after_failed_readback(tmp_path):
    module=load('safety')
    run=getattr(module,'run_probed_operation',None)
    assert callable(run), 'durable IPC uncertainty handler missing'
    report={'operations':[]};path=tmp_path/'report.json'
    def persist():path.write_text(json.dumps(report))
    def action():
        saved=json.loads(path.read_text())['operations'][-1]
        assert saved['status']=='uncertain' and saved['recovery_required'] is True
        raise ConnectionError('delivery uncertain')
    def reconcile():raise ConnectionError('readback unavailable')
    result=run(report,'mutation',action,reconcile,persist)
    saved=json.loads(path.read_text())['operations'][-1]
    assert result['status']=='uncertain'
    assert saved['recovery_required'] is True
    assert 'readback unavailable' in saved['reconciliation_error']


def test_ipc_output_path_is_absolute_even_for_relative_cli_argument(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    module=load('safety')
    resolve=getattr(module,'absolute_output_directory',None)
    assert callable(resolve), 'relative IPC save path can resolve in the board project instead of Python cwd'
    assert resolve(Path('runs/probe'))==tmp_path/'runs/probe'
