"""Reproducible full STM32 test firmware build, with ELF-derived capacity evidence.

This producer proves linkage and static allocation. It does not turn an ARM
cross-build into measured timing, USB enumeration, or board qualification.
"""
from pathlib import Path
import json
import re
import subprocess
import struct

from pcb_harness.circuit.bundle import read_json, resolve_local, sha256
from pcb_harness.orchestration.firmware_evidence import elf_usage

APPLICATION = ("core.c", "board.c", "main.c", "runtime.c", "usb_port.c",
               "can_ports.c", "ethernet_port.c", "adapters/stm32f1xx_hal_pcd_bounded.c")
HEADERS = ("core.h", "board.h", "usbd_conf.h", "stm32f1xx_hal_conf.h",
           "stm32f103c8.ld", "sources.lock.json", "vendor/microchip/spi/drv_spi.h",
           "host_checks.c", "host_driver_checks.c", "host_simulation.c", "hardware_monitor.py", "README.md",
           "adapters/derivatives.json", "adapters/stm32f1xx_hal_pcd_bounded.patch")
DRIVERS = {
    "USB": ("usb_service", "USBD_CDC", "HAL_PCD_IRQHandler"),
    "UART": ("serial_service", "HAL_UART_Transmit_DMA"),
    "RS485": ("serial_service", "HAL_UART_TxCpltCallback"),
    "RS232": ("serial_service", "HAL_UART_Transmit_DMA"),
    "I2C": ("i2c_service", "HAL_I2C_Master_Transmit_IT"),
    "SPI": ("external_spi_service", "spi_transfer"),
    "CAN": ("can_service", "DRV_CANFDSPI_OperationModeSelect"),
    "CAN_FD": ("can_service", "DRV_CANFDSPI_TransmitChannelLoad"),
    "Ethernet": ("ethernet_service", "wiz_send_data"),
}
OUTPUTS = ("full.elf", "full.map", "full.bin", "sections.txt", "symbols.txt",
           "disassembly.txt", "commands.json", "stack.json", "host-checks.txt", "driver-checks.txt",
           "queue-model.json", "timing.json", "stack-usage.txt")


def stack_rows(text):
    """Rebuild frame rows from retained GCC -fstack-usage output."""
    rows, unit = [], None
    for line in text.splitlines():
        if line.startswith('# unit '):
            unit = line[len('# unit '):]
            continue
        location, amount, kind = line.split("\t")
        if unit is None:
            raise ValueError('stack frame evidence lacks compiler unit')
        rows.append({"function": location.rsplit(":", 1)[1],
                     "bytes": int(amount), "kind": kind, "unit": unit})
    return rows


def runtime_exemptions(source_root):
    """Assembly startup symbols and compiler runtime helpers without .su rows."""
    startup = resolve_local(source_root, 'vendor/cmsis/startup_stm32f103xb.s').read_text()
    names = set(re.findall(r'^(\w+):', startup, re.M))
    names.update(re.findall(r'\.thumb_set\s+(\w+)\s*,', startup))
    return names


def stack_budget(rows, assembly, functions=None, exempt=()):
    """Conservative acyclic frame sums plus every permitted IRQ priority level.

    Indirect callback targets are reviewed for this exact board adapter: USB
    descriptors/CDC interface and UART DMA callbacks. Shared-bus/WIZnet callbacks
    are main-loop-only. 256 bytes separately cover libgcc assembly routines.
    This is a static engineering bound under these call restrictions, not a
    stack-watermark measurement or automatic proof of indirect-call safety.
    """
    graph, current = {}, None
    for line in assembly.splitlines():
        label = re.match(r"[0-9a-f]+ <([^>]+)>:", line)
        if label:
            current = label[1]
            graph[current] = set()
        call = re.search(r"\b(?:bl|blx|b\.w)\s+[0-9a-f]+ <([^>+]+)>", line)
        if call and current:
            graph[current].add(call[1])
    active, checked = set(), set()

    def check(name):
        if name in active:
            raise ValueError(f"recursive stack path: {name}")
        if name in checked:
            return
        active.add(name)
        for target in graph.get(name, ()):
            check(target)
        active.remove(name)
        checked.add(name)
    for name in graph:
        check(name)
    weights = {}
    for row in rows:
        names = [name for name in graph if re.sub(r'(\.(?:isra|constprop))\.\d+$', r'\1', name) == row['function']]
        if not names:
            continue
        if row['kind'] != 'static':
            raise ValueError(f"unbounded stack frame: {row['function']}")
        # Inlined duplicates across units are bounded by the larger frame.
        for name in names:
            weights[name] = max(weights.get(name, 0), row['bytes'])
    if 'main' in graph and 'main' not in weights:
        raise ValueError('missing compiler stack frame evidence for main')
    if functions is not None:
        # Every compiled C function in the linked call graph needs its own frame;
        # only startup assembly and libgcc helpers use the separate reserve.
        missing = sorted(name for name in graph if name in functions and name not in weights
                         and name not in exempt and not name.startswith('__'))
        if missing:
            raise ValueError('missing compiler stack frame evidence for ' + ', '.join(missing))

    def closure(roots):
        found = set()
        def visit(name):
            if name in found:
                return
            found.add(name)
            for target in graph.get(name, ()):
                visit(target)
        for root in roots:
            visit(root)
        return sum(weights.get(name, 0) for name in found)
    descriptor_callbacks = {'cdc_init', 'cdc_deinit', 'control', 'received', 'dev', 'lang', 'str',
                            'manufacturer', 'product', 'serial', 'configuration', 'interface',
                            'usb_class_alloc', 'usb_class_free'}
    priority_roots = {
        0: {'SysTick_Handler', 'I2C1_EV_IRQHandler', 'I2C1_ER_IRQHandler'},
        1: {'USB_LP_CAN1_RX0_IRQHandler'} | descriptor_callbacks |
           {name for name in graph if name.startswith('USBD_CDC_')},
        2: {name for name in graph if name.startswith(('USART', 'DMA1_Channel')) and
            name.endswith('_IRQHandler')} |
           {name for name in graph if name.startswith('UART_DMA') or
            name.startswith('HAL_UART_') and name.endswith('Callback')},
        3: {name for name in graph if name.startswith('EXTI') and name.endswith('_IRQHandler')},
    }
    levels = {str(level): closure(roots) for level, roots in priority_roots.items()}
    foreground = sum(weights.values())
    return {'conservative_bytes': foreground + sum(levels.values()) + 4 * 40 + 256,
            'foreground_all_retained_frame_sum': foreground, 'irq_priority_frame_sums': levels,
            'exception_alignment_bytes': 160, 'libgcc_assembly_reserve_bytes': 256,
            'assumptions': 'No recursion/reentrant main service; four NVIC preemption priorities, same-priority IRQs cannot nest; only reviewed CDC/descriptor and UART DMA indirect callbacks. Assembly routines manually bounded within256 bytes. Not measured high-water.'}


def timing_budget(root):
    """Source-bound wire/buffer limits; keep CPU and IRQ WCET unknown.

    Transaction DWT deadlines do not bound the sum of many transactions and
    HAL iterations across a scheduler pass. Never promote conditional queue
    simulation into a proof that those costs meet the assumed service cadence.
    """
    root = Path(root)
    code = (root / 'core.c').read_text()
    def array(name):
        match = re.search(rf'{name}\[PORTS\]=\{{([\d,]+)\}}', code)
        if not match:
            raise ValueError('missing source-bound workload arrays')
        return tuple(map(int, match[1].split(',')))
    sizes, periods = array('frame_length'), array('period_ms')
    if len(sizes) != 9 or len(periods) != 9 or min(periods) <= 0:
        raise ValueError('invalid nine-interface workload')
    ceil = lambda n, d: (n + d - 1) // d
    workload = {port: {'frame_bytes': size, 'period_ms': period, 'payload_bps': size * 8000 // period}
                for port, size, period in zip(DRIVERS, sizes, periods)}
    for port in ('UART', 'RS485', 'RS232'):
        workload[port].update(baud=115200, format='8N1',
                              echo_wire_us=ceil(workload[port]['frame_bytes'] * 20 * 1000000, 115200))
    workload['I2C'].update(clock_hz=100000, address=0x42, echo_wire_us=5940)
    workload['SPI'].update(clock_hz=750000, full_duplex_wire_us=ceil(64 * 8 * 1000000, 750000))
    for port in ('CAN', 'CAN_FD'):
        workload[port].update(nominal_bps=500000, data_bps=2000000 if port == 'CAN_FD' else None,
                              offered_bus_load_status='approximate10percent; exact stuffing/arbitration needs trace')
    return {'scope': 'source-bound-static-timing-and-buffer-analysis', 'hardware_tested': False,
            'wcet_proved': False, 'cpu_hz': 48000000, 'workload': workload,
            'queue_service_assumption_us': 2000,
            'poll_limits': {'spi1_max_transaction_us': max(ceil(96 * 8 * 1000000, 6000000),
                              ceil(64 * 8 * 1000000, 750000)) + 750,
                            'spi2_each_transaction_us': 1000, 'usb_suspend_reset_us': 20,
                            'usb_irq_transfer_quota': 4, 'i2c_operation_deadline_ms': 8,
                            'uart_transmit_deadline_ms': 10, 'udp_send_deadline_ms': 50},
            'buffers': {'queue_depth_per_port': 2, 'uart_ring_bytes_each': 256,
                        'uart_ring_fill_us': ceil(256 * 10 * 1000000, 115200),
                        'uart_drain_bytes_per_pass': 64, 'usb_ring_bytes': 256,
                        'usb_drain_bytes_per_pass': 64, 'w5500_rx_tx_bytes_each': 2048,
                        'can_rx_tx_tef_slots_each': 8},
            'source_sha256': {name: sha256(root / name) for name in
                            ('core.c', 'board.c', 'can_ports.c', 'ethernet_port.c', 'usb_port.c',
                             'stm32f1xx_hal_conf.h', 'adapters/stm32f1xx_hal_pcd_bounded.c')},
            'unproved': ['Total normal-case CPU/IRQ cycle bound including HAL indirect callbacks',
                        'Aggregate stalled-peripheral deadline across multiple CAN/WIZnet transactions; per-transfer bounds may exceed2ms when summed',
                        'USB host scheduling, I2C clock stretching, RS485 peer turnaround and CAN arbitration/service bursts'],
            'limits': 'Finite source waits and wire arithmetic only. Does not certify scheduler WCET or timing feasibility. Queue model requires a measured or independently proven2ms service bound.'}


def _elf_symbols(data, kinds=(1, 2)):
    """Extract defined function/object names from actual ELF, not editable nm text."""
    elf_usage(data)
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    shoff, shsize, shnum = header[6], header[11], header[12]
    sections = [struct.unpack_from('<IIIIIIIIII', data, shoff + i * shsize) for i in range(shnum)]
    found = set()
    for section in sections:
        if section[1] != 2:
            continue
        if section[9] != 16 or section[6] >= shnum or section[5] % 16:
            raise ValueError('invalid ELF symbol table')
        names = sections[section[6]]
        strings = data[names[4]:names[4] + names[5]]
        for offset in range(section[4], section[4] + section[5], 16):
            name, value, size, info, other, index = struct.unpack_from('<IIIBBH', data, offset)
            if name >= len(strings):
                raise ValueError('invalid ELF symbol name')
            if index and info & 15 in kinds:
                found.add(strings[name:].split(b'\0', 1)[0].decode('ascii'))
    return found


def _sources(root):
    root = Path(root)
    lock = read_json(resolve_local(root, "sources.lock.json"))
    if lock.get("schema_version") != 1 or not lock.get("files"):
        raise ValueError("invalid official sources lock")
    entries = {**{name: sha256(resolve_local(root, name)) for name in APPLICATION + HEADERS},
               **{"vendor/" + name: digest for name, digest in lock["files"].items()}}
    inventory = {str(path.relative_to(root)) for path in (root / 'vendor').rglob('*') if path.is_file()}
    if inventory != {name for name in entries if name.startswith('vendor/')}:
        raise ValueError('firmware vendor source inventory differs from lock')
    for name, digest in entries.items():
        if sha256(resolve_local(root, name)) != digest:
            raise ValueError(f"firmware source hash drift: {name}")
    derivative = read_json(resolve_local(root, 'adapters/derivatives.json'))
    for field in ('original', 'derivative', 'patch'):
        if sha256(resolve_local(root, derivative[field])) != derivative[field + '_sha256']:
            raise ValueError(f"firmware derivative hash drift: {field}")
    return entries


def build_complete(source_root, output, compiler):
    """Compile and link all drivers into one 64 KB / 20 KB ARM executable."""
    root, out, compiler = map(lambda p: Path(p).absolute(), (source_root, output, compiler))
    sources = _sources(root)
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(args):
        result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=120)
        commands.append({"argv": list(map(str, args)), "exit_code": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode:
            raise ValueError(f"firmware command failed: {result.stderr}")
        return result.stdout

    version = run([compiler, "--version"])
    includes = (".", "vendor/cmsis/core", "vendor/cmsis/device", "vendor/hal/Inc",
                "vendor/usb/Core/Inc", "vendor/usb/Class/CDC/Inc",
                "vendor/microchip/canfdspi", "vendor/microchip/spi",
                "vendor/wiznet/Ethernet", "vendor/wiznet/Ethernet/W5500")
    flags = ["-mcpu=cortex-m3", "-mthumb", "-mfix-cortex-m3-ldrd", "-Os", "-g", "-ffreestanding", "-fno-builtin",
             "-ffunction-sections", "-fdata-sections", "-fstack-usage", "-fno-common",
             "-DSTM32F103xB", "-DUSE_HAL_DRIVER", "-D_WIZCHIP_=5500", "-std=c11",
             *[flag for name in includes for flag in ("-I" if name == '.' else "-isystem", root / name)]]
    c_files = [root / name for name in APPLICATION]
    c_files += [path for path in sorted((root / "vendor/hal/Src").glob("*.c"))
                if path.name != 'stm32f1xx_hal_pcd.c']
    c_files += [root / "vendor/cmsis/system_stm32f1xx.c"]
    c_files += [root / "vendor/usb/Core/Src" / name for name in
                ("usbd_core.c", "usbd_ctlreq.c", "usbd_ioreq.c")]
    c_files += [root / "vendor/usb/Class/CDC/Src/usbd_cdc.c",
                root / "vendor/microchip/canfdspi/drv_canfdspi_api.c",
                root / "vendor/wiznet/Ethernet/wizchip_conf.c",
                root / "vendor/wiznet/Ethernet/W5500/w5500.c"]
    objects = []
    for number, source in enumerate(c_files):
        obj = out / f"{number:02d}-{source.stem}.o"
        warnings = ["-Wall", "-Wextra"]
        if str(source.relative_to(root)) in APPLICATION and 'adapters/' not in str(source.relative_to(root)):
            warnings += ["-Werror", "-Wno-misleading-indentation"]
        run([compiler, *flags, *warnings, "-c", source, "-o", obj])
        objects.append(obj)
    startup = out / "startup.o"
    run([compiler, "-mcpu=cortex-m3", "-mthumb", "-c",
         root / "vendor/cmsis/startup_stm32f103xb.s", "-o", startup])
    run([compiler, "-mcpu=cortex-m3", "-mthumb", "-nostdlib", *objects, startup,
         "-T", root / "stm32f103c8.ld", "-lgcc",
         f"-Wl,-Map={out / 'full.map'},--gc-sections,--build-id=none", "-o", out / "full.elf"])
    run([compiler.with_name("arm-none-eabi-objcopy"), "-O", "binary", out / "full.elf", out / "full.bin"])
    for tool, args, name in (("size", ["-A"], "sections.txt"),
                             ("nm", ["-S", "--defined-only"], "symbols.txt"),
                             ("objdump", ["-d"], "disassembly.txt")):
        (out / name).write_text(run([compiler.with_name(f"arm-none-eabi-{tool}"), *args, out / "full.elf"]))
    run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", root,
         root / "core.c", root / "host_checks.c", "-o", out / "host-checks"])
    (out / "host-checks.txt").write_text(run([out / "host-checks"]))
    run(["cc", "-std=c11", "-I", root / "vendor/microchip/spi", "-I", root / "vendor/microchip/canfdspi",
         root / "vendor/microchip/canfdspi/drv_canfdspi_api.c", root / "host_driver_checks.c",
         "-o", out / "driver-checks"])
    (out / "driver-checks.txt").write_text(run([out / "driver-checks"]))
    run(["cc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", root,
         root / "core.c", root / "host_simulation.c", "-o", out / "queue-model"])
    (out / "queue-model.json").write_text(run([out / "queue-model"]))
    # GCC stack frames are actual generated code, not the reserved stack section.
    usage_text = ''.join(f'# unit {path.name}\n' + path.read_text() for path in sorted(out.glob("*.su")))
    (out / "stack-usage.txt").write_text(usage_text)
    (out / "stack.json").write_text(json.dumps(stack_rows(usage_text), indent=2) + "\n")
    (out / 'timing.json').write_text(json.dumps(timing_budget(root), indent=2) + '\n')
    evidence = {"schema_version": 1, "scope": "nine-interface-test-firmware",
                "producer_sha256": sha256(Path(__file__)),
                "compiler_version": version.splitlines()[0], "compiler_sha256": sha256(compiler),
                "sources": sources, "outputs": {name: sha256(out / name) for name in OUTPUTS},
                "usage": elf_usage((out / "full.elf").read_bytes())}
    (out / "build.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return verify_complete(root, out)


def verify_complete(source_root, build_root):
    """Reject stale inputs/artifacts and recalculate capacity from the actual ELF."""
    try:
        evidence = read_json(resolve_local(build_root, "build.json"))
        if evidence["schema_version"] != 1 or evidence["scope"] != "nine-interface-test-firmware":
            raise ValueError("unsupported complete firmware evidence")
        if evidence['producer_sha256'] != sha256(Path(__file__)):
            raise ValueError('firmware producer hash drift')
        current = _sources(source_root)
        if evidence["sources"] != current or set(evidence["outputs"]) != set(OUTPUTS):
            raise ValueError("firmware input/output manifest drift")
        for name, digest in evidence["outputs"].items():
            if sha256(resolve_local(build_root, name)) != digest:
                raise ValueError(f"firmware hash drift: {name}")
        usage = elf_usage(resolve_local(build_root, "full.elf").read_bytes())
        if usage != evidence["usage"]:
            raise ValueError("firmware usage differs from actual ELF")
        symbols = _elf_symbols(resolve_local(build_root, 'full.elf').read_bytes())
        for port, required in DRIVERS.items():
            if not set(required) <= symbols:
                raise ValueError(f"missing linked firmware driver: {port}")
        commands = read_json(resolve_local(build_root, "commands.json"))
        if any(command["exit_code"] for command in commands):
            raise ValueError("failed command in firmware evidence")
        # Evidence can be copied into a frozen packet; compare source path
        # suffixes rather than assuming the original absolute checkout path.
        compiled = [arg for command in commands if '-c' in command['argv']
                    for arg in command['argv'] if arg.endswith(('.c', '.s'))]
        required = list(APPLICATION) + [name for name in current
                    if name.startswith('vendor/hal/Src/') and name.endswith('.c')
                    and not name.endswith('/stm32f1xx_hal_pcd.c')]
        required += ['vendor/cmsis/system_stm32f1xx.c', 'vendor/cmsis/startup_stm32f103xb.s',
                     'vendor/usb/Core/Src/usbd_core.c', 'vendor/usb/Core/Src/usbd_ctlreq.c',
                     'vendor/usb/Core/Src/usbd_ioreq.c', 'vendor/usb/Class/CDC/Src/usbd_cdc.c',
                     'vendor/microchip/canfdspi/drv_canfdspi_api.c',
                     'vendor/wiznet/Ethernet/wizchip_conf.c', 'vendor/wiznet/Ethernet/W5500/w5500.c']
        if len(compiled) != len(required) or any(not any(arg.endswith('/' + name)
                for arg in compiled) for name in required) or not any('-nostdlib' in c['argv'] for c in commands):
            raise ValueError('incomplete command evidence for full firmware compilation/linkage')
        rows = stack_rows(resolve_local(build_root, "stack-usage.txt").read_text())
        if read_json(resolve_local(build_root, "stack.json")) != rows:
            raise ValueError('stack frame evidence differs from retained compiler output')
        units = {row['unit'] for row in rows}
        objects = {Path(arg).name for command in commands if '-c' in command['argv']
                   for arg in command['argv'] if arg.endswith('.o') and arg.split('/')[-1] != 'startup.o'}
        if units != {name[:-2] + '.su' for name in objects}:
            raise ValueError('stack frame evidence does not cover every compiled C unit')
        elf = resolve_local(build_root, 'full.elf').read_bytes()
        stack = stack_budget(rows, resolve_local(build_root, "disassembly.txt").read_text(),
                             functions=_elf_symbols(elf, kinds=(2,)),
                             exempt=runtime_exemptions(source_root))
        if stack['conservative_bytes'] > usage['stack_bytes']:
            raise ValueError("static stack budget exceeds reservation")
        timing = timing_budget(source_root)
        if read_json(resolve_local(build_root, 'timing.json')) != timing:
            raise ValueError('static timing report differs from source-bound analysis')
        return {"scope": evidence["scope"], "full_firmware_build_passed": usage["stack_bytes"] >= 4096,
                "hardware_tested": False, "timing_qualified": False, "usage": usage,
                "queue_model": read_json(resolve_local(build_root, 'queue-model.json')),
                "static_stack_budget": stack,
                "static_timing_budget": timing,
                "driver_coverage": {key: list(value) for key, value in DRIVERS.items()},
                "compiler_version": evidence["compiler_version"],
                "build_sha256": sha256(resolve_local(build_root, "build.json")),
                "limits": "Static cross-build only; 30-minute concurrent load, stack high-water, WCET, signal integrity and silicon errata tests remain unmeasured."}
    except (OSError, KeyError, TypeError) as error:
        raise ValueError(f"missing or invalid complete firmware evidence: {error}") from error
