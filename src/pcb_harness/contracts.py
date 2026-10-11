import math


class HarnessError(Exception):
    def __init__(self,code,message):
        self.code=code
        super().__init__(message)


def number(value,name,*,positive=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise HarnessError('INVALID_ARGUMENT',f'{name} must be a finite number')
    if positive and value<=0:
        raise HarnessError('INVALID_ARGUMENT',f'{name} must be positive')
    return float(value)


def point(value):
    if not isinstance(value,(list,tuple)) or len(value)!=2:
        raise HarnessError('INVALID_ARGUMENT','point must contain exactly x,y in mm')
    return [number(value[0],'x_mm'),number(value[1],'y_mm')]


def validate_action(backend,name,args):
    if not isinstance(name,str):raise HarnessError('INVALID_ARGUMENT','action name must be text')
    if not isinstance(args,dict):raise HarnessError('INVALID_ARGUMENT','args must be an object')
    if name not in backend.capabilities():
        raise HarnessError('UNSUPPORTED_CAPABILITY',f'{name} is unavailable on this backend')
    result=dict(args)
    schemas={
        'place_footprint':({'ref','x_mm','y_mm'},{'rotation_deg','side'}),
        'move_footprint':({'ref','dx_mm','dy_mm'},set()),
        'rotate_footprint':({'ref','deg'},set()),
        'flip_footprint':({'ref'},set()),
        'route_track':({'net','layer','points_mm','width_mm'},set()),
        'add_via':({'net','x_mm','y_mm','drill_mm','dia_mm','layers'},set()),
        'delete_track':({'id'},set()),
        'add_zone':({'net','layer','polygon_mm','clearance_mm'},set()),
        'fill_zones':(set(),set())}
    required,optional=schemas[name]
    if not required.issubset(args) or set(args)-required-optional:
        raise HarnessError('INVALID_ARGUMENT',f'{name}: missing or unknown arguments')
    if 'ref' in args:
        if not isinstance(args['ref'],str):raise HarnessError('INVALID_ARGUMENT','ref must be text')
        footprint=backend.get_footprint(args['ref'])
        if footprint['locked']:raise HarnessError('LOCKED_OBJECT',f'{args["ref"]} is locked')
    if name=='place_footprint':
        result.update(x_mm=number(args['x_mm'],'x_mm'),y_mm=number(args['y_mm'],'y_mm'),
            rotation_deg=number(args.get('rotation_deg',footprint['rotation_deg']),'rotation_deg'))
        current_side=footprint.get('side','front');requested_side=args.get('side',current_side)
        if requested_side not in ('front','back'):
            raise HarnessError('INVALID_ARGUMENT','side must be front or back')
        result['side']=requested_side
        if requested_side!=current_side and 'flip_footprint' not in backend.capabilities():
            raise HarnessError('UNSUPPORTED_CAPABILITY','changing footprint side requires verified flip capability')
    if name=='move_footprint':
        result['dx_mm']=number(args['dx_mm'],'dx_mm');result['dy_mm']=number(args['dy_mm'],'dy_mm')
    if name=='rotate_footprint':result['deg']=number(args['deg'],'deg')
    if 'net' in args:
        if not isinstance(args['net'],str) or args['net'] not in backend.net_names():
            raise HarnessError('UNKNOWN_NET',f'unknown net {args["net"]!r}')
    if 'layer' in args and (not isinstance(args['layer'],str) or args['layer'] not in backend.enabled_layers()):
        raise HarnessError('UNKNOWN_LAYER',f'unknown copper layer {args["layer"]!r}')
    if name=='route_track':
        if not isinstance(args['points_mm'],(list,tuple)) or len(args['points_mm'])<2:
            raise HarnessError('INVALID_ARGUMENT','track requires at least two explicit points')
        result['points_mm']=[point(p) for p in args['points_mm']]
        if any(a==b for a,b in zip(result['points_mm'],result['points_mm'][1:])):
            raise HarnessError('INVALID_ARGUMENT','zero-length segments are not allowed')
        result['width_mm']=number(args['width_mm'],'width_mm',positive=True)
    if name=='add_via':
        result.update(x_mm=number(args['x_mm'],'x_mm'),y_mm=number(args['y_mm'],'y_mm'),
            drill_mm=number(args['drill_mm'],'drill_mm',positive=True),dia_mm=number(args['dia_mm'],'dia_mm',positive=True))
        if result['dia_mm']<=result['drill_mm']:
            raise HarnessError('INVALID_ARGUMENT','via diameter must exceed drill diameter')
        if args['layers']!=['F.Cu','B.Cu']:
            raise HarnessError('UNSUPPORTED_CAPABILITY','initial Kernel supports through vias only')
    if name=='delete_track':
        if not isinstance(args['id'],str):raise HarnessError('INVALID_ARGUMENT','id must be text')
        if not backend.has_track(args['id']):raise HarnessError('UNKNOWN_OBJECT','track id not found')
        if backend.track_locked(args['id']):raise HarnessError('LOCKED_OBJECT','track is locked')
    if name=='add_zone':
        if not isinstance(args['polygon_mm'],(list,tuple)) or len(args['polygon_mm'])<3:
            raise HarnessError('INVALID_ARGUMENT','zone requires at least three vertices')
        result['polygon_mm']=[point(p) for p in args['polygon_mm']]
        result['clearance_mm']=number(args['clearance_mm'],'clearance_mm',positive=True)
        polygon=result['polygon_mm']
        if len(set(map(tuple,polygon)))<3 or abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(polygon,polygon[1:]+polygon[:1])))<1e-9:
            raise HarnessError('INVALID_ARGUMENT','zone polygon has zero area')
    bounds=backend.bounds()
    points=[]
    if name=='route_track':points=result['points_mm']
    if name in ('place_footprint','add_via'):points=[[result['x_mm'],result['y_mm']]]
    if name=='move_footprint':points=[[footprint['x_mm']+result['dx_mm'],footprint['y_mm']+result['dy_mm']]]
    if name=='add_zone':points=result['polygon_mm']
    if bounds is not None and any(not(bounds[0]<=x<=bounds[2] and bounds[1]<=y<=bounds[3]) for x,y in points):
        raise HarnessError('OUT_OF_BOARD','requested point is outside the board bounds')
    return result
