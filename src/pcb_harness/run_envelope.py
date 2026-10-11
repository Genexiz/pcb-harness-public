"""Durable, fixed run limits. Admission never interrupts an atomic Kernel action."""
from pathlib import Path
import json
import math
import os
import subprocess
import sys
import uuid
from time import time as wall_time, monotonic
from .contracts import HarnessError


def boot_identity():
    """Same-boot monotonic timestamps are comparable across processes; otherwise stop."""
    try:
        if sys.platform=='darwin':
            result=subprocess.run(['/usr/sbin/sysctl','-n','kern.bootsessionuuid'],
                capture_output=True,text=True,timeout=3,check=True)
            return str(uuid.UUID(result.stdout.strip()))
        if sys.platform.startswith('linux'):
            return str(uuid.UUID(Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return None


class RunEnvelope:
    def __init__(self,path,identity,*,max_actions=300,max_duration_seconds=1200):
        if type(max_actions) is not int or max_actions<=0:
            raise HarnessError('INVALID_ARGUMENT','max_actions must be a positive integer')
        if type(max_duration_seconds) not in (int,float) or not math.isfinite(max_duration_seconds) or max_duration_seconds<=0:
            raise HarnessError('INVALID_ARGUMENT','max_duration_seconds must be positive and finite')
        self.path=Path(path)
        self.pending_path=self.path.with_name(self.path.name+'.pending')
        self._boot=boot_identity()
        self.config={'schema_version':1,'identity':identity,'max_actions':max_actions,
            'max_duration_seconds':max_duration_seconds}
        self.used=0;self.started_at=None;self.last_wall=None;self.pending=None
        self.evidence_error=None;self.clock_error=None
        self._mono_start=None;self._mono_base=0.;self._elapsed_floor=0.
        self._file_identity=None;self._size=0
        if self.path.is_symlink():raise HarnessError('UNSAFE_ARTIFACTS','run evidence cannot be a symlink')
        if self.path.exists():self._load()
        else:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            if self.pending_path.exists() or self.pending_path.is_symlink():
                raise HarnessError('RUN_EVIDENCE_REQUIRED','unresolved run marker exists without its ledger')
            self._append({'phase':'config',**self.config},initial=True)

    def _load(self):
        try:
            raw=self.path.read_text()
            if not raw.endswith('\n'):raise ValueError('incomplete run evidence')
            rows=raw.splitlines()
            header=json.loads(rows[0])
            if header.get('phase')!='config':raise ValueError('missing config header')
            if header!={'phase':'config',**self.config}:
                raise HarnessError('RUN_CONFIG_CONFLICT','run limits/identity are frozen; use the original configuration or a fresh run directory')
            for line in rows[1:]:
                row=json.loads(line);stamp=row['wall_time']
                if type(stamp) not in (int,float) or not math.isfinite(stamp):raise ValueError('invalid event time')
                if self.last_wall is not None and stamp<self.last_wall:raise ValueError('event clock moved backward')
                if row['phase']=='started':
                    if self.pending is not None or type(row['attempt']) is not int or row['attempt']!=self.used+1:
                        raise ValueError('unmatched or nonsequential admission')
                    if self.used>=self.config['max_actions']:raise ValueError('admission exceeds frozen limit')
                    if row['operation'] not in ('execute','create_checkpoint','restore_checkpoint'):raise ValueError('invalid write operation')
                    if self.started_at is None:
                        self.started_at=stamp
                        self._mono_start=row['monotonic_time']
                        if self._boot is None or row['boot_id']!=self._boot:
                            self.clock_error='boot epoch changed or unavailable; elapsed time cannot be proven across restart'
                        if type(self._mono_start) not in (int,float) or not math.isfinite(self._mono_start):
                            raise ValueError('invalid monotonic timestamp')
                    self.used+=1;self.pending=row['attempt']
                elif row['phase']=='finished':
                    if self.pending is None or type(row['attempt']) is not int or row['attempt']!=self.pending or type(row['ok']) is not bool:
                        raise ValueError('unmatched outcome')
                    self.pending=None
                else:raise ValueError('unknown run evidence phase')
                elapsed=row['elapsed_seconds']
                if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<self._elapsed_floor:
                    raise ValueError('invalid elapsed time evidence')
                self._elapsed_floor=elapsed
                self.last_wall=stamp
                if row.get('clock_error'):self.clock_error=str(row['clock_error'])
            if self.pending_path.exists() or self.pending_path.is_symlink():
                raise ValueError('unresolved durability marker; do not trust a complete but unconfirmed outcome')
            if self.pending is not None:raise ValueError('unfinished write; reconcile evidence before another write')
        except HarnessError:raise
        except (OSError,ValueError,IndexError,KeyError,TypeError,AttributeError) as error:
            self.evidence_error=str(error)
        if self.path.exists():
            stat=self.path.stat();self._file_identity=(stat.st_dev,stat.st_ino);self._size=stat.st_size

    def _sync_directory(self):
        directory=os.open(self.path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)

    def _mark_pending(self,attempt):
        try:
            with self.pending_path.open('x') as stream:
                stream.write(json.dumps({'attempt':attempt})+'\n')
                stream.flush();os.fsync(stream.fileno())
            self._sync_directory()
        except OSError as error:
            self.evidence_error=str(error)
            raise HarnessError('RUN_EVIDENCE_REQUIRED',f'unresolved run marker: {error}') from error

    def _clear_pending(self):
        try:
            self.pending_path.unlink()
            self._sync_directory()
        except OSError as error:
            # Preserve the stop marker if directory durability could not be confirmed.
            try:self._mark_pending(self.pending)
            except HarnessError:pass
            self.evidence_error=str(error)
            raise HarnessError('RUN_EVIDENCE_REQUIRED',f'cannot confirm outcome durability: {error}') from error

    def _append(self,row,*,initial=False):
        try:
            if not initial:
                stat=self.path.stat()
                if self.path.is_symlink() or (stat.st_dev,stat.st_ino)!=self._file_identity or stat.st_size!=self._size:
                    raise OSError('run evidence changed outside this writer')
            with self.path.open('x' if initial else 'a') as stream:
                stream.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
                stream.flush();os.fsync(stream.fileno())
            if initial:
                self._sync_directory()
            stat=self.path.stat();self._file_identity=(stat.st_dev,stat.st_ino);self._size=stat.st_size
        except (OSError,ValueError,TypeError) as error:
            self.evidence_error=str(error)
            raise HarnessError('RUN_EVIDENCE_REQUIRED',f'run evidence incomplete: {error}') from error

    def _elapsed(self,now):
        if not math.isfinite(now) or (self.last_wall is not None and now<self.last_wall):
            self.clock_error='wall clock moved backward or became invalid; run cannot admit writes'
        if self.started_at is None:return 0.
        elapsed=max(0.,now-self.started_at)
        if self._mono_start is not None:
            current_mono=monotonic()
            if current_mono<self._mono_start:self.clock_error='monotonic epoch changed; elapsed time cannot be proven'
            elapsed=max(elapsed,self._mono_base+current_mono-self._mono_start)
        self._elapsed_floor=max(self._elapsed_floor,elapsed)
        return self._elapsed_floor

    def status(self):
        return self._status(wall_time())

    def _status(self,now):
        elapsed=self._elapsed(now)
        return {'max_actions':self.config['max_actions'],
            'max_duration_seconds':self.config['max_duration_seconds'],
            'attempts_used':self.used,'attempts_remaining':max(0,self.config['max_actions']-self.used),
            'started_at':self.started_at,'elapsed_seconds':elapsed,
            'deadline_reached':elapsed>=self.config['max_duration_seconds'],
            'evidence_error':self.evidence_error or self.clock_error}

    def admit(self,operation,action_id=None):
        now=wall_time();state=self._status(now)
        if self.evidence_error:raise HarnessError('RUN_EVIDENCE_REQUIRED',self.evidence_error)
        if state['deadline_reached']:raise HarnessError('RUN_TIME_LIMIT','frozen run deadline reached; inspection remains available')
        if self.clock_error:raise HarnessError('RUN_CLOCK_ROLLBACK',self.clock_error)
        if self.pending is not None:raise HarnessError('RUN_EVIDENCE_REQUIRED','prior write has no outcome')
        if operation not in ('execute','create_checkpoint','restore_checkpoint'):
            raise HarnessError('INVALID_ARGUMENT','only board writes consume admission')
        if self.used>=self.config['max_actions']:raise HarnessError('RUN_ACTION_LIMIT','frozen action allowance exhausted; inspection remains available')
        attempt=self.used+1
        mono=monotonic()
        self._mark_pending(attempt)
        self._append({'phase':'started','attempt':attempt,'operation':operation,
            'action_id':action_id if isinstance(action_id,str) else None,'wall_time':now,
            'elapsed_seconds':state['elapsed_seconds'],'monotonic_time':mono,'boot_id':self._boot})
        if self.started_at is None:self.started_at=now;self._mono_start=mono
        self.last_wall=now;self.used=attempt;self.pending=attempt
        return attempt

    def finish(self,attempt,result):
        if self.evidence_error:raise HarnessError('RUN_EVIDENCE_REQUIRED',self.evidence_error)
        if self.pending!=attempt:raise HarnessError('RUN_EVIDENCE_REQUIRED','outcome does not match admitted write')
        # Atomic action/rollback has finished even if the deadline passed meanwhile.
        now=wall_time()
        self._append({'phase':'finished','attempt':attempt,'wall_time':max(now,self.last_wall),
            'elapsed_seconds':self._elapsed(now),'clock_error':self.clock_error,
            'ok':bool(result.get('ok',True)),'error_code':result.get('error_code'),
            'replayed':bool(result.get('replayed',False)),
            'rolled_back':bool(result.get('rolled_back',False)),
            'recovery_required':bool(result.get('recovery_required',False)),
            'revision':result.get('revision')})
        if now<self.last_wall:self.clock_error='wall clock moved backward during write'
        self._clear_pending()
        self.last_wall=max(now,self.last_wall);self.pending=None
