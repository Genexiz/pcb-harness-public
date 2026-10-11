# M4 pre-layout tooling review

Date: 2026-10-10. Base: `63fc9d2`. Reviewer: independent read-only subagent under
`executing-plans` / `requesting-code-review`. Full M4 milestone remains open.

Initial verdict: request changes; 3 Important, 0 Critical, no deferred Minor.
One fix pass completed with observed RED-to-GREEN reproductions; no re-review
was dispatched. Gate closure was correct before and after these fixes.
Final full suite:422 passing tests in61.81s, including all49 M4 tests, with no
skips. Final artifact integrity and copied probe verification pass.

1. ELF accounting omitted RAM PT_LOAD memory extent and allowed a flash
   NOBITS allocation past the physical end. Fix: include segment memory extent,
   validate full flash/RAM ranges and reject overlapping allocated sections.
   `test_ram_load_extent_counts_even_when_larger_than_named_sections` failed
   with28 instead of20000 bytes; flash NOBITS and overlapping allocations were
   accepted before fixes. These now pass. Actual flash/RAM boundary negatives
   and the real reduced8KB linker negative are also covered.
2. CAN FIFO wait bound used only scheduler tick, not client service period.
   Fix: wait `max(scheduler_period, client_period)` plus blocking and service.
   `test_can_fifo_bound_includes_its_own_service_period` previously accepted
   period0.1s/arrival9.99Hz/FIFO1 although its response bound exceeds deadline;
   it now rejects that configuration.
3. Report could assess old inputs while retaining changed input/build copies.
   Fix: capture design/checklist/source manifests before assessment; verify
   and report the captured firmware build. Controlled input mutation and
   replacement valid build metadata tests failed before the fix and now pass.

Declined-to-judge rulings, kept as explicit prerequisite gates:

- Complete interface firmware fit/functionality: outside this resource-probe
  software review; no complete drivers exist. Cost if mistaken: premature
  capacity/functional claims. Keep `FULL_FIRMWARE` unknown.
- Hardware WCET/concurrent traffic: no board execution occurred. Cost if
  mistaken: runtime FIFO/CPU loss despite arithmetic fit. Keep timing unknown.
- Silicon-specific errata: original ST snapshots and selected silicon revision
  are missing. Cost if mistaken: missed I2C/USB workarounds. Keep `ERRATA` and
  source integrity gate closed.
- Electrical/power/thermal/mechanical/native circuit acceptance: estimates and
  candidates are not a complete circuit or physical implementation. Cost if
  mistaken: incorrect supply, pin mapping or physical fit. Keep these gates
  unknown and do not start layout.
- Fabrication/release readiness: no selected fully confirmed manufacturing
  service or complete board exists. Cost if mistaken: invalid production
  artifacts. Keep fabrication/release eligibility closed.

Continuation rulings: use existing authorized inline checkout to preserve
native paths; execute the already approved v2 target after the explicit M4
continuation instruction; preserve failed source retrieval rather than invent
hashes. Costs if wrong are isolated implementation changes needing revision,
path recalibration, or additional source review respectively. No MCU/port
change, native mutation, merge, push or manufacture request was made.
