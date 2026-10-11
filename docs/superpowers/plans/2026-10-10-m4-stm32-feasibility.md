# M4 STM32 pre-layout feasibility implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one independent whole-change review at the end. The user's instruction to continue M4 authorizes execution of the existing v2 design and roadmap gates.

**Goal:** Produce a reproducible, source-bound real-target feasibility report that distinguishes resource arithmetic from functional firmware, electrical, mechanical and native-circuit acceptance.

**Architecture:** Keep the M3 bundle/writers unchanged until the actual circuit is ready. A versioned STM32 benchmark and a separate resource checklist feed deterministic pin/DMA/EXTI and wire-time checks. A cross-compiled Cortex-M3 resource probe supplies actual ELF/map evidence, explicitly scoped below complete interface firmware. The report closes layout when any prerequisite remains unknown.

**Tech Stack:** Python 3.11+, existing strict JSON loader, Arm GNU Toolchain, freestanding C; official manufacturer documents retained locally with SHA-256.

**Spec:** `PCB Harness — Design Spec (v2).md`, sections 3, 8, 9 and 12; `PCB Harness — Development Roadmap.md`, M4.

## Global constraints

- STM32F103C8T6, LQFP48, 64 KB flash and 20 KB RAM. Nine interfaces remain present; both CAN networks use external controllers.
- External regulated 5 V; USB-only power unsupported. WIZ550io remains the Ethernet module.
- Inline execution on the existing non-main project branch; preserve M0–M3 evidence. No provider key, route search, native writes, merge or push.
- Source retrieval and automated review never create human confirmations. Typical current is not a maximum; a capacity probe is not complete functional firmware.
- Full circuit/asset review, ERC/bootstrap/parity and fabrication coverage precede layout. Missing evidence must appear by name in the report.

## Review focus

Check omitted interfaces or reserved pins, DMA/EXTI alias collisions, optimistic wire-time assumptions, source/build drift, and promotion of partial firmware or power estimates into a layout pass. Each gets negative tests in its owning task.

### Task 1: Freeze candidate parts, source manifest and resource allocation

Files: `benchmarks/stm32-communications/design.json`, `sources.json`, `fetch_sources.py`; `checklists/stm32-communications/resources.json`; `tests/test_stm32_feasibility.py`.

Consumes v2 target; produces local source IDs, exact candidate MPN/package assignments, physical LQFP48 pin allocation, UART DMA channels and bus/interrupt policies.

- [x] Record sourced facts separately from engineering choices; pin functions come from DS5319 table 5, DMA from RM0008 table 78, errata ES096.
- [x] Write negative tests for duplicate pins, wrong package pin number, absent interface, SWD/boot/clock reuse, illegal AF, native CAN, DMA and EXTI collisions.
- [x] Run `.venv/bin/python -m pytest tests/test_stm32_feasibility.py -q`; expect failure on missing evaluator.
- [x] Implement pure checks in `src/pcb_harness/orchestration/stm32_feasibility.py`; expect all resource negatives rejected and chosen allocation accepted.

### Task 2: Bound bus arithmetic and electrical assumptions

Files: same evaluator/design/test file.

Consumes allocation and engineering workload; produces explicit SPI utilization/blocking estimates and multi-rail current/thermal status.

- [x] Write tests for oversubscribed bus, zero clock, NaN/negative inputs, FIFO deadline miss, omitted clients, typical-only current and missing thermal bound.
- [x] Run targeted tests RED; implement wire-time arithmetic `8 * bytes / clock + supplied overhead`, summed client occupancy, worst non-preemptive blocking and FIFO arrival deadline.
- [x] Keep firmware CPU/WCET and actual traffic-envelope verification unknown. Unknown current or regulator loss/thermal evidence keeps power unknown.
- [x] Run targeted tests GREEN; retain formulas, units and every assumption in report.

### Task 3: Cross-compile a resource probe and bind evidence

Files: `benchmarks/stm32-communications/firmware/{probe.c,startup.c,stm32f103c8.ld,build.py}`, `src/pcb_harness/orchestration/firmware_evidence.py`, `tests/test_stm32_firmware.py`.

Consumes compiler path; produces fresh ELF, binary, map, section sizes, source/tool/output hashes and stack/reserve accounting. Scope is `resource-probe`, never complete USB/CAN/Ethernet drivers.

- [x] Test missing/tampered ELF/map/source, flash/data load accounting, explicit stack reservation and RAM/flash overflow. Run RED.
- [x] Build with Cortex-M3/Thumb, `-Os -ffreestanding -fno-builtin -nostdlib`, linker 64K/20K limits and explicit 4K stack. Retain compiler version and all commands.
- [x] Run the real cross build and evidence checker; expect probe fit but full firmware status unknown. Test a reduced memory linker budget rejects the image.

### Task 4: Retain pre-layout report and document the gate

Files: `src/pcb_harness/orchestration/{__init__.py,m4.py}`, `tests/test_m4_feasibility.py`, `docs/capabilities/m4-progress.md`, benchmark README, roadmap and root README.

Consumes benchmark/checklist/source snapshots/build evidence; produces hash-bound report with per-gate status and precise blockers. Reports are written to new run directories only.

- [x] Test missing source, changed input, report output reuse, incomplete firmware/power/mechanical/circuit evidence never permits layout/release.
- [x] Run `.venv/bin/python -m pcb_harness.orchestration.m4 --help` and real acceptance command; no native board mutation occurs.
- [x] Run full `.venv/bin/python -m pytest -q` outside sandbox when native tests require it; expect baseline and new tests green.
- [x] Request one independent whole-change review under executing-plans. Fix important findings with observed RED→GREEN tests. Record limits and rulings in progress docs.
- [x] Commit verified local work, without merge/push. If source/firmware/power/circuit gates remain unknown, M4 is in progress and layout remains closed; never mark the milestone complete from software tests.
