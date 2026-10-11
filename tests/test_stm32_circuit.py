from copy import deepcopy
import pytest


def fixture():
    # Literal oracle: controllerTX links to PHYTXD; RXD links to controllerRX.
    parts={'controller':{'pins':[{'id':'p1','number':'1'},{'id':'p2','number':'2'},{'id':'p3','number':'3'}]},
           'phy':{'pins':[{'id':'p1','number':'1'},{'id':'p4','number':'4'}]}}
    topology={'id':'synthetic-tests','revision':'1','instances':[
        {'ref':'U2','part_id':'controller','value':'controller','block':'can','pins':{'1':'CAN_TX','2':'CAN_RX','3':None},'schematic_position_mm':[50,50]},
        {'ref':'U4','part_id':'phy','value':'phy','block':'can','pins':{'1':'CAN_TX','4':'CAN_RX'},'schematic_position_mm':[100,50]}], 'interfaces':[]}
    checks={'required_refs':['U2','U4'],'pin_nets':{'U2':{'1':'CAN_TX','2':'CAN_RX'},'U4':{'1':'CAN_TX','4':'CAN_RX'}},
            'values':{},'no_connect':{'U2':['3']},'isolated_nets':[['USB_VBUS','5V'],['USB_VBUS','3V3']]}
    return topology,parts,checks


def compile(case):
    from pcb_harness.orchestration.stm32_circuit import compile_topology
    return compile_topology(*case)


def test_explicit_connections_and_nc_remain_distinct():
    c=compile(fixture())
    assert {n['name'] for n in c['nets']}=={'/CAN_TX','/CAN_RX'}
    assert c['nets'][0]['endpoints']==[{'instance_id':'U2','pin_id':'p1'},{'instance_id':'U4','pin_id':'p1'}]
    assert c['no_connect'][0]['instance_id']=='U2' and c['no_connect'][0]['pin_id']=='p3'


@pytest.mark.parametrize('change',['unassigned','unknown-pin','duplicate-ref','absent-required','wrong-tx','hidden-nc','wrong-value','backfeed','unknown-part'])
def test_semantically_invalid_candidates_do_not_emit_schematic(change):
    top,parts,checks=fixture(); u2=top['instances'][0]
    if change=='unassigned': del u2['pins']['3']
    elif change=='unknown-pin': u2['pins']['99']='CAN_TX'
    elif change=='duplicate-ref': top['instances'].append(deepcopy(u2))
    elif change=='absent-required': top['instances'].pop()
    elif change=='wrong-tx': top['instances'][1]['pins']['1']='CAN_RX'
    elif change=='hidden-nc': u2['pins']['2']=None
    elif change=='wrong-value': checks['values']['U2']='specified-other-value'
    elif change=='backfeed': u2['pins']['1']='USB_VBUS';top['instances'][1]['pins']['1']='5V';checks['pin_nets']['U4']['1']='USB_VBUS'
    elif change=='unknown-part': u2['part_id']='absent'
    with pytest.raises(ValueError): compile((top,parts,checks))

from pathlib import Path
import json
from pcb_harness.circuit.bundle import read_json,sha256
from test_core_asset_preparation import candidate_case
from test_core_pin_evidence import pin_case
from test_wiznet_asset import xml
import xml.etree.ElementTree as ET


@pytest.fixture
def review_case(pin_case,tmp_path):
    from pcb_harness.orchestration.core_pin_evidence import prepare_pin_evidence
    prepare_pin_evidence(*pin_case)
    inputs=tmp_path/'draft-inputs';inputs.mkdir();libs=tmp_path/'support-library'
    (libs/'symbols').mkdir(parents=True);(libs/'footprints/Test1.0.pretty').mkdir(parents=True)
    (libs/'symbols/Test1.0.kicad_sym').write_text('''(kicad_symbol_lib (version 20250114)
      (symbol "Resistor" (in_bom yes) (on_board yes) (property "Value" "R" (at 0 2 0))
       (symbol "Resistor_0_1" (rectangle (start -1 -1) (end 1 1)))
       (symbol "Resistor_1_1" (pin passive line (at -2 0 0) (length 1) (name "1") (number "1"))
        (pin passive line (at 2 0 180) (length 1) (name "2") (number "2")))))''')
    (libs/'footprints/Test1.0.pretty/Resistor.kicad_mod').write_text('''(footprint "Resistor"
      (pad "1" smd rect (at -1 0) (size 1 1) (layers "F.Cu"))
      (pad "2" smd rect (at 1 0) (size 1 1) (layers "F.Cu")))''')
    top={'schema_version':1,'id':'synthetic-review','revision':'1','human_confirmed':False,'layout_allowed':False,
         'support_types':{'Rtype':{'symbol_template':'Test1.0:Resistor','footprint_template':'Test1.0:Resistor','mpn':'UNSELECTED-R','qualification':'unconfirmed'}},
         'instances':[{'ref':'U1','part_id':'STM32F103C8T6','value':'MCU','block':'test','pins':{'1':'A','2':'B'},'schematic_position_mm':[40,40]},
                      {'ref':'R1','part_id':'Rtype','value':'10k','block':'test','pins':{'1':'A','2':'B'},'schematic_position_mm':[70,40]},
                      {'ref':'M1','part_id':'WIZ550io_v1_2_candidate','value':'module','block':'test','pins':{str(i):None if i==12 else 'A' for i in range(1,15)},'schematic_position_mm':[100,40]}],
         'interfaces':[]}
    checks={'required_refs':['U1','R1','M1'],'pin_nets':{'U1':{'1':'A','2':'B'}},'no_connect':{'M1':['12']},'values':{'R1':'10k'},'isolated_nets':[],'section_titles':{'test':[10,10]}}
    for file,value in [('topology.json',top),('checks.json',checks)]: (inputs/file).write_text(json.dumps(value))
    raw=ET.tostring(xml());(inputs/'module.lbr').write_bytes(raw)
    meta={'url':'https://docs.wiznet.io/assets/files/wiz550io_v1.1-a5a559d2996452483d50f64d5eb708bd.zip',
          'sha256':sha256(inputs/'module.lbr'),'archive_member':'WIZ550io_V1.1.lbr','human_confirmed':False}
    (inputs/'source.json').write_text(json.dumps(meta))
    return inputs/'topology.json',inputs/'checks.json',pin_case[-1],libs,inputs/'module.lbr',inputs/'source.json',tmp_path/'runs/review'


def test_real_producer_keeps_pending_gates_and_never_exports_pcb(review_case):
    from pcb_harness.orchestration.stm32_circuit import prepare_review,verify_review
    r=prepare_review(*review_case);root=review_case[-1]
    assert r['instances']==3 and r['accepted_real_target_assets']==0
    assert not r['layout_allowed'] and not r['milestone_complete']
    assert not (root/'board.kicad_pcb').exists() and not (root/'bootstrap-manifest.json').exists()
    assert verify_review(root)
    assert 'UNCONFIRMED - DO NOT ORDER' in (root/'candidate-bom.csv').read_text()


@pytest.mark.parametrize('change',['schematic','bom','module-provenance','module-import','support-mpn','core-mpn','report','required-manifest'])
def test_refreshed_hash_does_not_admit_forged_candidate_derivatives(review_case,change):
    from pcb_harness.orchestration.stm32_circuit import prepare_review,verify_review
    prepare_review(*review_case);r=review_case[-1]
    manifest=read_json(r/'integrity.json')
    path=None
    if change=='schematic':
        path=r/'board.kicad_sch';path.write_text(path.read_text().replace('"/A"','"/WRONG"').replace('"A"','"WRONG"'))
    elif change=='bom':
        path=r/'candidate-bom.csv';path.write_text(path.read_text().replace('UNCONFIRMED - DO NOT ORDER','QUALIFIED'))
    elif change=='module-provenance':
        path=r/'inputs/module-source.json';d=read_json(path);d['url']='https://wrong.invalid';path.write_text(json.dumps(d))
    elif change=='module-import':
        path=r/'module-import.json';d=read_json(path);d['revision_qualified']=True;path.write_text(json.dumps(d))
    elif change in ['support-mpn','core-mpn']:
        path=r/'parts.json';d=read_json(path);d['parts'][-2 if change=='support-mpn' else 0]['mpn']='FAKE-QUALIFIED';path.write_text(json.dumps(d))
    elif change=='report':
        path=r/'report.json';d=read_json(path);d['layout_allowed']=True;path.write_text(json.dumps(d))
    elif change=='required-manifest': del manifest['artifacts']['inputs/wiz550io.lbr']
    if path:manifest['artifacts'][str(path.relative_to(r))]=sha256(path)
    (r/'integrity.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError): verify_review(r)


def test_review_project_resolves_its_frozen_local_libraries(review_case):
    from pcb_harness.orchestration.stm32_circuit import prepare_review
    prepare_review(*review_case);root=review_case[-1]
    assert 'assets/SupportTarget.kicad_sym' in (root/'sym-lib-table').read_text()
    assert 'assets/STM32Target.pretty' in (root/'fp-lib-table').read_text()


def test_passive_rail_bridge_is_rejected_without_linear_device_safety_claim():
    top,parts,checks=fixture()
    parts['r']={'pins':[{'id':'p1','number':'1'},{'id':'p2','number':'2'}]}
    top['instances'].append({'ref':'R1','part_id':'r','value':'0R','block':'test','pins':{'1':'USB_VBUS','2':'5V'},'schematic_position_mm':[20,20]})
    checks['required_refs'].append('R1')
    with pytest.raises(ValueError,match='rail bridge'):compile((top,parts,checks))


def test_finite_sense_resistors_are_not_claimed_to_be_direct_rail_short():
    top,parts,checks=fixture();parts['r']={'pins':[{'id':'p1','number':'1'},{'id':'p2','number':'2'}]}
    top['instances'].append({'ref':'R1','part_id':'r','value':'47k','block':'test','pins':{'1':'USB_VBUS','2':'5V'},'schematic_position_mm':[20,20]})
    checks['required_refs'].append('R1')
    assert len(compile((top,parts,checks))['instances'])==3


def test_project_context_is_present_for_native_local_library_resolution(review_case):
    from pcb_harness.orchestration.stm32_circuit import prepare_review
    prepare_review(*review_case)
    assert read_json(review_case[-1]/'board.kicad_pro')['meta']['filename']=='board.kicad_pro'


@pytest.fixture
def native_case(review_case):
    from pcb_harness.orchestration.stm32_circuit import prepare_review
    prepare_review(*review_case);root=review_case[-1];n=root/'native';n.mkdir()
    (n/'netlist.xml').write_text('''<export><components><comp ref="U1"/><comp ref="R1"/><comp ref="M1"/></components><nets>
    <net name="/A"><node ref="U1" pin="1"/><node ref="R1" pin="1"/>
    <node ref="M1" pin="1"/><node ref="M1" pin="2"/><node ref="M1" pin="3"/><node ref="M1" pin="4"/><node ref="M1" pin="5"/><node ref="M1" pin="6"/><node ref="M1" pin="7"/><node ref="M1" pin="8"/><node ref="M1" pin="9"/><node ref="M1" pin="10"/><node ref="M1" pin="11"/><node ref="M1" pin="13"/><node ref="M1" pin="14"/></net>
    <net name="/B"><node ref="U1" pin="2"/><node ref="R1" pin="2"/></net>
    <net name="unconnected-(M1-NC-Pad12)"><node ref="M1" pin="12"/></net></nets></export>''')
    erc={'$schema':'https://schemas.kicad.org/erc.v1.json','source':'board.kicad_sch','coordinate_units':'mm',
         'kicad_version':'10.0.6','included_severities':['error','warning','exclusion'],'ignored_checks':[],
         'sheets':[{'violations':[{'type':'power_pin_not_driven','severity':'error','description':'Synthetic report contract test','items':[]}]}]}
    (n/'erc.json').write_text(json.dumps(erc));(n/'svg').mkdir();(n/'svg/board.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    cli=root/'synthetic-cli-evidence';cli.write_text('synthetic CLI identity fixture; never executed')
    return root,cli


def test_native_summary_reconstructs_actual_failed_erc_and_endpoint_sets(native_case):
    from pcb_harness.orchestration.native_candidate import write_native_summary
    from pcb_harness.orchestration.stm32_circuit import verify_review
    root,cli=native_case;s=write_native_summary(root,cli)
    assert s['netlist_matches'] and not s['erc_clean'] and s['erc_violation_count']==1
    assert s['topology_net_count']==2 and s['native_net_count']==3 and s['explicit_nc_count']==1
    assert verify_review(root)


@pytest.mark.parametrize('change',['flags','netlist-claim','erc-count','image-drift','summary-absent','summary-omission','wrong-source','cli-drift','unexpected-node'])
def test_forged_or_drifting_native_evidence_is_rejected(native_case,change):
    from pcb_harness.orchestration.native_candidate import write_native_summary
    from pcb_harness.orchestration.stm32_circuit import verify_review
    root,cli=native_case
    if change=='image-drift':(root/'native/crop.png').write_bytes(b'synthetic crop contract')
    write_native_summary(root,cli);path=root/'native-summary.json';s=read_json(path)
    if change=='flags':s.update(erc_clean=True,release_eligible=True,layout_allowed=True)
    elif change=='netlist-claim':s['netlist_matches']=False
    elif change=='erc-count':s['erc_violation_count']=0
    elif change=='image-drift':(root/'native/crop.png').write_bytes(b'changed')
    elif change=='summary-absent':path.unlink()
    elif change=='summary-omission':del s['artifacts']['native/netlist.xml']
    elif change=='wrong-source':s['schematic_sha256']='0'*64
    elif change=='cli-drift':cli.write_text('changed compiler')
    elif change=='unexpected-node':
        p=root/'native/netlist.xml';p.write_text(p.read_text().replace('<node ref="U1" pin="1"/>','<node ref="UNEXPECTED" pin="1"/>'))
        s['artifacts']['native/netlist.xml']=sha256(p)
    if change!='summary-absent':path.write_text(json.dumps(s))
    with pytest.raises((ValueError,OSError)):verify_review(root)


def test_existing_verifier_cannot_ignore_a_forged_native_sidecar(native_case):
    from pcb_harness.orchestration.stm32_circuit import verify_review
    root,_=native_case
    (root/'native-summary.json').write_text(json.dumps({'erc_clean':True,'netlist_matches':False,'layout_allowed':True,'release_eligible':True}))
    with pytest.raises((ValueError,OSError)):verify_review(root)


def test_source_bound_sdo_model_is_a_derivative_without_mutating_core(review_case):
    from pcb_harness.orchestration.stm32_circuit import prepare_review
    from pcb_harness.orchestration.candidate_models import apply_sdo_models
    prepare_review(*review_case);root=review_case[-1]
    core=root/'inputs/pins/inputs/core';parts=read_json(core/'parts.json')['parts']
    # Synthetic packet cannot claim genuine pin12; failure before any write.
    before=(core/'assets/STM32Target.kicad_sym').read_bytes()
    with pytest.raises(ValueError,match='SDO'):
        apply_sdo_models(root,parts,{'enabled':True,'source_sha256':'0'*64})
    assert (core/'assets/STM32Target.kicad_sym').read_bytes()==before


def test_explicit_supply_markers_are_nonphysical_and_keep_layout_closed(review_case):
    from pcb_harness.orchestration.stm32_circuit import prepare_review
    from pcb_harness.orchestration.candidate_models import add_supply_markers
    from pcb_harness.circuit.sexpr import parse_sexpr,children,child
    prepare_review(*review_case);root=review_case[-1]
    tree=parse_sexpr((root/'board.kicad_sch').read_text())
    add_supply_markers(tree,read_json(root/'circuit.json'),[{'net':'/A','at':[140,100],'basis':'external regulated source engineering declaration'}])
    marker=children(tree,'symbol')[-1]
    assert child(marker,'on_board')[1]=='no' and child(marker,'in_bom')[1]=='no'
    assert child(marker,'lib_id')[1]=='HarnessAnnotations:SUPPLY_FLAG'
    assert read_json(root/'report.json')['layout_allowed'] is False


def test_recovered_sources_are_frozen_and_package_correction_survives_rederive(tmp_path):
    """Replacing source packet after capture must not alter the corrected U7 footprint."""
    from pcb_harness.orchestration.source_completion import capture_source_completion
    from pcb_harness.orchestration.stm32_circuit import prepare_review, verify_review
    repo=Path(__file__).resolve().parents[1]
    pins=repo/'runs/m4/core-pin-evidence-final-2026-10-10'
    if not pins.is_dir(): pytest.skip('original publisher/core packet integration evidence unavailable')
    source=tmp_path/'sources'
    capture_source_completion(repo/'benchmarks/stm32-communications/source-recovery/completion-input.json',repo,source)
    inputs=tmp_path/'draft-inputs';inputs.mkdir()
    top=read_json(repo/'benchmarks/stm32-communications/candidate-topology-presupport.json')
    next(i for i in top['instances'] if i['ref']=='U7')['value']='MAX3232IDWR'
    checks=read_json(repo/'checklists/stm32-communications/candidate-circuit-presupport.json')
    (inputs/'topology.json').write_text(json.dumps(top));(inputs/'checks.json').write_text(json.dumps(checks))
    target=tmp_path/'runs/review'
    prepare_review(inputs/'topology.json',inputs/'checks.json',pins,
        '/Applications/KiCad/KiCad.app/Contents/SharedSupport',
        repo/'runs/m4/completion-2026-10-10/retrieval/wiz550io.lbr',
        repo/'runs/m4/completion-2026-10-10/retrieval/module-source.json',target,source_completion=source)
    u7=next(p for p in read_json(target/'parts.json')['parts'] if p['id']=='MAX3232IDR')
    assert u7['mpn']=='MAX3232IDWR' and u7['footprint_id']=='STM32Target:MAX3232IDWR_DW'
    assert (target/'inputs/source-completion/integrity.json').is_file()
    (source/'facts.json').write_text('{}')
    assert verify_review(target)
    manifest=read_json(target/'integrity.json')
    manifest['artifacts'].pop('inputs/source-completion/facts.json')
    (target/'integrity.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='source|incomplete'):verify_review(target)


def test_source_reviewed_support_requires_frozen_packet_and_exact_overlay(tmp_path):
    from pcb_harness.orchestration.support_qualification import capture_support
    from pcb_harness.orchestration.source_completion import capture_source_completion
    from pcb_harness.orchestration.stm32_circuit import prepare_review, verify_review
    repo=Path(__file__).resolve().parents[1]
    pins=repo/'runs/m4/core-pin-evidence-final-2026-10-10'
    if not pins.is_dir():pytest.skip('retained publisher/core packets required')
    packet=tmp_path/'support';base=read_json(repo/'benchmarks/stm32-communications/candidate-topology-presupport.json')
    completed=capture_support(base,repo,packet)
    source=tmp_path/'sources';capture_source_completion(repo/'benchmarks/stm32-communications/source-recovery/completion-input.json',repo,source)
    top=completed['topology'];next(i for i in top['instances'] if i['ref']=='U7')['value']='MAX3232IDWR'
    checks=read_json(repo/'checklists/stm32-communications/candidate-circuit-presupport.json');delta=completed['checks_delta']
    checks['required_refs']=delta['required_refs']
    for key in ['pin_nets','values','no_connect']:
        checks[key]={k:v for k,v in checks[key].items() if k not in delta['remove_refs']}
        checks[key].update(delta[key])
    inputs=tmp_path/'draft-inputs';inputs.mkdir()
    (inputs/'topology.json').write_text(json.dumps(top));(inputs/'checks.json').write_text(json.dumps(checks))
    target=tmp_path/'runs/review'
    args=(inputs/'topology.json',inputs/'checks.json',pins,'/Applications/KiCad/KiCad.app/Contents/SharedSupport',repo/'runs/m4/completion-2026-10-10/retrieval/wiz550io.lbr',repo/'runs/m4/completion-2026-10-10/retrieval/module-source.json',target)
    result=prepare_review(*args,source_completion=source,support_completion=packet)
    assert result['unselected_support_types']==[]
    assert result['support_completion']['source_count']>=25
    assert not result['layout_allowed'] and not result['release_eligible']
    from pcb_harness.circuit.bundle import validate_document
    validate_document('parts',read_json(target/'parts.json'))
    assert verify_review(target)
    # Alter captured library but update outer hashes; calibrated overlay still rejects it.
    p=target/'inputs/libraries/symbols/SupportQualified.kicad_sym';p.write_text(p.read_text().replace('tri_state','output'))
    integrity=read_json(target/'integrity.json');integrity['artifacts']['inputs/libraries/symbols/SupportQualified.kicad_sym']=sha256(p)
    (target/'integrity.json').write_text(json.dumps(integrity))
    with pytest.raises(ValueError,match='overlay|support'):verify_review(target)
