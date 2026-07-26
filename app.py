from __future__ import annotations

import asyncio
import os
import re
import secrets
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


SOURCE_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))


def external_data_dir() -> Path:
    """Return the editable folder beside the .app when running from Finder."""
    if not getattr(sys, "frozen", False):
        return SOURCE_DIR

    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.suffix.lower() == ".app":
            return parent.parent
    return executable.parent


APP_DIR = external_data_dir()
INPUT_FILE = APP_DIR / "input.txt"
OUTPUT_DIR = APP_DIR / "outputs"
TEMPLATES_DIR = RESOURCE_DIR / "templates"
STATIC_DIR = RESOURCE_DIR / "static"

MAX_LOGGED_BODY_CHARS = 200_000
DEFAULT_TITLE_PATH_TEMPLATE = "/v3/titles/{id}"
DEFAULT_VERSION_PATH_TEMPLATE = "/v3/versions/{id}"
SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_url: str = Field(min_length=1, max_length=2048)
    title_path_template: str = Field(
        default=DEFAULT_TITLE_PATH_TEMPLATE,
        min_length=1,
        max_length=2048,
    )
    version_path_template: str = Field(
        default=DEFAULT_VERSION_PATH_TEMPLATE,
        min_length=1,
        max_length=2048,
    )
    token: SecretStr = Field(min_length=1, max_length=16_384)
    delay_seconds: float = Field(default=0.2, ge=0, le=30)
    timeout_seconds: float = Field(default=30, ge=1, le=300)

    @field_validator("root_url")
    @classmethod
    def validate_root_url(cls, value: str) -> str:
        return validate_http_url(value, field_name="Root URL", allow_query=False)

    @field_validator("title_path_template")
    @classmethod
    def validate_title_path_template(cls, value: str) -> str:
        return validate_route_template(value, field_name="1T title path")

    @field_validator("version_path_template")
    @classmethod
    def validate_version_path_template(cls, value: str) -> str:
        return validate_route_template(value, field_name="1V version path")

    @field_validator("token", mode="before")
    @classmethod
    def validate_token(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if "\r" in value or "\n" in value:
            raise ValueError("Token must not contain line breaks.")
        token = value.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token:
            raise ValueError("Token is required.")
        return token


@dataclass
class JobState:
    id: str
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    created_at: str = field(default_factory=lambda: utc_now().isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    total: int = 0
    processed: int = 0
    ok_count: int = 0
    not_found_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    current_id: str | None = None
    error: str | None = None
    summary_path: Path | None = None
    details_path: Path | None = None

    def as_dict(self) -> dict[str, object]:
        progress = 0 if self.total == 0 else round((self.processed / self.total) * 100, 1)
        result: dict[str, object] = {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total": self.total,
            "processed": self.processed,
            "progress_percent": progress,
            "ok_count": self.ok_count,
            "not_found_count": self.not_found_count,
            "error_count": self.error_count,
            "skipped_count": self.skipped_count,
            "current_id": self.current_id,
            "error": self.error,
        }
        if self.summary_path and self.summary_path.exists():
            result["summary_download_url"] = f"/api/jobs/{self.id}/files/summary"
        if self.details_path and self.details_path.exists():
            result["details_download_url"] = f"/api/jobs/{self.id}/files/details"
        return result


jobs: dict[str, JobState] = {}
shutdown_handler: Callable[[], None] | None = None

app = FastAPI(
    title="API ID Status Checker",
    version="1.3.0",
    description="Checks title and version IDs against a configured API.",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    safe_errors = []
    for error in exc.errors():
        safe_error = dict(error)
        safe_error.pop("input", None)
        safe_errors.append(safe_error)
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": safe_errors}),
    )


def configure_shutdown_handler(handler: Callable[[], None] | None) -> None:
    global shutdown_handler
    shutdown_handler = handler


def utc_now() -> datetime:
    return datetime.now(UTC)


def validate_http_url(value: str, *, field_name: str, allow_query: bool) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be a complete http:// or https:// URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field_name} must not contain embedded credentials.")
    if parsed.fragment:
        raise ValueError(f"{field_name} must not contain a URL fragment.")
    if parsed.query and not allow_query:
        raise ValueError(f"{field_name} must not contain query parameters.")

    normalized_path = parsed.path.rstrip("/")
    normalized = urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            normalized_path,
            parsed.query if allow_query else "",
            "",
        )
    )
    return normalized


def validate_route_template(value: str, *, field_name: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field_name} must not contain control characters.")

    candidate = value.strip()
    if not candidate:
        raise ValueError(f"{field_name} is required.")
    if any(character.isspace() for character in candidate):
        raise ValueError(f"{field_name} must not contain whitespace.")
    if "\\" in candidate:
        raise ValueError(f"{field_name} must use forward slashes.")
    if not candidate.startswith("/") or candidate.startswith("//"):
        raise ValueError(
            f"{field_name} must be a path beginning with one forward slash."
        )

    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"{field_name} must be a path, not a complete URL.")
    if "?" in candidate:
        raise ValueError(f"{field_name} must not contain query parameters.")
    if "#" in candidate:
        raise ValueError(f"{field_name} must not contain a URL fragment.")
    if "//" in candidate:
        raise ValueError(f"{field_name} must not contain a double slash.")
    if candidate.count("{id}") != 1:
        raise ValueError(f"{field_name} must contain exactly one {{id}} placeholder.")

    remaining = candidate.replace("{id}", "")
    if "{" in remaining or "}" in remaining:
        raise ValueError(f"{field_name} contains an unsupported placeholder.")

    decoded_path = candidate
    for _ in range(len(candidate) + 1):
        if re.search(r"%(?![0-9A-Fa-f]{2})", decoded_path):
            raise ValueError(f"{field_name} contains invalid percent encoding.")
        try:
            next_decoded_path = unquote(decoded_path, errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"{field_name} contains invalid UTF-8 percent encoding."
            ) from exc
        if next_decoded_path == decoded_path:
            break
        decoded_path = next_decoded_path
    else:
        raise ValueError(f"{field_name} contains excessive percent encoding.")

    if any(ord(character) < 32 or ord(character) == 127 for character in decoded_path):
        raise ValueError(f"{field_name} must not contain encoded control characters.")
    if any(character.isspace() for character in decoded_path):
        raise ValueError(f"{field_name} must not contain encoded whitespace.")
    if "?" in decoded_path:
        raise ValueError(f"{field_name} must not contain an encoded query marker.")
    if "#" in decoded_path:
        raise ValueError(f"{field_name} must not contain an encoded fragment marker.")
    if "\\" in decoded_path:
        raise ValueError(f"{field_name} must not contain encoded backslashes.")
    if decoded_path.count("/") != candidate.count("/"):
        raise ValueError(f"{field_name} must not contain encoded forward slashes.")
    if "//" in decoded_path:
        raise ValueError(f"{field_name} must not contain an encoded double slash.")
    if decoded_path.count("{id}") != 1:
        raise ValueError(
            f"{field_name} must contain exactly one unencoded {{id}} placeholder."
        )
    decoded_remaining = decoded_path.replace("{id}", "")
    if "{" in decoded_remaining or "}" in decoded_remaining:
        raise ValueError(f"{field_name} contains an encoded unsupported placeholder.")

    for segment in decoded_path.split("/"):
        if segment in {".", ".."}:
            raise ValueError(f"{field_name} must not contain path traversal segments.")

    return candidate


def read_input_ids(path: Path | None = None) -> list[str]:
    selected_path = INPUT_FILE if path is None else path
    if not selected_path.exists():
        raise FileNotFoundError(f"Input file not found: {selected_path}")
    text = selected_path.read_text(encoding="utf-8-sig")
    return [line.strip() for line in text.splitlines() if line.strip()]


def endpoint_for_id(
    api_id: str,
    *,
    title_path_template: str = DEFAULT_TITLE_PATH_TEMPLATE,
    version_path_template: str = DEFAULT_VERSION_PATH_TEMPLATE,
) -> str | None:
    encoded_id = quote(api_id, safe="")
    if api_id.startswith("1T"):
        return title_path_template.replace("{id}", encoded_id)
    if api_id.startswith("1V"):
        return version_path_template.replace("{id}", encoded_id)
    return None


def join_root_and_endpoint(root_url: str, endpoint: str) -> str:
    return f"{root_url.rstrip('/')}/{endpoint.lstrip('/')}"


def reason_phrase(status_code: int, fallback: str = "") -> str:
    if fallback:
        return fallback.replace("\r", " ").replace("\n", " ").strip()
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Unknown Status"


def redact_text(value: str, secret_values: list[str]) -> str:
    redacted = value
    for secret_value in sorted(
        {item for item in secret_values if item}, key=len, reverse=True
    ):
        redacted = redacted.replace(secret_value, "<redacted>")
    return redacted


def format_headers(headers: httpx.Headers, secret_values: list[str]) -> str:
    lines: list[str] = []
    for name, value in headers.multi_items():
        safe_name = redact_text(name, secret_values)
        safe_value = "<redacted>" if name.lower() in SENSITIVE_HEADERS else value
        safe_value = redact_text(safe_value, secret_values)
        lines.append(f"{safe_name}: {safe_value}")
    return "\n".join(lines) if lines else "(none)"


def format_response_body(response: httpx.Response, secret_values: list[str]) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if not response.content:
        return "(empty)"
    if not (
        content_type.startswith("text/")
        or "json" in content_type
        or "xml" in content_type
        or "javascript" in content_type
        or "x-www-form-urlencoded" in content_type
    ):
        return f"(binary response: {len(response.content)} bytes, not rendered)"

    body = redact_text(response.text, secret_values)
    if len(body) <= MAX_LOGGED_BODY_CHARS:
        return body
    omitted = len(body) - MAX_LOGGED_BODY_CHARS
    return (
        body[:MAX_LOGGED_BODY_CHARS]
        + f"\n\n... response body truncated; {omitted:,} characters omitted ..."
    )


def output_file_names(job_id: str) -> tuple[Path, Path]:
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
    suffix = job_id[:8]
    return (
        OUTPUT_DIR / f"summary_{timestamp}_{suffix}.txt",
        OUTPUT_DIR / f"details_{timestamp}_{suffix}.txt",
    )


def make_job(ids: list[str]) -> JobState:
    job_id = secrets.token_hex(16)
    summary_path, details_path = output_file_names(job_id)
    job = JobState(
        id=job_id,
        total=len(ids),
        summary_path=summary_path,
        details_path=details_path,
    )
    jobs[job_id] = job
    return job


def write_log_header(
    file_handle,
    *,
    title: str,
    job: JobState,
    request: JobRequest,
    secret_values: list[str],
) -> None:
    file_handle.write(f"{title}\n")
    file_handle.write("=" * 78 + "\n")
    file_handle.write(f"Job ID: {job.id}\n")
    file_handle.write(f"Started (UTC): {job.started_at}\n")
    file_handle.write(
        f"Root URL: {redact_text(request.root_url, secret_values)}\n"
    )
    file_handle.write(
        "1T title path: "
        f"{redact_text(request.title_path_template, secret_values)}\n"
    )
    file_handle.write(
        "1V version path: "
        f"{redact_text(request.version_path_template, secret_values)}\n"
    )
    file_handle.write("Authentication: Bearer token\n")
    file_handle.write(f"Request timeout: {request.timeout_seconds:g} seconds\n")
    file_handle.write(f"Delay between requests: {request.delay_seconds:g} seconds\n")
    file_handle.write(f"Input records: {job.total}\n")
    file_handle.write("=" * 78 + "\n\n")


async def run_job(
    job: JobState,
    request: JobRequest,
    ids: list[str],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    job.status = "running"
    job.started_at = utc_now().isoformat()

    assert job.summary_path is not None
    assert job.details_path is not None

    token = request.token.get_secret_value()
    secret_values = [token, quote(token, safe="")]

    timeout = httpx.Timeout(request.timeout_seconds)
    client_options: dict[str, object] = {
        "timeout": timeout,
        "follow_redirects": False,
        "transport": transport,
        "headers": {
            "Accept": "application/json",
            "User-Agent": "api-id-status-checker/1.3",
        },
    }

    try:
        with (
            job.summary_path.open("x", encoding="utf-8", buffering=1) as summary_file,
            job.details_path.open("x", encoding="utf-8", buffering=1) as details_file,
        ):
            os.chmod(job.summary_path, 0o600)
            os.chmod(job.details_path, 0o600)
            write_log_header(
                summary_file,
                title="API ID CHECK - SUMMARY",
                job=job,
                request=request,
                secret_values=secret_values,
            )
            write_log_header(
                details_file,
                title="API ID CHECK - DETAILED REQUEST / RESPONSE LOG",
                job=job,
                request=request,
                secret_values=secret_values,
            )

            async with httpx.AsyncClient(**client_options) as client:
                request_headers = {"Authorization": f"Bearer {token}"}

                for index, api_id in enumerate(ids, start=1):
                    job.current_id = api_id
                    safe_api_id = redact_text(api_id, secret_values)
                    endpoint = endpoint_for_id(
                        api_id,
                        title_path_template=request.title_path_template,
                        version_path_template=request.version_path_template,
                    )
                    details_file.write(
                        f"{'=' * 78}\n"
                        f"[{index}/{job.total}] ID: {safe_api_id}\n"
                        f"Started (UTC): {utc_now().isoformat()}\n"
                    )

                    if endpoint is None:
                        message = (
                            f"{safe_api_id} - SKIPPED "
                            "(unsupported prefix; expected 1T or 1V)"
                        )
                        summary_file.write(message + "\n")
                        details_file.write(
                            "Request: not sent\n"
                            "Result: unsupported ID prefix; expected 1T or 1V\n\n"
                        )
                        job.skipped_count += 1
                        job.processed += 1
                        continue

                    url = join_root_and_endpoint(request.root_url, endpoint)
                    started = asyncio.get_running_loop().time()
                    try:
                        response = await client.get(url, headers=request_headers)
                        elapsed = asyncio.get_running_loop().time() - started
                        phrase = reason_phrase(
                            response.status_code, response.reason_phrase
                        )
                        safe_phrase = redact_text(phrase, secret_values)

                        if response.status_code == 200:
                            summary_line = f"{safe_api_id} - OK (200)"
                            job.ok_count += 1
                        elif response.status_code == 404:
                            summary_line = f"{safe_api_id} - NOT FOUND (404)"
                            job.not_found_count += 1
                        else:
                            summary_line = (
                                f"{safe_api_id} - ERROR "
                                f"({response.status_code} {safe_phrase})"
                            )
                            job.error_count += 1

                        summary_file.write(summary_line + "\n")
                        details_file.write(
                            f"Request:\n"
                            f"{response.request.method} "
                            f"{redact_text(str(response.request.url), secret_values)}\n"
                            f"{format_headers(response.request.headers, secret_values)}\n\n"
                            f"Response:\n"
                            f"Status: {response.status_code} {safe_phrase}\n"
                            f"Elapsed: {elapsed:.3f} seconds\n"
                            f"{format_headers(response.headers, secret_values)}\n\n"
                            f"Body:\n"
                            f"{format_response_body(response, secret_values)}\n\n"
                        )
                    except httpx.HTTPError as exc:
                        elapsed = asyncio.get_running_loop().time() - started
                        safe_error = redact_text(
                            f"{type(exc).__name__}: {exc}", secret_values
                        )
                        summary_file.write(
                            f"{safe_api_id} - REQUEST ERROR ({safe_error})\n"
                        )
                        details_file.write(
                            "Request:\n"
                            f"GET {redact_text(url, secret_values)}\n"
                            "Authorization: <redacted>\n\n"
                            "Response: not received\n"
                            f"Elapsed: {elapsed:.3f} seconds\n"
                            f"Error: {safe_error}\n\n"
                        )
                        job.error_count += 1

                    job.processed += 1
                    if index < len(ids) and request.delay_seconds:
                        await asyncio.sleep(request.delay_seconds)

            summary_file.write(
                "\n"
                + "=" * 78
                + "\n"
                + f"Finished (UTC): {utc_now().isoformat()}\n"
                + f"OK: {job.ok_count}\n"
                + f"Not found: {job.not_found_count}\n"
                + f"Other errors: {job.error_count}\n"
                + f"Skipped: {job.skipped_count}\n"
            )

        job.status = "completed"
    except Exception as exc:
        job.status = "failed"
        safe_message = redact_text(f"{type(exc).__name__}: {exc}", secret_values)
        job.error = safe_message
        if job.details_path.exists():
            with job.details_path.open("a", encoding="utf-8") as details_file:
                details_file.write(
                    f"\n{'=' * 78}\nJOB FAILED\nError: {safe_message}\n"
                )
    finally:
        job.current_id = None
        job.finished_at = utc_now().isoformat()


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(TEMPLATES_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runtime")
async def runtime_info() -> dict[str, object]:
    return {
        "packaged_app": bool(getattr(sys, "frozen", False)),
        "data_directory": str(APP_DIR),
        "can_shutdown": shutdown_handler is not None,
    }


@app.post("/api/shutdown")
async def shutdown_application(
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    if shutdown_handler is None:
        raise HTTPException(
            status_code=404,
            detail="Application shutdown is available only in the packaged app.",
        )
    background_tasks.add_task(shutdown_handler)
    return {"status": "shutting_down"}


@app.get("/api/input-preview")
async def input_preview() -> dict[str, object]:
    try:
        ids = read_input_ids()
    except (OSError, UnicodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "input_file": str(INPUT_FILE),
        "count": len(ids),
        "title_count": sum(item.startswith("1T") for item in ids),
        "version_count": sum(item.startswith("1V") for item in ids),
        "unsupported_count": sum(
            not (item.startswith("1T") or item.startswith("1V")) for item in ids
        ),
        "sample": ids[:5],
    }


@app.post("/api/jobs", status_code=202)
async def create_job(
    request: JobRequest, background_tasks: BackgroundTasks
) -> dict[str, object]:
    try:
        ids = read_input_ids()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail="input.txt was not found beside the application.",
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not read input.txt: {exc}") from exc

    if not ids:
        raise HTTPException(
            status_code=400,
            detail="input.txt contains no IDs. Put one ID on each line.",
        )

    job = make_job(ids)
    background_tasks.add_task(run_job, job, request, ids)
    return job.as_dict()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, object]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.as_dict()


@app.get("/api/jobs/{job_id}/files/{file_kind}")
async def download_output(job_id: str, file_kind: Literal["summary", "details"]) -> FileResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    path = job.summary_path if file_kind == "summary" else job.details_path
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Output file is not available yet.")
    return FileResponse(path, media_type="text/plain", filename=path.name)
