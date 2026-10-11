"""Capture contract: bound PID/window, permission, no broad capture fallback."""
import importlib
from pathlib import Path
import pytest
from pcb_harness.contracts import HarnessError


def module():
    assert importlib.util.find_spec('pcb_harness.capture'),'editor capture module missing'
    return importlib.import_module('pcb_harness.capture')


def window(id=42,pid=123,title='board — PCB Editor',owner='pcbnew'):
    return {'kCGWindowNumber':id,'kCGWindowOwnerPID':pid,'kCGWindowName':title,
        'kCGWindowOwnerName':owner,'kCGWindowLayer':0,'kCGWindowBounds':{'X':1,'Y':2,'Width':800,'Height':600}}


def test_only_exact_instance_and_board_window_selected():
    m=module();expected=window()
    actual=m.select_editor_window([window(1,99),window(2,123,'Other Project — PCB Editor'),
        window(3,123,'board — Safari',owner='Safari'),expected],123,'board')
    assert actual==expected


@pytest.mark.parametrize('windows',[[],[window(1),window(2)],[window(pid=99)],[window(owner='Safari')]])
def test_missing_ambiguous_or_unrelated_window_refused(windows):
    with pytest.raises(HarnessError):module().select_editor_window(windows,123,'board')


def test_explicit_instance_socket_required_for_capture():
    m=module()
    assert m.instance_pid('ipc:///tmp/kicad/api-123.sock')==123
    with pytest.raises(HarnessError):m.instance_pid('ipc:///tmp/kicad/api.sock')


def test_permission_denial_does_not_invoke_screencapture(tmp_path,monkeypatch):
    m=module()
    class DeniedQuartz:
        @staticmethod
        def CGPreflightScreenCaptureAccess():return False
    monkeypatch.setattr(m,'load_quartz',lambda:DeniedQuartz)
    def forbidden(*a,**k):raise AssertionError('capture must not run without permission')
    monkeypatch.setattr(m.subprocess,'run',forbidden)
    with pytest.raises(HarnessError) as error:m.capture_editor(Path('board.kicad_pcb'),
        'ipc:///tmp/kicad/api-123.sock','revision',tmp_path)
    assert error.value.code=='SCREEN_CAPTURE_PERMISSION_REQUIRED'
    assert not (tmp_path/'editor.png').exists()
