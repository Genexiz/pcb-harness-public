# M2 Subscription-driven Routing Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove or falsify that one Codex host using the local PCB Harness MCP can place and route a human-reviewed tiny KiCad circuit in five native runs, with at least three runs reaching clean mandatory DRC, zero unconnected items, and circuit parity inside the frozen 300-action/1200-second envelope.

**Architecture:** A tracked unrouted fixture and manifest define the benchmark without embedding a solution. A thin interactive STDIO relay exposes the existing MCP tools to the subscribed Codex host and records tool inputs/results, but contains no placement or routing policy. A fail-closed scorer reads the frozen manifest, MCP budget ledger, host transcript, and final native verification from each isolated run; an aggregate report applies the 3/5 gate without deleting failures.

**Tech Stack:** Python 3.11, KiCad 10.0.6 PCB Editor IPC, `kicad-python==0.8.0`, MCP Python SDK 2.3.0, pytest 9.1.1, existing PCB Harness Kernel/MCP/run-envelope modules.

**Spec:** `PCB Harness — Design Spec (v2).md` (M2); `PCB Harness — Development Roadmap.md` (M2)

## Global Constraints

- Harness inference uses the Codex/ChatGPT Subscription host; normal local use must not require or forward a model-provider API key.
- The model must choose every placement, track path, layer, and via; no autorouter, shove router, route-search helper, or hidden golden route may produce tool arguments.
- Run configuration is frozen before the first write at exactly 300 admitted write attempts and 1200 seconds; rejected and rolled-back attempts count.
- Five native KiCad runs are retained, including tool/provider failures; the gate is at least 3/5 clean runs.
- A passing run requires mandatory geometric DRC clean, zero unconnected items, and clean schematic parity from saved native evidence.
- Exact model revision, sampling settings, provider token counts, and provider cost are recorded as `unavailable` when the host does not expose them; they are never inferred as zero.
- KiCad writes are limited to isolated project copies under `runs/`; tracked fixtures are immutable and the tested native write gate remains exact stable KiCad `10.0.6`.
- Every write uses a fresh queried revision and a unique action ID. An uncertain result is never retried automatically.
- This is routing feasibility, not fabrication release, a controlled provider comparison, or permission to start M3/M4.

## Review Focus

- A transcript with a clean final result but no accepted host-specified placement action or route action must fail scoring rather than pass as pre-routed input.
- Truncated/corrupt MCP ledgers, incomplete transcripts, missing native reports, or mismatched project/fixture hashes must fail closed and remain visible in the campaign report.
- Runs that cross 1200 seconds after an admitted action finishes must report the actual overrun and fail the envelope gate even if final geometry is clean.
- Replayed, stale, invalid, rejected, and rolled-back writes must remain counted; the scorer must not derive attempt totals only from successful actions.
- Different KiCad documents, socket instances, prerelease builds, or run-directory reuse must be rejected before mutation rather than silently substituted.

---

### Task 1: Freeze the tiny unrouted native benchmark

**Files:**
- Create: `fixtures/routing/tiny/board.kicad_pcb`
- Create: `fixtures/routing/tiny/board.kicad_pro`
- Create: `fixtures/routing/tiny/board.kicad_sch`
- Create: `fixtures/routing/tiny/board.kicad_dru`
- Create: `fixtures/routing/tiny/Harness.kicad_sym`
- Create: `fixtures/routing/tiny/Harness.pretty/Probe_R.kicad_mod`
- Create: `fixtures/routing/tiny/fp-lib-table`
- Create: `fixtures/routing/tiny/sym-lib-table`
- Create: `fixtures/routing/tiny/benchmark.json`
- Create: `eval/routing_smoke/fixture.py`
- Test: `tests/test_routing_fixture.py`

**Interfaces:**
- Consumes: the human-reviewed three-resistor/two-net circuit and native rules from `fixtures/capability/`.
- Produces: `load_benchmark(path: Path) -> dict`, `fixture_hashes(path: Path) -> dict[str, str]`, and a complete unrouted project bundle whose benchmark declares refs `R1..R3`, nets `/NET_A` and `/NET_B`, required placement action count `>=1`, and no pre-existing copper.

- [ ] **Step 1: Write the failing benchmark-contract tests**

```python
def test_tiny_routing_fixture_is_complete_unrouted_and_frozen():
    root = ROOT / "fixtures/routing/tiny"
    benchmark = load_benchmark(root / "benchmark.json")
    assert benchmark["schema_version"] == 1
    assert benchmark["board"] == "board.kicad_pcb"
    assert benchmark["refs"] == ["R1", "R2", "R3"]
    assert benchmark["nets"] == ["/NET_A", "/NET_B"]
    assert benchmark["initial_track_count"] == 0
    assert benchmark["initial_via_count"] == 0
    assert benchmark["min_host_placement_actions"] == 1
    assert fixture_hashes(root) == benchmark["sha256"]

def test_real_kicad_accepts_geometry_and_parity_but_reports_unconnected_input(tmp_path):
    result, report = run_drc(FIXTURE, tmp_path / "drc.json")
    assert result.returncode == 5
    assert report["violations"] == []
    assert report["schematic_parity"] == []
    assert report["unconnected_items"]
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/pytest tests/test_routing_fixture.py -q`

Expected: FAIL because `eval/routing_smoke/fixture.py` and `fixtures/routing/tiny/benchmark.json` do not exist.

- [ ] **Step 3: Add the minimal fixture loader and tracked project**

```python
def load_benchmark(path: Path) -> dict:
    data = json.loads(path.read_text())
    required = {"schema_version", "board", "refs", "nets", "initial_track_count",
                "initial_via_count", "min_host_placement_actions", "sha256"}
    if set(data) != required or data["schema_version"] != 1:
        raise ValueError("unsupported routing benchmark manifest")
    return data

def fixture_hashes(root: Path) -> dict[str, str]:
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != "benchmark.json")
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
```

Create the routing fixture from the reviewed capability circuit while removing every `segment` and `via`. Keep its schematic, symbol/footprint libraries, explicit-unit custom rule, rectangular outline, three placed-but-unlocked footprints, and two named nets. Write the computed hashes to `benchmark.json`; do not include route coordinates or a golden solution.

- [ ] **Step 4: Run focused and native fixture tests**

Run: `.venv/bin/pytest tests/test_routing_fixture.py tests/test_capability_fixtures.py -q`

Expected: PASS; the routing fixture has clean geometric/parity sections and non-empty unconnected evidence, while the existing capability fixture stays fully clean.

- [ ] **Step 5: Commit the benchmark**

```bash
git add fixtures/routing/tiny eval/routing_smoke/fixture.py tests/test_routing_fixture.py
git commit -m "Add frozen M2 tiny routing benchmark"
```

### Task 2: Record model-driven MCP sessions without routing logic

**Files:**
- Create: `eval/routing_smoke/session.py`
- Create: `eval/routing_smoke/prepare.py`
- Create: `eval/routing_smoke/__init__.py`
- Test: `tests/test_routing_session.py`

**Interfaces:**
- Consumes: `load_benchmark`, `fixture_hashes`, the existing `pcb_harness.mcp_server` CLI, newline-delimited host commands `{ "tool": str, "arguments": object }`.
- Produces: `prepare_campaign(fixture: Path, campaign: Path, repeats: int = 5) -> list[Path]`; an interactive process that prints one MCP result per input line and appends durable `host-transcript.jsonl` rows containing sequence, tool, arguments, result metadata, timestamps, and host disclosure.

- [ ] **Step 1: Write failing isolation/transcript tests**

```python
def test_prepare_creates_five_isolated_hash_bound_runs(tmp_path):
    runs = prepare_campaign(FIXTURE, tmp_path / "campaign", repeats=5)
    assert [p.name for p in runs] == ["run-1", "run-2", "run-3", "run-4", "run-5"]
    assert len({json.loads((p / "manifest.json").read_text())["run_id"] for p in runs}) == 5
    assert all((p / "project/board.kicad_pcb").is_file() for p in runs)
    with pytest.raises(FileExistsError):
        prepare_campaign(FIXTURE, tmp_path / "campaign", repeats=5)

def test_memory_relay_records_exact_calls_and_unavailable_model_fields(tmp_path):
    rows = run_memory_relay(tmp_path, [
        {"tool": "pcb_connect", "arguments": {}},
        {"tool": "pcb_summary", "arguments": {}},
    ])
    assert [row["tool"] for row in rows] == ["pcb_connect", "pcb_summary"]
    assert rows[0]["host"]["name"] == "Codex desktop subscription"
    assert rows[0]["host"]["exact_model"] == "unavailable"
    assert rows[0]["host"]["provider_tokens"] == "unavailable"
    assert rows[0]["host"]["provider_cost"] == "unavailable"
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/pytest tests/test_routing_session.py -q`

Expected: FAIL because campaign preparation and the relay do not exist.

- [ ] **Step 3: Implement isolated preparation and a policy-free relay**

```python
HOST_DISCLOSURE = {
    "name": "Codex desktop subscription",
    "exact_model": "unavailable",
    "sampling_settings": "unavailable",
    "provider_tokens": "unavailable",
    "provider_cost": "unavailable",
    "model_api_key_used_by_harness": False,
}

async def relay(client, source, sink, transcript):
    for line in source:
        command = json.loads(line)
        if set(command) != {"tool", "arguments"} or not isinstance(command["arguments"], dict):
            raise ValueError("commands require tool and object arguments")
        reply = await client.call_tool(command["tool"], command["arguments"])
        row = {"sequence": next_sequence(), "tool": command["tool"],
               "arguments": command["arguments"], "result": reply.structured_content,
               "host": HOST_DISCLOSURE, "recorded_at": time.time()}
        append_fsync(transcript, row)
        sink.write(json.dumps(row, allow_nan=False) + "\n")
        sink.flush()
```

The relay must only transport caller-provided tool names/arguments. It must not compute coordinates, choose layers, synthesize routes, retry failed writes, alter action IDs, reset budgets, or hide error responses. Launch the existing server with `--max-actions 300 --max-duration-seconds 1200`; strip `API_KEY` and `TOKEN` variables from its child environment.

- [ ] **Step 4: Run focused tests and actual Memory STDIO acceptance**

Run: `.venv/bin/pytest tests/test_routing_session.py tests/test_mcp_server.py tests/test_mcp_budget.py -q`

Expected: PASS, including one real MCP SDK STDIO relay session and exact durable transcript rows.

- [ ] **Step 5: Commit the session transport**

```bash
git add eval/routing_smoke/session.py eval/routing_smoke/prepare.py eval/routing_smoke/__init__.py tests/test_routing_session.py
git commit -m "Add auditable M2 host session transport"
```

### Task 3: Score each run and the 3/5 campaign fail-closed

**Files:**
- Create: `eval/routing_smoke/score.py`
- Test: `tests/test_routing_score.py`

**Interfaces:**
- Consumes: run `manifest.json`, `host-transcript.jsonl`, service `run.jsonl`, final `pcb_verify_geometry`, final `pcb_summary`, and benchmark hashes.
- Produces: `score_run(path: Path) -> dict`; `score_campaign(path: Path, expected_runs: int = 5) -> dict`; persisted `score.json` per run and campaign `report.json`.

- [ ] **Step 1: Write failing pass/fail and evidence-corruption tests**

```python
def test_run_pass_requires_native_clean_route_placement_and_envelope(evidence_factory):
    run = evidence_factory(clean=True, placement_actions=1, route_actions=2,
                           attempts=4, elapsed=35, native=True)
    score = score_run(run)
    assert score["passed"] is True
    assert score["mandatory_drc_clean"] is True
    assert score["zero_unconnected"] is True
    assert score["circuit_parity_clean"] is True

@pytest.mark.parametrize("change", [
    "missing_transcript", "corrupt_budget", "fixture_hash_mismatch", "no_placement",
    "no_route", "memory_backend", "geometric_issue", "unconnected", "parity_issue",
    "over_300_attempts", "over_1200_seconds", "recovery_required", "uncertain_write",
])
def test_run_fails_closed_for_missing_or_out_of_gate_evidence(evidence_factory, change):
    assert score_run(evidence_factory(change=change))["passed"] is False

def test_campaign_keeps_all_failures_and_requires_three_of_five(evidence_factory):
    campaign = evidence_factory.campaign([True, True, True, False, False])
    report = score_campaign(campaign)
    assert report["gate_passed"] is True and report["passed_runs"] == 3
    assert len(report["runs"]) == 5
```

- [ ] **Step 2: Run scorer tests and verify RED**

Run: `.venv/bin/pytest tests/test_routing_score.py -q`

Expected: FAIL because `score_run` and `score_campaign` do not exist.

- [ ] **Step 3: Implement minimal strict evidence parsing**

```python
def score_campaign(path: Path, expected_runs: int = 5) -> dict:
    runs = sorted(p for p in path.glob("run-*") if p.is_dir())
    if len(runs) != expected_runs:
        return {"gate_passed": False, "passed_runs": 0,
                "failures": [f"expected {expected_runs} runs; found {len(runs)}"], "runs": []}
    scored = [score_run(run) for run in runs]
    passed = sum(bool(run["passed"]) for run in scored)
    return {"schema_version": 1, "gate_passed": passed >= 3,
            "passed_runs": passed, "required_runs": 3, "total_runs": 5, "runs": scored}
```

`score_run` must parse every JSON/JSONL file strictly, match project and fixture hashes, derive admitted attempts from durable run-envelope `started`/`finished` evidence, retain all rejection/rollback error codes, require native backend and exact `10.0.6`, require at least one accepted placement-family action and one accepted `route_track`, and require the last native verification to contain empty geometric/connectivity evidence with no recovery/evidence error. It must report actual elapsed seconds and fail over 1200 even when the final tool call finishes cleanly.

- [ ] **Step 4: Run focused and whole-suite tests**

Run: `.venv/bin/pytest tests/test_routing_score.py tests/test_routing_session.py tests/test_run_envelope.py -q`

Expected: PASS with malformed/missing evidence rejected and all failed runs preserved.

Run: `.venv/bin/pytest -q`

Expected: PASS with no existing M0/M1/MCP regression.

- [ ] **Step 5: Commit the scorer**

```bash
git add eval/routing_smoke/score.py tests/test_routing_score.py
git commit -m "Add fail-closed M2 routing scorer"
```

### Task 4: Execute five native host-driven placement/routing runs

**Files:**
- Create (ignored evidence): `runs/routing/m2-2026-10-09/run-{1..5}/...`
- Create (ignored evidence): `runs/routing/m2-2026-10-09/report.json`
- Create: `playbooks/routing/m2-tiny.md`
- Modify: `docs/capabilities/m2-progress.md`

**Interfaces:**
- Consumes: Tasks 1–3, the running KiCad 10.0.6 PCB Editor IPC server, and the existing 14 local MCP tools.
- Produces: five immutable run bundles containing the exact input project, host transcript, MCP action/budget ledger, native checkpoint/verification artifacts, final board, score, and all failure evidence.

- [ ] **Step 1: Write and freeze the host playbook before any run**

The playbook must say: call `pcb_status`, `pcb_connect`, `pcb_summary`, initial `pcb_verify_geometry`, all three `pcb_get_footprint`, both `pcb_net_info`, and `pcb_render_board`; create `baseline`; make at least one host-selected placement-family write; after every write query a fresh revision; choose every route point/layer/width/via explicitly; use strict mode; never invoke an autorouter; never automatically retry an uncertain write; finish with `pcb_verify_geometry`, `pcb_list_unrouted`, `pcb_summary`, and a final render. It may describe tool semantics but must not contain route coordinates or a golden topology.

- [ ] **Step 2: Verify native preconditions and prepare five isolated runs**

Run: `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli version`

Expected: exactly `10.0.6`.

Run: `.venv/bin/python -m eval.routing_smoke.prepare --fixture fixtures/routing/tiny --campaign runs/routing/m2-2026-10-09 --repeats 5`

Expected: five new run directories; refusal if any target already exists.

For each run, open only that run's `project/board.kicad_pcb` in PCB Editor, resolve the exact PCB Editor socket/document through `pcb_connect`, and verify the returned project path, native server version, and zero prior admitted attempts before the first mutation. Do not close or discard any unrelated user document.

- [ ] **Step 3: Run the frozen host playbook independently for runs 1–5**

For each run, start the policy-free relay against that run's board and service directory. The subscribed Codex host reads only the benchmark/playbook plus that run's tool results and chooses its placement and route actions. Each tool call is submitted as one JSON command to the relay and recorded before the next decision.

Expected per run: no automatic uncertainty retry; every rejected action remains in evidence; the final board and native verification are retained whether the run passes or fails. A failure does not stop preparation/execution of later runs unless the shared native environment itself is uncertain or unsafe.

- [ ] **Step 4: Score after each run and aggregate only after all five**

Run: `.venv/bin/python -m eval.routing_smoke.score --campaign runs/routing/m2-2026-10-09`

Expected: `report.json` lists exactly five runs and every rejection/failure. `gate_passed` is true only when at least three runs independently satisfy native clean DRC/parity/connectivity and the frozen envelope.

- [ ] **Step 5: Commit playbook and factual progress, not ignored raw evidence**

```bash
git add playbooks/routing/m2-tiny.md docs/capabilities/m2-progress.md
git commit -m "Run M2 single-agent native routing feasibility"
```

The progress document must state the exact pass count, run paths, host/model fields actually exposed, unavailable fields, action/elapsed distributions, all failure categories, whether the gate passed, and that raw `runs/` evidence is local/ignored. Do not call M2 complete if fewer than three pass or any scorer evidence error remains unresolved.

### Task 5: Whole-change verification and M2 decision

**Files:**
- Modify: `PCB Harness — Development Roadmap.md`
- Modify: `README.md`
- Modify: `docs/mcp.md`
- Modify: `docs/capabilities/m2-progress.md`

**Interfaces:**
- Consumes: the complete Task 4 campaign report and all earlier M2 commits.
- Produces: a repository status that distinguishes implementation readiness, experiment outcome, local raw evidence, unresolved limitations, and the next milestone decision.

- [ ] **Step 1: Add result-aware documentation tests**

```python
def test_m2_docs_match_aggregate_report():
    report = json.loads((CAMPAIGN / "report.json").read_text())
    progress = (ROOT / "docs/capabilities/m2-progress.md").read_text()
    assert f'{report["passed_runs"]}/5' in progress
    assert ("Gate: PASS" if report["gate_passed"] else "Gate: FAIL") in progress
    assert "provider tokens: unavailable" in progress
    assert "provider cost: unavailable" in progress
```

Keep this as an evidence test that skips only when the local ignored campaign is absent; CI still validates the tracked fixture/session/scorer behavior with synthetic evidence.

- [ ] **Step 2: Run final verification**

Run: `.venv/bin/pytest -q`

Expected: all tests PASS.

Run: `.venv/bin/pip check`

Expected: `No broken requirements found.`

Run: `git diff --check`

Expected: no output.

Run the native final verification command recorded by Task 4 once more against every passing run's saved board copy; any drift changes that run to failed and requires regenerating the aggregate report, never editing the report by hand.

- [ ] **Step 3: Request one fresh whole-change review**

Review the merge-base-to-HEAD package against the spec, this plan's Global Constraints and Review Focus, plus `docs/capabilities/m2-progress.md`. Require the reviewer to inspect that neither the relay, scorer, fixture, nor playbook contains hidden route-selection logic and that failure evidence cannot be scored away.

- [ ] **Step 4: Apply at most one Important/Critical RED→GREEN fix pass**

For every accepted finding, first add the smallest reproducing test and watch it fail, then implement the fix and rerun the focused and whole suite. Record Minor findings as deferred; do not dispatch a duplicate review.

- [ ] **Step 5: Commit final factual status**

```bash
git add README.md docs/mcp.md docs/capabilities/m2-progress.md 'PCB Harness — Development Roadmap.md' tests
git commit -m "Record M2 routing feasibility decision"
```

If the aggregate gate passes, mark only M2 routing feasibility complete and recommend M3 as the next milestone. If it fails, keep M2 open and classify whether geometry context, tool ergonomics, host limitations, or environment failures dominated before proposing any multi-agent work.
