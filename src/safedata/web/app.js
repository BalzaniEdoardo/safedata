// Records editor page. Talks to the local server in webapp.py; the server
// validates again before writing, so the checks here are for quick feedback.
"use strict";

const token = location.hash.slice(1);
let state = null;      // last state from the server
let rows = [];         // {uid, orig: record | null (new), cur: record, deleted: bool}
let sort = { col: null, dir: 1 };
let nextUid = 1;
const $ = (id) => document.getElementById(id);

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: { "X-Token": token, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw Object.assign(new Error(data.error || res.statusText), { problems: data.problems || [] });
  return data;
}

function showMessage(text, kind, problems = []) {
  const box = $("message");
  box.hidden = !text;
  box.className = kind || "";
  box.textContent = text + (problems.length ? "\n" + problems.map((p) => "  • " + p).join("\n") : "");
}

// ------------------------------------------------------------------ loading

async function load(message) {
  try {
    state = await api("/api/state");
  } catch (e) {
    showMessage("Could not load the records: " + e.message, "error", e.problems);
    return;
  }
  $("file").textContent = state.file;
  $("location").textContent = `Dataset folder: ${state.dataset}`;
  for (const el of document.querySelectorAll(".records-file")) el.textContent = state.file;
  renderGitInfo();
  rows = state.rows.map((r) => ({ uid: nextUid++, orig: r, cur: { ...r }, deleted: false, problems: {} }));
  const inConflict = Array.isArray(state.conflicts);
  $("editor").hidden = inConflict;
  $("conflicts").hidden = !inConflict;
  if (inConflict) renderConflicts(); else renderTable();
  renderUncommitted();
  if (message) showMessage(...message); else if (!inConflict) showMessage("");
}

function renderGitInfo() {
  const g = state.git;
  if (!g || !g.branch) { $("gitinfo").textContent = "not a git repository"; return; }
  let text = `git branch: ${g.branch}`;
  if (g.ahead != null) {
    if (g.ahead) text += ` · ${g.ahead} commit(s) not pushed`;
    if (g.behind) text += ` · ${g.behind} commit(s) to pull`;
    text += " (as of the last fetch)";
  }
  $("gitinfo").textContent = text;
}

function renderUncommitted() {
  const lines = state.uncommitted || [];
  $("uncommitted").hidden = lines.length === 0;
  $("uncommitted-list").replaceChildren(...lines.map((l) => Object.assign(document.createElement("li"), { textContent: l })));
}

// ------------------------------------------------------------------ checking (rules live on the server)

const pending = new Set();
let checkTimer = null;

// Ask the server to check the given row soon; edits made in quick succession are sent together.
function queueCheck(row) {
  pending.add(row);
  $("save").disabled = true;
  clearTimeout(checkTimer);
  checkTimer = setTimeout(runChecks, 200);
}

async function runChecks() {
  const batch = [...pending];
  pending.clear();
  if (!batch.length) return;
  try {
    const res = await api("/api/check", { rows: Object.fromEntries(batch.map((r) => [r.uid, r.cur])) });
    for (const row of batch) row.problems = res.problems[row.uid] || {};
  } catch (e) {
    showMessage("Could not check the edits: " + e.message, "error");
  }
  for (const row of batch) if (row.tr) refreshRow(row);
  renderSummary();
}

const rowHasProblems = (row) => !row.deleted && Object.keys(row.problems).length > 0;

// ------------------------------------------------------------------ table

function columns() { return state.schema.columns; }
const isEdited = (row) => row.orig === null || row.deleted || columns().some((c) => row.cur[c.name] !== row.orig[c.name]);

function visibleRows() {
  const q = $("search").value.trim().toLowerCase();
  const onlyEdited = $("only-changed").checked;
  let out = rows.filter((r) => (!onlyEdited || isEdited(r)) &&
    (!q || columns().some((c) => String(r.cur[c.name]).toLowerCase().includes(q))));
  if (sort.col) {
    const col = columns().find((c) => c.name === sort.col);
    const numeric = col.input.sort === "number";
    out = out.slice().sort((a, b) => {
      const x = a.cur[sort.col], y = b.cur[sort.col];
      if (x === "" || y === "") return (x === "") - (y === "");
      return (numeric ? Number(x) - Number(y) : x.localeCompare(y)) * sort.dir;
    });
  }
  // new records first, so they stay in view
  return out.filter((r) => r.orig === null).concat(out.filter((r) => r.orig !== null));
}

function renderTable() {
  const head = document.createElement("tr");
  for (const c of columns()) {
    const th = document.createElement("th");
    th.textContent = c.name;
    th.title = c.description || "";
    if (sort.col === c.name) th.className = sort.dir > 0 ? "sorted-asc" : "sorted-desc";
    th.onclick = () => {
      sort = sort.col === c.name ? { col: c.name, dir: -sort.dir } : { col: c.name, dir: 1 };
      renderTable();
    };
    head.append(th);
  }
  head.append(document.createElement("th"));
  $("table").tHead.replaceChildren(head);
  $("table").tBodies[0].replaceChildren(...visibleRows().map(renderRow));
  renderSummary();
}

function renderRow(row) {
  const tr = document.createElement("tr");
  row.tr = tr;
  row.cells = {};
  for (const c of columns()) {
    const td = document.createElement("td");
    if (c.name === state.schema.key) {
      td.className = "key";
      td.textContent = row.orig === null ? "new" : row.cur[c.name];
    } else {
      const input = editorFor(c, row.cur[c.name]);
      input.disabled = row.deleted;
      input.addEventListener("input", () => {
        row.cur[c.name] = input.value;
        refreshRow(row);
        renderSummary();
        queueCheck(row);
      });
      td.append(input);
      row.cells[c.name] = td;
    }
    tr.append(td);
  }
  const actions = document.createElement("td");
  actions.className = "actions";
  const btn = document.createElement("button");
  if (row.orig === null) {
    btn.textContent = "Remove";
    btn.onclick = () => { rows = rows.filter((r) => r !== row); renderTable(); };
  } else {
    btn.textContent = row.deleted ? "Undo delete" : "Delete";
    btn.onclick = () => { row.deleted = !row.deleted; renderTable(); };
  }
  actions.append(btn);
  tr.append(actions);
  refreshRow(row);
  return tr;
}

// Build the input for a column from the spec the server derived from the schema.
function editorFor(col, value) {
  const spec = col.input;
  let el;
  if (spec.kind === "select") {
    el = document.createElement("select");
    for (const v of ["", ...spec.options]) el.append(new Option(v, v));
    if (value && !spec.options.includes(value)) el.append(new Option(value, value));  // keep an invalid value visible
  } else {
    el = document.createElement("input");
    el.type = spec.kind;
    if (spec.inputmode) el.inputMode = spec.inputmode;
    if (spec.min) el.min = spec.min;
    if (spec.max) el.max = spec.max;
  }
  el.value = value;
  return el;
}

function refreshRow(row) {
  row.tr.className = rowClass(row);
  for (const [name, td] of Object.entries(row.cells)) {
    const p = row.deleted ? null : row.problems[name];
    td.classList.toggle("changed", row.orig !== null && row.cur[name] !== row.orig[name]);
    td.classList.toggle("invalid", Boolean(p));
    td.title = p ? `${name}: ${p}` : "";
  }
}

const rowClass = (row) => (row.orig === null ? "added" : row.deleted ? "deleted" : "");

function renderSummary() {
  const added = rows.filter((r) => r.orig === null).length;
  const deleted = rows.filter((r) => r.deleted).length;
  const changed = rows.filter((r) => r.orig !== null && !r.deleted && isEdited(r)).length;
  const invalid = rows.filter((r) => isEdited(r) && rowHasProblems(r)).length;
  const total = added + deleted + changed;
  $("summary").textContent = total
    ? `${changed} changed, ${added} added, ${deleted} deleted, not saved` + (invalid ? ` · ${invalid} with problems` : "")
    : "no unsaved edits";
  $("save").disabled = total === 0 || invalid > 0 || pending.size > 0;
  $("discard").disabled = total === 0;
}

function hasUnsavedEdits() { return rows.some(isEdited); }

// ------------------------------------------------------------------ saving

function editsPayload() {
  const key = state.schema.key;
  const payload = { version: state.version, adds: [], updates: {}, deletes: {} };
  for (const r of rows) {
    if (r.orig === null) payload.adds.push(r.cur);
    else if (r.deleted) payload.deletes[r.orig[key]] = r.orig;
    else {
      const cols = {};
      for (const c of columns()) if (r.cur[c.name] !== r.orig[c.name]) cols[c.name] = [r.orig[c.name], r.cur[c.name]];
      if (Object.keys(cols).length) payload.updates[r.orig[key]] = cols;
    }
  }
  return payload;
}

async function save() {
  $("save").disabled = true;
  try {
    const res = await api("/api/save", editsPayload());
    const text = `Saved to ${state.file}. The file now shows as changed in git; commit it with your git tool to record it in the history.`;
    await load([text, "ok", res.saved]);
  } catch (e) {
    showMessage(e.message, "error", e.problems);
    renderSummary();
  }
}

// ------------------------------------------------------------------ conflicts

function renderConflicts() {
  const choices = {};
  const list = state.conflicts.map((c) => {
    const box = document.createElement("div");
    box.className = "conflict";
    const table = document.createElement("table");
    const head = document.createElement("tr");
    head.append(...["version", ...columns().map((x) => x.name)].map((t) => Object.assign(document.createElement("th"), { textContent: t })));
    table.append(head);
    for (const [label, rec] of [["local (yours)", c.local], ["incoming", c.incoming]]) {
      const tr = document.createElement("tr");
      tr.append(Object.assign(document.createElement("td"), { textContent: label }));
      if (!rec) {
        tr.append(Object.assign(document.createElement("td"), { textContent: "(deleted)", colSpan: columns().length }));
      } else {
        for (const col of columns()) {
          const other = rec === c.local ? c.incoming : c.local;
          const td = Object.assign(document.createElement("td"), { textContent: rec[col.name] });
          if (!other || other[col.name] !== rec[col.name]) td.className = "differs";
          tr.append(td);
        }
      }
      table.append(tr);
    }
    box.append(Object.assign(document.createElement("strong"), { textContent: `Record ${c.key}` }), table);
    for (const [value, text] of [["local", "Keep the local version"], ["incoming", "Keep the incoming version"]]) {
      const label = document.createElement("label");
      const radio = Object.assign(document.createElement("input"), { type: "radio", name: `c-${c.key}`, value });
      radio.onchange = () => { choices[c.key] = value; $("resolve").disabled = Object.keys(choices).length < state.conflicts.length; };
      label.append(radio, " " + text);
      box.append(label);
    }
    return box;
  });
  $("conflict-list").replaceChildren(...list);
  $("resolve").disabled = true;
  $("resolve").onclick = async () => {
    try {
      await api("/api/resolve", { version: state.version, choices });
      await load([`Resolved file written to ${state.file}. Review the diff in your git tool, then stage the file and commit to finish the merge.`, "ok"]);
    } catch (e) {
      showMessage(e.message, "error", e.problems);
    }
  };
  showMessage(`${state.conflicts.length} record(s) need a decision before the records can be edited.`, "error");
}

// ------------------------------------------------------------------ wiring

$("search").addEventListener("input", renderTable);
$("only-changed").addEventListener("change", renderTable);
$("save").addEventListener("click", save);
$("discard").addEventListener("click", () => {
  if (confirm("Discard all unsaved edits?")) load();
});
$("add").addEventListener("click", () => {
  const cur = Object.fromEntries(columns().map((c) => [c.name, ""]));
  const row = { uid: nextUid++, orig: null, cur, deleted: false, problems: {} };
  rows.push(row);
  renderTable();
  queueCheck(row);
  $("table").tBodies[0].querySelector("input, select")?.focus();
});
window.addEventListener("beforeunload", (e) => { if (hasUnsavedEdits()) e.preventDefault(); });

load();
