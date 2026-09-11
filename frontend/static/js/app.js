/* Document Intelligence frontend — plain JS, no build step.
 * Talks to the REST API exclusively via fetch(); the server only serves
 * static HTML shells for these two pages. */
(function () {
  "use strict";

  const API_BASE = "/api/v1";
  const LOW_CONFIDENCE_THRESHOLD = 0.7;

  const TYPE_LABELS = {
    invoice: "Invoice",
    balance_sheet: "Balance Sheet",
    profit_and_loss: "Profit & Loss",
    cash_flow_statement: "Cash Flow Statement",
  };

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") node.className = v;
        else if (k === "html") node.innerHTML = v;
        else node.setAttribute(k, v);
      }
    }
    (children || []).forEach((c) => {
      if (c == null) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function statusBadge(status) {
    const map = { PASS: "badge-pass", FAIL: "badge-fail", NOT_APPLICABLE: "badge-na", FAILED: "badge-fail" };
    return el("span", { class: `badge ${map[status] || "badge-na"}` }, [status]);
  }

  function formatDateTime(iso) {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  function formatValue(v) {
    if (v === null || v === undefined || v === "") return null;
    if (typeof v === "number") {
      return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    return String(v);
  }

  // ---------------------------------------------------------------------
  // Dashboard
  // ---------------------------------------------------------------------

  async function initDashboard() {
    const form = document.getElementById("uploadForm");
    const statusEl = document.getElementById("uploadStatus");
    const submitBtn = document.getElementById("submitBtn");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fileInput = document.getElementById("fileInput");
      const documentType = document.getElementById("documentType").value;
      if (!fileInput.files.length) return;

      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      fd.append("document_type", documentType);

      submitBtn.disabled = true;
      statusEl.innerHTML = "";
      statusEl.appendChild(el("span", { class: "muted" }, ["Processing document… this can take a few seconds for OCR."]));

      try {
        const resp = await fetch(`${API_BASE}/documents/process`, { method: "POST", body: fd });
        const data = await resp.json();
        if (!resp.ok) {
          const msg = data?.error?.message || "Processing failed.";
          statusEl.innerHTML = "";
          statusEl.appendChild(el("span", { style: "color:#c02b2b" }, [`Error: ${msg}`]));
          return;
        }
        statusEl.innerHTML = "";
        const badge = statusBadge(data.processing_status);
        statusEl.appendChild(
          el("span", {}, [
            "Done — ",
            badge,
            el("a", { href: `/documents/${encodeURIComponent(data.document_name)}`, style: "margin-left:8px" }, [
              "View result →",
            ]),
          ])
        );
        fileInput.value = "";
        loadDocuments();
      } catch (err) {
        statusEl.innerHTML = "";
        statusEl.appendChild(el("span", { style: "color:#c02b2b" }, [`Network error: ${err}`]));
      } finally {
        submitBtn.disabled = false;
      }
    });

    loadDocuments();
  }

  async function loadDocuments() {
    const wrap = document.getElementById("tableWrap");
    try {
      const resp = await fetch(`${API_BASE}/documents`);
      const data = await resp.json();
      if (!data.documents || data.documents.length === 0) {
        wrap.innerHTML = "";
        wrap.appendChild(el("div", { class: "empty-state" }, ["No documents processed yet. Upload one above to get started."]));
        return;
      }
      const table = el("table", {}, [
        el("thead", {}, [
          el("tr", {}, [
            el("th", {}, ["Document Name"]),
            el("th", {}, ["Type"]),
            el("th", {}, ["Status"]),
            el("th", {}, ["Confidence"]),
            el("th", {}, ["Processed At"]),
          ]),
        ]),
        el(
          "tbody",
          {},
          data.documents.map((doc) =>
            el(
              "tr",
              { class: "clickable", onclick: `window.location.href='/documents/${encodeURIComponent(doc.document_name)}'` },
              [
                el("td", {}, [doc.document_name]),
                el("td", {}, [el("span", { class: "type-pill" }, [TYPE_LABELS[doc.document_type] || doc.document_type])]),
                el("td", {}, [statusBadge(doc.processing_status)]),
                el("td", {}, [doc.overall_confidence != null ? `${Math.round(doc.overall_confidence * 100)}%` : "—"]),
                el("td", {}, [formatDateTime(doc.created_at)]),
              ]
            )
          )
        ),
      ]);
      wrap.innerHTML = "";
      wrap.appendChild(table);
    } catch (err) {
      wrap.innerHTML = "";
      wrap.appendChild(el("div", { class: "empty-state" }, [`Failed to load documents: ${err}`]));
    }
  }

  // ---------------------------------------------------------------------
  // Document detail page
  // ---------------------------------------------------------------------

  async function initDocumentPage() {
    const name = window.DOCUMENT_NAME;
    const content = document.getElementById("content");
    try {
      const resp = await fetch(`${API_BASE}/documents/${encodeURIComponent(name)}`);
      const data = await resp.json();
      if (!resp.ok) {
        document.getElementById("pageSubtitle").textContent = data?.error?.message || "Not found.";
        content.innerHTML = "";
        content.appendChild(el("div", { class: "empty-state" }, [data?.error?.message || "Document not found."]));
        return;
      }
      renderDocument(data);
    } catch (err) {
      content.innerHTML = "";
      content.appendChild(el("div", { class: "empty-state" }, [`Failed to load document: ${err}`]));
    }
  }

  function renderDocument(data) {
    document.getElementById("pageTitle").textContent = data.document_name;
    const subtitle = document.getElementById("pageSubtitle");
    subtitle.innerHTML = "";
    subtitle.appendChild(
      el("span", {}, [
        `${TYPE_LABELS[data.document_type] || data.document_type} · `,
        statusBadge(data.processing_status),
        data.overall_confidence != null ? ` · Confidence: ${Math.round(data.overall_confidence * 100)}%` : "",
        data.processing_metadata?.ocr_used ? " · OCR used" : "",
      ])
    );

    const content = document.getElementById("content");
    content.innerHTML = "";

    // Tabs
    const tabs = el("div", { class: "tabs" }, [
      el("button", { class: "tab-btn active", "data-tab": "extracted" }, ["Extracted Data"]),
      el("button", { class: "tab-btn", "data-tab": "validation" }, ["Financial Validation"]),
      el("button", { class: "tab-btn", "data-tab": "file" }, ["File Validation"]),
      el("button", { class: "tab-btn", "data-tab": "raw" }, ["Raw JSON"]),
    ]);
    content.appendChild(tabs);

    const panes = {
      extracted: renderExtractedPane(data),
      validation: renderValidationPane(data.validation),
      file: renderFileValidationPane(data.file_validation, data.processing_metadata),
      raw: renderRawPane(data),
    };
    Object.entries(panes).forEach(([key, node]) => {
      node.style.display = key === "extracted" ? "" : "none";
      node.dataset.pane = key;
      content.appendChild(node);
    });

    tabs.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        tabs.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        Object.values(panes).forEach((p) => (p.style.display = "none"));
        panes[btn.dataset.tab].style.display = "";
      });
    });
  }

  function isExtractedFieldShape(v) {
    return v && typeof v === "object" && !Array.isArray(v) && "value" in v;
  }

  function renderExtractedPane(data) {
    const pane = el("div", {});
    const extracted = data.extracted_data || {};
    const scalarEntries = [];
    const arrayEntries = [];

    for (const [key, value] of Object.entries(extracted)) {
      if (Array.isArray(value)) {
        arrayEntries.push([key, value]);
      } else {
        scalarEntries.push([key, value]);
      }
    }

    const card = el("div", { class: "card" }, [el("h2", {}, ["Extracted Fields"])]);
    const grid = el("div", { class: "kv-grid" });
    scalarEntries.forEach(([key, raw]) => {
      grid.appendChild(renderKvItem(key, raw));
    });
    card.appendChild(grid);
    pane.appendChild(card);

    arrayEntries.forEach(([key, items]) => {
      pane.appendChild(renderArrayTable(key, items));
    });

    return pane;
  }

  function prettyLabel(key) {
    return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function renderKvItem(key, raw) {
    const isField = isExtractedFieldShape(raw);
    const value = isField ? raw.value : raw;
    const confidence = isField ? raw.confidence : null;
    const evidence = isField ? raw.evidence : null;
    const missing = value === null || value === undefined;
    const lowConf = confidence != null && confidence < LOW_CONFIDENCE_THRESHOLD;

    const classes = ["kv-item"];
    if (missing) classes.push("missing");
    else if (lowConf) classes.push("low-confidence");

    const children = [
      el("div", { class: "kv-label" }, [prettyLabel(key)]),
      el("div", { class: "kv-value" }, [missing ? "— not found" : formatValue(value)]),
    ];
    if (confidence != null) {
      children.push(el("div", { class: "kv-conf" }, [`Confidence: ${Math.round(confidence * 100)}%${lowConf ? " ⚠ low" : ""}`]));
    }
    if (evidence && evidence.source_text) {
      const pg = evidence.page_number != null ? ` (p.${evidence.page_number})` : "";
      children.push(el("div", { class: "kv-evidence" }, [`"${evidence.source_text}"${pg}`]));
    }
    return el("div", { class: classes.join(" ") }, children);
  }

  function renderArrayTable(key, items) {
    const card = el("div", { class: "card" }, [el("h2", {}, [prettyLabel(key), ` (${items.length})`])]);
    if (!items.length) {
      card.appendChild(el("div", { class: "empty-state" }, ["No entries extracted."]));
      return card;
    }
    const columns = Array.from(
      items.reduce((set, item) => {
        if (item && typeof item === "object") Object.keys(item).forEach((k) => set.add(k));
        return set;
      }, new Set())
    );
    const wrap = el("div", { class: "line-items-table" });
    const table = el("table", {}, [
      el("thead", {}, [el("tr", {}, columns.map((c) => el("th", {}, [prettyLabel(c)])))]),
      el(
        "tbody",
        {},
        items.map((item) =>
          el(
            "tr",
            {},
            columns.map((c) => {
              const v = item ? item[c] : null;
              const text = Array.isArray(v) ? v.map(formatValue).join(", ") : formatValue(v);
              return el("td", {}, [text === null ? "—" : text]);
            })
          )
        )
      ),
    ]);
    wrap.appendChild(table);
    card.appendChild(wrap);
    return card;
  }

  function renderValidationPane(validation) {
    const pane = el("div", {});
    const card = el("div", { class: "card" }, [
      el("h2", {}, ["Financial Validation"]),
      el("div", { style: "margin-bottom:0.75rem" }, ["Overall: ", statusBadge(validation?.overall_status || "NOT_APPLICABLE")]),
    ]);
    const checks = validation?.checks || [];
    if (!checks.length) {
      card.appendChild(el("div", { class: "empty-state" }, ["No financial validation checks were applicable to this document."]));
    } else {
      const list = el("div", { class: "checks-list" });
      checks.forEach((c) => {
        const operandsText = Object.entries(c.operands || {})
          .map(([k, v]) => `${k}=${v != null ? formatValue(v) : "—"}`)
          .join(", ");
        const row = el("div", { class: `check-row ${c.status === "FAIL" ? "fail" : ""}` }, [
          el("div", { class: "check-main" }, [
            el("div", { class: "check-name" }, [prettyLabel(c.name) + (c.period ? ` — ${c.period}` : "")]),
            el("div", { class: "check-formula" }, [c.formula]),
            el("div", { class: "check-values" }, [
              operandsText ? `Inputs: ${operandsText}` : "",
              c.calculated_value != null ? ` · Calculated: ${formatValue(c.calculated_value)}` : "",
              c.reported_value != null ? ` · Reported: ${formatValue(c.reported_value)}` : "",
              c.variance != null ? ` · Variance: ${formatValue(c.variance)}` : "",
            ]),
            c.message ? el("div", { class: "check-values" }, [c.message]) : null,
          ]),
          statusBadge(c.status),
        ]);
        list.appendChild(row);
      });
      card.appendChild(list);
    }
    pane.appendChild(card);
    return pane;
  }

  function renderFileValidationPane(fv, meta) {
    const pane = el("div", {});
    const card = el("div", { class: "card" }, [el("h2", {}, ["File Validation"])]);
    const grid = el("div", { class: "kv-grid" });
    if (fv) {
      Object.entries(fv).forEach(([k, v]) => {
        if (v === null || v === undefined) return;
        grid.appendChild(
          el("div", { class: "kv-item" }, [el("div", { class: "kv-label" }, [prettyLabel(k)]), el("div", { class: "kv-value" }, [String(v)])])
        );
      });
    }
    card.appendChild(grid);
    pane.appendChild(card);

    if (meta) {
      const metaCard = el("div", { class: "card" }, [el("h2", {}, ["Processing Metadata"])]);
      const metaGrid = el("div", { class: "kv-grid" });
      Object.entries(meta).forEach(([k, v]) => {
        metaGrid.appendChild(
          el("div", { class: "kv-item" }, [el("div", { class: "kv-label" }, [prettyLabel(k)]), el("div", { class: "kv-value" }, [String(v)])])
        );
      });
      metaCard.appendChild(metaGrid);
      pane.appendChild(metaCard);
    }
    return pane;
  }

  function renderRawPane(data) {
    const pane = el("div", {});
    const card = el("div", { class: "card" }, [
      el("h2", {}, ["Raw Structured JSON"]),
      el("pre", { class: "json-view" }, [JSON.stringify(data, null, 2)]),
    ]);
    pane.appendChild(card);
    return pane;
  }

  window.DocIntel = { initDashboard, initDocumentPage };
})();
