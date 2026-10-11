"""Bounded SI-unit power calculations; absent source inputs remain unknown."""
import math


def power_budget(loads, regulator):
    assumptions = ["DC steady-state loads", "linear regulator; no switching-efficiency model", "thermal capacity is caller supplied"]
    values = [load[key] for load in loads for key in ("voltage_v", "current_a")]
    values += [regulator[key] for key in ("input_v", "output_v", "max_current_a", "max_dissipation_w")]
    for value in values:
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError("electrical inputs must be finite nonnegative SI values")
    if any(value is None for value in values) or not regulator["confirmed"] or any(not load["confirmed"] for load in loads):
        return {"status": "unknown", "passed": False, "output_power_w": None, "ldo_dissipation_w": None, "assumptions": assumptions}
    if regulator["input_v"] < regulator["output_v"] or any(load["voltage_v"] != regulator["output_v"] for load in loads):
        raise ValueError("load/output/input voltage domains differ")
    current = sum(load["current_a"] for load in loads)
    power = sum(load["voltage_v"] * load["current_a"] for load in loads)
    dissipation = (regulator["input_v"] - regulator["output_v"]) * current
    return {"status": "calculated", "passed": current <= regulator["max_current_a"] and dissipation <= regulator["max_dissipation_w"],
        "output_power_w": power, "ldo_dissipation_w": dissipation, "current_a": current,
        "formula": "sum(V*I); (Vin-Vout)*sum(I)", "units": "W, A, V", "assumptions": assumptions}
