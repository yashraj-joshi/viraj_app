# API ID Status Checker

A local FastAPI application that reads one ID per line from `input.txt`, calls
the appropriate API route, and produces two timestamped text files:

- `summary_*.txt` — one result line per input ID
- `details_*.txt` — the sanitized request, response status, headers, body, and
  timing for each API call

## Run the macOS application

The packaged Finder application is:

`API ID Status Checker.app`

Keep the application, `input.txt`, and the `outputs/` folder together in this
`viraj_app` folder. Double-click the application in Finder. It starts a private
server on `127.0.0.1` and opens the form in your default browser.

If port 8000 is already occupied, the application automatically selects another
available local port. Closing the browser does not stop the application; quit
**API ID Status Checker** from the Dock or Activity Monitor when finished.

This build is for Apple Silicon Macs running macOS 11 or newer. It is locally
signed but not notarized for distribution to other Macs.

## Routing

| ID prefix | Editable default path template |
| --- | --- |
| `1T` | `/v3/titles/{id}` |
| `1V` | `/v3/versions/{id}` |

Both templates can be edited in the form, must begin with exactly one `/`, and
must contain `{id}` exactly once. The placeholder may be its own path segment,
as in `/v3/titles/{id}`, or part of a segment, as in
`/v1/titles/OTP:{id}`. The root URL and selected path are joined with exactly
one slash. Path case is preserved and may matter to the server. The ID is
safely percent-encoded before it replaces `{id}`.

The prefix check is case-sensitive. Blank lines are ignored. IDs with any other
prefix are recorded as skipped and do not result in an API call.

## Run from the Python source

Python 3.13 is recommended.

```bash
cd /Users/yashrajjoshi/Downloads/viraj_app
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

Then open <http://127.0.0.1:8000>.

1. Replace the sample values in `input.txt` with the real IDs, one per line.
2. Enter the root API URL.
3. Review or edit the `1T` title and `1V` version path templates.
4. Enter the bearer token.
5. Start the check. The page shows live progress.
6. Download the summary and detailed logs when the run completes. Copies also
   remain in the local `outputs/` directory.

## Authentication

Enter the access token directly in the password-style **Bearer token** field.
Every API request sends it as:

```text
Authorization: Bearer <token>
```

The app does not support Basic authentication, client ID/client secret
authentication, OAuth token acquisition, or unauthenticated requests. A pasted
`Bearer ` prefix is accepted and normalized.

The token is kept only in memory while the job runs, cleared from the browser
form after the job starts, and never placed in a request URL or saved by the
application. Authorization headers, bearer-token values, cookies, and API keys
are redacted from the output logs.

## Result interpretation

- Exactly `200` is `OK`.
- `404` is `NOT FOUND`.
- Every other HTTP status is `ERROR`.
- Network, timeout, DNS, and TLS failures are `REQUEST ERROR`.
- Redirects are not followed; a redirect is recorded as an error.

Requests run sequentially with a default 0.2-second delay and a 30-second
timeout. Both values can be changed under **Request timing** in the form.

Text/JSON/XML response bodies are logged up to 200,000 characters per response.
Larger bodies are marked as truncated, and binary bodies are recorded by size
without dumping their bytes.

## Run the tests

```bash
source .venv/bin/activate
pytest -q
```

## Rebuild the macOS application

The repeatable build script creates an Apple Silicon `.app` using Python 3.13
and PyInstaller:

```bash
./build_macos_app.sh
```

## Privacy and network behavior

The server command binds only to `127.0.0.1`. Output files are created with
owner-only permissions. The root URL must use HTTP or HTTPS and cannot contain
embedded credentials, query parameters, or a fragment.
