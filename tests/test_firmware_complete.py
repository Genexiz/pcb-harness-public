"""Executable checks on firmware protocol, bounded transport and ARM evidence."""
from pathlib import Path
import subprocess
import json
import pytest

ROOT = Path(__file__).resolve().parents[1]
FW = ROOT / 'benchmarks/stm32-communications/firmware-full'
COMPILER = ROOT / 'runs/m4/toolchain/arm-gnu-toolchain-13.2.Rel1-darwin-arm64-arm-none-eabi/bin/arm-none-eabi-gcc'
MICROCHIP = (FW / 'vendor/microchip/canfdspi/drv_canfdspi_api.c').exists()
needs_microchip = pytest.mark.skipif(not MICROCHIP, reason='Microchip API not fetched; run firmware-full/fetch_microchip.py')
needs_build = pytest.mark.skipif(not (MICROCHIP and COMPILER.exists()),
                                 reason='recorded ARM compiler or fetched Microchip API unavailable')


def test_protocol_queue_scheduler_and_cs_faults(tmp_path):
    """Wrong CRC, sequence wrap, queue overwrite or nonexclusive CS must fail."""
    binary = tmp_path / 'host'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(FW),
                    str(FW / 'core.c'), str(FW / 'host_checks.c'), '-o', str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'protocol queue scheduler cs: passed'


@needs_build
def test_cross_build_and_manifest_integrity(tmp_path):
    """Compile all production drivers; drift or fake resource reports are rejected."""
    from pcb_harness.orchestration.firmware_complete import build_complete, verify_complete
    report = build_complete(FW, tmp_path / 'build', COMPILER)
    assert report['scope'] == 'nine-interface-test-firmware'
    assert report['full_firmware_build_passed'] is True
    assert report['hardware_tested'] is False
    assert report['usage']['stack_bytes'] >= 4096
    assert report['usage']['flash_bytes'] <= 65536
    assert report['usage']['ram_bytes'] <= 20480
    assert len(report['driver_coverage']) == 9
    elf = tmp_path / 'build' / 'full.elf'
    data = elf.read_bytes()
    elf.write_bytes(data + b'drift')
    with pytest.raises(ValueError, match='hash drift'):
        verify_complete(FW, tmp_path / 'build')


@needs_microchip
def test_official_can_timing_and_transport_error(tmp_path):
    """20 MHz rates and TDC must be actual vendor register writes, not names."""
    binary = tmp_path / 'can-checks'
    subprocess.run(['cc', '-std=c11', '-I', str(FW / 'vendor/microchip/spi'),
                    '-I', str(FW / 'vendor/microchip/canfdspi'),
                    str(FW / 'vendor/microchip/canfdspi/drv_canfdspi_api.c'),
                    str(FW / 'host_driver_checks.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


@needs_build
def test_complete_rejects_forged_usage_and_failed_commands(tmp_path):
    from pcb_harness.orchestration.firmware_complete import build_complete, verify_complete
    from pcb_harness.circuit.bundle import sha256
    build = tmp_path / 'build'
    build_complete(FW, build, COMPILER)
    evidence = json.loads((build / 'build.json').read_text())
    evidence['usage']['flash_bytes'] = 1
    (build / 'build.json').write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match='actual ELF'):
        verify_complete(FW, build)
    from pcb_harness.orchestration.firmware_evidence import elf_usage
    evidence['usage'] = elf_usage((build / 'full.elf').read_bytes())
    commands = json.loads((build / 'commands.json').read_text())
    commands[-1]['exit_code'] = 1
    (build / 'commands.json').write_text(json.dumps(commands))
    evidence['outputs']['commands.json'] = sha256(build / 'commands.json')
    (build / 'build.json').write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match='failed command'):
        verify_complete(FW, build)
    (build / 'commands.json').write_text('[]')
    evidence['outputs']['commands.json'] = sha256(build / 'commands.json')
    (build / 'build.json').write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match='incomplete command'):
        verify_complete(FW, build)


def test_stack_budget_includes_nested_interrupts_and_rejects_recursion():
    from pcb_harness.orchestration.firmware_complete import stack_budget
    rows = [{'function': f, 'bytes': n, 'kind': 'static'} for f, n in
            [('main', 256), ('USB_LP_CAN1_RX0_IRQHandler', 64), ('HAL_PCD_IRQHandler', 128),
             ('SysTick_Handler', 32)]]
    assembly = '''08000000 <main>:
08000100 <USB_LP_CAN1_RX0_IRQHandler>:
 8000102: f000 bl 08000200 <HAL_PCD_IRQHandler>
08000200 <HAL_PCD_IRQHandler>:
08000300 <SysTick_Handler>:
'''
    assert stack_budget(rows, assembly)['conservative_bytes'] == 1120
    assembly += ' 8000302: f000 bl 08000300 <SysTick_Handler>\n'
    with pytest.raises(ValueError, match='recursive'):
        stack_budget(rows, assembly)


def test_monitor_decode_crc_and_incomplete_capture_fail_closed():
    import runpy
    import binascii
    import struct
    monitor = runpy.run_path(str(FW / 'hardware_monitor.py'))
    payload = bytearray(128)
    payload[4:8] = bytes([0xa5, 0x5a, 7, 1])
    struct.pack_into('<10I', payload, 8, 42, 43, 0, 0, 0, 0, 0, 44, 5, 45)
    struct.pack_into('<H', payload, 126, binascii.crc_hqx(payload[:126], 65535))
    port, counters = monitor['decode_telemetry'](payload)
    assert port == 7 and counters['rx'] == 42 and counters['tx_complete'] == 45
    payload[50] ^= 1
    with pytest.raises(ValueError, match='CRC'):
        monitor['decode_telemetry'](payload)
    assert monitor['assess_capture']([], 1800)['capture_passed'] is False
    assert monitor['assess_capture']([], 1)['hardware_tested'] is False


def test_crc_table_against_independent_reference_all_octets(tmp_path):
    import ctypes
    import binascii
    library = tmp_path / 'core.dylib'
    subprocess.run(['cc', '-shared', '-I', str(FW), str(FW / 'core.c'), '-o', str(library)], check=True)
    crc = ctypes.CDLL(str(library)).crc16
    crc.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    crc.restype = ctypes.c_uint16
    for value in range(256):
        payload = bytes([value]) * 128
        assert crc(payload, len(payload)) == binascii.crc_hqx(payload, 65535)


def test_thirty_minute_portable_queue_transport_model(tmp_path):
    """Model is explicitly conditional on2ms service, never silicon evidence."""
    binary = tmp_path / 'simulation'
    subprocess.run(['cc', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(FW),
                    str(FW / 'core.c'), str(FW / 'host_simulation.c'), '-o', str(binary)], check=True)
    result = json.loads(subprocess.run([str(binary)], text=True, capture_output=True, check=True).stdout)
    assert result['scope'] == 'portable-model-with-assumed-service'
    assert result['hardware_tested'] is False
    assert result['duration_ms'] == 1800000
    assert result['rx'][0] == 225000 and result['rx'][8] == 225000
    assert min(result['rx']) > 100000
    assert result['overflow'] == 0


def _capture_samples():
    periods = [8, 8, 8, 8, 10, 10, 3, 4, 8]
    samples = []
    for index in range(2001):
        elapsed = index * 0.9
        for port, period in enumerate(periods):
            counters = {field: 0 for field in ('rx', 'tx', 'crc_error', 'lost', 'reorder',
                        'overflow', 'timeout', 'service', 'latency_ms_max', 'tx_complete')}
            progress = int(elapsed * 1000 / period)
            counters.update(rx=progress, tx=progress, tx_complete=progress, service=index * 900,
                            latency_ms_max=10, stack_high_water_bytes=1024, scheduler_us_max=1000,
                            usb_irq_us_max=15, i2c_irq_us_max=15, device_tick_ms=int(elapsed * 1000))
            samples.append({'port': port, 'elapsed': elapsed, 'counters': counters})
    return samples


@pytest.mark.parametrize('fault', ['low_load', 'intermediate_reset', 'scheduler_stall', 'clock_reset'])
def test_capture_rejects_underload_intermediate_reset_and_timing_faults(fault):
    import runpy
    assess = runpy.run_path(str(FW / 'hardware_monitor.py'))['assess_capture']
    samples = _capture_samples()
    assert assess(samples, 1800)['capture_passed'] is True
    if fault == 'low_load':
        for sample in samples:
            for key in ('rx', 'tx', 'tx_complete'):
                sample['counters'][key] //= 10
    elif fault == 'intermediate_reset':
        samples[1000 * 9]['counters']['rx'] = 0
    elif fault == 'scheduler_stall':
        samples[-9]['counters']['scheduler_us_max'] = 10000
    else:
        samples[1000 * 9]['counters']['device_tick_ms'] = 0
    assert assess(samples, 1800)['capture_passed'] is False


@pytest.mark.parametrize('drift', ['extra_file', 'omitted_lock_file'])
def test_source_manifest_rejects_untracked_vendor_sources(tmp_path, drift):
    import shutil
    from pcb_harness.orchestration.firmware_complete import _sources
    copied = tmp_path / 'firmware'
    shutil.copytree(FW, copied)
    if drift == 'extra_file':
        (copied / 'vendor/hal/Src/extra.c').write_text('int injected_source;\n')
    else:
        lock = json.loads((copied / 'sources.lock.json').read_text())
        del lock['files']['hal/LICENSE.md']
        (copied / 'sources.lock.json').write_text(json.dumps(lock))
    with pytest.raises(ValueError, match='inventory'):
        _sources(copied)


def test_stack_budget_rejects_missing_compiler_frames():
    from pcb_harness.orchestration.firmware_complete import stack_budget
    with pytest.raises(ValueError, match='missing compiler stack'):
        stack_budget([], '08000000 <main>:\n')


@needs_build
def test_complete_rejects_removed_elf_driver_even_with_forged_symbol_report(tmp_path):
    from pcb_harness.orchestration.firmware_complete import build_complete, verify_complete
    from pcb_harness.circuit.bundle import sha256
    build = tmp_path / 'build'
    build_complete(FW, build, COMPILER)
    elf = build / 'full.elf'
    data = elf.read_bytes()
    assert b'usb_service\x00' in data
    elf.write_bytes(data.replace(b'usb_service\x00', b'xxx_service\x00'))
    evidence = json.loads((build / 'build.json').read_text())
    evidence['outputs']['full.elf'] = sha256(elf)
    (build / 'build.json').write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match='missing linked firmware driver'):
        verify_complete(FW, build)


def test_static_timing_report_keeps_unproved_cpu_bound_explicit():
    from pcb_harness.orchestration.firmware_complete import timing_budget
    result = timing_budget(FW)
    assert result['scope'] == 'source-bound-static-timing-and-buffer-analysis'
    assert result['hardware_tested'] is False
    assert result['wcet_proved'] is False
    assert result['workload']['USB']['payload_bps'] == 128000
    assert result['workload']['RS485']['echo_wire_us'] == 5556
    assert result['buffers']['uart_ring_fill_us'] == 22223
    assert result['poll_limits']['spi1_max_transaction_us'] == 1433
    assert result['queue_service_assumption_us'] == 2000
    assert result['source_sha256']['board.c']


def test_stack_budget_counts_gcc_optimized_clone_frames():
    from pcb_harness.orchestration.firmware_complete import stack_budget
    rows = [{'function': 'main', 'bytes': 256, 'kind': 'static'},
            {'function': 'worker.isra', 'bytes': 64, 'kind': 'static'}]
    assembly = '08000000 <main>:\n 8000002: f000 bl 08000100 <worker.isra.0>\n08000100 <worker.isra.0>:\n'
    assert stack_budget(rows, assembly)['foreground_all_retained_frame_sum'] == 320


def test_stack_budget_rejects_any_omitted_compiled_function_frame():
    from pcb_harness.orchestration.firmware_complete import stack_budget
    assembly = '08000000 <main>:\n 8000000: bl 8000010 <helper>\n08000010 <helper>:\n'
    rows = [{'function': 'main', 'bytes': 32, 'kind': 'static'}]
    with pytest.raises(ValueError, match='missing compiler stack frame evidence for helper'):
        stack_budget(rows, assembly, functions={'main', 'helper'})
    budget = stack_budget(rows, assembly, functions={'main', 'helper'}, exempt={'helper'})
    assert budget['foreground_all_retained_frame_sum'] == 32


@pytest.mark.parametrize('tamper', ['stack.json', 'stack-usage.txt'])
def test_complete_rejects_rehashed_omitted_stack_rows(tmp_path, tamper):
    from pcb_harness.orchestration.firmware_complete import build_complete, verify_complete
    from pcb_harness.circuit.bundle import sha256
    if not (COMPILER.exists() and MICROCHIP):
        pytest.skip('recorded ARM compiler unavailable')
    build = tmp_path / 'build'
    build_complete(FW, build, COMPILER)
    target = build / tamper
    if tamper == 'stack.json':
        rows = json.loads(target.read_text())
        target.write_text(json.dumps([r for r in rows if r['function'] != 'usb_service']))
    else:
        target.write_text(''.join(line for line in target.read_text().splitlines(True)
                                  if ':usb_service\t' not in line))
    assert sha256(target) != json.loads((build / 'build.json').read_text())['outputs'][tamper]
    evidence = json.loads((build / 'build.json').read_text())
    evidence['outputs'][tamper] = sha256(target)
    (build / 'build.json').write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match='stack frame evidence'):
        verify_complete(FW, build)


def test_microchip_fetch_verifies_archive_and_each_locked_file(tmp_path):
    import importlib.util, io, zipfile, hashlib
    spec = importlib.util.spec_from_file_location('fetch_microchip', FW / 'fetch_microchip.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not (FW / 'vendor/microchip/canfdspi/drv_canfdspi_api.c').exists():
        pytest.skip('Microchip files not fetched')
    lock = json.loads((FW / 'sources.lock.json').read_text())
    names = [n for n in lock['files'] if n.startswith('microchip/') and not n.startswith('microchip/spi/')]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name in names:
            archive.writestr('pkg/src/' + name.rsplit('/', 1)[1], (FW / 'vendor' / name).read_bytes())
    data = buffer.getvalue()
    fake = json.loads(json.dumps(lock))
    next(s for s in fake['sources'] if s['id'] == 'microchip')['archive_sha256'] = hashlib.sha256(data).hexdigest()
    assert module.extract(data, fake, tmp_path) == sorted(names)
    assert all((tmp_path / n).read_bytes() == (FW / 'vendor' / n).read_bytes() for n in names)
    with pytest.raises(ValueError, match='archive SHA-256'):
        module.extract(data + b'x', fake, tmp_path / 'other')
    assert not (tmp_path / 'other').exists()
