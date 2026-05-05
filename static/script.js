const fileInput = document.getElementById("fileInput");
const dropzone = document.getElementById("dropzone");
const fileList = document.getElementById("fileList");
const assessBtn = document.getElementById("assessBtn");
const clearBtn = document.getElementById("clearBtn");
const loading = document.getElementById("loading");
const errorBox = document.getElementById("error");
const results = document.getElementById("results");

let files = [];

function fmtSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(2) + " MB";
}

function iconFor(file) {
  if (file.type.startsWith("image/")) return "\u{1F5BC}";
  if (file.type === "application/pdf") return "\u{1F4C4}";
  return "\u{1F4DD}";
}

function renderFiles() {
  fileList.innerHTML = "";
  files.forEach((file, i) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="name"><span>${iconFor(file)}</span><span>${file.name}</span><span class="size">${fmtSize(file.size)}</span></div>
      <button class="remove" data-i="${i}" title="Remove">&times;</button>
    `;
    fileList.appendChild(li);
  });
  fileList.querySelectorAll(".remove").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const i = parseInt(e.currentTarget.dataset.i, 10);
      files.splice(i, 1);
      renderFiles();
      updateButtons();
    });
  });
}

function updateButtons() {
  assessBtn.disabled = files.length === 0;
  clearBtn.disabled = files.length === 0;
}

function addFiles(list) {
  for (const f of list) {
    if (!files.find((x) => x.name === f.name && x.size === f.size)) {
      files.push(f);
    }
  }
  if (files.length > 12) files = files.slice(0, 12);
  renderFiles();
  updateButtons();
}

dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => addFiles(e.target.files));

["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag");
  })
);
dropzone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

clearBtn.addEventListener("click", () => {
  files = [];
  fileInput.value = "";
  renderFiles();
  updateButtons();
  results.classList.add("hidden");
  errorBox.classList.add("hidden");
});

assessBtn.addEventListener("click", runAssessment);

async function runAssessment() {
  if (files.length === 0) return;
  errorBox.classList.add("hidden");
  results.classList.add("hidden");
  loading.classList.remove("hidden");
  assessBtn.disabled = true;

  const fd = new FormData();
  files.forEach((f) => fd.append("documents", f));

  try {
    const res = await fetch("/api/assess", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Assessment failed");
    renderResults(data);
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove("hidden");
  } finally {
    loading.classList.add("hidden");
    assessBtn.disabled = false;
  }
}

function renderResults(data) {
  const summary = data.summary || {};
  const score = Number(summary.green_score ?? 0) || 0;

  const ring = document.querySelector(".score-ring");
  ring.style.setProperty("--p", Math.max(0, Math.min(100, score)));
  document.getElementById("scoreValue").textContent = Math.round(score);

  document.getElementById("ratingBadge").textContent = summary.rating || "--";
  document.getElementById("decisionBadge").textContent = "Decision: " + (summary.decision || "--");
  const bps = summary.recommended_green_rate_discount_bps ?? 0;
  document.getElementById("discountBadge").textContent = bps > 0 ? `Discount: ${bps} bps` : "No pricing benefit";
  document.getElementById("introText").textContent = data.introduction || "";

  const reasons = document.getElementById("keyReasons");
  reasons.innerHTML = "";
  (summary.key_reasons || []).forEach((r) => {
    const li = document.createElement("li");
    li.textContent = r;
    reasons.appendChild(li);
  });

  const labels = {
    E: "E - Emissions Performance (35%)",
    V: "V - External Verification (25%)",
    T: "T - YoY Improvement (20%)",
    G: "G - Governance Maturity (20%)",
  };
  const components = document.getElementById("components");
  components.innerHTML = "";
  ["E", "V", "T", "G"].forEach((k) => {
    const c = (data.scores || {})[k] || {};
    const value = c.score === null || c.score === undefined ? "N/A" : Math.round(c.score);
    const width = c.score === null || c.score === undefined ? 0 : Math.max(0, Math.min(100, c.score));
    const div = document.createElement("div");
    div.className = "component";
    div.innerHTML = `
      <h3>${labels[k]}</h3>
      <div class="val"><strong>${value}</strong><small>${value === "N/A" ? "" : "/ 100"}</small></div>
      <div class="bar"><div style="width:${width}%"></div></div>
      <p>${escapeHtml(c.reasoning || "")}</p>
      <div class="conf">Confidence: ${c.confidence ?? 0}/100</div>
    `;
    components.appendChild(div);
  });

  const flagsBox = document.getElementById("riskFlags");
  flagsBox.innerHTML = "";
  const flags = data.risk_flags || [];
  if (flags.length === 0) {
    flagsBox.innerHTML = `<div class="muted">No risk flags raised.</div>`;
  } else {
    flags.forEach((f) => {
      const div = document.createElement("div");
      div.className = `flag ${f.severity || "low"}`;
      div.innerHTML = `<span class="sev">${f.severity || "low"}</span><span>${escapeHtml(f.message || "")}</span>`;
      flagsBox.appendChild(div);
    });
  }

  const docsBox = document.getElementById("documents");
  docsBox.innerHTML = "";
  (data.documents || []).forEach((doc) => {
    const div = document.createElement("div");
    div.className = "doc";
    const fields = doc.extracted_fields || {};
    const rows = Object.entries(fields)
      .map(([k, v]) => `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(formatVal(v))}</td></tr>`)
      .join("");
    div.innerHTML = `
      <div class="doc-head">
        <span class="doc-type">${escapeHtml(doc.document_type || "Unclassified")}</span>
        <span>${escapeHtml(doc.document_name || "")}</span>
      </div>
      <table>${rows || `<tr><td colspan="2" class="muted">No fields extracted</td></tr>`}</table>
    `;
    docsBox.appendChild(div);
  });

  document.getElementById("rawJson").textContent = JSON.stringify(data, null, 2);
  results.classList.remove("hidden");
}

function formatVal(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
