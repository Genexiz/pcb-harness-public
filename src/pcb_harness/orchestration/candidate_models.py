"""Explicit source-reviewed schematic models; never human confirmation."""
from copy import deepcopy
import hashlib
from pcb_harness.circuit.bundle import resolve_local
from pcb_harness.circuit.sexpr import Atom,children,child,walk,parse_sexpr,dump_sexpr
from pcb_harness.circuit.writer import node,stable_uuid

SDO_SHA='0041b5bddb2a341794958f7a3195b931b349eb863f685935bb80aee377661ff5'


def apply_sdo_models(root,parts,settings):
    """MCP2518FD pin12 SDO: Table7-6 p81 CS2SDOZ explicitly specifies HighZ."""
    if settings!={'enabled':True,'source_sha256':SDO_SHA} or settings.get('enabled') is not True:
        raise ValueError('SDO model requires calibrated original DS20006027B source')
    source=resolve_local(root,'inputs/pins/sources/mcp2518fd.pdf').read_bytes()
    if hashlib.sha256(source).hexdigest()!=SDO_SHA:raise ValueError('SDO original source hash differs')
    chosen=[p for p in parts if p['mpn']=='MCP2518FD-E/SL']
    if len(chosen)!=1:raise ValueError('SDO model has ambiguous target part')
    part=chosen[0];relative=part['symbol']['path']
    raw=resolve_local(root/'inputs/pins/inputs/core',relative).read_bytes()
    library=parse_sexpr(raw.decode())
    symbol=next(s for s in children(library,'symbol') if s[1]==part['symbol_id'].split(':')[1])
    pins=[p for p in walk(symbol,'pin') if child(p,'number')[1]=='12']
    declared=[p for p in part['pins'] if p['number']=='12']
    if len(pins)!=1 or len(declared)!=1 or pins[0][1]!='output' or declared[0]['type']!='output' or declared[0]['name']!='SDO':
        raise ValueError('SDO original symbol/declaration is not the calibrated pin12 output')
    pins[0][1]=Atom('tri_state');declared[0]['type']='tri_state'
    part['required_fact_ids'].append(part['id']+':sdo-high-z')
    blob=(dump_sexpr(library)+'\n').encode();digest=hashlib.sha256(blob).hexdigest()
    for p in parts:
        if p['symbol']['path']==relative:p['symbol']['sha256']=digest
    return {relative:blob}



def sdo_fact():
    """Unconfirmed record for the SDO retyping applied by apply_sdo_models."""
    return {'id': 'MCP2518FD-E_SL:sdo-high-z', 'document_id': 'mcp2518fd', 'document_sha256': SDO_SHA,
            'locator': 'DS20006027B Table 7-6 p81 (CS2SDOZ)',
            'claim': 'MCP2518FD SDO (pin 12) is high impedance while nCS is high (CS2SDOZ); '
                     'justifies tri_state pin type on the shared SPI bus. Agent source review; not re-read by a person.',
            'status': 'unconfirmed', 'critical': True, 'value': None, 'units': None,
            'kind': 'operating', 'confirmation': None}

def supply_symbol():
    effects=lambda:node('effects',node('font',node('size',1,1)))
    return node('symbol','SUPPLY_FLAG',node('power'),node('in_bom',Atom('no')),node('on_board',Atom('no')),
        node('property','Reference','#FLG',node('at',0,3,0),effects(),node('hide',Atom('yes'))),
        node('property','Value','SUPPLY_DRIVE',node('at',0,3,0),effects()),
        node('symbol','SUPPLY_FLAG_0_1',node('polyline',node('pts',node('xy',0,0),node('xy',0,1.27),node('xy',-1.27,2.54),node('xy',1.27,2.54),node('xy',0,1.27)),
             node('stroke',node('width',0),node('type',Atom('default'))),node('fill',node('type',Atom('none'))))),
        node('symbol','SUPPLY_FLAG_1_1',node('pin',Atom('power_out'),Atom('line'),node('at',0,0,90),node('length',0),
             node('name','SUPPLY',effects()),node('number','1',effects()))))


def add_supply_markers(tree,circuit,markers):
    nets={n['name'] for n in circuit['nets']};used=set()
    symbol=supply_symbol();symbol[1]='HarnessAnnotations:SUPPLY_FLAG'
    child(tree,'lib_symbols').append(symbol)
    sheet=child(tree,'uuid')[1]
    for i,m in enumerate(markers,1):
        if set(m)!={'net','at','basis'} or m['net'] not in nets or m['net'] in used or not m['basis']:
            raise ValueError('invalid explicit supply-drive declaration')
        used.add(m['net']);x,y=m['at'];uid=lambda key:stable_uuid(circuit['id'],'supply/'+m['net']+'/'+key)
        effects=node('effects',node('font',node('size',1,1)))
        marker=node('symbol',node('lib_id','HarnessAnnotations:SUPPLY_FLAG'),node('at',x,y,0),node('unit',1),
                    node('in_bom',Atom('no')),node('on_board',Atom('no')),node('dnp',Atom('no')),node('uuid',uid('symbol')),
                    node('property','Reference',f'#FLG{i:03d}',node('at',x,y-4,0),deepcopy(effects),node('hide',Atom('yes'))),
                    node('property','Value','SUPPLY_DRIVE',node('at',x,y-4,0),deepcopy(effects)),
                    node('pin','1',node('uuid',uid('pin'))),
                    node('instances',node('project','board',node('path','/'+sheet,node('reference',f'#FLG{i:03d}'),node('unit',1)))))
        tree.append(marker)
        tree.append(node('label',m['net'][1:],node('at',x,y,0),deepcopy(effects),node('uuid',uid('label'))))
