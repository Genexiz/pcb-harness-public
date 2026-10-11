"""Explicit synthetic fault inputs; no repair, placement, or routing policy."""
from copy import deepcopy

CIRCUIT_CODES = {"wrong_pinout":"PINOUT_MISMATCH", "wrong_footprint":"FOOTPRINT_MISMATCH",
    "missing_interface":"INTERFACE_MISSING", "voltage_mismatch":"VOLTAGE_MISMATCH",
    "ignored_errata":"ERRATA_UNRESOLVED", "duplicate_ref":"DUPLICATE_REF",
    "no_connect_mismatch":"NO_CONNECT_MISMATCH", "native_usb_can_concurrent":"PERIPHERAL_CONFLICT"}


def circuit_negative(original, original_checklist, variant):
    bundle, checklist = deepcopy(original), deepcopy(original_checklist)
    circuit, part = bundle["circuit"], bundle["parts"]["parts"][0]
    if variant == "wrong_pinout":
        circuit["nets"][0]["endpoints"][0]["pin_id"]="p2"
        circuit["nets"][1]["endpoints"][0]["pin_id"]="p1"
    elif variant == "wrong_footprint":
        part["package"]="Different-package"
    elif variant == "missing_interface":
        expected={"id":"uart","kind":"UART","count":1,"role":"controller","rate":{"value":115200,"units":"baud"}}
        bundle["requirements"]["interfaces"]=[expected]
        checklist["interfaces"]=[deepcopy(expected)]
    elif variant == "voltage_mismatch":
        fact=deepcopy(bundle["facts"]["facts"][0])
        fact.update(id="operating",kind="operating",value=3.3,units="V",range=[0,3.6])
        bundle["facts"]["facts"].append(fact)
        part["pins"][0].update(operating_range_v=[0,3.6],operating_fact_id="operating")
        circuit["nets"][0]["voltage_range_v"]=[4.8,5.2]
    elif variant == "ignored_errata":
        fact=deepcopy(bundle["facts"]["facts"][0])
        fact.update(id="errata-x",kind="errata")
        bundle["facts"]["facts"].append(fact)
        part["errata_fact_ids"]=["errata-x"]
        checklist["required_errata_ids"]=["errata-x"]
    elif variant == "duplicate_ref":
        circuit["instances"][1]["ref"]="R1"
    elif variant == "no_connect_mismatch":
        circuit["no_connect"]=[{"instance_id":"r1","pin_id":"p1","reason":"intentional","fact_id":"fixture"}]
    elif variant == "native_usb_can_concurrent":
        part["mpn"]="STM32F103C8T6"
        for instance in checklist["expected_instances"]:
            instance["mpn"]="STM32F103C8T6"
        interfaces=[{"id":name.lower(),"kind":name,"count":1,"role":"device","rate":{"value":100,"units":"bit/s"}} for name in ("USB","CAN")]
        bundle["requirements"].update(interfaces=interfaces,concurrent_groups=[["usb","can"]])
        checklist.update(interfaces=deepcopy(interfaces),concurrent_groups=[["usb","can"]])
        circuit["interfaces"]=[{"id":"usb","kind":"USB","instance_id":"r1","peripheral":"USB","pin_ids":["p1"]},
            {"id":"can","kind":"CAN","instance_id":"r1","peripheral":"CAN","pin_ids":["p2"]}]
    else:
        raise ValueError(variant)
    return bundle,checklist


FABRICATION_RULES={"width":"track_width","clearance":"clearance","drill":"via_drill",
    "diameter":"via_diameter","annular":"annular_ring","hole_clearance":"inner_drill_clearance",
    "hole_spacing":"hole_to_hole","edge":"copper_edge"}


def bad_geometry(text,variant):
    extra=""
    if variant=="width":
        text=text.replace("(width 0.4)","(width 0.1)",1)
    elif variant=="clearance":
        extra='(segment (start 21 20) (end 19.5 18) (width 0.4) (layer "F.Cu") (net 2))'
    elif variant=="drill":
        text=text.replace("(drill 0.3)","(drill 0.2)",1)
    elif variant=="diameter":
        text=text.replace("(size 0.6)","(size 0.5)",1)
    elif variant=="annular":
        text=text.replace("(drill 0.3)","(drill 0.4)",1)
    elif variant=="hole_clearance":
        text=text.replace('(2 "B.Cu" signal)','(4 "In1.Cu" signal) (6 "In2.Cu" signal) (2 "B.Cu" signal)')
        extra='(segment (start 21.5 24) (end 21.5 26) (width 0.2) (layer "In1.Cu") (net 1))'
    elif variant=="hole_spacing":
        extra='(via (at 21.5 25) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 2))'
    elif variant=="edge":
        extra='(segment (start 10.3 12) (end 10.3 16) (width 0.4) (layer "F.Cu") (net 1))'
    elif variant!="positive":
        raise ValueError(variant)
    return text.rstrip()[:-1]+extra+")\n"
