"""Strict, local-only versioned circuit input bundles."""
from importlib.resources import files
from pathlib import Path
import hashlib
import json
import math

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

KINDS = ("requirements", "documents", "parts", "facts", "circuit", "constraints", "checklist", "fabrication")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"nonfinite JSON value: {value}")


def finite_tree(data):
    if isinstance(data, float) and not math.isfinite(data):
        raise ValueError("nonfinite JSON number")
    if isinstance(data, dict):
        for value in data.values():
            finite_tree(value)
    if isinstance(data, list):
        for value in data:
            finite_tree(value)


def read_json(path):
    data = json.loads(Path(path).read_text(), object_pairs_hook=unique_object,
        parse_constant=reject_constant)
    finite_tree(data)
    return data


def schema_for(kind):
    if kind not in KINDS:
        raise ValueError(f"unsupported schema kind: {kind}")
    return json.loads(files("pcb_harness.circuit").joinpath(f"schemas/{kind}.schema.json").read_text())


def validate_document(kind, data):
    finite_tree(data)
    try:
        validator = Draft202012Validator(schema_for(kind), registry=Registry(), format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(data), key=lambda e: str(list(e.path)))
        if errors:
            raise ValueError(f"{kind}: {errors[0].message}")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"{kind}: offline schema validation failed: {error}") from error


def resolve_local(root, relative):
    root = Path(root).absolute()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("local artifact path escaped bundle")
    target = root / relative
    for candidate in (root, *target.parents, target):
        if candidate.is_symlink():
            raise ValueError("symlinked artifact path is not allowed")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("local artifact path escaped bundle")
    return target


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def referenced_paths(bundle):
    for document in bundle["documents"]["documents"]:
        yield document["path"]
    for part in bundle["parts"]["parts"]:
        yield part["symbol"]["path"]
        yield part["footprint"]["path"]


def load_bundle(root):
    bundle = {}
    for kind in KINDS:
        data = read_json(resolve_local(root, f"{kind}.json"))
        validate_document(kind, data)
        bundle[kind] = data
        for key, entries in data.items():
            if isinstance(entries, list) and entries and all(isinstance(e, dict) and "id" in e for e in entries):
                ids = [entry["id"] for entry in entries]
                if len(ids) != len(set(ids)):
                    raise ValueError(f"duplicate IDs in {kind}.{key}")
    refs = [instance["ref"] for instance in bundle["circuit"]["instances"]]
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate instance refs")
    for relative in referenced_paths(bundle):
        if not resolve_local(root, relative).is_file():
            raise ValueError(f"missing referenced artifact: {relative}")
    return bundle


def bundle_hashes(root):
    bundle = load_bundle(root)
    paths = [f"{kind}.json" for kind in KINDS] + list(referenced_paths(bundle))
    return {relative: sha256(resolve_local(root, relative)) for relative in sorted(set(paths))}
