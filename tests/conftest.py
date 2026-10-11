from pathlib import Path
import shutil
from copy import deepcopy
import pytest
from pcb_harness.circuit.bundle import load_bundle

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def valid_bundle(tmp_path):
    root = tmp_path / "input"
    shutil.copytree(ROOT / "fixtures/circuit/tiny", root)
    return load_bundle(root), root


@pytest.fixture
def circuit_case(valid_bundle):
    original, root = valid_bundle
    def make(variant):
        bundle = deepcopy(original)
        checklist = deepcopy(bundle["checklist"])
        circuit = bundle["circuit"]
        part = bundle["parts"]["parts"][0]
        if variant == "wrong_pinout":
            circuit["nets"][0]["endpoints"][0]["pin_id"] = "p2"
            circuit["nets"][1]["endpoints"][0]["pin_id"] = "p1"
        elif variant == "wrong_footprint":
            part["package"] = "Different-package"
        elif variant == "missing_interface":
            expected = {"id": "uart", "kind": "UART", "count": 1, "role": "controller",
                "rate": {"value": 115200, "units": "baud"}}
            bundle["requirements"]["interfaces"] = [expected]
            checklist["interfaces"] = [deepcopy(expected)]
        elif variant == "voltage_mismatch":
            fact = deepcopy(bundle["facts"]["facts"][0])
            fact.update(id="operating", kind="operating", value=3.3, units="V", range=[0, 3.6])
            bundle["facts"]["facts"].append(fact)
            part["pins"][0].update(operating_range_v=[0, 3.6], operating_fact_id="operating")
            circuit["nets"][0]["voltage_range_v"] = [4.8, 5.2]
        elif variant == "ignored_errata":
            fact = deepcopy(bundle["facts"]["facts"][0])
            fact.update(id="errata-x", kind="errata")
            bundle["facts"]["facts"].append(fact)
            part["errata_fact_ids"] = ["errata-x"]
            checklist["required_errata_ids"] = ["errata-x"]
        elif variant == "duplicate_ref":
            circuit["instances"][1]["ref"] = "R1"
        elif variant == "no_connect_mismatch":
            circuit["no_connect"] = [{"instance_id": "r1", "pin_id": "p1", "reason": "intentional", "fact_id": "fixture"}]
        elif variant in ("native_usb_can_concurrent", "external_can"):
            part["mpn"] = "STM32F103C8T6"
            for expected in checklist["expected_instances"]:
                expected["mpn"] = "STM32F103C8T6"
            interfaces = [{"id": name.lower(), "kind": name, "count": 1, "role": "device",
                "rate": {"value": 100, "units": "bit/s"}} for name in ("USB", "CAN")]
            bundle["requirements"].update(interfaces=interfaces, concurrent_groups=[["usb", "can"]])
            checklist.update(interfaces=deepcopy(interfaces), concurrent_groups=[["usb", "can"]])
            circuit["interfaces"] = [{"id": "usb", "kind": "USB", "instance_id": "r1", "peripheral": "USB", "pin_ids": ["p1"]},
                {"id": "can", "kind": "CAN", "instance_id": "r1", "peripheral": "CAN" if variant == "native_usb_can_concurrent" else "external_CAN", "pin_ids": ["p2"]}]
        elif variant == "missing_constraint":
            bundle["constraints"]["constraints"] = []
        elif variant != "positive":
            raise ValueError(variant)
        return bundle, root, checklist
    return make


@pytest.fixture
def profile_case(valid_bundle):
    bundle, root = valid_bundle
    def make(variant="positive"):
        profile = deepcopy(bundle["fabrication"])
        facts = deepcopy(bundle["facts"])
        constraints = deepcopy(bundle["constraints"])
        if variant == "routing_values_only":
            profile["categories"] = profile["categories"][:3]
        elif variant == "target_below_floor":
            profile["categories"][0].update(status="confirmed", manufacturer_floor=0.3, design_target=0.2)
        elif variant != "positive":
            raise ValueError(variant)
        return profile, facts, constraints
    return make
