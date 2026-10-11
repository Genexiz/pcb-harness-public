# M4 core pin evidence implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; one independent read-only review at completion.

**Goal:** Bind manufacturer pin names and package observations to the six prepared core assets and retained source revisions, producing unconfirmed M3 identity facts for circuit work.

**Architecture:** Author explicit per-pin manufacturer-to-symbol aliases from publisher pin tables. A deterministic local runner freezes the verified core preparation, observations, source lock and available PDF bytes, then compares the aliases with actual symbols/pad ownership. Its verifier reconstructs the report/facts from frozen inputs. Missing ST bytes remain missing; AI observations never manufacture human confirmation.

**Tech Stack:** Existing Python JSON/schema/asset tooling; KiCad-derived local artifacts; bundled PDF tools for read-only source inspection.

**Spec:** `PCB Harness — Design Spec (v2).md` sections 3/4/9/12; `docs/capabilities/m4-core-preparation.md`; `benchmarks/stm32-communications/circuit-draft.md`.

## Global constraints

- Preserve STM32F103C8T6 and all nine interfaces; exact core MPN/package/source associations remain calibrated.
- No editor writes, inference provider key, route optimization, fabrication request, merge or push.
- Existing prepared parts/assets remain unchanged. Observations are candidate evidence, never automatic confirmation or electrical/land-pattern acceptance.
- Retained original documents and library derivatives stay in ignored runs; public metadata contains authored observations, hashes and locators only.
- Layout/release/M4 completion remain false. Support BOM, WIZ550io, firmware, power, mechanical, errata and fabrication gates remain open.

## Review focus

- Missing or altered PDF bytes must not produce source-bound facts; unavailable entries must not carry fabricated original hashes.
- Number-set equality must not hide an alias mapped to a wrong pin or a changed prepared symbol.
- Duplicate/missing parts, unexpected fields, asserted human confirmation and source/package substitution fail admission.
- Updated derived hashes must not hide changed facts, counts, blockers or accepted status.
- Frozen source files and core preparation must survive original-input edits and reject unsafe/overlapping output paths.

### Task 1: Author and audit core pin/package evidence

**Files:** `benchmarks/stm32-communications/core-pin-observations.json`, `src/pcb_harness/orchestration/core_pin_evidence.py`, `tests/test_core_pin_evidence.py`, `docs/capabilities/m4-core-pin-evidence.md`, benchmark README and M4 progress.

**Interfaces:** `prepare_pin_evidence(core_root, observations_path, source_lock_path, source_root, output)` freezes all inputs into a new run and returns the candidate report. `verify_pin_evidence(root)` checks hashes and recomputes report/facts/observations against the frozen verified core run. CLI takes the five corresponding paths; exits2 for unresolved prerequisites.

- [x] Inspect publisher pin tables and package/order codes for all six parts, record each manufacturer name and explicit corresponding symbol name, and mark source-unavailable STM32 observations as such.
- [x] Write synthetic positive/missing-source tests plus negative cases for duplicate/missing/changed pins, incorrect package/source links, source drift/unsafe paths, claimed confirmation, and changed derived facts/report even with refreshed derived hashes.
  ```python
  report = prepare_pin_evidence(core, observations, lock, sources, output)
  assert report['accepted_real_target_assets'] == 0
  assert not report['layout_allowed']
  assert verify_pin_evidence(output)
  ```
  Run `.venv/bin/python -m pytest tests/test_core_pin_evidence.py -q`; expected RED because producer is absent.
- [x] Freeze source inputs before evaluation. Verify complete core preparation. Admit exact part/ref/package/source identity and complete one-to-one numbered aliases. Hash each available original PDF from the same captured bytes; reject unavailable entries with hashes and mismatched publisher URLs. Generate strict M3 unconfirmed identity facts only for sourced observations. Reconstruct derivatives in verifier.
- [x] Run targeted tests GREEN, then the real runner against `runs/m4/core-assets-final-2026-10-10` and `runs/m4/engineering-final-2026-10-10/sources`. Expect CLI2, five source-bound pin inventories, STM32 unavailable, no confirmed facts or accepted assets.
- [x] Run full suite, wheel/dependency/whitespace checks and one independent review of this continuation. Repair Important findings with observed RED-to-GREEN tests. Retain reproduction/evidence/scope rulings and commit verified work.

## Completion boundary

This completes the core pin evidence packet and unconfirmed identity facts, not circuit acceptance. It deliberately does not claim a qualified land pattern, purchasing availability, full support BOM, WIZ550io mechanics, electrical limits, firmware or a working board.
