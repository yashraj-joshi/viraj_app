# Regeneration prompt: API ID Status Checker for macOS

Copy everything between **BEGIN PROMPT** and **END PROMPT** into a capable
macOS coding agent.

---

## BEGIN PROMPT

You are an expert macOS and Python packaging engineer. Complete this task
autonomously, validate the finished artifact, and do not stop after merely
writing source code.

### Goal

Create this destination:

`/Users/yashrajjoshi/Downloads/my_app`

It must contain a Finder-launchable application named:

`API ID Status Checker.app`

It must also contain `input.txt`, an empty `outputs/` directory, the complete
maintainable Python source project, tests, dependency files, the custom app icon
builder, and a repeatable macOS build script.

Do not modify or delete either of these existing projects:

- `/Users/yashrajjoshi/Downloads/viraj`
- `/Users/yashrajjoshi/Downloads/viraj_app`

### Important definition of “exact”

A fresh PyInstaller build cannot be guaranteed byte-for-byte identical because
build timestamps, dependency metadata, Mach-O UUIDs, and signatures can change.
Therefore:

1. If `/Users/yashrajjoshi/Downloads/viraj_app` exists and contains a valid
   `API ID Status Checker.app`, treat it as the canonical source and duplicate
   it without rebuilding. This is the required primary workflow and is the only
   way to preserve the exact existing app bundle.
2. Use the rebuild specification later in this prompt only if the canonical
   source is missing or invalid. A rebuild must be functionally and
   structurally identical, but it may not be byte-for-byte identical.

### Destination safety

Inspect `/Users/yashrajjoshi/Downloads/my_app` before writing:

- If it does not exist, create it.
- If it exists and is empty, reuse it.
- If it contains files, do not delete or overwrite them silently. Compare it
  with the canonical source. If it is already an exact copy, continue with
  validation. Otherwise stop and clearly report the conflict.

### Primary workflow: exact duplication

1. Verify the canonical app before copying:

   - `plutil -lint` must accept its `Contents/Info.plist`.
   - `codesign --verify --deep --strict` must succeed.
   - Its executable must be a Mach-O 64-bit `arm64` executable.
   - `CFBundleIdentifier` must be
     `com.local.api-id-status-checker`.
   - `CFBundleShortVersionString` must be `1.3.0`.
   - `CFBundleVersion` must be `4`.
   - `LSMinimumSystemVersion` must be `11.0`.

2. Copy the complete contents of
   `/Users/yashrajjoshi/Downloads/viraj_app` into
   `/Users/yashrajjoshi/Downloads/my_app`.

   Use `/usr/bin/ditto` so macOS bundle metadata, executable permissions,
   symlinks, extended attributes, and the `.app` structure are preserved. Do
   not use a copying method that dereferences or loses bundle symlinks.

3. Do not rebuild or re-sign a valid copied app. Re-signing would make it
   different from the canonical bundle.

4. Make sure `my_app/outputs/` exists and is empty. Do not copy old generated
   summary or detailed logs. Keep the copied `input.txt` sample.

5. Remove only generated caches from the new copy, if present:

   - `__pycache__/`
   - `.pytest_cache/`
   - `.DS_Store`

   Do not remove source files or anything from the canonical project.

### Required destination structure

The final result must look like this:

```text
/Users/yashrajjoshi/Downloads/my_app/
├── API ID Status Checker.app
├── input.txt
├── outputs/
├── app.py
├── mac_app_launcher.py
├── build_macos_app.sh
├── requirements.txt
├── requirements-dev.txt
├── requirements-build.txt
├── pytest.ini
├── README.md
├── REGENERATION_PROMPT.md
├── .gitignore
├── static/
│   ├── app.js
│   └── styles.css
├── templates/
│   └── index.html
├── packaging/
│   └── make_icon.py
└── tests/
    └── test_app.py
```

The `.app` is internally a macOS application bundle (a directory), but it must
appear as one application icon in Finder. Do not replace it with a loose
executable.

### Functional behavior that must be preserved

The application is a local FastAPI batch API checker.

#### Input

- Read `/Users/yashrajjoshi/Downloads/my_app/input.txt`.
- Read UTF-8 with optional BOM.
- One ID per line.
- Trim surrounding whitespace and ignore blank lines.
- Preserve order and process duplicate IDs independently.
- IDs and output data must never be written inside the `.app` bundle.

The sample file contains:

```text
1T00000001
1T00000002
1V00000001
1V00000002
```

#### Routing

- Provide two editable path-only templates:

  - `title_path_template`, default `/v3/titles/{id}`
  - `version_path_template`, default `/v3/versions/{id}`

- Each template must contain exactly one literal `{id}` and must begin with
  exactly one `/`. The placeholder may be a complete path segment or embedded
  within a segment, such as `/v1/titles/OTP:{id}`.
- Preserve the user-entered path case. Both defaults intentionally use
  lowercase `v3`.
- Reject absolute or protocol-relative URLs, query strings, fragments, double
  slashes, backslashes, whitespace/control characters, traversal segments,
  missing/repeated `{id}`, and unsupported brace placeholders.
- Join the normalized root URL and selected template with exactly one slash
  while retaining any root base path. Do not use `urljoin`.
- Prefix matching is case-sensitive.
- Apply path-segment percent encoding to the entire ID before replacing `{id}`;
  static text may remain before or after the encoded ID in that segment.
- Unsupported prefixes are recorded as skipped and do not cause an HTTP call.

#### HTTP and result rules

- Perform sequential asynchronous GET requests using `httpx.AsyncClient`.
- Default delay between requests: `0.2` seconds.
- Default timeout: `30` seconds.
- Both values are configurable in the form.
- Keep TLS verification enabled.
- Do not follow redirects.
- Exactly HTTP `200` means `OK`.
- HTTP `404` means `NOT FOUND`.
- Every other HTTP status means `ERROR`.
- Timeout, DNS, connection, and TLS failures mean `REQUEST ERROR`.

#### Authentication

The web form has exactly one authentication method: a required user-supplied
bearer token. Send every API GET with:

```text
Authorization: Bearer <token>
```

Accept the raw token and safely normalize a pasted leading `Bearer ` prefix.
Do not support HTTP Basic, client IDs, client secrets, OAuth token acquisition,
token URLs, scope, audience, or unauthenticated requests. Reject legacy
authentication fields in the job API instead of silently accepting them.

Keep the token only in memory while the job runs. Do not place it in request
URLs or persist it. Validation-error responses must not echo invalid token input.

#### Output files

Create the output files only in:

`/Users/yashrajjoshi/Downloads/my_app/outputs`

Each run creates two unique timestamped files:

- `summary_YYYYMMDD_HHMMSS_JOBID.txt`
- `details_YYYYMMDD_HHMMSS_JOBID.txt`

Create them with owner-only permissions (`0600`).

Summary examples:

```text
1T123 - OK (200)
1V456 - NOT FOUND (404)
1T789 - ERROR (503 Service Unavailable)
1TFAIL - REQUEST ERROR (ConnectError: connection refused)
BAD - SKIPPED (unsupported prefix; expected 1T or 1V)
```

The log header records the configured root URL and both route templates. The
detailed log records each ID, sanitized request URL and headers, response
status, elapsed time, response headers, and response body. Redact:

- `Authorization`
- Bearer tokens
- cookies
- proxy authorization
- API-key headers

Redact the token anywhere it appears, including response bodies and error text.
Log textual response bodies up to 200,000 characters per response, mark larger
bodies as truncated, and record binary responses by size without dumping their
bytes.

#### Web interface

Preserve the polished responsive interface with:

- Root API URL field
- Editable `1T` title and `1V` version path-template fields, prefilled with the
  defaults above
- Live `1T` and `1V` composed-request previews that update as the root URL or
  templates change
- A concise note that `{id}` is required exactly once, may be embedded within a
  path segment, path case matters, and the root/path boundary always uses
  exactly one slash
- One required password-style bearer-token field
- Show/hide token control
- Configurable delay and timeout
- Visible `1T` and `1V` routing cards
- Live input preview and counts
- Background-job progress
- Counts for OK, 404, errors, and skipped IDs
- Download links for summary and detailed logs
- Responsive desktop/mobile styling
- A packaged-only “Quit application” control

The token must be cleared from the browser form after a job starts.
Use text-safe DOM APIs for dynamic values.

#### FastAPI endpoints

Preserve these endpoints:

- `GET /`
- `GET /health`
- `GET /api/runtime`
- `POST /api/shutdown`
- `GET /api/input-preview`
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/files/summary`
- `GET /api/jobs/{job_id}/files/details`

Jobs run in the background and expose live polling status. The shutdown endpoint
must be unavailable during ordinary source execution and enabled only by the
packaged launcher.

`POST /api/jobs` and the generated OpenAPI schema must expose
`title_path_template` and `version_path_template` alongside the root URL, token,
delay, and timeout. Reject unexpected fields.

### Runtime path behavior

The app must use two path roots:

- Bundled read-only resources (`templates/` and `static/`) come from
  `sys._MEIPASS` when frozen.
- Editable data (`input.txt` and `outputs/`) comes from the directory containing
  the `.app`, derived from `sys.executable`.

Never derive editable paths from the current working directory; Finder launch
working directories are unreliable.

When the copied app is launched from `my_app`, `GET /api/runtime` and
`GET /api/input-preview` must report the new external directory:

`/Users/yashrajjoshi/Downloads/my_app`

### Native launcher behavior

The packaged launcher must:

- Bind only to `127.0.0.1`.
- Prefer port 8000.
- Automatically bind another available local port if 8000 is occupied.
- Start one Uvicorn server using the asyncio loop and h11 HTTP implementation.
- Open the default browser only after `/health` returns 200.
- Support `API_CHECKER_NO_BROWSER=1` for automated testing.
- Create `outputs/` if missing.
- Create a small sample `input.txt` if it is missing.
- Display a macOS error dialog and write `launcher_error.txt` beside the app if
  startup fails.
- Connect the packaged `POST /api/shutdown` endpoint to
  `server.should_exit = True`.

### Rebuild fallback

Use this only when the canonical `viraj_app` source or `.app` is unavailable or
invalid.

Use:

- Python `3.13.11`
- FastAPI `0.140.0`
- httpx `0.28.1`
- Uvicorn `0.51.0`
- PyInstaller `6.21.0`
- Pillow `12.3.0`
- pytest `9.1.1`

The build must:

1. Create an isolated temporary Python 3.13 virtual environment.
2. Install `requirements-build.txt`.
3. Generate the green/lime custom `.icns` icon using
   `packaging/make_icon.py`.
4. Run PyInstaller using:

   - `--onedir`
   - `--windowed`
   - name `API ID Status Checker`
   - bundle identifier `com.local.api-id-status-checker`
   - the custom `.icns`
   - `templates:templates`
   - `static:static`
   - collected Uvicorn submodules

5. Set:

   - `CFBundleShortVersionString = 1.3.0`
   - `CFBundleVersion = 4`
   - `LSMinimumSystemVersion = 11.0`

6. Ad-hoc sign the result:

   ```bash
   codesign --force --deep --sign - "API ID Status Checker.app"
   ```

7. The build is Apple Silicon `arm64` and must support macOS 11 or newer.
8. Use `/usr/bin/ditto` when staging the final `.app`.
9. Do not leave build virtual environments, PyInstaller work directories,
   caches, or synthetic test output in `my_app`.

### Required verification

Do all of the following before reporting completion:

1. Confirm `my_app/input.txt` exists.
2. Confirm `my_app/outputs/` exists and is empty.
3. Confirm the complete source structure exists.
4. Run the Python tests; all ten tests must pass.
5. Run JavaScript syntax validation.
6. Run:

   ```bash
   plutil -lint \
     "/Users/yashrajjoshi/Downloads/my_app/API ID Status Checker.app/Contents/Info.plist"

   codesign --verify --deep --strict \
     "/Users/yashrajjoshi/Downloads/my_app/API ID Status Checker.app"

   file \
     "/Users/yashrajjoshi/Downloads/my_app/API ID Status Checker.app/Contents/MacOS/API ID Status Checker"
   ```

7. Launch the application through Launch Services/Finder, not only by importing
   Python:

   ```bash
   open -n -g --env API_CHECKER_NO_BROWSER=1 \
     "/Users/yashrajjoshi/Downloads/my_app/API ID Status Checker.app"
   ```

8. Verify:

   - `/health` returns 200.
   - `/api/runtime` reports `packaged_app: true`.
   - `data_directory` is exactly
     `/Users/yashrajjoshi/Downloads/my_app`.
   - `/api/input-preview` reads `my_app/input.txt`.
   - `/openapi.json` exposes both editable route-template fields with the
     correct defaults.
   - Bundled `/`, CSS, and JavaScript load.
   - The bundled UI shows both editable templates and live composed-URL
     previews.
   - `POST /api/shutdown` stops the packaged process cleanly.

9. Occupy port 8000 with a controlled local server, launch the app again, and
   verify it selects another loopback port and still shuts down cleanly.

10. Run a controlled local mock API through all four sample IDs and verify:

    - With defaults, both `1T` requests use `/v3/titles/` and both `1V`
      requests use `/v3/versions/`.
    - A second controlled run with custom mixed-case templates preserves their
      exact case, retains a root base path, substitutes an embedded placeholder
      such as `OTP:{id}`, and contains no double slash at the join boundary.
    - Every outbound API request carries exactly
      `Authorization: Bearer <test-token>`.
    - The summary correctly records controlled 200, 404, and 503 responses.
    - Both output downloads work.
    - Both files are created under `my_app/outputs` with mode `0600`.
    - Neither output file contains the test token.
    - No input or output file is created inside the `.app`.

11. Remove the synthetic mock-run output files afterward, leaving the external
    `outputs/` directory empty and ready for the user.
12. Confirm no test servers or app processes remain running.

### Final response

Lead with the completed application path and state that the original projects
were untouched. Briefly report:

- App path
- Input path
- Output directory
- Architecture and minimum macOS version
- Test count/result
- Signing and Finder-launch result

Do not claim byte-for-byte identity if you had to use the rebuild fallback.

## END PROMPT
