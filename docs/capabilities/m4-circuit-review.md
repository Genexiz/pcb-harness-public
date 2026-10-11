# STM32 real-target candidate schematic

Date: 2026-10-10. Full M4 remains open. This continuation produces an actual
reviewable schematic and candidate BOM, with all nine interfaces, rather than
claiming a passed gate from another evidence flag.

The retained candidate `runs/m4/circuit-review-final-2026-10-10` contains104
physical components,30 part types,73 named nets and19 explicit NC contacts.
It preserves the eight core IC instances and adds WIZ550io plus95 support
instances. It contains no PCB, routing, fabrication exports or accepted
bootstrap manifest. `layout_allowed`, `release_eligible`, `milestone_complete`
and `independent_functional_acceptance` remain false.

## What is now concrete

- Direct STM32F103C8T6 pin assignments, five local100nF bypass candidates,
  bulk/analog bypass, reset/boot controls,8MHz HSE candidate and SWD.
- TPS62162DSGR connections,2.2uH/10uF/22uF LC targets,PG pullup and supply test points.
- USB2 Type-C candidate: duplicate contacts, separate5.1k CC Rd resistors,
  ESD/22R series candidates,1.5k D+ pullup and transistor VBUS-presence/attach
  circuit. VBUS is not directly connected to either board supply rail.
- Two MCP2518FD/MCP2562FD networks, separate40MHz crystal candidates,
  controller CS/IRQ pullups, supply bypass and default-open120R terminations.
- RS485 DE/nRE control and default pulldown, candidate TVS/termination;
  RS232 charge-pump caps and deliberate unused-input/output policy.
- WIZ550io SPI2/control connections,UART/I2C/SPI headers, test points and
  four groundedM3 mounting-hole candidates.

This is an explicit **support topology**, not a completed exact purchasing
BOM. Eighteen support types still use `UNSELECTED-*` identifiers; their
ratings, manufacturer curves, exact parts, mating parts and protection remain
unqualified. The CSV labels every row `UNCONFIRMED - DO NOT ORDER`; engineering
notes retain tolerance/CL/effective-capacitance and default-open choices.

## Original module CAD

The manufacturer [Eagle library page](https://docs.wiznet.io/Design-Guide/eagle_cad_library_of_wiznet_products)
links the retained WIZ550io v1.1 ZIP/member. The archive SHA-256 is
`89a1f912b7be9491eb1b48644b50562c249ddf4689c4afa576f71f2ab7ca8e37`;
`WIZ550io_V1.1.lbr` SHA-256 is
`db43a64d52c1aa966f3067e599a15338ac6d56221db19f2a834e37f9f33fa0a3`.
The importer retains all14 numbered pad identities, XY positions with the
Eagle-to-KiCad Y inversion,1.016mm drills and four3mm NPTH holes. Single-unit
symbol aliases are checked against J1/J2 manual numbering; pad12 is NC.

The original library does not specify copper diameter. A1.8mm candidate diameter
and inscribed circular adaptation of octagons are explicit engineering choices.
Original package lines are kept on F.Fab, not an asserted courtyard. Passive
Eagle pin types remain passive; v1.1-to-v1.2 equivalence, socket selection,
seating height, pad qualification, body/55-vs54mm conflict and redistribution
permission are not accepted by this conversion.

## Native result

KiCad10.0.6 opens the saved schematic, exports SVG and XML netlist. Exact native
endpoint sets match every73 named nets and all19 NC singleton nets. Local
symbol/footprint tables and project context resolve both frozen namespaces.
Schematic positions are on the1.27mm grid; there are no library-link or
endpoint-grid warnings in the final retained candidate. Visual inspection of
native crops fixed duplicate stacked-pin labels, field justification and
clipped/overlong value presentation. Full qualification notes remain in CSV.

**ERC is not clean:** exit5, four errors. Three are `power_pin_not_driven` for
5V/3V3/GND; one is `pin_to_pin` on the two controller SDO outputs sharing MISO.
The source templates model SDO as ordinary output. A source-reviewed tri-state
model and correct explicit supply-drive annotations are needed; no errors were
excluded and no saved exact-core type was silently rewritten. Native endpoint
consistency alone cannot prove physical power, legal shared-bus timing or USB
unpowered behavior. Raw ERC is retained without reinterpreting its coordinates.

## Reproduce

Obtain the original publisher ZIP from the linked Eagle page, retain the
`WIZ550io_V1.1.lbr` member, and create module-source JSON with the publisher URL,
member name, SHA-256, retrieval date and `human_confirmed=false`. Prior core and
pin packets must pass their original verifiers. Installed libraries are
captured before any derivative is constructed.

```sh
.venv/bin/python -m pcb_harness.orchestration.stm32_circuit \
  --pins runs/m4/core-pin-evidence-final-2026-10-10 \
  --eagle runs/m4/completion-2026-10-10/retrieval/wiz550io.lbr \
  --module-source runs/m4/completion-2026-10-10/retrieval/module-source.json \
  --output runs/m4/circuit-review-new
```

Exit2 is intentional. `verify_review(root)` reconstitutes parts, assets,
module metadata, circuit, annotated schematic, BOM and gate report from frozen
core/pin packets, authored topology/checks, library bytes and original Eagle
member. Updated derivative hashes cannot by themselves fabricate acceptance.
This protects against artifact drift, not coordinated malicious replacement of
all authored inputs and hashes or authentication of publisher claims.

Native checks are independent of the serializer:

```sh
KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
"$KICAD_CLI" sch export svg --output RUN/native/svg RUN/board.kicad_sch
"$KICAD_CLI" sch export netlist --format kicadxml --output RUN/native/netlist.xml RUN/board.kicad_sch
"$KICAD_CLI" sch erc --format json --severity-all --exit-code-violations --output RUN/native/erc.json RUN/board.kicad_sch
```

Replace RUN with the new candidate directory. After exports and visual crops are final, call
`pcb_harness.orchestration.native_candidate.write_native_summary(root, cli)`.
It creates `native-summary.json` once, binding the CLI executable digest,
retained schematic/input-integrity digest and every native artifact. The public
`verify_review` invokes native verification whenever native evidence exists;
missing/drifting/forged summaries fail. The native verifier reconstructs exact
endpoint/NC/component coverage and raw ERC claims; it reports four errors
separately from exact netlist consistency. Updating all authored/raw inputs and
hashes is still not publisher/process authentication.

## Remaining M4 work and scope rulings

1. Retain original ST DS5319/RM0008/ES096; the canonical alias retry timed out
   outside the sandbox. No original-file hash was invented.
2. Qualify all exact support MPNs, crystals/CL/ESR, bias-dependent capacitance,
   connector/socket packages, protected external5V and unpowered headers/USB.
3. Complete source-bound operating/pin/package facts,MAX3232 narrowSOIC evidence,
   independent electrical/errata review and actual critical confirmations.
4. Implement complete nine-interface firmware, build/map, bounded timing and
   IRQ/stack proofs; the existing576B resource probe has no peripheral drivers.
5. Complete power/thermal/module limits, revision-matched mechanics, selected
   fabrication profile and accepted native/ERC/bootstrap/parity.
6. Only then layout/routing and saved-board verification/release package;
   physical30-minute validation remains M5.

Ruling: Keep the established non-main checkout and approved v2 target. Local
candidate artifacts can be revised if the scope was misunderstood.

Ruling: A review-only schematic is legitimate while critical facts/errata are
open. The accepted `write_project` gate remains unchanged; no dummy errata
mitigation or stripped required fact admits a PCB. Misreading this draft as
accepted would risk manufacturing an unqualified board.

Ruling: The zero-ohm/inductor/explicitly closed-jumper rail-bridge check rejects
obvious supply ties only. Finite resistors, transistor junctions and ESD paths
need analog/off-state review; this graph is not a backfeed certification.

## Independent review and verification

One independent read-only whole-change review found two Important issues,
no Critical and no Minor. Both were reproduced before the fixes:

- Decorative5.08mm label wires could merge distinct caller nets even when
  upstream review passed. A real KiCad regression exported one net instead of
  two. Accepted `write_project` now retains direct labels; review-only outward
  wires reject unintended pin/wire contacts before serialization. Native
  regression verifies the two nets and all six literal resistor endpoints.
- Candidate verification ignored native-summary/artifact drift. Forged flags
  and post-summary changed crops passed. The new native verifier reconstructs
  raw report claims, binds CLI/source evidence, requires all native artifacts,
  detects image drift and missing summaries, and keeps layout/release false.

The fix pass uses observed RED-to-GREEN cases; no second review was dispatched.
Targeted converter/topology/producer/writer/symbol tests:76 passed. Final full
suite after both fixes: **612 passed in77.09s**, no skips. Fresh final packet
and native summary verification both pass; every73 named-net endpoint set,
all19 NC contacts and104 native components match. SVG/netlist exits are0;
ERC exit5 retains its four errors. Wheel build, dependency and whitespace
checks pass. These results cannot close full M4 by themselves.

The reviewer declined to certify procurement, missing ST originals, module
revision/socket mechanics, USB unpowered injection/protection, oscillator and
component tolerances, firmware/timing, power/thermal and fabrication/hardware.
Ruling: all remain unmet original gates; an engineering draft must not be
interpreted as their acceptance.
