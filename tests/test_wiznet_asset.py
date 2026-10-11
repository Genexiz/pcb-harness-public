"""Importer characterizations use hand-authored XML, not manufacturer approval."""
from copy import deepcopy
import xml.etree.ElementTree as ET
import pytest
from pcb_harness.circuit.sexpr import child, children, walk

NAMES = ['GND@1','GND@2','MOSI','MISO','SCLK','SCSN','3V3D@1','3V3D@2',
         '3V3D','RDY','RSTN','NC','INTN','GND']


def xml():
    root=ET.Element('eagle',version='6.5.0'); lib=ET.SubElement(ET.SubElement(root,'drawing'),'library')
    package=ET.SubElement(ET.SubElement(lib,'packages'),'package',name='WIZ550IO_V1.1')
    syms=ET.SubElement(lib,'symbols'); ds=ET.SubElement(ET.SubElement(lib,'devicesets'),'deviceset',name='W550IO_V1.1')
    gates=ET.SubElement(ds,'gates'); device=ET.SubElement(ET.SubElement(ds,'devices'),'device',name='',package='WIZ550IO_V1.1')
    connects=ET.SubElement(device,'connects')
    for gate,size in [(1,8),(2,6)]:
        sn=f'WIZ550IO_V1.1_{gate}'; symbol=ET.SubElement(syms,'symbol',name=sn)
        ET.SubElement(gates,'gate',name=f'G${gate}',symbol=sn,x='0',y='0')
        for j in range(size):
            n=j+1 if gate==1 else j+9; name=NAMES[n-1]
            ET.SubElement(symbol,'pin',name=name,x='0',y=str(-2.54*j),length='short',direction='pas')
            ET.SubElement(package,'pad',name=str(n),x=str(n),y='11.43' if gate==1 else '-11.43',drill='1.016',shape='square' if j==0 else 'octagon')
            ET.SubElement(connects,'connect',gate=f'G${gate}',pin=name,pad=str(n))
    ET.SubElement(package,'wire',x1='-27.5',y1='13',x2='27.5',y2='13',width='0.127',layer='21')
    ET.SubElement(package,'hole',x='-15.1',y='10',drill='3')
    return root


def convert(tree):
    from pcb_harness.orchestration.wiznet_asset import convert_wiz550io
    return convert_wiz550io(ET.tostring(tree))


def test_original_pad_mapping_and_y_flip():
    symbol,fp,metadata=convert(xml())
    pads={p[1]:p for p in children(fp,'pad') if p[1]}
    assert len(pads)==14
    assert child(pads['1'],'at')[1:]==[1.0,-11.43]
    assert child(pads['9'],'at')[1:]==[9.0,11.43]
    assert child(pads['1'],'drill')[1]==1.016
    pins={child(p,'number')[1]:child(p,'name')[1] for p in walk(symbol,'pin')}
    assert pins['3']=='MOSI' and pins['11']=='RSTN' and pins['12']=='NC' and pins['14']=='GND'
    holes=[p for p in children(fp,'pad') if p[2]=='np_thru_hole']
    assert child(holes[0],'at')[1:]==[-15.1,-10.0]
    assert metadata['revision_qualified'] is False
    assert metadata['pad_diameter_source']=='engineering choice; Eagle omitted diameter'


@pytest.mark.parametrize('change',['wrong-map','duplicate-pad','missing-pad','rotation','nonfinite','wrong-package','unsupported-shape','duplicate-connect','entity'])
def test_invalid_or_unsupported_original_is_rejected(change):
    tree=xml(); p=tree.find('.//package'); cs=tree.find('.//connects')
    if change=='wrong-map': cs.find("connect[@pin='MOSI']").set('pad','4')
    elif change=='duplicate-pad': p.append(deepcopy(p.find('pad')))
    elif change=='missing-pad': p.remove(p.find('pad'))
    elif change=='rotation': p.find('pad').set('rot','R90')
    elif change=='nonfinite': p.find('pad').set('x','nan')
    elif change=='wrong-package': tree.find('.//device').set('package','other')
    elif change=='unsupported-shape': p.find('pad').set('shape','long')
    elif change=='duplicate-connect': cs.append(deepcopy(cs.find('connect')))
    if change=='entity':
        from pcb_harness.orchestration.wiznet_asset import convert_wiz550io
        with pytest.raises(ValueError): convert_wiz550io(b'<!DOCTYPE eagle [<!ENTITY x "bad">]>'+ET.tostring(tree))
    else:
        with pytest.raises(ValueError): convert(tree)
