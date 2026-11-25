from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_INVESTIGATION: dict[str, tuple[str, list[str]]] = {
    "Locator not found": (
        "The saved scanner locator did not match an element in the current page.",
        [
            "Run a fresh scan and compare the current page structure with the saved locator metadata.",
            "Confirm the application loaded the expected route and state.",
        ],
    ),
    "Ambiguous locator": (
        "More than one current element matched a locator that was expected to be unique.",
        [
            "Run a fresh scan to refresh measured locator counts.",
            "Add a stable, unique accessible name or test identifier to the intended element.",
        ],
    ),
    "Element not visible": (
        "A unique matching element was present, but Playwright reported that it was not visible.",
        [
            "Check whether the element is hidden by the current page state, responsive layout, or CSS.",
            "Run the check after the application reaches its intended stable state.",
        ],
    ),
    "Element disabled": (
        "The observed button enabled state differed from the saved expected state.",
        [
            "Check the actual disabled attribute and aria-disabled state in the current page.",
            "Confirm the expected state is still appropriate for the selected application state.",
        ],
    ),
    "Navigation failure": (
        "The browser could not load the registered application URL.",
        [
            "Check application availability, DNS, TLS, and the registered URL.",
            "Review whether a redirect or dependent request was blocked by destination safety checks.",
        ],
    ),
    "Assertion failure": (
        "The browser-observed value differed from the saved expected result.",
        [
            "Compare the observed value with the current page content and the scan used to generate this case.",
            "If the application changed intentionally, refresh the scan and regenerate the affected test case.",
        ],
    ),
    "Timeout": (
        "A browser navigation or assertion operation exceeded its configured timeout.",
        [
            "Check application response time and whether the target element is rendered after initial navigation.",
            "Retry after confirming the application is responsive.",
        ],
    ),
    "Browser execution error": (
        "The browser raised an unexpected error while evaluating the assertion.",
        [
            "Review the sanitized execution diagnostic and retry the run.",
            "Check the local Playwright browser installation and application compatibility.",
        ],
    ),
}

_POSSIBLE_CAUSES = {
    "Locator not found": "Possible causes include a changed page structure, a different route, or content that is no longer rendered. None is confirmed by this result.",
    "Ambiguous locator": "Possible causes include duplicated accessible names or a changed page structure. The result confirms multiple matches, but not why they exist.",
    "Element not visible": "Possible causes include a hidden UI state, responsive layout, or CSS changes. The result does not identify which condition applies.",
    "Element disabled": "Possible causes include application state or a changed control rule. The result confirms the state mismatch but not its cause.",
    "Navigation failure": "Possible causes include application availability, DNS/TLS issues, or a redirect blocked by URL safety checks. The specific cause is unconfirmed.",
    "Assertion failure": "Possible causes include changed page content or a stale scan expectation. The value mismatch alone does not establish a root cause.",
    "Timeout": "Possible causes include a slow response or delayed rendering. The recorded timeout does not distinguish between them.",
    "Browser execution error": "Possible causes include a local browser/runtime issue or an application compatibility problem. Neither is confirmed.",
}


def analyze_failure(result: Mapping[str, Any]) -> dict[str, Any] | None:
    if result.get("execution_status") not in {"Failed", "Blocked", "Error"}:
        return None

    details = result.get("failure_details")
    details = details if isinstance(details, Mapping) else {}
    raw_category = details.get("category")
    category = raw_category if isinstance(raw_category, str) else "Assertion failure"
    if category in {"Locator metadata missing", "Locator not found"}:
        category = "Locator not found"
    if category not in _INVESTIGATION:
        category = "Assertion failure"

    summary, steps = _INVESTIGATION[category]
    diagnostic = details.get("details")
    if not isinstance(diagnostic, str) or not diagnostic:
        diagnostic = result.get("error_message")
    if not isinstance(diagnostic, str):
        diagnostic = "No additional browser diagnostic was recorded."

    return {
        "failure_category": category,
        "error_summary": str(result.get("error_message") or summary),
        "diagnostic_details": diagnostic,
        "likely_cause": _POSSIBLE_CAUSES[category],
        "suggested_investigation_steps": steps,
    }


__all__ = ["analyze_failure"]
