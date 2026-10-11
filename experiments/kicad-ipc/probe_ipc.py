"""Disposable M0 probe. Only edits the exact capability scratch document.

Requires the fixture already open in PCB Editor. No GUI-driving or autorouting.
Operations are explicit coordinates; baseline copper is preserved afterwards.
"""
from pathlib import Path
import argparse
import hashlib
import json
import uuid

from kipy import KiCad
from kipy.board import Board
from kipy.client import KiCadClient
from kipy.board_types import Track, Via, Zone, BoardLayer
from kipy.geometry import Vector2, Angle, PolygonWithHoles, PolyLine, PolyLineNode
from kipy.proto.common.types import DocumentType
from kipy.util.units import from_mm
from verification import select_document
from safety import require_unchanged, wait_until_ready, run_probed_operation, absolute_output_directory

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / 'runs/capability/live/board.kicad_pcb'


def xy(point):
    return [point.x / 1_000_000, point.y / 1_000_000]


def snapshot(board):
    return {
        'footprints': sorted([{'id': f.id.value, 'ref': f.reference_field.text.value,
            'xy_mm': xy(f.position), 'angle_deg': f.orientation.degrees, 'layer': f.layer,
            'locked': f.locked, 'pads': sorted([{'id': p.id.value, 'number': p.number,
                'xy_mm': xy(p.position), 'net': p.net.name} for p in f.definition.pads], key=lambda p:p['number'])}
            for f in board.get_footprints()], key=lambda f:f['ref']),
        'tracks': sorted([{'id': t.id.value, 'start_mm': xy(t.start), 'end_mm': xy(t.end),
            'width_mm':t.width/1_000_000, 'layer':t.layer, 'net':t.net.name}
            for t in board.get_tracks()], key=lambda t:t['id']),
        'vias': sorted([{'id':v.id.value, 'xy_mm':xy(v.position), 'net':v.net.name,
            'drill_mm':v.drill_diameter/1_000_000, 'diameter_mm':v.diameter/1_000_000}
            for v in board.get_vias()], key=lambda v:v['id']),
        'zones': sorted([{'id':z.id.value,'net':z.net.name if z.net else None,
            'layers':list(z.layers),'filled':z.filled} for z in board.get_zones()],key=lambda z:z['id'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'runs/capability/ipc')
    parser.add_argument('--socket', default='ipc:///tmp/kicad/api.sock')
    options = parser.parse_args()
    options.output=absolute_output_directory(options.output)
    options.output.mkdir(parents=True, exist_ok=True)
    client = KiCadClient(options.socket,'pcb-harness-m0-probe','',3000)
    kicad = KiCad.from_client(client)
    doc = select_document(kicad.get_open_documents(DocumentType.DOCTYPE_PCB), EXPECTED)
    board = Board(client, doc)
    report = {'server_version':str(kicad.get_version()), 'binding_api':str(kicad.get_api_version()),
        'expected_document':str(EXPECTED),'socket':options.socket,'document':str(doc), 'operations':[]}
    def project_hashes():
        return {str(p.relative_to(EXPECTED.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in EXPECTED.parent.rglob('*') if p.is_file() and
            (p.suffix in ('.kicad_pro','.kicad_dru','.kicad_sch','.kicad_sym','.kicad_mod')
             or p.name in ('fp-lib-table','sym-lib-table'))}
    def persist():
        (options.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def preserve_recovery(reason):
        report['recovery_required']=True
        report['recovery_reason']=str(reason)
        target=options.output/f'recovery-{uuid.uuid4()}.kicad_pcb'
        try:
            board.save_as(str(target),include_project=True)
            report['recovery_copy']=str(target)
        except Exception as error:
            report['recovery_copy_error']=str(error)
        persist()
    def guarded_revert(expected_board_text):
        try:
            require_unchanged(expected_board_text,board.get_as_string(),baseline_files,project_hashes())
        except Exception as error:
            preserve_recovery(error)
            raise
        board.revert()
    def operation(name, action):
        def reconcile():
            require_unchanged(baseline_board_text,board.get_as_string(),baseline_files,project_hashes())
        entry=run_probed_operation(report,name,action,reconcile,persist)
        print(name,entry['status'],entry.get('error',''),flush=True)
        if entry['recovery_required']:
            preserve_recovery(entry.get('reconciliation_error','operation uncertain'))
            raise RuntimeError('probe state uncertain; stop before further mutations')
        return entry
    baseline = snapshot(board)
    if not (len(baseline['footprints'])==3 and len(baseline['tracks'])==8 and len(baseline['vias'])==3):
        raise ValueError('live project does not match the expected scratch fixture')
    baseline_board_text=board.get_as_string()
    baseline_files=project_hashes()
    report['baseline_board_digest']=hashlib.sha256(baseline_board_text.encode()).hexdigest()
    report['baseline_project_hashes']=baseline_files
    report['status']='running'
    persist()
    (options.output/'baseline.json').write_text(json.dumps(baseline,indent=2))
    operation('query_geometry',lambda:{'snapshot':baseline,'nets':[n.name for n in board.get_nets()]})
    try:
        board.save()
        baseline_board_text=board.get_as_string()
        baseline_files=project_hashes()
        report['baseline_board_digest']=hashlib.sha256(baseline_board_text.encode()).hexdigest()
        report['baseline_project_hashes']=baseline_files
        (options.output/'baseline-live-text.kicad_pcb').write_text(baseline_board_text)
        persist()
        board.save_as(str(options.output/'baseline.kicad_pcb'),include_project=True)
    except Exception as error:
        preserve_recovery(error)
        raise

    def fp(ref='R1'):
        return next(f for f in board.get_footprints() if f.reference_field.text.value==ref)

    def move_rotate_drop():
        commit = board.begin_commit()
        try:
            part = fp()
            part.position = Vector2.from_xy_mm(30,18)
            part.orientation = Angle.from_degrees(90)
            result = board.update_items(part)
            assert len(result)==1
            actual = result[0]
            assert xy(actual.position)==[30,18]
            assert actual.orientation.degrees==90
            pads = {p.number:xy(p.position) for p in actual.definition.pads}
            assert pads == {'1':[30,19],'2':[30,17]}, pads
            observed = {'staged_position':xy(actual.position),'staged_pads':pads,
                'published_query_position':xy(fp().position)}
            assert observed['published_query_position']==[20,20], observed
        finally:
            board.drop_commit(commit)
        assert snapshot(board)==baseline, 'drop_commit did not restore geometry'
        return {'during':observed,'restored':True}
    operation('move_rotate_drop_commit',move_rotate_drop)

    def create_remove():
        commit = board.begin_commit()
        expected_changed=None
        try:
            part = fp().clone()
            part.reference_field.text.value = 'R99'
            part.position = Vector2.from_xy_mm(30,22)
            # clone clears only the root ID; assign fresh child and field IDs explicitly.
            for item in list(part.definition.items)+[part.reference_field,part.value_field,part.datasheet_field,part.description_field]:
                if hasattr(item,'id') and hasattr(item.id,'value'):
                    item.id.value = str(uuid.uuid4())
            created = board.create_items(part)
            assert len(created)==1 and len(board.get_footprints())==3
            board.push_commit(commit,'M0 create footprint')
            commit=None
            expected_changed=board.get_as_string()
            assert len(board.get_footprints())==4
            board.remove_items(created)
            expected_changed=board.get_as_string()
            assert len(board.get_footprints())==3
        finally:
            if commit is not None:board.drop_commit(commit)
            elif expected_changed is not None:guarded_revert(expected_changed)
        assert snapshot(board)==baseline
        return {'created_count':1,'removed_count':1,'restored':True,
            'limitation':'creation from existing footprint definition; library loader not yet proven'}
    operation('create_remove_footprint',create_remove)

    def exact_copper():
        commit = board.begin_commit()
        expected_changed=None
        try:
            net = next(n for n in board.get_nets() if n.name=='/NET_B')
            track = Track(); track.start=Vector2.from_xy_mm(21,25); track.end=Vector2.from_xy_mm(25,27)
            track.width=from_mm(0.4); track.layer=BoardLayer.BL_B_Cu; track.net=net
            via = Via(); via.position=Vector2.from_xy_mm(25,27); via.diameter=from_mm(0.6)
            via.drill_diameter=from_mm(0.3); via.net=net
            created=board.create_items([track,via])
            assert len(created)==2 and len(board.get_tracks())==8 and len(board.get_vias())==3
            board.push_commit(commit,'M0 exact track and via')
            commit=None
            expected_changed=board.get_as_string()
            assert len(board.get_tracks())==9 and len(board.get_vias())==4
            actual=next(t for t in board.get_tracks() if t.id==created[0].id)
            assert xy(actual.start)==[21,25] and xy(actual.end)==[25,27] and actual.width==from_mm(0.4)
            actual.width=from_mm(0.5)
            updated=board.update_items(actual)
            expected_changed=board.get_as_string()
            assert len(updated)==1
            readback=next(t for t in board.get_tracks() if t.id==actual.id)
            assert readback.width==from_mm(0.5)
            actual_via=next(v for v in board.get_vias() if v.id==created[1].id)
            assert xy(actual_via.position)==[25,27] and actual_via.diameter==from_mm(0.6)
            assert actual_via.drill_diameter==from_mm(0.3) and actual_via.net.name=='/NET_B'
            evidence=snapshot(board)
            board.remove_items(created)
            expected_changed=board.get_as_string()
        finally:
            if commit is not None:board.drop_commit(commit)
            elif expected_changed is not None:guarded_revert(expected_changed)
        assert snapshot(board)==baseline
        return {'during':evidence,'restored':True}
    operation('exact_tracks_vias_update_delete',exact_copper)

    def commit_revert():
        commit=board.begin_commit()
        part=fp(); part.position=Vector2.from_xy_mm(25,20)
        part.orientation=Angle.from_degrees(90)
        updated=board.update_items(part)
        assert len(updated)==1
        board.push_commit(commit,'M0 explicit movement')
        assert xy(fp().position)==[25,20]
        assert fp().orientation.degrees==90
        observed_pads={p.number:xy(p.position) for p in fp().definition.pads}
        assert observed_pads=={'1':[25,21],'2':[25,19]}
        expected_changed=board.get_as_string()
        guarded_revert(expected_changed)
        assert snapshot(board)==baseline
        return {'push_visible':True,'published_pad_positions':observed_pads,'saved_baseline_restored':True}
    operation('push_commit_revert_saved_board',commit_revert)

    def flip():
        commit=board.begin_commit()
        expected_changed=None
        try:
            result=board.flip_items(fp())
            assert len(result)==1 and result[0].layer==BoardLayer.BL_B_Cu
            query_layer_before_push=fp().layer
            # Native 10.0.6 FlipItems is visible immediately; ordinary updates stage.
            assert query_layer_before_push in (BoardLayer.BL_F_Cu,BoardLayer.BL_B_Cu)
            board.push_commit(commit,'M0 native flip')
            commit=None
            expected_changed=board.get_as_string()
            assert fp().layer==BoardLayer.BL_B_Cu
            evidence={'layer':fp().layer,'pads':{p.number:xy(p.position) for p in fp().definition.pads},
                'angle_deg':fp().orientation.degrees,'published':True,
                'query_layer_before_push':query_layer_before_push}
            assert evidence['pads']=={'1':[21,20],'2':[19,20]}, evidence
        finally:
            if commit is not None:board.drop_commit(commit)
            elif expected_changed is not None:guarded_revert(expected_changed)
        assert snapshot(board)==baseline
        return evidence
    operation('native_flip_items',flip)

    def zone_fill():
        commit=board.begin_commit()
        expected_changed=None
        try:
            zone=Zone(); zone.layers=[BoardLayer.BL_B_Cu]
            zone.net=next(n for n in board.get_nets() if n.name=='/NET_B')
            outline=PolygonWithHoles(); line=PolyLine()
            for x,y in [(12,12),(68,12),(68,28),(12,28)]:
                line.append(PolyLineNode.from_point(Vector2.from_xy_mm(x,y)))
            outline.outline=line; zone.outline=outline; zone.clearance=from_mm(0.2)
            created=board.create_items(zone)
            assert len(created)==1
            board.push_commit(commit,'M0 ground zone')
            commit=None
            board.refill_zones(block=False)
            wait_until_ready(kicad.ping,timeout=10.0)
            zones=board.get_zones()
            assert len(zones)==1 and zones[0].filled
            expected_changed=board.get_as_string()
            board.save_as(str(options.output/'zone-filled.kicad_pcb'),include_project=True)
            evidence={'filled':True,'polygon_layers':list(zones[0].filled_polygons)}
        finally:
            if commit is not None:
                board.drop_commit(commit)
            elif expected_changed is not None:
                guarded_revert(expected_changed)
            else:
                preserve_recovery('zone mutation committed; completion unknown; automatic revert refused')
        assert snapshot(board)==baseline
        return evidence
    operation('create_refill_zone',zone_fill)

    def locked_update():
        commit=board.begin_commit()
        expected_changed=None
        try:
            part=fp();part.locked=True
            staged=board.update_items(part)
            locked=staged[0];locked.position=Vector2.from_xy_mm(26,20)
            board.update_items(locked)
            board.push_commit(commit,'M0 native lock test')
            commit=None
            expected_changed=board.get_as_string()
            position=xy(fp().position)
            actual_locked=fp().locked
        finally:
            if commit is not None:board.drop_commit(commit)
            elif expected_changed is not None:guarded_revert(expected_changed)
        assert snapshot(board)==baseline
        return {'locked_move_position_mm':position,'locked_flag':actual_locked,
            'kernel_must_enforce_locks':position!=[20,20]}
    operation('native_lock_behavior',locked_update)

    def second_client_change():
        second_client=KiCadClient(options.socket,'pcb-harness-m0-second-writer','',3000)
        second_kicad=KiCad.from_client(second_client)
        second_doc=select_document(second_kicad.get_open_documents(DocumentType.DOCTYPE_PCB),EXPECTED)
        second=Board(second_client,second_doc)
        before=snapshot(board)
        commit=second.begin_commit()
        expected_changed=None
        try:
            part=next(f for f in second.get_footprints() if f.reference_field.text.value=='R1')
            part.position=Vector2.from_xy_mm(28,20);second.update_items(part)
            second.push_commit(commit,'M0 external writer')
            commit=None
            expected_changed=board.get_as_string()
            after=snapshot(board)
            assert before!=after
        finally:
            if commit is not None:second.drop_commit(commit)
            elif expected_changed is not None:guarded_revert(expected_changed)
        assert snapshot(board)==baseline
        return {'change_observable':True,'limitation':'second IPC writer; real manual GUI edit not yet proven'}
    operation('external_writer_change_detection',second_client_change)

    def disconnected_query():
        bad=KiCad(socket_path='ipc:///tmp/pcb-harness-no-such-socket.sock',timeout_ms=250)
        try: bad.get_version()
        except Exception as error:
            return {'error_type':type(error).__name__,'no_mutation_attempted':True,
                'limitation':'unreachable socket read only; ambiguous mutation delivery not yet proven'}
        raise AssertionError('unexpected connection to missing socket')
    operation('disconnected_query',disconnected_query)
    try:
        require_unchanged(baseline_board_text,board.get_as_string(),baseline_files,project_hashes())
        board.save()
    except Exception as error:
        preserve_recovery(error)
        raise
    final=snapshot(board)
    report['baseline_restored']=final==baseline
    report['final_snapshot']=final
    report['board_sha256']=hashlib.sha256(EXPECTED.read_bytes()).hexdigest()
    report['status']='finished'
    persist()
    assert report['baseline_restored'],'scratch fixture not restored; do not continue'


if __name__=='__main__': main()
