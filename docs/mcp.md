# Local MCP — subscription-first

The local STDIO server exposes 14 tools around the same Kernel. The model and sign-in belong to your MCP host. This server makes no inference requests, asks for no model API key, and opens no HTTP port.

Current evidence proves the official SDK client and real STDIO process work in modern and legacy modes. Codex discovers all 14 tools, connects to an exact scratch board, receives native PNGs and performs guarded native writes. M2 single-agent routing feasibility passed 4/5 runs in `runs/routing/m2-2026-10-09-r3`: four runs reached clean mandatory DRC, zero unconnected and clean parity; one lost checkpoint reply stopped with `RECOVERY_REQUIRED` and was not retried.

## Install and test

From your local checkout, with Python 3.11 and KiCad installed for native CLI tests:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-mcp.lock
.venv/bin/python -m pip install -e '.[test,mcp]' --no-deps --no-build-isolation
.venv/bin/python -m pytest -q
.venv/bin/python experiments/mcp/smoke_stdio.py --output runs/mcp/<new-acceptance-run>
```

The optional SDK dependency is `mcp==2.3.0`. Kernel users need no MCP SDK unless running the MCP server/protocol tests. The full test extra installs it. No LLM/provider SDK is added.

## Choose an explicit backend

Native (default):

```sh
.venv/bin/python -m pcb_harness.mcp_server --workspace "$PWD" --run-directory "$PWD/runs/mcp/native" --project "$PWD/runs/capability/live/board.kicad_pcb"
```

Open that exact scratch board in PCB Editor and enable KiCad API for native queries. Specify `--socket ipc:///tmp/kicad/api-<pid>.sock` when the default belongs to another instance. Failed native connection returns a structured error; it never selects the demo instead.

**Native mutations/checkpoint writes are enabled only for the exact connected scratch backend on KiCad 10.0.6**, following successful current M1 native smoke and settings-conflict acceptance. Older/newer patches or majors remain disabled with `NATIVE_ACCEPTANCE_REQUIRED`; no tool or launch flag overrides this acceptance gate. Kernel recovery, locks, revisions and frozen budgets still apply independently. KiCad API is a local command interface, not a model API key.

Explicit demo:

```sh
.venv/bin/python -m pcb_harness.mcp_server --workspace "$PWD" --run-directory "$PWD/runs/mcp/demo" --backend memory
```

Memory is test-only: every result has `test_only=true`; it never edits KiCad and cannot claim fabrication readiness. Same-process disconnect/connect retains the fixture and journal. Across process restart, a fresh Memory fixture cannot resume the old state and must fail closed; choose a fresh demo run directory explicitly if you intend a new test. Native run paths must remain persistent for reconnect/resume checks.

## Connect Codex

Use Codex with ChatGPT sign-in for subscription access. Model choice/access/usage limits belong to the host; this server needs no `GOOGLE_API_KEY` or `OPENAI_API_KEY`, and does not read or forward sign-in credentials.

Copy the relevant table from `examples/mcp/codex-native.toml` or `codex-memory-demo.toml` into your supported Codex MCP configuration, replacing `/absolute/path/PCB_Harness` with your checkout. Keep the existing configuration and other servers. Each run journal allows only one server writer, so two clients using the same run concurrently are refused.

Restart/reload the host's MCP connection and confirm all three steps: server discovery, `pcb_status`, then an actual tool call after `pcb_connect`. A config entry alone is not a verified host integration. Hosted ChatGPT web uses a different connection surface; local STDIO configuration is not automatically available there.

## Tools

| Tool | Purpose |
| --- | --- |
| `pcb_status` | Configured backend, connection/readiness, capabilities, test-only/recovery flags |
| `pcb_connect` | Bind the fixed project/run/backend from trusted launch arguments |
| `pcb_summary` | Counts, current revision, capabilities and limited verification status |
| `pcb_get_footprint` | Footprint/pad coordinates, side/lock and revision |
| `pcb_net_info` | Canonical net pads/tracks/length; no routing search |
| `pcb_list_unrouted` | Unconnected findings and revision |
| `pcb_execute` | Caller-chosen explicit intent + expected revision + unique ID; strict by default |
| `pcb_create_checkpoint` | Named checkpoint with fresh expected revision |
| `pcb_restore_checkpoint` | Guarded restore; conflicts block writes |
| `pcb_verify_geometry` | Geometry/connectivity findings, always `release_verified=false`; not ERC/release |
| `pcb_disconnect` | Release board connection, retain fixed journal/uncertainty |

Pure read queries are annotated read-only. Native verification/unrouted queries are additive writes because they create saved-copy/report artifacts; Memory verification remains read-only. Lifecycle and mutation tools are not read-only; host permissions apply independently. Unknown top-level tool arguments are rejected instead of silently ignored by the SDK. Kernel errors return both MCP `isError=true` and structured `error_code`, with matching JSON text for legacy clients.

Query a fresh revision before writing. Tool `args` depend on the selected action; Kernel validates units, object/net/layer names, geometry and locks. Immediate same-ID replay does not mutate twice. Changed intents conflict; old results invalidated by later changes are not current success.

No tool can change backend/project/run path, override native version acceptance, reset recovery or bypass the journal. Checkpoint capture is bound to the caller-authorized pre-save revision; a concurrent change is rejected. Native save can rebase persisted file hashes only while the serialized live board stays unchanged, and the captured copy is hash-checked. This is an observed-conflict guard, not atomic protection against every GUI race. An unfinished action or failed evidence blocks writes across reconnect; disconnected status retains uncertainty. The server serializes all calls and owns a fixed-run lease; the native adapter additionally owns a project lease.

## Evidence and remaining scope

`runs/mcp/stdio-acceptance-2026-10-09/report.json` records modern/legacy protocol, server identity, 11 discovered tools, real Memory movement/readback/replay and stale rejection, without model-key environment variables. Tests cover actual rollback, checkpoint restore, validation, fixed paths, duplicate writers and recovery behavior.

Subscribed-host mutation acceptance after gate reload, controlled routing experiments/evals, arbitrary geometry/rules and broader platform support remain separate gates. No public repository/package has been published and no project license selected yet. The server is inspectable and documented for the planned open-source release; SDK/dependency licenses remain their own.

Official references checked: [Python SDK](https://github.com/modelcontextprotocol/python-sdk), [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [ChatGPT sign-in](https://learn.chatgpt.com/docs/auth).

## Visual tools (14 tools total)

Three additive-write tools now return actual PNG `ImageContent` plus structured/text metadata; base64 is confined to the image block. The host may analyze the image using its supported vision model/subscription. The server performs no model inference and needs no model API key.

- `pcb_render_board(layers=['F.Cu','B.Cu'], width_px=1024)`: whole-board PNG. `Edge.Cuts` is included for calibration; width accepts 256–2048 px.
- `pcb_render_region(region_mm=[xmin,ymin,xmax,ymax], layers=..., width_px=...)`: bounded crop in physical board mm, with uniform `board_to_pixel` mapping and captured revision.
- `pcb_capture_editor()`: real bound editor-window screenshot on macOS, requiring a live native connection, explicit `api-<PID>.sock`, one matching PCB Editor board window and existing Screen Recording permission. No desktop capture, automatic permission prompt, Memory screenshot or render fallback. Screenshot metadata has `board_coordinate_mapping=null`; it is not precision geometry input.

Render metadata includes source, selected layers, bounds/crop, mm→pixel mapping, PNG hash/dimensions and revision. Labels distinguish Memory/test views from saved native boards/live native snapshots. The image complements structured pad geometry and DRC; it never grants release readiness. Any observed document/revision change refuses image delivery. Files are written only under the configured run directory.

Native rendering exports from an IPC snapshot and validates the saved root-level rectangular outline against queried bounds, then calibrates SVG units/offset from the actual export. It does not reuse an old version's offset. Memory rendering is a limited, labelled diagram. External/active SVG references, oversized SVG/PNG and invalid crops/layers are refused.

Install the normal MCP/test extras for resvg-py0.5.0 and Pillow12.3.0. Editor capture additionally needs the macOS-only `capture` extra:

```sh
.venv/bin/python -m pip install -e '.[mcp,capture]'
.venv/bin/python experiments/mcp/smoke_visuals.py --output runs/visual/<new-run>
```

The visual smoke produces full/crop PNGs from the immutable synthetic KiCad fixture and tests actual modern/legacy STDIO ImageContent. That is a saved-board/protocol proof, not live GUI or host vision-model acceptance.

Evidence: `runs/visual/acceptance-2026-10-09/{report.json,board/render.png,r1-crop/render.png}`. Current actual process permission preflight returned false, no permission was requested and no screenshot was attempted. Live IPC render and actual Codex image delivery/analysis are now verified; real editor window capture remains unverified (the current default socket does not supply the capture tool's required explicit PID identity).

Known deferred minors from fresh review: legends may clip at small widths/many layers (full JSON metadata remains available); selecting all 32 copper layers can hit normalization's layer-count limit after adding Edge.Cuts. Prefer normal 1024 px views and the actual enabled layer subset for this initial scope. Capture is currently macOS/English-title specific; unsupported identity/platform/permission returns explicit errors.

## Frozen run envelope

Every new MCP run freezes `--max-actions` (default 300) and `--max-duration-seconds` (default 1200) at server launch. These are admission limits for the initial M2 experiment; no model tokens/costs are inferred. Every result includes `run_budget` with used/remaining attempts, elapsed seconds, start timestamp (Unix seconds), deadline status and evidence errors.

```sh
.venv/bin/python -m pcb_harness.mcp_server --workspace "$PWD" --run-directory "$PWD/runs/mcp/<new-run>" --backend memory --max-actions 300 --max-duration-seconds 1200
.venv/bin/python experiments/mcp/smoke_budget.py --output runs/mcp/<new-budget-acceptance>
```

The timer starts on the first admitted execute/create-checkpoint/restore-checkpoint request, including a rejected one. Idle time before that request is excluded; disconnect/restart downtime afterward counts. All three write tools consume one admission each, including stale/locked/invalid/native-gated requests, same-ID replay, and JSON Schema failures at the MCP boundary. Identifiable raw tools/call requests with malformed argument containers are counted before SDK parameter validation; they retain the SDK transport error rather than a tool response. Completely unparseable messages without an identifiable tool are transport failures, not admitted board intents. Reads, verification, rendering and lifecycle calls do not consume admissions. Requests denied by an already exhausted limit do not dispatch a Kernel action or increase the admitted count.

`RUN_ACTION_LIMIT`/`RUN_TIME_LIMIT` stops further writes while inspection remains available. A previously admitted action may finish after the deadline: verification and internal rollback complete before any further request is admitted. This is an admission deadline, not a hard process timeout or a promise that total execution finishes within 20 minutes. M2 evaluation must report actual elapsed time, including overruns. Host execution/approval waits outside tool calls are not cancelled by the server.

`run.jsonl` contains a frozen config header and fsynced admission/outcome rows, separate from the detailed Kernel `actions.jsonl`. A fsynced `run.jsonl.pending` marker precedes admission and is cleared only after the outcome is fsynced; a complete JSON row alone cannot clear unresolved durability on restart. Failure confirming marker removal recreates the stop marker when the filesystem allows it. This does not establish OS/power-loss recovery under every storage failure. Limits/backend/project cannot be changed for the same run (`RUN_CONFIG_CONFLICT`); reconnect never renews them. Clock checks use monotonic and wall elapsed plus persisted same-boot monotonic timestamps, include downtime, and refuse backward clocks or unknown/changed boot epoch (`RUN_CLOCK_ROLLBACK`). On macOS the boot identity is read from kern.bootsessionuuid; no OS setting/permission is changed. If that read is unavailable, a new in-process run still works but restarting an active run cannot admit writes. This conservative gate avoids renewing time when clock continuity is unproven. Missing/torn/unmatched/failed evidence causes `RUN_EVIDENCE_REQUIRED`; no refund or automatic retry. A terminal evidence failure can follow a successful board edit: inspect the returned revision/outcome and preserve both journals rather than replaying.

Historical directories containing `actions.jsonl` but no run ledger fail startup with `RUN_MIGRATION_REQUIRED`. Preserve their evidence and use an explicitly new directory for a new experiment; native project/recovery conflicts still apply independently. The new budget layer does not reconcile an uncertain project. Memory state across process restart remains nonrecoverable as documented above. Direct experimental Kernel scripts do not use this MCP admission layer and are not M2 budget proofs.

No reset/extend tool is provided. Limits are not tamper-proof against a person modifying their own files; external truncation/replacement detected during the current service session blocks writes. Budget exhaustion never disables the existing native acceptance or recovery guards.

Acceptance evidence: `runs/mcp/budget-reviewed-2026-10-09/report.json` exercises actual modern/legacy STDIO with an explicit six-admission test envelope, malformed request, checkpoint, movement, replay, stale rejection, restore, limit rejection and reconnect. Final readback/verification/PNG remains available. Native routing evidence is separate under `runs/routing/m2-2026-10-09-r3`: the aggregate gate passed 4/5 with all raw failures retained. Exact host model revision, sampling settings, provider tokens and provider cost were unavailable; Harness used no model-provider API key.

Actual Codex-host evidence: runs/mcp/host-discovery-2026-10-09/report.json. This historical report captured discovery/status/error delivery with the API disabled. The later host-native report below proves exact native connection and live PNG delivery/inspection.


## Current native acceptance (2026-10-09)

- `runs/capability/kicad-10.0.6-ipc-reviewed-2026-10-09/report.json`: ten primitive probes, native flip/pad readback and baseline restore.
- `runs/kernel/native-10.0.6-2026-10-09/smoke.json`: native DRC rollback, stale/locked intents, flip/side/placement, explicit route/replay/journal resume, delete/via/zone/refill and exact baseline restore.
- `runs/kernel/native-conflict-10.0.6-2026-10-09/conflict.json`: saved settings conflict preserved, subsequent writes blocked, own exact-byte cleanup verified.
- `runs/mcp/native-reviewed-2026-10-09/report.json`: actual native STDIO checkpoint/move/readback/replay/restore/short rollback/reconnect with final clean geometry/connectivity.
- `runs/mcp/host-native-2026-10-09/report.json`: actual Codex native summary and live PNG delivery/visual inspection, separate from editor screenshots and autonomous routing.
- `runs/routing/m2-2026-10-09-r3/report.json`: M2 host-driven placement/routing gate PASS 4/5. Passing runs used one placement plus four explicit route actions and finished inside the 300-action/1200-second envelope; the failed run retained `RECOVERY_REQUIRED` after a lost checkpoint reply.

Native 10.0.6 FlipItems can be queried immediately before push, unlike ordinary staged UpdateItems. Dropping its commit can regenerate footprint-property UUIDs despite restored geometric positions; full serialized guards correctly stop on this difference. The failed probe and its explicit exact-state cleanup are retained as evidence. No blanket normalization or generic automatic recovery was added.

An older MCP session journal captured the scratch revision before these external acceptance probes and must not be cleared to accept a different saved-byte state. After proved baseline restoration, use an explicitly new experiment run (the configured host run is `runs/mcp/native-accepted-2026-10-09`) and reload the host MCP connection for the updated code. Old artifacts/journals remain intact; this does not grant a fresh budget to an unfinished experiment.
