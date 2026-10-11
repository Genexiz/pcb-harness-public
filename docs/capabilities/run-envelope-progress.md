# Execution ledger — plan: docs/superpowers/plans/2026-10-09-run-envelope.md

- User authorized continuation inline 2026-10-09. Current clean branch work/m0-kicad-capability, HEAD 83095d6. Reuse the existing checkout per the established execution preference.
- Live preflight: KiCad 10.0.6; no /tmp/kicad socket; current tools include no PCB Harness host tools. Exact scratch-open request sent while independent M2 preparation continues.
- Ruling: implement the already specified M2 envelope while native acceptance is unavailable — protects actual future experiments without pretending the native gate passed — cost if wrong: boundary ergonomics may need revision before routing acceptance.
- Ruling: count every admitted write request, including replay/validation/native-gate failures, and never interrupt internal rollback — conservative accounting and atomic recovery — cost if wrong: experiments may spend budget on unusable calls and require a fresh versioned run.
- Ruling: limits freeze at launch; clock starts on first write, includes downtime; existing journals without budget evidence require a fresh run directory — avoids accidental counter reset — cost if wrong: legacy runs become inspection-only through the old code until explicitly migrated; no silent migration provided.
- Preflight: service owns lease/serialization; Kernel keeps its action identity/recovery contracts; budget wrapper admits before dispatch and persists terminal outcome; SDK invalid write arguments must use the same wrapper. Native write gate remains closed.

- Task 1 RED: 18 failures + 5 setup errors from absent run-envelope module. GREEN: 23 focused cases; durable limits, sequential attempts, clock/deadline, incomplete/corrupt/I/O evidence covered.
- Task 2 RED: 11 boundary cases failed (missing service limits/CLI flags and migration guard). GREEN: 61 service/SDK/envelope cases, including actual modern/legacy STDIO.
- Extra restart regression RED: monotonic elapsed vanished across reopen when wall clock lagged. Root cause: only raw wall timestamps were durable. Persisted elapsed watermark + reopened monotonic baseline; GREEN: 64 focused cases. Runtime truncation and expired-run inspection checks also passed.
- Task 3 acceptance script/docs/examples prepared; whole-suite and fresh whole-change review next. No model provider or key handling added; native gate unchanged.

- Verification before review: whole suite 205 passed in 17.21s, pip check clean, diff check clean. Real STDIO smoke report runs/mcp/budget-acceptance-2026-10-09/report.json PASS (modern+legacy, six admissions per mode, invalid/replay/stale/checkpoint/restore accounted; read/verify/image after exhaustion). Native CLI tests included; live native IPC/host still unverified.
- One fresh budget-only review dispatched; no duplicated earlier MCP/visual/M1 review.

- Actual host refresh after user Continue: current Codex chat now discovers 14 pcb_harness tools; pcb_status succeeds with real frozen budget metadata, pcb_connect returns BACKEND_UNAVAILABLE/connection refused (no PCB Editor socket). Report runs/mcp/host-discovery-2026-10-09/report.json. Host discovery/call is now proven; successful native connection/vision/mutations still pending.

- Fresh review: 3 Important, no Critical. Confirmed RED all three: idle monotonic elapsed lost on reopen; complete-but-unfsynced terminal row accepted on reopen; raw legacy arguments-array write escaped tool-schema admission. GREEN: 67 focused cases after one fix pass.
- Fixed time continuity using persisted first-admission monotonic timestamp and verified boot identity. Unknown/changed boot or backward clocks fail closed; no query writes needed. Ruling: unknown/rebooted clock epoch blocks resumed writes — time continuity cannot be proven — cost if wrong: conservative restart denial even with a usable project; explicit reconciliation remains future scope.
- Fixed durability with fsynced pending marker before admission and clear after fsynced terminal outcome, recreating marker on directory-durability failure where possible. Failed terminal outcome retains original board-result evidence; no retry/refund.
- Fixed malformed argument containers with public SDK middleware before typed parameter validation; transport INVALID_PARAMS is retained while identifiable board writes are counted. Completely unidentifiable malformed JSON remains transport failure outside board admission.
- Extra boundary tests cover changed boot epoch, clock-failure latch across reopen and failed marker-removal durability; full verification next. No re-review dispatch; previous review findings addressed with covering regressions.

- Final verification after the one review fix pass: 211 passed in 18.26s; pip check clean; real modern/legacy STDIO report runs/mcp/budget-reviewed-2026-10-09/report.json PASS; git diff --check clean. All 3 Important review findings have RED→GREEN coverage; no deferred minors from this review.
- Tasks 1–3 complete for this slice. Native M1 acceptance, live host vision, tiny-board five-run routing, full manufacturing profiles/STM32 design and public licensed release remain incomplete. No unsafe automatic recovery, API key, autorouter, push or merge introduced.
- Keep existing local work branch and checkout as authorized; no integration/publication action requested. Evidence stays under ignored runs; code/tests/plans/docs committed locally.
