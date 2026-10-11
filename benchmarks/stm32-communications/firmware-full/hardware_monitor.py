"""Real-device USB/UART/UDP echo and 30-minute telemetry capture (standard library).

CAN/I2C/SPI require physical peers described in README. A capture is evidence for
review, not automatic board identity, stack-watermark or signal-integrity proof.
"""
import argparse
import binascii
import json
import os
from pathlib import Path
import selectors
import socket
import struct
import termios
import time
import tty

FIELDS = ('rx', 'tx', 'crc_error', 'lost', 'reorder', 'overflow', 'timeout',
          'service', 'latency_ms_max', 'tx_complete')
DIAGNOSTICS = ('usb_driver_faults', 'scheduler_tick_overruns', 'scheduler_us_max', 'spi_faults',
               'usb_reset_events', 'usb_suspend_events', 'usb_irq_us_max', 'i2c_irq_us_max',
               'device_tick_ms', 'stack_high_water_bytes')


def decode_telemetry(payload):
    if len(payload) != 128 or binascii.crc_hqx(payload[:126], 65535) != int.from_bytes(payload[126:], 'little'):
        raise ValueError('invalid frame length or CRC')
    if payload[4:6] != bytes([0xa5, 0x5a]):
        return None
    if payload[6] >= 9 or payload[7] != 1:
        raise ValueError('invalid telemetry port/version')
    counters = dict(zip(FIELDS, struct.unpack_from('<10I', payload, 8)))
    counters.update(zip(DIAGNOSTICS, struct.unpack_from('<10I', payload, 48)))
    return payload[6], counters


def assess_capture(samples, elapsed):
    failures, deltas = [], {}
    # Engineering acceptance thresholds for the selected firmware envelope;
    # 1% permits capture-boundary rounding, not a lower offered-load claim.
    periods = (8, 8, 8, 8, 10, 10, 3, 4, 8)
    if elapsed < 1800:
        failures.append('duration below30 minutes')
    for port in range(9):
        subset = [s for s in samples if s['port'] == port]
        if len(subset) < 2 or subset[-1]['elapsed'] - subset[0]['elapsed'] < 1790:
            failures.append(f'port{port}: insufficient capture span')
            continue
        first, last = subset[0]['counters'], subset[-1]['counters']
        span = subset[-1]['elapsed'] - subset[0]['elapsed']
        delta = {k: last[k] - first[k] for k in FIELDS if k != 'latency_ms_max'}
        deltas[str(port)] = delta
        if max(b['elapsed'] - a['elapsed'] for a, b in zip(subset, subset[1:])) > 2:
            failures.append(f'port{port}: telemetry gap exceeds2 seconds')
        if min(delta['rx'], delta['tx_complete'], delta['service']) <= 0:
            failures.append(f'port{port}: no verified bidirectional progress')
        if min(delta['rx'], delta['tx_complete']) < int(span * 1000 / periods[port] * 0.99):
            failures.append(f'port{port}: below selected frame-rate envelope')
        if any(delta[k] != 0 for k in ('crc_error', 'lost', 'reorder', 'overflow', 'timeout')):
            failures.append(f'port{port}: CRC/loss/reorder/overflow/timeout or reset')
        if any(value < 0 for value in delta.values()):
            failures.append(f'port{port}: counters decreased/reset')
        for a, b in zip(subset, subset[1:]):
            if b['elapsed'] <= a['elapsed'] or any(b['counters'][k] < a['counters'][k]
                    for k in FIELDS + ('device_tick_ms',)):
                failures.append(f'port{port}: intermediate counters/clock decreased or capture reordered')
                break
        if last.get('scheduler_us_max', 0) == 0 or last['scheduler_us_max'] > 2000:
            failures.append(f'port{port}: absent/excessive scheduler duration versus2ms model')
        if last['latency_ms_max'] > 100:
            failures.append(f'port{port}: echo latency exceeds100ms acceptance target')
        for k in ('usb_driver_faults', 'spi_faults', 'usb_reset_events', 'usb_suspend_events'):
            if last.get(k, 0) != first.get(k, 0):
                failures.append(f'port{port}: {k} changed')
        if last.get('stack_high_water_bytes', 0) >= 8192 or last.get('stack_high_water_bytes', 0) == 0:
            failures.append(f'port{port}: absent/overflowing stack watermark')
    return {'scope': 'device-telemetry-capture', 'capture_passed': not failures,
            'hardware_tested': False, 'elapsed_seconds': elapsed, 'failures': failures,
            'counter_deltas': deltas,
            'limits': 'Capture review still requires firmware hash, board/peer identity, line rates and simultaneous peer traffic, stack watermark, clock and electrical validation. No automatic hardware qualification.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--usb', required=True, help='CDC serial device, e.g. /dev/cu.usbmodem...')
    p.add_argument('--uart', action='append', default=[], help='115200 echo peer device; repeat for UART/RS232')
    p.add_argument('--rs485', help='115200 adapter-managed DE/RE; verify whole-frame turnaround below2ms before use')
    p.add_argument('--udp-bind', default='192.168.50.1', help='UDP peer IP reachable by WIZ550io')
    p.add_argument('--seconds', type=float, default=1802)
    p.add_argument('--board-id', required=True)
    p.add_argument('--firmware-elf-sha256', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    selector, resources, samples = selectors.DefaultSelector(), [], []
    streams, pending = {}, {}
    start = time.monotonic()
    with Path(args.output).open('x') as log:
        log.write(json.dumps({'scope': 'hardware-capture-header', 'board_id': args.board_id,
                              'firmware_elf_sha256': args.firmware_elf_sha256,
                              'started_unix': time.time(), 'arguments': vars(args)}) + '\n')
        try:
            for path in [args.usb, *args.uart, *([args.rs485] if args.rs485 else [])]:
                fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                saved = termios.tcgetattr(fd)
                resources.append((fd, saved))
                tty.setraw(fd)
                mode = termios.tcgetattr(fd)
                mode[4] = mode[5] = termios.B115200
                mode[2] |= termios.CLOCAL | termios.CREAD
                termios.tcsetattr(fd, termios.TCSANOW, mode)
                selector.register(fd, selectors.EVENT_READ, ('serial', path == args.usb, path == args.rs485))
                streams[fd], pending[fd] = bytearray(), bytearray()
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            resources.append((udp, None))
            udp.bind((args.udp_bind, 5001))
            udp.setblocking(False)
            selector.register(udp, selectors.EVENT_READ, ('udp', False, False))
            while time.monotonic() - start < args.seconds:
                for key, events in selector.select(0.05):
                    kind, is_usb, is_rs485 = key.data
                    if kind == 'udp':
                        packet, peer = key.fileobj.recvfrom(2048)
                        if len(packet) != 128 or binascii.crc_hqx(packet[:126], 65535) != int.from_bytes(packet[126:], 'little'):
                            raise ValueError('UDP peer frame CRC/length')
                        key.fileobj.sendto(packet, (peer[0], 5000))
                        continue
                    fd = key.fd
                    if events & selectors.EVENT_WRITE and pending[fd]:
                        try:
                            sent = os.write(fd, pending[fd])
                            del pending[fd][:sent]
                        except BlockingIOError:
                            pass
                    if events & selectors.EVENT_READ:
                        chunk = os.read(fd, 4096)
                        if not chunk:
                            raise ValueError('serial device disconnected')
                        if is_rs485:
                            streams[fd].extend(chunk)
                            while len(streams[fd]) >= 32:
                                frame = bytes(streams[fd][:32]);del streams[fd][:32]
                                if binascii.crc_hqx(frame[:30], 65535) != int.from_bytes(frame[30:], 'little'):
                                    raise ValueError('RS485 peer frame CRC')
                                pending[fd].extend(frame)
                        else:
                            pending[fd].extend(chunk)
                        if len(pending[fd]) > 65536:
                            raise ValueError('host echo queue overflow')
                        if is_usb:
                            streams[fd].extend(chunk)
                            while len(streams[fd]) >= 128:
                                frame = bytes(streams[fd][:128]);del streams[fd][:128]
                                decoded = decode_telemetry(frame)
                                if decoded:
                                    port, counters = decoded
                                    record = {'elapsed': time.monotonic() - start,
                                              'port': port, 'counters': counters}
                                    samples.append(record)
                                    log.write(json.dumps(record) + '\n');log.flush()
                    selector.modify(fd, selectors.EVENT_READ |
                                    (selectors.EVENT_WRITE if pending[fd] else 0), key.data)
            result = assess_capture(samples, time.monotonic() - start)
        except (OSError, ValueError) as error:
            result = assess_capture(samples, time.monotonic() - start)
            result['capture_passed'] = False
            result['failures'].append(str(error))
        finally:
            for resource, saved in reversed(resources):
                if isinstance(resource, int):
                    if saved is not None:
                        termios.tcsetattr(resource, termios.TCSANOW, saved)
                    os.close(resource)
                else:
                    resource.close()
            selector.close()
        log.write(json.dumps({'summary': result}) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['capture_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
