# M3 Circuit Grounding and Fabrication Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task inline, as selected in the approved design spec. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the M3 requirements-to-reviewed-circuit-to-native-bootstrap pipeline, prove that independently specified circuit mistakes are rejected, and keep unknown critical facts and incomplete fabrication evidence out of release eligibility.

**Architecture:** Versioned local JSON bundles carry requirements, parts, source facts, circuit, constraints, independent checklist, and a service-specific fabrication profile. Separate validators, provenance checks, circuit review, rule compilation, and native writers produce hash-bound reports. Synthetic fixtures calibrate these components; actual STM32 part allocation and full-board layout remain M4.

**Tech Stack:** Python 3.11; `jsonschema==4.26.0` (already installed locally, add as an explicit runtime dependency); KiCad CLI stable `10.0.6`; pytest 9.1.1. No model provider, network fetch, inference SDK, or automatic router in the implementation.

**Spec:** `PCB Harness — Design Spec (v2).md`, sections 3–5, 8, and 12; `PCB Harness — Development Roadmap.md`, M3. These existing approved documents are the design authority.

## Global Constraints

- Ordinary local use requires no model-provider API key. The subscribed host owns model decisions; deterministic tools validate and serialize caller inputs.
- KiCad is the native source of geometry and ERC/DRC/parity evidence; Memory and synthetic facts cannot prove a real board works.
- Critical facts need human confirmation before release. The agent must never create or promote a production human confirmation.
- Manufacturer operating conditions and absolute maximum ratings are separate facts. Engineering targets are labeled engineering choices, never manufacturer minima.
- Circuit review consumes an independently supplied checklist; neither circuit nor generated PCB can define its own correctness oracle.
- Required constraints are checked from requirements/checklist toward constraints, so an omitted constraint is a failure.
- Unknown/manual critical facts close release eligibility. A structurally complete profile is distinct from confirmed manufacturing compliance.
- The MCU target remains STM32F103C8T6 with concurrent interfaces and external CAN controllers. M3 tests the native USB/CAN conflict detector; M4 selects/verifies the complete real BOM and firmware/resource allocation.
- Exact stable KiCad `10.0.6` is required for native acceptance. New generated profiles do not relax the existing M0/M1 native-write guard; custom-rule IPC integration is outside M3.
- Writers create fresh project directories under `runs/`, reject overwrite/symlink/path escape, never touch a user editor document, and serialize explicitly supplied placement coordinates. No copper routing is generated.
- Retain failure reports and native raw artifacts. A clean unrouted bootstrap is not routed, design-validated, fabrication-reviewed, or hardware-tested.
- Keep the current authorized branch `work/m0-kicad-capability`; local commits only. Implementation is inline with one fresh final reviewer.

## Review Focus

- A circuit and asset map changed together must not evade the independent expected-pin/interface checklist; matching generated connectivity alone never proves functional correctness.
- Truncated JSON, duplicate keys, nonfinite values, remote schema references, path traversal, and symlinked source/assets must be rejected before output creation or document access outside the bundle.
- A confirmation attached to an old document/asset hash must not confirm a new revision; synthetic evidence must not confer production release eligibility.
- Unknown service-dependent fabrication categories, a removed required constraint, or a design target below a confirmed manufacturing floor must close the relevant gate rather than vanish from reports.
- Native command failure, stale reports, an incomplete generated project, or a failed upstream review must never yield accepted bootstrap evidence or overwrite an existing run.

## Scope and document model

Use local files only during validation. Source acquisition is an explicit preparation step; a URL alone is not cached evidence. Schema objects use `additionalProperties: false`, `schema_version: 1`, stable text IDs, finite numeric values with explicit units, and no runtime `$ref` downloads. Cross-document references and uniqueness are semantic checks after schema validation.

The input bundle contains:

| File | Contract |
| --- | --- |
| `requirements.json` | `id`, functional requirements with IDs, power inputs, board size/layers/thickness, interface IDs/kind/count/role/rate with units, concurrent interface groups, environment, assembly choice |
| `documents.json` | document ID/title/revision/source URL/retrieval date, local relative path, SHA-256, license/redistribution status; source may be `manufacturer`, `engineering_choice`, or `synthetic` |
| `parts.json` | part ID/full MPN/manufacturer/package/revision/lifecycle, symbol/footprint IDs and local paths/hashes/licenses, pins with stable IDs/numbers/names/types, symbol-pin→pad mapping, recommended voltage domains, separate absolute-maximum fact IDs, required-component/errata fact IDs |
| `facts.json` | fact ID/document ID/page or section/claim, status `confirmed` or `unconfirmed`, critical flag, units/value when numeric, provenance hash; confirmation identity and exact document hash required when confirmed |
| `circuit.json` | circuit/revision IDs, instances with stable ID/ref/part ID/value/block/source facts and caller-specified schematic/PCB bootstrap coordinates; nets with ID/name/class/voltage range and endpoints; intentional no-connect endpoints with reason/fact; interface assignments and errata mitigations |
| `constraints.json` | constraint ID/requirement IDs/fact IDs/status/scope/severity/mandatory flag, evaluation kind `rule`, `visual`, or `manual`, quantity/units/tolerance/evaluator/evidence, explicitly separate manufacturer floor and engineering target |
| `checklist.json` | independent checklist ID/revision/provenance and exact expected refs/MPNs/packages/pin-role→net mappings, interfaces/counts/roles/concurrency, required facts/constraints/errata mitigations/no-connect endpoints and known peripheral conflict rules |
| `fabrication.json` | profile/revision ID, vendor/service/source/retrieval, stackup/material/thickness/copper per layer/finish/mask/via process/assembly, and a keyed requirement for every fabrication category below |

Fabrication categories are explicit: track width, copper clearance, through-via drill/diameter/annular ring, inner-layer drill-to-copper, PTH/NPTH sizes and clearances, hole-to-hole, copper-to-routed-edge, slots, mask opening/web, silkscreen width/height/clearance, and assembly capabilities/spacing. Each category records applicable/not-applicable with reason, source facts, manufacturer floor, design target, units, status, and evaluator. Missing categories are structural failures; unsupported/manual evaluators remain in compliance results. Actual JLCPCB reference data remains unconfirmed until a person verifies exact selected service/stackup applicability.

## Source/API checks completed before planning

- Installed CLI reports `10.0.6`. Local `sch export netlist --help` supports `--format kicadxml`; `sch export svg --help` supports a fresh output directory.
- Installed JSON Schema library is `4.26.0`; use `Draft202012Validator` with an offline registry and explicit format checks. Official docs: <https://python-jsonschema.readthedocs.io/en/stable/validate/>.
- KiCad custom rules distinguish `track_width`, `clearance`, `via_diameter`, `hole_size`, `annular_width`, `hole_clearance`, `hole_to_hole`, and `edge_clearance`. Documented behavior is a candidate API, not native acceptance: <https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom-design-rules>.
- CLI acceptance commands: <https://docs.kicad.org/10.0/en/cli/cli.html>.
- JLCPCB reference capabilities include service-dependent and inner-layer constraints; retain provenance rather than copying a generic three-number profile: <https://jlcpcb.com/capabilities/pcb-capabilities>.

---

### Task 1: Versioned schemas and a strict offline bundle loader

**Files:**
- Create: `src/pcb_harness/circuit/__init__.py`, `src/pcb_harness/circuit/bundle.py`
- Create: `src/pcb_harness/circuit/schemas/{requirements,documents,parts,facts,circuit,constraints,checklist,fabrication}.schema.json`
- Create: `schemas/README.md` (points to packaged authoritative schema files)
- Modify: `pyproject.toml` (explicit pinned dependency and schema package data)
- Test: `tests/test_circuit_bundle.py`

**Interfaces:**
- Consumes: the eight local JSON files described above.
- Produces: `load_bundle(root: Path) -> dict[str, dict]`, `validate_document(kind: str, data: dict) -> None`, `bundle_hashes(root: Path) -> dict[str, str]`, and `resolve_local(root: Path, relative: str) -> Path`.

- [ ] **Step 1: Write failing contract/security tests**

```python
def test_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path):
    from pcb_harness.circuit.bundle import load_bundle
    for text in ('{"schema_version":1,"schema_version":2}', '{"schema_version":NaN}'):
        (tmp_path / "requirements.json").write_text(text)
        with pytest.raises(ValueError):
            load_bundle(tmp_path)

@pytest.mark.parametrize("path", ["../outside.json", "/tmp/outside.json"])
def test_local_reference_cannot_escape_bundle(tmp_path, path):
    from pcb_harness.circuit.bundle import resolve_local
    with pytest.raises(ValueError):
        resolve_local(tmp_path, path)
```

Also cover an intermediate symlink, unsupported schema version, unknown properties, invalid units/counts/confirmation format, missing file, duplicate IDs, and attempted remote `$ref` resolution. Validate every packaged schema with `Draft202012Validator.check_schema` and verify installed-package schema access without relying on repository-relative paths.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest tests/test_circuit_bundle.py -q`

Expected: FAIL because the bundle API does not exist.

- [ ] **Step 3: Implement strict decoding and offline schema validation**

```python
def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

def reject_constant(value):
    raise ValueError(f"nonfinite JSON value: {value}")
```

Load with these hooks, reject floating overflow recursively, validate against bundled schemas through `importlib.resources`, and use an offline registry. Resolve each referenced path beneath the input root without following any symlink component. SHA-256 each input JSON and referenced artifact. Reject duplicate IDs within each domain and duplicate instance refs before downstream writers.

- [ ] **Step 4: Run GREEN and package validation**

Run: `.venv/bin/python -m pytest tests/test_circuit_bundle.py -q`

Expected: PASS; malformed inputs fail before any output file is created.

- [ ] **Step 5: Commit**

Run: `git add src/pcb_harness/circuit schemas/README.md pyproject.toml tests/test_circuit_bundle.py`

Run: `git commit -m "Add strict M3 circuit bundle schemas"`

### Task 2: Hash-bound document facts and parts assets

**Files:**
- Create: `src/pcb_harness/circuit/provenance.py`, `src/pcb_harness/circuit/sexpr.py`, `src/pcb_harness/circuit/assets.py`
- Create: `docs_store/README.md`, `parts/README.md`
- Create: `fixtures/circuit/tiny/{requirements,documents,parts,facts,circuit,constraints,checklist,fabrication}.json`
- Create: `fixtures/circuit/tiny/sources/fixture-design.md`
- Create: `fixtures/circuit/tiny/assets/Harness.kicad_sym`, `fixtures/circuit/tiny/assets/Harness.pretty/Probe_R.kicad_mod`
- Test: `tests/test_circuit_provenance.py`, `tests/test_circuit_assets.py`
- Create: `tests/conftest.py` (M3 copied-bundle fixtures; preserve any existing content if present)

**Interfaces:**
- Consumes: Task 1 `load_bundle`, `resolve_local`, and the existing reviewed three-resistor circuit/asset definitions under `fixtures/routing/tiny/`.
- Produces: `audit_provenance(bundle: dict, root: Path) -> dict`, `parse_sexpr(text: str) -> list`, `dump_sexpr(node: list) -> str`, `load_part_assets(part: dict, root: Path) -> dict` returning embedded symbol definition, footprint tree, symbol pin geometry/types, and actual pad-number multiset.
- Test fixture: `valid_bundle(tmp_path) -> tuple[dict, Path]` copies `fixtures/circuit/tiny` into a fresh temporary input root and returns `load_bundle(root), root`.

- [ ] **Step 1: Write RED tests**

```python
def test_changed_document_cannot_reuse_confirmation(valid_bundle):
    from pcb_harness.circuit.provenance import audit_provenance
    bundle, root = valid_bundle
    (root / "sources/fixture-design.md").write_text("different revision\n")
    report = audit_provenance(bundle, root)
    assert report["passed"] is False
    assert report["release_eligible"] is False

def test_synthetic_confirmations_cannot_release_real_hardware(valid_bundle):
    from pcb_harness.circuit.provenance import audit_provenance
    bundle, root = valid_bundle
    report = audit_provenance(bundle, root)
    assert report["release_eligible"] is False
```

Cover mismatched MPN/package revision, missing source page/section, stale asset hash, unknown pin type, pad mapping to nonexistent pad, exposed pad omitted, duplicate pad numbers represented as repeated physical pads, absolute-max fact mistakenly used as an operating-domain fact, and S-expression strings containing quotes/backslashes/newlines. Reject malformed/truncated S-expressions and never use `eval`.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest tests/test_circuit_provenance.py tests/test_circuit_assets.py -q`

Expected: FAIL on absent APIs.

- [ ] **Step 3: Add provenance/asset audit and the synthetic fixture**

The source fixture document identifies all three parallel resistors, expected pin 1 `/NET_A`, pin 2 `/NET_B`, original native acceptance, asset authorship, and synthetic scope. It is an authored test oracle, not a manufacturer datasheet. Preserve explicit `synthetic` source classification and unconfirmed real release status. Copy the authored symbol/footprint definitions and bind their hashes; change neither existing capability nor routing fixtures.

```python
@pytest.fixture
def valid_bundle(tmp_path):
    root = tmp_path / "input"
    shutil.copytree(ROOT / "fixtures/circuit/tiny", root)
    return load_bundle(root), root
```

```python
def same_document_revision(fact, document):
    return fact["document_sha256"] == document["sha256"]
```

Audit document bytes and fact/document/confirmation binding, asset identity/hash/license metadata and electrical pin coverage; issue structured IDs for every unknown/mismatch. Keep `passed` (consistent evidence) separate from `release_eligible` (no synthetic/unconfirmed critical dependency). Implement the small quoted-string S-expression parser/serializer and inspect actual library pins and pad numbers, rather than trusting the circuit's mapping.

- [ ] **Step 4: Run GREEN**

Run: `.venv/bin/python -m pytest tests/test_circuit_bundle.py tests/test_circuit_provenance.py tests/test_circuit_assets.py -q`

Expected: PASS; fixture is internally auditable and production release remains false.

- [ ] **Step 5: Commit**

Run: `git add src/pcb_harness/circuit fixtures/circuit/tiny docs_store/README.md parts/README.md tests/conftest.py tests/test_circuit_provenance.py tests/test_circuit_assets.py`

Run: `git commit -m "Add hash-bound circuit facts and parts assets"`

### Task 3: Independent upstream circuit review and constraint coverage

**Files:**
- Create: `src/pcb_harness/circuit/review.py`, `src/pcb_harness/circuit/calculations.py`
- Create: `checklists/circuit/README.md`, `checklists/circuit/stm32f103-concurrency.json`
- Test: `tests/test_circuit_review.py`, `tests/test_circuit_calculations.py`
- Modify: `tests/conftest.py` (adds `circuit_case` fixture)

**Interfaces:**
- Consumes: Task 1 bundle, Task 2 audited facts/assets, and an independent checklist loaded from its explicit caller-specified path.
- Produces: `review_circuit(bundle: dict, root: Path, checklist: dict) -> dict` with `passed`, `release_eligible`, stable `issues`, `unknowns`, `coverage`, and `input_sha256`; `power_budget(loads: list[dict], regulator: dict) -> dict` with formula/units/assumptions and explicit unknown inputs.
- Test fixture: `circuit_case(variant: str) -> tuple[dict, Path, dict]` deep-copies the positive bundle/checklist and applies one explicit mutation; it never changes the independent checklist to accommodate a circuit mutation. Variant inputs needing active interfaces/errata extend the synthetic baseline with declarative synthetic parts/facts and a separate expected checklist first, then introduce the fault.

- [ ] **Step 1: Write RED tests with an independent oracle**

```python
@pytest.mark.parametrize("variant,code", [
    ("wrong_pinout", "PINOUT_MISMATCH"),
    ("wrong_footprint", "FOOTPRINT_MISMATCH"),
    ("missing_interface", "INTERFACE_MISSING"),
    ("voltage_mismatch", "VOLTAGE_MISMATCH"),
    ("ignored_errata", "ERRATA_UNRESOLVED"),
    ("duplicate_ref", "DUPLICATE_REF"),
    ("no_connect_mismatch", "NO_CONNECT_MISMATCH"),
    ("native_usb_can_concurrent", "PERIPHERAL_CONFLICT"),
])
def test_independent_review_rejects_consistent_but_wrong_circuit(circuit_case, variant, code):
    from pcb_harness.circuit.review import review_circuit
    bundle, root, checklist = circuit_case(variant)
    result = review_circuit(bundle, root, checklist)
    assert result["passed"] is False
    assert code in {issue["code"] for issue in result["issues"]}
```

Keep the checklist unchanged when mutating both circuit and part mappings. Additional tests remove a required constraint entirely, connect an intentional no-connect endpoint, omit a power/reset/boot/debug requirement, allocate one physical pin to conflicting interfaces, swap recommended/absolute ranges, and present unknown critical facts. Native USB plus native CAN concurrent on exact STM32F103C8T6 is blocked; external CAN assignments are not falsely classified as native peripheral use. The checked-in concurrency checklist cites the existing target decision and ST source; it does not fabricate confirmed real package facts.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest tests/test_circuit_review.py tests/test_circuit_calculations.py -q`

Expected: FAIL on missing review/calculation APIs.

- [ ] **Step 3: Implement deterministic review**

```python
def voltage_compatible(net_range, operating_range):
    return (operating_range[0] <= net_range[0]
            and net_range[1] <= operating_range[1])
```

Resolve endpoints by stable instance/pin IDs, cross-check refs/MPN/package/assets against the external checklist, reject duplicate/unknown endpoints, and compare expected pin-role/net assignments even if generated connectivity would match. Require every electrical pin to have a net or an allowed intentional no-connect declaration. Validate interface count/role/rates and required concurrent groups against requirements/checklist. Check errata mitigations and constraint coverage from the independent required sets; unimplemented manual critical checks remain unknown. Run provenance audit first and preserve its failures.

Power calculations use `sum(V * I)` and LDO dissipation `(Vin - Vout) * I`, with finite nonnegative SI-unit inputs, supplied regulator limits, and stated assumptions. Unknown current/thermal facts produce unknown, not zero or pass. These formula checks do not claim firmware throughput or full M4 thermal feasibility.

- [ ] **Step 4: Run GREEN**

Run: `.venv/bin/python -m pytest tests/test_circuit_review.py tests/test_circuit_calculations.py tests/test_circuit_provenance.py -q`

Expected: PASS; all eight gate negatives rejected by upstream review, with no reliance on generated PCB parity.

- [ ] **Step 5: Commit**

Run: `git add src/pcb_harness/circuit/review.py src/pcb_harness/circuit/calculations.py checklists/circuit tests/conftest.py tests/test_circuit_review.py tests/test_circuit_calculations.py`

Run: `git commit -m "Add independent upstream circuit review"`

### Task 4: Complete fabrication profile validation and native-tested rule compilation

**Files:**
- Create: `src/pcb_harness/fabrication/__init__.py`, `src/pcb_harness/fabrication/profile.py`, `src/pcb_harness/fabrication/compiler.py`
- Create: `parts/fabrication/jlcpcb-reference-unconfirmed.json`
- Test: `tests/test_fabrication_profile.py`, `tests/test_fabrication_native.py`
- Modify: `tests/conftest.py` (adds `profile_case` fixture)

**Interfaces:**
- Consumes: Task 1 fabrication/constraint schemas and Task 2 source facts, plus existing `pcb_harness.native_reports.run_verification`.
- Produces: `review_profile(profile: dict, facts: dict) -> dict`; `compile_rules(profile: dict, constraints: dict) -> dict` returning `.kicad_pro` settings data, `.kicad_dru` text, and explicit supported/manual/unknown compliance entries. No file mutation in compilation.
- Test fixture: `profile_case(variant: str) -> tuple[dict, dict, dict]` returns `profile, facts, constraints`; use confirmed synthetic numerical floors for native compiler calibration only. They never confer eligibility on the unconfirmed real JLCPCB reference profile.

- [ ] **Step 1: Write RED tests**

```python
def test_three_number_profile_cannot_be_complete(profile_case):
    from pcb_harness.fabrication.profile import review_profile
    profile, facts, constraints = profile_case("routing_values_only")
    result = review_profile(profile, facts)
    assert result["passed"] is False
    assert result["release_eligible"] is False

def test_engineering_target_cannot_relax_manufacturer_floor(profile_case):
    from pcb_harness.fabrication.compiler import compile_rules
    profile, facts, constraints = profile_case("target_below_floor")
    with pytest.raises(ValueError, match="manufacturing floor"):
        compile_rules(profile, constraints)
```

Cover every missing fabrication category, inconsistent layer count/copper map/via process, `not_applicable` without reason, unit confusion, net-specific stricter circuit constraints, unsupported evaluator retained in report, unconfirmed critical category, and malicious custom-rule names/net strings escaped through the S-expression serializer.

Native tests copy the existing routed capability project into a fresh test output and apply the compiled profile. Independently modify width, clearance, via drill/diameter/annular geometry, drilled-hole clearance, hole-to-hole spacing, and copper-to-edge geometry. The generated `.kicad_dru` must reject these negatives through real CLI even when the corresponding broad project minimum is relaxed; a clean baseline must pass. Net-class preferred sizes alone cannot satisfy enforcement tests.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest tests/test_fabrication_profile.py tests/test_fabrication_native.py -q`

Expected: FAIL on absent profile/compiler APIs.

- [ ] **Step 3: Implement profile coverage and compiled constraints**

Use explicit unit conversions and `effective_min = max(confirmed_manufacturer_floor, engineering_target, circuit_min)` only when their source status and domain are known. Never infer a missing manufacturer floor from an engineering target. Emit explicit-unit custom constraints for the native-tested subset; include profile/rule/source IDs in a hash-bound compilation manifest. Other profile categories remain visible as manual or unknown, preventing release eligibility where critical. Build the JLCPCB reference profile with complete category structure, selected-service placeholders represented as explicit unknown data, and engineering targets from the approved spec (`0.20mm` width/clearance, `0.30/0.60mm` via drill/diameter, `0.50mm` routed edge); it is deliberately not release eligible. Do not invent a confirmed JLCPCB minimum.

```python
def minimum_for(confirmed_floor, target, circuit_min):
    return max(confirmed_floor, target, circuit_min)
```

- [ ] **Step 4: Run GREEN including native negatives**

Run: `.venv/bin/python -m pytest tests/test_fabrication_profile.py tests/test_fabrication_native.py -q`

Expected: PASS; recorded native constraints reject all chosen bad fixtures and no unknown is promoted to pass.

- [ ] **Step 5: Commit**

Run: `git add src/pcb_harness/fabrication parts/fabrication tests/conftest.py tests/test_fabrication_profile.py tests/test_fabrication_native.py`

Run: `git commit -m "Add provenance-aware fabrication rule compiler"`

### Task 5: Readable schematic and unrouted PCB writer with native bootstrap verification

**Files:**
- Create: `src/pcb_harness/circuit/writer.py`, `src/pcb_harness/circuit/bootstrap.py`
- Test: `tests/test_circuit_writer.py`, `tests/test_circuit_bootstrap.py`

**Interfaces:**
- Consumes: Task 1 bundle/hash helpers, Task 2 asset parser, Task 3 review report, Task 4 compilation output, and existing native report parser/runner.
- Produces: `write_project(bundle: dict, root: Path, checklist: dict, output: Path) -> dict`; `verify_bootstrap(project: Path, cli: Path) -> dict` with native commands, raw reports, exported netlist, input/output hashes, geometry/ERC/parity/connectivity categories, and explicit `unrouted` status.

- [ ] **Step 1: Write RED tests**

```python
def test_writer_refuses_failed_upstream_review(circuit_case, tmp_path):
    from pcb_harness.circuit.writer import write_project
    bundle, root, checklist = circuit_case("wrong_pinout")
    output = tmp_path / "runs/project"
    with pytest.raises(ValueError, match="circuit review"):
        write_project(bundle, root, checklist, output)
    assert not output.exists()

def test_native_bootstrap_has_clean_erc_parity_and_unrouted_connectivity(valid_bundle, tmp_path):
    from pcb_harness.circuit.writer import write_project
    from pcb_harness.circuit.bootstrap import verify_bootstrap
    bundle, root = valid_bundle
    checklist = bundle["checklist"]
    output = tmp_path / "runs/bootstrap"
    write_project(bundle, root, checklist, output)
    result = verify_bootstrap(output / "board.kicad_pcb", CLI)
    assert result["accepted"] is True
    assert result["erc_clean"] is True
    assert result["parity_clean"] is True
    assert result["zero_unconnected"] is False
    assert result["routed"] is False
```

Cover output reuse/symlink/traversal, stable IDs/repeat serialization, escaped values/labels/source notes, multiple asset libraries, caller-specified coordinates unchanged, intentional no-connect markers, mapped pad nets, wrong exported-netlist endpoints, native CLI failure/stale artifacts, and drift between verification snapshot and project.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest tests/test_circuit_writer.py tests/test_circuit_bootstrap.py -q`

Expected: FAIL on absent writer/bootstrap APIs.

- [ ] **Step 3: Implement deterministic native serialization and validation**

Use Task 2 S-expression trees for authored asset definitions, stable UUIDv5 from circuit/instance/pin IDs, one readable sheet with block/source notes, explicit symbol positions, net labels and intentional no-connect markers. Build the PCB from mapped footprint trees and explicit bootstrap positions, matching schematic paths/pin functions, enabled layers and caller-declared rectangular outline. Create local library tables and copy audited assets; emit zero segments/vias/zones. Apply Task 4 project/rule output. Refuse unsupported asset/layout forms with clear capability errors rather than quietly substituting assets.

```python
def stable_uuid(circuit_id, object_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"pcb-harness/m3/{circuit_id}/{object_id}"))
```

Verification creates a fresh saved project copy and checks exact CLI version. Run `sch erc`, `pcb drc --schematic-parity`, `sch export netlist --format kicadxml`, and `sch export svg`; record commands/exit/stdout/stderr plus raw JSON/XML/SVG. Parse netlist endpoints independently and compare with circuit/checklist. DRC exit 5 is accepted only when every geometric/parity section is empty and the only remaining issues are expected unrouted connectivity. ERC or parity failure always rejects bootstrap. Return `release_eligible: false` for synthetic/unconfirmed facts and do not use the IPC editor or modify its write gate.

Native test constants are defined in each native test module: `ROOT = Path(__file__).resolve().parents[1]`, `FIXTURE = ROOT / "fixtures/circuit/tiny"`, `CHECKLIST = FIXTURE / "checklist.json"`, and `CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")`. Skip native tests only when no CLI is installed, never when an installed CLI fails or has a different version. Pure validation tests always run.

- [ ] **Step 4: Run GREEN and inspect schematic SVG**

Run: `.venv/bin/python -m pytest tests/test_circuit_writer.py tests/test_circuit_bootstrap.py tests/test_circuit_review.py -q`

Expected: PASS; native schematic readable with refs/values/net labels/source notes, exact netlist/PCB parity, and no generated routing.

Render the test output SVG to a PNG with the installed `resvg-py` and inspect visually. If labels overlap, fix writer layout with a regression case; no review seat or new rendering dependency is needed.

- [ ] **Step 5: Commit**

Run: `git add src/pcb_harness/circuit/writer.py src/pcb_harness/circuit/bootstrap.py tests/test_circuit_writer.py tests/test_circuit_bootstrap.py`

Run: `git commit -m "Add reviewed native schematic and PCB bootstrap"`

### Task 6: Reproducible M3 acceptance runner and factual milestone decision

**Files:**
- Create: `eval/circuit_smoke/__init__.py`, `eval/circuit_smoke/run.py`
- Create: `playbooks/circuit/m3-grounding.md`, `docs/capabilities/m3-progress.md`
- Modify: `README.md`, `PCB Harness — Development Roadmap.md`, `CONTRIBUTING.md`
- Test: `tests/test_m3_acceptance.py`

**Interfaces:**
- Consumes: Tasks 1–5; independent checklist path; fresh run output; exact CLI.
- Produces: `run_acceptance(bundle_root: Path, checklist_path: Path, output: Path, cli: Path) -> dict`, CLI `python -m eval.circuit_smoke.run --bundle ... --checklist ... --output ... --cli ...`, retained native positive/negative evidence and final M3 report.

- [ ] **Step 1: Write RED end-to-end gate tests**

```python
def test_acceptance_preserves_all_known_bad_results(tmp_path):
    from eval.circuit_smoke.run import run_acceptance
    result = run_acceptance(FIXTURE, CHECKLIST, tmp_path / "runs/m3", CLI)
    assert result["gate_passed"] is True
    assert set(result["circuit_negatives"]) == {
        "wrong_pinout", "wrong_footprint", "missing_interface", "voltage_mismatch",
        "ignored_errata", "duplicate_ref", "no_connect_mismatch", "native_usb_can_concurrent"}
    assert all(case["rejected"] for case in result["circuit_negatives"].values())
    assert result["release_eligible"] is False
```

Cover failed positive bootstrap, a negative circuit accepted, unknown critical fabrication evidence, tampered report/input hashes, and run-directory reuse. Acceptance must preserve the available case results if one later case fails.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest tests/test_m3_acceptance.py -q`

Expected: FAIL because the acceptance runner does not exist.

- [ ] **Step 3: Implement the deterministic acceptance CLI and docs**

Run the fixed synthetic positive fixture, all eight upstream circuit negatives, native compiler negatives and bootstrap checks. Mutations are explicit test inputs and never a repair/search loop. Write a frozen input manifest before work and preserve every case outcome/error plus upstream/compliance/native reports. Report `implementation_gate`, `native_bootstrap_gate`, `circuit_negative_gate`, `fabrication_negative_gate`, combined `gate_passed`, and separate `release_eligible` with blocking facts. Add playbook order: validate → audit → independent review → profile/coverage → write fresh bundle → native saved-copy verification → inspect SVG → report. State exact unsupported forms and unknown real target facts.

Update docs only from retained evidence. A passing M3 software acceptance gate does not freeze the real STM32 BOM, prove firmware fit, or confirm JLCPCB production readiness; those facts remain explicit M4/release blockers.

- [ ] **Step 4: Run acceptance and final checks**

Run: `.venv/bin/python -m pytest tests/test_m3_acceptance.py -q`

Expected: PASS.

Run: `.venv/bin/python -m eval.circuit_smoke.run --bundle fixtures/circuit/tiny --checklist fixtures/circuit/tiny/checklist.json --output runs/circuit/m3-2026-10-09 --cli /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`

Expected: retained report with all eight circuit negatives rejected, compiled-rule native negatives rejected, native positive bootstrap accepted, and production release false with stated blockers. Refuse any existing output directory.

Run: `.venv/bin/python -m pytest -q`

Expected: PASS, including the existing 263-test baseline.

Run: `.venv/bin/python -m pip check`

Expected: `No broken requirements found.`

Run: `git diff --check`

Expected: no output.

- [ ] **Step 5: Commit**

Run: `git add eval/circuit_smoke playbooks/circuit/m3-grounding.md docs/capabilities/m3-progress.md README.md 'PCB Harness — Development Roadmap.md' CONTRIBUTING.md tests/test_m3_acceptance.py`

Run: `git commit -m "Record M3 grounded circuit acceptance"`

## Final whole-change review and finish

Use executing-plans' single fresh final review against the recorded M3 base commit (`546a9fb` if unchanged before implementation) and final HEAD, with the exact Review Focus, approved design spec, plan and ledger rulings. Inspect independent checklist separation, fact confirmation binding, generated project/netlist identity, manual/unknown fabrication coverage, retained failures, no route selection and unchanged native-write safety. Accept/re-grade findings by user-visible effect. Apply one Important/Critical RED→GREEN fix pass and rerun the whole suite; defer Minor findings explicitly and do not dispatch a second review.

Preserve the local branch and all native run evidence. Mark M3 complete only if its acceptance report supports every M3 implementation/native/negative gate; otherwise state the exact failed gate. Keep actual-board release eligibility separate and start no M4 layout in this plan.

## Plan self-review

- Sections 3–5/8/12 coverage: Task 1 schemas; Task 2 document/asset provenance; Task 3 circuit/resource/voltage/errata/coverage/calculations; Task 4 complete fabrication structure and compiler negatives; Task 5 readable schematic/bootstrap/native exact connectivity; Task 6 retained gate evidence/docs.
- M4 full-BOM/pin scheduling/firmware/power-thermal feasibility, actual manufacturer human confirmations, and M5 release/manufacturing/hardware tests are explicit exclusions, not hidden implementation gaps.
- All consuming API signatures are produced by an earlier task. Schema names and fixture paths are consistent across tasks.
- Every Review Focus has a named owner and negative tests. No source URL alone or synthetic confirmation can confer production release eligibility.
- No provider keys, model inference, routing search, IPC mutation-gate expansion, merge, push, or production order is introduced.
