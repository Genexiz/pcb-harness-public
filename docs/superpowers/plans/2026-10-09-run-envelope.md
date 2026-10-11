# M2 run envelope execution plan

Spec: PCB Harness — Design Spec (v2).md, M2; Development Roadmap, M2.
Goal: freeze and enforce 300 admitted write requests / 1200 wall seconds per local MCP run, without inference keys. This is preparation for M2, not native acceptance or a successful routing experiment.

## Design and constraints

Reuse the authorized SSD checkout and work/m0-kicad-capability branch. Continue inline under the existing user authorization. A separate durable JSONL run ledger, protected by the existing service writer lease, freezes launch limits and backend/project identity before tools run. Clock starts at the first write request, including rejected writes. All execute/checkpoint/restore requests, including replay and schema-invalid requests, consume admission; queries, rendering, connection and disconnect do not. Internal atomic rollback is never interrupted. Deadline is checked before dispatch, with elapsed time reported afterward; this is not a hard process kill at 1200 seconds. No new write after expiry. Same-process timing uses the greater of monotonic and wall elapsed; restart includes downtime and detects backward wall clock against the last durable event.

Persist admission before dispatch and outcome after it. Missing/torn/unmatched evidence blocks further writes, never refunds attempts, while inspection stays available. A changed limit/config fails startup. Existing action journals without a run ledger require a new run directory; do not silently reset historical budgets. No reset/extend tool. Existing native acceptance/recovery gates remain authoritative.

## Review focus

1. Reconnect/restart and a different launch limit cannot renew counters/time.
2. Invalid/stale/short/replayed writes cannot evade counting; no edit when exhausted.
3. Clock rollback or failed/torn evidence prevents dispatch.
4. An in-flight action may cross deadline but finishes verification/rollback; next write denied.
5. Real modern/legacy STDIO exposes budget metadata and schema-invalid requests consume budget.

## Task 1: Durable envelope

Create src/pcb_harness/run_envelope.py and tests/test_run_envelope.py.
Consumes: fixed service run directory, backend/project identity, max_actions (positive integer), max_duration_seconds (positive finite number).
Produces: RunEnvelope(path, identity, max_actions=300, max_duration_seconds=1200), status(), admit(operation, action_id=None), finish(attempt, result). status returns limits, attempts_used/remaining, started_at, elapsed_seconds, deadline_reached, evidence_error. admit fsyncs start before returning sequential ID; finish fsyncs categorized outcome.

RED tests cover literal 2-attempt cap, config mismatch, process reopen, expired time, monotonic clock/rollback, unmatched/torn ledger and I/O failure. Expected initial failure: module absent. Implement durable append/parser + dual clock admission, then run focused tests.

```python
run=RunEnvelope(path, identity, max_actions=2, max_duration_seconds=1200)
a=run.admit('execute'); run.finish(a, {'ok': False, 'error_code':'STALE_REVISION'})
b=run.admit('execute'); run.finish(b, {'ok': True})
assert run.status()['attempts_used']==2
with pytest.raises(HarnessError): run.admit('execute')
```

## Task 2: Service/protocol boundary

Modify src/pcb_harness/mcp_service.py, src/pcb_harness/mcp_server.py. Tests: tests/test_mcp_service.py, tests/test_mcp_server.py.
Service constructor gains launch limits. After lease acquisition create envelope; close lease on constructor failure. All write operations pass through durable admission/outcome wrapper; final tags include current run_budget. Signature/connection/native/recovery rejections are counted. StrictMCPServer schema validation delegates invalid write rejection to the same service wrapper. CLI gains --max-actions and --max-duration-seconds. Tool count stays 14.

```python
service=MCPService(workspace=tmp_path, run_directory=tmp_path/'runs/test', backend='memory', max_actions=1)
service.connect(); before=service.call('summary')['revision']
first=service.call('execute', name='move_footprint', args={'ref':'R1','dx_mm':2,'dy_mm':0}, expected_revision=before, action_id='one')
assert first['ok'] and first['run_budget']['attempts_used']==1
assert service.call('execute', name='move_footprint', args={'ref':'R1','dx_mm':2,'dy_mm':0}, expected_revision=first['revision'], action_id='two')['error_code']=='RUN_ACTION_LIMIT'
assert service.call('get_footprint', ref='R1')['x_mm']==22
```

Watch RED before implementation. Cover rollback and stale rejection, replay count, checkpoint exhaustion, queries/render after expiry, reconnect and actual SDK invalid schema. Add actual STDIO limit test in modern and legacy modes with model keys removed.

## Task 3: Acceptance and documentation

Create experiments/mcp/smoke_budget.py; produce a new ignored runs/mcp/budget-acceptance-* report using actual modern/legacy STDIO Memory calls, stale rejection, checkpoint/restore, exhaustion, remaining read/verification/image tools. Document configurable limits, clock start/admission semantics, no refund/reset, legacy migration and failure gates in docs/mcp.md, README.md, examples/mcp/*.toml. Update ledger and roadmap status; do not claim host/native routing readiness.

Run .venv/bin/python -m pytest -q (native CLI needs approved unsandboxed execution), pip check, smoke_budget. One fresh whole-change review (not a repeated review of previous slices), one Important fix pass with RED→GREEN if needed. Commit local work; no push/merge/publish.
