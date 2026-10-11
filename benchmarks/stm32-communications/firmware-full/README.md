# STM32F103C8T6 nine-interface test firmware

This is actual ARM firmware, not the earlier capacity probe. It links the pinned
ST STM32CubeF1 v1.8.6 CMSIS/HAL/USB CDC sources, Microchip MCP251xFD API and WIZnet
ioLibrary v3.2.0. Original sources, notices and hashes remain in `vendor/` and
`sources.lock.json`. The USB PCD derivative has its original hash, exact patch and
derivative hash in `adapters/derivatives.json`. The SPI transport header is an
application adapter, not an unmodified Microchip header.

Build from the repository root using the retained local toolchain (no network,
paid service or model-provider key):

```sh
.venv/bin/python - <<'PY'
from pathlib import Path
from pcb_harness.orchestration.firmware_complete import build_complete
root = Path.cwd()
result = build_complete(
    root / 'benchmarks/stm32-communications/firmware-full',
    root / 'runs/m4/full-firmware-2026-10-11-r2',
    root / 'runs/m4/toolchain/arm-gnu-toolchain-13.2.Rel1-darwin-arm64-arm-none-eabi/bin/arm-none-eabi-gcc')
print(result)
PY
```

The output directory must not exist. Keep old runs; choose a new run name for
subsequent builds. `full.elf`, `full.bin`, `full.map`, `stack.json`, `timing.json`,
`commands.json`, `symbols.txt`, `disassembly.txt` and host-test results are hashed
in `build.json`. The linker limits are exactly 64 KiB Flash and 20 KiB SRAM,
including an 8 KiB stack. No heap or dynamic allocation is used; USB class memory
is a single static allocation. Retained `.su` files give compiler stack frames.
Verification checks actual ELF allocation and defined driver symbols, input
inventory, commands, hashes and source-derived timing report. Build evidence
proves compilation and static capacity; it does not certify hardware behavior.

## Selected implementation

| Interface | Hardware / workload |
|---|---|
| USB CDC | Native USB FS, 128-byte frames every 8 ms; 128 kbit/s plus 10 Hz telemetry |
| UART | USART1 PA9/PA10, DMA TX/RX; 115200 8N1, 32 bytes / 8 ms |
| RS485 | USART2 PA2/PA3, PA1 DE/RE; same serial rate, half-duplex echo |
| RS232 | USART3 PB10/PB11, same serial rate through transceiver |
| I2C | I2C1 PB6/PB7, 100 kHz; address 0x42, write32/read32 every10 ms |
| SPI header | SPI1 PA5/PA6/PA7, PB9 CS; 750 kHz, 64 bytes every10 ms |
| Classical CAN | MCP2518FD CS PA4, interrupt PB0; 500 kbit/s, ID0x600, 8 bytes / 3 ms |
| CAN FD | MCP2518FD CS PA8, interrupt PB1; 500 kbit/s nominal / 2 Mbit/s data, ID0x601, 64 bytes / 4 ms, BRS |
| Ethernet | WIZ550io SPI2 PB13/PB14/PB15, CS PB12, reset PB5, ready PC13, interrupt PB8; UDP128 bytes / 8 ms |

The MCU uses external8 MHz CMOS HSE in BYPASS mode and PLL×6: SYSCLK48 MHz,
APB1 24 MHz, USB48 MHz. SPI1 internal controller accesses and SPI2 use6 MHz.
MCP2518FD clocks are20 MHz, PLL off. Native bxCAN stays unused to avoid the
USB/bxCAN shared memory conflict. The pin/clock layout must be compared with the
exact qualified board revision before programming. REV_ID0x2003 is required;
physical package marking still needs a separate errata applicability review.

Each network has a two-frame queue. USART RX uses three independent256-byte
circular DMA rings and64-byte per-pass quotas. CRC16 CCITT-FALSE and16-bit
sequence numbers detect corruption/loss/reordering. TX completion is recorded
separately from submission; RS485 DE goes LOW only after UART transmission
complete, rather than DMA completion. Serial framing drains periodically and
does not rely on IDLE. Shared SPI1 CS ownership forbids reentry, changes speed
with all CS HIGH and selects exactly one device. Microchip global scratch
buffers are only used in the non-reentrant main loop. Each CAN RX/TX/TEF FIFO has
8 slots; CAN RAM is initialized in32 bounded64-byte CRC-protected transactions.
USB PMA assignments do not overlap. USB interrupt work has a four-transfer quota
and a20 µs DWT bound on the ES096 suspend-reset wait. W5500 register-size reads
are bounded and changing values are deferred; unbounded `socket.c` polling is
excluded. DWT transaction limits, state deadlines, retries and counters expose
failures instead of claiming peripheral progress.

## Timing and physical acceptance

`timing.json` records wire time, ring fill time and finite polling deadlines
from the selected sources. The portable30-minute model executes the real core
queue/CRC/scheduler under an **assumed2 ms service interval**, and is explicitly
not silicon evidence. For example, serial32-byte half-duplex echo needs at
least5.556 ms at115200baud; the256-byte RX ring fills in22.223 ms. The SPI1
maximum single transaction deadline is1.433 ms; multiple transactions per CAN
service may add up to more than2 ms under faults. HAL/IRQ cycles and aggregate
healthy/fault service cost have not been independently proven. `wcet_proved` and
`timing_qualified` therefore remain false for a concrete missing timing proof,
not merely because a board has not yet been manufactured. A successful ELF
build must not bypass that prelayout timing gate.

Bring-up needs a regulated external5 V supply with the exact qualified board,
SWD programmer, verified silicon marking/REV_ID, clock readback, and isolated
traffic peers for all nine interfaces. No USB-only power claim is made. Verify
115200baud serial adapters, RS232 voltage levels and RS485 DE/RE/termination,
then qualify the half-duplex peer turnaround (below2 ms after request completion).
The I2C peer must latch a complete32-byte write and return it from a read at0x42.
The SPI peer may return the previous complete64-byte request during the next
transaction; prime this pipeline before the recorded acceptance interval.
It must release MISO when CS is HIGH and meet the documented electrical load.
Use two physically separate, properly terminated CAN peers with correct ID,
Classical/FD modes and rates; qualify exact10% offered bus load using a trace,
since wire stuffing and arbitration cannot be inferred from payload counters.

The Ethernet device is192.168.50.100/24, gateway192.168.50.1; its factory module
MAC is preserved. Firmware transmits UDP to192.168.50.1:5001 and receives on5000.
Use a private bench subnet with no conflicting address. USB VID/PID0483:5740 and
serialM4-TEST-0001 are experimental test identifiers; assigned identifiers and
unique serials are a separate shipping requirement.

`hardware_monitor.py` provides standard-library CDC/UART/RS232/RS485 and UDP echo
and telemetry capture. Example (replace devices, board ID and exact ELF hash):

```sh
.venv/bin/python benchmarks/stm32-communications/firmware-full/hardware_monitor.py \
  --usb /dev/cu.usbmodemTEST --uart /dev/cu.UART --uart /dev/cu.RS232 \
  --rs485 /dev/cu.RS485 --udp-bind 192.168.50.1 --seconds 1802 \
  --board-id YOUR_BOARD_REV_AND_SERIAL --firmware-elf-sha256 ACTUAL_ELF_SHA256 \
  --output /private/tmp/m4-hardware-capture.jsonl
```

Start recording after all peers have initialized. The monitor retains raw
samples and rejects bad CRC, short duration, missing ports, telemetry gaps,
underload, any loss/reorder/overflow/timeout increase, intermediate counter/clock
reset, excessive scheduler duration, invalid stack watermark and excessive
latency. The1% frame-rate allowance is only a capture-boundary tolerance.
Scheduler≤2 ms and echo≤100 ms are declared engineering acceptance targets,
not manufacturer limits. A monitor pass still has `hardware_tested=false` until
someone reviews identity/hash, simultaneous independent peers, clock, silicon
errata, stack high-water and electrical evidence. No physical capture is supplied
by this build.
