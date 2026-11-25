import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.test_generator import _validate_case, generate_test_cases, generate_tests

REQUIRED_FIELDS = {
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
}

VALID_PRIORITIES = {"High", "Medium", "Low"}
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
VALID_EXECUTION_TYPES = {"Manual", "Automated"}
STATUS_NOT_EXECUTED = "Not Executed"


def _assert_valid_case(case):
    assert set(case.keys()) >= REQUIRED_FIELDS
    assert isinstance(case["preconditions"], list) and case["preconditions"]
    assert isinstance(case["steps"], list) and case["steps"]
    assert all(isinstance(step, str) and step.strip() for step in case["steps"])
    assert isinstance(case["test_data"], dict)
    assert case["priority"] in VALID_PRIORITIES
    assert case["category"] in VALID_CATEGORIES
    assert case["execution_type"] in VALID_EXECUTION_TYPES
    assert case["status"] == STATUS_NOT_EXECUTED
    assert isinstance(case["test_case_id"], str) and case["test_case_id"]


def test_heading_generation_uses_actual_headings():
    result = generate_test_cases({"headings": ["Welcome", "Pricing"]})
    cases = result["test_cases"]

    assert any(case["category"] == "Functional" and "Welcome" in case["scenario"] for case in cases)
    assert any(case["category"] == "Functional" and "Pricing" in case["scenario"] for case in cases)


def test_button_generation_uses_actual_button_metadata():
    result = generate_test_cases({"buttons": [{"text": "Submit", "type": "submit"}, {"text": "Cancel", "type": "button"}]})
    cases = result["test_cases"]

    assert any(case["category"] == "Button Interaction" and "Submit" in case["scenario"] for case in cases)
    assert any(case["category"] == "Button Interaction" and "Cancel" in case["scenario"] for case in cases)


def test_required_input_positive_and_negative_cases():
    result = generate_test_cases({"inputs": [{"name": "email", "type": "text", "required": True}]})
    cases = result["test_cases"]

    assert any(case["category"] == "Positive" and "required" in case["scenario"].lower() for case in cases)
    assert any(case["category"] == "Input Validation" and "required" in case["scenario"].lower() for case in cases)


def test_optional_input_behavior_is_not_required():
    result = generate_test_cases({"inputs": [{"name": "nickname", "type": "text", "required": False}]})
    cases = result["test_cases"]

    assert any(case["category"] == "Functional" and "optional" in case["scenario"].lower() for case in cases)
    assert not any(case["category"] == "Input Validation" and "required" in case["scenario"].lower() for case in cases)


def test_email_input_invalid_format_is_generated():
    result = generate_test_cases({"inputs": [{"name": "email", "type": "email", "required": True}]})
    cases = result["test_cases"]

    assert any(case["category"] == "Input Validation" and "email" in case["scenario"].lower() for case in cases)
    assert any(case["test_data"].get("invalid_email") == "not-an-email" for case in cases)


def test_form_metadata_generation_uses_actual_fields():
    result = generate_test_cases({
        "forms": [{"id": "signup-form", "method": "post", "action": "/signup", "fields": [{"name": "email", "required": True}, {"name": "name", "required": False}]}]
    })
    cases = result["test_cases"]

    assert any(case["category"] == "Form Validation" and "signup-form" in case["scenario"] for case in cases)
    assert any(case["test_data"].get("required_fields") for case in cases)


def test_malformed_element_metadata_is_handled_safely():
    result = generate_test_cases({
        "buttons": [None, "submit", {"text": "Login"}],
        "links": [123, {"text": "Help", "href": "https://example.com/help"}],
        "inputs": ["bad", {"type": "email", "required": True}],
    })

    assert result["test_cases"]
    assert any(case["category"] == "Button Interaction" for case in result["test_cases"])
    assert any(case["category"] == "Navigation" for case in result["test_cases"])
    assert any(case["category"] == "Input Validation" for case in result["test_cases"])


def test_same_link_text_with_different_destinations():
    result = generate_test_cases({
        "final_url": "https://example.com/app",
        "links": [
            {"text": "Docs", "href": "/docs"},
            {"text": "Docs", "href": "https://other.example.com/docs"},
        ],
    })

    assert result["summary"]["generated_count"] == 2
    assert len({case["test_case_id"] for case in result["test_cases"]}) == 2
    assert {case["test_data"]["destination_type"] for case in result["test_cases"]} == {"relative internal", "different-origin absolute"}


def test_identical_links_are_deduplicated():
    result = generate_test_cases({
        "final_url": "https://example.com/app",
        "links": [
            {"text": "Docs", "href": "/docs"},
            {"text": "Docs", "href": "/docs"},
        ],
    })

    assert result["summary"]["generated_count"] == 1


def test_same_input_name_with_different_constraints():
    result = generate_test_cases({
        "inputs": [
            {"name": "code", "type": "text", "required": True, "minlength": 3, "maxlength": 5},
            {"name": "code", "type": "number", "required": True, "min": 1, "max": 10},
        ]
    })

    ids = [case["test_case_id"] for case in result["test_cases"]]
    assert len(ids) == len(set(ids))
    assert any(case["category"] == "Boundary" for case in result["test_cases"])


def test_ids_differ_when_relevant_test_data_differs():
    first = generate_test_cases({"links": [{"text": "Docs", "href": "/docs"}]})
    second = generate_test_cases({"links": [{"text": "Docs", "href": "https://example.com/docs"}]})

    assert first["test_cases"][0]["test_case_id"] != second["test_cases"][0]["test_case_id"]


def test_ids_remain_stable_for_identical_scan_data():
    scan = {"final_url": "https://example.com/app", "buttons": [{"text": "Submit", "type": "submit"}]}
    first = generate_test_cases(scan)
    second = generate_test_cases(scan)

    assert first["test_cases"][0]["test_case_id"] == second["test_cases"][0]["test_case_id"]


def test_cases_without_structured_executor_metadata_remain_manual():
    result = generate_test_cases({
        "final_url": "https://example.com/app",
        "headings": ["Welcome"],
        "buttons": [{"text": "Continue"}],
        "links": [{"text": "Home", "href": "/"}],
        "inputs": [{"name": "email", "type": "email", "required": True}],
        "forms": [{"id": "contact-form", "fields": [{"name": "email", "required": True}]}],
    })

    assert result["test_cases"]
    assert all(case["execution_type"] == "Manual" for case in result["test_cases"])


def _unique_locator(strategy, value):
    return {
        "strategy": strategy,
        "value": value,
        "match_count": 1,
        "is_unique": True,
    }


def _automation_scan():
    return {
        "final_url": "https://example.com/",
        "headings": ["Welcome"],
        "links": [{"text": "Docs", "href": "/docs"}],
        "inputs": [{"name": "nickname", "type": "text", "required": False}],
        "element_metadata": {
            "headings": [
                {
                    "element_text": "Welcome",
                    "locator_candidates": [
                        _unique_locator("role", {"role": "heading", "name": "Welcome"})
                    ],
                }
            ],
            "links": [
                {
                    "text": "Docs",
                    "href": "/docs",
                    "locator_candidates": [
                        _unique_locator("role", {"role": "link", "name": "Docs"})
                    ],
                }
            ],
            "inputs": [
                {
                    "name": "nickname",
                    "required": False,
                    "readonly": False,
                    "locator_candidates": [_unique_locator("id", "nickname")],
                }
            ],
        },
    }


def test_supported_heading_and_input_attribute_assertions_are_automated():
    cases = generate_test_cases(_automation_scan())["test_cases"]

    heading = next(case for case in cases if case["test_data"].get("heading") == "Welcome")
    required = next(
        case
        for case in cases
        if case["test_data"].get("assertion", {}).get("attribute") == "required"
    )
    readonly = next(
        case
        for case in cases
        if case["test_data"].get("assertion", {}).get("attribute") == "readonly"
    )
    optional_behavior = next(
        case for case in cases if "optional" in case["scenario"].lower()
    )

    assert heading["execution_type"] == "Automated"
    assert required["execution_type"] == "Automated"
    assert required["test_data"]["assertion"] == {
        "type": "attribute",
        "attribute": "required",
        "expected": False,
    }
    assert readonly["execution_type"] == "Automated"
    assert readonly["test_data"]["assertion"] == {
        "type": "attribute",
        "attribute": "readonly",
        "expected": False,
    }
    assert optional_behavior["execution_type"] == "Manual"


def test_link_automation_requires_exact_saved_href_and_unique_locator():
    scan = _automation_scan()
    cases = generate_test_cases(scan)["test_cases"]
    link_case = next(case for case in cases if case["category"] == "Navigation")
    assert link_case["execution_type"] == "Automated"
    assert link_case["test_data"]["href"] == "/docs"

    scan["element_metadata"]["links"][0]["locator_candidates"] = []
    unsupported = generate_test_cases(scan)["test_cases"]
    unsupported_link = next(case for case in unsupported if case["category"] == "Navigation")
    assert unsupported_link["execution_type"] == "Manual"


def test_same_origin_absolute_url_classification():
    result = generate_test_cases({
        "final_url": "https://example.com/app",
        "links": [{"text": "Profile", "href": "https://example.com/profile"}],
    })

    assert result["test_cases"][0]["test_data"]["destination_type"] == "same-origin absolute"


def test_different_origin_absolute_url_classification():
    result = generate_test_cases({
        "final_url": "https://example.com/app",
        "links": [{"text": "About", "href": "https://other.example.com/about"}],
    })

    assert result["test_cases"][0]["test_data"]["destination_type"] == "different-origin absolute"


def test_relative_url_classification():
    result = generate_test_cases({
        "final_url": "https://example.com/app",
        "links": [{"text": "Products", "href": "/products"}],
    })

    assert result["test_cases"][0]["test_data"]["destination_type"] == "relative internal"


def test_missing_or_malformed_link_destinations_are_handled_safely():
    result = generate_test_cases({
        "final_url": "https://example.com/app",
        "links": [{"text": "Missing", "href": ""}, {"text": "Malformed", "href": "http://"}],
    })

    types = {case["test_data"]["destination_type"] for case in result["test_cases"]}
    assert "missing" in types
    assert "malformed" in types


def test_pattern_validation_is_separated_from_boundary_testing():
    result = generate_test_cases({"inputs": [{"name": "code", "type": "text", "pattern": "^[A-Z]{3}$"}]})
    cases = result["test_cases"]

    assert any(case["category"] == "Input Validation" and "pattern" in str(case["test_data"]).lower() for case in cases)
    assert all(case["category"] != "Boundary" for case in cases)


def test_numeric_boundaries_are_based_on_actual_min_max():
    result = generate_test_cases({"inputs": [{"name": "age", "type": "number", "required": True, "min": 1, "max": 10}]})
    cases = result["test_cases"]

    assert any(case["category"] == "Boundary" and "numeric" in case["scenario"].lower() for case in cases)
    assert not any(case["category"] == "Input Validation" and "not-a-number" in str(case["test_data"]).lower() for case in cases)


def test_invalid_cases_are_rejected():
    invalid_case = {
        "test_case_id": "",
        "scenario": "",
        "description": "",
        "preconditions": [],
        "steps": [""],
        "test_data": "invalid",
        "expected_result": "",
        "priority": "Urgent",
        "category": "Unknown",
        "execution_type": "Automated Candidate",
        "status": "Executed",
    }
    valid, issues = _validate_case(invalid_case)

    assert valid is False
    assert issues


def test_empty_scan_returns_empty_generation_summary():
    result = generate_test_cases({})
    assert result["test_cases"] == []
    assert result["summary"]["empty_scan"] is True
    assert result["summary"]["generated_count"] == 0


def test_generate_tests_returns_list_of_cases_for_backward_compatibility():
    cases = generate_tests({"links": [{"text": "Docs", "href": "/docs"}]})

    assert isinstance(cases, list)
    assert cases
    assert cases[0]["status"] == STATUS_NOT_EXECUTED


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    db_dir = tmp_path / "backend_data"
    db_dir.mkdir()
    monkeypatch.setattr(backend_main, "DATABASE_DIR", db_dir)
    monkeypatch.setattr(backend_main, "DATABASE_PATH", db_dir / "testpilot.db")
    backend_main.init_db()
    client = TestClient(backend_main.app)
    yield client
    client.close()


def _create_project_and_scan(api_client, *, result_json=None, project_name="Demo App", url="https://example.com"):
    project_response = api_client.post(
        "/api/projects",
        json={"name": project_name, "url": url, "description": "Test application"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    with backend_main.get_db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO scans (project_id, status, started_at, completed_at, page_title, final_url, result_json, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "completed",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:01Z",
                "Example",
                "https://example.com/home",
                json.dumps(result_json or {}, ensure_ascii=False),
                None,
            ),
        )
        connection.commit()
        scan_id = cursor.lastrowid

    return project_id, scan_id


def test_database_table_creation(api_client):
    with backend_main.get_db_connection() as connection:
        rows = connection.execute(
            "PRAGMA table_info(test_cases)"
        ).fetchall()

    names = {row[1] for row in rows}
    assert {"id", "test_case_id", "project_id", "scan_id", "scenario", "description", "preconditions", "steps", "test_data", "expected_result", "priority", "category", "execution_type", "status", "created_at", "updated_at"} <= names


def test_execution_type_schema_migration_preserves_ids_and_execution_history(tmp_path):
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE applications (id INTEGER PRIMARY KEY);
        CREATE TABLE scans (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            FOREIGN KEY(project_id) REFERENCES applications(id)
        );
        CREATE TABLE test_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_case_id TEXT NOT NULL UNIQUE,
            project_id INTEGER NOT NULL,
            scan_id INTEGER NOT NULL,
            scenario TEXT NOT NULL,
            description TEXT NOT NULL,
            preconditions TEXT NOT NULL,
            steps TEXT NOT NULL,
            test_data TEXT NOT NULL,
            expected_result TEXT NOT NULL,
            priority TEXT NOT NULL,
            category TEXT NOT NULL,
            execution_type TEXT NOT NULL CHECK(execution_type = 'Manual'),
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES applications(id),
            FOREIGN KEY(scan_id) REFERENCES scans(id)
        );
        CREATE TABLE execution_runs (id INTEGER PRIMARY KEY);
        CREATE TABLE execution_results (
            id INTEGER PRIMARY KEY,
            execution_run_id INTEGER NOT NULL,
            test_case_id TEXT NOT NULL,
            execution_status TEXT NOT NULL,
            FOREIGN KEY(execution_run_id) REFERENCES execution_runs(id),
            FOREIGN KEY(test_case_id) REFERENCES test_cases(test_case_id)
        );
        INSERT INTO applications (id) VALUES (4);
        INSERT INTO scans (id, project_id) VALUES (9, 4);
        INSERT INTO test_cases (
            id, test_case_id, project_id, scan_id, scenario, description,
            preconditions, steps, test_data, expected_result, priority, category,
            execution_type, status, created_at, updated_at
        ) VALUES (
            12, 'TC-LEGACY', 4, 9, 'Saved case', 'Preserve this record',
            '[]', '[]', '{"assertion":{"type":"attribute"}}', 'Expected',
            'High', 'Functional', 'Manual', 'Passed', 'created', 'updated'
        );
        INSERT INTO execution_runs (id) VALUES (21);
        INSERT INTO execution_results (
            id, execution_run_id, test_case_id, execution_status
        ) VALUES (31, 21, 'TC-LEGACY', 'Passed');
        """
    )
    connection.commit()

    backend_main._migrate_test_case_execution_type(connection)

    case = connection.execute(
        "SELECT * FROM test_cases WHERE test_case_id = 'TC-LEGACY'"
    ).fetchone()
    history = connection.execute(
        "SELECT * FROM execution_results WHERE id = 31"
    ).fetchone()
    assert case["id"] == 12
    assert case["execution_type"] == "Manual"
    assert case["status"] == "Passed"
    assert case["test_data"] == '{"assertion":{"type":"attribute"}}'
    assert history["execution_run_id"] == 21
    assert history["test_case_id"] == "TC-LEGACY"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE test_cases SET execution_type = 'NotSupported' WHERE id = 12"
        )
    connection.rollback()
    connection.close()


def test_generate_and_persist_test_cases(api_client):
    project_id, scan_id = _create_project_and_scan(
        api_client,
        result_json={
            "final_url": "https://example.com/home",
            "links": [{"text": "Docs", "href": "/docs"}],
            "buttons": [{"text": "Submit", "type": "submit"}],
            "inputs": [{"name": "email", "type": "email", "required": True}],
        },
    )

    response = api_client.post(f"/api/projects/{project_id}/scans/{scan_id}/test-cases/generate")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["saved_count"] >= 1
    assert body["test_cases"]
    assert all(case["status"] == "Not Executed" for case in body["test_cases"])


def test_automated_type_is_persisted_and_returned_by_inventory_api(api_client):
    project_id, scan_id = _create_project_and_scan(
        api_client,
        result_json=_automation_scan(),
    )
    generated = api_client.post(
        f"/api/projects/{project_id}/scans/{scan_id}/test-cases/generate"
    )

    assert generated.status_code == 200, generated.text
    automated_case = next(
        case
        for case in generated.json()["test_cases"]
        if case["test_data"].get("heading") == "Welcome"
    )
    assert automated_case["execution_type"] == "Automated"

    inventory = api_client.get(f"/api/projects/{project_id}/test-cases")
    assert inventory.status_code == 200
    inventory_case = next(
        case
        for case in inventory.json()
        if case["test_case_id"] == automated_case["test_case_id"]
    )
    assert inventory_case["execution_type"] == "Automated"


def test_targeted_backfill_preserves_other_cases_statuses_and_execution_history(api_client):
    project_id, scan_id = _create_project_and_scan(
        api_client,
        result_json=_automation_scan(),
    )
    generated = api_client.post(
        f"/api/projects/{project_id}/scans/{scan_id}/test-cases/generate"
    )
    assert generated.status_code == 200, generated.text
    target_ids = {
        case["test_case_id"] for case in generated.json()["test_cases"]
    }
    assert target_ids

    with backend_main.get_db_connection() as connection:
        connection.execute(
            """
            UPDATE test_cases
            SET execution_type = 'Manual',
                status = CASE WHEN test_case_id = ? THEN 'Failed' ELSE status END
            WHERE project_id = ? AND scan_id = ?
            """,
            (next(iter(target_ids)), project_id, scan_id),
        )
        other_scan_id = connection.execute(
            """
            INSERT INTO scans (
                project_id, status, started_at, completed_at, final_url, result_json
            ) VALUES (?, 'completed', 'created', 'completed', ?, ?)
            """,
            (project_id, "https://example.com/other", json.dumps(_automation_scan())),
        ).lastrowid
        unrelated_id = "TC-OTHER-SCAN"
        connection.execute(
            """
            INSERT INTO test_cases (
                test_case_id, project_id, scan_id, scenario, description,
                preconditions, steps, test_data, expected_result, priority,
                category, execution_type, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'Unrelated', 'Keep unchanged', '[]', '[]', '{}',
                      'Expected', 'Low', 'Functional', 'Manual',
                      'Not Executed', 'created', 'updated')
            """,
            (unrelated_id, project_id, other_scan_id),
        )
        history_case_id = next(iter(target_ids))
        execution_run_id = connection.execute(
            """
            INSERT INTO execution_runs (
                project_id, scan_id, status, total_tests, passed, started_at, completed_at
            ) VALUES (?, ?, 'completed', 1, 1, 'started', 'completed')
            """,
            (project_id, scan_id),
        ).lastrowid
        connection.execute(
            """
            INSERT INTO execution_results (
                execution_run_id, test_case_id, execution_status,
                action_performed, expected_result, actual_result, duration_ms,
                started_at, completed_at
            ) VALUES (?, ?, 'Passed', 'Inspect heading', 'Expected', 'Observed',
                      1, 'started', 'completed')
            """,
            (execution_run_id, history_case_id),
        )
        connection.commit()

    counts = backend_main.backfill_execution_types(project_id, scan_id)

    with backend_main.get_db_connection() as connection:
        target_rows = connection.execute(
            """
            SELECT id, test_case_id, execution_type, status
            FROM test_cases WHERE project_id = ? AND scan_id = ?
            """,
            (project_id, scan_id),
        ).fetchall()
        unrelated = connection.execute(
            "SELECT execution_type, status FROM test_cases WHERE test_case_id = ?",
            (unrelated_id,),
        ).fetchone()
        history = connection.execute(
            """
            SELECT execution_run_id, test_case_id, execution_status
            FROM execution_results WHERE execution_run_id = ?
            """,
            (execution_run_id,),
        ).fetchall()

    assert counts["Automated"] > 0
    assert counts["Manual"] > 0
    assert {row["test_case_id"] for row in target_rows} == target_ids
    assert {row["execution_type"] for row in target_rows} == {"Automated", "Manual"}
    assert next(row for row in target_rows if row["test_case_id"] == history_case_id)["status"] == "Failed"
    assert unrelated["execution_type"] == "Manual"
    assert unrelated["status"] == "Not Executed"
    assert len(history) == 1
    assert history[0]["execution_run_id"] == execution_run_id
    assert history[0]["test_case_id"] == history_case_id
    assert history[0]["execution_status"] == "Passed"


def test_retrieval_by_project_and_test_case_id(api_client):
    project_id, scan_id = _create_project_and_scan(
        api_client,
        result_json={"final_url": "https://example.com/home", "links": [{"text": "Docs", "href": "/docs"}]},
    )
    generate_response = api_client.post(f"/api/projects/{project_id}/scans/{scan_id}/test-cases/generate")
    assert generate_response.status_code == 200

    list_response = api_client.get(f"/api/projects/{project_id}/test-cases")
    assert list_response.status_code == 200
    assert list_response.json()

    test_case_id = list_response.json()[0]["test_case_id"]
    get_response = api_client.get(f"/api/test-cases/{test_case_id}")
    assert get_response.status_code == 200
    assert get_response.json()["test_case_id"] == test_case_id


def test_duplicate_prevention_for_same_scan(api_client):
    project_id, scan_id = _create_project_and_scan(
        api_client,
        result_json={"final_url": "https://example.com/home", "links": [{"text": "Docs", "href": "/docs"}]},
    )

    first = api_client.post(f"/api/projects/{project_id}/scans/{scan_id}/test-cases/generate")
    second = api_client.post(f"/api/projects/{project_id}/scans/{scan_id}/test-cases/generate")

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(second.json()["test_cases"]) == len(first.json()["test_cases"])
    assert second.json()["summary"]["duplicate_count"] >= 0

    with backend_main.get_db_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM test_cases WHERE project_id = ? AND scan_id = ?",
            (project_id, scan_id),
        ).fetchone()[0]
    assert count == len(first.json()["test_cases"])


def test_identical_generated_cases_are_project_scoped_and_legacy_ids_are_preserved(api_client):
    scan_metadata = {
        "final_url": "https://example.com/",
        "links": [{"text": "Learn more", "href": "https://iana.org/help/example-domains"}],
    }
    generated_case = generate_test_cases(scan_metadata)["test_cases"][0]

    with backend_main.get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO applications (id, name, url, created_at, updated_at)
            VALUES (5, 'Legacy project', 'https://example.com', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO applications (id, name, url, created_at, updated_at)
            VALUES (6, 'New project', 'https://example.com', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """
        )
        for scan_id, project_id in ((3, 5), (8, 6)):
            connection.execute(
                """
                INSERT INTO scans (
                    id, project_id, status, started_at, completed_at, final_url, result_json
                ) VALUES (?, ?, 'completed', ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    project_id,
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:01Z",
                    scan_metadata["final_url"],
                    json.dumps(scan_metadata),
                ),
            )
        connection.execute(
            """
            INSERT INTO test_cases (
                test_case_id, project_id, scan_id, scenario, description,
                preconditions, steps, test_data, expected_result, priority,
                category, execution_type, status, created_at, updated_at
            ) VALUES (?, 5, 3, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Blocked', ?, ?)
            """,
            (
                generated_case["test_case_id"],
                generated_case["scenario"],
                generated_case["description"],
                json.dumps(generated_case["preconditions"]),
                json.dumps(generated_case["steps"]),
                json.dumps(generated_case["test_data"]),
                generated_case["expected_result"],
                generated_case["priority"],
                generated_case["category"],
                generated_case["execution_type"],
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.commit()

    legacy_generation = api_client.post("/api/projects/5/scans/3/test-cases/generate")
    assert legacy_generation.status_code == 200, legacy_generation.text
    legacy_body = legacy_generation.json()
    assert legacy_body["project_id"] == legacy_body["summary"]["project_id"] == 5
    assert legacy_body["scan_id"] == legacy_body["summary"]["scan_id"] == 3
    assert legacy_body["summary"]["generated_count"] == 1
    assert legacy_body["summary"]["saved_count"] == 1
    assert legacy_body["summary"]["inserted_count"] == 0
    assert legacy_body["summary"]["duplicate_count"] == 1
    assert legacy_body["test_cases"][0]["test_case_id"] == generated_case["test_case_id"]
    assert legacy_body["test_cases"][0]["persistence_status"] == "duplicate"

    project_generation = api_client.post("/api/projects/6/scans/8/test-cases/generate")
    assert project_generation.status_code == 200, project_generation.text
    project_body = project_generation.json()
    project_case_id = project_body["test_cases"][0]["test_case_id"]
    assert project_body["project_id"] == project_body["summary"]["project_id"] == 6
    assert project_body["scan_id"] == project_body["summary"]["scan_id"] == 8
    assert project_body["summary"]["generated_count"] == 1
    assert project_body["summary"]["saved_count"] == 1
    assert project_body["summary"]["inserted_count"] == 1
    assert project_body["summary"]["duplicate_count"] == 0
    assert project_case_id != generated_case["test_case_id"]
    assert project_body["test_cases"][0]["persistence_status"] == "inserted"

    repeated = api_client.post("/api/projects/6/scans/8/test-cases/generate")
    assert repeated.status_code == 200, repeated.text
    repeated_body = repeated.json()
    assert repeated_body["summary"]["inserted_count"] == 0
    assert repeated_body["summary"]["duplicate_count"] == 1
    assert repeated_body["test_cases"][0]["test_case_id"] == project_case_id
    assert repeated_body["test_cases"][0]["persistence_status"] == "duplicate"

    with backend_main.get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO scans (
                id, project_id, status, started_at, completed_at, final_url, result_json
            ) VALUES (9, 6, 'completed', ?, ?, ?, ?)
            """,
            (
                "2026-01-02T00:00:00Z",
                "2026-01-02T00:00:01Z",
                scan_metadata["final_url"],
                json.dumps(scan_metadata),
            ),
        )
        connection.commit()
    later_scan = api_client.post("/api/projects/6/scans/9/test-cases/generate")
    assert later_scan.status_code == 200, later_scan.text
    assert later_scan.json()["summary"]["inserted_count"] == 0
    assert later_scan.json()["summary"]["duplicate_count"] == 1
    assert later_scan.json()["test_cases"][0]["test_case_id"] == project_case_id

    legacy_cases = api_client.get("/api/projects/5/test-cases").json()
    project_cases = api_client.get("/api/projects/6/test-cases").json()
    assert [case["test_case_id"] for case in legacy_cases] == [generated_case["test_case_id"]]
    assert [case["test_case_id"] for case in project_cases] == [project_case_id]

    legacy_status = api_client.patch(
        f"/api/test-cases/{generated_case['test_case_id']}/status",
        json={"status": "Failed"},
    )
    project_status = api_client.patch(
        f"/api/test-cases/{project_case_id}/status",
        json={"status": "Passed"},
    )
    assert legacy_status.status_code == project_status.status_code == 200
    assert legacy_status.json()["status"] == "Failed"
    assert project_status.json()["status"] == "Passed"
    assert api_client.get(f"/api/projects/5/test-cases").json()[0]["status"] == "Failed"
    assert api_client.get(f"/api/projects/6/test-cases").json()[0]["status"] == "Passed"


def test_invalid_project_or_scan_ids(api_client):
    project_response = api_client.post(
        "/api/projects",
        json={"name": "App", "url": "https://example.com", "description": "desc"},
    )
    project_id = project_response.json()["id"]
    response = api_client.post(f"/api/projects/{project_id + 999}/scans/1/test-cases/generate")
    assert response.status_code == 404

    with backend_main.get_db_connection() as connection:
        connection.execute(
            "INSERT INTO scans (project_id, status, started_at, completed_at, page_title, final_url, result_json, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, "completed", "2024-01-01T00:00:00Z", "2024-01-01T00:00:01Z", "Title", "https://example.com/home", json.dumps({"links": []}), None),
        )
        connection.commit()
        missing_scan_id = connection.execute("SELECT MAX(id) FROM scans").fetchone()[0] + 1

    response = api_client.post(f"/api/projects/{project_id}/scans/{missing_scan_id}/test-cases/generate")
    assert response.status_code == 404


def test_scan_project_ownership_validation(api_client):
    first_project = api_client.post("/api/projects", json={"name": "Project A", "url": "https://example.com", "description": "One"})
    second_project = api_client.post("/api/projects", json={"name": "Project B", "url": "https://example.org", "description": "Two"})

    first_project_id = first_project.json()["id"]
    second_project_id = second_project.json()["id"]

    with backend_main.get_db_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO scans (project_id, status, started_at, completed_at, page_title, final_url, result_json, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (first_project_id, "completed", "2024-01-01T00:00:00Z", "2024-01-01T00:00:01Z", "Title", "https://example.com/home", json.dumps({"links": [{"text": "Docs", "href": "/docs"}]}), None),
        )
        scan_id = cursor.lastrowid

    response = api_client.post(f"/api/projects/{second_project_id}/scans/{scan_id}/test-cases/generate")
    assert response.status_code == 400


def test_invalid_status_rejected_and_valid_status_updates(api_client):
    project_id, scan_id = _create_project_and_scan(
        api_client,
        result_json={"final_url": "https://example.com/home", "links": [{"text": "Docs", "href": "/docs"}]},
    )
    generate_response = api_client.post(f"/api/projects/{project_id}/scans/{scan_id}/test-cases/generate")
    assert generate_response.status_code == 200
    test_case_id = generate_response.json()["test_cases"][0]["test_case_id"]

    bad_status = api_client.patch(f"/api/test-cases/{test_case_id}/status", json={"status": "Unknown"})
    assert bad_status.status_code in {400, 422}

    good_status = api_client.patch(f"/api/test-cases/{test_case_id}/status", json={"status": "Passed"})
    assert good_status.status_code == 200
    assert good_status.json()["status"] == "Passed"
    assert good_status.json()["execution_type"] == "Manual"


def test_existing_endpoint_regression(api_client):
    response = api_client.get("/api/projects")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    create_response = api_client.post(
        "/api/projects",
        json={"name": "Regression", "url": "https://example.com", "description": "Keep app endpoints working"},
    )
    assert create_response.status_code == 201
