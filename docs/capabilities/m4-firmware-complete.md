# M4 nine-interface firmware build and remaining timing gate

Verified on2026-10-11 with the retained Arm GNU Toolchain13.2.Rel1. The genuine
STM32F103C8T6 test firmware links all nine selected drivers from pinned official
ST/Microchip/WIZnet sources. This is separate from the earlier resource probe.
No download, paid service or model-provider API key was needed for this run.

Build instructions, board mappings, source/license provenance and physical peer
contracts are in `benchmarks/stm32-communications/firmware-full/README.md`.
Producer: `src/pcb_harness/orchestration/firmware_complete.py`.
Fresh artifacts: `runs/m4/full-firmware-2026-10-11-r2/` (post-review rebuild; the earlier `full-firmware-2026-10-11` predates the stack-evidence fix and no longer verifies). The stack bound is rebuilt from retained GCC `-fstack-usage` output (`stack-usage.txt`). Every linked compiled C function needs a frame row; only startup-assembly symbols and `__` runtime helpers use the 256-byte reserve.

| Result | Actual retained evidence |
|---|---|
| Flash | 34,708 bytes /65,536 |
| SRAM including stack | 17,160 bytes /20,480 |
| Static data/buffers | 8,968 bytes |
| Reserved stack | 8,192 bytes |
| Conservative compiler/call/IRQ stack bound | 5,856 bytes, conditional on documented callback/non-reentrancy restrictions |
| Queue simulation | 1,800,000 ms, all nine ports progressing, zero overflow under assumed2 ms service |
| Hardware tested | false; no physical capture supplied |
| Static CPU/IRQ timing qualified | false; aggregate WCET proof is still missing |

`full.elf`/`full.map`/`full.bin`, all command outputs, the compiler hash, source
inventory and output hashes are recorded in `build.json`. `timing.json` carries
source-bound wire/buffer/poll bounds. Verification reads allocation and driver
symbols from the actual ELF; editable `nm` text cannot certify an absent driver.
The pinned vendor inventory must match exactly, including license files. Every
compiled production source and the link command must appear in command evidence.

Focused executable validation is18 tests in `tests/test_firmware_complete.py`.
They run actual C protocol/CRC/queue/arbitration code, the unmodified Microchip
CAN timing API, the real ARM cross-build, and a portable30-minute queue model.
New adversarial regressions were observed RED before GREEN for untracked/omitted
vendor files, capture underload/intermediate resets/stalls, forged ELF driver
text, missing command/stack evidence and GCC optimized-clone stack accounting.
The latter was an actual analysis bug: `.su` uses `name.isra` while disassembly
uses `name.isra.0`; the earlier implementation silently omitted those frames.

## Concrete timing gap

The source provides a1.433 ms maximum SPI1 transaction deadline, a1 ms SPI2
transaction deadline, UART32-byte round-trip wire floor5.556 ms, I2C32-byte
write/read wire floor5.940 ms, external SPI64-byte wire floor0.683 ms and UART
RX-ring fill time22.223 ms. These numbers are arithmetic bounds or source
policies, not measured silicon values. A CAN service makes multiple SPI
transactions, and W5500 service also performs multiple transactions; their
individual bounds do not prove the total scheduler pass finishes in2 ms.
CPU/IRQ/callback cycle costs, HAL bounded-iteration costs and aggregate service
bursts need an independent static WCET proof or measured capacity evidence.
The queue-model2 ms assumption must not bypass that missing prelayout timing
proof. This gate is not being held solely because M5 physical acceptance has
not yet run.

## Physical dependencies

For M5 acceptance, retain board revision/serial, package marking/REV_ID, exact
programmed ELF hash, clock/line-rate readback, SWD stack high-water evidence and
simultaneous peers for USB/UART/RS232/RS485/I2C/SPI/two separate CAN networks/UDP.
The standard-library monitor and exact peer requirements are already supplied.
It rejects underload, CRC/loss/reorder/overflow/timeouts, intermediate reset,
telemetry gaps, invalid stack watermark and excessive scheduler/echo latency.
It still leaves `hardware_tested=false` until identity, line-rate/electrical and
errata evidence is reviewed. No fabricated measurements or human confirmations
are included in this software build.
