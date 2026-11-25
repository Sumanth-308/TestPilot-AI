import json

import pytest
from fastapi.testclient import TestClient

from backend import main as backend_main
from backend import test_executor


@pytest.fixture
def settings_client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(backend_main, "DATABASE_DIR", data_dir)
    monkeypatch.setattr(backend_main, "DATABASE_PATH", data_dir / "testpilot.db")
    monkeypatch.setattr(backend_main, "validate_destination_url", lambda value: value)
    monkeypatch.setattr(test_executor, "validate_destination_url", lambda value: value)
    backend_main.init_db()
    client = TestClient(backend_main.app)
    yield client
    client.close()


def _create_project(client: TestClient) -> int:
    response = client.post(
        "/api/projects",
        json={"name": "Settings project", "url": "https://app.example.test"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _update_payload(settings: dict) -> dict:
    return {
        key: value
        for key, value in settings.items()
        if key not in {"configured_environments", "updated_at"}
    }


def test_settings_are_persisted_validated_and_reset(settings_client):
    project_id = _create_project(settings_client)
    defaults = settings_client.get("/api/settings")
    assert defaults.status_code == 200
    body = defaults.json()
    body.update(
        {
            "workspace_name": "Release workspace",
            "default_environment": "staging",
            "default_project_id": project_id,
            "environment_urls": {
                str(project_id): {"staging": "https://staging.example.test"}
            },
            "execution_timeout_ms": 15000,
            "max_tests_per_run": 12,
            "quality_gate_pass_rate_threshold": 92,
            "quality_gate_failure_threshold": 1,
        }
    )

    saved = settings_client.put("/api/settings", json=_update_payload(body))
    assert saved.status_code == 200, saved.text
    reloaded = settings_client.get("/api/settings").json()
    assert reloaded["workspace_name"] == "Release workspace"
    assert reloaded["default_environment"] == "staging"
    assert reloaded["default_project_id"] == project_id
    assert reloaded["environment_urls"][str(project_id)] == {
        "staging": "https://staging.example.test/"
    }
    assert reloaded["configured_environments"][str(project_id)] == ["staging"]
    assert reloaded["execution_timeout_ms"] == 15000
    assert reloaded["max_tests_per_run"] == 12

    invalid_timeout = {**body, "execution_timeout_ms": 0}
    assert settings_client.put("/api/settings", json=_update_payload(invalid_timeout)).status_code == 422
    invalid_url = {
        **body,
        "environment_urls": {
            str(project_id): {"staging": "https://user:password@staging.example.test"}
        },
    }
    assert settings_client.put("/api/settings", json=_update_payload(invalid_url)).status_code == 422
    query_url = {
        **body,
        "environment_urls": {
            str(project_id): {"staging": "https://staging.example.test/?token=secret"}
        },
    }
    assert settings_client.put("/api/settings", json=_update_payload(query_url)).status_code == 422
    unknown_project = {**body, "default_project_id": 999}
    assert settings_client.put("/api/settings", json=_update_payload(unknown_project)).status_code == 422

    reset = settings_client.post("/api/settings/reset")
    assert reset.status_code == 200
    assert reset.json()["workspace_name"] == "TestPilot AI"
    assert reset.json()["default_environment"] == "development"
    assert reset.json()["default_project_id"] is None


def test_settings_apply_environment_timeout_and_quality_gate_to_execution(
    settings_client, monkeypatch
):
    project_id = _create_project(settings_client)
    with backend_main.get_db_connection() as connection:
        scan_cursor = connection.execute(
            """
            INSERT INTO scans (project_id, status, started_at, completed_at, result_json)
            VALUES (?, 'completed', '2026-01-01T00:00:00Z', '2026-01-01T00:00:01Z', ?)
            """,
            (project_id, json.dumps({"element_metadata": {}})),
        )
        scan_id = scan_cursor.lastrowid
        connection.execute(
            """
            INSERT INTO test_cases (
                test_case_id, project_id, scan_id, scenario, description,
                preconditions, steps, test_data, expected_result, priority,
                category, execution_type, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TC-SETTINGS-WORKFLOW",
                project_id,
                scan_id,
                "Verify a saved control.",
                "Settings workflow integration test.",
                "[]",
                "[]",
                json.dumps({"element_kind": "button"}),
                "Control exists.",
                "Low",
                "Button Interaction",
                "Manual",
                "Not Executed",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )

    captured = {}
    execution_status = {"value": "Passed"}

    async def fake_execution(url, cases, **options):
        captured.update(url=url, cases=cases, options=options)
        return [
            {
                "test_case_id": "TC-SETTINGS-WORKFLOW",
                "execution_status": execution_status["value"],
                "action_performed": "Inspect the saved control.",
                "assertion_performed": "The control exists.",
                "expected_result": "Control exists.",
                "actual_result": "The control exists.",
                "error_message": None,
                "failure_details": None,
                "duration_ms": 4,
                "screenshot_path": None,
                "started_at": "2026-01-01T00:00:01Z",
                "completed_at": "2026-01-01T00:00:01Z",
            }
        ]

    monkeypatch.setattr(backend_main, "execute_test_cases", fake_execution)
    settings = settings_client.get("/api/settings").json()
    settings.update(
        {
            "default_environment": "staging",
            "environment_urls": {
                str(project_id): {"staging": "https://staging.example.test"}
            },
            "execution_timeout_ms": 17777,
            "max_tests_per_run": 1,
            "quality_gate_pass_rate_threshold": 90,
            "quality_gate_failure_threshold": 0,
        }
    )
    assert settings_client.put("/api/settings", json=_update_payload(settings)).status_code == 200

    response = settings_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": ["TC-SETTINGS-WORKFLOW"]},
    )
    assert response.status_code == 201, response.text
    run = response.json()
    assert captured["url"] == "https://staging.example.test/"
    assert captured["options"] == {"timeout_ms": 17777, "max_test_cases": 1}
    assert run["environment"] == "staging"
    assert run["quality_gate_passed"] is True
    assert run["quality_gate_pass_rate"] == 100

    execution_status["value"] = "Failed"
    settings["quality_gate_pass_rate_threshold"] = 0
    settings["quality_gate_failure_threshold"] = 0
    assert settings_client.put("/api/settings", json=_update_payload(settings)).status_code == 200
    failed_run = settings_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": ["TC-SETTINGS-WORKFLOW"]},
    )
    assert failed_run.status_code == 201
    assert failed_run.json()["quality_gate_passed"] is False
    assert failed_run.json()["quality_gate_pass_rate"] == 0

    settings["quality_gate_failure_threshold"] = 1
    assert settings_client.put("/api/settings", json=_update_payload(settings)).status_code == 200
    tolerated_run = settings_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": ["TC-SETTINGS-WORKFLOW"]},
    )
    assert tolerated_run.status_code == 201
    assert tolerated_run.json()["quality_gate_passed"] is True

    too_many = settings_client.post(
        f"/api/projects/{project_id}/executions",
        json={"test_case_ids": ["TC-SETTINGS-WORKFLOW", "TC-SETTINGS-WORKFLOW-2"]},
    )
    assert too_many.status_code == 422


def test_scan_uses_the_active_environment_url(settings_client, monkeypatch):
    project_id = _create_project(settings_client)
    scanned_urls = []

    async def fake_scan(url):
        scanned_urls.append(url)
        return {"page_title": "Staging", "final_url": url, "element_metadata": {}}

    monkeypatch.setattr(backend_main, "scan_application_url", fake_scan)
    settings = settings_client.get("/api/settings").json()
    settings.update(
        {
            "default_environment": "staging",
            "environment_urls": {
                str(project_id): {"staging": "https://staging.example.test"}
            },
        }
    )
    assert settings_client.put("/api/settings", json=_update_payload(settings)).status_code == 200
    persisted = settings_client.get("/api/settings").json()
    assert persisted["default_environment"] == "staging"
    assert persisted["environment_urls"][str(project_id)] == {
        "staging": "https://staging.example.test/"
    }

    response = settings_client.post(f"/api/projects/{project_id}/scans")
    assert response.status_code == 200
    assert scanned_urls == ["https://staging.example.test/"]


def test_existing_execution_run_schema_is_migrated_without_data_loss(tmp_path, monkeypatch):
    data_dir = tmp_path / "legacy"
    data_dir.mkdir()
    database_path = data_dir / "testpilot.db"
    monkeypatch.setattr(backend_main, "DATABASE_DIR", data_dir)
    monkeypatch.setattr(backend_main, "DATABASE_PATH", database_path)
    import sqlite3

    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE execution_runs (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            scan_id INTEGER,
            status TEXT NOT NULL,
            total_tests INTEGER NOT NULL,
            passed INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            blocked INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            not_automatable INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            duration_ms INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        INSERT INTO execution_runs (
            id, project_id, status, total_tests, started_at
        ) VALUES (9, 5, 'completed', 2, '2026-01-01T00:00:00Z')
        """
    )
    connection.commit()
    connection.close()

    backend_main.init_db()
    with backend_main.get_db_connection() as migrated:
        run = migrated.execute("SELECT * FROM execution_runs WHERE id = 9").fetchone()
        columns = {row["name"] for row in migrated.execute("PRAGMA table_info(execution_runs)")}
    assert run["project_id"] == 5
    assert run["total_tests"] == 2
    assert run["environment"] == "development"
    assert {
        "quality_gate_passed",
        "quality_gate_pass_rate",
        "quality_gate_pass_rate_threshold",
        "quality_gate_failure_threshold",
    }.issubset(columns)
