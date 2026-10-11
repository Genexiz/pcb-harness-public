"""Initial real backend, deliberately restricted to workspace run-directory copies.

Known M0 rules and rectangular outline only. Single-writer lease protects harness
instances, not manual GUI edits; full revision checks detect observed conflicts.
"""
from pathlib import Path
import fcntl
import hashlib
import json
import shutil
import uuid

from kipy import KiCad
from kipy.board import Board
from kipy.client import KiCadClient
from kipy.board_types import BoardLayer,BoardRectangle,Track,Via,Zone
from kipy.geometry import Vector2,Angle,PolygonWithHoles,PolyLine,PolyLineNode
from kipy.proto.common.types import DocumentType
from kipy.util.board_layer import CANONICAL_LAYER_NAMES
from kipy.util.units import from_mm
from .contracts import HarnessError
from .native_reports import select_document,run_verification
from .initial_rules import validate_probe_rules
from .safety import wait_until_ready


def supports_native_flip(version):
    # Pin tested API family; future majors need their own native acceptance.
    return version.major==10 and version.minor==0 and version.patch>=6


def classify_issues(issues):
    result={'geometric':[],'connectivity':[]}
    temporary={'unconnected_items','track_dangling','via_dangling'}
    for item in issues:
        normalized={'type':item['type'],'ids':sorted(i['uuid'] for i in item.get('items',[]) if i.get('uuid')),
            'severity':item['severity'],'description':item.get('description',''),'items':item.get('items',[])}
        result['connectivity' if item['type'] in temporary else 'geometric'].append(normalized)
    return result


def wait_ready(ping,timeout=10):
    try:wait_until_ready(ping,timeout=timeout)
    except TimeoutError as error:raise HarnessError('RECOVERY_REQUIRED',str(error)) from error


class ScratchIPCBackend:
    kind='kicad-ipc-scratch'
    def __init__(self,project_path,*,workspace=None,socket='ipc:///tmp/kicad/api.sock',cli=None,artifacts=None):
        self.workspace=Path(workspace or Path(__file__).resolve().parents[2]).resolve()
        self.path=Path(project_path).resolve()
        if not self.path.is_relative_to(self.workspace/'runs') or self.path.suffix!='.kicad_pcb':
            raise HarnessError('UNSAFE_PROJECT','initial adapter only edits copies in the workspace run directory')
        if not all(self.path.with_suffix(s).is_file() for s in ('.kicad_pcb','.kicad_pro','.kicad_sch','.kicad_dru')):
            raise HarnessError('INVALID_PROJECT','complete project bundle is required')
        validate_probe_rules(self.path.with_suffix('.kicad_dru'))
        self.cli=Path(cli or '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
        self.artifacts=Path(artifacts or self.workspace/'runs/kernel'/str(uuid.uuid4())).resolve()
        if not self.artifacts.is_relative_to(self.workspace/'runs') or self.artifacts.is_relative_to(self.path.parent):
            raise HarnessError('UNSAFE_ARTIFACTS','artifacts must be a separate workspace run directory')
        if any(p.is_symlink() for p in self.path.parent.rglob('*')):
            raise HarnessError('UNSAFE_PROJECT','initial scratch project cannot contain symlink assets')
        self.artifacts.mkdir(parents=True,exist_ok=True)
        self._lease=None;self._cache=None;self._active_checkpoint=None
        try:
            self._lease=(self.path.parent/'.pcb-harness.writer.lock').open('a')
            try:fcntl.flock(self._lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise HarnessError('WRITER_BUSY','another harness writer owns this scratch project')
            self.client=KiCadClient(socket,f'pcb-harness-kernel-{uuid.uuid4()}','',3000)
            self.kicad=KiCad.from_client(self.client)
            self.server_version=self.kicad.get_version()
            self._native_flip=supports_native_flip(self.server_version)
            doc=select_document(self.kicad.get_open_documents(DocumentType.DOCTYPE_PCB),self.path)
            self.board=Board(self.client,doc)
            self._layers={CANONICAL_LAYER_NAMES[x]:x for x in self.board.get_enabled_layers()
                if CANONICAL_LAYER_NAMES.get(x,'').endswith('.Cu')}
            self.bounds()  # unknown outline is rejected before any mutation
            self._known_saved_files=self._project_hashes()
        except Exception:
            self.close();raise

    def close(self):
        if self._lease is not None:
            self._lease.close();self._lease=None

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def capabilities(self):
        actions={'place_footprint','move_footprint','rotate_footprint','route_track','add_via','delete_track','add_zone','fill_zones'}
        if self._native_flip:actions.add('flip_footprint')
        return actions
    def identity(self):return {'backend':self.kind,'project_path':str(self.path)}
    def enabled_layers(self):return set(self._layers)
    def net_names(self):return {n.name for n in self.board.get_nets() if n.name}
    def _footprint(self,ref):
        parts=[f for f in self.board.get_footprints() if f.reference_field.text.value==ref]
        if len(parts)!=1:raise HarnessError('UNKNOWN_REF',f'expected one footprint {ref}; found {len(parts)}')
        return parts[0]
    def get_footprint(self,ref):
        f=self._footprint(ref)
        return {'id':f.id.value,'ref':ref,'x_mm':f.position.x/1e6,'y_mm':f.position.y/1e6,
            'rotation_deg':f.orientation.degrees,'locked':f.locked,
            'side':'front' if f.layer==BoardLayer.BL_F_Cu else 'back',
            'pads':[{'number':p.number,'net':p.net.name,'position_mm':[p.position.x/1e6,p.position.y/1e6]} for p in f.definition.pads]}
    def has_track(self,id):return any(t.id.value==id for t in self.board.get_tracks())
    def track_locked(self,id):return next(t.locked for t in self.board.get_tracks() if t.id.value==id)
    def net_info(self,net):
        pads=[{'ref':f.reference_field.text.value,'id':p.id.value,'number':p.number,
            'position_mm':[p.position.x/1e6,p.position.y/1e6],'net':p.net.name}
            for f in self.board.get_footprints() for p in f.definition.pads if p.net.name==net]
        tracks=[t for t in self.board.get_tracks() if t.net.name==net]
        return {'net':net,'pads':pads,'tracks':[{'id':t.id.value,'layer':CANONICAL_LAYER_NAMES[t.layer],
            'start_mm':[t.start.x/1e6,t.start.y/1e6],'end_mm':[t.end.x/1e6,t.end.y/1e6],
            'width_mm':t.width/1e6} for t in tracks],'track_length_mm':sum(t.length()/1e6 for t in tracks)}
    def bounds(self):
        edges=[s for s in self.board.get_shapes() if s.layer==BoardLayer.BL_Edge_Cuts]
        if len(edges)!=1 or not isinstance(edges[0],BoardRectangle):
            raise HarnessError('UNSUPPORTED_OUTLINE','initial scratch backend requires a single rectangular Edge.Cuts outline')
        a,b=edges[0].top_left,edges[0].bottom_right
        return [min(a.x,b.x)/1e6,min(a.y,b.y)/1e6,max(a.x,b.x)/1e6,max(a.y,b.y)/1e6]
    def _project_hashes(self):
        return {str(p.relative_to(self.path.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.path.parent.rglob('*') if p.is_file() and
            (p.suffix in ('.kicad_pcb','.kicad_pro','.kicad_dru','.kicad_sch','.kicad_sym','.kicad_mod') or p.name in ('fp-lib-table','sym-lib-table'))}
    def revision(self):
        text=self.board.get_as_string()
        return hashlib.sha256((text+json.dumps(self._project_hashes(),sort_keys=True)).encode()).hexdigest()
    def _snapshot_copy(self,target):
        shutil.copytree(self.path.parent,target,ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','*-backups'))
        self.board.save_as(str(target/self.path.name),overwrite=True,include_project=True)
        return target/self.path.name
    def ensure_document(self):
        try:select_document(self.kicad.get_open_documents(DocumentType.DOCTYPE_PCB),self.path)
        except ValueError as error:raise HarnessError('DOCUMENT_CHANGED','bound scratch document is no longer open') from error

    def visual_snapshot(self,target):
        target=Path(target).resolve()
        if not target.is_relative_to(self.workspace/'runs') or target.is_relative_to(self.path.parent):
            raise HarnessError('UNSAFE_ARTIFACTS','visual snapshot must be a separate run-directory copy')
        self.ensure_document()
        revision=self.revision();bounds=self.bounds()
        board=self._snapshot_copy(target)
        self.ensure_document()
        if self.revision()!=revision:raise HarnessError('CONCURRENT_EDIT','board changed during visual snapshot')
        return board,bounds,revision

    def checkpoint(self,*,expected_current=None):
        authorized=self.revision()
        if expected_current is not None and authorized!=expected_current:
            raise HarnessError('CONCURRENT_EDIT','board changed before checkpoint capture')
        before_text=self.board.get_as_string()
        before_files=self._project_hashes()
        capture_digest=hashlib.sha256((before_text+json.dumps(before_files,sort_keys=True)).encode()).hexdigest()
        if capture_digest!=authorized or before_files!=self._known_saved_files:
            raise HarnessError('CONCURRENT_EDIT','board/project changed before checkpoint save')
        self.board.save()  # only an unchanged, authorized scratch state may be persisted
        after_text=self.board.get_as_string()
        after_files=self._project_hashes()
        if after_text!=before_text:
            raise HarnessError('RECOVERY_REQUIRED','serialized board changed during checkpoint save')
        # Save may reformat persisted files, but must not change the live board.
        self._known_saved_files=after_files
        target=self.artifacts/f'checkpoint-{uuid.uuid4()}'
        shutil.copytree(self.path.parent,target,ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','*-backups'))
        if self.board.get_as_string()!=before_text or self._project_hashes()!=after_files:
            raise HarnessError('RECOVERY_REQUIRED','project changed during checkpoint copy')
        for relative,expected_hash in after_files.items():
            if hashlib.sha256((target/relative).read_bytes()).hexdigest()!=expected_hash:
                raise HarnessError('RECOVERY_REQUIRED','checkpoint bytes differ from captured project')
        revision=self.revision()
        expected_after=hashlib.sha256((after_text+json.dumps(after_files,sort_keys=True)).encode()).hexdigest()
        if revision!=expected_after:
            raise HarnessError('RECOVERY_REQUIRED','checkpoint completion readback changed')
        token={'project_path':str(self.path),'capture_before_revision':authorized,'revision':revision,
            'project_hashes':after_files,'directory':str(target)}
        (target/'manifest.json').write_text(json.dumps(token,indent=2))
        self._active_checkpoint=token
        return token
    def restore(self,token,*,expected_current):
        if token.get('project_path')!=str(self.path):
            raise HarnessError('RECOVERY_REQUIRED','checkpoint belongs to a different originating project')
        if expected_current is None or self.revision()!=expected_current or self._project_hashes()!=self._known_saved_files:
            target=self.artifacts/f'recovery-{uuid.uuid4()}'
            try:self._snapshot_copy(target)
            finally:raise HarnessError('RECOVERY_REQUIRED',f'concurrent/uncertain state; automatic restore refused; recovery {target}')
        checkpoint=Path(token['directory']).resolve()
        if not checkpoint.is_relative_to(self.artifacts) or not checkpoint.is_dir():
            raise HarnessError('RECOVERY_REQUIRED','checkpoint does not belong to this run')
        # Validate all bytes before touching the live bundle.
        for relative,expected_hash in token['project_hashes'].items():
            source=(checkpoint/relative).resolve()
            if not source.is_relative_to(checkpoint) or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=expected_hash:
                raise HarnessError('RECOVERY_REQUIRED','checkpoint artifact missing or altered')
        for relative in token['project_hashes']:
            destination=(self.path.parent/relative).resolve()
            if not destination.is_relative_to(self.path.parent):
                raise HarnessError('RECOVERY_REQUIRED','live bundle target resolves outside scratch directory')
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(checkpoint/relative,destination)
        self.board.revert()
        self._known_saved_files=self._project_hashes()
        if self.revision()!=token['revision']:
            raise HarnessError('RECOVERY_REQUIRED','revert did not restore the full checkpoint revision')
        self._cache=None
    def apply(self,name,args):
        if self._active_checkpoint is None or self.revision()!=self._active_checkpoint['revision']:
            raise HarnessError('CONCURRENT_EDIT','scratch board changed since checkpoint')
        commit=self.board.begin_commit()
        try:
            ids=[]
            if name in ('place_footprint','move_footprint','rotate_footprint','flip_footprint'):
                f=self._footprint(args['ref'])
                if f.locked:raise HarnessError('LOCKED_OBJECT','footprint locked since validation')
                current_side='front' if f.layer==BoardLayer.BL_F_Cu else 'back'
                if name=='flip_footprint' or (name=='place_footprint' and args.get('side',current_side)!=current_side):
                    if not self._native_flip:raise HarnessError('UNSUPPORTED_CAPABILITY','native flip requires KiCad 10.0.6+')
                    target_layer=BoardLayer.BL_B_Cu if current_side=='front' else BoardLayer.BL_F_Cu
                    flipped=self.board.flip_items(f)
                    if len(flipped)!=1 or flipped[0].id!=f.id or flipped[0].layer!=target_layer:
                        raise HarnessError('MUTATION_FAILED','native flip did not return the requested footprint side')
                    f=flipped[0]
                if name=='place_footprint':f.position=Vector2.from_xy_mm(args['x_mm'],args['y_mm']);f.orientation=Angle.from_degrees(args['rotation_deg'])
                if name=='move_footprint':f.position=Vector2.from_xy_mm(f.position.x/1e6+args['dx_mm'],f.position.y/1e6+args['dy_mm'])
                if name=='rotate_footprint':f.orientation=Angle.from_degrees(f.orientation.degrees+args['deg'])
                changed=self.board.update_items(f)
                if len(changed)!=1:raise HarnessError('MUTATION_FAILED','footprint update did not return one item')
                ids=[x.id.value for x in changed]
            elif name=='route_track':
                net=next(n for n in self.board.get_nets() if n.name==args['net']);items=[]
                for a,b in zip(args['points_mm'],args['points_mm'][1:]):
                    t=Track();t.start=Vector2.from_xy_mm(*a);t.end=Vector2.from_xy_mm(*b)
                    t.width=from_mm(args['width_mm']);t.layer=self._layers[args['layer']];t.net=net;items.append(t)
                created=self.board.create_items(items)
                if len(created)!=len(items):raise HarnessError('MUTATION_FAILED','track creation incomplete')
                ids=[x.id.value for x in created]
            elif name=='add_via':
                v=Via();v.position=Vector2.from_xy_mm(args['x_mm'],args['y_mm'])
                v.diameter=from_mm(args['dia_mm']);v.drill_diameter=from_mm(args['drill_mm'])
                v.net=next(n for n in self.board.get_nets() if n.name==args['net'])
                created=self.board.create_items(v)
                if len(created)!=1:raise HarnessError('MUTATION_FAILED','via creation incomplete')
                ids=[created[0].id.value]
            elif name=='delete_track':
                t=next(t for t in self.board.get_tracks() if t.id.value==args['id'])
                if t.locked:raise HarnessError('LOCKED_OBJECT','track locked since validation')
                self.board.remove_items(t);ids=[args['id']]
            elif name=='add_zone':
                z=Zone();z.layers=[self._layers[args['layer']]];z.clearance=from_mm(args['clearance_mm'])
                z.net=next(n for n in self.board.get_nets() if n.name==args['net'])
                outline=PolygonWithHoles();line=PolyLine()
                for p in args['polygon_mm']:line.append(PolyLineNode.from_point(Vector2.from_xy_mm(*p)))
                outline.outline=line;z.outline=outline
                created=self.board.create_items(z)
                if len(created)!=1:raise HarnessError('MUTATION_FAILED','zone creation incomplete')
                ids=[created[0].id.value]
            elif name=='fill_zones':ids=[z.id.value for z in self.board.get_zones()]
            else:raise HarnessError('UNSUPPORTED_CAPABILITY',name)
            self.board.push_commit(commit,f'PCB Harness {name}')
            commit=None
            if name in ('add_zone','fill_zones'):
                self.board.refill_zones(block=False);wait_ready(self.kicad.ping)
            return ids
        finally:
            if commit is not None:self.board.drop_commit(commit)
    def persist_accepted(self,*,expected_current):
        if self.revision()!=expected_current or self._project_hashes()!=self._known_saved_files:
            raise HarnessError('CONCURRENT_EDIT','accepted state changed before durable completion')
        self.board.save()
        self._known_saved_files=self._project_hashes()
        self._cache=None
    def verify(self):
        validate_probe_rules(self.path.with_suffix('.kicad_dru'))
        revision=self.revision()
        if self._cache and self._cache[0]==revision:return self._cache[1]
        target=self.artifacts/f'verify-{uuid.uuid4()}'
        copy=self._snapshot_copy(target)
        result=run_verification(self.cli,'drc',copy,target/'drc.json')
        (target/'result.json').write_text(json.dumps(result,indent=2))
        if result['status']!='verified':raise HarnessError('VERIFICATION_FAILED',result.get('error','native DRC did not finish'))
        if self.revision()!=revision:raise HarnessError('CONCURRENT_EDIT','board changed during saved-copy verification')
        categorized=classify_issues(result['issues'])
        categorized.update(ignored_checks=result['ignored_checks'],evidence=str(target),release_verified=False)
        self._cache=(revision,categorized)
        return categorized
    def summary(self):
        current=self.revision();cached=self._cache[1] if self._cache and self._cache[0]==current else None
        return {'footprint_count':len(self.board.get_footprints()),'track_count':len(self.board.get_tracks()),
            'via_count':len(self.board.get_vias()),'zone_count':len(self.board.get_zones()),
            'geometric_issue_count':len(cached['geometric']) if cached else None,
            'unrouted_count':sum(v['type']=='unconnected_items' for v in cached['connectivity']) if cached else None,
            'capabilities':sorted(self.capabilities()),'server_version':str(self.server_version),
            'limitations':['scratch-only; rectangular outline; known initial rules; no fabrication release']}
