# M4 STM32 feasibility progress

Date: 2026-10-10. Status: pre-layout feasibility tooling implemented; M4 is not complete.

Execution plan: `docs/superpowers/plans/2026-10-10-m4-stm32-feasibility.md`.
Baseline: commit `63fc9d2`, clean existing branch `work/m0-kicad-capability`; 373 tests passed outside the sandbox in 62.02 s.

Ruling: Continue inline in the existing project checkout, as specified in the v2 design and roadmap, preserving its native paths and prior evidence. Creating a new checkout would require recalibrating paths without benefiting this read-only pre-layout assessment.

Ruling: The approved v2 design and explicit instruction to continue M4 provide scope/execution authority. Write the milestone plan and execute it without repeating approval questions. Any design change that changes the MCU or removes a port remains outside that authority.

Ruling: Full M4 layout depends on its pre-layout gate. A cross-compiled resource probe and estimated SPI occupancy do not establish complete functional firmware or measured WCET. Preserve unknowns until those dependencies have evidence.

## Retained result

Final post-review report: `runs/m4/feasibility-2026-10-10-final/report.json`, with input/source
snapshots and firmware evidence bound by `integrity.json`. Gate is closed:
`layout_allowed=false`, `release_eligible=false`, `milestone_complete=false`.
CLI returns2 for this result. This is a real-target candidate allocation,
not the synthetic M3 fixture and not an actual complete circuit.

Static allocation preserves all9 interfaces, reserves SWD/boot/HSE/power and
uses 45 of48 package pins. PA15/PB3/PB4 remain unused. No remap/JTAG disabling
is needed by the proposed default mapping. Three UART DMA TX/RX pairs consume
channels2–7; SPI1/SPI2 use bounded polling, I2C1 interrupts. External CAN
interrupts use EXTI0/1, Ethernet EXTI8.

Under the explicit full-payload workload and engineering overhead assumptions,
SPI1 utilization is25.82%, SPI2 3.81%. The external header is budgeted at
500kHz, slower than its selected562.5kHz divider, and limited to64-byte
non-preemptive chunks. These estimates do not validate firmware CPU/WCET,
short-frame CAN workloads, DMA/IRQ latency or the physical30-minute test.

Official Arm GNU Toolchain13.2.rel1 archive SHA-256 matched the publisher
checksum. Real Cortex-M3 ELF/map build: flash576 bytes, static data9104 bytes,
reserved stack4096 bytes, total RAM13200/20480 bytes. The build exercises real
CRC/queues and retains chosen buffer reservations. It contains no peripheral
drivers and cannot be used to assert complete firmware fit or board bring-up.
Host C tests check known CRC, invalid CRC rejection, queue-full and wraparound.

Engineering reserves: 3V3 load0.57A plus direct5V CAN PHY load0.16A. With a
chosen80% efficiency estimate, total5V input is0.63025A. Maximum-current,
loss/thermal and external-device load evidence is still unknown. WIZ550io
documents141mA typical, no maximum;132mA belongs to a different chip/module
scope. Selected CAN PHY is5V/VIO3V3, so its load is not hidden in the buck rail.

Seven of10 publisher source snapshots are retained. Full ST DS5319/RM0008/
ES096 downloads timed out/failed; ST-hosted attachment fallbacks returned HTML
and were not accepted as PDFs. Web inspection does not supply an original-file
hash. Frozen source failures remain explicit, rather than being replaced with
unverified mirrored documents.

## Evidence required before layout

- Complete interface firmware build/map, buffers/stack and bounded timing.
- Source-bound power/thermal design, including module maximum/validated limit.
- Complete exact BOM/passives/protection/clock/USB-C circuitry and audited
  symbol-pad assets; actual circuit review/native ERC/bootstrap/parity.
- Version-matched module/connector envelopes and mechanical drawing.
- Retained ST sources and silicon-specific errata/workarounds.
- Selected fabrication/assembly service and mandatory coverage.

M4 evaluator currently has no producer for these complete-board gates. They
remain explicitly unknown even if callers change flags or supply estimates.
The roadmap's full-board layout/routing/release package has not started.

## Verification and independent review

The initial suite passed 414 tests. An independent software reviewer found
three Important issues: incomplete ELF allocated-range/segment accounting,
FIFO waiting bounds ignoring a job's service period, and input/build capture
drift. Six reproductions failed before the one fix pass; all 49 M4 tests passed
after fixes. Two additional boundary cases already rejected the bad images.
Details and explicit scope rulings: [M4 review](m4-review.md).

The final resource probe build retains the same measured usage. The final
report returns CLI exit2 with all seven unresolved gate categories and passes
artifact integrity. The reduced8KB RAM linker negative rejects the probe with
5008-byte overflow, retained in `runs/m4/negative-ram-build/commands.json`.
Final full suite: **422 tests passed** outside the sandbox in61.81s, no skips.
Wheel build and dependency checks pass. These software results do not close M4.

## Engineering continuation, 2026-10-10

Plan: `docs/superpowers/plans/2026-10-10-m4-engineering-evidence.md`.
Baseline: `2c13cca`; existing non-main checkout and approved inline method
preserved. Source audit rejects HTML masquerading as PDF, incomplete PDF/PNG
envelopes and unsupported formats; envelope checks do not verify document
semantics or revision. Original seven publisher hashes remain unchanged;
the appended WIZnet drawing brings retention to8/11. Four outside-sandbox ST
canonical/legacy endpoint attempts timed out at25s. No original hash invented.

Fresh report: `runs/m4/engineering-2026-10-10/report.json`; copied dossier,
design/checklist/source manifest, publisher snapshots and real Cortex-M3 probe
are bound by integrity. Exit2, artifact integrity passed. Layout/release and
milestone completion remain false. Probe remains576B Flash/13200B RAM including
4096B stack, with no complete drivers.

`engineering.json` binds source observations and keeps engineering choices
explicit. Both MCP2518FD configurations pass RAM/FIFO/bit-rate arithmetic:
eight RX/TX/TEF slots, RX and TEF timestamps, Classical384/2048B and
FD1280/2048B. Both nominal500kbit/s and FD data2Mbit/s sample at80% with selected
40MHz SYSCLK. This does not validate TDC, oscillator/propagation, ECC/driver
setup, FIFO runtime service or hardware functionality.

CAN transceiver VIO is explicit on3V3 with2mA combined reserve; supply reserves
are3V3=0.572A/direct5V=0.16A. Existing80% efficiency estimate now gives0.6319A
5V input. Source conditional/no-load/typical currents are not full-load bounds.
Regulator initial accuracy/PSM behavior, loss/thermal and exact biased L/C need
qualification. All eight grouped loads retain incomplete full-load evidence.

Mechanical assessment explicitly flags WIZ550io54mm page vs55mm drawing, uses
56x27x25.5mm conservative screening and records missing connector/socket
envelopes.17 targeted ES096 policies are planned, not implemented; no physical
silicon marking/REV_ID or complete errata review exists. Source0x2003 aliases
multiple markings. `circuit-draft.md` gives core IC pin connections and concrete
USB-C/boot/reset/clock/protection/termination/header policies for all interfaces;
exact support BOM and audited pin-symbol-pad assets still require completion.

Ruling: Retain54/55mm as a source conflict until reference planes are established;
screen conservatively but do not accept the footprint — cost if wrong: extra
mechanical review or allowance, rather than an undersized board envelope.
Ruling: Keep100kHz I2C target and make repeated-start/rise-time/slave-stretching
conditions explicit — cost if wrong: a documented design revision is needed;
never silently reduce the interface rate or claim firmware compliance.

Targeted verification after independent review:96 M4 tests passed, including
nine RED-to-GREEN cases for VDD/VIO fact applicability, full inventory/regulator
coverage and concurrent source-file replacement. The real cross-build passed
and `runs/m4/engineering-final-2026-10-10` has valid artifact integrity, CLI
exit2 and the same seven unresolved prerequisites. Review findings, rulings and
verification are in [M4 engineering review](m4-engineering-review.md).
Final full suite outside the sandbox:469 passed in63.81s, no skips. Wheel build,
dependency check and diff whitespace check passed. This completes the engineering
evidence continuation; full M4 remains open before layout.

## Core asset continuation, 2026-10-10

Inspected installed KiCad10.0.6 libraries and retained six IC template/pad
candidate mappings. Exact CAN SOIC/FD symbols and WIZ550io assets are absent;
the installed THVD1450DR default footprint conflicts with TI's SOIC orderable
part. No substitute MPN or accepted real-target asset was introduced.

The real TPS62162 WSON footprint exposed stencil/NPTH ownership handling in
the auditor/writer. Five positive cases were RED before the repair; full suite
477 tests now passes, with two preserved copper negatives. A saved-copy
synthetic native bootstrap with stencil/NPTH shapes passes ERC/geometry/parity
and exact netlist. Details and unchanged full-board prerequisites:
[core asset inspection](m4-core-assets.md).

## Exact core asset preparation, 2026-10-10

Prepared six standalone exact-MPN symbol/footprint assets and the core BOM for
eight ICs plus one unresolved WIZ550io instance. Source libraries/footprints and
candidate/design/source-link inputs are captured and integrity-bound before
construction; installed files are unchanged. Missing pinout/package fact IDs,
twelve support categories and module mechanics remain explicit.

The final `runs/m4/core-assets-final-2026-10-10` report returns2 and passes retained
structural/integrity checks, with accepted real-target assets0. Full M4 remains
open; no actual STM32 schematic/native circuit acceptance or layout is claimed.
[Preparation, scope rulings and reproduction](m4-core-preparation.md).
Independent review found two Important admission/semantic-binding gaps; sixteen
RED-to-GREEN cases close these and related report consistency boundaries.
Six standalone symbols open/export in KiCad10.0.6; full board gates remain open.
Final full suite528 tests passes in66.73s, no skips; wheel/dependency checks and
final retained semantic/integrity verification pass. This closes the core asset
preparation continuation; exact support BOM and complete source-bound circuit
remain subsequent work.

## Core pin evidence continuation, 2026-10-10

Authored explicit manufacturer-to-symbol numbered aliases for all six core IC
types and froze them with the verified core preparation and original sources.
Five retained publisher PDFs bind candidate observations for55 pins and10 M3
identity facts. STM32's48-pin inventory has no retained original PDF/hash;
no MCU identity fact is manufactured. All facts remain unconfirmed, accepted
real-target assets remain0 and layout/release/M4 completion remain false.

The retained MAX3232 source has no exact MAX3232IDR ordering row or narrow-D
land-pattern appendix; this remains a qualification gap, with no MPN change.
The new packet's verifier reconstructs its report/facts/aliases from frozen
inputs and rejects overstated acceptance even if derived hashes are updated.
See [core pin evidence and reproduction](m4-core-pin-evidence.md).

Independent review found one Important retrieved-URL admission gap; two
observed RED-to-GREEN cases close it, plus one strict Boolean source-metadata
case. Final preparation/packet suite70 passes; full suite561 passes in71.64s,
no skips. Final retained packet: `runs/m4/core-pin-evidence-final-2026-10-10`;
hash/semantic verification, wheel/dependency and whitespace checks pass.
Core pin evidence preparation is complete, while full M4 remains open.

## Real-target review schematic continuation

The nine-interface candidate now has104 physical components,30 part types,
73 named nets and19 explicit NC contacts. Original WIZnet Eagle CAD supplies
reviewable module header geometry. KiCad10.0.6 opens/exports it and native
netlist endpoints match; ERC retains four errors (three missing power-drive
annotations, one shared MISO output-type model). Support topology is concrete,
while18 support types still need exact purchasing parts/qualification. The
accepted writer gate is not bypassed; no PCB/layout/release was produced.
See [candidate schematic and remaining M4 work](m4-circuit-review.md).

Final continuation verification:612 tests passed in77.09s, no skips. One
independent review found two Important issues (label wires merging nets and
native sidecar escaping verification), both fixed with RED-to-GREEN tests.
Final retained packet: `runs/m4/circuit-review-final-2026-10-10`; full candidate
and native verification pass with four ERC errors retained. Full M4 remains
open; see the linked evidence/remaining-work register.

## Integrated source/support/firmware continuation — 2026-10-11

The current 141-component/57-type/99-net circuit has zero KiCad 10.0.6 ERC
violations at every severity, with KiCad's four default-ignored checks and three
declared supply-drive markers, and exact exported netlist endpoints. All nine
real drivers cross-compile to 34,708 bytes Flash and 17,160 bytes RAM, including
8,192 bytes stack. Source recovery and exact support packets are captured and
reverified. The historical baseline files remain byte-identical to their
committed versions beside `qualified-design/`.

An independent review found 10 Important issues: authored gate flags, dropped
sub-packet blockers, untracked required facts, in-place baseline edits and
overstated docs. They are fixed with regressions. The sealed
`runs/m4/completion-2026-10-11-r3` reports 9 pre-layout blockers, including
power/thermal, errata and USB/protection; all 116 required facts are recorded, unconfirmed. M4 is
not complete. See the [integrated completion checkpoint](m4-completion.md).
