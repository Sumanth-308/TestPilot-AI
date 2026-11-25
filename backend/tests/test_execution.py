import asyncio
import csv
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from playwright.async_api import Playwright, TimeoutError as PlaywrightTimeoutError, async_playwright

from backend import main as backend_main
from backend import test_executor
from backend.bug_analysis import analyze_failure
from backend.scanner import _collect_element_metadata
from backend.test_generator import generate_test_cases


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(backend_main, "DATABASE_DIR", data_dir)
    monkeypatch.setattr(backend_main, "DATABASE_PATH", data_dir / "testpilot.db")
    monkeypatch.setattr(backend_main, "validate_destination_url", lambda value: value)
    backend_main.init_db()
    client = TestClient(backend_main.app)
    yield client
    client.close()


def _button_case() -> dict:
    return {
        "test_case_id": "TC-BUTTON",
        "execution_type": "Automated",
        "scenario": "Verify button 'Continue' is visible.",
        "description": "Check the scanned button.",
        "category": "Button Interaction",
        "expected_result": "The button is visible.",
        "test_data": {"text": "Continue", "metadata": {"type": "button"}},
    }


def _link_case() -> dict:
    return {
        "test_case_id": "TC-LINK",
        "execution_type": "Automated",
        "scenario": "Inspect the link 'Docs'.",
        "description": "Check its scanned destination.",
        "category": "Navigation",
        "expected_result": "The live href equals the scanned href.",
        "test_data": {
            "text": "Docs",
            "href": "/docs",
            "destination_type": "relative internal",
            "final_url": "https://example.com/",
        },
    }


def _scan_result(metadata: dict) -> dict:
    return {"final_url": "https://example.com/", "element_metadata": metadata}


def test_real_browser_executes_safe_assertions_and_rejects_unsupported_cases():
    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(
                '<h1 id="page-title">Welcome</h1>'
                '<button data-testid="continue">Continue</button>'
                '<a href="/docs">Docs</a>'
                '<label for="contact">Contact</label><input id="contact" minlength="2">'
            )
            metadata = await _collect_element_metadata(page)
            result = _scan_result(metadata)

            heading_case = {
                "test_case_id": "TC-HEADING",
                "execution_type": "Automated",
                "category": "Functional",
                "expected_result": "Heading is present.",
                "test_data": {"heading": "Welcome"},
            }
            button = await test_executor.execute_case(page, _button_case(), result)
            link = await test_executor.execute_case(page, _link_case(), result)
            await page.get_by_role("link", name="Docs").evaluate(
                "(element) => element.setAttribute('href', '/elsewhere')"
            )
            changed_link = await test_executor.execute_case(page, _link_case(), result)
            heading = await test_executor.execute_case(page, heading_case, result)

            input_case = generate_test_cases(
                {
                    "element_metadata": {
                        "inputs": [metadata["inputs"][0]],
                        "buttons": [],
                    }
                }
            )["test_cases"]
            input_attribute_case = next(
                case
                for case in input_case
                if case["test_data"].get("assertion", {}).get("attribute") == "required"
            )
            input_result = await test_executor.execute_case(page, input_attribute_case, result)
            readonly_case = next(
                case
                for case in input_case
                if case["test_data"].get("assertion", {}).get("attribute") == "readonly"
            )
            readonly_result = await test_executor.execute_case(page, readonly_case, result)

            unsupported = {
                "test_case_id": "TC-UNSUPPORTED",
                "category": "Input Validation",
                "expected_result": "The application responds to malformed input.",
                "test_data": {"invalid_email": "not-an-email"},
            }
            unsupported_result = await test_executor.execute_case(page, unsupported, result)

            await context.close()
            await browser.close()
            return (
                button,
                link,
                changed_link,
                heading,
                input_result,
                readonly_result,
                unsupported_result,
            )

    button, link, changed_link, heading, input_result, readonly_result, unsupported = asyncio.run(run())
    assert button["execution_status"] == "Passed"
    assert link["execution_status"] == "Passed"
    assert link["actual_result"] == "The live link href and destination classification match the saved scan."
    assert changed_link["execution_status"] == "Failed"
    assert "'/elsewhere'" in changed_link["actual_result"]
    assert heading["execution_status"] == "Passed"
    assert input_result["execution_status"] == "Passed"
    assert input_result["expected_result"] == "The input required attribute matches the saved scanner value False."
    assert readonly_result["execution_status"] == "Passed"
    assert readonly_result["expected_result"] == "The input readonly attribute matches the saved scanner value False."
    assert unsupported["execution_status"] == "Not Automatable"


def test_manual_case_is_not_executed_even_when_its_assertion_is_supported():
    scan = _scan_result(
        {
            "headings": [
                {
                    "element_text": "Welcome",
                    "locator_candidates": [
                        {
                            "strategy": "role",
                            "value": {"role": "heading", "name": "Welcome"},
                            "match_count": 1,
                            "is_unique": True,
                        }
                    ],
                }
            ]
        }
    )
    manual_case = {
        "test_case_id": "TC-MANUAL",
        "execution_type": "Manual",
        "category": "Functional",
        "test_data": {"heading": "Welcome"},
        "expected_result": "Heading is present.",
    }

    assert test_executor.assess_automation_capability(manual_case, scan)["automatable"]
    assert not test_executor.assess_automation(manual_case, scan)["automatable"]
    result = asyncio.run(test_executor.execute_case(None, manual_case, scan))
    assert result["execution_status"] == "Not Automatable"
    assert result["assertion_performed"] is None


def test_actual_assertion_mismatch_is_failed_not_passed():
    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content('<h1 id="page-title">Updated title</h1>')
            scan = await _collect_element_metadata(page)
            scan["headings"][0]["element_text"] = "Expected title"
            result = await test_executor.execute_case(
                page,
                {
                    "test_case_id": "TC-ASSERT",
                    "execution_type": "Automated",
                    "category": "Functional",
                    "expected_result": "The expected heading is present.",
                    "test_data": {"heading": "Expected title"},
                },
                _scan_result(scan),
            )
            await browser.close()
            return result

    result = asyncio.run(run())
    assert result["execution_status"] == "Failed"
    assert result["failure_details"]["category"] == "Assertion failure"


def test_ambiguous_locators_and_missing_locator_metadata_are_blocked():
    case = {
        "test_case_id": "TC-AMBIGUOUS",
        "execution_type": "Automated",
        "category": "Functional",
        "test_data": {"heading": "Welcome"},
        "expected_result": "Heading is visible.",
    }
    duplicated = _scan_result(
        {
            "headings": [
                {
                    "element_text": "Welcome",
                    "locator_candidates": [
                        {
                            "strategy": "role",
                            "value": {"role": "heading", "name": "Welcome"},
                            "match_count": 2,
                            "is_unique": False,
                        }
                    ],
                },
                {
                    "element_text": "Welcome",
                    "locator_candidates": [
                        {
                            "strategy": "role",
                            "value": {"role": "heading", "name": "Welcome"},
                            "match_count": 2,
                            "is_unique": False,
                        }
                    ],
                },
            ]
        }
    )
    assessment = test_executor.assess_automation(case, duplicated)
    assert assessment["automatable"] is False
    assert assessment["eligibility"] == "Ambiguous locator"

    missing = test_executor.assess_automation(case, _scan_result({"headings": []}))
    assert missing["eligibility"] == "Locator metadata missing"


def test_timeout_is_reported_as_error(monkeypatch):
    class TimeoutLocator:
        async def get_attribute(self, _attribute):
            raise PlaywrightTimeoutError("fixture timeout")

    async def resolve(_page, _target):
        return TimeoutLocator(), None

    monkeypatch.setattr(test_executor, "_resolve_locator", resolve)

    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            case = _link_case()
            scan = _scan_result(
                {
                    "links": [
                        {
                            "text": "Docs",
                            "href": "/docs",
                            "locator_candidates": [
                                {
                                    "strategy": "role",
                                    "value": {"role": "link", "name": "Docs"},
                                    "match_count": 1,
                                    "is_unique": True,
                                }
                            ],
                        }
                    ]
                }
            )
            result = await test_executor.execute_case(page, case, scan)
            await browser.close()
            return result

    result = asyncio.run(run())
    assert result["execution_status"] == "Error"
    assert result["failure_details"]["category"] == "Timeout"


def test_execution_closes_browser_and_context_for_local_html_fixture(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<button data-testid="continue">Continue</button>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(test_executor, "validate_destination_url", lambda value: value)

    original_async_playwright = async_playwright
    closed = {"context": False, "browser": False}

    class ContextProxy:
        def __init__(self, inner):
            self.inner = inner

        async def route(self, *args):
            await self.inner.route(*args)

        async def new_page(self):
            return await self.inner.new_page()

        async def close(self):
            await self.inner.close()
            closed["context"] = True

    class BrowserProxy:
        def __init__(self, inner):
            self.inner = inner

        async def new_context(self, **kwargs):
            return ContextProxy(await self.inner.new_context(**kwargs))

        async def close(self):
            await self.inner.close()
            closed["browser"] = True

    class ChromiumProxy:
        def __init__(self, inner):
            self.inner = inner

        async def launch(self, **kwargs):
            return BrowserProxy(await self.inner.launch(**kwargs))

    class PlaywrightProxy:
        def __init__(self, inner):
            self.chromium = ChromiumProxy(inner.chromium)

    class ManagerProxy:
        def __init__(self):
            self.manager = original_async_playwright()

        async def __aenter__(self) -> Playwright:
            inner = await self.manager.__aenter__()
            return PlaywrightProxy(inner)

        async def __aexit__(self, *args):
            return await self.manager.__aexit__(*args)

    monkeypatch.setattr(test_executor, "async_playwright", ManagerProxy)
    scan = _scan_result(
        {
            "buttons": [
                {
                    "element_text": "Continue",
                    "accessible_name": "Continue",
                    "tag_name": "button",
                    "locator_candidates": [
                        {
                            "strategy": "data-testid",
                            "value": "continue",
                            "match_count": 1,
                            "is_unique": True,
                        }
                    ],
                }
            ]
        }
    )

    try:
        results = asyncio.run(
            test_executor.execute_test_cases(
                f"http://127.0.0.1:{server.server_port}/",
                [(_button_case(), scan)],
            )
        )
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()

    assert results[0]["execution_status"] == "Passed"
    assert closed == {"context": True, "browser": True}


def _create_project_and_case(client, result_json):
    project = client.post(
        "/api/projects",
        json={"name": "=Report Formula", "url": "https://example.com"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    with backend_main.get_db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO scans (
                project_id, status, started_at, completed_at, page_title,
                final_url, result_json, error_message
            ) VALUES (?, 'completed', ?, ?, ?, ?, ?, NULL)
            """,
            (
                project_id,
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:01Z",
                "Example",
                "https://example.com/",
                json.dumps(result_json),
            ),
        )
        connection.commit()
        scan_id = cursor.lastrowid
    generated = client.post(f"/api/projects/{project_id}/scans/{scan_id}/test-cases/generate")
    assert generated.status_code == 200, generated.text
    test_case_id = generated.json()["test_cases"][0]["test_case_id"]
    return project_id, test_case_id


def _insert_unexecuted_case(project_id, scan_id, test_case_id):
    with backend_main.get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO test_cases (
                test_case_id, project_id, scan_id, scenario, description,
                preconditions, steps, test_data, expected_result, priority,
                category, execution_type, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, '[]', '[]', '{}', ?, 'Medium', 'Functional',
                      'Manual', 'Not Executed', ?, ?)
            """,
            (
                test_case_id,
                project_id,
                scan_id,
                f"Unselected case {test_case_id}",
                "This case is not part of the execution run.",
                "The case remains unchanged.",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.commit()


def _clone_test_case(project_id, source_test_case_id, cloned_test_case_id):
    with backend_main.get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO test_cases (
                test_case_id, project_id, scan_id, scenario, description,
                preconditions, steps, test_data, expected_result, priority,
                category, execution_type, status, created_at, updated_at
            )
            SELECT ?, project_id, scan_id, scenario, description,
                   preconditions, steps, test_data, expected_result, priority,
                   category, execution_type, status, created_at, updated_at
            FROM test_cases
            WHERE test_case_id = ? AND project_id = ?
            """,
            (cloned_test_case_id, source_test_case_id, project_id),
        )
        connection.commit()


def _execution_result(test_case_id, execution_status, completed_at="2026-01-01T00:00:01Z"):
    return {
        "test_case_id": test_case_id,
        "execution_status": execution_status,
        "action_performed": "Opened app; inspected the saved assertion.",
        "assertion_performed": "The live value matches the saved expectation.",
        "expected_result": "The saved expectation matches.",
        "actual_result": "Observed the live value.",
        "error_message": None if execution_status == "Passed" else f"Execution {execution_status}.",
        "failure_details": (
            None
            if execution_status == "Passed"
            else {"category": "Assertion failure", "details": f"Observed {execution_status}."}
        ),
        "duration_ms": 8,
        "screenshot_path": None,
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": completed_at,
    }


def test_execution_api_persistence_history_analysis_and_csv(api_client, monkeypatch):
    case = _link_case()
    project_id, test_case_id = _create_project_and_case(
        api_client,
        {
            "final_url": "https://example.com/",
            "links": [{"text": "Docs", "href": "/docs"}],
            "element_metadata": {
                "links": [
                    {
                        "text": "Docs",
                        "href": "/docs",
                        "locator_candidates": [
                            {
                                "strategy": "role",
                                "value": {"role": "link", "name": "Docs"},
                                "match_count": 1,
                                "is_unique": True,
                            }
                        ],
                    }
                ]
            },
        },
    )

    async def fake_execution(_url, _cases, **_settings):
        return [
            {
                "test_case_id": test_case_id,
                "execution_status": "Failed",
                "action_performed": "Opened app; inspected link.",
                "assertion_performed": "The href matches the scan.",
                "expected_result": "The link is unchanged.",
                "actual_result": "The link differs.",
                "error_message": "Assertion failure: test fixture.",
                "failure_details": {
                    "category": "Assertion failure",
                    "details": "The live href differed.",
                },
                "duration_ms": 8,
                "screenshot_path": None,
                "started_at": "2026-01-01T00:00:01Z",
                "completed_at": "2026-01-01T00:00:01Z",
            }
        ]

    monkeypatch.setattr(backend_main, "execute_test_cases", fake_execution)
    candidates = api_client.get(f"/api/projects/{project_id}/execution-candidates")
    assert candidates.status_code == 200
    assert candidates.json()[0]["automatable"] is True

    started = api_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": [test_case_id]},
    )
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["failed"] == 1
    assert body["results"][0]["analysis"]["failure_category"] == "Assertion failure"
    run_id = body["id"]

    history = api_client.get(f"/api/projects/{project_id}/executions")
    assert history.status_code == 200
    assert history.json()[0]["id"] == run_id
    details = api_client.get(f"/api/executions/{run_id}")
    assert details.status_code == 200
    assert details.json()["results"][0]["test_case_id"] == test_case_id
    assert api_client.get(f"/api/executions/{run_id}/results").json()[0]["execution_status"] == "Failed"
    assert api_client.get(f"/api/bug-analysis?project_id={project_id}").json()[0]["failure_category"] == "Assertion failure"

    report = api_client.get(f"/api/reports?project_id={project_id}")
    assert report.status_code == 200
    assert report.json()["projects"][0]["failed"] == 1
    csv_report = api_client.get(f"/api/reports.csv?project_id={project_id}")
    assert csv_report.status_code == 200
    assert "Failure Categories" in csv_report.text
    assert "'=Report Formula" in csv_report.text
    csv_rows = list(csv.DictReader(io.StringIO(csv_report.text)))
    summary_row = next(row for row in csv_rows if row["Record Type"] == "Run Summary")
    result_row = next(row for row in csv_rows if row["Record Type"] == "Test Case Result")
    assert summary_row["Project ID"] == str(project_id)
    assert summary_row["Run ID"] == str(run_id)
    assert result_row["Project ID"] == str(project_id)
    assert result_row["Run ID"] == str(run_id)
    assert result_row["Test Case ID"] == test_case_id
    assert result_row["Scenario"].startswith("Inspect the link 'Docs'")
    assert result_row["Execution Status"] == "Failed"
    assert result_row["Expected Result"] == "The link is unchanged."
    assert result_row["Actual Result"] == "The link differs."
    assert result_row["Test Duration (ms)"] == "8"
    assert "The live href differed." in result_row["Failure Details"]
    assert result_row["Error Message"] == "Assertion failure: test fixture."
    assert api_client.get("/api/dashboard/summary").json()["tests_executed"] == 1
    with backend_main.get_db_connection() as connection:
        case_status = connection.execute(
            "SELECT status FROM test_cases WHERE test_case_id = ?",
            (test_case_id,),
        ).fetchone()["status"]
    assert case_status == "Failed"


def test_dashboard_metrics_aggregate_persisted_runs_across_projects(api_client):
    project_ids = []
    for name in ("Dashboard runs", "Empty project", "Project without runs"):
        response = api_client.post(
            "/api/projects",
            json={"name": name, "url": "https://example.com"},
        )
        assert response.status_code == 201, response.text
        project_ids.append(response.json()["id"])

    run_project_id, empty_project_id, no_history_project_id = project_ids
    with backend_main.get_db_connection() as connection:
        scan_ids = {}
        for project_id in (run_project_id, no_history_project_id):
            cursor = connection.execute(
                """
                INSERT INTO scans (
                    project_id, status, started_at, completed_at, final_url, result_json
                ) VALUES (?, 'completed', 'started', 'completed', ?, '{}')
                """,
                (project_id, "https://example.com/"),
            )
            scan_ids[project_id] = cursor.lastrowid

        for project_id, count in ((run_project_id, 7), (no_history_project_id, 1)):
            for index in range(count):
                connection.execute(
                    """
                    INSERT INTO test_cases (
                        test_case_id, project_id, scan_id, scenario, description,
                        preconditions, steps, test_data, expected_result, priority,
                        category, execution_type, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'Dashboard fixture', '[]', '[]', '{}',
                              'Expected', 'Medium', 'Functional', 'Manual',
                              'Not Executed', 'created', 'updated')
                    """,
                    (
                        f"TC-DASHBOARD-{project_id}-{index}",
                        project_id,
                        scan_ids[project_id],
                        f"Case {index}",
                    ),
                )

        run_values = (
            (5, 1, 1, 1, 1, 1, "2026-01-01T00:00:00Z"),
            (2, 2, 0, 0, 0, 0, "2026-01-02T00:00:00Z"),
        )
        for total, passed, failed, blocked, errors, not_automatable, started_at in run_values:
            connection.execute(
                """
                INSERT INTO execution_runs (
                    project_id, scan_id, status, total_tests, passed, failed,
                    blocked, errors, not_automatable, environment, started_at,
                    completed_at, duration_ms
                ) VALUES (?, ?, 'completed', ?, ?, ?, ?, ?, ?, 'development', ?, ?, 10)
                """,
                (
                    run_project_id,
                    scan_ids[run_project_id],
                    total,
                    passed,
                    failed,
                    blocked,
                    errors,
                    not_automatable,
                    started_at,
                    started_at,
                ),
            )
        connection.commit()

    summary = api_client.get("/api/dashboard/summary")
    assert summary.status_code == 200
    metrics = summary.json()
    assert {
        key: metrics[key]
        for key in (
            "project_count",
            "test_case_count",
            "total_runs",
            "tests_executed",
            "pass_rate",
            "passed",
            "failed",
            "blocked",
            "errors",
        )
    } == {
        "project_count": 3,
        "test_case_count": 8,
        "total_runs": 2,
        "tests_executed": 6,
        "pass_rate": 50.0,
        "passed": 3,
        "failed": 1,
        "blocked": 1,
        "errors": 1,
    }
    assert len(metrics["recent_runs"]) == 2

    report = api_client.get("/api/reports")
    project_rows = {row["project_id"]: row for row in report.json()["projects"]}
    assert project_rows[run_project_id]["total_runs"] == 2
    assert project_rows[run_project_id]["passed"] == 3
    assert project_rows[empty_project_id]["total_runs"] == 0
    assert project_rows[empty_project_id]["total_test_cases"] == 0
    assert project_rows[no_history_project_id]["total_runs"] == 0
    assert project_rows[no_history_project_id]["total_test_cases"] == 1


@pytest.mark.parametrize(
    ("execution_status", "inventory_status"),
    [
        ("Passed", "Passed"),
        ("Failed", "Failed"),
        ("Blocked", "Blocked"),
        ("Error", "Blocked"),
        ("Not Automatable", "Blocked"),
    ],
)
def test_execution_outcome_updates_only_current_run_test_cases(
    api_client, monkeypatch, execution_status, inventory_status
):
    scan_result = {
        "final_url": "https://example.com/",
        "links": [{"text": "Docs", "href": "/docs"}],
        "element_metadata": {
            "links": [
                {
                    "text": "Docs",
                    "href": "/docs",
                    "locator_candidates": [
                        {
                            "strategy": "role",
                            "value": {"role": "link", "name": "Docs"},
                            "match_count": 1,
                            "is_unique": True,
                        }
                    ],
                }
            ]
        },
    }
    project_id, test_case_id = _create_project_and_case(api_client, scan_result)
    with backend_main.get_db_connection() as connection:
        scan_id = connection.execute(
            "SELECT scan_id FROM test_cases WHERE test_case_id = ?",
            (test_case_id,),
        ).fetchone()["scan_id"]
    unselected_test_case_id = "TC-UNSELECTED"
    _insert_unexecuted_case(project_id, scan_id, unselected_test_case_id)
    other_project_id, other_project_case_id = _create_project_and_case(api_client, scan_result)

    async def fake_execution(_url, _cases, **_settings):
        return [_execution_result(test_case_id, execution_status)]

    monkeypatch.setattr(backend_main, "execute_test_cases", fake_execution)
    response = api_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": [test_case_id]},
    )

    assert response.status_code == 201, response.text
    run = response.json()
    assert run["results"][0]["execution_status"] == execution_status
    assert run["results"][0]["execution_run_id"] == run["id"]
    with backend_main.get_db_connection() as connection:
        statuses = {
            row["test_case_id"]: row["status"]
            for row in connection.execute(
                """
                SELECT test_case_id, status FROM test_cases
                WHERE test_case_id IN (?, ?, ?)
                """,
                (test_case_id, unselected_test_case_id, other_project_case_id),
            )
        }
        persisted_results = connection.execute(
            "SELECT COUNT(*) FROM execution_results WHERE execution_run_id = ?",
            (run["id"],),
        ).fetchone()[0]

    assert statuses == {
        test_case_id: inventory_status,
        unselected_test_case_id: "Not Executed",
        other_project_case_id: "Not Executed",
    }
    assert persisted_results == 1
    assert api_client.get(f"/api/projects/{project_id}/executions").json()[0]["id"] == run["id"]
    assert api_client.get(f"/api/projects/{other_project_id}/executions").json() == []


def test_partial_executor_results_are_replaced_with_run_scoped_errors(
    api_client, monkeypatch
):
    scan_result = {
        "final_url": "https://example.com/",
        "links": [{"text": "Docs", "href": "/docs"}],
        "element_metadata": {
            "links": [
                {
                    "text": "Docs",
                    "href": "/docs",
                    "locator_candidates": [
                        {
                            "strategy": "role",
                            "value": {"role": "link", "name": "Docs"},
                            "match_count": 1,
                            "is_unique": True,
                        }
                    ],
                }
            ]
        },
    }
    project_id, first_test_case_id = _create_project_and_case(api_client, scan_result)
    second_test_case_id = "TC-SECOND-SELECTED"
    _clone_test_case(project_id, first_test_case_id, second_test_case_id)

    async def incomplete_execution(_url, _cases, **_settings):
        return [_execution_result(first_test_case_id, "Passed")]

    monkeypatch.setattr(backend_main, "execute_test_cases", incomplete_execution)
    response = api_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": [first_test_case_id, second_test_case_id]},
    )

    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "error"
    assert run["errors"] == 2
    assert {result["execution_status"] for result in run["results"]} == {"Error"}
    assert {result["test_case_id"] for result in run["results"]} == {
        first_test_case_id,
        second_test_case_id,
    }
    with backend_main.get_db_connection() as connection:
        statuses = {
            row["test_case_id"]: row["status"]
            for row in connection.execute(
                "SELECT test_case_id, status FROM test_cases WHERE project_id = ?",
                (project_id,),
            )
        }
        persisted_results = connection.execute(
            "SELECT COUNT(*) FROM execution_results WHERE execution_run_id = ?",
            (run["id"],),
        ).fetchone()[0]
    assert statuses == {
        first_test_case_id: "Blocked",
        second_test_case_id: "Blocked",
    }
    assert persisted_results == 2


def test_later_execution_updates_inventory_without_overwriting_history(
    api_client, monkeypatch
):
    project_id, test_case_id = _create_project_and_case(
        api_client,
        {
            "final_url": "https://example.com/",
            "links": [{"text": "Docs", "href": "/docs"}],
            "element_metadata": {
                "links": [
                    {
                        "text": "Docs",
                        "href": "/docs",
                        "locator_candidates": [
                            {
                                "strategy": "role",
                                "value": {"role": "link", "name": "Docs"},
                                "match_count": 1,
                                "is_unique": True,
                            }
                        ],
                    }
                ]
            },
        },
    )
    outcomes = iter(("Passed", "Failed"))

    async def successive_executions(_url, cases, **_settings):
        status_value = next(outcomes)
        return [_execution_result(cases[0][0]["test_case_id"], status_value)]

    monkeypatch.setattr(backend_main, "execute_test_cases", successive_executions)
    first = api_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": [test_case_id]},
    )
    second = api_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": [test_case_id]},
    )

    assert first.status_code == second.status_code == 201
    first_run_id = first.json()["id"]
    second_run_id = second.json()["id"]
    with backend_main.get_db_connection() as connection:
        inventory_status = connection.execute(
            "SELECT status FROM test_cases WHERE test_case_id = ?",
            (test_case_id,),
        ).fetchone()["status"]
        history = connection.execute(
            """
            SELECT execution_run_id, execution_status
            FROM execution_results
            WHERE test_case_id = ?
            ORDER BY execution_run_id
            """,
            (test_case_id,),
        ).fetchall()

    assert inventory_status == "Failed"
    assert [(row["execution_run_id"], row["execution_status"]) for row in history] == [
        (first_run_id, "Passed"),
        (second_run_id, "Failed"),
    ]


def test_execution_api_validates_project_and_test_case_ids(api_client):
    response = api_client.post(
        "/api/projects/999/executions",
        json={"test_case_ids": ["one", "one"]},
    )
    assert response.status_code == 422

    project = api_client.post(
        "/api/projects",
        json={"name": "App", "url": "https://example.com"},
    )
    project_id = project.json()["id"]
    response = api_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": ["TC-MISSING"]},
    )
    assert response.status_code == 404
    assert api_client.get("/api/projects/999/executions").status_code == 404


def test_execution_api_runs_local_html_fixture_end_to_end(api_client, monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<button data-testid="continue">Continue</button>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    app_url = f"http://127.0.0.1:{server.server_port}/"
    monkeypatch.setattr(test_executor, "validate_destination_url", lambda value: value)
    project = api_client.post(
        "/api/projects",
        json={"name": "Local fixture", "url": app_url},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    scan_result = {
        "final_url": app_url,
        "element_metadata": {
            "buttons": [
                {
                    "tag_name": "button",
                    "element_text": "Continue",
                    "accessible_name": "Continue",
                    "locator_candidates": [
                        {
                            "strategy": "data-testid",
                            "value": "continue",
                            "match_count": 1,
                            "is_unique": True,
                        }
                    ],
                }
            ]
        },
    }
    try:
        with backend_main.get_db_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scans (
                    project_id, status, started_at, completed_at, final_url, result_json
                ) VALUES (?, 'completed', ?, ?, ?, ?)
                """,
                (
                    project_id,
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:01Z",
                    app_url,
                    json.dumps(scan_result),
                ),
            )
            scan_id = cursor.lastrowid
            test_case_id = "TC-LOCAL-FIXTURE"
            connection.execute(
                """
                INSERT INTO test_cases (
                    test_case_id, project_id, scan_id, scenario, description,
                    preconditions, steps, test_data, expected_result, priority,
                    category, execution_type, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_case_id,
                    project_id,
                    scan_id,
                    "Verify button 'Continue' is visible.",
                    "Check the scanned button.",
                    "[]",
                    "[]",
                    json.dumps({"text": "Continue", "metadata": {"type": "button"}}),
                    "The button is visible.",
                    "Medium",
                    "Button Interaction",
                    "Automated",
                    "Not Executed",
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                ),
            )
            connection.commit()

        response = api_client.post(
            f"/api/projects/{project_id}/executions",
            json={"test_case_ids": [test_case_id]},
        )
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()

    assert response.status_code == 201, response.text
    assert response.json()["passed"] == 1
    assert response.json()["results"][0]["execution_status"] == "Passed"
    history = api_client.get(f"/api/projects/{project_id}/executions")
    assert history.json()[0]["total_tests"] == 1


def test_generator_creates_explicit_safe_button_and_input_assertions():
    result = generate_test_cases(
        {
            "element_metadata": {
                "buttons": [
                    {
                        "accessible_name": "Submit",
                        "enabled": False,
                        "locator_candidates": [],
                    }
                ],
                "inputs": [
                    {
                        "name": "email",
                        "required": True,
                        "minlength": "5",
                        "locator_candidates": [],
                    }
                ],
            }
        }
    )
    assertions = [case["test_data"].get("assertion") for case in result["test_cases"]]
    assert {"type": "enabled", "expected": False} in assertions
    assert {"type": "attribute", "attribute": "required", "expected": True} in assertions
    assert {"type": "attribute", "attribute": "minlength", "expected": "5"} in assertions


@pytest.mark.parametrize(
    ("raw_category", "expected_category"),
    [
        ("Locator not found", "Locator not found"),
        ("Locator metadata missing", "Locator not found"),
        ("Ambiguous locator", "Ambiguous locator"),
        ("Element not visible", "Element not visible"),
        ("Element disabled", "Element disabled"),
        ("Navigation failure", "Navigation failure"),
        ("Assertion failure", "Assertion failure"),
        ("Timeout", "Timeout"),
        ("Browser execution error", "Browser execution error"),
    ],
)
def test_failure_analysis_classifies_execution_evidence(raw_category, expected_category):
    finding = analyze_failure(
        {
            "execution_status": "Failed",
            "error_message": "Recorded test failure.",
            "failure_details": {"category": raw_category, "details": "Observed fixture diagnostic."},
        }
    )
    assert finding is not None
    assert finding["failure_category"] == expected_category
    assert "Possible causes" in finding["likely_cause"]
    assert finding["diagnostic_details"] == "Observed fixture diagnostic."
