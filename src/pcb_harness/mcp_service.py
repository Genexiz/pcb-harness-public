"""Serialized, fixed-path MCP service. The host owns inference and sign-in."""
from pathlib import Path
import fcntl
import inspect
import threading
import uuid
from .contracts import HarnessError
from .kernel import Kernel
from .memory import MemoryBackend
from .run_envelope import RunEnvelope

WRITE_OPERATIONS={'execute','create_checkpoint','restore_checkpoint'}


class MCPService:
    def __init__(self, *, workspace, run_directory, backend='kicad', project=None,
                 socket='ipc:///tmp/kicad/api.sock',max_actions=300,max_duration_seconds=1200):
        self.workspace=Path(workspace).resolve()
        self.run_directory=Path(run_directory).resolve()
        self.backend=backend
        self.project=Path(project or self.workspace/'runs/capability/live/board.kicad_pcb').resolve()
        self.socket=socket
        if backend not in ('kicad','memory'):
            raise HarnessError('INVALID_ARGUMENT','backend must be kicad or explicit test-only memory')
        if not self.workspace.is_dir():
            raise HarnessError('INVALID_ARGUMENT','workspace must exist')
        if self.run_directory==self.workspace/'runs' or not self.run_directory.is_relative_to(self.workspace/'runs'):
            raise HarnessError('UNSAFE_ARTIFACTS','MCP run directory must be a child of workspace/runs')
        if backend=='kicad':
            if not self.project.is_relative_to(self.workspace/'runs') or self.project.suffix!='.kicad_pcb':
                raise HarnessError('UNSAFE_PROJECT','native project must be a scratch board under workspace/runs')
            if self.run_directory.is_relative_to(self.project.parent):
                raise HarnessError('UNSAFE_ARTIFACTS','run directory must be separate from scratch source')
        self._lock=threading.RLock()
        self._kernel=None
        self._native=None
        self._memory=None
        self._closed=False
        self._recovery_required=False
        self.run_directory.mkdir(parents=True,exist_ok=True)
        self._lease=(self.run_directory/'.mcp-writer.lock').open('a')
        try:fcntl.flock(self._lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self._lease.close()
            raise HarnessError('WRITER_BUSY','another MCP server owns this run journal')

        try:
            if (self.run_directory/'actions.jsonl').exists() and not (self.run_directory/'run.jsonl').exists():
                raise HarnessError('RUN_MIGRATION_REQUIRED','historical run has no budget evidence; use a fresh run directory, preserving the old evidence')
            self._envelope=RunEnvelope(self.run_directory/'run.jsonl',
                {'workspace':str(self.workspace),'backend':self.backend,
                 'project':str(self.project) if self.backend=='kicad' else None},
                max_actions=max_actions,max_duration_seconds=max_duration_seconds)
        except Exception:
            self._lease.close()
            raise

    def _native_editing_enabled(self):
        if self.backend!='kicad' or self._native is None or self._kernel is None or self._kernel.backend is not self._native:
            return False
        version=getattr(self._native,'server_version',None)
        return (getattr(self._native,'kind',None)=='kicad-ipc-scratch' and
            tuple(getattr(version,key,None) for key in ('major','minor','patch'))==(10,0,6) and
            getattr(version,'full_version',None)=='10.0.6')

    def _tag(self,data):
        budget=self._envelope.status()
        self._recovery_required=(self._recovery_required or bool(budget['evidence_error']) or data.get('recovery_required',False)
            or bool(self._kernel and self._kernel.recovery_required))
        return {**data,'ok':data.get('ok',True),'backend':self.backend,
            'test_only':self.backend=='memory','native_editing_enabled':self._native_editing_enabled(),
            'capabilities':sorted(self._kernel.backend.capabilities()) if self._kernel else [],
            'recovery_required':self._recovery_required,'run_budget':budget}

    def _error(self,code,message):
        return self._tag({'ok':False,'error_code':code,'message':str(message)})

    def status(self):
        with self._lock:
            return self._tag({'connected':self._kernel is not None,'closed':self._closed,
                'project':str(self.project) if self.backend=='kicad' else None,
                'run_directory':str(self.run_directory),
                'native_acceptance':'initial M1 verified on KiCad 10.0.6; writes require that connected scratch backend',
                'inference':'host-driven; no model API key used by server'})

    def connect(self):
        with self._lock:
            if self._closed:return self._error('SERVICE_CLOSED','server has closed')
            if self._kernel is None:
                candidate=None
                try:
                    if self.backend=='memory':
                        if self._memory is None:self._memory=MemoryBackend.fixture()
                        candidate=self._memory
                    else:
                        from .ipc import ScratchIPCBackend
                        candidate=ScratchIPCBackend(self.project,workspace=self.workspace,
                            socket=self.socket,artifacts=self.run_directory/'native')
                        self._native=candidate
                    self._kernel=Kernel(candidate,journal_path=self.run_directory/'actions.jsonl')
                except Exception as error:
                    if self._native is not None:self._native.close();self._native=None
                    return self._error(getattr(error,'code','BACKEND_UNAVAILABLE'),error)
            if self._kernel.recovery_required or self._recovery_required:
                return {**self.status(),'ok':False,'error_code':'RECOVERY_REQUIRED',
                    'message':'fixed run journal requires reconciliation; reconnect does not reset it'}
            return self.status()

    def _write(self,operation,handler,action_id=None):
        try:attempt=self._envelope.admit(operation,action_id)
        except HarnessError as error:return self._error(error.code,error)
        try:result=handler()
        except Exception as error:result=self._error(getattr(error,'code','TOOL_ERROR'),error)
        try:self._envelope.finish(attempt,result)
        except HarnessError as error:
            self._recovery_required=True
            return self._tag({**result,'ok':False,'error_code':error.code,'message':str(error),
                'outcome_before_evidence_failure':{'ok':result.get('ok'),
                    'error_code':result.get('error_code'),'revision':result.get('revision')}})
        return self._tag(result)

    def reject_write(self,operation,message):
        """SDK schema failures share the same admission/evidence path as typed writes."""
        with self._lock:
            if self._closed:return self._error('SERVICE_CLOSED','server has closed')
            return self._write(operation,lambda:self._error('INVALID_ARGUMENT',message))

    def call(self,operation,**arguments):
        with self._lock:
            if self._closed:return self._error('SERVICE_CLOSED','server has closed')
            if operation in WRITE_OPERATIONS:
                return self._write(operation,lambda:self._call(operation,**arguments),arguments.get('action_id'))
            return self._call(operation,**arguments)

    def _call(self,operation,**arguments):
        with self._lock:
            if self._kernel is None:return self._error('SESSION_NOT_CONNECTED','call pcb_connect first')
            operations={
                'summary':self._kernel.summary,'get_footprint':self._kernel.get_footprint,
                'net_info':self._kernel.net_info,'list_unrouted':self._kernel.list_unrouted,
                'verify':self._kernel.verify,'execute':self._kernel.execute,
                'create_checkpoint':self._kernel.create_checkpoint,
                'restore_checkpoint':self._kernel.restore_checkpoint}
            if operation not in operations:return self._error('UNKNOWN_OPERATION',operation)
            if self.backend=='kicad' and operation in ('execute','create_checkpoint','restore_checkpoint') and not self._native_editing_enabled():
                return self._error('NATIVE_ACCEPTANCE_REQUIRED',
                    'native writes require the exact connected scratch backend on verified KiCad 10.0.6')
            if self._recovery_required and operation in ('execute','create_checkpoint','restore_checkpoint'):
                return self._error('RECOVERY_REQUIRED','uncertain run must be reconciled before writes')
            handler=operations[operation]
            try:inspect.signature(handler).bind(**arguments)
            except TypeError as error:return self._error('INVALID_ARGUMENT',error)
            try:return self._tag(handler(**arguments))
            except Exception as error:return self._error(getattr(error,'code','TOOL_ERROR'),error)

    def render(self,layers,*,region_mm=None,width_px=1024):
        with self._lock:
            if self._kernel is None:return self._error('SESSION_NOT_CONNECTED','call pcb_connect first')
            try:
                from .rendering import validate_view,memory_svg,render_svg,export_saved_board
                backend=self._kernel.backend;before=backend.revision();bounds=backend.bounds()
                bounds,selected,region=validate_view(bounds,layers,region_mm,width_px)
                copper={x for x in selected if x.endswith('.Cu')}
                if not copper.issubset(backend.enabled_layers()):raise HarnessError('UNKNOWN_LAYER','requested copper layer is not enabled')
                target=self.run_directory/'visual'/str(uuid.uuid4())
                if self.backend=='memory':
                    if any(x not in {'F.Cu','B.Cu','Edge.Cuts'} for x in selected):raise HarnessError('UNKNOWN_LAYER','Memory demo supports copper/outline views only')
                    result=render_svg(memory_svg(backend,selected),bounds,[0,0],before,selected,target,
                        region_mm=region,width_px=width_px,source='Memory demo',test_only=True)
                else:
                    target.mkdir(parents=True,exist_ok=False)
                    board,bounds,captured=backend.visual_snapshot(target/'snapshot')
                    if captured!=before:raise HarnessError('CONCURRENT_EDIT','visual capture revision changed')
                    result=export_saved_board(board,bounds,before,selected,target/'image',region_mm=region,width_px=width_px,cli=backend.cli,source='KiCad live snapshot')
                    backend.ensure_document()
                if backend.revision()!=before:raise HarnessError('CONCURRENT_EDIT','board changed while producing image; query again')
                return self._tag(result)
            except Exception as error:return self._error(getattr(error,'code','RENDER_FAILED'),error)

    def capture_editor(self):
        with self._lock:
            if self._kernel is None:return self._error('SESSION_NOT_CONNECTED','call pcb_connect first')
            if self.backend=='memory':return self._error('CAPTURE_UNAVAILABLE','Memory demo has no PCB Editor window; no fake screenshot generated')
            try:
                from .capture import capture_editor
                self._kernel.backend.ensure_document()
                before=self._kernel.backend.revision()
                result=capture_editor(self.project,self.socket,before,self.run_directory/'visual'/str(uuid.uuid4()))
                self._kernel.backend.ensure_document()
                if self._kernel.backend.revision()!=before:raise HarnessError('CONCURRENT_EDIT','board changed while capturing editor')
                return self._tag(result)
            except Exception as error:return self._error(getattr(error,'code','CAPTURE_FAILED'),error)

    def disconnect(self):
        with self._lock:
            if self._native is not None:self._native.close();self._native=None
            self._kernel=None
            return self.status()

    def close(self):
        with self._lock:
            self.disconnect()
            if not self._closed:
                self._lease.close()
                self._closed=True
