"""Small tested guards for experimental probes, not atomic multi-writer recovery."""
import time
from pathlib import Path
from kipy.errors import ApiError, ConnectionError
from kipy.proto.common import ApiStatusCode


def absolute_output_directory(path):
    return Path(path).resolve()


def require_unchanged(expected_board, observed_board, expected_files, observed_files):
    if observed_board != expected_board or observed_files != expected_files:
        raise ValueError('external board/project change detected; automatic restore refused')


def wait_until_ready(ping, *, timeout=10.0, interval=0.05):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            ping()
            return
        except ApiError as error:
            if error.code != ApiStatusCode.AS_BUSY:raise
        except (ConnectionError, IOError):
            pass
        time.sleep(min(interval,max(0,deadline-time.monotonic())))
    raise TimeoutError('zone completion could not be reconciled before deadline')


def run_probed_operation(report,name,action,reconcile,persist):
    started=time.monotonic()
    entry={'name':name,'status':'uncertain','recovery_required':True}
    report['operations'].append(entry)
    persist()
    try:
        entry['evidence']=action()
        reconcile()
        entry.update(status='supported',recovery_required=False)
    except Exception as error:
        entry.update(error_type=type(error).__name__,error=str(error))
        try:
            reconcile()
            entry.update(status='failed',recovery_required=False)
        except Exception as reconciliation:
            entry['reconciliation_error']=str(reconciliation)
    entry['seconds']=round(time.monotonic()-started,3)
    persist()
    return entry
