(function () {
  "use strict";

  const scriptEl = document.getElementById("script");
  const csvInput = document.getElementById("csv-input");
  const fileLabel = document.getElementById("file-label");
  const runBtn = document.getElementById("run-btn");
  const errorBox = document.getElementById("error-box");
  const pipelineItems = Array.from(document.querySelectorAll("#pipeline-track li"));

  const STAGE_ORDER = ["lexer", "parser", "semantic", "optimizer", "backend", "runtime"];

  csvInput.addEventListener("change", () => {
    fileLabel.textContent = csvInput.files.length
      ? csvInput.files[0].name
      : "Drop a CSV here or click to choose one";
  });

  document.getElementById("load-example").addEventListener("click", () => {
    location.reload();
  });

  // ---------------- tabs ----------------
  document.getElementById("tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("panel-" + btn.dataset.tab).classList.add("active");
  });

  function resetPipeline() {
    pipelineItems.forEach((li) => li.classList.remove("active", "ok", "fail"));
  }

  function markStages(failedStage, reachedRuntimeSkip) {
    // Walk stage order; mark ok up to (not incl) failedStage, mark failedStage as fail.
    // If no failedStage, mark all ok (or runtime as skipped/grey if reachedRuntimeSkip).
    let failIdx = failedStage ? STAGE_ORDER.indexOf(failedStage) : -1;
    STAGE_ORDER.forEach((stage, idx) => {
      const li = pipelineItems.find((el) => el.dataset.stage === stage);
      if (!li) return;
      if (failIdx !== -1 && idx > failIdx) return; // untouched
      if (failIdx !== -1 && idx === failIdx) {
        li.classList.add("fail");
        return;
      }
      if (stage === "runtime" && reachedRuntimeSkip) {
        li.classList.add("active"); // amber = attempted but skipped (no CSV)
        return;
      }
      li.classList.add("ok");
    });
  }

  function stageKeyFromResultStage(s) {
    if (s === "lexer") return "lexer";
    if (s === "parser") return "parser";
    if (s === "semantic") return "semantic";
    if (s === "csv-parse" || s === "runtime") return "runtime";
    return null; // 'done' or 'static-only' -> no failure
  }

  function esc(v) {
    if (v === null || v === undefined) return "";
    return String(v).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function renderTokens(tokens) {
    const t = document.getElementById("tokens-table");
    let html = "<thead><tr><th>#</th><th>Type</th><th>Value</th><th>Line</th><th>Col</th></tr></thead><tbody>";
    tokens.forEach((tok, i) => {
      html += `<tr><td>${i}</td><td><span class="tag">${esc(tok.type)}</span></td>` +
        `<td>${esc(tok.value)}</td><td>${tok.line}</td><td>${tok.col}</td></tr>`;
    });
    html += "</tbody>";
    t.innerHTML = tokens.length ? html : "";
  }

  function renderAst(ast) {
    document.getElementById("ast-view").textContent = ast ? JSON.stringify(ast, null, 2) : "";
  }

  function renderIrTable(tableId, ir) {
    const t = document.getElementById(tableId);
    let html = "<thead><tr><th>Line</th><th>Op</th><th>Dataframe</th><th>Args</th></tr></thead><tbody>";
    ir.forEach((instr) => {
      html += `<tr><td>${instr.line}</td><td><span class="tag">${esc(instr.op)}</span></td>` +
        `<td>${esc(instr.df)}</td><td>${esc(JSON.stringify(instr.args))}</td></tr>`;
    });
    html += "</tbody>";
    t.innerHTML = ir.length ? html : "";
  }

  function renderNotes(containerId, notes, cls) {
    const box = document.getElementById(containerId);
    box.innerHTML = "";
    notes.forEach((n) => {
      const div = document.createElement("div");
      div.className = "note" + (cls ? " " + cls : "");
      div.textContent = n;
      box.appendChild(div);
    });
  }

  function renderTrace(trace) {
    const t = document.getElementById("trace-table");
    let html = "<thead><tr><th>Line</th><th>Op</th><th>Dataframe</th><th>Rows</th><th>Cols</th></tr></thead><tbody>";
    trace.forEach((row) => {
      html += `<tr><td>${row.line}</td><td><span class="tag">${esc(row.op)}</span></td>` +
        `<td>${esc(row.df)}</td><td>${row.rows}</td><td>${row.cols}</td></tr>`;
    });
    html += "</tbody>";
    t.innerHTML = trace.length ? html : "";
  }

  function renderPreview(preview, runId) {
    const empty = document.getElementById("preview-empty");
    const meta = document.getElementById("preview-meta");
    const table = document.getElementById("preview-table");
    const dlRow = document.getElementById("download-row");

    if (!preview) {
      empty.classList.remove("hidden");
      meta.classList.add("hidden");
      dlRow.classList.add("hidden");
      table.innerHTML = "";
      return;
    }
    empty.classList.add("hidden");
    meta.classList.remove("hidden");
    meta.textContent = `${preview.total_rows} rows x ${preview.total_cols} columns` +
      (preview.rows.length < preview.total_rows ? ` (showing first ${preview.rows.length})` : "");

    let html = "<thead><tr>" + preview.columns.map((c) => `<th>${esc(c)}</th>`).join("") + "</tr></thead><tbody>";
    preview.rows.forEach((row) => {
      html += "<tr>" + preview.columns.map((c) => `<td>${esc(row[c])}</td>`).join("") + "</tr>";
    });
    html += "</tbody>";
    table.innerHTML = html;

    if (runId) {
      dlRow.classList.remove("hidden");
      document.getElementById("dl-csv").href = `/download/${runId}/csv`;
      document.getElementById("dl-py").href = `/download/${runId}/py`;
    } else {
      dlRow.classList.add("hidden");
    }
  }

  async function run() {
    resetPipeline();
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
    runBtn.disabled = true;
    runBtn.textContent = "Compiling...";

    const fd = new FormData();
    fd.append("script", scriptEl.value);
    if (csvInput.files.length) fd.append("csv_file", csvInput.files[0]);

    try {
      const resp = await fetch("/compile", { method: "POST", body: fd });
      const data = await resp.json();

      renderTokens(data.tokens || []);
      renderAst(data.ast);
      renderIrTable("ir-table", data.ir || []);
      renderIrTable("optimized-table", data.optimized_ir || []);
      renderNotes("ir-warnings", data.semantic_warnings || [], "warn");
      renderNotes("opt-notes", data.optimizer_notes || []);
      document.getElementById("code-view").textContent = data.generated_code || "";
      renderTrace(data.trace || []);
      renderPreview(data.preview, data.run_id);

      const failStage = stageKeyFromResultStage(data.stage);
      const skipRuntime = data.stage === "static-only";
      markStages(failStage, skipRuntime);

      if (data.errors && data.errors.length) {
        errorBox.classList.remove("hidden");
        errorBox.textContent = data.errors.map((e) => {
          const loc = e.line ? ` (line ${e.line}${e.col ? ", col " + e.col : ""})` : "";
          return `${e.message}${loc}`;
        }).join("\n");
      }
    } catch (err) {
      errorBox.classList.remove("hidden");
      errorBox.textContent = "Request failed: " + err.message +
        "\n\nIs the Flask server running? See README.md for setup steps.";
      markStages("lexer", false);
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = "Compile & Run \u25B6";
    }
  }

  runBtn.addEventListener("click", run);

  // Ctrl/Cmd+Enter to run
  scriptEl.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      run();
    }
  });
})();
