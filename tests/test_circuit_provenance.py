from pcb_harness.circuit.provenance import audit_provenance
from copy import deepcopy


def test_fixture_auditable_but_not_production_eligible(valid_bundle):
    bundle, root = valid_bundle
    result = audit_provenance(bundle, root)
    assert result["passed"] is True
    assert result["release_eligible"] is False


def test_changed_document_cannot_reuse_confirmation(valid_bundle):
    bundle, root = valid_bundle
    (root / "sources/fixture-design.md").write_text("different revision\n")
    result = audit_provenance(bundle, root)
    assert result["passed"] is False
    assert result["release_eligible"] is False


def test_stale_confirmation_rejected(valid_bundle):
    bundle, root = valid_bundle
    fact = bundle["facts"]["facts"][0]
    fact.update(status="confirmed", confirmation={"reviewer": "test-only", "document_sha256": "0" * 64})
    result = audit_provenance(bundle, root)
    assert "STALE_CONFIRMATION" in {x["code"] for x in result["issues"]}


def test_unknown_critical_fact_stays_unknown(valid_bundle):
    bundle, root = valid_bundle
    bundle["facts"]["facts"][0]["critical"] = True
    result = audit_provenance(bundle, root)
    assert result["unknowns"]
    assert result["release_eligible"] is False


def test_numeric_nominal_cannot_confirm_an_operating_range(valid_bundle):
    bundle, root = valid_bundle
    fact = deepcopy(bundle["facts"]["facts"][0])
    fact.update(id="operating", kind="operating", value=3.3, units="V")
    bundle["facts"]["facts"].append(fact)
    bundle["parts"]["parts"][0]["pins"][0].update(
        operating_range_v=[0, 6], operating_fact_id="operating")
    result = audit_provenance(bundle, root)
    assert {"code": "OPERATING_RANGE_UNKNOWN", "id": "p1"} in result["unknowns"]


def test_declared_operating_range_cannot_exceed_sourced_bounds(valid_bundle):
    bundle, root = valid_bundle
    fact = deepcopy(bundle["facts"]["facts"][0])
    fact.update(id="operating", kind="operating", value=3.3, units="V", range=[0, 3.6])
    bundle["facts"]["facts"].append(fact)
    bundle["parts"]["parts"][0]["pins"][0].update(
        operating_range_v=[0, 6], operating_fact_id="operating")
    result = audit_provenance(bundle, root)
    assert "FACT_RANGE_MISMATCH" in {issue["code"] for issue in result["issues"]}


def test_exact_sourced_operating_bounds_are_auditable(valid_bundle):
    bundle, root = valid_bundle
    fact = deepcopy(bundle["facts"]["facts"][0])
    fact.update(id="operating", kind="operating", value=3.3, units="V", range=[0, 3.6])
    bundle["facts"]["facts"].append(fact)
    bundle["parts"]["parts"][0]["pins"][0].update(
        operating_range_v=[0, 3.6], operating_fact_id="operating")
    result = audit_provenance(bundle, root)
    assert result["passed"] is True
    assert result["unknowns"] == []
