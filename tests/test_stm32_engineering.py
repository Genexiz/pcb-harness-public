"""Engineering arithmetic must catch omitted loads and optimistic device settings."""
from copy import deepcopy
from pathlib import Path
import pytest

from pcb_harness.circuit.bundle import read_json

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks/stm32-communications"
DIGEST = "a" * 64


def evidence():
    design = read_json(BENCHMARK / "design.json")
    source_lock = {"schema_version": 1, "documents": [
        {"id": "doc", "path": "doc.pdf", "status": "retrieved", "sha256": DIGEST}]}
    sources = {"hashes": {"doc.pdf": DIGEST}}
    def fact(fid, part, metric, unit, minimum, maximum, coverage="operating-range"):
        return dict(id=fid, part=part, metric=metric, unit=unit, minimum=minimum,
                    supply_domain=("VIO" if fid.startswith("can-vio-") else "VDD")
                    if metric in ("supply", "current") else None,
                    maximum=maximum, coverage=coverage, source_id="doc", source_sha256=DIGEST,
                    locator="test-only table", conditions="synthetic test conditions")
    facts = [fact("clock", "MCP2518FD-E/SL", "clock", "Hz", 40000000, 40000000),
             fact("length", "WIZ550io v1.2", "length", "mm", 55, 55),
             fact("width", "WIZ550io v1.2", "width", "mm", 26, 26),
             fact("height", "WIZ550io v1.2", "height", "mm", 24.5, 24.5)]
    loads = []
    for lid, part, qty, rail, current in [
        ("mcu", "STM32F103C8T6", 1, 3.3, 0.1),
        ("ethernet", "WIZ550io v1.2", 1, 3.3, 0.25),
        ("can-controllers", "MCP2518FD-E/SL", 2, 3.3, 0.03),
        ("can-vdd", "MCP2562FD-E/SN", 2, 5, 0.08),
        ("can-vio", "MCP2562FD-E/SN", 2, 3.3, 0.001),
        ("rs232", "MAX3232IDR", 1, 3.3, 0.03),
        ("rs485", "THVD1450DR", 1, 3.3, 0.08),
        ("support", "LEDs/pullups/headers", 1, 3.3, 0.05),
    ]:
        facts += [fact(lid+"-supply", part, "supply", "V", rail*0.9, rail*1.1),
                  fact(lid+"-current", part, "current", "A", None, current, "full-workload")]
        loads.append(dict(id=lid, part=part, quantity=qty, rail_v=rail,
                          supply_domain="VIO" if lid == "can-vio" else "VDD",
                          reserve_per_device_a=current, supply_fact=lid+"-supply", current_fact=lid+"-current"))
    nominal = dict(brp=1, tseg1=63, tseg2=16, sjw=16, target_bps=500000)
    data = dict(brp=1, tseg1=15, tseg2=4, sjw=4, target_bps=2000000)
    controllers = [dict(interface=interface, part="MCP2518FD-E/SL", sysclk_hz=40000000,
                        clock_fact="clock", rx_slots=8, tx_slots=8, tef_slots=8,
                        payload_bytes=payload, rx_timestamp=True, tef_timestamp=True,
                        nominal=deepcopy(nominal), data=deepcopy(data) if payload == 64 else None)
                   for interface, payload in (("can_classical", 8), ("can_fd", 64))]
    dossier = dict(schema_version=1, design_id=design["id"], facts=facts,
                   controllers=controllers, power=dict(rails=[dict(voltage_v=3.3, minimum_v=3.135, maximum_v=3.465),
                                                            dict(voltage_v=5, minimum_v=4.75, maximum_v=5.25)], loads=loads),
                   mechanical=dict(module_part="WIZ550io v1.2", length_facts=["length"], width_fact="width",
                                   height_fact="height", screening_length_mm=56, screening_width_mm=27,
                                   screening_height_mm=25.5, connectors=[]),
                   errata=dict(source_id="doc", source_sha256=DIGEST, locator="ES096 Rev15 synthetic fixture",
                               device_marking=None, rev_id=None, items=[]))
    from pcb_harness.orchestration.engineering_evidence import ERRATA_ITEMS
    dossier["errata"]["items"] = [dict(id=e, policy="Planned firmware review; not implemented") for e in ERRATA_ITEMS]
    return design, dossier, sources, source_lock


def assess(inputs):
    from pcb_harness.orchestration.engineering_evidence import assess_engineering
    return assess_engineering(*inputs)


def codes(result, category):
    return {i["code"] for i in result[category]["issues"]}


def test_controller_ram_counts_rx_timestamp_tx_and_tef_independently():
    result = assess(evidence())
    classical, fd = result["controllers"]["devices"]
    assert classical["ram_used_bytes"] == 384
    assert fd["ram_used_bytes"] == 1280
    assert fd["ram_free_bytes"] == 768
    assert fd["nominal"]["bitrate_bps"] == 500000
    assert fd["data"]["bitrate_bps"] == 2000000
    assert fd["data"]["sample_point"] == 0.8
    assert result["controllers"]["arithmetic_passed"]
    assert result["controllers"]["firmware_status"] == "unknown"


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d["controllers"].pop(), "CONTROLLER_COVERAGE"),
    (lambda d: d["controllers"][1].update(rx_slots=32, tx_slots=32), "CONTROLLER_RAM"),
    (lambda d: d["controllers"][0].update(rx_slots=7), "RX_FIFO_COVERAGE"),
    (lambda d: d["controllers"][1]["nominal"].update(sjw=17), "BIT_TIMING"),
    (lambda d: d["controllers"][1]["data"].update(tseg1=14), "BIT_RATE"),
    (lambda d: d["controllers"][1]["data"].update(target_bps=1000000), "TARGET_RATE"),
    (lambda d: d["controllers"][1].update(sysclk_hz=20000000), "CLOCK_RANGE"),
    (lambda d: d["controllers"][1].update(payload_bytes=8), "CONTROLLER_MODE"),
])
def test_impossible_or_incomplete_controller_configuration_fails(mutate, code):
    inputs = evidence()
    mutate(inputs[1])
    result = assess(inputs)
    assert not result["controllers"]["arithmetic_passed"]
    assert code in codes(result, "controllers")


def test_can_vio_load_is_included_on_3v3_and_kept_separate_from_vdd():
    result = assess(evidence())
    assert result["power"]["reserve_3v3_a"] == pytest.approx(0.572)
    assert result["power"]["reserve_5v_a"] == pytest.approx(0.16)
    assert result["power"]["status"] == "unknown"
    assert not result["power"]["passed"]


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d["power"]["loads"].pop(4), "LOAD_COVERAGE"),
    (lambda d: d["power"]["rails"].pop(), "RAIL_COVERAGE"),
    (lambda d: d["power"]["loads"][2].update(quantity=1), "LOAD_IDENTITY"),
    (lambda d: d["power"]["loads"][4].update(rail_v=5), "LOAD_IDENTITY"),
    (lambda d: d["power"]["rails"][0].update(maximum_v=4), "SUPPLY_RANGE"),
    (lambda d: d["power"]["loads"][1].update(current_fact="mcu-current"), "FACT_APPLICABILITY"),
    (lambda d: d["power"]["loads"][1].update(reserve_per_device_a=0.01), "CURRENT_RESERVE"),
])
def test_power_omissions_and_out_of_range_rails_are_visible(mutate, code):
    inputs = evidence()
    mutate(inputs[1])
    assert code in codes(assess(inputs), "power")


@pytest.mark.parametrize("coverage", ["typical", "no-load", "specific-condition", "unavailable"])
def test_conditional_current_never_becomes_full_load_maximum(coverage):
    inputs = evidence()
    next(f for f in inputs[1]["facts"] if f["id"] == "ethernet-current")["coverage"] = coverage
    result = assess(inputs)
    assert "ethernet" in result["power"]["unbounded_loads"]


def test_source_hash_drift_stays_unresolved_even_with_plausible_numbers():
    inputs = evidence()
    inputs[1]["facts"][0]["source_sha256"] = "b" * 64
    result = assess(inputs)
    assert "SOURCE_BINDING" in {i["code"] for i in result["source_issues"]}
    assert not result["controllers"]["arithmetic_passed"]


def test_duplicate_source_or_fact_ids_are_rejected():
    inputs = evidence()
    inputs[3]["documents"].append(deepcopy(inputs[3]["documents"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        assess(inputs)
    inputs = evidence()
    inputs[1]["facts"].append(deepcopy(inputs[1]["facts"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        assess(inputs)


def test_conflicting_lengths_and_missing_connectors_keep_mechanics_unresolved():
    inputs = evidence()
    extra = deepcopy(inputs[1]["facts"][1])
    extra.update(id="other-length", minimum=54, maximum=54)
    inputs[1]["facts"].append(extra)
    inputs[1]["mechanical"]["length_facts"].append("other-length")
    result = assess(inputs)
    assert {"MECHANICAL_CONFLICT", "CONNECTOR_COVERAGE"} <= codes(result, "mechanical")
    assert not result["mechanical"]["passed"]


def test_a_body_smaller_than_documented_extent_fails_screening():
    inputs = evidence()
    inputs[1]["mechanical"]["screening_length_mm"] = 54
    assert "MODULE_ENVELOPE" in codes(assess(inputs), "mechanical")


def test_errata_list_cannot_omit_driver_workarounds_or_prove_implementation():
    inputs = evidence()
    inputs[1]["errata"]["items"].pop()
    result = assess(inputs)
    assert "ERRATA_COVERAGE" in codes(result, "errata")
    assert result["errata"]["status"] == "unknown"
    assert not result["errata"]["passed"]
    assert result["errata"]["silicon_status"] == "unknown"


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(design_id="different-target"),
    lambda d: d.update(layout_passed=True),
    lambda d: d["controllers"][0].update(rx_slots=True),
    lambda d: d["power"]["rails"][0].update(maximum_v=float("nan")),
    lambda d: d["controllers"][0].update(payload_bytes=7),
])
def test_invalid_dossier_is_rejected(mutate):
    inputs = evidence()
    mutate(inputs[1])
    with pytest.raises(ValueError):
        assess(inputs)


@pytest.mark.parametrize("load_id,field,other_fact", [
    ("can-vdd", "current_fact", "can-vio-current"),
    ("can-vio", "current_fact", "can-vdd-current"),
    ("can-vdd", "supply_fact", "can-vio-supply"),
    ("can-vio", "supply_fact", "can-vdd-supply"),
])
def test_power_fact_must_describe_the_load_supply_domain(load_id, field, other_fact):
    inputs = evidence()
    load = next(x for x in inputs[1]["power"]["loads"] if x["id"] == load_id)
    load[field] = other_fact
    if load_id == "can-vdd" and field == "current_fact":
        load["reserve_per_device_a"] = 0.001
    result = assess(inputs)
    assert "FACT_APPLICABILITY" in codes(result, "power")
    if field == "current_fact":
        observed = next(x for x in result["power"]["loads"] if x["id"] == load_id)
        assert not observed["documented_full_load_bound"]


@pytest.mark.parametrize("change", ["missing", "different", "extra", "different-both"])
def test_power_screening_reconciles_regulator_and_entire_inventory(change):
    inputs = evidence()
    design = inputs[0]
    regulator = next(x for x in design["parts"] if x["ref"] == "U8")
    if change == "missing":
        design["parts"].remove(regulator)
    elif change == "extra":
        extra = deepcopy(design["parts"][1])
        extra["ref"] = "U9"
        design["parts"].append(extra)
    else:
        regulator["mpn"] = "unreviewed-regulator"
        if change == "different-both":
            design["power"]["regulator"] = regulator["mpn"]
    assert "PART_COVERAGE" in codes(assess(inputs), "power")
