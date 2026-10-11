"""Bounded original Eagle importer, not a module mechanical qualification."""
import hashlib
import math
import xml.etree.ElementTree as ET
from pcb_harness.circuit.sexpr import Atom
from pcb_harness.circuit.writer import node

# Independently checked against WIZnet's J1/J2 manual. J2 maps to pads9..14.
PIN_NAMES = ['GND@1','GND@2','MOSI','MISO','SCLK','SCSN','3V3D@1','3V3D@2',
             '3V3D','RDY','RSTN','NC','INTN','GND']


def number(element, key):
    value = float(element.attrib[key])
    if not math.isfinite(value):
        raise ValueError('nonfinite Eagle geometry')
    return value


def one(elements, message):
    if len(elements) != 1:
        raise ValueError(message)
    return elements[0]


def convert_wiz550io(raw):
    """Keep pad coordinates/drills/wires; explicitly choose missing annulus size.

    Only the calibrated WIZ550io v1.1 subset is supported. Passive pin types
    are retained from Eagle; v1.2 equivalence and socket fit need review.
    """
    if b'<!ENTITY' in raw.upper() or b'<!DOCTYPE' in raw.upper() and b'[' in raw:
        raise ValueError('XML entities/internal DTD are not supported')
    try:
        root = ET.fromstring(raw)
        if root.tag != 'eagle': raise ValueError('not Eagle XML')
        lib = one(root.findall('./drawing/library'), 'ambiguous Eagle library')
        ds = one(lib.findall("./devicesets/deviceset[@name='W550IO_V1.1']"), 'wrong deviceset')
        device = one(ds.findall('./devices/device'), 'ambiguous Eagle device')
        if device.get('package') != 'WIZ550IO_V1.1': raise ValueError('wrong package')
        package = one(lib.findall("./packages/package[@name='WIZ550IO_V1.1']"), 'ambiguous package')
        pads=package.findall('pad'); connects=device.findall('./connects/connect')
        if (len(pads)!=14 or {p.get('name') for p in pads}!={str(i) for i in range(1,15)}
                or len(connects)!=14): raise ValueError('incomplete or duplicate pad mapping')
        gates={g.get('name'):g for g in ds.findall('./gates/gate')}
        if len(gates)!=2 or set(gates)!={'G$1','G$2'}: raise ValueError('unsupported gates')
        expected={(f'G${1 if i<=8 else 2}', name):str(i) for i,name in enumerate(PIN_NAMES,1)}
        actual={(c.get('gate'),c.get('pin')):c.get('pad') for c in connects}
        if len(actual)!=14 or actual!=expected: raise ValueError('manual/header mapping differs')
        for (gate,name),pad in actual.items():
            symbol=one(lib.findall(f"./symbols/symbol[@name='{gates[gate].get('symbol')}']"),'missing gate symbol')
            pin=one([p for p in symbol.findall('pin') if p.get('name')==name],'missing/duplicate symbol pin')
            if pin.get('direction')!='pas': raise ValueError('unsupported pin direction')
        name='WIZ550io_v1_2_candidate'
        effects=lambda:node('effects',node('font',node('size',1.27,1.27)))
        symbol=node('symbol',name,node('pin_names',node('offset',1.016)),node('in_bom',Atom('yes')),node('on_board',Atom('yes')),
                    node('property','Reference','M',node('at',0,13.97,0),effects()),
                    node('property','Value','WIZ550io v1.2 candidate',node('at',0,-13.97,0),effects()),
                    node('property','Footprint','WIZTarget:'+name,node('at',0,0,0),effects(),node('hide',Atom('yes'))))
        body=node('symbol',name+'_0_1',node('rectangle',node('start',-12.7,12.7),node('end',12.7,-12.7),
                   node('stroke',node('width',0.254),node('type',Atom('default'))),node('fill',node('type',Atom('background')))))
        pins=node('symbol',name+'_1_1')
        for i,pname in enumerate(PIN_NAMES,1):
            left=i<=8; row=i-1 if left else i-9
            pins.append(node('pin',Atom('passive'),Atom('line'),node('at',-15.24 if left else 15.24,10.16-row*2.54,0 if left else 180),
                        node('length',2.54),node('name',pname,effects()),node('number',str(i),effects())))
        symbol.extend([body,pins])
        fp=node('footprint',name,node('version',20241229),node('generator','pcb_harness_wiznet_import'),node('layer','F.Cu'),
                node('descr','Original WIZnet v1.1 Eagle coordinates; v1.2 and socket qualification pending'),
                node('attr',Atom('through_hole')),
                node('property','Reference','REF**',node('at',0,-16,0),node('layer','F.SilkS'),effects()),
                node('property','Value','WIZ550io v1.2 candidate',node('at',0,16,0),node('layer','F.Fab'),effects()))
        for p in pads:
            drill=number(p,'drill')
            if p.get('rot','R0')!='R0' or p.get('shape') not in ('square','octagon') or drill<=0:
                raise ValueError('unsupported pad shape/rotation/drill')
            if set(p.attrib)-{'name','x','y','drill','shape','rot'}: raise ValueError('unsupported pad attributes')
            fp.append(node('pad',p.get('name'),Atom('thru_hole'),Atom('rect' if p.get('shape')=='square' else 'circle'),
                      node('at',number(p,'x'),-number(p,'y')),node('size',1.8,1.8),node('drill',drill),node('layers','*.Cu','*.Mask')))
        for hole in package.findall('hole'):
            d=number(hole,'drill')
            if d<=0: raise ValueError('invalid hole drill')
            fp.append(node('pad','',Atom('np_thru_hole'),Atom('circle'),node('at',number(hole,'x'),-number(hole,'y')),
                           node('size',d,d),node('drill',d),node('layers','*.Cu','*.Mask')))
        for wire in package.findall('wire'):
            if wire.get('layer')!='21' or float(wire.get('curve','0'))!=0: raise ValueError('unsupported package wire')
            fp.append(node('fp_line',node('start',number(wire,'x1'),-number(wire,'y1')),node('end',number(wire,'x2'),-number(wire,'y2')),
                           node('stroke',node('width',number(wire,'width')),node('type',Atom('solid'))),node('layer','F.Fab')))
        if any(el.tag not in ('wire','pad','hole','text') for el in package): raise ValueError('unsupported package primitive')
        metadata={'source_sha256':hashlib.sha256(raw).hexdigest(),'original_revision':'WIZ550io v1.1',
                  'target_revision':'WIZ550io v1.2','revision_qualified':False,'pad_diameter_mm':1.8,
                  'pad_diameter_source':'engineering choice; Eagle omitted diameter',
                  'octagon_conversion':'circle inscribed in chosen diameter; land-pattern qualification pending',
                  'mechanical_qualified':False,'pin_type_source':'Eagle passive types; electrical semantics unqualified'}
        return symbol,fp,metadata
    except (KeyError,TypeError,ET.ParseError,OverflowError) as error:
        raise ValueError('invalid calibrated Eagle input') from error
