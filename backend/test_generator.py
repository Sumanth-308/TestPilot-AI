from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

try:
    from backend.test_executor import classify_execution_type, classify_link_destination
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from test_executor import classify_execution_type, classify_link_destination

REQUIRED_FIELDS = (
    "test_case_id",
    "scenario",
    "description",
    "preconditions",
    "steps",
    "test_data",
    "expected_result",
    "priority",
    "category",
    "execution_type",
    "status",
)

VALID_CATEGORIES = {
    "Positive",
    "Negative",
    "Boundary",
    "Input Validation",
    "Form Validation",
    "Navigation",
    "Button Interaction",
    "Functional",
}
VALID_PRIORITIES = {"High", "Medium", "Low"}
VALID_EXECUTION_TYPES = {"Manual", "Automated"}
STATUS_NOT_EXECUTED = "Not Executed"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return [value]
    return [value]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_scan_result(scan_result: Any) -> dict[str, Any]:
    if isinstance(scan_result, Mapping):
        return dict(scan_result)
    if scan_result is None:
        return {}
    return {"value": scan_result}


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _candidate_id(data: Mapping[str, Any]) -> str:
    digest = hashlib.sha1(_stable_json(data).encode("utf-8")).hexdigest()[:16]
    return f"TC-{digest}"


def _safe_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _field_label(field: Mapping[str, Any], fallback: str) -> str:
    for key in ("name", "id", "placeholder", "label"):
        value = _clean_text(field.get(key))
        if value:
            return value
    return fallback


def _collect_supported_metadata(scan_result: Mapping[str, Any]) -> dict[str, int]:
    counts = {
        "headings": 0,
        "buttons": 0,
        "links": 0,
        "inputs": 0,
        "forms": 0,
    }
    for key in counts:
        item = scan_result.get(key)
        if item is None:
            continue
        if isinstance(item, list):
            counts[key] = len(item)
        else:
            counts[key] = 1
    return counts


def _normalize_case_data(data: Any) -> Any:
    if isinstance(data, Mapping):
        return {str(key): _normalize_case_data(value) for key, value in sorted(data.items(), key=lambda item: str(item[0]))}
    if isinstance(data, list):
        return [_normalize_case_data(item) for item in data]
    if isinstance(data, tuple):
        return [_normalize_case_data(item) for item in data]
    return data


def _deduplicate_cases(cases: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            continue
        signature_data = {
            "scenario": _clean_text(case.get("scenario")),
            "category": _clean_text(case.get("category")),
            "test_data": _normalize_case_data(case.get("test_data")),
            "description": _clean_text(case.get("description")),
        }
        signature = _stable_json(signature_data)
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(dict(case))
    return unique


def _build_case(
    *,
    scenario: str,
    description: str,
    preconditions: list[str],
    steps: list[str],
    test_data: dict[str, Any],
    expected_result: str,
    priority: str,
    category: str,
    execution_type: str,
) -> dict[str, Any]:
    stable_data = {
        "scenario": scenario,
        "description": description,
        "preconditions": preconditions,
        "steps": steps,
        "test_data": test_data,
        "expected_result": expected_result,
        "priority": priority,
        "category": category,
        "execution_type": execution_type,
        "status": STATUS_NOT_EXECUTED,
    }
    return {
        "test_case_id": _candidate_id(stable_data),
        "scenario": scenario,
        "description": description,
        "preconditions": preconditions,
        "steps": steps,
        "test_data": test_data,
        "expected_result": expected_result,
        "priority": priority,
        "category": category,
        "execution_type": execution_type,
        "status": STATUS_NOT_EXECUTED,
    }


def _validate_case(case: Mapping[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not isinstance(case, Mapping):
        return False, ["Case is not a mapping."]

    missing = [field for field in REQUIRED_FIELDS if field not in case]
    if missing:
        issues.append(f"Missing required fields: {', '.join(missing)}")

    for field in ("scenario", "description", "expected_result", "priority", "category", "execution_type", "status"):
        value = case.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"{field} must be a non-empty string.")

    preconditions = case.get("preconditions")
    if not isinstance(preconditions, list) or not preconditions:
        issues.append("preconditions must be a non-empty list.")
    elif any(not isinstance(item, str) or not item.strip() for item in preconditions):
        issues.append("Each precondition must be a non-empty string.")

    steps = case.get("steps")
    if not isinstance(steps, list) or not steps:
        issues.append("steps must be a non-empty list.")
    elif any(not isinstance(item, str) or not item.strip() for item in steps):
        issues.append("Each step must be a non-empty string.")

    test_data = case.get("test_data")
    if not isinstance(test_data, dict):
        issues.append("test_data must be a dictionary.")

    priority = case.get("priority")
    if priority not in VALID_PRIORITIES:
        issues.append(f"Invalid priority: {priority!r}")

    category = case.get("category")
    if category not in VALID_CATEGORIES:
        issues.append(f"Invalid category: {category!r}")

    execution_type = case.get("execution_type")
    if execution_type not in VALID_EXECUTION_TYPES:
        issues.append(f"Invalid execution type: {execution_type!r}")

    status = case.get("status")
    if status != STATUS_NOT_EXECUTED:
        issues.append(f"Status must be '{STATUS_NOT_EXECUTED}'.")

    case_id = case.get("test_case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        issues.append("test_case_id must be a non-empty string.")

    return not issues, issues


def _generate_heading_cases(headings: Any) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for heading in _as_list(headings):
        text = _clean_text(heading)
        if not text:
            continue
        cases.append(
            _build_case(
                scenario=f"Verify heading '{text}' is present on the page.",
                description=f"Confirm the headed content '{text}' appears in the scanner metadata for the page.",
                preconditions=["Page is loaded."],
                steps=[
                    "Open the page under test.",
                    f"Locate the heading '{text}' in the rendered content.",
                    "Confirm the heading matches the scanned metadata.",
                ],
                test_data={"heading": text},
                expected_result="The heading is present in the page content as detected by the scanner metadata.",
                priority="Medium",
                category="Functional",
                execution_type="Manual",
            )
        )
    return cases


def _generate_button_cases(buttons: Any) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for button in _as_list(buttons):
        data = _safe_mapping(button)
        text = _clean_text(data.get("text") or data.get("label") or data.get("aria-label"))
        if not text:
            continue
        cases.append(
            _build_case(
                scenario=f"Verify the button '{text}' is present on the page.",
                description=f"Check that the button '{text}' is included in the page metadata without claiming an interaction result.",
                preconditions=["Page is loaded."],
                steps=[
                    "Open the page under test.",
                    f"Locate the button '{text}'.",
                    "Record its visible presence and available metadata.",
                ],
                test_data={
                    "text": text,
                    "type": _clean_text(data.get("type") or "button"),
                    "metadata": {str(key): value for key, value in data.items()},
                },
                expected_result="The button is visible and identifiable from the scanner metadata, but no interaction result is assumed.",
                priority="Medium",
                category="Button Interaction",
                execution_type="Manual",
            )
        )
    return cases


def _generate_link_cases(links: Any, final_url: str | None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for link in _as_list(links):
        data = _safe_mapping(link)
        text = _clean_text(data.get("text") or data.get("label") or data.get("href"))
        href = _clean_text(data.get("href"))
        if not text and not href:
            continue
        destination_kind = classify_link_destination(href, final_url)
        target = href or "same page"
        scenario = f"Inspect the link '{text or target}' and classify its destination as '{destination_kind}'."
        description = (
            "Use the actual href and the scanned page final_url as the origin reference to classify the destination "
            "without claiming navigation success or failure."
        )
        cases.append(
            _build_case(
                scenario=scenario,
                description=description,
                preconditions=["Page is loaded.", "Link metadata is available."],
                steps=[
                    "Open the page under test.",
                    f"Inspect the link '{text or target}' and its href '{href or 'not provided'}'.",
                    f"Classify the destination using the page origin '{final_url or 'unknown'}'.",
                    "Do not assert that navigation succeeded without runtime execution.",
                ],
                test_data={
                    "text": text,
                    "href": href,
                    "destination_type": destination_kind,
                    "final_url": final_url,
                },
                expected_result="The destination type is correctly identified from the actual scanner metadata and final_url origin context.",
                priority="Medium",
                category="Navigation",
                execution_type="Manual",
            )
        )
    return cases


def _parse_numeric_constraint(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric_value = float(value)
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            numeric_value = float(cleaned)
        except ValueError:
            return None
    else:
        return None

    if math.isnan(numeric_value) or math.isinf(numeric_value):
        return None
    return numeric_value


def _generate_input_cases(inputs: Any) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, element in enumerate(_as_list(inputs), start=1):
        field = _safe_mapping(element)
        if not field:
            continue
        input_type = _clean_text(field.get("type") or "text").lower()
        field_name = _field_label(field, f"input_{index}")
        required = bool(field.get("required"))
        constraints = {
            key: field.get(key)
            for key in ("min", "max", "minlength", "maxlength", "pattern")
            if field.get(key) is not None
        }
        base_data = {
            "name": field_name,
            "type": input_type,
            "required": required,
            "constraints": constraints,
            "id": field.get("id"),
            "placeholder": field.get("placeholder"),
        }

        if required:
            cases.append(
                _build_case(
                    scenario=f"Verify the required '{field_name}' field accepts valid input.",
                    description=f"Check the required {input_type or 'text'} field '{field_name}' using the actual scanner metadata.",
                    preconditions=["The form is loaded.", "The required field is present."],
                    steps=[
                        "Open the form under test.",
                        f"Enter a valid value into the required field '{field_name}'.",
                        "Document the observed validation or submission outcome without assuming success.",
                    ],
                    test_data=base_data,
                    expected_result="The required field is verified against real application behavior once execution is available; no success claim is assumed in this metadata-only step.",
                    priority="High",
                    category="Positive",
                    execution_type="Manual",
                )
            )

            cases.append(
                _build_case(
                    scenario=f"Check invalid input handling for the required '{field_name}' field.",
                    description=f"Inspect the required field '{field_name}' for invalid-entry handling using actual scanner metadata only.",
                    preconditions=["The form is loaded.", "The required field is present."],
                    steps=[
                        "Open the form under test.",
                        f"Leave the required field '{field_name}' empty or provide invalid content.",
                        "Observe the application's actual response without assuming a specific validation rule.",
                    ],
                    test_data={**base_data, "invalid_input": "empty_or_invalid"},
                    expected_result="The invalid-entry outcome is identified only from the actual application behavior and not from invented validation assumptions.",
                    priority="High",
                    category="Input Validation",
                    execution_type="Manual",
                )
            )
        else:
            cases.append(
                _build_case(
                    scenario=f"Check the optional '{field_name}' field when left empty.",
                    description=f"Evaluate the optional field '{field_name}' with no value using only the discovered form metadata.",
                    preconditions=["The form is loaded.", "The optional field is present."],
                    steps=[
                        "Open the form under test.",
                        f"Leave the optional field '{field_name}' empty.",
                        "Document the actual result without assuming a specific outcome.",
                    ],
                    test_data={**base_data, "submitted_value": ""},
                    expected_result="The application handles the empty optional field according to its real behavior, without assuming a specific result.",
                    priority="Medium",
                    category="Functional",
                    execution_type="Manual",
                )
            )

        if input_type == "number":
            numeric_min = _parse_numeric_constraint(field.get("min"))
            numeric_max = _parse_numeric_constraint(field.get("max"))
            if numeric_min is not None:
                cases.append(
                    _build_case(
                        scenario=f"Check numeric lower-bound handling for '{field_name}'.",
                        description=f"Use the actual min constraint for '{field_name}' to assess minimum-boundary behavior.",
                        preconditions=["The input field is present.", "A numeric minimum constraint is in the scan metadata."],
                        steps=[
                            "Open the form under test.",
                            f"Apply the minimum boundary value for '{field_name}'.",
                            "Verify the actual application behavior at that boundary.",
                        ],
                        test_data={**base_data, "boundary_type": "numeric_min", "boundary_value": numeric_min},
                        expected_result="The field is evaluated against the actual minimum boundary value without inventing additional numeric limits.",
                        priority="High",
                        category="Boundary",
                        execution_type="Manual",
                    )
                )
            if numeric_max is not None:
                cases.append(
                    _build_case(
                        scenario=f"Check numeric upper-bound handling for '{field_name}'.",
                        description=f"Use the actual max constraint for '{field_name}' to assess maximum-boundary behavior.",
                        preconditions=["The input field is present.", "A numeric maximum constraint is in the scan metadata."],
                        steps=[
                            "Open the form under test.",
                            f"Apply the maximum boundary value for '{field_name}'.",
                            "Verify the actual application behavior at that boundary.",
                        ],
                        test_data={**base_data, "boundary_type": "numeric_max", "boundary_value": numeric_max},
                        expected_result="The field is evaluated against the actual maximum boundary value without inventing additional numeric limits.",
                        priority="High",
                        category="Boundary",
                        execution_type="Manual",
                    )
                )

        minlength = field.get("minlength")
        maxlength = field.get("maxlength")
        if isinstance(minlength, int) and not isinstance(minlength, bool):
            cases.append(
                _build_case(
                    scenario=f"Check minimum-length handling for '{field_name}'.",
                    description=f"Use the actual minlength constraint for '{field_name}' to assess minimum-length behavior.",
                    preconditions=["The input field is present.", "A minimum-length constraint is in the scan metadata."],
                    steps=[
                        "Open the form under test.",
                        f"Enter a value at the minimum length for '{field_name}'.",
                        "Verify the application behavior at that length boundary.",
                    ],
                    test_data={**base_data, "boundary_type": "length_min", "boundary_value": minlength},
                    expected_result="The field is evaluated against the actual minimum-length constraint without inventing new length rules.",
                    priority="High",
                    category="Boundary",
                    execution_type="Manual",
                )
            )
        if isinstance(maxlength, int) and not isinstance(maxlength, bool):
            cases.append(
                _build_case(
                    scenario=f"Check maximum-length handling for '{field_name}'.",
                    description=f"Use the actual maxlength constraint for '{field_name}' to assess maximum-length behavior.",
                    preconditions=["The input field is present.", "A maximum-length constraint is in the scan metadata."],
                    steps=[
                        "Open the form under test.",
                        f"Enter a value at the maximum length for '{field_name}'.",
                        "Verify the application behavior at that length boundary.",
                    ],
                    test_data={**base_data, "boundary_type": "length_max", "boundary_value": maxlength},
                    expected_result="The field is evaluated against the actual maximum-length constraint without inventing new length rules.",
                    priority="High",
                    category="Boundary",
                    execution_type="Manual",
                )
            )

        pattern = field.get("pattern")
        if isinstance(pattern, str) and pattern.strip():
            cases.append(
                _build_case(
                    scenario=f"Validate the pattern for '{field_name}'.",
                    description=f"Check the actual pattern constraint for '{field_name}' without inventing unsupported validation rules.",
                    preconditions=["The input field is present.", "A pattern constraint is in the scan metadata."],
                    steps=[
                        "Open the form under test.",
                        f"Apply a value that should satisfy or fail the pattern '{pattern}' for '{field_name}'.",
                        "Observe the actual validation result.",
                    ],
                    test_data={**base_data, "pattern": pattern},
                    expected_result="The field behavior is checked against the actual pattern metadata and no additional validation rules are assumed.",
                    priority="High",
                    category="Input Validation",
                    execution_type="Manual",
                )
            )

        if input_type == "email":
            cases.append(
                _build_case(
                    scenario=f"Check malformed email handling for '{field_name}'.",
                    description=f"Exercise the email-type field '{field_name}' with malformed input using the actual field metadata.",
                    preconditions=["The field is present.", "The field type indicates email input."],
                    steps=[
                        "Open the form under test.",
                        f"Enter a malformed email value into '{field_name}'.",
                        "Inspect the actual application response to invalid email input.",
                    ],
                    test_data={**base_data, "invalid_email": "not-an-email"},
                    expected_result="The application response to malformed email input is evaluated from the actual runtime behavior, not from assumed validation rules.",
                    priority="High",
                    category="Input Validation",
                    execution_type="Manual",
                )
            )

    return cases


def _generate_form_cases(forms: Any) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for form in _as_list(forms):
        data = _safe_mapping(form)
        if not data:
            continue
        form_id = _clean_text(data.get("id") or data.get("name") or "anonymous-form")
        method = _clean_text(data.get("method") or "get").lower()
        action = _clean_text(data.get("action") or "")
        fields = _safe_list(data.get("fields"))
        required_fields = [
            _field_label(_safe_mapping(field), "unknown-field")
            for field in fields
            if _safe_mapping(field).get("required")
        ]
        cases.append(
            _build_case(
                scenario=f"Validate required fields on form '{form_id}'.",
                description=f"Review the actual form definition for '{form_id}' with method '{method}' and action '{action or 'not specified'}'.",
                preconditions=["The form metadata is available."],
                steps=[
                    "Inspect the form definition.",
                    f"Review the method '{method}' and action '{action or 'not specified'}'.",
                    f"Check the required fields: {', '.join(required_fields) if required_fields else 'none declared'}.",
                    "Document the validation requirements actually exposed by the metadata.",
                ],
                test_data={"id": form_id, "method": method, "action": action, "required_fields": required_fields},
                expected_result="The required-field metadata and form definition are documented without assuming a successful submission response.",
                priority="High",
                category="Form Validation",
                execution_type="Manual",
            )
        )
    return cases


def _metadata_assertion_case(
    *,
    scenario: str,
    description: str,
    expected_result: str,
    priority: str,
    category: str,
    element_kind: str,
    locator_candidates: Any,
    assertion: dict[str, Any],
) -> dict[str, Any]:
    case = _build_case(
        scenario=scenario,
        description=description,
        preconditions=["The scanned page is loaded."],
        steps=[
            "Open the saved application URL.",
            scenario,
            "Do not interact with the element or submit a form.",
        ],
        test_data={
            "element_kind": element_kind,
            "locator_candidates": _safe_list(locator_candidates),
            "assertion": assertion,
        },
        expected_result=expected_result,
        priority=priority,
        category=category,
        execution_type="Manual",
    )
    return case


def _generate_metadata_assertion_cases(scan_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = _safe_mapping(scan_result.get("element_metadata"))
    cases: list[dict[str, Any]] = []

    for button in _safe_list(metadata.get("buttons")):
        element = _safe_mapping(button)
        enabled = element.get("enabled")
        if not isinstance(enabled, bool):
            continue
        label = _clean_text(element.get("accessible_name") or element.get("element_text")) or "unnamed button"
        state = "enabled" if enabled else "disabled"
        cases.append(
            _metadata_assertion_case(
                scenario=f"Verify button '{label}' is {state}.",
                description="Compare the current button enabled state with the boolean state measured by the scanner.",
                expected_result=f"The button is {state}, matching the saved scanner metadata.",
                priority="Medium",
                category="Button Interaction",
                element_kind="button",
                locator_candidates=element.get("locator_candidates"),
                assertion={"type": "enabled", "expected": enabled},
            )
        )

    input_attributes = ("required", "readonly", "minlength", "maxlength", "min", "max", "pattern")
    for index, field in enumerate(_safe_list(metadata.get("inputs")), start=1):
        element = _safe_mapping(field)
        label = _field_label(element, f"input_{index}")
        for attribute in input_attributes:
            expected = element.get(attribute)
            if expected is None or (not isinstance(expected, (str, bool, int, float))):
                continue
            cases.append(
                _metadata_assertion_case(
                    scenario=f"Verify input '{label}' has {attribute}={expected!r}.",
                    description="Compare the live input attribute with the value explicitly recorded by the scanner.",
                    expected_result=f"The input {attribute} attribute matches the saved scanner value {expected!r}.",
                    priority="Medium",
                    category="Input Validation",
                    element_kind="input",
                    locator_candidates=element.get("locator_candidates"),
                    assertion={"type": "attribute", "attribute": attribute, "expected": expected},
                )
            )

    return cases


def _generate_cases_from_scan(scan_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    final_url = _clean_text(scan_result.get("final_url")) or None
    cases.extend(_generate_heading_cases(scan_result.get("headings")))
    cases.extend(_generate_button_cases(scan_result.get("buttons")))
    cases.extend(_generate_link_cases(scan_result.get("links"), final_url))
    cases.extend(_generate_input_cases(scan_result.get("inputs")))
    cases.extend(_generate_form_cases(scan_result.get("forms")))
    cases.extend(_generate_metadata_assertion_cases(scan_result))
    for case in cases:
        case["execution_type"] = classify_execution_type(case, scan_result)
        case["test_case_id"] = _candidate_id(
            {
                key: case[key]
                for key in (
                    "scenario",
                    "description",
                    "preconditions",
                    "steps",
                    "test_data",
                    "expected_result",
                    "priority",
                    "category",
                    "execution_type",
                    "status",
                )
            }
        )
    return cases


def _validate_generated_cases(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    valid_cases: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_ids: set[str] = set()

    for index, case in enumerate(cases, start=1):
        ok, issues = _validate_case(case)
        if not ok:
            errors.append(f"Case #{index} invalid: {'; '.join(issues)}")
            continue
        case_id = str(case["test_case_id"]).strip()
        if case_id in seen_ids:
            errors.append(f"Duplicate test_case_id detected: {case_id}")
            continue
        seen_ids.add(case_id)
        valid_cases.append(dict(case))

    return valid_cases, errors


def generate_test_cases(scan_result: Any) -> dict[str, Any]:
    """Generate structured, metadata-backed test suggestions and a generation summary."""
    normalized = _normalize_scan_result(scan_result)
    supported_metadata = _collect_supported_metadata(normalized)
    cases = _generate_cases_from_scan(normalized)
    deduplicated = _deduplicate_cases(cases)
    valid_cases, validation_errors = _validate_generated_cases(deduplicated)

    summary = {
        "generated_count": len(valid_cases),
        "empty_scan": not any(supported_metadata.values()) or len(valid_cases) == 0,
        "supported_metadata": supported_metadata,
        "generated_categories": {
            category: sum(1 for case in valid_cases if case.get("category") == category)
            for category in sorted(VALID_CATEGORIES)
        },
        "notes": [],
    }

    if not any(supported_metadata.values()):
        summary["notes"].append("No supported scanner metadata was available; no test suggestions were generated.")
    if validation_errors:
        summary["notes"].extend(validation_errors)
    if not summary["notes"] and valid_cases:
        summary["notes"].append("Test cases generated from supported scanner metadata only.")

    return {"test_cases": valid_cases, "summary": summary}


def generate_tests(scan_result: Any) -> list[dict[str, Any]]:
    """Backward-compatible helper returning only the generated case list."""
    return generate_test_cases(scan_result)["test_cases"]


__all__ = [
    "generate_test_cases",
    "generate_tests",
]
