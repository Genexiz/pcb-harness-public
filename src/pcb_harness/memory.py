"""Limited circle-pad/segment model for Kernel tests. Never a release verifier."""
from copy import deepcopy
import hashlib
import json
import math
import uuid
from .contracts import HarnessError


def point_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    scale=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(p[0]-a[0]-scale*dx,p[1]-a[1]-scale*dy)


def segment_distance(a,b,c,d):
    def cross(p,q,r):return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0:return 0
    return min(point_distance(a,c,d),point_distance(b,c,d),point_distance(c,a,b),point_distance(d,a,b))


class MemoryBackend:
    kind='memory-test-only'
    def __init__(self):
        self._scope_id=str(uuid.uuid4())
        self.footprints={};self.tracks={};self.vias={}
        self.minimum_width=0.2;self.clearance=0.2
        self.board_bounds=[10,10,70,30]

    @classmethod
    def fixture(cls):
        board=cls()
        for i,x in enumerate([20,40,60],1):
            board.footprints[f'R{i}']={'id':f'R{i}','ref':f'R{i}','x_mm':x,'y_mm':20,
                'rotation_deg':0,'locked':False,'local_pads':[
                    {'number':'1','offset_mm':[-1,0],'net':'/NET_A'},
                    {'number':'2','offset_mm':[1,0],'net':'/NET_B'}]}
        return board

    def capabilities(self):return {'place_footprint','move_footprint','rotate_footprint','route_track','add_via','delete_track'}
    def identity(self):return {'backend':self.kind,'project_id':self._scope_id}
    def bounds(self):return self.board_bounds
    def enabled_layers(self):return {'F.Cu','B.Cu'}
    def net_names(self):return {p['net'] for f in self.footprints.values() for p in f['local_pads']}
    def has_track(self,id):return id in self.tracks
    def track_locked(self,id):return self.tracks[id].get('locked',False)
    def revision(self):
        return hashlib.sha256(json.dumps([self.footprints,self.tracks,self.vias,self.board_bounds,
            self.minimum_width,self.clearance],sort_keys=True).encode()).hexdigest()

    def get_footprint(self,ref):
        if ref not in self.footprints:raise HarnessError('UNKNOWN_REF',f'unknown footprint {ref}')
        result=deepcopy(self.footprints[ref]);a=math.radians(result['rotation_deg'])
        result['pads']=[]
        for p in result.pop('local_pads'):
            dx,dy=p['offset_mm']
            result['pads'].append({'number':p['number'],'net':p['net'],'position_mm':[
                round(result['x_mm']+dx*math.cos(a)+dy*math.sin(a),9),
                round(result['y_mm']-dx*math.sin(a)+dy*math.cos(a),9)]})
        return result

    def checkpoint(self,*,expected_current=None):
        before=self.revision()
        if expected_current is not None and before!=expected_current:
            raise HarnessError('CONCURRENT_EDIT','board changed before checkpoint capture')
        state=deepcopy((self.footprints,self.tracks,self.vias))
        if self.revision()!=before:
            raise HarnessError('CONCURRENT_EDIT','board changed during checkpoint capture')
        return {'identity':self.identity(),'state':state,'capture_before_revision':before,'revision':before}
    def net_info(self,net):
        return {'net':net,'pads':[{'ref':ref,**p} for ref in self.footprints for p in self.get_footprint(ref)['pads'] if p['net']==net],
            'tracks':[deepcopy(t) for t in self.tracks.values() if t['net']==net],
            'track_length_mm':sum(math.dist(t['a'],t['b']) for t in self.tracks.values() if t['net']==net)}
    def restore(self,token,*,expected_current):
        if token.get('identity')!=self.identity():raise HarnessError('RECOVERY_REQUIRED','checkpoint belongs to another project')
        if expected_current is None or self.revision()!=expected_current:
            raise HarnessError('RECOVERY_REQUIRED','current state changed or mutation delivery unknown')
        self.footprints,self.tracks,self.vias=deepcopy(token['state'])

    def apply(self,name,args):
        if name in ('place_footprint','move_footprint','rotate_footprint'):
            f=self.footprints[args['ref']]
            if name=='place_footprint':f.update(x_mm=args['x_mm'],y_mm=args['y_mm'],rotation_deg=args['rotation_deg'])
            if name=='move_footprint':f['x_mm']+=args['dx_mm'];f['y_mm']+=args['dy_mm']
            if name=='rotate_footprint':f['rotation_deg']=(f['rotation_deg']+args['deg']+180)%360-180
            return [f['id']]
        if name=='route_track':
            ids=[]
            for a,b in zip(args['points_mm'],args['points_mm'][1:]):
                id=str(uuid.uuid4());ids.append(id)
                self.tracks[id]={'id':id,'a':a,'b':b,'width_mm':args['width_mm'],'layer':args['layer'],'net':args['net']}
            return ids
        if name=='add_via':
            id=str(uuid.uuid4());self.vias[id]={'id':id,**args};return [id]
        if name=='delete_track':del self.tracks[args['id']];return [args['id']]
        raise HarnessError('UNSUPPORTED_CAPABILITY',name)

    def verify(self):
        issues=[]
        pads=[{'id':f'{ref}.{p["number"]}',**p} for ref in self.footprints for p in self.get_footprint(ref)['pads']]
        def issue(type,ids,description):issues.append({'type':type,'ids':sorted(ids),'description':description})
        tracks=list(self.tracks.values())
        footprint_list=list(self.footprints.values())
        def courtyard(f):
            a=math.radians(f['rotation_deg']);dx=2*abs(math.cos(a))+1.4*abs(math.sin(a));dy=2*abs(math.sin(a))+1.4*abs(math.cos(a))
            return [f['x_mm']-dx,f['y_mm']-dy,f['x_mm']+dx,f['y_mm']+dy]
        for i,f in enumerate(footprint_list):
            a=courtyard(f)
            for other in footprint_list[:i]:
                b=courtyard(other)
                if min(a[2],b[2])>max(a[0],b[0])+1e-9 and min(a[3],b[3])>max(a[1],b[1])+1e-9:
                    issue('courtyards_overlap',[f['id'],other['id']],'test fixture courtyard bounding boxes overlap')
        def edge_gap(p,radius):
            return min(p[0]-self.board_bounds[0],p[1]-self.board_bounds[1],
                self.board_bounds[2]-p[0],self.board_bounds[3]-p[1])-radius
        for t in tracks:
            if t['width_mm']<self.minimum_width:issue('track_width',[t['id']],f'min {self.minimum_width}; actual {t["width_mm"]}')
            if min(edge_gap(t['a'],t['width_mm']/2),edge_gap(t['b'],t['width_mm']/2))<0.5-1e-9:
                issue('copper_edge_clearance',[t['id']],'minimum copper-to-edge 0.5 mm')
            if t['layer']=='F.Cu':
                for p in pads:
                    if t['net']==p['net']:continue
                    gap=point_distance(p['position_mm'],t['a'],t['b'])-0.5-t['width_mm']/2
                    if gap<self.clearance-1e-9:issue('shorting_items' if gap<=0 else 'clearance',[t['id'],p['id']],f'gap_mm={round(gap,9)}')
        for i,t in enumerate(tracks):
            for other in tracks[i+1:]:
                if t['net']==other['net'] or t['layer']!=other['layer']:continue
                gap=segment_distance(t['a'],t['b'],other['a'],other['b'])-(t['width_mm']+other['width_mm'])/2
                if gap<self.clearance-1e-9:issue('shorting_items' if gap<=0 else 'clearance',[t['id'],other['id']],f'gap_mm={round(gap,9)}')
        for v in self.vias.values():
            if v['dia_mm']<0.5 or v['drill_mm']<0.2:issue('via_dimensions',[v['id']],'below test profile minimum')
            if edge_gap([v['x_mm'],v['y_mm']],v['dia_mm']/2)<0.5-1e-9:
                issue('copper_edge_clearance',[v['id']],'minimum copper-to-edge 0.5 mm')
            for p in pads:
                if p['net']==v['net']:continue
                gap=math.dist(p['position_mm'],[v['x_mm'],v['y_mm']])-0.5-v['dia_mm']/2
                if gap<self.clearance-1e-9:issue('shorting_items' if gap<=0 else 'clearance',[v['id'],p['id']],f'gap_mm={round(gap,9)}')
            for t in tracks:
                if t['net']==v['net']:continue
                gap=point_distance([v['x_mm'],v['y_mm']],t['a'],t['b'])-v['dia_mm']/2-t['width_mm']/2
                if gap<self.clearance-1e-9:issue('shorting_items' if gap<=0 else 'clearance',[v['id'],t['id']],f'gap_mm={round(gap,9)}')
        via_list=list(self.vias.values())
        for i,v in enumerate(via_list):
            for other in via_list[:i]:
                if v['net']==other['net']:continue
                gap=math.dist([v['x_mm'],v['y_mm']],[other['x_mm'],other['y_mm']])-(v['dia_mm']+other['dia_mm'])/2
                if gap<self.clearance-1e-9:issue('shorting_items' if gap<=0 else 'clearance',[v['id'],other['id']],f'gap_mm={round(gap,9)}')
        connectivity=[]
        for net in sorted(self.net_names()):
            nodes=[('pad',p['id'],p['position_mm'],{'F.Cu'},0.5) for p in pads if p['net']==net]
            pad_count=len(nodes)
            nodes.extend(('via',v['id'],[v['x_mm'],v['y_mm']],set(v['layers']),v['dia_mm']/2) for v in self.vias.values() if v['net']==net)
            objects=[t for t in tracks if t['net']==net]
            # Small graph: pads and segments connect by actual overlap on common layer.
            groups=[{i} for i in range(len(nodes)+len(objects))]
            def merge(i,j):
                a=next(g for g in groups if i in g);b=next(g for g in groups if j in g)
                if a is not b:a.update(b);groups.remove(b)
            for i,node in enumerate(nodes):
                for j,other in enumerate(nodes[:i]):
                    if node[3]&other[3] and math.dist(node[2],other[2])<=node[4]+other[4]:merge(i,j)
                for j,t in enumerate(objects):
                    if t['layer'] in node[3] and point_distance(node[2],t['a'],t['b'])<=node[4]+t['width_mm']/2:merge(i,len(nodes)+j)
            for i,t in enumerate(objects):
                for j,other in enumerate(objects[:i]):
                    if t['layer']==other['layer'] and segment_distance(t['a'],t['b'],other['a'],other['b'])<=(t['width_mm']+other['width_mm'])/2:merge(len(nodes)+i,len(nodes)+j)
            pad_groups={next(min(g) for g in groups if i in g) for i in range(pad_count)}
            if len(pad_groups)>1:connectivity.append({'type':'unconnected_items','net':net,'groups':len(pad_groups)})
        return {'geometric':issues,'connectivity':connectivity}

    def summary(self):
        v=self.verify()
        return {'footprint_count':len(self.footprints),'track_count':len(self.tracks),'via_count':len(self.vias),
            'geometric_issue_count':len(v['geometric']),'unrouted_count':len(v['connectivity']),
            'limitations':['circle pads and courtyard bounding boxes, segments/through vias; no release verification']}
