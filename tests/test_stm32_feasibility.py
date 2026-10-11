"""Reject real resource conflicts and optimistic feasibility arithmetic."""
from copy import deepcopy
from pathlib import Path
import pytest

from pcb_harness.circuit.bundle import read_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs():
    return (read_json(ROOT / "benchmarks/stm32-communications/design.json"),
            read_json(ROOT / "checklists/stm32-communications/resources.json"))


def assess(design, checklist):
    from pcb_harness.orchestration.stm32_feasibility import assess_design
    return assess_design(design, checklist)


def test_chosen_default_pin_allocation_has_no_conflicts(inputs):
    report = assess(*inputs)
    assert report["resources"]["passed"]
    assert report["resources"]["unused_gpio"] == ["PA15", "PB3", "PB4"]
    assert report["human_confirmed"] is False


@pytest.mark.parametrize("mutation,code", [
    (lambda d: d["pins"][8].update(pin="PA13", number=34), "PIN_CONFLICT"),
    (lambda d: d["pins"][8].update(number=11), "PACKAGE_PIN"),
    (lambda d: d["pins"].pop(0), "MISSING_SIGNAL"),
    (lambda d: d["pins"][10].update(function="USART3_TX"), "PIN_FUNCTION"),
    (lambda d: d["interfaces"].pop("rs232"), "INTERFACE_SET"),
    (lambda d: d["interfaces"]["usb"].update(peripheral="CAN"), "INTERFACE_ALLOCATION"),
    (lambda d: d["interfaces"]["can_fd"].update(peripheral="CAN"), "INTERFACE_ALLOCATION"),
    (lambda d: d["dma"].append({"request": "SPI2_RX", "channel": 4}), "DMA_CONFLICT"),
    (lambda d: d["dma"][0].update(channel=1), "DMA_MAPPING"),
    (lambda d: d["dma"].pop(), "DMA_COVERAGE"),
    (lambda d: d["exti"][2].update(line=1), "EXTI_CONFLICT"),
    (lambda d: d["exti"].pop(), "EXTI_COVERAGE"),
    (lambda d: d.update(mcu="STM32F103CBT6"), "TARGET_CHANGED"),
    (lambda d: d.update(package="LQFP64"), "TARGET_CHANGED"),
])
def test_resource_negative_is_rejected(inputs, mutation, code):
    design, checklist = inputs
    mutation(design)
    report = assess(design, checklist)
    assert not report["resources"]["passed"]
    assert code in {issue["code"] for issue in report["resources"]["issues"]}


def test_wire_budget_uses_per_device_clock_and_retains_unknown_cpu(inputs):
    report = assess(*inputs)
    spi1 = report["scheduling"]["buses"][0]
    # (32+20 + 81.7778+20)us/1ms + (1024+20)us/10ms
    assert spi1["utilization"] == pytest.approx(0.2581777777777778)
    assert spi1["max_blocking_s"] == pytest.approx(0.001044)
    assert report["scheduling"]["wire_budget_passed"]
    assert report["scheduling"]["functional_timing_status"] == "unknown"


@pytest.mark.parametrize("mutation,code", [
    (lambda d: d["buses"][0]["jobs"][2].update(period_s=0.001), "BUS_UTILIZATION"),
    (lambda d: d["buses"][0]["jobs"][0].update(arrival_hz=100000), "FIFO_DEADLINE"),
    (lambda d: d["buses"][0]["jobs"][0].update(arrival_hz=1500), "SERVICE_RATE"),
    (lambda d: d["buses"][0]["jobs"].pop(), "BUS_CLIENT_COVERAGE"),
    (lambda d: d["buses"][0]["jobs"][0].update(clock_hz=19000000), "SPI_CLOCK"),
])
def test_wire_budget_negatives(inputs, mutation, code):
    design, checklist = inputs
    mutation(design)
    report = assess(design, checklist)
    assert not report["scheduling"]["wire_budget_passed"]
    assert code in {issue["code"] for issue in report["scheduling"]["issues"]}


def test_can_fifo_bound_includes_its_own_service_period(inputs):
    design, checklist = inputs
    design["buses"][0]["jobs"][0].update(period_s=0.1, arrival_hz=9.99, fifo_frames=1)
    report = assess(design, checklist)
    assert not report["scheduling"]["wire_budget_passed"]
    assert "FIFO_DEADLINE" in {i["code"] for i in report["scheduling"]["issues"]}


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_clock_fails_closed(inputs, value):
    design, checklist = inputs
    design["buses"][0]["jobs"][0]["clock_hz"] = value
    with pytest.raises(ValueError):
        assess(design, checklist)


def test_engineering_current_and_efficiency_are_never_maximum_power_proof(inputs):
    report = assess(*inputs)
    assert report["power"]["status"] == "unknown"
    assert not report["power"]["passed"]
    assert report["power"]["reserve_3v3_a"] == pytest.approx(0.572)
    assert report["power"]["estimated_5v_input_a"] == pytest.approx(0.6319)
    assert "WIZ550io" in report["power"]["unknown_current_parts"]


def test_source_bound_maxima_still_need_thermal_evidence(inputs):
    design, checklist = inputs
    for load in design["power"]["loads"]:
        load["max_current_a"] = load["reserve_current_a"]
    design["power"]["minimum_efficiency"] = 0.8
    # Caller-supplied numbers are estimates until a full sourced electrical review.
    report = assess(design, checklist)
    assert not report["power"]["passed"]
    assert report["power"]["thermal_status"] == "unknown"


def test_extra_fields_and_nonfinite_power_are_rejected(inputs):
    design, checklist = inputs
    design["power"]["loads"][0]["max_current_a"] = float("nan")
    with pytest.raises(ValueError):
        assess(design, checklist)
    design = deepcopy(inputs[0])
    design["layout_passed"] = True
    with pytest.raises(ValueError):
        assess(design, checklist)
