"""M0 transport fault injection on the isolated live fixture; never retries a write.

Send EndCommit once, close the connection before receiving its reply, then
reconcile with an independent client. This is not an OS-crash recovery proof.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

from kipy import KiCad
from kipy.board import Board
from kipy.client import KiCadClient
from kipy.geometry import Vector2
from kipy.proto.common import ApiRequest
from kipy.proto.common.types import DocumentType
from probe_ipc import EXPECTED, snapshot
from safety import require_unchanged, run_probed_operation
from verification import select_document


class LostReplyClient(KiCadClient):
    armed = False
    injected = False

    def send(self, command, response_type):
        if self.armed and type(command).__name__ == 'EndCommit':
            self.armed = False
            if not self._connected:
                self._connect()
            envelope = ApiRequest()
            envelope.message.Pack(command)
            envelope.header.kicad_token = self._kicad_token
            envelope.header.client_name = self._client_name
            self._conn.send(envelope.SerializeToString())
            self._conn.close()
            self._connected = False
            self.injected = True
            raise ConnectionError('injected lost EndCommit reply; write must not be retried')
        return super().send(command, response_type)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--socket', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    client = LostReplyClient(args.socket, 'pcb-harness-m0-lost-reply', '', 3000)
    kicad = KiCad.from_client(client)
    document = select_document(kicad.get_open_documents(DocumentType.DOCTYPE_PCB), EXPECTED)
    board = Board(client, document)
    observer_kicad = KiCad(socket_path=args.socket, client_name='pcb-harness-m0-reconcile')
    observer = Board(observer_kicad._client,
        select_document(observer_kicad.get_open_documents(DocumentType.DOCTYPE_PCB), EXPECTED))
    baseline = snapshot(observer)
    if len(baseline['footprints']) != 3 or baseline['footprints'][0]['xy_mm'] != [20, 20]:
        raise ValueError('scratch baseline mismatch')
    board.save()
    baseline_text = observer.get_as_string()
    def files():
        return {str(p.relative_to(EXPECTED.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in EXPECTED.parent.rglob('*') if p.is_file() and
            (p.suffix in ('.kicad_pcb', '.kicad_pro', '.kicad_sch', '.kicad_dru',
                          '.kicad_mod', '.kicad_sym') or p.name.endswith('lib-table'))}
    baseline_files = files()
    report = {'status': 'running', 'socket': args.socket,
        'expected_document': str(EXPECTED), 'operations': []}
    def persist():
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    def reconcile_baseline():
        require_unchanged(baseline_text, observer.get_as_string(), baseline_files, files())
    def action():
        commit = board.begin_commit()
        part = next(f for f in board.get_footprints() if f.reference_field.text.value == 'R1')
        part.position = Vector2.from_xy_mm(24, 20)
        board.update_items(part)
        client.armed = True
        board.push_commit(commit, 'M0 lost reply injection')
        raise RuntimeError('fault injection did not run')
    entry = run_probed_operation(report, 'lost_commit_reply', action, reconcile_baseline, persist)
    report['injected'] = client.injected
    report['write_retries'] = 0
    persist()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        observed = snapshot(observer)
        if observed['footprints'][0]['xy_mm'] == [24, 20]:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError('delivery not reconciled; retain uncertain state and scratch board')
    report['published_commit_observed'] = True
    report['observed_after_lost_reply'] = observed
    persist()
    if entry['status'] != 'uncertain' or not entry['recovery_required']:
        raise RuntimeError('lost reply incorrectly treated as safe failure')
    # Explicit probe recovery only after the complete expected post-state is known.
    expected = json.loads(json.dumps(baseline))
    expected['footprints'][0]['xy_mm'] = [24, 20]
    for pad in expected['footprints'][0]['pads']:
        pad['xy_mm'][0] += 4
    if observed != expected:
        raise RuntimeError('unexpected concurrent geometry; automatic recovery refused')
    changed_text = observer.get_as_string()
    require_unchanged(changed_text, observer.get_as_string(), baseline_files, files())
    observer.revert()
    report['baseline_restored'] = snapshot(observer) == baseline
    require_unchanged(baseline_text, observer.get_as_string(), baseline_files, files())
    if not report['baseline_restored']:
        raise RuntimeError('baseline restoration failed')
    report['status'] = 'passed'
    report['reconciliation'] = 'published once; explicit guarded saved-board restore'
    persist()
    print('Lost EndCommit reply: PASS; uncertain journal retained; no retry; baseline restored')


if __name__ == '__main__':
    main()
