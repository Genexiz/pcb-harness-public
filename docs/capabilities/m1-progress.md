# Execution ledger — plan: docs/superpowers/plans/2026-10-03-m1-kernel.md

- Resume 2026-10-08: user authorized work at <repository>. Reuse existing work/m0-kicad-capability branch; original uncommitted M1 source/tests preserved.
- Prior tasks 1–3 have existing RED→GREEN evidence under runs/kernel and runs/capability; fresh reviewer kernel_review already completed. Resume its remaining fix/native verification pass; no duplicate reviewer dispatch.
- Ruling: repository moved and KiCad upgraded to 10.0.6. Reinstall local editable package; add wheel 0.45.1 to local venv for installation. Cost if wrong: environment mismatch; package path and suite verified.
- Baseline suite: 99 passed, including real native CLI cases, on KiCad 10.0.6.
- Ruling: native flip gated to verified major 10.0 with patch >=6; older/future major stays unavailable pending native contract tests. Cost if wrong: lost capability on future version, never speculative mutation.
- Pre-flight: contracts consume advertised backend capabilities; Kernel consumes checkpoint token/revision and journal evidence; CLI parser remains fail-closed. New native 10.0.6 needs post-publish flip/readback and saved-file parity verification.
- Native GUI tools not available this turn; no IPC socket observed. Requested user open exact scratch board while independent work continues.

- New regressions RED: checkpoint evidence/readback failure (2), flip version gating (6), advertised side-change/explicit flip validation (2); 10 failed, 52 passed before implementation.
- GREEN: 62 Kernel/IPC unit tests passed after fail-closed checkpoint attempts and native flip contract changes. Memory backend keeps flip unavailable; real IPC uses native command, never edits layer alone.
- M0 flip prototype corrected to validate staged reply, push then read published pads, then guarded revert. Original unsupported 10.0.0 never reached this branch; new 10.0.6 needs native acceptance.
- Native smoke expanded: server/socket evidence, stale/locked rejection, flip/side placement/pad readback and same-state journal resume replay.

- Whole suite after fixes: 109 passed on KiCad 10.0.6. Native DRC/ERC/parity/SVG on immutable fixture also PASS, artifacts runs/capability/kicad-10.0.6-cli.
- Pin wheel 0.45.1 in build/dependency inputs so the documented no-build-isolation editable install works on a fresh venv; no global packages changed.

- Native settings-conflict acceptance prepared: external saved min-clearance edit must survive denied restore; Kernel must block subsequent writes; only exact probe-owned bytes can be explicitly cleaned up afterward. This is a conflict test, not an automatic recovery path.

- Action result revision contract RED→GREEN: accepted and rolled-back routes now retain before_revision plus current/after revision. Kernel tests 50 passed. Native backend remains pending current GUI acceptance.
- Initial Kernel guide documents scratch restrictions, ignored/temporary findings, leases, durable identity binding, relocation and uncertain-state behavior; broader spec contracts remain explicit future scope.

- Prior fresh review findings carried forward: journal/checkpoint origin binding; durable accepted state + stale historical replay; restore-evidence failure latch; essential ignored-check audit. Associated regression tests remain green in the whole suite. Location/multiplicity, unsupported side changes, recovery flags and query revision findings also covered.
- Final verification this continuation: 111 passed in 12.50s (64 Kernel/adapter, 37 M0 report/safety, 10 real CLI). KiCad 10.0.6 immutable fixture DRC/parity/ERC/SVG PASS. New flip/zone/conflict native acceptance scripts are prepared and syntax-checked, not run.
- Task 4 incomplete: no /tmp/kicad IPC socket after independent work. User request to open exact scratch board remains pending; no native UI tool available in this turn. No new M1 native pass or milestone completion claimed.
- Ruling: preserve previous one-fresh-review/fix-pass evidence; do not dispatch a duplicate re-review of that same resumed implementation. New flip contract and checkpoint/result fixes have RED→GREEN tests, but native verification remains required. Cost if wrong: undiscovered native divergence; gate M1 completion on actual acceptance runs.

- User steering 2026-10-09: Subscription-first MCP is now primary; no required LLM provider key. Native M1 acceptance remains pending; M2 MCP wrapper follows it. Codex host owns inference/sign-in, Kernel owns action validation/journal/DRC. No MCP code or host registration claimed yet.

- MCP integration review 2026-10-09 tightened checkpoint capture: backend receives expected_current, token binds capture_before_revision, and Kernel refuses a foreign captured baseline before applying intent. Native save may rebase saved file hashes only with unchanged serialized live board and verified copied bytes. Pure Memory concurrent-capture regressions passed; actual native save semantics still need current GUI acceptance.

- Native continuation 2026-10-09: user enabled KiCad API; exact scratch connects on api.sock, server 10.0.6. Actual Codex pcb_summary + live render succeeds and image is observed. Disconnect MCP project lease before standalone probes.
- Native M0 RED: FlipItems query became visible before push, unlike UpdateItems staging assumption. Probe dropped commit then full-text guard caught regenerated R1 property UUIDs; stopped before any further mutation. Geometry/copper/project files unchanged. Explicit reconciliation compared complete parsed state: only four R1 property UUIDs differed; fresh exact text/hash guard then native revert restored full semantic baseline and all saved bytes. Raw failed run retained; no retry or guard weakening.
- Ruling: specialize flip visibility evidence, do not assume UpdateItems staging applies to FlipItems — observed native 10.0.6 query disproved it — cost if wrong: future native versions may change visibility; still require post-push side/pad readback and exact baseline restoration. Persist post-save baseline text/digests for recovery evidence.

- Native M0 GREEN: runs/capability/kicad-10.0.6-ipc-reviewed-2026-10-09/report.json, 10 supported operations, baseline_restored=true. Flip side/pad readback and guarded baseline revert verified; save/drop serialization details retained.
- Native M1 GREEN: runs/kernel/native-10.0.6-2026-10-09/smoke.json PASS, short rollback, stale/locked rejection, flip/place-side/move/route/delete/via/zone/refill, same-state action replay and journal resume, full exact baseline restore, final native DRC/connectivity clean.
- Native settings conflict GREEN: runs/kernel/native-conflict-10.0.6-2026-10-09/conflict.json PASS; externally changed settings bytes preserved, next write RECOVERY_REQUIRED, only own exact probe change explicitly cleaned up; final baseline restored.
- Next slice: unlock MCP mutations only for the actual connected native backend on exactly tested 10.0.6; other versions stay gated. No arbitrary enable flag or tool added. Existing probe changed saved-file byte revision, so use an explicit new MCP experiment run after proved baseline rather than clearing the old journal.

- MCP version-gate RED: actual 10.0.6 acceptance predicate test failed (old hardcoded false); old/future versions remain correctly denied. GREEN: 45 service/protocol/budget cases; connected instance identity prevents a foreign backend version from unlocking edits.
- Actual native STDIO GREEN: runs/mcp/native-acceptance-2026-10-09/report.json, real checkpoint/move/readback/replay/restore/known-short rollback/reconnect, final native geometry/connectivity clean. No model inference/provider key used.
- One fresh review of the newly unlocked exact-version gate/probe slice dispatched; previous whole M1/MCP reviews are not repeated. Full regression and host config reload remain next.

- Fresh gate-only review: one Important prerelease/git-build bypass, no Critical/Minor. Root cause: checking numeric triplet without full server release string. Confirmed RED: 10.0.6-rc1 and 10.0.6-12-gdeadbeef incorrectly unlocked. Fix pins full_version=10.0.6 as well as triplet, independent of the binding API build string. No re-review needed; covering tests and fresh native smoke verify final behavior.
- Ruling: unlock only the exact tested stable 10.0.6 native instance — no speculative acceptance of other builds — cost if wrong: usable future/dev builds stay unavailable until their acceptance is run.
- Ruling: select an explicit new host experiment journal after verified baseline restoration, keep the pre-probe old journal intact — external native probes changed saved-byte revisions — cost if wrong: old session remains unusable for writes; no uncertain history is cleared or reused as current evidence.

- Final verification after the one gate review fix pass: 218 passed in 17.50s; pip check clean; real native STDIO runs/mcp/native-reviewed-2026-10-09/report.json PASS after exact full_version pin. Final saved-project copy runs/kernel/native-final-2026-10-09/summary.json: native DRC+schematic parity/ERC verified, zero issues. Immutable tracked fixture unchanged.
- Initial M1 acceptance complete for tested 10.0.6 scratch scope. Broader shapes/profiles/arbitrary GUI writers, all OS-crash timings, full hardware STM32/multi-protocol design/manufacturing release and M2 five autonomous runs remain outside this result.
- Actual subscribed Codex host native summary/render was successful and the PNG inspected; runs/mcp/host-native-2026-10-09/report.json. This proves live native image delivery/analysis, not editor-window screenshot success.
- Updated the already authorized pcb_harness host config run directory only to runs/mcp/native-accepted-2026-10-09, preserving other parsed settings and private backup outside repo. Old run/journal retained. Actual host pcb_status still returns old directory and old disabled gate, so live process reload is required; new host mutation capability is not falsely claimed.
- Review finding Important full-version bypass fixed RED→GREEN; no Critical/Minor outstanding and no re-review. Preserve current local development branch/checkout; no push/merge/publication.
