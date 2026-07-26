const form = document.querySelector("#job-form");
const rootUrl = document.querySelector("#root-url");
const titlePathTemplate = document.querySelector("#title-path-template");
const versionPathTemplate = document.querySelector("#version-path-template");
const titleRoutePreview = document.querySelector("#title-route-preview");
const versionRoutePreview = document.querySelector("#version-route-preview");
const titleRouteCard = document.querySelector("#title-route-card");
const versionRouteCard = document.querySelector("#version-route-card");
const token = document.querySelector("#token");
const toggleToken = document.querySelector("#toggle-token");
const runButton = document.querySelector("#run-button");
const formError = document.querySelector("#form-error");
const progressPanel = document.querySelector("#progress-panel");
const jobStatus = document.querySelector("#job-status");
const progressLabel = document.querySelector("#progress-label");
const progressPercent = document.querySelector("#progress-percent");
const progressBar = document.querySelector("#progress-bar");
const progressTrack = document.querySelector(".progress-track");
const currentId = document.querySelector("#current-id");
const jobError = document.querySelector("#job-error");
const downloads = document.querySelector("#downloads");
const summaryDownload = document.querySelector("#summary-download");
const detailsDownload = document.querySelector("#details-download");
const quitApplication = document.querySelector("#quit-application");

let pollTimer = null;

function showError(element, message) {
  element.textContent = message;
  element.hidden = !message;
}

function formatApiError(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item.msg || JSON.stringify(item))
      .join(" ");
  }
  return fallback;
}

function routeTemplateError(value, label) {
  if (/[\u0000-\u001f\u007f]/u.test(value)) {
    return `${label} must not contain control characters.`;
  }
  const template = value.trim();
  if (!template) return `${label} is required.`;
  if (!template.startsWith("/") || template.startsWith("//")) {
    return `${label} must begin with one forward slash.`;
  }
  if (/\s/u.test(template)) return `${label} must not contain whitespace.`;
  if (template.includes("\\")) return `${label} must use forward slashes.`;
  if (template.includes("?")) return `${label} must not contain a query string.`;
  if (template.includes("#")) return `${label} must not contain a fragment.`;
  if (template.includes("//")) return `${label} must not contain a double slash.`;

  const placeholders = template.match(/\{id\}/gu) || [];
  if (placeholders.length !== 1) {
    return `${label} must contain {id} exactly once.`;
  }
  const remaining = template.replace("{id}", "");
  if (remaining.includes("{") || remaining.includes("}")) {
    return `${label} contains an unsupported placeholder.`;
  }
  let decodedPath = template;
  for (
    let decodingPass = 0;
    decodingPass <= template.length;
    decodingPass += 1
  ) {
    let nextDecodedPath = decodedPath;
    try {
      nextDecodedPath = decodeURIComponent(decodedPath);
    } catch {
      return `${label} contains invalid percent encoding.`;
    }
    if (nextDecodedPath === decodedPath) break;
    decodedPath = nextDecodedPath;
  }
  if (/[\u0000-\u001f\u007f]/u.test(decodedPath)) {
    return `${label} must not contain encoded control characters.`;
  }
  if (/\s/u.test(decodedPath)) {
    return `${label} must not contain encoded whitespace.`;
  }
  if (decodedPath.includes("?")) {
    return `${label} must not contain an encoded query marker.`;
  }
  if (decodedPath.includes("#")) {
    return `${label} must not contain an encoded fragment marker.`;
  }
  if (decodedPath.includes("\\")) {
    return `${label} must not contain encoded backslashes.`;
  }
  const slashCount = (valueToCount) =>
    Array.from(valueToCount).filter((character) => character === "/").length;
  if (slashCount(decodedPath) !== slashCount(template)) {
    return `${label} must not contain encoded forward slashes.`;
  }
  if (decodedPath.includes("//")) {
    return `${label} must not contain an encoded double slash.`;
  }
  const decodedPlaceholders = decodedPath.match(/\{id\}/gu) || [];
  if (decodedPlaceholders.length !== 1) {
    return `${label} must contain exactly one unencoded {id} placeholder.`;
  }
  const decodedRemaining = decodedPath.replace("{id}", "");
  if (decodedRemaining.includes("{") || decodedRemaining.includes("}")) {
    return `${label} contains an encoded unsupported placeholder.`;
  }
  for (const segment of decodedPath.split("/")) {
    if (segment === "." || segment === "..") {
      return `${label} must not contain path traversal segments.`;
    }
  }
  return "";
}

function updateRoutePreview(input, preview, card, label, sampleId) {
  const error = routeTemplateError(input.value, label);
  input.setCustomValidity(error);
  if (error) {
    input.setAttribute("aria-invalid", "true");
  } else {
    input.removeAttribute("aria-invalid");
  }
  card.classList.toggle("route-invalid", Boolean(error));
  if (error) {
    preview.textContent = "Fix the route template to preview";
    preview.removeAttribute("title");
    return;
  }

  const root = (rootUrl.value.trim() || rootUrl.placeholder).replace(/\/+$/u, "");
  const path = input.value.trim().replace(
    "{id}",
    encodeURIComponent(sampleId),
  );
  const fullUrl = `${root}/${path.replace(/^\/+/u, "")}`;
  preview.textContent = fullUrl;
  preview.title = fullUrl;
}

function updateRoutePreviews() {
  updateRoutePreview(
    titlePathTemplate,
    titleRoutePreview,
    titleRouteCard,
    "1T title path",
    "1T_EXAMPLE",
  );
  updateRoutePreview(
    versionPathTemplate,
    versionRoutePreview,
    versionRouteCard,
    "1V version path",
    "1V_EXAMPLE",
  );
}

async function readInputPreview() {
  const loading = document.querySelector("#input-loading");
  const state = document.querySelector("#input-state");
  const error = document.querySelector("#input-error");
  loading.hidden = false;
  state.hidden = true;
  showError(error, "");

  try {
    const response = await fetch("/api/input-preview", {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(payload, "Could not read input.txt."));
    }

    document.querySelector("#input-count").textContent = payload.count;
    document.querySelector("#title-count").textContent = payload.title_count;
    document.querySelector("#version-count").textContent = payload.version_count;
    document.querySelector("#unsupported-count").textContent =
      payload.unsupported_count;
    document.querySelector("#input-path").textContent = payload.input_file;

    const sample = document.querySelector("#sample-ids");
    sample.replaceChildren();
    for (const id of payload.sample) {
      const code = document.createElement("code");
      code.textContent = id;
      sample.append(code);
    }
    state.hidden = false;
  } catch (errorValue) {
    showError(error, errorValue.message);
  } finally {
    loading.hidden = true;
  }
}

async function configureRuntimeControls() {
  try {
    const response = await fetch("/api/runtime", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return;
    const runtime = await response.json();
    quitApplication.hidden = !(runtime.packaged_app && runtime.can_shutdown);
  } catch {
    quitApplication.hidden = true;
  }
}

function setRunning(isRunning) {
  runButton.disabled = isRunning;
  document.querySelector(".button-label").textContent = isRunning
    ? "Check in progress…"
    : "Start API check";
}

function updateJobDisplay(job) {
  progressPanel.hidden = false;
  jobStatus.textContent = job.status;
  jobStatus.className = `job-status ${job.status}`;

  const percentage = Number(job.progress_percent || 0);
  progressPercent.textContent = `${percentage}%`;
  progressBar.style.width = `${percentage}%`;
  progressTrack.setAttribute("aria-valuenow", String(percentage));
  progressLabel.textContent = `${job.processed} of ${job.total} processed`;
  currentId.textContent = job.current_id ? `Checking ${job.current_id}` : "";

  document.querySelector("#ok-count").textContent = job.ok_count;
  document.querySelector("#not-found-count").textContent = job.not_found_count;
  document.querySelector("#error-count").textContent = job.error_count;
  document.querySelector("#skipped-count").textContent = job.skipped_count;

  showError(jobError, job.error || "");

  if (job.status === "completed" || job.status === "failed") {
    setRunning(false);
    const hasSummary = Boolean(job.summary_download_url);
    const hasDetails = Boolean(job.details_download_url);
    summaryDownload.hidden = !hasSummary;
    detailsDownload.hidden = !hasDetails;
    if (hasSummary) summaryDownload.href = job.summary_download_url;
    if (hasDetails) detailsDownload.href = job.details_download_url;
    downloads.hidden = !(hasSummary || hasDetails);
  }
}

async function pollJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {
      headers: { Accept: "application/json" },
    });
    const job = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(job, "Could not read job status."));
    }
    updateJobDisplay(job);
    if (job.status === "completed" || job.status === "failed") {
      pollTimer = null;
      return;
    }
    pollTimer = window.setTimeout(() => pollJob(jobId), 500);
  } catch (errorValue) {
    showError(jobError, errorValue.message);
    setRunning(false);
    pollTimer = null;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;

  if (pollTimer) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
  showError(formError, "");
  showError(jobError, "");
  downloads.hidden = true;
  summaryDownload.hidden = false;
  detailsDownload.hidden = false;
  setRunning(true);

  const payload = {
    root_url: rootUrl.value.trim(),
    title_path_template: titlePathTemplate.value.trim(),
    version_path_template: versionPathTemplate.value.trim(),
    token: token.value,
    delay_seconds: Number(document.querySelector("#delay-seconds").value),
    timeout_seconds: Number(document.querySelector("#timeout-seconds").value),
  };

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const job = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(job, "Could not start the API check."));
    }

    token.value = "";
    token.type = "password";
    toggleToken.textContent = "Show";
    toggleToken.setAttribute("aria-label", "Show bearer token");
    updateJobDisplay(job);
    pollJob(job.id);
  } catch (errorValue) {
    showError(formError, errorValue.message);
    setRunning(false);
  }
});

toggleToken.addEventListener("click", () => {
  const reveal = token.type === "password";
  token.type = reveal ? "text" : "password";
  toggleToken.textContent = reveal ? "Hide" : "Show";
  toggleToken.setAttribute(
    "aria-label",
    reveal ? "Hide bearer token" : "Show bearer token",
  );
});
rootUrl.addEventListener("input", updateRoutePreviews);
titlePathTemplate.addEventListener("input", updateRoutePreviews);
versionPathTemplate.addEventListener("input", updateRoutePreviews);
document
  .querySelector("#refresh-input")
  .addEventListener("click", readInputPreview);
quitApplication.addEventListener("click", async () => {
  if (!window.confirm("Quit API ID Status Checker?")) return;
  quitApplication.disabled = true;
  quitApplication.textContent = "Stopping…";
  try {
    const response = await fetch("/api/shutdown", { method: "POST" });
    if (!response.ok) throw new Error("Shutdown request failed.");
    quitApplication.textContent = "Application stopped — close this tab";
  } catch {
    quitApplication.disabled = false;
    quitApplication.textContent = "Quit application";
  }
});

updateRoutePreviews();
readInputPreview();
configureRuntimeControls();
