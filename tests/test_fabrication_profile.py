from copy import deepcopy
import pytest
from pcb_harness.fabrication.profile import review_profile
from pcb_harness.fabrication.compiler import compile_rules


def test_three_number_profile_cannot_be_complete(profile_case):
    profile, facts, constraints = profile_case("routing_values_only")
    result = review_profile(profile, facts)
    assert result["passed"] is False
    assert result["release_eligible"] is False


def test_engineering_target_cannot_relax_manufacturer_floor(profile_case):
    profile, facts, constraints = profile_case("target_below_floor")
    with pytest.raises(ValueError, match="manufacturing floor"):
        compile_rules(profile, constraints)


def test_unconfirmed_profile_has_complete_structure_but_no_release(profile_case):
    profile, facts, constraints = profile_case()
    result = review_profile(profile, facts)
    assert result["passed"] is True
    assert result["release_eligible"] is False
    assert len(result["unknowns"]) == 17


@pytest.mark.parametrize("change", ["missing_category", "wrong_copper", "no_reason", "wrong_units"])
def test_incomplete_fabrication_contract_rejected(profile_case, change):
    profile, facts, constraints = profile_case()
    if change == "missing_category":
        profile["categories"].pop()
    elif change == "wrong_copper":
        profile["copper_oz"].pop()
    elif change == "no_reason":
        profile["categories"][0]["applicable"] = False
    else:
        profile["categories"][0]["units"] = "in"
    assert review_profile(profile, facts)["passed"] is False


def test_net_specific_stricter_rule_and_manual_items_preserved(profile_case):
    profile, facts, constraints = profile_case()
    constraint = deepcopy(constraints["constraints"][0])
    constraint.update(id="power-width", scope="net:/NET_A", value=0.8)
    constraints["constraints"].append(constraint)
    result = compile_rules(profile, constraints)
    assert "0.8mm" in result["rules"]
    assert "A.NetName == '/NET_A'" in result["rules"]
    assert any(item["id"] == "slots" and item["status"] == "unknown" for item in result["compliance"])


def test_unsafe_condition_input_is_rejected(profile_case):
    profile, facts, constraints = profile_case()
    constraints["constraints"][0]["scope"] = "net:bad' || true"
    with pytest.raises(ValueError):
        compile_rules(profile, constraints)


def test_unsupported_fabrication_categories_remain_release_blockers(profile_case):
    profile, facts, constraints = profile_case()
    fact = facts["facts"][0]
    fact.update(status="confirmed", value=0.1, units="mm", confirmation={
        "reviewer": "TEST ONLY synthetic floor", "document_sha256": fact["document_sha256"]})
    for category in profile["categories"]:
        category.update(status="confirmed", manufacturer_floor=0.1, design_target=0.2, evaluator="rule")
    result = review_profile(profile, facts)
    assert result["passed"] is True
    assert result["release_eligible"] is False
    assert {item["id"] for item in result["unknowns"]} == {
        "pth_size", "npth_size", "slots", "mask_opening", "mask_web",
        "silk_width", "silk_height", "silk_clearance", "assembly_spacing"}
