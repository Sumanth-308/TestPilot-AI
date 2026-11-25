import csv
import io
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

try:
    from backend.scanner import scan_application_url, validate_destination_url
    from backend.test_generator import generate_test_cases
    from backend.test_executor import (
        assess_automation,
        classify_execution_type,
        execute_test_cases,
        validate_execution_url,
    )
    from backend.bug_analysis import analyze_failure
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from scanner import scan_application_url, validate_destination_url
    from test_generator import generate_test_cases
    from test_executor import (
        assess_automation,
        classify_execution_type,
        execute_test_cases,
        validate_execution_url,
    )
    from bug_analysis import analyze_failure

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "data"
DATABASE_PATH = DATABASE_DIR / "testpilot.db"
logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _create_test_cases_table(connection: sqlite3.Connection, table_name: str) -> None:
    if table_name not in {"test_cases", "test_cases_new"}:
        raise ValueError("Invalid test-case table name")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
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
            priority TEXT NOT NULL CHECK(priority IN ('High', 'Medium', 'Low')),
            category TEXT NOT NULL CHECK(category IN (
                'Positive', 'Negative', 'Boundary', 'Input Validation',
                'Form Validation', 'Navigation', 'Button Interaction', 'Functional'
            )),
            execution_type TEXT NOT NULL CHECK(execution_type IN ('Manual', 'Automated')),
            status TEXT NOT NULL CHECK(status IN ('Not Executed', 'Passed', 'Failed', 'Blocked')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES applications(id) ON DELETE CASCADE,
            FOREIGN KEY(scan_id) REFERENCES scans(id) ON DELETE CASCADE
        )
        """
    )


def _migrate_test_case_execution_type(connection: sqlite3.Connection) -> None:
    schema = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'test_cases'"
    ).fetchone()
    if schema is None or "Automated" in schema["sql"]:
        return

    columns = (
        "id", "test_case_id", "project_id", "scan_id", "scenario", "description",
        "preconditions", "steps", "test_data", "expected_result", "priority",
        "category", "execution_type", "status", "created_at", "updated_at",
    )
    column_list = ", ".join(columns)
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE IF EXISTS test_cases_new")
        _create_test_cases_table(connection, "test_cases_new")
        connection.execute(
            f"""
            INSERT INTO test_cases_new ({column_list})
            SELECT {column_list} FROM test_cases
            """
        )
        connection.execute("DROP TABLE test_cases")
        connection.execute("ALTER TABLE test_cases_new RENAME TO test_cases")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise sqlite3.IntegrityError("Test-case schema migration found foreign-key violations")
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def init_db() -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                page_title TEXT,
                final_url TEXT,
                result_json TEXT,
                error_message TEXT,
                FOREIGN KEY(project_id) REFERENCES applications(id) ON DELETE CASCADE
            )
            """
        )
        _create_test_cases_table(connection, "test_cases")
        _migrate_test_case_execution_type(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_scans_project_id ON scans (project_id, started_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_test_cases_project_id ON test_cases (project_id, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_test_cases_scan_id ON test_cases (scan_id, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_test_cases_status ON test_cases (status, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_test_cases_category ON test_cases (category, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_test_cases_priority ON test_cases (priority, created_at DESC)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                scan_id INTEGER,
                status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'error')),
                total_tests INTEGER NOT NULL CHECK(total_tests >= 0),
                passed INTEGER NOT NULL DEFAULT 0 CHECK(passed >= 0),
                failed INTEGER NOT NULL DEFAULT 0 CHECK(failed >= 0),
                blocked INTEGER NOT NULL DEFAULT 0 CHECK(blocked >= 0),
                errors INTEGER NOT NULL DEFAULT 0 CHECK(errors >= 0),
                not_automatable INTEGER NOT NULL DEFAULT 0 CHECK(not_automatable >= 0),
                environment TEXT NOT NULL DEFAULT 'development',
                quality_gate_passed INTEGER,
                quality_gate_pass_rate REAL,
                quality_gate_pass_rate_threshold REAL,
                quality_gate_failure_threshold INTEGER,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_ms INTEGER NOT NULL DEFAULT 0 CHECK(duration_ms >= 0),
                FOREIGN KEY(project_id) REFERENCES applications(id) ON DELETE CASCADE,
                FOREIGN KEY(scan_id) REFERENCES scans(id) ON DELETE SET NULL
            )
            """
        )
        execution_run_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(execution_runs)")
        }
        for column, definition in (
            ("environment", "TEXT NOT NULL DEFAULT 'development'"),
            ("quality_gate_passed", "INTEGER"),
            ("quality_gate_pass_rate", "REAL"),
            ("quality_gate_pass_rate_threshold", "REAL"),
            ("quality_gate_failure_threshold", "INTEGER"),
        ):
            if column not in execution_run_columns:
                connection.execute(f"ALTER TABLE execution_runs ADD COLUMN {column} {definition}")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_run_id INTEGER NOT NULL,
                test_case_id TEXT NOT NULL,
                execution_status TEXT NOT NULL CHECK(execution_status IN (
                    'Passed', 'Failed', 'Blocked', 'Error', 'Not Automatable'
                )),
                action_performed TEXT NOT NULL,
                assertion_performed TEXT,
                expected_result TEXT,
                actual_result TEXT,
                error_message TEXT,
                failure_details TEXT,
                duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
                screenshot_path TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                FOREIGN KEY(execution_run_id) REFERENCES execution_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(test_case_id) REFERENCES test_cases(test_case_id) ON DELETE CASCADE,
                UNIQUE(execution_run_id, test_case_id)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_runs_project_started ON execution_runs (project_id, started_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_runs_scan_id ON execution_runs (scan_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_results_run_status ON execution_results (execution_run_id, execution_status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_results_case_id ON execution_results (test_case_id)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                workspace_name TEXT NOT NULL CHECK(length(trim(workspace_name)) BETWEEN 1 AND 80),
                default_environment TEXT NOT NULL CHECK(default_environment IN (
                    'development', 'staging', 'production'
                )),
                default_project_id INTEGER,
                environment_urls TEXT NOT NULL DEFAULT '{}',
                execution_timeout_ms INTEGER NOT NULL CHECK(execution_timeout_ms BETWEEN 250 AND 60000),
                max_tests_per_run INTEGER NOT NULL CHECK(max_tests_per_run BETWEEN 1 AND 100),
                quality_gate_pass_rate_threshold REAL NOT NULL
                    CHECK(quality_gate_pass_rate_threshold BETWEEN 0 AND 100),
                quality_gate_failure_threshold INTEGER NOT NULL
                    CHECK(quality_gate_failure_threshold BETWEEN 0 AND 1000),
                updated_at TEXT NOT NULL,
                FOREIGN KEY(default_project_id) REFERENCES applications(id) ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO workspace_settings (
                id, workspace_name, default_environment, default_project_id,
                environment_urls, execution_timeout_ms, max_tests_per_run,
                quality_gate_pass_rate_threshold, quality_gate_failure_threshold,
                updated_at
            ) VALUES (1, 'TestPilot AI', 'development', NULL, '{}', 10000, 100, 80, 0, ?)
            """,
            (utc_now_iso(),),
        )
        connection.commit()


def serialize_application(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "url": row["url"],
        "description": row["description"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_application_or_404(project_id: int) -> dict:
    try:
        with get_db_connection() as connection:
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (project_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while retrieving application") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")

    return serialize_application(row)


def serialize_scan(row: sqlite3.Row) -> dict[str, Any]:
    result_json: Optional[dict[str, Any]] = None
    raw_result = row["result_json"]
    if raw_result:
        try:
            result_json = json.loads(raw_result)
        except json.JSONDecodeError:
            result_json = None

    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "status": row["status"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "page_title": row["page_title"],
        "final_url": row["final_url"],
        "result_json": result_json,
        "error_message": row["error_message"],
    }


def get_scan_or_404(scan_id: int) -> dict[str, Any]:
    try:
        with get_db_connection() as connection:
            row = connection.execute(
                "SELECT * FROM scans WHERE id = ?",
                (scan_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while retrieving scan") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    return serialize_scan(row)


def serialize_test_case(row: sqlite3.Row) -> dict[str, Any]:
    def decode_json(value: Any, default: Any) -> Any:
        if value in (None, ""):
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return value

    return {
        "id": row["id"],
        "test_case_id": row["test_case_id"],
        "project_id": row["project_id"],
        "scan_id": row["scan_id"],
        "scenario": row["scenario"],
        "description": row["description"],
        "preconditions": decode_json(row["preconditions"], []),
        "steps": decode_json(row["steps"], []),
        "test_data": decode_json(row["test_data"], {}),
        "expected_result": row["expected_result"],
        "priority": row["priority"],
        "category": row["category"],
        "execution_type": row["execution_type"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def backfill_execution_types(project_id: int, scan_id: int) -> dict[str, int]:
    updated = {"Automated": 0, "Manual": 0}
    try:
        with get_db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            scan_row = connection.execute(
                """
                SELECT result_json, status FROM scans
                WHERE id = ? AND project_id = ?
                """,
                (scan_id, project_id),
            ).fetchone()
            if scan_row is None:
                raise ValueError("The scan does not belong to the requested project")
            scan_result = _decode_json(scan_row["result_json"], None)
            if scan_row["status"] != "completed" or not isinstance(scan_result, dict):
                raise ValueError("Execution types can only be backfilled from a completed scan")

            rows = connection.execute(
                """
                SELECT * FROM test_cases
                WHERE project_id = ? AND scan_id = ?
                ORDER BY id
                """,
                (project_id, scan_id),
            ).fetchall()
            now = utc_now_iso()
            for row in rows:
                case = serialize_test_case(row)
                execution_type = classify_execution_type(case, scan_result)
                updated[execution_type] += 1
                if execution_type == row["execution_type"]:
                    continue
                cursor = connection.execute(
                    """
                    UPDATE test_cases
                    SET execution_type = ?, updated_at = ?
                    WHERE id = ? AND project_id = ? AND scan_id = ?
                      AND execution_type = ?
                    """,
                    (
                        execution_type,
                        now,
                        row["id"],
                        project_id,
                        scan_id,
                        row["execution_type"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError(
                        "Test-case execution type changed during the targeted backfill"
                    )
            connection.commit()
    except ValueError:
        raise
    except sqlite3.Error as exc:
        logger.exception(
            "Could not backfill execution types for project %s scan %s",
            project_id,
            scan_id,
        )
        raise RuntimeError("Database error while backfilling test-case execution types") from exc
    return updated


def project_scoped_test_case_id(project_id: int, generated_id: str) -> str:
    base_id = generated_id.removeprefix("TC-")
    return f"TC-{project_id}-{base_id}"


def get_test_case_or_404(test_case_id: str) -> dict[str, Any]:
    try:
        with get_db_connection() as connection:
            row = connection.execute(
                "SELECT * FROM test_cases WHERE test_case_id = ?",
                (test_case_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while retrieving test case") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Test case not found")

    return serialize_test_case(row)


VALID_TEST_CASE_STATUSES = {"Not Executed", "Passed", "Failed", "Blocked"}
EXECUTION_STATUS_TO_TEST_CASE_STATUS = {
    "Passed": "Passed",
    "Failed": "Failed",
    "Blocked": "Blocked",
    "Error": "Blocked",
    "Not Automatable": "Blocked",
}


class ApplicationCreate(BaseModel):
    name: str = Field(..., min_length=1)
    url: AnyHttpUrl
    description: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Application name is required")
        return value.strip()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("url")
    @classmethod
    def validate_project_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        try:
            validate_destination_url(str(value))
        except ValueError as exc:
            raise ValueError("Application URL is not allowed") from exc
        return value


class ApplicationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    url: Optional[AnyHttpUrl] = None
    description: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Application name is required")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("url")
    @classmethod
    def validate_project_url(cls, value: Optional[AnyHttpUrl]) -> Optional[AnyHttpUrl]:
        if value is None:
            return None
        try:
            validate_destination_url(str(value))
        except ValueError as exc:
            raise ValueError("Application URL is not allowed") from exc
        return value


class ScanRecord(BaseModel):
    id: int
    project_id: int
    status: str
    started_at: str
    completed_at: Optional[str] = None
    page_title: Optional[str] = None
    final_url: Optional[str] = None
    result_json: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None

    @field_validator("result_json", mode="before")
    @classmethod
    def decode_result_json(cls, value: Any) -> Optional[dict[str, Any]]:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return value


class TestCaseStatusUpdate(BaseModel):
    status: Literal["Not Executed", "Passed", "Failed", "Blocked"]


class ExecutionStartRequest(BaseModel):
    test_case_ids: list[str] = Field(min_length=1, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("test_case_ids")
    @classmethod
    def validate_test_case_ids(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 100 for value in values):
            raise ValueError("Each test case ID must contain between 1 and 100 characters")
        if len(set(values)) != len(values):
            raise ValueError("Test case IDs must be unique")
        return values


EnvironmentName = Literal["development", "staging", "production"]


class EnvironmentUrls(BaseModel):
    development: Optional[AnyHttpUrl] = None
    staging: Optional[AnyHttpUrl] = None
    production: Optional[AnyHttpUrl] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("development", "staging", "production")
    @classmethod
    def validate_environment_url(cls, value: Optional[AnyHttpUrl]) -> Optional[AnyHttpUrl]:
        if value is None:
            return None
        parsed = urlsplit(str(value))
        if parsed.query or parsed.fragment:
            raise ValueError("Environment URL must not include query strings or fragments")
        try:
            validate_execution_url(str(value))
        except ValueError as exc:
            raise ValueError("Environment URL is not allowed") from exc
        return value


class WorkspaceSettingsUpdate(BaseModel):
    workspace_name: str = Field(min_length=1, max_length=80)
    default_environment: EnvironmentName = "development"
    default_project_id: Optional[int] = Field(default=None, ge=1)
    environment_urls: dict[int, EnvironmentUrls] = Field(default_factory=dict)
    execution_timeout_ms: int = Field(default=10000, ge=250, le=60000)
    max_tests_per_run: int = Field(default=100, ge=1, le=100)
    quality_gate_pass_rate_threshold: float = Field(default=80, ge=0, le=100)
    quality_gate_failure_threshold: int = Field(default=0, ge=0, le=1000)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("workspace_name")
    @classmethod
    def validate_workspace_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Workspace name is required")
        return value.strip()

    @field_validator("environment_urls")
    @classmethod
    def validate_environment_project_ids(
        cls, value: dict[int, EnvironmentUrls]
    ) -> dict[int, EnvironmentUrls]:
        if any(project_id < 1 for project_id in value):
            raise ValueError("Environment configuration must reference a registered project")
        return value


init_db()

app = FastAPI(
    title="TestPilot AI",
    description="Browser-based application testing and test-case management.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_workspace_settings() -> dict[str, Any]:
    try:
        with get_db_connection() as connection:
            row = connection.execute("SELECT * FROM workspace_settings WHERE id = 1").fetchone()
            registered_project_ids = {
                project["id"] for project in connection.execute("SELECT id FROM applications")
            }
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while retrieving settings") from exc

    if row is None:
        raise HTTPException(status_code=500, detail="Workspace settings are not initialized")
    raw_urls = _decode_json(row["environment_urls"], {})
    if not isinstance(raw_urls, dict):
        raise HTTPException(status_code=500, detail="Stored environment settings are invalid")
    environment_urls: dict[int, dict[str, str]] = {}
    configured_environments: dict[int, list[str]] = {}
    for raw_project_id, urls in raw_urls.items():
        try:
            project_id = int(raw_project_id)
        except (TypeError, ValueError):
            continue
        if project_id not in registered_project_ids:
            continue
        if not isinstance(urls, dict):
            continue
        safe_urls = {
            environment: url
            for environment, url in urls.items()
            if environment in {"development", "staging", "production"}
            and isinstance(url, str)
        }
        environment_urls[project_id] = safe_urls
        configured_environments[project_id] = sorted(safe_urls)

    return {
        "workspace_name": row["workspace_name"],
        "default_environment": row["default_environment"],
        "default_project_id": row["default_project_id"],
        "environment_urls": environment_urls,
        "configured_environments": configured_environments,
        "execution_timeout_ms": row["execution_timeout_ms"],
        "max_tests_per_run": row["max_tests_per_run"],
        "quality_gate_pass_rate_threshold": row["quality_gate_pass_rate_threshold"],
        "quality_gate_failure_threshold": row["quality_gate_failure_threshold"],
        "updated_at": row["updated_at"],
    }


def save_workspace_settings(payload: WorkspaceSettingsUpdate) -> dict[str, Any]:
    try:
        with get_db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project_ids = set(payload.environment_urls)
            if payload.default_project_id is not None:
                project_ids.add(payload.default_project_id)
            if project_ids:
                placeholders = ",".join("?" for _ in project_ids)
                found = connection.execute(
                    f"SELECT id FROM applications WHERE id IN ({placeholders})",
                    tuple(sorted(project_ids)),
                ).fetchall()
                if {row["id"] for row in found} != project_ids:
                    raise HTTPException(
                        status_code=422,
                        detail="Settings reference an application that is not registered",
                    )

            urls = {
                str(project_id): {
                    environment: str(url)
                    for environment, url in values.model_dump(mode="json").items()
                    if url is not None
                }
                for project_id, values in payload.environment_urls.items()
            }
            connection.execute(
                """
                UPDATE workspace_settings
                SET workspace_name = ?, default_environment = ?, default_project_id = ?,
                    environment_urls = ?, execution_timeout_ms = ?, max_tests_per_run = ?,
                    quality_gate_pass_rate_threshold = ?, quality_gate_failure_threshold = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    payload.workspace_name,
                    payload.default_environment,
                    payload.default_project_id,
                    json.dumps(urls, ensure_ascii=False),
                    payload.execution_timeout_ms,
                    payload.max_tests_per_run,
                    payload.quality_gate_pass_rate_threshold,
                    payload.quality_gate_failure_threshold,
                    utc_now_iso(),
                ),
            )
            connection.commit()
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        logger.exception("Could not save workspace settings")
        raise HTTPException(status_code=500, detail="Database error while saving settings") from exc
    return get_workspace_settings()


def resolve_environment_url(application: dict[str, Any], settings: dict[str, Any]) -> str:
    project_urls = settings["environment_urls"].get(application["id"], {})
    url = project_urls.get(settings["default_environment"], application["url"])
    try:
        return validate_execution_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Configured application URL is not allowed") from exc


def evaluate_quality_gate(
    counts: dict[str, int], settings: dict[str, Any]
) -> tuple[bool, float | None]:
    assertion_count = counts["Passed"] + counts["Failed"] + counts["Error"]
    pass_rate = counts["Passed"] * 100 / assertion_count if assertion_count else None
    quality_failures = counts["Failed"] + counts["Error"]
    passed = (
        assertion_count > 0
        and pass_rate is not None
        and pass_rate >= settings["quality_gate_pass_rate_threshold"]
        and quality_failures <= settings["quality_gate_failure_threshold"]
    )
    return passed, pass_rate


@app.get("/")
def home():
    return {
        "message": "Welcome to TestPilot AI!",
        "status": "Backend is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/api/settings")
def read_settings():
    return get_workspace_settings()


@app.put("/api/settings")
def update_settings(payload: WorkspaceSettingsUpdate):
    return save_workspace_settings(payload)


@app.post("/api/settings/reset")
def reset_settings():
    return save_workspace_settings(WorkspaceSettingsUpdate(workspace_name="TestPilot AI"))


@app.get("/api/projects")
def list_projects():
    try:
        with get_db_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM applications ORDER BY created_at DESC, id DESC"
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while listing applications") from exc

    return [serialize_application(row) for row in rows]


@app.post("/api/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: ApplicationCreate):
    now = utc_now_iso()

    try:
        with get_db_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO applications (name, url, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.name,
                    str(payload.url),
                    payload.description,
                    now,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while creating application") from exc

    if row is None:
        raise HTTPException(status_code=500, detail="Application could not be created")

    return serialize_application(row)


@app.get("/api/projects/{project_id}")
def get_project(project_id: int):
    return get_application_or_404(project_id)


@app.put("/api/projects/{project_id}")
def update_project(project_id: int, payload: ApplicationUpdate):
    existing = get_application_or_404(project_id)

    if (
        'name' not in payload.model_fields_set
        and 'url' not in payload.model_fields_set
        and 'description' not in payload.model_fields_set
    ):
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    name = payload.name if 'name' in payload.model_fields_set else existing["name"]
    url = str(payload.url) if 'url' in payload.model_fields_set else existing["url"]
    description = (
        payload.description
        if 'description' in payload.model_fields_set
        else existing["description"]
    )
    updated_at = utc_now_iso()

    try:
        with get_db_connection() as connection:
            connection.execute(
                """
                UPDATE applications
                SET name = ?, url = ?, description = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, url, description, updated_at, project_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (project_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while updating application") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")

    return serialize_application(row)


@app.post("/api/projects/{project_id}/scans")
async def create_scan(project_id: int):
    application = get_application_or_404(project_id)
    settings = get_workspace_settings()
    url = resolve_environment_url(application, settings)

    try:
        validate_destination_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Application URL is not allowed") from exc

    started_at = utc_now_iso()

    try:
        with get_db_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scans (project_id, status, started_at, completed_at, page_title, final_url, result_json, error_message)
                VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL)
                """,
                (project_id, "running", started_at),
            )
            connection.commit()
            scan_id = cursor.lastrowid
            row = connection.execute(
                "SELECT * FROM scans WHERE id = ?",
                (scan_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while creating scan") from exc

    if row is None:
        raise HTTPException(status_code=500, detail="Scan could not be created")

    try:
        result = await scan_application_url(url)
        completed_at = utc_now_iso()
        payload = json.dumps(result, ensure_ascii=False)
        with get_db_connection() as connection:
            connection.execute(
                """
                UPDATE scans
                SET status = ?, completed_at = ?, page_title = ?, final_url = ?, result_json = ?, error_message = NULL
                WHERE id = ?
                """,
                ("completed", completed_at, result.get("page_title"), result.get("final_url"), payload, row["id"]),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM scans WHERE id = ?",
                (row["id"],),
            ).fetchone()
    except Exception as exc:
        message = str(exc) or "The application scan failed"
        with get_db_connection() as connection:
            connection.execute(
                """
                UPDATE scans
                SET status = ?, completed_at = ?, error_message = ?
                WHERE id = ?
                """,
                ("failed", utc_now_iso(), message, row["id"]),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM scans WHERE id = ?",
                (row["id"],),
            ).fetchone()
        return serialize_scan(row)

    return serialize_scan(row)


@app.get("/api/projects/{project_id}/scans", response_model=list[ScanRecord])
def list_scans(project_id: int):
    get_application_or_404(project_id)

    try:
        with get_db_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM scans WHERE project_id = ? ORDER BY started_at DESC, id DESC",
                (project_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while listing scans") from exc

    return [serialize_scan(row) for row in rows]


@app.get("/api/scans/{scan_id}", response_model=ScanRecord)
def get_scan(scan_id: int):
    return get_scan_or_404(scan_id)


@app.post("/api/projects/{project_id}/scans/{scan_id}/test-cases/generate")
def generate_scan_test_cases(project_id: int, scan_id: int):
    get_application_or_404(project_id)
    scan = get_scan_or_404(scan_id)

    if scan["project_id"] != project_id:
        raise HTTPException(status_code=400, detail="Scan does not belong to the requested project")

    if scan["status"] != "completed":
        raise HTTPException(status_code=400, detail="Test cases can only be generated from completed scans")

    result_json = scan.get("result_json")
    if not isinstance(result_json, dict):
        raise HTTPException(status_code=400, detail="The scan result is missing metadata for test generation")

    generated = generate_test_cases(result_json)
    cases = generated.get("test_cases", [])
    summary = generated.get("summary") or {}

    now = utc_now_iso()
    saved_cases: list[dict[str, Any]] = []
    inserted_count = 0

    try:
        with get_db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for case in cases:
                if not isinstance(case, dict):
                    continue
                generated_id = str(case.get("test_case_id") or "").strip()
                if not generated_id:
                    continue
                scoped_id = project_scoped_test_case_id(project_id, generated_id)
                existing = connection.execute(
                    """
                    SELECT * FROM test_cases
                    WHERE project_id = ? AND test_case_id IN (?, ?)
                    ORDER BY CASE WHEN test_case_id = ? THEN 0 ELSE 1 END
                    LIMIT 1
                    """,
                    (project_id, generated_id, scoped_id, generated_id),
                ).fetchone()
                if existing is not None:
                    saved_case = serialize_test_case(existing)
                    saved_case["persistence_status"] = "duplicate"
                    saved_cases.append(saved_case)
                    continue

                payload = (
                    scoped_id,
                    project_id,
                    scan_id,
                    case.get("scenario"),
                    case.get("description"),
                    json.dumps(case.get("preconditions", []), ensure_ascii=False),
                    json.dumps(case.get("steps", []), ensure_ascii=False),
                    json.dumps(case.get("test_data", {}), ensure_ascii=False),
                    case.get("expected_result"),
                    case.get("priority"),
                    case.get("category"),
                    case.get("execution_type"),
                    case.get("status"),
                    now,
                    now,
                )
                connection.execute(
                    """
                    INSERT INTO test_cases (
                        test_case_id, project_id, scan_id, scenario, description,
                        preconditions, steps, test_data, expected_result,
                        priority, category, execution_type, status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                inserted_count += 1
                row = connection.execute(
                    "SELECT * FROM test_cases WHERE test_case_id = ?",
                    (scoped_id,),
                ).fetchone()
                if row is None:
                    raise sqlite3.IntegrityError("Inserted test case could not be retrieved")
                saved_case = serialize_test_case(row)
                saved_case["persistence_status"] = "inserted"
                saved_cases.append(saved_case)
            connection.commit()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while saving generated test cases") from exc

    response_summary = {
        **summary,
        "generated_count": len(cases),
        "saved_count": len(saved_cases),
        "inserted_count": inserted_count,
        "duplicate_count": len(cases) - inserted_count,
        "project_id": project_id,
        "scan_id": scan_id,
    }
    return {
        "project_id": project_id,
        "scan_id": scan_id,
        "test_cases": saved_cases,
        "summary": response_summary,
    }


@app.get("/api/projects/{project_id}/test-cases")
def list_project_test_cases(project_id: int, scan_id: Optional[int] = None, category: Optional[str] = None, priority: Optional[str] = None, status: Optional[str] = None):
    get_application_or_404(project_id)

    query = "SELECT * FROM test_cases WHERE project_id = ?"
    params: list[Any] = [project_id]

    if scan_id is not None:
        query += " AND scan_id = ?"
        params.append(scan_id)
    if category is not None:
        query += " AND category = ?"
        params.append(category)
    if priority is not None:
        query += " AND priority = ?"
        params.append(priority)
    if status is not None:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC, id DESC"

    try:
        with get_db_connection() as connection:
            rows = connection.execute(query, params).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while listing project test cases") from exc

    return [serialize_test_case(row) for row in rows]


@app.get("/api/test-cases/{test_case_id}")
def get_saved_test_case(test_case_id: str):
    return get_test_case_or_404(test_case_id)


@app.patch("/api/test-cases/{test_case_id}/status")
def update_test_case_status(test_case_id: str, payload: TestCaseStatusUpdate):
    record = get_test_case_or_404(test_case_id)
    new_status = payload.status

    if new_status not in VALID_TEST_CASE_STATUSES:
        raise HTTPException(status_code=400, detail="Status must be one of: Not Executed, Passed, Failed, Blocked")

    updated_at = utc_now_iso()

    try:
        with get_db_connection() as connection:
            connection.execute(
                "UPDATE test_cases SET status = ?, updated_at = ? WHERE test_case_id = ?",
                (new_status, updated_at, test_case_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM test_cases WHERE test_case_id = ?",
                (test_case_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while updating test case status") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Test case not found")

    return serialize_test_case(row)


def _decode_json(value: Any, default: Any) -> Any:
    if not isinstance(value, str) or not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def serialize_execution_result(row: sqlite3.Row) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "execution_run_id": row["execution_run_id"],
        "test_case_id": row["test_case_id"],
        "execution_status": row["execution_status"],
        "action_performed": row["action_performed"],
        "assertion_performed": row["assertion_performed"],
        "expected_result": row["expected_result"],
        "actual_result": row["actual_result"],
        "error_message": row["error_message"],
        "failure_details": _decode_json(row["failure_details"], None),
        "duration_ms": row["duration_ms"],
        "screenshot_path": row["screenshot_path"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }
    result["analysis"] = analyze_failure(result)
    return result


def serialize_execution_run(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "project_name": row["project_name"] if "project_name" in row.keys() else None,
        "scan_id": row["scan_id"],
        "status": row["status"],
        "total_tests": row["total_tests"],
        "passed": row["passed"],
        "failed": row["failed"],
        "blocked": row["blocked"],
        "errors": row["errors"],
        "not_automatable": row["not_automatable"],
        "environment": row["environment"],
        "quality_gate_passed": (
            bool(row["quality_gate_passed"]) if row["quality_gate_passed"] is not None else None
        ),
        "quality_gate_pass_rate": row["quality_gate_pass_rate"],
        "quality_gate_pass_rate_threshold": row["quality_gate_pass_rate_threshold"],
        "quality_gate_failure_threshold": row["quality_gate_failure_threshold"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "duration_ms": row["duration_ms"],
    }


def get_execution_run_or_404(execution_run_id: int) -> sqlite3.Row:
    try:
        with get_db_connection() as connection:
            row = connection.execute(
                """
                SELECT r.*, a.name AS project_name
                FROM execution_runs r
                JOIN applications a ON a.id = r.project_id
                WHERE r.id = ?
                """,
                (execution_run_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while retrieving execution run") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Execution run not found")
    return row


def get_execution_results(execution_run_id: int) -> list[dict[str, Any]]:
    try:
        with get_db_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM execution_results
                WHERE execution_run_id = ?
                ORDER BY id
                """,
                (execution_run_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while retrieving execution results") from exc
    return [serialize_execution_result(row) for row in rows]


@app.get("/api/projects/{project_id}/execution-candidates")
def list_execution_candidates(project_id: int):
    get_application_or_404(project_id)
    try:
        with get_db_connection() as connection:
            rows = connection.execute(
                """
                SELECT tc.*, s.result_json
                FROM test_cases tc
                LEFT JOIN scans s ON s.id = tc.scan_id
                WHERE tc.project_id = ?
                ORDER BY tc.created_at DESC, tc.id DESC
                """,
                (project_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while listing execution candidates") from exc

    candidates = []
    for row in rows:
        case = serialize_test_case(row)
        scan_result = _decode_json(row["result_json"], {})
        scan_result = scan_result if isinstance(scan_result, dict) else {}
        candidates.append({**case, **assess_automation(case, scan_result)})
    return candidates


@app.post("/api/projects/{project_id}/executions", status_code=status.HTTP_201_CREATED)
async def start_execution(project_id: int, payload: ExecutionStartRequest):
    application = get_application_or_404(project_id)
    settings = get_workspace_settings()
    application_url = resolve_environment_url(application, settings)
    if len(payload.test_case_ids) > settings["max_tests_per_run"]:
        raise HTTPException(
            status_code=422,
            detail=f"A run cannot include more than {settings['max_tests_per_run']} test cases.",
        )
    try:
        validate_execution_url(application_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Application URL is not allowed for browser execution") from exc

    placeholders = ",".join("?" for _ in payload.test_case_ids)
    try:
        with get_db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                f"""
                SELECT tc.*, s.result_json
                FROM test_cases tc
                JOIN scans s ON s.id = tc.scan_id
                WHERE tc.project_id = ? AND tc.test_case_id IN ({placeholders})
                """,
                (project_id, *payload.test_case_ids),
            ).fetchall()
            if len(rows) != len(payload.test_case_ids):
                raise HTTPException(
                    status_code=404,
                    detail="One or more test cases were not found in this project",
                )
            requested_order = {case_id: index for index, case_id in enumerate(payload.test_case_ids)}
            rows = sorted(rows, key=lambda row: requested_order[row["test_case_id"]])

            cases_with_scans = []
            scan_ids = set()
            for row in rows:
                case = serialize_test_case(row)
                raw_scan = _decode_json(row["result_json"], {})
                scan_result = raw_scan if isinstance(raw_scan, dict) else {}
                cases_with_scans.append((case, scan_result))
                scan_ids.add(case["scan_id"])

            started_at = utc_now_iso()
            cursor = connection.execute(
                """
                INSERT INTO execution_runs (
                    project_id, scan_id, status, total_tests, environment,
                    quality_gate_pass_rate_threshold, quality_gate_failure_threshold,
                    started_at
                ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    next(iter(scan_ids)) if len(scan_ids) == 1 else None,
                    len(cases_with_scans),
                    settings["default_environment"],
                    settings["quality_gate_pass_rate_threshold"],
                    settings["quality_gate_failure_threshold"],
                    started_at,
                ),
            )
            execution_run_id = cursor.lastrowid
            connection.commit()
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        logger.exception("Could not create execution run")
        raise HTTPException(status_code=500, detail="Database error while creating execution run") from exc

    run_started = time.perf_counter()
    try:
        results = await execute_test_cases(
            application_url,
            cases_with_scans,
            timeout_ms=settings["execution_timeout_ms"],
            max_test_cases=settings["max_tests_per_run"],
        )
        expected_test_case_ids = {case["test_case_id"] for case, _ in cases_with_scans}
        if (
            len(results) != len(cases_with_scans)
            or any(not isinstance(result, dict) for result in results)
        ):
            raise RuntimeError("The browser executor did not produce one result for each selected test case")
        result_test_case_ids = [result.get("test_case_id") for result in results]
        if (
            any(not isinstance(test_case_id, str) for test_case_id in result_test_case_ids)
            or len(set(result_test_case_ids)) != len(result_test_case_ids)
            or set(result_test_case_ids) != expected_test_case_ids
        ):
            raise RuntimeError("The browser executor returned results for an unexpected set of test cases")
        run_status = "completed"
    except Exception as exc:
        logger.error(
            "Execution run %s failed before producing results (%s)",
            execution_run_id,
            type(exc).__name__,
        )
        results = []
        for case, scan_result in cases_with_scans:
            eligibility = assess_automation(case, scan_result)
            if eligibility["automatable"]:
                results.append(
                    {
                        "test_case_id": case["test_case_id"],
                        "execution_status": "Error",
                        "action_performed": "Open the saved application URL.",
                        "assertion_performed": eligibility.get("assertion"),
                        "expected_result": case["expected_result"],
                        "actual_result": None,
                        "error_message": "Browser execution could not be completed.",
                        "failure_details": {
                            "category": "Browser execution error",
                            "details": f"Execution raised {type(exc).__name__}.",
                        },
                        "duration_ms": 0,
                        "screenshot_path": None,
                        "started_at": utc_now_iso(),
                        "completed_at": utc_now_iso(),
                    }
                )
            else:
                results.append(
                    {
                        "test_case_id": case["test_case_id"],
                        "execution_status": (
                            "Blocked"
                            if eligibility["eligibility"] in {"Ambiguous locator", "Locator metadata missing"}
                            else "Not Automatable"
                        ),
                        "action_performed": eligibility["action"],
                        "assertion_performed": None,
                        "expected_result": case["expected_result"],
                        "actual_result": None,
                        "error_message": eligibility["reason"],
                        "failure_details": {
                            "category": eligibility["eligibility"],
                            "details": eligibility["reason"],
                        },
                        "duration_ms": 0,
                        "screenshot_path": None,
                        "started_at": utc_now_iso(),
                        "completed_at": utc_now_iso(),
                    }
                )
        run_status = "error"

    counts = {
        "Passed": sum(result["execution_status"] == "Passed" for result in results),
        "Failed": sum(result["execution_status"] == "Failed" for result in results),
        "Blocked": sum(result["execution_status"] == "Blocked" for result in results),
        "Error": sum(result["execution_status"] == "Error" for result in results),
        "Not Automatable": sum(result["execution_status"] == "Not Automatable" for result in results),
    }
    quality_gate_passed, quality_gate_pass_rate = evaluate_quality_gate(
        counts, settings
    )
    completed_at = utc_now_iso()
    duration_ms = max(0, round((time.perf_counter() - run_started) * 1000))
    try:
        with get_db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for result in results:
                connection.execute(
                    """
                    INSERT INTO execution_results (
                        execution_run_id, test_case_id, execution_status,
                        action_performed, assertion_performed, expected_result,
                        actual_result, error_message, failure_details,
                        duration_ms, screenshot_path, started_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        execution_run_id,
                        result["test_case_id"],
                        result["execution_status"],
                        result["action_performed"],
                        result["assertion_performed"],
                        result["expected_result"],
                        result["actual_result"],
                        result["error_message"],
                        json.dumps(result["failure_details"], ensure_ascii=False)
                        if result["failure_details"] is not None
                        else None,
                        result["duration_ms"],
                        result["screenshot_path"],
                        result["started_at"],
                        result["completed_at"],
                    ),
                )
                cursor = connection.execute(
                    """
                    UPDATE test_cases
                    SET status = ?, updated_at = ?
                    WHERE test_case_id = ? AND project_id = ?
                      AND EXISTS (
                          SELECT 1
                          FROM execution_results er
                          JOIN execution_runs current_run
                            ON current_run.id = er.execution_run_id
                          WHERE er.execution_run_id = ?
                            AND er.test_case_id = test_cases.test_case_id
                            AND current_run.project_id = test_cases.project_id
                      )
                    """,
                    (
                        EXECUTION_STATUS_TO_TEST_CASE_STATUS[result["execution_status"]],
                        result["completed_at"],
                        result["test_case_id"],
                        project_id,
                        execution_run_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError(
                        "Execution result could not be synchronized with its test case"
                    )
            connection.execute(
                """
                UPDATE execution_runs
                SET status = ?, passed = ?, failed = ?, blocked = ?, errors = ?,
                    not_automatable = ?, quality_gate_passed = ?, quality_gate_pass_rate = ?,
                    completed_at = ?, duration_ms = ?
                WHERE id = ?
                """,
                (
                    run_status,
                    counts["Passed"],
                    counts["Failed"],
                    counts["Blocked"],
                    counts["Error"],
                    counts["Not Automatable"],
                    int(quality_gate_passed),
                    quality_gate_pass_rate,
                    completed_at,
                    duration_ms,
                    execution_run_id,
                ),
            )
            connection.commit()
    except sqlite3.Error as exc:
        logger.exception("Could not persist execution results for run %s", execution_run_id)
        try:
            with get_db_connection() as connection:
                connection.execute(
                    "UPDATE execution_runs SET status = 'error', completed_at = ?, duration_ms = ? WHERE id = ?",
                    (utc_now_iso(), duration_ms, execution_run_id),
                )
                connection.commit()
        except sqlite3.Error:
            logger.exception("Could not mark execution run %s as errored", execution_run_id)
        raise HTTPException(status_code=500, detail="Database error while saving execution results") from exc

    return {
        **serialize_execution_run(get_execution_run_or_404(execution_run_id)),
        "results": get_execution_results(execution_run_id),
    }


@app.get("/api/projects/{project_id}/executions")
def list_project_executions(project_id: int):
    get_application_or_404(project_id)
    try:
        with get_db_connection() as connection:
            rows = connection.execute(
                """
                SELECT r.*, a.name AS project_name
                FROM execution_runs r
                JOIN applications a ON a.id = r.project_id
                WHERE r.project_id = ?
                ORDER BY r.started_at DESC, r.id DESC
                """,
                (project_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while listing execution history") from exc
    return [serialize_execution_run(row) for row in rows]


@app.get("/api/executions/{execution_run_id}")
def get_execution(execution_run_id: int):
    row = get_execution_run_or_404(execution_run_id)
    return {**serialize_execution_run(row), "results": get_execution_results(execution_run_id)}


@app.get("/api/executions/{execution_run_id}/results")
def list_execution_results(execution_run_id: int):
    get_execution_run_or_404(execution_run_id)
    return get_execution_results(execution_run_id)


@app.get("/api/bug-analysis")
def list_bug_analysis(project_id: Optional[int] = None):
    if project_id is not None:
        get_application_or_404(project_id)
    query = """
        SELECT er.*, r.project_id, r.started_at AS run_started_at,
               a.name AS project_name, tc.scenario
        FROM execution_results er
        JOIN execution_runs r ON r.id = er.execution_run_id
        JOIN applications a ON a.id = r.project_id
        JOIN test_cases tc ON tc.test_case_id = er.test_case_id
        WHERE er.execution_status IN ('Failed', 'Blocked', 'Error')
    """
    params: tuple[Any, ...] = ()
    if project_id is not None:
        query += " AND r.project_id = ?"
        params = (project_id,)
    query += " ORDER BY r.started_at DESC, er.id DESC"
    try:
        with get_db_connection() as connection:
            rows = connection.execute(query, params).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while analyzing execution failures") from exc

    findings = []
    for row in rows:
        result = serialize_execution_result(row)
        findings.append(
            {
                **result,
                **(result["analysis"] or {}),
                "project_id": row["project_id"],
                "project_name": row["project_name"],
                "scenario": row["scenario"],
                "run_started_at": row["run_started_at"],
            }
        )
    return findings


def _safe_csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


@app.get("/api/reports")
def get_reports(project_id: Optional[int] = None):
    if project_id is not None:
        get_application_or_404(project_id)
    try:
        with get_db_connection() as connection:
            project_rows = connection.execute(
                """
                SELECT a.id AS project_id, a.name AS project_name,
                       (SELECT COUNT(*) FROM test_cases tc WHERE tc.project_id = a.id) AS total_test_cases,
                       (SELECT COUNT(*) FROM execution_runs r WHERE r.project_id = a.id) AS total_runs,
                       (SELECT COALESCE(SUM(r.passed), 0) FROM execution_runs r WHERE r.project_id = a.id) AS passed,
                       (SELECT COALESCE(SUM(r.failed), 0) FROM execution_runs r WHERE r.project_id = a.id) AS failed,
                       (SELECT COALESCE(SUM(r.blocked), 0) FROM execution_runs r WHERE r.project_id = a.id) AS blocked,
                       (SELECT COALESCE(SUM(r.errors), 0) FROM execution_runs r WHERE r.project_id = a.id) AS errors,
                       (SELECT COALESCE(SUM(r.not_automatable), 0) FROM execution_runs r WHERE r.project_id = a.id) AS not_automatable
                FROM applications a
                WHERE (? IS NULL OR a.id = ?)
                ORDER BY a.name COLLATE NOCASE
                """,
                (project_id, project_id),
            ).fetchall()
            run_rows = connection.execute(
                """
                SELECT r.*, a.name AS project_name
                FROM execution_runs r
                JOIN applications a ON a.id = r.project_id
                WHERE (? IS NULL OR r.project_id = ?)
                ORDER BY r.started_at DESC, r.id DESC
                """,
                (project_id, project_id),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while preparing execution report") from exc

    runs = [serialize_execution_run(row) for row in run_rows]
    for run in runs:
        failures = [
            item
            for item in get_execution_results(run["id"])
            if item["execution_status"] in {"Failed", "Blocked", "Error"}
        ]
        categories = sorted(
            {
                item["analysis"]["failure_category"]
                for item in failures
                if item["analysis"] is not None
            }
        )
        run["failure_summaries"] = categories

    return {
        "projects": [dict(row) for row in project_rows],
        "runs": runs,
    }


@app.get("/api/reports.csv")
def download_execution_report(project_id: Optional[int] = None):
    report = get_reports(project_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Project ID",
            "Project",
            "Run ID",
            "Run Status",
            "Started At",
            "Completed At",
            "Total",
            "Passed",
            "Failed",
            "Blocked",
            "Errors",
            "Not Automatable",
            "Duration (ms)",
            "Failure Categories",
            "Record Type",
            "Test Case ID",
            "Scenario",
            "Execution Status",
            "Expected Result",
            "Actual Result",
            "Test Duration (ms)",
            "Failure Details",
            "Error Message",
        ]
    )
    for run in report["runs"]:
        writer.writerow(
            [
                _safe_csv_cell(run["project_id"]),
                _safe_csv_cell(run["project_name"]),
                _safe_csv_cell(run["id"]),
                _safe_csv_cell(run["status"]),
                _safe_csv_cell(run["started_at"]),
                _safe_csv_cell(run["completed_at"]),
                _safe_csv_cell(run["total_tests"]),
                _safe_csv_cell(run["passed"]),
                _safe_csv_cell(run["failed"]),
                _safe_csv_cell(run["blocked"]),
                _safe_csv_cell(run["errors"]),
                _safe_csv_cell(run["not_automatable"]),
                _safe_csv_cell(run["duration_ms"]),
                _safe_csv_cell(", ".join(run["failure_summaries"])),
                "Run Summary",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )

    try:
        with get_db_connection() as connection:
            result_rows = connection.execute(
                """
                SELECT r.project_id, a.name AS project_name, r.id AS run_id,
                       r.status AS run_status, r.started_at, r.completed_at,
                       er.test_case_id, tc.scenario, er.execution_status,
                       er.expected_result, er.actual_result, er.duration_ms,
                       er.failure_details, er.error_message
                FROM execution_results er
                JOIN execution_runs r ON r.id = er.execution_run_id
                JOIN applications a ON a.id = r.project_id
                JOIN test_cases tc ON tc.test_case_id = er.test_case_id
                WHERE (? IS NULL OR r.project_id = ?)
                ORDER BY r.started_at DESC, r.id DESC, er.id
                """,
                (project_id, project_id),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while preparing execution report") from exc

    for row in result_rows:
        failure_details = _decode_json(row["failure_details"], None)
        writer.writerow(
            [
                _safe_csv_cell(row["project_id"]),
                _safe_csv_cell(row["project_name"]),
                _safe_csv_cell(row["run_id"]),
                _safe_csv_cell(row["run_status"]),
                _safe_csv_cell(row["started_at"]),
                _safe_csv_cell(row["completed_at"]),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "Test Case Result",
                _safe_csv_cell(row["test_case_id"]),
                _safe_csv_cell(row["scenario"]),
                _safe_csv_cell(row["execution_status"]),
                _safe_csv_cell(row["expected_result"]),
                _safe_csv_cell(row["actual_result"]),
                _safe_csv_cell(row["duration_ms"]),
                _safe_csv_cell(
                    json.dumps(failure_details, ensure_ascii=False)
                    if failure_details is not None
                    else ""
                ),
                _safe_csv_cell(row["error_message"]),
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="testpilot-execution-report.csv"'},
    )


@app.get("/api/dashboard/summary")
def get_dashboard_summary():
    try:
        with get_db_connection() as connection:
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM applications) AS project_count,
                    (SELECT COUNT(*) FROM test_cases) AS test_case_count,
                    (SELECT COUNT(*) FROM execution_runs) AS run_count,
                    COALESCE(SUM(passed + failed + blocked + errors), 0) AS executed,
                    COALESCE(SUM(passed), 0) AS passed,
                    COALESCE(SUM(failed), 0) AS failed,
                    COALESCE(SUM(blocked), 0) AS blocked,
                    COALESCE(SUM(errors), 0) AS errors
                FROM execution_runs
                """
            ).fetchone()
            rows = connection.execute(
                """
                SELECT r.*, a.name AS project_name
                FROM execution_runs r
                JOIN applications a ON a.id = r.project_id
                ORDER BY r.started_at DESC, r.id DESC
                LIMIT 8
                """
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while loading dashboard summary") from exc

    executed = counts["executed"]
    return {
        "project_count": counts["project_count"],
        "test_case_count": counts["test_case_count"],
        "total_runs": counts["run_count"],
        "tests_executed": executed,
        "pass_rate": round(counts["passed"] * 100 / executed, 1) if executed else None,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "blocked": counts["blocked"],
        "errors": counts["errors"],
        "recent_runs": [serialize_execution_run(row) for row in rows],
    }


@app.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int):
    get_application_or_404(project_id)

    try:
        with get_db_connection() as connection:
            connection.execute("DELETE FROM applications WHERE id = ?", (project_id,))
            connection.commit()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database error while deleting application") from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
