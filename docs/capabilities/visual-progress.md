# Execution ledger — plan: docs/superpowers/plans/2026-10-09-visual-tools.md

- User approved visual tools; inline execution remains authorized. Subscription-first/Open Source constraints retained.
- Ruling: render from native saved-copy SVG as main geometry view; capture only the bound editor window. No screenshot/desktop fallback for failed native rendering. Cost if wrong: unsupported visual paths; report them explicitly.
- Ruling: choose resvg-py0.5.0 and Pillow12.3.0 for self-contained rasterization, avoiding a separate Cairo runtime requirement; pin dependencies. Optional Quartz12.2.2 is macOS-only. Cost if wrong: renderer/OS-version differences; verify actual pixels/metadata and decline unsupported capture.
- Native CLI10.0.6 verified installed; current IPC socket and native UI tool absent. Saved-fixture CLI images and Memory protocol tests can proceed; live IPC/editor capture acceptance remains a separate gate.
- Pre-flight: backend snapshot/bounds/revision → renderer → service metadata/private PNG bytes → MCP ImageContent. Capture bytes cannot carry calibrated board coordinates and must preserve exact instance/window identity.

- Renderer RED: 18 missing-feature cases; native pixel/mapping investigation found CLI10.0.6 with explicit --scale1 now offset[-10,-10]. Old M0 offset is not reused. Added saved root-level outline comparison so translationally wrong bounds cannot masquerade as calibrated. Current renderer 19 cases GREEN including actual CLI pixels.
- Capture/service RED: 9 failures/16 pass; GREEN25 for exact PID/window, no permission invocation, explicit Memory capture refusal and stable revision-bound renders.
- Protocol RED: missing three tools caused4 failures/23 pass. MCP now returns TextContent + PNG ImageContent; private bytes are excluded from JSON/base64 text. Focused suite53 passed.
- Actual Quartz preflight: screen_recording permission=False; no permission request and no screenshot attempted. Current IPC socket absent. Window capture/live native snapshot still unverified; saved-fixture/native CLI and Memory render results stay labelled separately.
- Guard added to live visual snapshot/capture: exact document must still be open before/after producing image; revision change refuses delivery with no image. Native mutation gate unchanged.

- Full verification: 168 passed in 16.30s; actual visual smoke runs/visual/acceptance-2026-10-09 PASS, including native CLI full/crop and current/legacy STDIO ImageContent. Viewed both native saved-fixture PNGs: source/layer/revision/mm labels and copper/crop visible; not live screenshots.
- Fresh reviewer visual_review: no confirmed Critical/Important; focused53 cases passed. Deferred minor: narrow/many-layer legend clipping; full structured metadata preserved. Deferred minor: all32 copper layers can normalize to33 with Edge.Cuts and hit repeated validation limit; initial target uses an enabled subset, failure is explicit, no wrong image returned.
- Declined-to-judge ruling: live IPC snapshot, actual window owner/title, screenshot success and host image display remain unverified. Keep those gates closed/explicit; saved fixture and mocked OS contract tests cannot establish them. Cost if wrong: future native/host mismatch, requiring actual environment acceptance. No re-review/fix pass needed for confirmed Important findings because none were reported.
