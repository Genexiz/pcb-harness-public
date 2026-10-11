"""Ignoring strict JSON, offline schemas, or path boundaries breaks these tests."""
from pathlib import Path
import json
import pytest


def test_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path):
    from pcb_harness.circuit.bundle import load_bundle
    for text in ('{"schema_version":1,"schema_version":2}', '{"schema_version":NaN}',
                 '{"schema_version":1,"value":1e999}'):
        (tmp_path / "requirements.json").write_text(text)
        with pytest.raises(ValueError):
            load_bundle(tmp_path)


@pytest.mark.parametrize("path", ["../outside.json", "/tmp/outside.json"])
def test_local_reference_cannot_escape_bundle(tmp_path, path):
    from pcb_harness.circuit.bundle import resolve_local
    with pytest.raises(ValueError):
        resolve_local(tmp_path, path)


def test_symlink_component_is_rejected(tmp_path):
    from pcb_harness.circuit.bundle import resolve_local
    (tmp_path / "outside").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError):
        resolve_local(tmp_path, "link/data.json")


def test_packaged_schemas_are_valid_and_strict():
    from importlib.resources import files
    from jsonschema import Draft202012Validator
    from pcb_harness.circuit.bundle import KINDS, validate_document
    for kind in KINDS:
        schema = json.loads(files("pcb_harness.circuit").joinpath(f"schemas/{kind}.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        with pytest.raises(ValueError):
            validate_document(kind, {"schema_version": 1, "unknown": True})


@pytest.mark.parametrize("value", [0, 2, True, "1"])
def test_unsupported_schema_version_fails(value):
    from pcb_harness.circuit.bundle import validate_document
    with pytest.raises(ValueError):
        validate_document("requirements", {"schema_version": value})


def test_schema_cannot_resolve_remote_reference(monkeypatch):
    from pcb_harness.circuit import bundle
    monkeypatch.setattr(bundle, "schema_for", lambda kind: {"$ref": "https://example.org/schema"})
    with pytest.raises(ValueError):
        bundle.validate_document("requirements", {})


@pytest.mark.parametrize("change", ["bad_count", "bad_units", "unknown_property"])
def test_invalid_interface_contract_rejected(change):
    from pcb_harness.circuit.bundle import validate_document
    interface = {"id": "uart", "kind": "UART", "count": 1, "role": "controller",
        "rate": {"value": 115200, "units": "baud"}}
    data = {"schema_version": 1, "id": "test", "functional": [], "power_inputs": [],
        "board": {"width_mm": 60, "height_mm": 20, "layers": 2, "thickness_mm": 1.6},
        "interfaces": [interface], "concurrent_groups": [],
        "environment": {"temperature_range_c": [0, 40]}, "assembly": "none"}
    if change == "bad_count":
        interface["count"] = 0
    elif change == "bad_units":
        interface["rate"]["units"] = "mm"
    else:
        interface["hidden"] = True
    with pytest.raises(ValueError):
        validate_document("requirements", data)
