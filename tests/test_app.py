from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

import app as checker


def test_endpoint_routing_and_encoding() -> None:
    assert checker.endpoint_for_id("1T123") == "/v3/titles/1T123"
    assert checker.endpoint_for_id("1V456") == "/v3/versions/1V456"
    assert checker.endpoint_for_id("1T/with ? unsafe") == (
        "/v3/titles/1T%2Fwith%20%3F%20unsafe"
    )
    assert checker.endpoint_for_id(
        "1T/with ? unsafe",
        title_path_template="/Custom/Titles/OTP:{id}/status",
        version_path_template="/custom/versions/{id}",
    ) == "/Custom/Titles/OTP:1T%2Fwith%20%3F%20unsafe/status"
    assert checker.endpoint_for_id(
        "1V456",
        title_path_template="/Custom/Titles/{id}",
        version_path_template="/CaseSensitive/Versions/{id}",
    ) == "/CaseSensitive/Versions/1V456"
    assert checker.endpoint_for_id("1t123") is None
    assert checker.endpoint_for_id("other") is None


def test_read_input_ids_ignores_blank_lines_and_strips_bom(tmp_path: Path) -> None:
    input_path = tmp_path / "input.txt"
    input_path.write_text("\ufeff1T1\n\n  1V2  \n", encoding="utf-8")
    assert checker.read_input_ids(input_path) == ["1T1", "1V2"]


def test_url_and_job_request_validation() -> None:
    assert (
        checker.validate_http_url(
            "HTTPS://api.example.com/base/", field_name="Root URL", allow_query=False
        )
        == "https://api.example.com/base"
    )
    with pytest.raises(ValueError):
        checker.validate_http_url(
            "file:///tmp/data", field_name="Root URL", allow_query=False
        )
    with pytest.raises(ValueError):
        checker.validate_http_url(
            "https://user:secret@example.com", field_name="Root URL", allow_query=False
        )
    with pytest.raises(ValueError):
        checker.validate_http_url(
            "https://api.example.com?secret=x",
            field_name="Root URL",
            allow_query=False,
        )
    with pytest.raises(ValueError, match="Field required"):
        checker.JobRequest(root_url="https://api.example.com")
    with pytest.raises(ValueError, match="Token is required"):
        checker.JobRequest(root_url="https://api.example.com", token="   ")
    with pytest.raises(ValueError, match="line breaks"):
        checker.JobRequest(
            root_url="https://api.example.com",
            token="token-value\ninjected-header",
        )
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        checker.JobRequest(
            root_url="https://api.example.com",
            token="token-value",
            auth_mode="none",
        )

    normalized = checker.JobRequest(
        root_url="https://api.example.com",
        token="  Bearer token-value  ",
    )
    assert normalized.token.get_secret_value() == "token-value"
    assert normalized.title_path_template == "/v3/titles/{id}"
    assert normalized.version_path_template == "/v3/versions/{id}"


def test_route_template_validation_and_url_joining() -> None:
    assert (
        checker.validate_route_template(
            "  /Custom/Titles/{id}/status  ",
            field_name="1T title path",
        )
        == "/Custom/Titles/{id}/status"
    )
    assert (
        checker.validate_route_template(
            "/v3/caf%C3%A9/{id}",
            field_name="1T title path",
        )
        == "/v3/caf%C3%A9/{id}"
    )
    assert (
        checker.validate_route_template(
            "/v1/titles/OTP:{id}",
            field_name="1T title path",
        )
        == "/v1/titles/OTP:{id}"
    )
    assert (
        checker.validate_route_template(
            "/v1/titles/prefix-{id}-suffix",
            field_name="1T title path",
        )
        == "/v1/titles/prefix-{id}-suffix"
    )

    invalid_templates = [
        "",
        "v3/titles/{id}",
        "//other.example/{id}",
        "https://other.example/{id}",
        "/v3/titles/{id}?view=full",
        "/v3/titles/{id}#fragment",
        "/v3//titles/{id}",
        "/v3/titles/{other}",
        "/v3/titles/{id}/{id}",
        "/v3/../titles/{id}",
        "/v3/%2e%2e/titles/{id}",
        "/v3/%2e%2e%2ftitles/{id}",
        "/v3/%2E%2E%5Ctitles/{id}",
        "/v3/%252e%252e/titles/{id}",
        "/v3/%25ZZ/titles/{id}",
        "/v3/%FF/titles/{id}",
        "/v3/titles/%3Fview/{id}",
        "/v3/titles/%23fragment/{id}",
        "/v3/titles/%20space/{id}",
        "/v3/titles/%ZZ/{id}",
        "/v1/%7Bother%7D/OTP:{id}",
        "/v1/OTP:%7Bid%7D/{id}",
        "/v3\\titles\\{id}",
        "/v3/titles/{id}\nInjected",
    ]
    deeply_encoded_traversal = "../"
    for _ in range(5):
        deeply_encoded_traversal = quote(deeply_encoded_traversal, safe="")
    invalid_templates.append(f"/v3/{deeply_encoded_traversal}titles/{{id}}")
    for template in invalid_templates:
        with pytest.raises(ValueError):
            checker.validate_route_template(
                template,
                field_name="Route path",
            )

    assert (
        checker.join_root_and_endpoint(
            "https://api.example.com",
            "/v3/titles/1T1",
        )
        == "https://api.example.com/v3/titles/1T1"
    )
    assert (
        checker.join_root_and_endpoint(
            "https://api.example.com/base/",
            "/v3/titles/1T1",
        )
        == "https://api.example.com/base/v3/titles/1T1"
    )


def test_home_and_input_preview(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    input_path = tmp_path / "input.txt"
    input_path.write_text("1T1\n1V2\nBAD\n", encoding="utf-8")
    monkeypatch.setattr(checker, "INPUT_FILE", input_path)

    with TestClient(checker.app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "API ID Status Checker" in home.text
        assert 'id="title-path-template"' in home.text
        assert 'value="/v3/titles/{id}"' in home.text
        assert 'id="version-path-template"' in home.text
        assert 'value="/v3/versions/{id}"' in home.text

        preview = client.get("/api/input-preview")
        assert preview.status_code == 200
        assert preview.json()["count"] == 3
        assert preview.json()["title_count"] == 1
        assert preview.json()["version_count"] == 1
        assert preview.json()["unsupported_count"] == 1

        schema = client.get("/openapi.json").json()
        job_properties = schema["components"]["schemas"]["JobRequest"]["properties"]
        assert "token" in job_properties
        assert job_properties["title_path_template"]["default"] == "/v3/titles/{id}"
        assert (
            job_properties["version_path_template"]["default"]
            == "/v3/versions/{id}"
        )
        assert {
            "auth_mode",
            "client_id",
            "client_secret",
            "token_url",
            "oauth_scope",
            "oauth_audience",
        }.isdisjoint(job_properties)

        invalid_token = "never-echo-this-token\ninjected-header"
        invalid = client.post(
            "/api/jobs",
            json={
                "root_url": "https://api.example.com",
                "token": invalid_token,
            },
        )
        assert invalid.status_code == 422
        assert invalid_token not in invalid.text
        assert "input" not in invalid.json()["detail"][0]

        invalid_route = "/v3/titles/{id}\nnever-echo-this-route"
        invalid = client.post(
            "/api/jobs",
            json={
                "root_url": "https://api.example.com",
                "title_path_template": invalid_route,
                "version_path_template": "/v3/versions/{id}",
                "token": "test-token",
            },
        )
        assert invalid.status_code == 422
        assert invalid_route not in invalid.text
        assert "input" not in invalid.json()["detail"][0]


def test_runtime_endpoint_reports_source_mode() -> None:
    checker.configure_shutdown_handler(None)
    with TestClient(checker.app) as client:
        runtime = client.get("/api/runtime")
        assert runtime.status_code == 200
        assert runtime.json()["packaged_app"] is False
        assert runtime.json()["can_shutdown"] is False

        shutdown = client.post("/api/shutdown")
        assert shutdown.status_code == 404


def test_batch_generates_summary_and_detailed_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_dir = tmp_path / "outputs"
    monkeypatch.setattr(checker, "OUTPUT_DIR", output_dir)
    checker.jobs.clear()

    requested_paths: list[str] = []
    bearer_token = "test-bearer-token"

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        assert request.headers["authorization"] == f"Bearer {bearer_token}"
        if request.url.path.endswith("/OTP:1TGOOD/status"):
            return httpx.Response(
                200,
                json={"result": "good", "tokenEcho": bearer_token},
                headers={"X-Test": "yes"},
            )
        if request.url.path.endswith("/1VMISSING"):
            return httpx.Response(404, json={"message": "missing"})
        return httpx.Response(503, text="temporarily unavailable")

    ids = ["1TGOOD", "1VMISSING", "BAD-PREFIX", "1TERROR"]
    job = checker.make_job(ids)
    request = checker.JobRequest(
        root_url="https://api.example.com/base/",
        title_path_template=f"/Custom/{bearer_token}/Titles/OTP:{{id}}/status",
        version_path_template="/custom/Versions/{id}",
        token=bearer_token,
        delay_seconds=0,
        timeout_seconds=5,
    )
    transport = httpx.MockTransport(handler)

    asyncio.run(checker.run_job(job, request, ids, transport=transport))

    assert job.status == "completed"
    assert job.processed == 4
    assert job.ok_count == 1
    assert job.not_found_count == 1
    assert job.error_count == 1
    assert job.skipped_count == 1
    assert requested_paths == [
        "/base/Custom/test-bearer-token/Titles/OTP:1TGOOD/status",
        "/base/custom/Versions/1VMISSING",
        "/base/Custom/test-bearer-token/Titles/OTP:1TERROR/status",
    ]

    assert job.summary_path is not None
    summary = job.summary_path.read_text(encoding="utf-8")
    assert "1TGOOD - OK (200)" in summary
    assert "1VMISSING - NOT FOUND (404)" in summary
    assert "BAD-PREFIX - SKIPPED" in summary
    assert "1TERROR - ERROR (503 Service Unavailable)" in summary
    assert bearer_token not in summary
    assert "1T title path: /Custom/<redacted>/Titles/OTP:{id}/status" in summary

    assert job.details_path is not None
    details = job.details_path.read_text(encoding="utf-8")
    assert (
        "GET https://api.example.com/base/Custom/<redacted>/Titles/OTP:1TGOOD/status"
        in details
    )
    assert "1T title path: /Custom/<redacted>/Titles/OTP:{id}/status" in details
    assert "1V version path: /custom/Versions/{id}" in details
    assert '"result":"good"' in details.replace(" ", "")
    assert "authorization: <redacted>" in details.lower()
    assert bearer_token not in details


def test_transport_error_is_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(checker, "OUTPUT_DIR", tmp_path / "outputs")
    checker.jobs.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    ids = ["1TFAIL"]
    job = checker.make_job(ids)
    request = checker.JobRequest(
        root_url="https://api.example.com",
        token="transport-error-token",
        delay_seconds=0,
    )
    asyncio.run(
        checker.run_job(job, request, ids, transport=httpx.MockTransport(handler))
    )

    assert job.status == "completed"
    assert job.error_count == 1
    assert job.summary_path is not None
    assert "1TFAIL - REQUEST ERROR (ConnectError: connection refused)" in (
        job.summary_path.read_text(encoding="utf-8")
    )


def test_bearer_token_is_sent_directly_and_redacted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(checker, "OUTPUT_DIR", tmp_path / "outputs")
    checker.jobs.clear()
    seen_authorization: list[str] = []
    seen_methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers.get("authorization", "")
        seen_authorization.append(authorization)
        seen_methods.append(request.method)
        assert authorization == "Bearer very-secret-token"
        return httpx.Response(
            200,
            json={
                "result": "good",
                "tokenEcho": "very-secret-token",
            },
        )

    ids = ["1TGOOD"]
    job = checker.make_job(ids)
    request = checker.JobRequest(
        root_url="https://api.example.com",
        token="very-secret-token",
        delay_seconds=0,
    )
    asyncio.run(
        checker.run_job(
            job,
            request,
            ids,
            transport=httpx.MockTransport(handler),
        )
    )

    assert job.status == "completed"
    assert job.ok_count == 1
    assert seen_methods == ["GET"]
    assert seen_authorization == ["Bearer very-secret-token"]
    assert job.details_path is not None
    details = job.details_path.read_text(encoding="utf-8")
    assert "Authentication: Bearer token" in details
    assert "authorization: <redacted>" in details.lower()
    assert "very-secret-token" not in details


def test_missing_input_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(checker, "INPUT_FILE", tmp_path / "missing.txt")
    with TestClient(checker.app) as client:
        response = client.post(
            "/api/jobs",
            json={
                "root_url": "https://api.example.com",
                "token": "test-token",
            },
        )
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "input.txt was not found beside the application."
    )
