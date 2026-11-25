from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, async_playwright

try:
    from backend.scanner import validate_destination_url
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from scanner import validate_destination_url

logger = logging.getLogger(__name__)

ExecutionStatus = Literal["Passed", "Failed", "Blocked", "Error", "Not Automatable"]
ACTION_TIMEOUT_MS = 3_000
NAVIGATION_TIMEOUT_MS = 10_000
MAX_TEST_CASES_PER_RUN = 100
_BROWSER_SEMAPHORE = asyncio.Semaphore(2)
_LOCATOR_PREFERENCE = ("data-testid", "role", "label", "id", "name", "placeholder", "css")
_ATTRIBUTE_ASSERTIONS = {"required", "readonly", "minlength", "maxlength", "min", "max", "pattern"}
_LINK_DESTINATIONS = {
    "missing",
    "anchor",
    "external",
    "same-origin absolute",
    "different-origin absolute",
    "absolute",
    "relative internal",
    "malformed",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_url_origin(
    url: str | None, *, fallback_scheme: str | None = None
) -> tuple[str, str, int] | None:
    value = _text(url)
    if not value:
        return None
    if value.startswith("//"):
        if not fallback_scheme:
            return None
        value = f"{fallback_scheme}:{value}"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if not parsed.scheme or not parsed.hostname:
        return None
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    default_ports = {"http": 80, "https": 443}
    if port is None:
        port = default_ports.get(scheme)
    return scheme, hostname, port or 0


def classify_link_destination(href: Any, final_url: str | None) -> str:
    value = _text(href)
    if not value:
        return "missing"
    if value.startswith("#"):
        return "anchor"
    candidate = value
    fallback_scheme = None
    if isinstance(final_url, str) and final_url:
        try:
            final_parts = urlsplit(final_url)
        except ValueError:
            final_parts = None
        if final_parts and final_parts.scheme:
            fallback_scheme = final_parts.scheme.lower()
    if value.startswith("//"):
        if not fallback_scheme:
            return "malformed"
        candidate = f"{fallback_scheme}:{value}"
    if candidate.startswith(("mailto:", "tel:")):
        return "external"
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return "malformed"
    if parsed.scheme and parsed.hostname:
        target_origin = _normalize_url_origin(candidate)
        source_origin = _normalize_url_origin(final_url, fallback_scheme=fallback_scheme)
        if target_origin and source_origin:
            if target_origin == source_origin:
                return "same-origin absolute"
            return "different-origin absolute"
        if target_origin:
            return "absolute"
        return "malformed"
    if candidate.startswith(("/", "./", "../", "?")):
        return "relative internal"
    if not parsed.scheme and not parsed.netloc:
        return "relative internal"
    return "malformed"


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_execution_url(value: str) -> str:
    validate_destination_url(value)
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Application URLs containing credentials are not allowed for browser execution")
    return value


def _result(
    test_case: Mapping[str, Any],
    *,
    status: ExecutionStatus,
    action: str,
    assertion: str | None,
    actual: str | None,
    started_at: str,
    started: float,
    error: str | None = None,
    failure_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "test_case_id": test_case.get("test_case_id", ""),
        "execution_status": status,
        "action_performed": action,
        "assertion_performed": assertion,
        "expected_result": test_case.get("expected_result"),
        "actual_result": actual,
        "error_message": error,
        "failure_details": failure_details,
        "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
        "screenshot_path": None,
        "started_at": started_at,
        "completed_at": _now_iso(),
    }


def _target_matches(
    test_case: Mapping[str, Any], scan_result: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    test_data = test_case.get("test_data")
    if not isinstance(test_data, Mapping):
        return None, None, "Test data does not define a supported assertion."

    assertion = test_data.get("assertion")
    if isinstance(assertion, Mapping):
        assertion_type = assertion.get("type")
        kind = test_data.get("element_kind")
        if assertion_type == "enabled" and kind == "button" and isinstance(assertion.get("expected"), bool):
            assertion_text = f"Button enabled state equals {assertion['expected']}."
            expected_field = "enabled"
            expected_value = assertion["expected"]
        elif (
            assertion_type == "attribute"
            and kind == "input"
            and assertion.get("attribute") in _ATTRIBUTE_ASSERTIONS
        ):
            attribute = assertion["attribute"]
            expected_value = assertion.get("expected")
            expected_type = bool if attribute in {"required", "readonly"} else str
            if type(expected_value) is not expected_type:
                return None, None, "The input assertion value does not match the scanner metadata type."
            assertion_text = (
                f"Input attribute {attribute} equals {expected_value!r}."
            )
            expected_field = attribute
        else:
            return None, None, "The explicit assertion type is not supported."

        candidates = test_data.get("locator_candidates")
        if not isinstance(candidates, list):
            candidates = []
        metadata = scan_result.get("element_metadata")
        category = {"button": "buttons", "input": "inputs"}.get(kind)
        scanned = _list(metadata.get(category)) if isinstance(metadata, Mapping) and category else []
        verified = []
        for element in scanned:
            if (
                not isinstance(element, Mapping)
                or type(element.get(expected_field)) is not type(expected_value)
                or element.get(expected_field) != expected_value
            ):
                continue
            for candidate in candidates:
                if (
                    not isinstance(candidate, Mapping)
                    or candidate.get("strategy") not in _LOCATOR_PREFERENCE
                    or candidate.get("is_unique") is not True
                    or candidate.get("match_count") != 1
                ):
                    continue
                if any(
                    isinstance(saved, Mapping)
                    and saved.get("strategy") == candidate.get("strategy")
                    and saved.get("value") == candidate.get("value")
                    and saved.get("is_unique") is True
                    and saved.get("match_count") == 1
                    for saved in _list(element.get("locator_candidates"))
                ):
                    verified.append(dict(candidate))
        return {"locator_candidates": verified}, assertion_text, None

    metadata = scan_result.get("element_metadata")
    if not isinstance(metadata, Mapping):
        return {"locator_candidates": []}, None, "The scan does not contain structured locator metadata."

    category = test_case.get("category")
    target_assertion: dict[str, Any] = {}
    if category == "Functional" and isinstance(test_data.get("heading"), str):
        label = _text(test_data.get("heading"))
        elements = _list(metadata.get("headings"))
        assertion_text = f"Heading is visible and its text equals {label!r}."
        matches = [
            item for item in elements
            if isinstance(item, Mapping) and _text(item.get("element_text")) == label
        ]
    elif category == "Button Interaction" and isinstance(test_data.get("text"), str):
        data = test_data.get("metadata")
        legacy = data if isinstance(data, Mapping) else {}
        label = _text(test_data.get("text"))
        elements = _list(metadata.get("buttons"))
        assertion_text = f"Button {label!r} is visible."
        matches = [
            item for item in elements
            if isinstance(item, Mapping)
            and label in {
                _text(item.get("element_text")),
                _text(item.get("accessible_name")),
                _text(item.get("text")),
            }
            and (
                not legacy.get("type")
                or not item.get("tag_name")
                or _text(item.get("tag_name")) == _text(legacy.get("type"))
            )
        ]
    elif category == "Navigation" and isinstance(test_data.get("href"), str):
        href = test_data["href"]
        destination_type = test_data.get("destination_type")
        if not isinstance(destination_type, str) or destination_type not in _LINK_DESTINATIONS:
            return None, None, "The saved link destination assertion is not supported."
        label = _text(test_data.get("text"))
        elements = _list(metadata.get("links"))
        assertion_text = (
            f"Link href equals {href!r} and its destination is classified as "
            f"{destination_type!r}."
        )
        final_url = test_data.get("final_url") or scan_result.get("final_url")
        target_assertion = {
            "expected_href": href,
            "destination_type": destination_type,
            "final_url": final_url if isinstance(final_url, str) else None,
        }
        matches = [
            item for item in elements
            if isinstance(item, Mapping)
            and item.get("href") == href
            and _text(item.get("text") or item.get("element_text")) == label
        ]
    else:
        return None, None, "The scenario requires application behavior or an unsupported action."

    if len(matches) > 1:
        return None, assertion_text, "The test case matches multiple scanned elements."
    if not matches:
        return {"locator_candidates": []}, assertion_text, "No scanned element matches this test case."
    target = dict(matches[0])
    target.update(target_assertion)
    return target, assertion_text, None


def assess_automation_capability(
    test_case: Mapping[str, Any], scan_result: Mapping[str, Any]
) -> dict[str, Any]:
    target, assertion, reason = _target_matches(test_case, scan_result)
    if target is None:
        ambiguous = reason is not None and "multiple scanned elements" in reason.lower()
        missing_metadata = reason is not None and (
            "structured locator metadata" in reason.lower()
            or "no scanned element matches" in reason.lower()
        )
        if ambiguous or missing_metadata:
            return {
                "automatable": False,
                "eligibility": "Ambiguous locator" if ambiguous else "Locator metadata missing",
                "reason": reason,
                "action": "No browser action will be performed.",
            }
        return {
            "automatable": False,
            "eligibility": "Not Automatable",
            "reason": reason,
            "action": "No browser action will be performed.",
        }

    candidates = _list(target.get("locator_candidates"))
    unique = [
        candidate for candidate in candidates
        if isinstance(candidate, Mapping)
        and candidate.get("is_unique") is True
        and candidate.get("match_count") == 1
        and candidate.get("strategy") in _LOCATOR_PREFERENCE
    ]
    if not unique:
        ambiguous = any(
            isinstance(candidate, Mapping) and candidate.get("match_count", 0) not in (0, None)
            for candidate in candidates
        )
        reason = "Scanner metadata reports only ambiguous locator candidates." if ambiguous else (
            "The scan has no measured, unique locator for this element."
        )
        return {
            "automatable": False,
            "eligibility": "Ambiguous locator" if ambiguous else "Locator metadata missing",
            "reason": reason,
            "action": "No browser action will be performed.",
        }

    return {
        "automatable": True,
        "eligibility": "Automatable",
        "reason": None,
        "action": "Open the saved application URL and inspect the uniquely identified element without interacting with it.",
        "assertion": assertion,
    }


def classify_execution_type(
    test_case: Mapping[str, Any], scan_result: Mapping[str, Any]
) -> str:
    return (
        "Automated"
        if assess_automation_capability(test_case, scan_result)["automatable"]
        else "Manual"
    )


def assess_automation(
    test_case: Mapping[str, Any], scan_result: Mapping[str, Any]
) -> dict[str, Any]:
    if test_case.get("execution_type") != "Automated":
        return {
            "automatable": False,
            "eligibility": "Not Automatable",
            "reason": "This test case is classified as Manual.",
            "action": "No browser action will be performed.",
        }
    return assess_automation_capability(test_case, scan_result)


def _make_locator(page: Page, candidate: Mapping[str, Any]) -> Locator:
    strategy = candidate.get("strategy")
    value = candidate.get("value")
    if strategy == "data-testid" and isinstance(value, str):
        return page.get_by_test_id(value)
    if strategy == "role" and isinstance(value, Mapping):
        role, name = value.get("role"), value.get("name")
        if isinstance(role, str) and isinstance(name, str):
            return page.get_by_role(role, name=name, exact=True, include_hidden=True)
    if strategy == "label" and isinstance(value, str):
        return page.get_by_label(value, exact=True)
    if strategy == "placeholder" and isinstance(value, str):
        return page.get_by_placeholder(value, exact=True)
    if strategy == "id" and isinstance(value, str):
        return page.locator(f"[id={json.dumps(value)}]")
    if strategy == "name" and isinstance(value, str):
        return page.locator(f"[name={json.dumps(value)}]")
    if strategy == "css" and isinstance(value, str):
        return page.locator(value)
    raise ValueError("The scanner locator candidate is invalid or unsupported.")


async def _resolve_locator(page: Page, target: Mapping[str, Any]) -> tuple[Locator | None, str | None]:
    candidates = _list(target.get("locator_candidates"))
    ordered = sorted(
        (candidate for candidate in candidates if isinstance(candidate, Mapping)),
        key=lambda item: _LOCATOR_PREFERENCE.index(item["strategy"])
        if item.get("strategy") in _LOCATOR_PREFERENCE else len(_LOCATOR_PREFERENCE),
    )
    if not ordered:
        return None, "Locator metadata is missing."

    observed_ambiguous = False
    for candidate in ordered:
        if (
            candidate.get("is_unique") is not True
            or candidate.get("match_count") != 1
            or candidate.get("strategy") not in _LOCATOR_PREFERENCE
        ):
            observed_ambiguous |= candidate.get("match_count", 0) not in (0, None, 1)
            continue
        try:
            locator = _make_locator(page, candidate)
            count = await locator.count()
        except Exception:
            logger.debug("Unable to resolve a verified scanner locator")
            continue
        if count == 1:
            return locator, None
        observed_ambiguous |= count > 1

    if observed_ambiguous:
        return None, "The scanner locator is ambiguous in the current page."
    return None, "The scanner locator no longer matches an element on the current page."


async def execute_case(
    page: Page,
    test_case: Mapping[str, Any],
    scan_result: Mapping[str, Any],
    timeout_ms: int = ACTION_TIMEOUT_MS,
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = _now_iso()
    plan = assess_automation(test_case, scan_result)
    if not plan["automatable"]:
        status: ExecutionStatus = (
            "Blocked" if plan["eligibility"] in {"Ambiguous locator", "Locator metadata missing"}
            else "Not Automatable"
        )
        return _result(
            test_case,
            status=status,
            action=plan["action"],
            assertion=None,
            actual=None,
            started_at=started_at,
            started=started,
            error=plan["reason"],
            failure_details={"category": plan["eligibility"], "details": plan["reason"]},
        )

    target, assertion_text, target_error = _target_matches(test_case, scan_result)
    if target is None:
        return _result(
            test_case,
            status="Not Automatable",
            action=plan["action"],
            assertion=assertion_text,
            actual=None,
            started_at=started_at,
            started=started,
            error=target_error,
        )

    page.set_default_timeout(timeout_ms)
    locator, locator_error = await _resolve_locator(page, target)
    if locator is None:
        ambiguous = locator_error is not None and "ambiguous" in locator_error.lower()
        return _result(
            test_case,
            status="Blocked",
            action=plan["action"],
            assertion=assertion_text,
            actual=None,
            started_at=started_at,
            started=started,
            error=locator_error,
            failure_details={
                "category": "Ambiguous locator" if ambiguous else "Locator not found",
                "details": locator_error,
            },
        )

    try:
        test_data = test_case.get("test_data")
        assertion = test_data.get("assertion") if isinstance(test_data, Mapping) else None
        if isinstance(assertion, Mapping) and assertion.get("type") == "enabled":
            native_enabled = await locator.is_enabled()
            aria_disabled = await locator.get_attribute("aria-disabled")
            actual: Any = native_enabled and aria_disabled != "true"
            expected = assertion["expected"]
        elif isinstance(assertion, Mapping) and assertion.get("type") == "attribute":
            attribute = assertion["attribute"]
            actual_attribute = await locator.get_attribute(attribute)
            expected = assertion.get("expected")
            actual = actual_attribute is not None if isinstance(expected, bool) else actual_attribute
        elif test_case.get("category") == "Navigation":
            actual_href = await locator.get_attribute("href")
            actual = (
                actual_href,
                classify_link_destination(actual_href, target.get("final_url")),
            )
            expected = (target.get("expected_href"), target.get("destination_type"))
        else:
            visible = await locator.is_visible()
            if not visible:
                return _result(
                    test_case,
                    status="Failed",
                    action=plan["action"],
                    assertion=assertion_text,
                    actual="The element exists but is not visible.",
                    started_at=started_at,
                    started=started,
                    error="Element not visible.",
                    failure_details={
                        "category": "Element not visible",
                        "details": "A unique locator matched, but Playwright reports that the element is not visible.",
                    },
                )
            if test_case.get("category") == "Functional":
                actual = _text(await locator.inner_text())
                data = test_case.get("test_data")
                expected = _text(data.get("heading")) if isinstance(data, Mapping) else ""
            else:
                actual = "Element is visible."
                expected = "Element is visible."

        passed = actual == expected
        if test_case.get("category") == "Navigation":
            actual_text = "The live link href and destination classification match the saved scan." if passed else (
                f"Observed href {actual[0]!r} classified as {actual[1]!r}; "
                f"expected href {expected[0]!r} classified as {expected[1]!r}."
            )
        else:
            actual_text = f"Observed {actual!r}; expected {expected!r}."
        failure_details = None
        error = None
        if not passed:
            category = "Element disabled" if (
                isinstance(assertion, Mapping)
                and assertion.get("type") == "enabled"
                and actual is False
            ) else "Assertion failure"
            error = f"{category}: the observed value did not match the saved expectation."
            failure_details = {
                "category": category,
                "details": (
                    "The live link href did not match the saved scanner metadata."
                    if test_case.get("category") == "Navigation"
                    else actual_text
                ),
            }
        return _result(
            test_case,
            status="Passed" if passed else "Failed",
            action=plan["action"],
            assertion=assertion_text,
            actual=actual_text,
            started_at=started_at,
            started=started,
            error=error,
            failure_details=failure_details,
        )
    except PlaywrightTimeoutError as exc:
        return _result(
            test_case,
            status="Error",
            action=plan["action"],
            assertion=assertion_text,
            actual=None,
            started_at=started_at,
            started=started,
            error="The browser operation timed out.",
            failure_details={
                "category": "Timeout",
                "details": f"Playwright raised {type(exc).__name__} while evaluating the assertion.",
            },
        )
    except Exception as exc:
        logger.error("Browser assertion failed unexpectedly (%s)", type(exc).__name__)
        return _result(
            test_case,
            status="Error",
            action=plan["action"],
            assertion=assertion_text,
            actual=None,
            started_at=started_at,
            started=started,
            error=f"Browser assertion error ({type(exc).__name__}).",
            failure_details={
                "category": "Browser execution error",
                "details": f"Playwright raised {type(exc).__name__}.",
            },
        )


async def execute_test_cases(
    application_url: str,
    test_cases: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    timeout_ms: int = NAVIGATION_TIMEOUT_MS,
    max_test_cases: int = MAX_TEST_CASES_PER_RUN,
) -> list[dict[str, Any]]:
    if not 250 <= timeout_ms <= 60_000:
        raise ValueError("Execution timeout must be between 250 and 60000 milliseconds.")
    if not 1 <= max_test_cases <= MAX_TEST_CASES_PER_RUN:
        raise ValueError(f"Maximum test cases must be between 1 and {MAX_TEST_CASES_PER_RUN}.")
    if len(test_cases) > max_test_cases:
        raise ValueError(f"A run cannot include more than {max_test_cases} test cases.")
    validate_execution_url(application_url)

    results: list[dict[str, Any] | None] = [None] * len(test_cases)
    eligible_indices = [
        index for index, (case, scan) in enumerate(test_cases)
        if assess_automation(case, scan)["automatable"]
    ]
    eligible_set = set(eligible_indices)
    for index, (case, scan) in enumerate(test_cases):
        if index not in eligible_set:
            started = time.perf_counter()
            started_at = _now_iso()
            plan = assess_automation(case, scan)
            status: ExecutionStatus = (
                "Blocked"
                if plan["eligibility"] in {"Ambiguous locator", "Locator metadata missing"}
                else "Not Automatable"
            )
            results[index] = _result(
                case,
                status=status,
                action=plan["action"],
                assertion=plan.get("assertion"),
                actual=None,
                started_at=started_at,
                started=started,
                error=plan["reason"],
                failure_details={"category": plan["eligibility"], "details": plan["reason"]},
            )
    if not eligible_indices:
        return [result for result in results if result is not None]

    browser = None
    context = None
    failure: tuple[str, str] | None = None
    async with _BROWSER_SEMAPHORE:
        try:
            async with async_playwright() as playwright:
                try:
                    browser = await playwright.chromium.launch(headless=True)
                    context = await browser.new_context(
                        accept_downloads=False,
                        service_workers="block",
                    )

                    async def guard_request(route: Any, request: Any) -> None:
                        try:
                            validate_execution_url(request.url)
                        except ValueError:
                            await route.abort()
                            return
                        await route.continue_()

                    await context.route("**/*", guard_request)
                    page = await context.new_page()
                    try:
                        await page.goto(
                            application_url,
                            wait_until="domcontentloaded",
                            timeout=timeout_ms,
                        )
                    except PlaywrightTimeoutError:
                        failure = (
                            "Timeout",
                            "The application did not finish loading before the navigation timeout.",
                        )
                    except Exception as exc:
                        failure = (
                            "Navigation failure",
                            f"Application navigation failed ({type(exc).__name__}).",
                        )
                    else:
                        for index in eligible_indices:
                            case, scan = test_cases[index]
                            results[index] = await execute_case(page, case, scan, timeout_ms)
                except Exception as exc:
                    logger.error("Browser setup failed during test execution (%s)", type(exc).__name__)
                    failure = (
                        "Browser execution error",
                        f"Browser setup failed ({type(exc).__name__}).",
                    )
                finally:
                    if context is not None:
                        try:
                            await context.close()
                        except Exception as exc:
                            logger.error("Failed to close execution browser context (%s)", type(exc).__name__)
                    if browser is not None:
                        try:
                            await browser.close()
                        except Exception as exc:
                            logger.error("Failed to close execution browser (%s)", type(exc).__name__)
        except Exception as exc:
            logger.error("Playwright shutdown failed during test execution (%s)", type(exc).__name__)
            failure = (
                "Browser execution error",
                f"Playwright shutdown failed ({type(exc).__name__}).",
            )

    if failure:
        category, message = failure
        for index in eligible_indices:
            case, scan = test_cases[index]
            started = time.perf_counter()
            started_at = _now_iso()
            results[index] = _result(
                case,
                status="Error",
                action="Open the saved application URL.",
                assertion=None,
                actual=None,
                started_at=started_at,
                started=started,
                error=message,
                failure_details={"category": category, "details": message},
            )

    return [result for result in results if result is not None]


__all__ = ["assess_automation", "execute_case", "execute_test_cases"]
