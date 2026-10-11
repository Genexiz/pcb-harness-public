# Execution ledger — plan: docs/superpowers/plans/2026-10-09-local-mcp.md

- User approved Subscription-first/Open Source direction and requested continued implementation inline.
- Ruling: prepare and verify MCP protocol/demo independently while native editing remains blocked until current M1 acceptance passes. This progresses useful work without falsely advancing the native gate; cost if wrong is incomplete host ergonomics, not speculative board editing.
- Ruling: use existing local Python repo, STDIO and official SDK 2.3.0. Plugin skill's cloud default is inapplicable because KiCad hardware/files are local and user requires Subscription-first use. No cloud project/public endpoint created.
- Pre-flight: service consumes Kernel revision/checkpoint results; MCP adapter only translates typed calls/results; fixed launch paths and persistent journal protect reconnect. Single service/run writer lock must cover all tools including close.
- Installed KiCad 10.0.6; no /tmp/kicad socket observed. User's earlier exact scratch-open request remains pending. Native tools not available in this turn.

- Task 1 RED: missing service module plus checkpoint/verify contracts; 6 failed/7 errors/50 passed. GREEN: 63 Kernel/service cases passed. Native selection and run leases remain fixed.
- Task 2 initial protocol RED: 4 failures before server existed. GREEN: 4 real SDK client/server tests including actual STDIO process without model keys.
- Additional boundary RED: Memory summary omitted capabilities and SDK silently ignored unknown top-level arguments. Fixed using backend capability output and public MCPServer list_tools/call_tool overrides with JSON Schema validation; 20 service/protocol cases GREEN. Native write guard covered against real Kernel state without a live IPC dependency.
- No model provider dependencies or API-key access added. Official SDK 2.3.0 inspected locally; v2 uses MCPServer/Client and snake_case Python fields, not v1 FastMCP assumptions.

- Modern + legacy real STDIO tests passed; whole suite 134 passed before final status fix. Reproducible SDK acceptance report runs/mcp/stdio-acceptance-2026-10-09/report.json passed both modes, 11 tools, real Memory movement/replay/stale rejection; no provider keys.
- Disconnect recovery display RED→GREEN: previously showed false while journal remained uncertain. Service now latches visible uncertainty across disconnect and refuses writes until reconciliation; 22 service/protocol cases GREEN.
- Task 3 docs/config examples/CONTRIBUTING prepared. One fresh MCP-only reviewer dispatched as required by executing-plans; no duplicate old M1 review. Native editing and current host integration still not claimed.

- Fresh review: no Critical, one Important checkpoint capture race, one Minor annotation mismatch. Regraded annotation mismatch Important because host approval policy can treat an actual filesystem writer as read-only; native queries can create artifacts even while native board editing is gated.
- Review fix RED: concurrent checkpoint capture, action against foreign captured baseline, native verification annotation; 3 failed/58 passed. GREEN: authorized pre-save capture binding and explicit persisted-file rebasing, uncertain checkpoint/action latch, additive-write native verification annotations; 77 focused cases passed.
- Declined-to-judge ruling: native GUI/socket/saved-copy behavior and subscribed-host acceptance remain unverified, so native mutation gate stays closed and config alone is not a connection claim. Cost if wrong: eventual native divergence; require actual acceptance before enabling board edits. No re-review dispatched.

- Final whole suite after the one review fix pass: 138 passed in 15.95s; pip check reports no broken requirements. Actual STDIO smoke runs/mcp/stdio-reviewed-2026-10-09/report.json PASS in modern + legacy modes with 11 tools.
- Codex configuration added for pcb_harness using local Python/STDIO, fixed SSD workspace/run and exact scratch board; existing settings preserved and private backup retained outside repo. No model key, credentials or tool approval override added. Config parsed/validated; actual app discovery/call awaits MCP reload and is not yet claimed.
- Native GUI/socket/saved-copy behavior remains unverified, native mutation/checkpoint tools stay blocked; M2 routing proof and public Open Source release remain separate gates.
