"""Hash-bound evidence audit; human confirmation is never manufactured here."""
from .bundle import resolve_local, sha256, validate_document
from .assets import load_part_assets


def audit_provenance(bundle, root):
    issues, unknowns = [], []
    def issue(code, identifier, message):
        issues.append({"code": code, "id": identifier, "message": message})
    documents = {doc["id"]: doc for doc in bundle["documents"]["documents"]}
    facts = {fact["id"]: fact for fact in bundle["facts"]["facts"]}
    for kind in ("documents", "facts", "parts", "checklist"):
        try:
            validate_document(kind, bundle[kind])
        except ValueError as error:
            issue("INVALID_SCHEMA", kind, str(error))
    for doc in documents.values():
        try:
            if sha256(resolve_local(root, doc["path"])) != doc["sha256"]:
                issue("DOCUMENT_HASH_MISMATCH", doc["id"], "source bytes changed")
        except (ValueError, OSError) as error:
            issue("DOCUMENT_UNAVAILABLE", doc["id"], str(error))
    for fact in facts.values():
        doc = documents.get(fact["document_id"])
        if not doc or fact["document_sha256"] != doc["sha256"]:
            issue("FACT_SOURCE_MISMATCH", fact["id"], "fact has no exact source revision")
        if fact["status"] == "confirmed":
            confirmation = fact["confirmation"]
            if not confirmation or confirmation["document_sha256"] != fact["document_sha256"]:
                issue("STALE_CONFIRMATION", fact["id"], "confirmation does not bind current document")
        elif fact["critical"]:
            unknowns.append({"code": "CRITICAL_FACT_UNCONFIRMED", "id": fact["id"]})
    checklist = bundle["checklist"]
    doc = documents.get(checklist["document_id"])
    if not doc or checklist["document_sha256"] != doc["sha256"]:
        issue("CHECKLIST_SOURCE_MISMATCH", checklist["id"], "checklist source revision missing")
    for part in bundle["parts"]["parts"]:
        try:
            load_part_assets(part, root)
        except (ValueError, OSError) as error:
            issue("ASSET_MISMATCH", part["id"], str(error))
        for identifier in part["fact_ids"] + part["required_fact_ids"] + part["errata_fact_ids"]:
            if identifier not in facts:
                issue("FACT_MISSING", identifier, "part references absent fact")
        for pin in part["pins"]:
            for field, kind in (("operating_fact_id", "operating"), ("absolute_maximum_fact_id", "absolute_maximum")):
                identifier = pin[field]
                if identifier and (identifier not in facts or facts[identifier]["kind"] != kind):
                    issue("FACT_KIND_MISMATCH", identifier, f"{field} has wrong fact kind")
            if pin["operating_range_v"] is not None and pin["operating_fact_id"] is None:
                issue("FACT_MISSING", pin["id"], "operating range has no source fact")
            if pin["operating_range_v"] is not None and pin["operating_fact_id"] in facts:
                operating_fact = facts[pin["operating_fact_id"]]
                bounds = operating_fact.get("range")
                declared = pin["operating_range_v"]
                if bounds is None:
                    unknowns.append({"code": "OPERATING_RANGE_UNKNOWN", "id": pin["id"]})
                elif (not isinstance(bounds,list) or len(bounds) != 2
                        or not all(type(value) in (int,float) for value in bounds)
                        or operating_fact["units"] != "V"
                        or not bounds[0] <= declared[0] <= declared[1] <= bounds[1]):
                    issue("FACT_RANGE_MISMATCH", pin["id"], "operating range exceeds explicit sourced voltage bounds")
    nonproduction = any(doc["source"] == "synthetic" or doc["redistribution"] != "allowed"
        for doc in documents.values())
    return {"passed": not issues, "release_eligible": not issues and not unknowns and not nonproduction,
        "issues": issues, "unknowns": unknowns, "synthetic": any(doc["source"] == "synthetic" for doc in documents.values())}
