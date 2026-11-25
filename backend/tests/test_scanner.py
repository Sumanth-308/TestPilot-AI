import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient
from playwright.async_api import async_playwright

from backend import main as backend_main
from backend import scanner
from backend.scanner import (
    _collect_buttons,
    _collect_element_metadata,
    _collect_forms,
    _collect_headings,
    _collect_inputs,
    _collect_links,
)


def test_scan_endpoint_persists_title_and_metadata_after_failed_request(
    tmp_path, monkeypatch
):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = (
                b"<title>Route fixture</title>"
                b"<script src='/blocked.js'></script>"
                b"<h1>Available page</h1>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    def validate_fixture_destination(url):
        if url.endswith("/blocked.js"):
            raise ValueError("Fixture request blocked")
        return url

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(backend_main, "DATABASE_DIR", data_dir)
    monkeypatch.setattr(backend_main, "DATABASE_PATH", data_dir / "testpilot.db")
    backend_main.init_db()
    monkeypatch.setattr(scanner, "validate_destination_url", validate_fixture_destination)
    monkeypatch.setattr(backend_main, "validate_destination_url", validate_fixture_destination)
    monkeypatch.setattr(backend_main, "validate_execution_url", validate_fixture_destination)
    url = f"http://127.0.0.1:{server.server_port}/"
    client = TestClient(backend_main.app)

    try:
        project_response = client.post(
            "/api/projects",
            json={"name": "Scanner route fixture", "url": url},
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]

        response = client.post(f"/api/projects/{project_id}/scans")
        assert response.status_code == 200, response.text
        result = response.json()

        assert result["status"] == "completed"
        assert result["page_title"] == "Route fixture"
        assert result["result_json"]["headings"] == ["Available page"]
        assert result["result_json"]["element_metadata"]["headings"]
        assert any(
            "/blocked.js" in failure
            for failure in result["result_json"]["navigation_failures"]
        )

        with backend_main.get_db_connection() as connection:
            persisted = connection.execute(
                "SELECT status, page_title, result_json FROM scans WHERE id = ?",
                (result["id"],),
            ).fetchone()
    finally:
        client.close()
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()

    assert persisted["status"] == "completed"
    assert persisted["page_title"] == "Route fixture"
    persisted_result = json.loads(persisted["result_json"])
    assert persisted_result["headings"] == ["Available page"]
    assert persisted_result["element_metadata"]["headings"]


def _run_dom_test(html, collect):
    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html)
            try:
                return await collect(page)
            finally:
                await browser.close()

    return asyncio.run(run())


def _candidate(element, strategy):
    return next(candidate for candidate in element["locator_candidates"] if candidate["strategy"] == strategy)


def test_button_metadata_has_measured_role_and_test_id_locators():
    async def collect(page):
        return await _collect_element_metadata(page)

    metadata = _run_dom_test(
        '<button aria-label="Save changes" data-testid="save-button">Save</button>',
        collect,
    )["buttons"][0]

    assert metadata["tag_name"] == "button"
    assert metadata["element_text"] == "Save"
    assert metadata["accessible_name"] == "Save changes"
    assert metadata["aria_role"] == "button"
    assert _candidate(metadata, "data-testid")["is_unique"] is True
    assert _candidate(metadata, "role")["value"] == {"role": "button", "name": "Save changes"}
    assert _candidate(metadata, "role")["match_count"] == 1
    assert _candidate(metadata, "css")["is_unique"] is True


def test_link_metadata_and_locator_candidates():
    async def collect(page):
        return await _collect_element_metadata(page)

    link = _run_dom_test(
        '<a href="/docs" target="_blank" rel="noopener">Documentation</a>',
        collect,
    )["links"][0]

    assert link["text"] == "Documentation"
    assert link["href"] == "/docs"
    assert link["target"] == "_blank"
    assert link["rel"] == "noopener"
    assert link["aria_role"] == "link"
    assert _candidate(link, "role")["is_unique"] is True


def test_input_metadata_captures_label_and_validation_attributes():
    async def collect(page):
        return await _collect_element_metadata(page)

    field = _run_dom_test(
        '<label for="email">Email address</label>'
        '<input id="email" name="email" type="email" placeholder="you@example.com" '
        'required readonly minlength="4" maxlength="50" min="1" max="10" pattern="[a-z]+">',
        collect,
    )["inputs"][0]

    assert field["associated_label"] == "Email address"
    assert field["required"] is True
    assert field["readonly"] is True
    assert field["minlength"] == "4"
    assert field["maxlength"] == "50"
    assert field["min"] == "1"
    assert field["max"] == "10"
    assert field["pattern"] == "[a-z]+"
    assert _candidate(field, "label")["match_count"] == 1
    assert _candidate(field, "id")["is_unique"] is True
    assert _candidate(field, "name")["is_unique"] is True
    assert _candidate(field, "placeholder")["is_unique"] is True


def test_duplicate_accessible_names_are_not_reported_as_unique():
    async def collect(page):
        return await _collect_element_metadata(page)

    buttons = _run_dom_test(
        '<button aria-label="Continue">Next</button><button aria-label="Continue">Next</button>',
        collect,
    )["buttons"]

    for button in buttons:
        candidate = _candidate(button, "role")
        assert candidate["match_count"] == 2
        assert candidate["is_unique"] is False


def test_duplicate_and_missing_ids_and_attributes_are_handled():
    async def collect(page):
        return await _collect_element_metadata(page)

    metadata = _run_dom_test(
        '<input id="shared"><input id="shared"><input><button></button><a href="/blank"></a>',
        collect,
    )

    assert all(_candidate(field, "id")["match_count"] == 2 for field in metadata["inputs"][:2])
    assert all(_candidate(field, "id")["is_unique"] is False for field in metadata["inputs"][:2])
    assert metadata["inputs"][2]["element_id"] is None
    assert all(candidate["strategy"] != "id" for candidate in metadata["inputs"][2]["locator_candidates"])
    assert metadata["buttons"][0]["accessible_name"] is None
    assert metadata["links"][0]["accessible_name"] is None


def test_disabled_and_hidden_elements_are_reported_without_values():
    async def collect(page):
        return await _collect_element_metadata(page)

    metadata = _run_dom_test(
        '<button disabled>Disabled</button><button style="display:none">Hidden</button>'
        '<input type="password" value="private-password">'
        '<textarea>private-notes</textarea><input type="hidden" name="csrf" value="private-token">',
        collect,
    )

    assert metadata["buttons"][0]["enabled"] is False
    assert metadata["buttons"][0]["disabled"] is True
    assert metadata["buttons"][1]["visibility"] == "hidden"
    assert metadata["inputs"][0]["type"] == "password"
    assert metadata["inputs"][0]["element_text"] == ""
    assert metadata["inputs"][1]["element_text"] == ""
    serialized = repr(metadata)
    assert "private-password" not in serialized
    assert "private-notes" not in serialized
    assert "private-token" not in serialized


def test_form_metadata_includes_fields_and_submit_buttons_without_values():
    async def collect(page):
        return await _collect_element_metadata(page)

    form = _run_dom_test(
        '<form id="signup" name="signup-form" method="post" action="/signup">'
        '<label for="contact">Contact</label><input id="contact" name="contact">'
        '<button type="submit">Send</button></form><input id="external" name="external" form="signup">',
        collect,
    )["forms"][0]

    assert form["id"] == "signup"
    assert form["name"] == "signup-form"
    assert form["method"] == "post"
    assert form["action"] == "/signup"
    assert form["fields"][0]["associated_label"] == "Contact"
    assert [field["name"] for field in form["fields"]] == ["contact", "external"]
    assert form["submit_buttons"][0]["text"] == "Send"
    assert form["element_text"] == ""


def test_legacy_scan_collectors_keep_their_existing_output_shape():
    async def collect(page):
        return {
            "headings": await _collect_headings(page),
            "buttons": await _collect_buttons(page),
            "links": await _collect_links(page),
            "inputs": await _collect_inputs(page),
            "forms": await _collect_forms(page),
            "element_metadata": await _collect_element_metadata(page),
        }

    result = _run_dom_test(
        '<h1>Welcome</h1><h1 style="display:none">Hidden heading</h1>'
        '<button id="save">Save</button><a href="/docs">Docs</a>'
        '<form id="contact"><input id="email" name="email" type="email" required></form>',
        collect,
    )

    assert set(result) == {"headings", "buttons", "links", "inputs", "forms", "element_metadata"}
    assert result["headings"] == ["Welcome"]
    assert result["buttons"] == [{"text": "Save", "type": "button", "form_id": None}]
    assert result["links"] == [{"text": "Docs", "href": "/docs"}]
    assert result["inputs"] == [{"type": "email", "name": "email", "placeholder": None, "id": "email", "required": True}]
    assert result["forms"] == [{
        "id": "contact",
        "action": "",
        "method": "get",
        "fields": [{"type": "email", "name": "email", "placeholder": None, "id": "email", "required": True}],
    }]
    assert result["element_metadata"]["headings"][1]["visibility"] == "hidden"