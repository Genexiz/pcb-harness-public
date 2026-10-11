"""Review-only real-target schematic; unresolved evidence never admits layout."""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
import io
from pathlib import Path
import re

from pcb_harness.circuit.assets import load_part_assets
from pcb_harness.circuit.bundle import read_json, resolve_local, sha256, validate_document
from pcb_harness.circuit.sexpr import Atom, child, children, dump_sexpr, parse_sexpr, walk
from pcb_harness.circuit.symbols import flatten_symbol
from pcb_harness.circuit.writer import build_review_schematic, node, output_path, stable_uuid
from pcb_harness.orchestration.core_assets import LICENSE, write_json
from pcb_harness.orchestration.core_pin_evidence import verify_pin_evidence
from pcb_harness.orchestration.wiznet_asset import convert_wiz550io

BLOCKERS=['CRITICAL_FACT_CONFIRMATION','ST_ORIGINAL_SOURCES','EXACT_SUPPORT_MPN_QUALIFICATION',
          'MODULE_REVISION_SOCKET_MECHANICS','USB_UNPOWERED_ATTACH_INJECTION',
          'INPUT_AND_HEADER_PROTECTION','FULL_FIRMWARE_TIMING','POWER_THERMAL',
          'SILICON_ERRATA','INDEPENDENT_FUNCTIONAL_CIRCUIT_REVIEW','NATIVE_ACCEPTED_BOOTSTRAP',
          'FABRICATION_SERVICE_PROFILE','LICENSE_REVIEW']


def compile_topology(topology, parts, checks):
    """Strict pin assignment and independent literal critical-connection checks.

    This proves the authored candidate topology, not manufacturer semantics.
    Every physical pin must have an explicit net or explicit NC; missing pins
    never become a quiet default NC.
    """
    refs=[i['ref'] for i in topology['instances']]
    if len(set(refs))!=len(refs) or set(refs)!=set(checks['required_refs']):
        raise ValueError('incomplete or duplicate candidate inventory')
    by_ref={i['ref']:i for i in topology['instances']}
    for ref, expected in checks['pin_nets'].items():
        if ref not in by_ref or any(by_ref[ref]['pins'].get(p)!=net for p,net in expected.items()):
            raise ValueError(f'independent critical pin expectation differs: {ref}')
    for ref,value in checks['values'].items():
        if by_ref.get(ref,{}).get('value')!=value:
            raise ValueError(f'independent support value differs: {ref}')
    for ref, numbers in checks['no_connect'].items():
        if {n for n,net in by_ref[ref]['pins'].items() if net is None}!=set(numbers):
            raise ValueError(f'independent NC differs: {ref}')
    for pair in checks['isolated_nets']:
        if len(pair)!=2 or pair[0]==pair[1]: raise ValueError('invalid isolation contract')
    # Reject zero-ohm/inductor/explicitly closed jumper rail bridges. This is
    # not an off-state injection or nonlinear transistor/ESD simulation.
    graph={}
    for instance in topology['instances']:
        zero_resistor = re.fullmatch(r'R[0-9]+',instance['ref']) and instance['value'].lower() in ('0','0r','0ohm')
        inductor = re.fullmatch(r'L[0-9]+',instance['ref'])
        closed_jumper = re.fullmatch(r'JP[0-9]+',instance['ref']) and instance.get('state') == 'closed'
        if zero_resistor or inductor or closed_jumper:
            values=[n for n in instance['pins'].values() if n is not None]
            if len(values)==2:
                a,b=values
                graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
    for a,b in checks['isolated_nets']:
        visited=set();pending=[a]
        while pending:
            n=pending.pop()
            if n in visited:continue
            visited.add(n);pending.extend(graph.get(n,set())-visited)
        if b in visited:raise ValueError('forbidden passive rail bridge')
    instances,nets,nc=[],{},[]
    for i,instance in enumerate(topology['instances']):
        part=parts.get(instance['part_id'])
        if part is None: raise ValueError('unknown candidate part')
        if (not re.fullmatch(r'[A-Z]+[0-9]+',instance['ref'])
                or set(instance['pins'])!={p['number'] for p in part['pins']}):
            raise ValueError('missing or unknown explicitly assigned pin')
        # Grid is only a serialization placeholder, never a floorplan/placement.
        instances.append({'id':instance['ref'],'ref':instance['ref'],'part_id':instance['part_id'],
            'value':instance['value'],'block':instance['block'],'fact_ids':[],
            'schematic_position_mm':instance['schematic_position_mm'],'bootstrap_position_mm':[15+i%15*6,15+i//15*6]})
        for pin in part['pins']:
            endpoint={'instance_id':instance['ref'],'pin_id':pin['id']}
            net=instance['pins'][pin['number']]
            if net is None:
                nc.append({**endpoint,'reason':'Explicit candidate NC; independent source qualification pending',
                           'fact_id':'engineering-topology'})
            else:
                if not isinstance(net,str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+',net): raise ValueError('unsafe candidate net')
                if net not in nets:
                    voltage={'GND':[0,0],'3V3':[3.135,3.465],'5V':[4.75,5.25]}.get(net)
                    nets[net]={'id':net,'name':'/'+net,'net_class':'Default','voltage_range_v':voltage,'endpoints':[]}
                nets[net]['endpoints'].append(endpoint)
    circuit={'schema_version':1,'id':topology['id'],'revision':topology['revision'],'instances':instances,
             'nets':list(nets.values()),'no_connect':nc,'interfaces':deepcopy(topology['interfaces']),'errata_mitigations':[]}
    validate_document('circuit',circuit)
    valid={(i['id'],p['id']) for i in instances for p in parts[i['part_id']]['pins']}
    allocated=set()
    for interface in circuit['interfaces']:
        for pin in interface['pin_ids']:
            key=(interface['instance_id'],pin)
            if key not in valid or key in allocated: raise ValueError('invalid/duplicate interface allocation')
            allocated.add(key)
    return circuit


def candidate_metadata(name, symbol, footprint, mpn, manufacturer='unselected', license=LICENSE):
    symbol_id='SupportTarget:'+name
    footprint[1]=name
    fp_path=f'assets/SupportTarget.pretty/{name}.kicad_mod'
    footprint_hash=hashlib.sha256((dump_sexpr(footprint)+'\n').encode()).hexdigest()
    pins=[{'id':'p'+str(child(p,'number')[1]),'number':str(child(p,'number')[1]),'name':str(child(p,'name')[1]),
           'type':str(p[1]),'operating_range_v':None,'operating_fact_id':None,'absolute_maximum_fact_id':None} for p in walk(symbol,'pin')]
    return {'id':name,'mpn':mpn,'manufacturer':manufacturer,'package':name+' candidate template',
        'revision':'unqualified-candidate','lifecycle':'unknown','symbol_id':symbol_id,'footprint_id':'SupportTarget:'+name,
        'symbol':{'path':'assets/SupportTarget.kicad_sym','sha256':'0'*64,'license':license},
        'footprint':{'path':fp_path,'sha256':footprint_hash,'license':license},'pins':pins,
        'pin_map':[{'pin_id':p['id'],'symbol_pin':p['number'],'pads':[p['number']]} for p in pins],
        'fact_ids':[],'required_fact_ids':[name+':pinout',name+':qualification'],'errata_fact_ids':[]}


def freeze_tree(source, destination, manifest):
    for relative in [*manifest, 'integrity.json']:
        raw=resolve_local(source,relative).read_bytes()
        if relative!='integrity.json' and hashlib.sha256(raw).hexdigest()!=manifest[relative]: raise ValueError('source changed during capture')
        target=resolve_local(destination,relative);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)


def support_evidence(root, top, *, check_libraries=True):
    packet=root/'inputs/support-completion'
    selected=any(s.get('qualification')=='source_reviewed' for s in top['support_types'].values())
    if not packet.exists():
        if selected:raise ValueError('source-reviewed support requires a frozen support packet')
        return None,{}
    from .support_qualification import verify_support, support_asset_bytes
    evidence=verify_support(packet)
    expected=deepcopy(evidence['topology'])
    if (root/'inputs/source-completion').exists():
        from .source_completion import load_source_completion
        patch=load_source_completion(root/'inputs/source-completion')['rs232_correction']['topology_value_patch']
        next(i for i in expected['instances'] if i['ref']==patch['ref'])['value']=patch['value']
    if json.dumps(top,sort_keys=True)!=json.dumps(expected,sort_keys=True):
        raise ValueError('source-reviewed support topology differs from frozen derivation')
    overlay=support_asset_bytes(packet)
    if check_libraries:
        for relative,blob in overlay.items():
            if resolve_local(root/'inputs/libraries',relative).read_bytes()!=blob:
                raise ValueError('source-reviewed support library overlay differs')
    return evidence,overlay


def asset_derivatives(root, top):
    support_evidence(root,top)
    core=root/'inputs/pins/inputs/core'
    parts=deepcopy(read_json(core/'parts.json')['parts'])
    expected={}
    for p in parts:
        for kind in ['symbol','footprint']:
            rel=p[kind]['path'];expected[rel]=resolve_local(core,rel).read_bytes()
    if top.get('sdo_model') is not None:
        from .candidate_models import apply_sdo_models
        expected.update(apply_sdo_models(root,parts,top['sdo_model']))
    completion=root/'inputs/source-completion'
    if completion.exists():
        from .source_completion import apply_source_completion
        parts,expected,evidence=apply_source_completion(completion,parts,expected)
        patch=evidence['rs232_correction']['topology_value_patch']
        target=[i for i in top['instances'] if i['ref']==patch['ref']]
        if len(target)!=1 or target[0]['value']!=patch['value']:
            raise ValueError('source correction topology Value differs')
    symbols=[]
    for name,spec in top['support_types'].items():
        ns,symname=spec['symbol_template'].split(':');fpns,fpname=spec['footprint_template'].split(':')
        library=parse_sexpr(resolve_local(root/'inputs/libraries',f'symbols/{ns}.kicad_sym').read_text())
        symbol=flatten_symbol(library,symname,name,{'Value':spec['mpn'],'Footprint':'SupportTarget:'+name,
                                                 'Description':'UNCONFIRMED SUPPORT CANDIDATE'})
        fp=parse_sexpr(resolve_local(root/'inputs/libraries',f'footprints/{fpns}.pretty/{fpname}.kicad_mod').read_text())
        if fp[0]!='footprint' or fp[1]!=fpname: raise ValueError('source footprint identity differs')
        symbols.append(symbol);p=candidate_metadata(name,symbol,fp,spec['mpn'],spec.get('manufacturer','unselected'));parts.append(p)
        if spec.get('qualification')=='source_reviewed':
            p['package']=spec['footprint_template'].split(':')[1]
            p['revision']='source-reviewed-candidate'
        expected[p['footprint']['path']]=(dump_sexpr(fp)+'\n').encode()
    raw=resolve_local(root,'inputs/wiz550io.lbr').read_bytes()
    meta=read_json(resolve_local(root,'inputs/module-source.json'))
    if (meta.get('sha256')!=hashlib.sha256(raw).hexdigest()
            or meta.get('url')!='https://docs.wiznet.io/assets/files/wiz550io_v1.1-a5a559d2996452483d50f64d5eb708bd.zip'
            or meta.get('archive_member')!='WIZ550io_V1.1.lbr' or meta.get('human_confirmed') is not False):
        raise ValueError('unbound manufacturer module source')
    sym,fp,module_import=convert_wiz550io(raw)
    for prop in children(sym,'property'):
        if prop[1]=='Footprint':prop[2]='SupportTarget:WIZ550io_v1_2_candidate'
    symbols.append(sym)
    p=candidate_metadata('WIZ550io_v1_2_candidate',sym,fp,'WIZ550io v1.2','WIZnet',
                         'Manufacturer Eagle library; redistribution permission unknown')
    parts.append(p);expected[p['footprint']['path']]=(dump_sexpr(fp)+'\n').encode()
    lib_path='assets/SupportTarget.kicad_sym'
    expected[lib_path]=(dump_sexpr(node('kicad_symbol_lib',node('version',20250114),
                         node('generator','pcb_harness_review_candidate'),*symbols))+'\n').encode()
    for p in parts:
        if p['symbol']['path']==lib_path:p['symbol']['sha256']=hashlib.sha256(expected[lib_path]).hexdigest()
    return parts,expected,module_import


def review_tree(bundle,checks,root):
    tree=build_review_schematic(bundle,root)
    if checks.get('supply_markers'):
        from .candidate_models import add_supply_markers
        add_supply_markers(tree,bundle['circuit'],checks['supply_markers'])
    tree[:]=[n for n in tree if not isinstance(n,list) or n[0]!='text']
    for block,(x,y) in checks['section_titles'].items():
        tree.append(node('text',block.upper()+' - CANDIDATE',node('at',x,y,0),
                         node('effects',node('font',node('size',2,2)),node('justify',Atom('left'))),
                         node('uuid',stable_uuid(bundle['circuit']['id'],'section/'+block))))
    return dump_sexpr(tree)+'\n'


def bom_text(topology,circuit,parts):
    stream=io.StringIO(newline='');w=csv.writer(stream)
    w.writerow(['Reference','Value / engineering target','Candidate MPN or unselected type','Footprint template','Qualification','Engineering notes'])
    authored={i['ref']:i for i in topology['instances']}
    part_map={p['id']:p for p in parts}
    for i in circuit['instances']:
        p=part_map[i['part_id']];w.writerow([i['ref'],i['value'],p['mpn'],p['footprint_id'],
            'UNCONFIRMED - DO NOT ORDER',authored[i['ref']].get('qualification_note','')])
    return stream.getvalue()


def library_tables(parts, *, supply_annotations=False):
    tables={'board.kicad_pro':(json.dumps({'meta':{'filename':'board.kicad_pro','version':1}},indent=2)+'\n').encode()}
    for filename,kind,field in [('sym-lib-table','sym_lib_table','symbol'),('fp-lib-table','fp_lib_table','footprint')]:
        entries={}
        for p in parts:
            ns=p[field+'_id'].split(':')[0]
            path=p[field]['path'] if field=='symbol' else str(Path(p[field]['path']).parent)
            if ns in entries and entries[ns]!=path:raise ValueError('conflicting local candidate library')
            entries[ns]=path
        if field=='symbol' and supply_annotations:
            from .candidate_models import supply_symbol
            path='assets/HarnessAnnotations.kicad_sym'
            library=node('kicad_symbol_lib',node('version',20250114),node('generator','pcb_harness_annotations'),supply_symbol())
            tables[path]=(dump_sexpr(library)+'\n').encode()
            entries['HarnessAnnotations']=path
        table=node(kind,node('version',7))
        for ns,path in entries.items():
            table.append(node('lib',node('name',ns),node('type','KiCad'),node('uri','${KIPRJMOD}/'+path),
                              node('options',''),node('descr','UNCONFIRMED review candidate')))
        tables[filename]=(dump_sexpr(table)+'\n').encode()
    return tables


def report_for(root,topology,parts,circuit):
    missing=sorted({p['mpn'] for p in parts if p['mpn'].startswith('UNSELECTED-')})
    report={'schema_version':1,'scope':'review-only schematic; no PCB or bootstrap',
            'instances':len(circuit['instances']),'part_types':len(parts),'nets':len(circuit['nets']),
            'interfaces':sorted(i['id'] for i in circuit['interfaces']), 'explicit_no_connect':len(circuit['no_connect']),
            'unselected_support_types':missing,'human_confirmed':False,'layout_allowed':False,
            'release_eligible':False,'milestone_complete':False,'accepted_real_target_assets':0,
            'structural_topology_checks_passed':True,'independent_functional_acceptance':False,
            'module_source':read_json(resolve_local(root,'inputs/module-source.json')),
            'blockers':list(BLOCKERS),
            'limits':['Native schematic readability/netlist is separately verified; no clean ERC/bootstrap claim from serialization.',
                      'Support values are explicit engineering targets; exact purchasing parts/effective ratings remain unqualified.',
                      'Core required facts and MCU errata are retained; review serialization does not admit write_project.']}
    if (root/'inputs/source-completion').exists():
        from .source_completion import load_source_completion
        report['source_completion']=load_source_completion(root/'inputs/source-completion')['report']
        report['blockers'].remove('ST_ORIGINAL_SOURCES')
    support,_=support_evidence(root,topology)
    if support is not None:
        report['support_completion']={'source_count':len(support['sources_verified']),
            'selected_part_types':len(support['catalog']['parts']),
            'human_confirmed':False,'hardware_verified':False,
            'firmware_requirements':support['firmware_requirements']}
    return report


def prepare_review(topology_path, checks_path, pin_packet, library_root, eagle_path, module_source, output, *, source_completion=None, support_completion=None):
    topology_path=Path(topology_path).absolute();output=output_path(topology_path.parent,output)
    pin_packet=Path(pin_packet).absolute();verify_pin_evidence(pin_packet)
    top=read_json(topology_path);checks=read_json(checks_path);meta=read_json(module_source)
    if (top.get('human_confirmed') is not False or top.get('layout_allowed') is not False
            or type(top.get('schema_version')) is not int or top['schema_version']!=1): raise ValueError('invalid candidate status')
    raw=resolve_local(Path(eagle_path).absolute().parent,Path(eagle_path).name).read_bytes()
    if (meta.get('sha256')!=hashlib.sha256(raw).hexdigest()
            or meta.get('url')!='https://docs.wiznet.io/assets/files/wiz550io_v1.1-a5a559d2996452483d50f64d5eb708bd.zip'
            or meta.get('archive_member')!='WIZ550io_V1.1.lbr' or meta.get('human_confirmed') is not False):
        raise ValueError('unbound manufacturer module source')
    module_symbol,module_fp,module_import=convert_wiz550io(raw)
    overlay={}
    if support_completion is not None:
        from .support_qualification import verify_support, support_asset_bytes
        support_completion=Path(support_completion).absolute()
        verify_support(support_completion)
        overlay=support_asset_bytes(support_completion)
    # Capture all library inputs before deriving assets, never read live sources later.
    library_root=Path(library_root).absolute();blobs={}
    for spec in top['support_types'].values():
        if spec.get('qualification') not in ('unconfirmed','source_reviewed'): raise ValueError('unsupported support qualification')
        if spec.get('qualification')=='source_reviewed' and support_completion is None:
            raise ValueError('source-reviewed support requires a frozen support packet')
        for key,folder,extension in [('symbol_template','symbols','.kicad_sym'),('footprint_template','footprints','.kicad_mod')]:
            identifier=spec[key]
            if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.]*:[A-Za-z0-9_][A-Za-z0-9_.+-]*',identifier): raise ValueError('unsafe asset template')
            ns,name=identifier.split(':');path=f'{folder}/{ns}{extension}' if folder=='symbols' else f'{folder}/{ns}.pretty/{name}{extension}'
            if path not in blobs:blobs[path]=overlay[path] if path in overlay else resolve_local(library_root,path).read_bytes()
    blobs.update(overlay)
    output.mkdir(parents=True,exist_ok=False)
    for relative,value in [('inputs/topology.json',top),('inputs/checks.json',checks),('inputs/module-source.json',meta),('module-import.json',module_import)]:
        p=resolve_local(output,relative);p.parent.mkdir(parents=True,exist_ok=True);write_json(p,value)
    (output/'inputs/wiz550io.lbr').write_bytes(raw)
    freeze_tree(pin_packet,output/'inputs/pins',read_json(pin_packet/'integrity.json')['artifacts'])
    if source_completion is not None:
        from .source_completion import verify_source_completion
        source_completion=Path(source_completion).absolute()
        verify_source_completion(source_completion)
        freeze_tree(source_completion,output/'inputs/source-completion',read_json(source_completion/'integrity.json')['artifacts'])
    if support_completion is not None:
        freeze_tree(support_completion,output/'inputs/support-completion',read_json(support_completion/'integrity.json')['artifacts'])
    core=output/'inputs/pins/inputs/core';core_parts=read_json(core/'parts.json')['parts']
    for p in core_parts:
        for kind in ['symbol','footprint']:
            relative=p[kind]['path'];target=resolve_local(output,relative);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(resolve_local(core,relative).read_bytes())
    for relative,blob in blobs.items():
        p=resolve_local(output/'inputs/libraries',relative);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob)
    parts,derived_assets,module_import=asset_derivatives(output,top)
    derived_assets.update(library_tables(parts,supply_annotations=bool(checks.get('supply_markers'))))
    for relative,blob in derived_assets.items():
        target=resolve_local(output,relative);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
    write_json(output/'module-import.json',module_import)
    for p in parts:load_part_assets(p,output)
    part_map={p['id']:p for p in parts};circuit=compile_topology(top,part_map,checks)
    bundle={'parts':{'schema_version':1,'parts':parts},'circuit':circuit}
    write_json(output/'parts.json',bundle['parts']);write_json(output/'circuit.json',circuit)
    (output/'board.kicad_sch').write_text(review_tree(bundle,checks,output))
    (output/'candidate-bom.csv').write_text(bom_text(top,circuit,parts),newline='')
    report=report_for(output,top,parts,circuit);write_json(output/'report.json',report)
    artifacts={str(p.relative_to(output)):sha256(p) for p in output.rglob('*') if p.is_file()}
    write_json(output/'integrity.json',{'schema_version':1,'artifacts':artifacts})
    verify_review(output)
    return report


def _verify_review_inputs(root):
    root=Path(root).absolute();manifest=read_json(resolve_local(root,'integrity.json'))
    required={'board.kicad_sch','parts.json','circuit.json','candidate-bom.csv','report.json','module-import.json',
              'inputs/topology.json','inputs/checks.json','inputs/module-source.json','inputs/wiz550io.lbr','inputs/pins/integrity.json'}
    if type(manifest.get('schema_version')) is not int or manifest['schema_version']!=1 or not required<=set(manifest['artifacts']):
        raise ValueError('incomplete candidate evidence')
    for relative,digest in manifest['artifacts'].items():
        if sha256(resolve_local(root,relative))!=digest:raise ValueError('candidate artifact drift: '+relative)
    verify_pin_evidence(root/'inputs/pins')
    if (root/'inputs/source-completion').exists():
        from .source_completion import verify_source_completion
        verify_source_completion(root/'inputs/source-completion')
        source_artifacts=read_json(root/'inputs/source-completion/integrity.json')['artifacts']
        required.update('inputs/source-completion/'+r for r in [*source_artifacts,'integrity.json'])
        if not required<=set(manifest['artifacts']):raise ValueError('incomplete source completion capture')
    if (root/'inputs/support-completion').exists():
        support_artifacts=read_json(root/'inputs/support-completion/integrity.json')['artifacts']
        required.update('inputs/support-completion/'+r for r in [*support_artifacts,'integrity.json'])
        if not required<=set(manifest['artifacts']):raise ValueError('incomplete support completion capture')
    top=read_json(root/'inputs/topology.json');checks=read_json(root/'inputs/checks.json')
    parts,assets,module_import=asset_derivatives(root,top)
    assets.update(library_tables(parts,supply_annotations=bool(checks.get('supply_markers'))))
    required.update(assets)
    if not required<=set(manifest['artifacts']):raise ValueError('incomplete candidate asset manifest')
    for relative,blob in assets.items():
        if resolve_local(root,relative).read_bytes()!=blob:raise ValueError('candidate asset differs from frozen source')
    circuit=compile_topology(top,{p['id']:p for p in parts},checks)
    for file,expected in [('parts.json',{'schema_version':1,'parts':parts}),('circuit.json',circuit),
                          ('module-import.json',module_import),('report.json',report_for(root,top,parts,circuit))]:
        if json.dumps(read_json(root/file),sort_keys=True)!=json.dumps(expected,sort_keys=True):raise ValueError('candidate derivative differs: '+file)
    bundle={'parts':{'schema_version':1,'parts':parts},'circuit':circuit}
    if (resolve_local(root,'board.kicad_sch').read_text()!=review_tree(bundle,checks,root)
            or resolve_local(root,'candidate-bom.csv').read_bytes()!=bom_text(top,circuit,parts).encode()):
        raise ValueError('candidate schematic/BOM differs from frozen topology')
    return True


def verify_review(root):
    root=Path(root).absolute()
    _verify_review_inputs(root)
    if (root/'native-summary.json').exists() or (root/'native').exists():
        from pcb_harness.orchestration.native_candidate import verify_native_review
        verify_native_review(root)
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--topology',default='benchmarks/stm32-communications/candidate-topology.json')
    p.add_argument('--checks',default='checklists/stm32-communications/candidate-circuit.json')
    p.add_argument('--pins',required=True);p.add_argument('--library-root',default='/Applications/KiCad/KiCad.app/Contents/SharedSupport')
    p.add_argument('--eagle',required=True);p.add_argument('--module-source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--source-completion',help='Verified recovered original-source packet; remains unconfirmed')
    p.add_argument('--support-completion',help='Verified exact support source and topology packet')
    a=p.parse_args();r=prepare_review(a.topology,a.checks,a.pins,a.library_root,a.eagle,a.module_source,a.output,source_completion=a.source_completion,support_completion=a.support_completion)
    print(json.dumps(r));return 2


if __name__=='__main__':raise SystemExit(main())
