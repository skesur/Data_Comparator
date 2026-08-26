// ============================================================
// Data Comparator — frontend controller
// No framework: DOM APIs + fetch() against the Django JSON API.
// ============================================================

const API = {
  upload: "/api/upload/",
  dataset: (id) => `/api/datasets/${id}/`,
  datasetFull: (id) => `/api/datasets/${id}/full/`,
  download: (id) => `/api/datasets/${id}/download/`,
  clean: (id) => `/api/datasets/${id}/clean/`,
  reset: (id) => `/api/datasets/${id}/reset/`,
  visualize: (id) => `/api/datasets/${id}/visualize/`,
  compare: (id) => `/api/datasets/${id}/compare/`,
  predict: (runId) => `/api/runs/${runId}/predict/`,
};

const state = {
  datasetId: null,
  filename: null,
  viewingAllRows: false,
  columnsMeta: {},
  lastRunId: null,
  lastRunFeatures: [],
  lastRunBestModel: null,
  lastRunModelNames: [],
};

function csrfToken() {
  return document.querySelector('input[name="csrfmiddlewaretoken"]').value;
}

async function apiFetch(url, options = {}) {
  const opts = {
    method: options.method || "GET",
    headers: { "X-CSRFToken": csrfToken(), ...(options.headers || {}) },
  };
  if (options.body instanceof FormData) {
    opts.body = options.body; // let browser set multipart boundary
  } else if (options.body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(options.body);
  }
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function showError(elId, message) {
  const el = document.getElementById(elId);
  el.textContent = message;
  el.classList.remove("hidden");
}
function clearError(elId) {
  document.getElementById(elId).classList.add("hidden");
}

// ---------------- Step navigation ----------------

function goToStep(stepName) {
  document.querySelectorAll(".step-panel").forEach((p) => p.classList.remove("active"));
  document.getElementById(`panel-${stepName}`).classList.add("active");
  document.querySelectorAll(".step-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.step === stepName);
  });
}

function unlockSteps() {
  document.querySelectorAll(".step-btn").forEach((b) => (b.disabled = false));
}

document.querySelectorAll(".step-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (!btn.disabled) goToStep(btn.dataset.step);
  });
});

// ---------------- Step 1: Upload ----------------

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files.length) handleUpload(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleUpload(fileInput.files[0]);
});

async function handleUpload(file) {
  clearError("upload-error");
  document.getElementById("dropzone-label").textContent = `Uploading ${file.name}...`;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await apiFetch(API.upload, { method: "POST", body: formData });
    state.datasetId = data.dataset_id;
    state.filename = data.filename;
    state.columnsMeta = data.columns_meta;

    document.getElementById("status-line").textContent =
      `${data.filename} — ${data.row_count} rows × ${data.column_count} cols`;
    document.getElementById("dropzone-label").textContent = `${data.filename} loaded — click to replace`;

    renderColumnsMeta(data.columns_meta);
    resetViewAllRowsToggle();
    renderPreviewTable(data.preview, data.row_count, data.column_count);
    populateColumnDropdowns(data.columns_meta);

    unlockSteps();
    goToStep("clean");
  } catch (err) {
    showError("upload-error", err.message);
    document.getElementById("dropzone-label").textContent = "Drag a file here, or click to browse";
  }
}

// ---------------- Step 2: Clean ----------------

function renderColumnsMeta(meta) {
  const container = document.getElementById("columns-meta");
  container.innerHTML = "";
  Object.entries(meta).forEach(([col, info]) => {
    const chip = document.createElement("div");
    chip.className = "col-chip";
    chip.innerHTML = `<b>${col}</b> <span class="dtype">${info.dtype}</span>` +
      (info.nulls > 0 ? ` <span class="nulls">${info.nulls} nulls</span>` : "");
    container.appendChild(chip);
  });
}

function resetViewAllRowsToggle() {
  state.viewingAllRows = false;
  document.getElementById("view-all-rows-btn").textContent = "View all rows";
  document.getElementById("preview-table-scroll").classList.remove("expanded");
  document.getElementById("preview-truncated-note").classList.add("hidden");
}

function renderPreviewTable(rows, rowCount, colCount) {
  document.getElementById("preview-dims").textContent = rowCount != null ? `(${rowCount} × ${colCount})` : "";
  const table = document.getElementById("preview-table");
  table.innerHTML = "";
  if (!rows || !rows.length) return;

  const cols = Object.keys(rows[0]);
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr>`;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = cols.map((c) => `<td>${row[c] === null || row[c] === undefined ? "—" : row[c]}</td>`).join("");
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

function renderSteps(steps) {
  const list = document.getElementById("steps-list");
  list.innerHTML = "";
  (steps || []).forEach((s) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${s.operation}</span> ${JSON.stringify(s.params)}`;
    list.appendChild(li);
  });
}

// ---------------- View all rows / download CSV ----------------

document.getElementById("view-all-rows-btn").addEventListener("click", async () => {
  const btn = document.getElementById("view-all-rows-btn");
  const scroller = document.getElementById("preview-table-scroll");
  const note = document.getElementById("preview-truncated-note");

  if (state.viewingAllRows) {
    // Toggle back to the short preview without a network call
    state.viewingAllRows = false;
    btn.textContent = "View all rows";
    scroller.classList.remove("expanded");
    note.classList.add("hidden");
    try {
      const data = await apiFetch(API.dataset(state.datasetId));
      renderPreviewTable(data.preview, data.row_count, data.column_count);
    } catch (err) {
      showError("clean-error", err.message);
    }
    return;
  }

  try {
    const data = await apiFetch(API.datasetFull(state.datasetId));
    const colCount = Object.keys(state.columnsMeta).length;
    renderPreviewTable(data.rows, data.returned_count, colCount);
    state.viewingAllRows = true;
    btn.textContent = "Show fewer rows";
    scroller.classList.add("expanded");
    if (data.truncated) {
      note.textContent = `Showing the first ${data.returned_count.toLocaleString()} rows — the full dataset is larger than that.`;
      note.classList.remove("hidden");
    } else {
      note.classList.add("hidden");
    }
  } catch (err) {
    showError("clean-error", err.message);
  }
});

document.getElementById("download-csv-btn").addEventListener("click", () => {
  if (!state.datasetId) return;
  window.location.href = API.download(state.datasetId);
});

const OP_PARAM_TEMPLATES = {
  drop_nulls: () => `
    <label>Columns (leave blank = all)</label>
    <select id="p-columns" multiple size="4"></select>`,
  fill_nulls: () => `
    <label>Column</label><select id="p-column"></select>
    <label>Strategy</label>
    <select id="p-strategy">
      <option value="mean">Mean</option>
      <option value="median">Median</option>
      <option value="mode">Mode</option>
      <option value="constant">Constant value</option>
    </select>
    <div id="p-constant-wrap" class="hidden">
      <label>Value</label><input type="text" id="p-value">
    </div>`,
  drop_column: () => `<label>Column</label><select id="p-column"></select>`,
  rename_column: () => `
    <label>Column</label><select id="p-old-name"></select>
    <label>New name</label><input type="text" id="p-new-name">`,
  encode_categorical: () => `
    <label>Column</label><select id="p-column"></select>
    <label>Method</label>
    <select id="p-method"><option value="label">Label encode</option><option value="onehot">One-hot encode</option></select>`,
  scale_numeric: () => `
    <label>Column</label><select id="p-column"></select>
    <label>Method</label>
    <select id="p-method"><option value="standard">Standard (z-score)</option><option value="minmax">Min-Max</option></select>`,
  cast_dtype: () => `
    <label>Column</label><select id="p-column"></select>
    <label>Target dtype</label>
    <select id="p-dtype">
      <option value="int64">int64</option>
      <option value="float64">float64</option>
      <option value="str">str</option>
      <option value="category">category</option>
      <option value="datetime64[ns]">datetime64[ns]</option>
    </select>`,
};

function fillColumnSelect(select, { multiple = false } = {}) {
  select.innerHTML = "";
  Object.keys(state.columnsMeta).forEach((col) => {
    const opt = document.createElement("option");
    opt.value = col;
    opt.textContent = col;
    select.appendChild(opt);
  });
}

function renderOpParams() {
  const op = document.getElementById("op-select").value;
  const container = document.getElementById("op-params");
  container.innerHTML = OP_PARAM_TEMPLATES[op]();

  container.querySelectorAll("select[id^='p-column'], select#p-old-name, select#p-columns")
    .forEach((sel) => fillColumnSelect(sel, { multiple: sel.multiple }));

  const strategySel = container.querySelector("#p-strategy");
  if (strategySel) {
    strategySel.addEventListener("change", () => {
      document.getElementById("p-constant-wrap").classList.toggle("hidden", strategySel.value !== "constant");
    });
  }
}

document.getElementById("op-select").addEventListener("change", renderOpParams);
renderOpParams();

function collectOpParams(op) {
  const val = (id) => document.getElementById(id)?.value;
  switch (op) {
    case "drop_nulls": {
      const sel = document.getElementById("p-columns");
      const columns = Array.from(sel.selectedOptions).map((o) => o.value);
      return { columns: columns.length ? columns : null };
    }
    case "fill_nulls":
      return { column: val("p-column"), strategy: val("p-strategy"), value: val("p-value") };
    case "drop_column":
      return { column: val("p-column") };
    case "rename_column":
      return { old_name: val("p-old-name"), new_name: val("p-new-name") };
    case "encode_categorical":
      return { column: val("p-column"), method: val("p-method") };
    case "scale_numeric":
      return { column: val("p-column"), method: val("p-method") };
    case "cast_dtype":
      return { column: val("p-column"), dtype: val("p-dtype") };
    default:
      return {};
  }
}

document.getElementById("apply-op-btn").addEventListener("click", async () => {
  clearError("clean-error");
  const operation = document.getElementById("op-select").value;
  const params = collectOpParams(operation);

  try {
    const data = await apiFetch(API.clean(state.datasetId), {
      method: "POST",
      body: { operation, params },
    });
    state.columnsMeta = data.columns_meta;
    renderColumnsMeta(data.columns_meta);
    resetViewAllRowsToggle();
    renderPreviewTable(data.preview, data.row_count, data.column_count);
    populateColumnDropdowns(data.columns_meta);
    renderOpParams();
    refreshDatasetDetail();
  } catch (err) {
    showError("clean-error", err.message);
  }
});

document.getElementById("reset-btn").addEventListener("click", async () => {
  clearError("clean-error");
  try {
    const data = await apiFetch(API.reset(state.datasetId), { method: "POST" });
    state.columnsMeta = data.columns_meta;
    renderColumnsMeta(data.columns_meta);
    resetViewAllRowsToggle();
    renderPreviewTable(data.preview, data.row_count, data.column_count);
    populateColumnDropdowns(data.columns_meta);
    renderOpParams();
    document.getElementById("steps-list").innerHTML = "";
  } catch (err) {
    showError("clean-error", err.message);
  }
});

async function refreshDatasetDetail() {
  const data = await apiFetch(API.dataset(state.datasetId));
  renderSteps(data.steps);
}

// ---------------- Step 3: Visualize ----------------

const VIZ_PARAM_TEMPLATES = {
  histogram: () => `<label>Column</label><select id="v-column"></select><label>Bins</label><input type="number" id="v-bins" value="30">`,
  scatter: () => `<label>X column</label><select id="v-x"></select><label>Y column</label><select id="v-y"></select><label>Color by (optional)</label><select id="v-color"><option value="">—</option></select>`,
  line: () => `<label>X column</label><select id="v-x"></select><label>Y column</label><select id="v-y"></select>`,
  bar: () => `<label>X column</label><select id="v-x"></select><label>Y column (optional)</label><select id="v-y"><option value="">—</option></select><label>Aggregation</label><select id="v-agg"><option value="count">Count</option><option value="mean">Mean</option><option value="sum">Sum</option></select>`,
  box: () => `<label>Column</label><select id="v-column"></select><label>Group by (optional)</label><select id="v-group"><option value="">—</option></select>`,
  correlation: () => `<label>Columns (leave blank = all numeric)</label><select id="v-columns" multiple size="5"></select>`,
};

function renderVizParams() {
  const type = document.getElementById("chart-type-select").value;
  const container = document.getElementById("viz-params");
  container.innerHTML = VIZ_PARAM_TEMPLATES[type]();
  container.querySelectorAll("select").forEach((sel) => {
    const keepBlank = sel.querySelector('option[value=""]');
    fillColumnSelect(sel);
    if (keepBlank) sel.insertAdjacentHTML("afterbegin", '<option value="">—</option>');
  });
}
document.getElementById("chart-type-select").addEventListener("change", renderVizParams);

document.getElementById("render-chart-btn").addEventListener("click", async () => {
  clearError("viz-error");
  const chart_type = document.getElementById("chart-type-select").value;
  const val = (id) => document.getElementById(id)?.value || undefined;

  let payload = { chart_type };
  if (chart_type === "histogram") payload = { ...payload, column: val("v-column"), bins: Number(val("v-bins")) || 30 };
  if (chart_type === "scatter") payload = { ...payload, x_column: val("v-x"), y_column: val("v-y"), color_column: val("v-color") };
  if (chart_type === "line") payload = { ...payload, x_column: val("v-x"), y_column: val("v-y") };
  if (chart_type === "bar") payload = { ...payload, x_column: val("v-x"), y_column: val("v-y"), agg: val("v-agg") };
  if (chart_type === "box") payload = { ...payload, column: val("v-column"), group_by: val("v-group") };
  if (chart_type === "correlation") {
    const sel = document.getElementById("v-columns");
    const cols = Array.from(sel.selectedOptions).map((o) => o.value);
    payload = { ...payload, columns: cols.length ? cols : null };
  }

  try {
    const data = await apiFetch(API.visualize(state.datasetId), { method: "POST", body: payload });
    Plotly.newPlot("chart-container", data.figure.data, data.figure.layout, { responsive: true });
    state.lastChartTitle = chart_type;
    document.getElementById("download-chart-btn").classList.remove("hidden");
  } catch (err) {
    showError("viz-error", err.message);
  }
});

document.getElementById("download-chart-btn").addEventListener("click", () => {
  const chartDiv = document.getElementById("chart-container");
  if (!chartDiv || !chartDiv.data) return;
  Plotly.downloadImage(chartDiv, {
    format: "png",
    filename: `data_comparator_${state.lastChartTitle || "chart"}`,
    width: chartDiv.clientWidth || 900,
    height: chartDiv.clientHeight || 500,
  });
});

// ---------------- Step 4: Compare models ----------------

function populateColumnDropdowns(meta) {
  const targetSel = document.getElementById("target-select");
  targetSel.innerHTML = "";
  Object.keys(meta).forEach((col) => {
    const opt = document.createElement("option");
    opt.value = col;
    opt.textContent = col;
    targetSel.appendChild(opt);
  });
  renderFeatureCheckboxes();
  renderVizParams();
}

function renderFeatureCheckboxes() {
  const container = document.getElementById("feature-checkboxes");
  container.innerHTML = "";
  const target = document.getElementById("target-select").value;
  Object.keys(state.columnsMeta).forEach((col) => {
    if (col === target) return;
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" value="${col}"> ${col}`;
    container.appendChild(label);
  });
}
document.getElementById("target-select").addEventListener("change", renderFeatureCheckboxes);

document.getElementById("compare-btn").addEventListener("click", async () => {
  clearError("compare-error");
  const target_column = document.getElementById("target-select").value;
  const feature_columns = Array.from(
    document.querySelectorAll("#feature-checkboxes input:checked")
  ).map((el) => el.value);
  const task_type = document.getElementById("task-type-select").value || null;

  if (!target_column || !feature_columns.length) {
    showError("compare-error", "Pick a target column and at least one feature column.");
    return;
  }

  const resultsEl = document.getElementById("compare-results");
  resultsEl.innerHTML = `<p class="hint">Training models…</p>`;

  try {
    const data = await apiFetch(API.compare(state.datasetId), {
      method: "POST",
      body: { target_column, feature_columns, task_type },
    });
    renderCompareResults(data);
    state.lastRunId = data.run_id;
    state.lastRunFeatures = feature_columns;
    state.lastRunBestModel = data.best_model_name;
    state.lastRunModelNames = Object.keys(data.results);
    setupPredictForm(feature_columns, data.best_model_name, state.lastRunModelNames);
  } catch (err) {
    resultsEl.innerHTML = "";
    showError("compare-error", err.message);
  }
});

function renderCompareResults(data) {
  const container = document.getElementById("compare-results");
  container.innerHTML = `<h3>${data.task_type} — best: ${data.best_model_name}</h3>`;

  const sorted = Object.entries(data.results).sort(
    (a, b) => b[1].primary_score - a[1].primary_score
  );

  sorted.forEach(([name, r]) => {
    const card = document.createElement("div");
    card.className = "model-card" + (name === data.best_model_name ? " best" : "");
    const metricsHtml = Object.entries(r.metrics)
      .map(([k, v]) => `${k}: <b>${v}</b>`)
      .join(" &nbsp;·&nbsp; ");
    card.innerHTML = `
      <span class="model-name">${name}</span>
      ${name === data.best_model_name ? '<span class="best-tag">BEST</span>' : ""}
      <div class="metrics">${metricsHtml} &nbsp;·&nbsp; ${r.train_time_sec}s</div>`;
    container.appendChild(card);
  });
}

// ---------------- Step 5: Predict ----------------

function setupPredictForm(featureColumns, bestModelName, modelNames) {
  document.getElementById("predict-hint").textContent = "Choose a model and enter values for each feature.";

  const modelSelect = document.getElementById("predict-model-select");
  modelSelect.innerHTML = "";
  modelNames.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name === bestModelName ? `${name} (best)` : name;
    modelSelect.appendChild(opt);
  });
  modelSelect.value = bestModelName;
  document.getElementById("predict-model-row").classList.remove("hidden");

  const container = document.getElementById("predict-inputs");
  container.innerHTML = "";
  featureColumns.forEach((col) => {
    const wrap = document.createElement("div");
    const dtype = state.columnsMeta[col]?.dtype || "";
    wrap.innerHTML = `<label>${col} <span style="color:var(--text-dim)">(${dtype})</span></label>
      <input type="text" data-feature="${col}" id="predict-${col}">`;
    container.appendChild(wrap);
  });
  document.getElementById("predict-btn").classList.remove("hidden");
  document.getElementById("predict-result").classList.add("hidden");
}

document.getElementById("predict-btn").addEventListener("click", async () => {
  clearError("predict-error");
  const input = {};
  state.lastRunFeatures.forEach((col) => {
    const raw = document.getElementById(`predict-${col}`).value;
    const num = Number(raw);
    input[col] = raw !== "" && !isNaN(num) ? num : raw;
  });
  const model_name = document.getElementById("predict-model-select").value;

  try {
    const data = await apiFetch(API.predict(state.lastRunId), { method: "POST", body: { input, model_name } });
    const resultBox = document.getElementById("predict-result");
    resultBox.textContent = `Prediction (${data.model_used}): ${data.prediction}`;
    resultBox.classList.remove("hidden");
  } catch (err) {
    showError("predict-error", err.message);
  }
});