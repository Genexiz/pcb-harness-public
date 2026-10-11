"""Bounded F103C8 resource and wire-time estimates, not functional acceptance."""
import math
from jsonschema import Draft202012Validator

from pcb_harness.circuit.bundle import finite_tree


def obj(properties):
    return {"type": "object", "required": list(properties), "properties": properties,
            "additionalProperties": False}


def array(items):
    return {"type": "array", "items": items}


TEXT = {"type": "string", "minLength": 1}
NUMBER = {"type": "number", "minimum": 0}
POSITIVE = {"type": "number", "exclusiveMinimum": 0}
INTEGER = {"type": "integer", "minimum": 0}
NULL_NUMBER = {"type": ["number", "null"], "minimum": 0}
BOOL = {"type": "boolean"}
INTERFACE = obj({"signals": array(TEXT), "peripheral": TEXT, "io": TEXT})
REQUIRED_INTERFACES = {"usb", "uart", "rs232", "rs485", "i2c", "spi",
                       "can_classical", "can_fd", "ethernet"}
SCHEMA = obj({
    "schema_version": {"const": 1}, "id": TEXT, "mcu": TEXT, "package": TEXT,
    "pins": array(obj({"signal": TEXT, "pin": TEXT, "number": INTEGER, "function": TEXT})),
    "interfaces": {"type": "object", "additionalProperties": INTERFACE},
    "dma": array(obj({"request": TEXT, "channel": INTEGER})),
    "exti": array(obj({"signal": TEXT, "line": INTEGER})),
    "buses": array(obj({"id": TEXT, "clock_hz": POSITIVE, "scheduler_period_s": POSITIVE,
        "utilization_limit": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
        "jobs": array(obj({"interface": TEXT, "bytes": INTEGER, "clock_hz": POSITIVE,
            "period_s": POSITIVE, "overhead_s": NUMBER, "arrival_hz": NUMBER, "fifo_frames": INTEGER}))})),
    "power": obj({"input_v": POSITIVE, "output_v": POSITIVE, "regulator": TEXT,
        "rated_current_a": POSITIVE, "minimum_efficiency": {"type": ["number", "null"], "exclusiveMinimum": 0, "maximum": 1},
        "max_loss_w": NULL_NUMBER, "theta_ja_c_per_w": NULL_NUMBER,
        "ambient_c": {"type": "number"}, "max_junction_c": {"type": "number"},
        "loads": array(obj({"part": TEXT, "voltage_v": POSITIVE, "reserve_current_a": NUMBER,
                            "max_current_a": NULL_NUMBER, "source_id": {"type": ["string", "null"]}})),
        "engineering_efficiency_estimate": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
        "usb_only_supported": BOOL}),
    "parts": array(obj({"ref": TEXT, "mpn": TEXT, "package": TEXT, "source_id": TEXT,
                        "status": {"const": "candidate"}})),
    "mechanical": obj({"width_mm": POSITIVE, "height_mm": POSITIVE, "mounting_holes": INTEGER,
                       "module_envelope_verified": BOOL, "connector_envelopes_verified": BOOL}),
    "assumptions": array(TEXT),
})


def validate_design(design):
    finite_tree(design)
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(design), key=lambda e: str(list(e.path)))
    if errors:
        raise ValueError(f"STM32 design {list(errors[0].path)}: {errors[0].message}")


def issue(issues, code, detail):
    issues.append({"code": code, "detail": detail})


def resources(design, checklist):
    issues = []
    if (design["mcu"], design["package"]) != ("STM32F103C8T6", "LQFP48"):
        issue(issues, "TARGET_CHANGED", "Only STM32F103C8T6 LQFP48 is calibrated")
    if checklist["schema_version"] != 1 or (checklist["mcu"], checklist["package"]) != ("STM32F103C8T6", "LQFP48"):
        raise ValueError("unsupported resource checklist")
    pins, signals = set(), set()
    for entry in design["pins"]:
        signal, pin = entry["signal"], entry["pin"]
        if pin in pins or signal in signals:
            issue(issues, "PIN_CONFLICT", f"duplicate physical pin or logical signal: {signal}/{pin}")
        pins.add(pin)
        signals.add(signal)
        if checklist["physical_pins"].get(pin) != entry["number"]:
            issue(issues, "PACKAGE_PIN", f"{signal}: wrong physical package pin")
        if checklist["allowed_signals"].get(signal) != {"pin": pin, "function": entry["function"]}:
            issue(issues, "PIN_FUNCTION", f"{signal}: allocation differs from default AF/reserved checklist")
    for signal in set(checklist["allowed_signals"]) - signals:
        issue(issues, "MISSING_SIGNAL", signal)
    if set(design["interfaces"]) != REQUIRED_INTERFACES or set(checklist["interfaces"]) != REQUIRED_INTERFACES:
        issue(issues, "INTERFACE_SET", "all nine target interfaces required")
    for name, interface in design["interfaces"].items():
        if interface != checklist["interfaces"].get(name):
            issue(issues, "INTERFACE_ALLOCATION", name)
    channels, requests = set(), set()
    for entry in design["dma"]:
        request, channel = entry["request"], entry["channel"]
        if channel in channels or request in requests:
            issue(issues, "DMA_CONFLICT", request)
        channels.add(channel)
        requests.add(request)
        if checklist["dma_requests"].get(request) != channel:
            issue(issues, "DMA_MAPPING", request)
    required_dma = {f"USART{i}_{direction}" for i in (1, 2, 3) for direction in ("TX", "RX")}
    if not required_dma <= requests:
        issue(issues, "DMA_COVERAGE", "six UART TX/RX requests required by this firmware policy")
    lines, exti_signals = set(), set()
    for entry in design["exti"]:
        signal, line = entry["signal"], entry["line"]
        if line in lines or signal in exti_signals:
            issue(issues, "EXTI_CONFLICT", signal)
        lines.add(line)
        exti_signals.add(signal)
        if checklist["required_exti"].get(signal) != line:
            issue(issues, "EXTI_MAPPING", signal)
    if exti_signals != set(checklist["required_exti"]):
        issue(issues, "EXTI_COVERAGE", "CAN1/CAN2/Ethernet interrupt lines required")
    return {"passed": not issues, "issues": issues,
            "unused_gpio": sorted(pin for pin in checklist["physical_pins"] if pin.startswith("P") and pin not in pins),
            "scope": "static package/default-AF/DMA/EXTI allocation; no silicon execution"}


def scheduling(design, checklist):
    issues, results, seen = [], [], set()
    expected = {"SPI1": {"can_classical", "can_fd", "spi"}, "SPI2": {"ethernet"}}
    for bus in design["buses"]:
        bid = bus["id"]
        if bid in seen:
            issue(issues, "BUS_CLIENT_COVERAGE", f"duplicate bus {bid}")
        seen.add(bid)
        clients = [job["interface"] for job in bus["jobs"]]
        if set(clients) != expected.get(bid) or len(clients) != len(set(clients)):
            issue(issues, "BUS_CLIENT_COVERAGE", bid)
        if bid not in checklist["max_spi_hz"] or bus["clock_hz"] > checklist["max_spi_hz"].get(bid, 0):
            issue(issues, "SPI_CLOCK", bid)
        jobs = []
        for job in bus["jobs"]:
            if job["clock_hz"] > bus["clock_hz"] or (job["interface"] == "spi" and job["clock_hz"] > 1000000):
                issue(issues, "SPI_CLOCK", job["interface"])
            duration = 8 * job["bytes"] / job["clock_hz"] + job["overhead_s"]
            if not math.isfinite(duration):
                raise ValueError("wire-time arithmetic overflow")
            jobs.append({**job, "duration_s": duration})
        utilization = sum(job["duration_s"] / job["period_s"] for job in jobs)
        blocking = max((job["duration_s"] for job in jobs), default=0)
        service = sum(job["duration_s"] for job in jobs if job["interface"].startswith("can_"))
        if not math.isfinite(utilization) or utilization > bus["utilization_limit"]:
            issue(issues, "BUS_UTILIZATION", bid)
        for job in jobs:
            if job["interface"].startswith("can_"):
                if job["arrival_hz"] <= 0 or job["fifo_frames"] <= 0:
                    issue(issues, "FIFO_DEADLINE", job["interface"])
                    continue
                # One frame drained each period. Compute conservative initial backlog wait.
                deadline = job["fifo_frames"] / job["arrival_hz"]
                response = max(bus["scheduler_period_s"], job["period_s"]) + blocking + service
                job.update(fifo_deadline_s=deadline, wire_response_bound_s=response)
                if response >= deadline:
                    issue(issues, "FIFO_DEADLINE", job["interface"])
                if job["arrival_hz"] >= 1 / job["period_s"]:
                    issue(issues, "SERVICE_RATE", job["interface"])
        results.append({"id": bid, "utilization": utilization, "max_blocking_s": blocking, "jobs": jobs})
    if seen != set(expected):
        issue(issues, "BUS_CLIENT_COVERAGE", "both SPI buses required")
    return {"wire_budget_passed": not issues, "buses": results, "issues": issues,
            "functional_timing_status": "unknown",
            "formula": "duration=8*bytes/clock_hz+overhead_s; utilization=sum(duration/period); FIFO deadline=frames/arrival_hz",
            "limits": "chosen full-payload workload, supplied overhead, FIFO allocation and bounded blocking; CPU/driver WCET not measured"}


def power_estimate(power):
    if power["input_v"] != 5 or power["output_v"] != 3.3 or power["usb_only_supported"]:
        raise ValueError("only external 5V -> 3.3V benchmark power policy is supported")
    if any(load["voltage_v"] not in (3.3, 5) for load in power["loads"]):
        raise ValueError("unsupported load rail")
    reserve = sum(load["reserve_current_a"] for load in power["loads"] if load["voltage_v"] == 3.3)
    direct = sum(load["reserve_current_a"] for load in power["loads"] if load["voltage_v"] == 5)
    input_estimate = direct + 3.3 * reserve / (5 * power["engineering_efficiency_estimate"])
    if not math.isfinite(input_estimate):
        raise ValueError("power arithmetic overflow")
    return {"status": "unknown", "passed": False, "reserve_3v3_a": reserve,
            "direct_5v_reserve_a": direct, "estimated_5v_input_a": input_estimate,
            "reserve_current_within_regulator_rating": reserve <= power["rated_current_a"],
            "unknown_current_parts": [load["part"] for load in power["loads"] if load["max_current_a"] is None],
            "thermal_status": "unknown", "formula": "I_5V_est=I_5V_direct+3.3*I_3V3/(5*estimated_efficiency)",
            "limits": "engineering reserves only; no source-bound maximum-current/electrical review or validated thermal model"}


def assess_design(design, checklist):
    validate_design(design)
    return {"schema_version": 1, "design_id": design["id"], "human_confirmed": False,
            "resources": resources(design, checklist), "scheduling": scheduling(design, checklist),
            "power": power_estimate(design["power"]), "assumptions": design["assumptions"]}
