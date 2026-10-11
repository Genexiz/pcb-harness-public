import pytest
from pcb_harness.circuit.calculations import power_budget


def test_ldo_calculation_uses_supplied_current_and_limits():
    report = power_budget([{"voltage_v": 3.3, "current_a": 0.2, "confirmed": True}],
        {"input_v": 5, "output_v": 3.3, "max_current_a": 0.5, "max_dissipation_w": 0.3, "confirmed": True})
    assert report["output_power_w"] == pytest.approx(0.66)
    assert report["ldo_dissipation_w"] == pytest.approx(0.34)
    assert report["passed"] is False


def test_unknown_current_cannot_become_zero():
    report = power_budget([{"voltage_v": 3.3, "current_a": None, "confirmed": False}],
        {"input_v": 5, "output_v": 3.3, "max_current_a": 0.5, "max_dissipation_w": 1, "confirmed": True})
    assert report["status"] == "unknown"
    assert report["passed"] is False


@pytest.mark.parametrize("current", [-1, float("inf"), True])
def test_invalid_electrical_input_rejected(current):
    with pytest.raises(ValueError):
        power_budget([{"voltage_v": 3.3, "current_a": current, "confirmed": True}],
            {"input_v": 5, "output_v": 3.3, "max_current_a": 0.5, "max_dissipation_w": 1, "confirmed": True})
