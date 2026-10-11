# M4 reviewable circuit completion implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline and one independent whole-change review. The latest explicit instruction is to finish the authorized v2 work without another check-in.

**Goal:** Complete the autonomous exact-support and circuit preparation through a reviewable nine-interface schematic and native netlist evidence; stop at actual external/human evidence requirements, never manufacture M4 completion.

**Architecture:** Preserve verified core preparation and pin packets. Import manufacturer module CAD into auditable local assets, freeze authored support inventory and explicit net assignments, and use existing M3 schema/review/writer contracts. Critical source gaps remain unconfirmed and are visible in both artifacts and reports. Native generation is permitted only when existing structural circuit/profile review passes; full-board layout remains closed.

**Tech Stack:** Python/jsonschema, KiCad 10.0.6 CLI, original WIZnet Eagle XML, existing exact-core assets.

**Spec:** `PCB Harness — Design Spec (v2).md` sections3,8,9,12; `PCB Harness — Development Roadmap.md` M4; `benchmarks/stm32-communications/circuit-draft.md`.

## Global Constraints

- Direct STM32F103C8T6, all nine interfaces, independent external CAN controllers, external regulated5V.
- No autorouter, no paid service or model API key; work in the established non-main checkout.
- Missing sources and critical confirmations cannot be invented; candidate assets and engineering choices never become manufacturer guarantees.
- Draft schematic/native connectivity is not functional or layout acceptance; layout/release/M4 status stays false until the complete-board gates really pass.
- Preserve user projects and existing runs; create new immutable outputs only.

## Review Focus

- Eagle pad/signal identity, Y-axis transform, rotation and NC are preserved without guessed header origins.
- Support inventory covers power/clock/USB attach and unpowered behavior, with no unspecified values represented as qualified purchasing parts.
- Shared SPI pins appear only once in interface allocation while endpoint connectivity remains complete.
- Report verifier cannot approve derived claims independently of its frozen source inputs.
- A clean netlist/ERC does not overstate missing source, package, firmware, thermal or human evidence.

### Task 1: Original module asset and explicit support topology

**Files:** new `src/pcb_harness/orchestration/stm32_circuit.py`, `tests/test_stm32_circuit.py`, benchmark support topology/checklist files, candidate inventory.

**Interfaces:** consumes verified core preparation and source-bound pin packets; produces a strict candidate bundle and independent expectations with frozen inputs.

- [x] Write failing tests for original Eagle mapping/coordinate conversion, tampered pins/source, circuit endpoint coverage and critical USB/CAN/power/boot negatives.
- [x] Run targeted tests; expected missing producer/behavior failures.
- [x] Implement bounded manufacturer CAD conversion and explicit candidate topology; retain unsupported module body/revision/socket constraints.
- [x] Run targeted suite; expected GREEN; retain original source hashes and local derivatives.

### Task 2: Reviewable candidate schematic and evidence closure

**Files:** real run packet, native exports and capability/progress/reproduction docs.

**Interfaces:** consumes Task1 bundle; produces native schematic/board bootstrap only under existing review, fresh CLI netlist/ERC/parity evidence, final remaining-work register.

- [x] Run actual producer into a new run; expected exit2 for unresolved complete-board gates.
- [x] Inspect native schematic render and native pin/net comparisons; fix generation defects with reproductions.
- [x] Verify hashes and all tests, wheel/dependencies/whitespace; expected GREEN.
- [x] Dispatch one independent review of the whole change, fix Important/Critical findings with RED-to-GREEN tests in one pass.
- [x] Commit local changes without push/merge; final report states reachable work done and exact human/external blockers.

## Exit criteria

A reviewable real-target circuit packet, not another empty evidence flag. Complete M4 still requires critical confirmations, firmware/timing, thermal/module measurements, fabrication and physical evidence. If original CAD or support facts cannot support safe native generation, preserve completed bundle and concrete failed gates instead of bypassing review.

Execution outcome: review-only schematic is complete; exact support qualification and full M4 remain open. Existing accepted writer refused unresolved errata as designed, so no PCB or gate bypass was added. Native ERC retains four declared model/drive errors; final review fixed two software findings in one pass.
