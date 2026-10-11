"""Single-writer action Kernel with durable attempt evidence and guarded rollback."""
from copy import deepcopy
from collections import Counter
from pathlib import Path
import json
import os
import threading
import uuid
from .contracts import HarnessError,validate_action


def intent_signature(name,args,mode):
    return json.dumps({'name':name,'args':args,'mode':mode},sort_keys=True,allow_nan=False)


def violation_map(violations):
    # Conservatively treat changed evidence as a regression, even for the same objects.
    return Counter(json.dumps(v,sort_keys=True) for v in violations)


class Kernel:
    def __init__(self,backend,*,journal_path=None):
        self.backend=backend
        self._writer=threading.RLock()
        default_journal=getattr(backend,'artifacts',None)
        self.journal_path=Path(journal_path) if journal_path else (default_journal/'actions.jsonl' if default_journal else None)
        self._identity=backend.identity()
        self.seen={}
        self.checkpoints={}
        self.recovery_required=False
        if self.journal_path and self.journal_path.exists():
            pending=set()
            bound=False;terminal_revision=None
            try:
                for line in self.journal_path.read_text().splitlines():
                    row=json.loads(line)
                    if row['phase']=='session':
                        if row.get('identity')!=self._identity:raise ValueError('journal belongs to another project')
                        bound=True;terminal_revision=row.get('revision')
                    elif row['phase']=='started':pending.add(row['action_id'])
                    elif row['phase']=='finished':
                        pending.discard(row['action_id'])
                        self.seen[row['action_id']]=(row['signature'],row['result'])
                        terminal_revision=row['result'].get('revision')
                    elif row['phase']=='checkpoint':
                        self.checkpoints[row['name']]=row['token'];terminal_revision=row.get('revision')
                    else:raise ValueError('unknown journal phase')
                self.recovery_required=(not bound or bool(pending) or terminal_revision!=backend.revision()
                    or any(r[1].get('recovery_required') for r in self.seen.values()))
            except (OSError,ValueError,KeyError,TypeError,AttributeError):self.recovery_required=True
        elif self.journal_path:
            self._append({'phase':'session','identity':self._identity,'revision':backend.revision(),'schema_version':1})

    def _append(self,row):
        if self.journal_path:
            self.journal_path.parent.mkdir(parents=True,exist_ok=True)
            with self.journal_path.open('a') as stream:
                stream.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
                stream.flush();os.fsync(stream.fileno())

    def summary(self):
        with self._writer:
            before=self.backend.revision();data=self.backend.summary();after=self.backend.revision()
            if before!=after:raise HarnessError('CONCURRENT_EDIT','board changed during query')
            return {**data,'revision':after,
                'backend':self.backend.kind,'recovery_required':self.recovery_required}

    def get_footprint(self,ref):
        with self._writer:
            before=self.backend.revision();data=deepcopy(self.backend.get_footprint(ref));after=self.backend.revision()
            if before!=after:raise HarnessError('CONCURRENT_EDIT','board changed during query')
            return {**data,'revision':after}

    def net_info(self,net):
        with self._writer:
            before=self.backend.revision()
            if net not in self.backend.net_names():raise HarnessError('UNKNOWN_NET',net)
            data=deepcopy(self.backend.net_info(net));after=self.backend.revision()
            if before!=after:raise HarnessError('CONCURRENT_EDIT','board changed during query')
            return {**data,'revision':after}

    def list_unrouted(self):
        with self._writer:
            before=self.backend.revision();data=deepcopy([v for v in self.backend.verify()['connectivity'] if v['type']=='unconnected_items']);after=self.backend.revision()
            if before!=after:raise HarnessError('CONCURRENT_EDIT','board changed during query')
            return {'items':data,'revision':after}

    def verify(self):
        with self._writer:
            before=self.backend.revision()
            data=deepcopy(self.backend.verify())
            after=self.backend.revision()
            if before!=after:raise HarnessError('CONCURRENT_EDIT','board changed during verification query')
            return {**data,'revision':after,'release_verified':False}

    def create_checkpoint(self,name,*,expected_revision=None):
        with self._writer:
            if self.recovery_required:raise HarnessError('RECOVERY_REQUIRED','reconcile unfinished action first')
            authorized_revision=self.backend.revision()
            if expected_revision is not None and authorized_revision!=expected_revision:
                raise HarnessError('STALE_REVISION','query the current board before checkpointing')
            if not isinstance(name,str) or not name or len(name)>128:raise HarnessError('INVALID_ARGUMENT','checkpoint name must be nonempty text')
            action_id=f'checkpoint-{uuid.uuid4()}'
            signature=intent_signature('create_checkpoint',{'name':name},'strict')
            try:
                self._append({'phase':'started','action_id':action_id,'signature':signature})
                token=self.backend.checkpoint(expected_current=authorized_revision)
                revision=self.backend.revision()
                if token.get('capture_before_revision')!=authorized_revision:
                    raise HarnessError('CONCURRENT_EDIT','checkpoint baseline differs from authorized revision')
                if token.get('revision',revision)!=revision:
                    raise HarnessError('CONCURRENT_EDIT','board changed after checkpoint')
                self._append({'phase':'checkpoint','name':name,'token':token,'revision':revision})
                self._append({'phase':'finished','action_id':action_id,'signature':signature,
                    'result':{'ok':True,'name':name,'revision':revision,'recovery_required':False}})
            except Exception as error:
                self.recovery_required=True
                raise HarnessError('RECOVERY_REQUIRED',f'checkpoint evidence incomplete: {error}') from error
            self.checkpoints[name]=token
            return {'name':name,'revision':revision}

    def restore_checkpoint(self,name,*,expected_revision):
        with self._writer:
            current=self.backend.revision()
            if self.recovery_required:return {'ok':False,'error_code':'RECOVERY_REQUIRED','revision':current,'recovery_required':True}
            if current!=expected_revision:return {'ok':False,'error_code':'STALE_REVISION','revision':current}
            if name not in self.checkpoints:return {'ok':False,'error_code':'UNKNOWN_CHECKPOINT','revision':current}
            id=f'restore-{uuid.uuid4()}';signature=intent_signature('restore_checkpoint',{'name':name},'strict')
            result={'ok':False,'action_id':id,'recovery_required':False,'revision':current,'before_revision':current}
            try:
                self._append({'phase':'started','action_id':id,'signature':signature,'intent':{'name':'restore_checkpoint','args':{'name':name}},'expected_revision':current})
                self.backend.restore(self.checkpoints[name],expected_current=current)
                result['ok']=True
                result['revision']=self.backend.revision()
                self._append({'phase':'finished','action_id':id,'signature':signature,'result':result})
            except Exception as error:
                self.recovery_required=True
                result.update(ok=False,error_code='RECOVERY_REQUIRED',recovery_required=True,message=str(error))
                try:result['revision']=self.backend.revision()
                except Exception:result['revision']=None
                try:self._append({'phase':'finished','action_id':id,'signature':signature,'result':result})
                except Exception as evidence_error:result['evidence_error']=str(evidence_error)
            self.seen[id]=(signature,result)
            return result

    def execute(self,name,args,*,expected_revision,action_id,mode='strict'):
        with self._writer:
            return self._execute(name,args,expected_revision=expected_revision,action_id=action_id,mode=mode)

    def _execute(self,name,args,*,expected_revision,action_id,mode):
        try:revision=self.backend.revision()
        except Exception as error:
            return {'ok':False,'action_id':action_id,'revision':None,'before_revision':None,'changed_ids':[],
                'error_code':'BACKEND_UNAVAILABLE','message':str(error),'recovery_required':self.recovery_required}
        result={'ok':False,'action_id':action_id,'revision':revision,'before_revision':revision,
            'changed_ids':[],'drc_delta':{'added':[],'resolved':[]},'warnings':[],
            'replayed':False,'recovery_required':False}
        def reject(code,message):
            return {**result,'error_code':code,'message':str(message),'recovery_required':self.recovery_required or code=='RECOVERY_REQUIRED'}
        if self.recovery_required:return reject('RECOVERY_REQUIRED','unfinished or uncertain prior action; reconcile before writes')
        if not isinstance(action_id,str) or not action_id or len(action_id)>128:
            return reject('INVALID_ARGUMENT','action_id must be nonempty text, at most 128 characters')
        if mode not in ('strict','permissive'):return reject('INVALID_ARGUMENT','mode must be strict or permissive')
        try:signature=intent_signature(name,args,mode)
        except (ValueError,TypeError):return reject('INVALID_ARGUMENT','intent must be finite JSON data')
        if action_id in self.seen:
            old_signature,old_result=self.seen[action_id]
            if signature!=old_signature:return reject('ACTION_ID_CONFLICT','id already used for a different intent')
            if old_result.get('revision')!=revision:
                return reject('ACTION_RESULT_STALE','historical action result is not the current board; use fresh queries and action IDs')
            return {**deepcopy(old_result),'replayed':True}
        if expected_revision!=result['revision']:return reject('STALE_REVISION','query the current board before editing')
        try:validated=validate_action(self.backend,name,args)
        except HarnessError as error:return reject(error.code,error)
        except Exception as error:return reject('BACKEND_UNAVAILABLE',error)
        token=None
        observed_revision=None
        attempt_started=False
        try:
            before=self.backend.verify()['geometric']
            if self.backend.revision()!=expected_revision:
                return reject('STALE_REVISION','board changed while validating intent')
            self._append({'phase':'started','action_id':action_id,'intent':{'name':name,'args':validated},
                'signature':signature,'expected_revision':expected_revision})
            attempt_started=True
            token=self.backend.checkpoint(expected_current=expected_revision)
            if token.get('capture_before_revision')!=expected_revision:
                raise HarnessError('CONCURRENT_EDIT','checkpoint baseline differs from authorized action')
            ids=self.backend.apply(name,validated)
            observed_revision=self.backend.revision()
            after=self.backend.verify()
            if self.backend.revision()!=observed_revision:
                raise HarnessError('CONCURRENT_EDIT','board changed during verification')
            old,new=violation_map(before),violation_map(after['geometric'])
            result.update(changed_ids=ids,drc_delta={
                'added':[json.loads(k) for k in sorted((new-old).elements())],
                'resolved':[json.loads(k) for k in sorted((old-new).elements())]},
                connectivity_findings=after['connectivity'])
            if after.get('ignored_checks'):
                result['warnings'].append('Initial checks excluded: '+', '.join(c['key'] for c in after['ignored_checks']))
            if mode=='strict' and result['drc_delta']['added']:
                self.backend.restore(token,expected_current=observed_revision)
                result.update(error_code='GEOMETRY_REGRESSION',message='new or changed geometric violation; action rolled back',rolled_back=True)
            else:
                if hasattr(self.backend,'persist_accepted'):
                    self.backend.persist_accepted(expected_current=observed_revision)
                result['ok']=True
        except Exception as error:
            result.update(error_code=getattr(error,'code','TOOL_ERROR'),message=str(error))
            if attempt_started and token is None:
                self.recovery_required=True
                result['recovery_required']=True
            if token is not None:
                try:
                    self.backend.restore(token,expected_current=observed_revision)
                    result['rolled_back']=True
                except Exception as recovery:
                    self.recovery_required=True
                    result.update(recovery_required=True,recovery_error=str(recovery))
        try:
            result['revision']=self.backend.revision()
            self._append({'phase':'finished','action_id':action_id,'signature':signature,'result':result})
        except Exception as evidence_error:
            self.recovery_required=True
            result.update(ok=False,recovery_required=True,error_code='RECOVERY_REQUIRED',message=str(evidence_error))
        self.seen[action_id]=(signature,deepcopy(result))
        return result
