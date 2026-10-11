"""Bounded SVG→PNG board views with explicit, calibrated mm/pixel metadata."""
from pathlib import Path
import hashlib
import io
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from PIL import Image,ImageDraw,ImageFont
import resvg_py
from .contracts import HarnessError,number

NS='http://www.w3.org/2000/svg'
CLI=Path('/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
LAYERS={'F.Cu','B.Cu','Edge.Cuts','F.SilkS','B.SilkS','F.Fab','B.Fab'}|{f'In{i}.Cu' for i in range(1,31)}
COLORS={'F.Cu':'#C83434','B.Cu':'#4D7FC4','Edge.Cuts':'#D0D2CD'}


def rectangle(value):
    if not isinstance(value,(list,tuple)) or len(value)!=4:
        raise HarnessError('INVALID_ARGUMENT','region/bounds must be [xmin,ymin,xmax,ymax] mm')
    box=[number(v,'region_mm') for v in value]
    if box[2]<=box[0] or box[3]<=box[1]:raise HarnessError('INVALID_ARGUMENT','region must have positive area')
    return box


def validate_view(bounds,layers,region,width):
    bounds=rectangle(bounds);region=rectangle(region) if region is not None else bounds
    if not isinstance(width,int) or isinstance(width,bool) or not 256<=width<=2048:
        raise HarnessError('INVALID_ARGUMENT','width_px must be an integer from 256 to 2048')
    if not isinstance(layers,(list,tuple)) or not layers or len(layers)>32 or any(not isinstance(x,str) or x not in LAYERS for x in layers):
        raise HarnessError('UNKNOWN_LAYER','unknown/empty plot layer list')
    if not(bounds[0]<=region[0]<region[2]<=bounds[2] and bounds[1]<=region[1]<region[3]<=bounds[3]):
        raise HarnessError('OUT_OF_BOARD','crop must lie inside the physical outline')
    if not all(math.isfinite(region[j]-region[i]) for i,j in ((0,2),(1,3))):
        raise HarnessError('INVALID_ARGUMENT','region span is not finite')
    return bounds,list(dict.fromkeys([*layers,'Edge.Cuts'])),region


def safe_svg(text):
    if not isinstance(text,str) or len(text.encode())>16*1024*1024 or '<!ENTITY' in text.upper():
        raise HarnessError('UNSAFE_SVG','SVG too large or contains entity declarations')
    try:root=ET.fromstring(text)
    except ET.ParseError as error:raise HarnessError('UNSAFE_SVG','invalid SVG XML') from error
    if root.tag!=f'{{{NS}}}svg':raise HarnessError('UNSAFE_SVG','expected SVG root namespace')
    for node in root.iter():
        local=node.tag.split('}')[-1]
        if local in {'script','foreignObject','image','filter','animate','set'}:
            raise HarnessError('UNSAFE_SVG','active/external/filter SVG content is unsupported')
        for key,value in node.attrib.items():
            key=key.split('}')[-1]
            if key.lower().startswith('on') or (key in ('href','src') and not value.startswith('#')):
                raise HarnessError('UNSAFE_SVG','external references/event handlers refused')
        style=' '.join([*node.attrib.values(),node.text or ''] if local=='style' else list(node.attrib.values()))
        if '@import' in style.lower() or any(not u.strip(' \"\'').startswith('#') for u in re.findall(r'url\((.*?)\)',style,re.I)):
            raise HarnessError('UNSAFE_SVG','external CSS references refused')
    return root


def native_offset(root,bounds):
    outlines=[]
    def visit(node,style='',transforms=()):
        own=node.get('style','');effective=own if 'stroke:' in own else style
        chain=transforms+(node.get('transform',''),)
        if node.tag==f'{{{NS}}}path' and 'stroke:#D0D2CD;' in effective:
            if any(t not in ('','translate(0 0) scale(1 1)') for t in chain):
                raise HarnessError('UNSUPPORTED_MAPPING','outline transform is not calibrated')
            d=node.get('d','')
            if re.search(r'[A-DF-KN-Yac-df-kn-y]',d):
                raise HarnessError('UNSUPPORTED_MAPPING','outline must use absolute M/L/Z coordinates')
            values=[float(x) for x in re.findall(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',d)]
            outlines.append(list(zip(values[::2],values[1::2])))
        for child in node:visit(child,effective,chain)
    visit(root)
    if len(outlines)!=1 or len(outlines[0])!=4:raise HarnessError('UNSUPPORTED_MAPPING','expected one rectangular native outline')
    corners=outlines[0];xmin,ymin,xmax,ymax=bounds
    ox=min(p[0] for p in corners)-xmin;oy=min(p[1] for p in corners)-ymin
    expected=[(xmin+ox,ymin+oy),(xmax+ox,ymin+oy),(xmax+ox,ymax+oy),(xmin+ox,ymax+oy)]
    if any(abs(a-b)>0.0002 for p,q in zip(sorted(corners),sorted(expected)) for a,b in zip(p,q)):
        raise HarnessError('UNSUPPORTED_MAPPING','native outline disagrees with supplied geometry bounds')
    # Native page-size-mode=2 exporter uses physical mm and unit viewBox scale.
    view=[float(x) for x in root.get('viewBox','').split()]
    for attr,index in [('width',2),('height',3)]:
        value=root.get(attr,'')
        if not value.endswith('mm') or len(view)!=4 or abs(float(value[:-2])-view[index])>0.0002:
            raise HarnessError('UNSUPPORTED_MAPPING','native SVG unit scale is not calibrated')
    return [ox,oy]


def render_svg(svg_text,bounds_mm,offset_mm,revision,layers,output,*,region_mm=None,width_px=1024,source='SVG view',test_only=False):
    bounds,layers,region=validate_view(bounds_mm,layers,region_mm,width_px)
    if not isinstance(offset_mm,(list,tuple)) or len(offset_mm)!=2:raise HarnessError('UNSUPPORTED_MAPPING','missing SVG offset')
    offset=[number(v,'offset_mm') for v in offset_mm]
    root=safe_svg(svg_text)
    x0,y0,x1,y1=region;spanx,spany=x1-x0,y1-y0
    margin=32;header=100;footer=52
    scale=min((width_px-2*margin)/spanx,(width_px*0.7)/spany)
    board_w=max(1,round(spanx*scale));board_h=max(1,round(spany*scale))
    # Choose one exact scale for the pixel image, tolerating subpixel letterboxing.
    scale=min(board_w/spanx,board_h/spany)
    left=(width_px-board_w)//2;top=header
    height=header+board_h+footer
    root.set('viewBox',f'{x0+offset[0]} {y0+offset[1]} {spanx} {spany}')
    root.set('width',str(board_w));root.set('height',str(board_h))
    root.set('preserveAspectRatio','xMinYMin meet')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    path=output/'render.png'
    if path.exists():raise HarnessError('OUTPUT_EXISTS','refusing to replace prior render')
    try:raw=resvg_py.svg_to_bytes(svg_string=ET.tostring(root,encoding='unicode'),width=board_w,height=board_h)
    except Exception as error:raise HarnessError('RENDER_FAILED',str(error)) from error
    board=Image.open(io.BytesIO(raw)).convert('RGBA')
    if board.size!=(board_w,board_h):raise HarnessError('RENDER_FAILED','raster dimensions disagree with mapping')
    canvas=Image.new('RGB',(width_px,height),(17,24,39));canvas.paste(board,(left,top),board)
    draw=ImageDraw.Draw(canvas);font=ImageFont.load_default(size=14)
    label='MEMORY/TEST VIEW' if test_only else source
    draw.text((16,10),label,fill=(255,191,71) if test_only else (245,245,245),font=font)
    draw.text((16,34),'Layers: '+', '.join(layers),fill='white',font=font)
    draw.text((16,58),'Revision: '+str(revision)[:32],fill='white',font=font)
    draw.text((16,height-42),f'mm: x [{x0:g}, {x1:g}]  y [{y0:g}, {y1:g}] | x right, y down',fill='white',font=font)
    draw.text((16,height-22),'Geometry authority: structured queries; image is supplementary',fill=(172,185,204),font=font)
    stream=io.BytesIO();canvas.save(stream,format='PNG');png=stream.getvalue()
    if len(png)>6*1024*1024:raise HarnessError('RENDER_FAILED','PNG exceeds MCP image budget')
    path.write_bytes(png)
    metadata={'ok':True,'source':source,'test_only':test_only,'revision':revision,'layers':layers,
        'bounds_mm':bounds,'region_mm':region,'board_to_svg_offset_mm':offset,
        'board_to_pixel':{'board_origin_mm':[x0,y0],'pixel_origin':[left,top],'pixels_per_mm':scale,'axis':'x right, y down'},
        'image':{'path':str(path.resolve()),'mime_type':'image/png','width_px':width_px,'height_px':height,
            'sha256':hashlib.sha256(png).hexdigest()},'release_verified':False}
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return {**metadata,'_image_bytes':png}


def memory_svg(backend,layers):
    from xml.sax.saxutils import escape
    x0,y0,x1,y1=backend.bounds()
    parts=[f'<svg xmlns="{NS}" width="{x1-x0}mm" height="{y1-y0}mm" viewBox="{x0} {y0} {x1-x0} {y1-y0}">',
        f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="#111827" stroke="#D0D2CD" stroke-width="0.05"/>']
    for ref in backend.footprints:
        f=backend.get_footprint(ref);layer='B.Cu' if f.get('side')=='back' else 'F.Cu'
        if layer not in layers:continue
        parts.append(f'<text x="{f["x_mm"]}" y="{f["y_mm"]-2}" font-size="1.2" fill="white">{escape(ref)}</text>')
        for pad in f['pads']:
            x,y=pad['position_mm'];parts.append(f'<circle cx="{x}" cy="{y}" r="0.5" fill="{COLORS[layer]}"/>')
    for t in backend.tracks.values():
        if t['layer'] not in layers:continue
        a,b=t['a'],t['b'];parts.append(f'<path d="M {a[0]} {a[1]} L {b[0]} {b[1]}" stroke="{COLORS[t["layer"]]}" stroke-width="{t["width_mm"]}" fill="none"/>')
    for via in backend.vias.values():
        if not {'F.Cu','B.Cu'}.intersection(layers):continue
        x,y=via['x_mm'],via['y_mm'];parts.append(f'<circle cx="{x}" cy="{y}" r="{via["dia_mm"]/2}" fill="#CCA854"/><circle cx="{x}" cy="{y}" r="{via["drill_mm"]/2}" fill="#111827"/>')
    return ''.join(parts)+'</svg>'


def saved_outline_bounds(path):
    """Parse only the saved root-level rectangular outline; not an editor/parser API."""
    text=Path(path).read_text()
    if len(text)>32*1024*1024:raise HarnessError('UNSUPPORTED_MAPPING','saved board exceeds parser budget')
    tokens=re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text)
    stack=[];root=None
    for token in tokens:
        if token=='(':
            if len(stack)>64:raise HarnessError('UNSUPPORTED_MAPPING','board nesting exceeds parser budget')
            node=[]
            if stack:stack[-1].append(node)
            stack.append(node)
        elif token==')':
            if not stack:raise HarnessError('UNSUPPORTED_MAPPING','unbalanced saved board')
            root=stack.pop()
        else:
            if not stack:raise HarnessError('UNSUPPORTED_MAPPING','invalid saved board')
            stack[-1].append(token[1:-1] if token.startswith('"') else token)
    if stack or not root or root[0]!='kicad_pcb':raise HarnessError('UNSUPPORTED_MAPPING','invalid saved board root')
    edges=[]
    for node in root[1:]:
        if isinstance(node,list) and node and str(node[0]).startswith('gr_'):
            fields={f[0]:f[1:] for f in node[1:] if isinstance(f,list) and f}
            if fields.get('layer')==['Edge.Cuts']:
                if node[0]!='gr_rect':raise HarnessError('UNSUPPORTED_MAPPING','saved outline is not one rectangle')
                try:a=[float(v) for v in fields['start']];b=[float(v) for v in fields['end']]
                except (KeyError,ValueError):raise HarnessError('UNSUPPORTED_MAPPING','invalid saved outline points')
                if len(a)!=2 or len(b)!=2:raise HarnessError('UNSUPPORTED_MAPPING','invalid saved outline points')
                edges.append(rectangle([min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])]))
    if len(edges)!=1:raise HarnessError('UNSUPPORTED_MAPPING','expected one saved rectangular outline')
    return edges[0]


def export_saved_board(board_path,bounds_mm,revision,layers,output,*,region_mm=None,width_px=1024,cli=CLI,source='saved KiCad board'):
    bounds,layers,region=validate_view(bounds_mm,layers,region_mm,width_px)
    if saved_outline_bounds(board_path)!=bounds:
        raise HarnessError('UNSUPPORTED_MAPPING','queried bounds disagree with saved board outline')
    output=Path(output);output.mkdir(parents=True,exist_ok=False);svg=output/'raw.svg'
    command=[str(cli),'pcb','export','svg','--layers',','.join(layers),'--mode-single','--page-size-mode','2',
        '--exclude-drawing-sheet','--scale','1','-o',str(svg.resolve()),str(Path(board_path).resolve())]
    try:result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    except (OSError,subprocess.TimeoutExpired) as error:raise HarnessError('EXPORT_FAILED',str(error)) from error
    (output/'export.json').write_text(json.dumps({'command':command,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2))
    if result.returncode!=0 or not svg.is_file():raise HarnessError('EXPORT_FAILED','native SVG export did not complete')
    if svg.stat().st_size>16*1024*1024:raise HarnessError('UNSAFE_SVG','native SVG exceeds size budget')
    text=svg.read_text();offset=native_offset(safe_svg(text),bounds)
    return render_svg(text,bounds,offset,revision,layers,output,region_mm=region,width_px=width_px,source=source)
