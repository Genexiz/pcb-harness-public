import pytest
from pcb_harness.circuit.review import review_circuit


def test_independent_positive_review_accepts_synthetic_topology(circuit_case):
    bundle, root, checklist = circuit_case("positive")
    result = review_circuit(bundle, root, checklist)
    assert result["passed"] is True
    assert result["release_eligible"] is False


@pytest.mark.parametrize("variant,code", [
    ("wrong_pinout", "PINOUT_MISMATCH"), ("wrong_footprint", "FOOTPRINT_MISMATCH"),
    ("missing_interface", "INTERFACE_MISSING"), ("voltage_mismatch", "VOLTAGE_MISMATCH"),
    ("ignored_errata", "ERRATA_UNRESOLVED"), ("duplicate_ref", "DUPLICATE_REF"),
    ("no_connect_mismatch", "NO_CONNECT_MISMATCH"),
    ("native_usb_can_concurrent", "PERIPHERAL_CONFLICT"),
    ("missing_constraint", "CONSTRAINT_MISSING"),
])
def test_independent_review_rejects_consistent_but_wrong_circuit(circuit_case, variant, code):
    bundle, root, checklist = circuit_case(variant)
    result = review_circuit(bundle, root, checklist)
    assert result["passed"] is False
    assert code in {issue["code"] for issue in result["issues"]}


def test_external_can_not_classified_as_native_conflict(circuit_case):
    bundle, root, checklist = circuit_case("external_can")
    assert review_circuit(bundle, root, checklist)["passed"] is True


@pytest.mark.parametrize("usb,can", [("USB", "CAN1"), ("USB_FS", "CAN"), ("usb1", "can1")])
def test_native_peripheral_aliases_cannot_evade_conflict(circuit_case, usb, can):
    bundle, root, checklist = circuit_case("native_usb_can_concurrent")
    bundle["circuit"]["interfaces"][0]["peripheral"] = usb
    bundle["circuit"]["interfaces"][1]["peripheral"] = can
    result = review_circuit(bundle, root, checklist)
    assert "PERIPHERAL_CONFLICT" in {issue["code"] for issue in result["issues"]}


def test_unknown_native_peripheral_assignment_is_rejected(circuit_case):
    bundle, root, checklist = circuit_case("native_usb_can_concurrent")
    bundle["circuit"]["interfaces"][1]["peripheral"] = "misspelled_controller"
    result = review_circuit(bundle, root, checklist)
    assert "PERIPHERAL_UNKNOWN" in {issue["code"] for issue in result["issues"]}


@pytest.mark.parametrize("change", ["quantity", "value", "evaluator"])
def test_unsupported_mandatory_constraint_remains_unknown(circuit_case, change):
    bundle, root, checklist = circuit_case("positive")
    constraint = bundle["constraints"]["constraints"][0]
    constraint.update(status="confirmed", evidence=["TEST ONLY calibration record"])
    constraint[change] = None if change == "value" else "unsupported"
    result = review_circuit(bundle, root, checklist)
    assert {"code": "CONSTRAINT_UNVERIFIED", "id": "route-width"} in result["unknowns"]
    assert result["release_eligible"] is False


def test_changed_part_and_circuit_cannot_redefine_checklist(circuit_case):
    bundle, root, checklist = circuit_case("positive")
    bundle["parts"]["parts"][0]["mpn"] = "OTHER"
    for expected in bundle["checklist"]["expected_instances"]:
        expected["mpn"] = "OTHER"
    assert review_circuit(bundle, root, checklist)["passed"] is False


def test_duplicate_pin_allocation_blocks_review(circuit_case):
    bundle, root, checklist = circuit_case("external_can")
    bundle["circuit"]["interfaces"][1]["pin_ids"] = ["p1"]
    assert "PIN_ALLOCATION_CONFLICT" in {x["code"] for x in review_circuit(bundle, root, checklist)["issues"]}


def test_absolute_maximum_is_not_operating_voltage_fact(circuit_case):
    bundle, root, checklist = circuit_case("voltage_mismatch")
    bundle["facts"]["facts"][-1]["kind"] = "absolute_maximum"
    assert "FACT_KIND_MISMATCH" in {x["code"] for x in review_circuit(bundle, root, checklist)["issues"]}
