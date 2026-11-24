// OBJ//TRAKR front-end
const $ = (s) => document.querySelector(s);
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};

const S = {
  schema: [], defaults: {}, params: {}, video: null,
  frame: 0, playing: false, inF: null, outF: null, ph: 540,
  stillBusy: false, stillPending: false, job: null,
};

const BUILTIN = {
  "WHITE (default)": {},
  "WHITE + EDGES": { edge_enabled: true, links: true },
  "MINIMAL": { box_style: "full", box_thickness: 1, data_lines: 0, show_coords: false, trails: false, crosshair: false,
    decode_frames: 0, box_fill: 0, hud: false, glow: 0.15, text_bg: 0.35 },
  "MATRIX GREEN": { box_color: "#00ff66", text_color: "#b6ffcf", hud_color: "#00ff66", link_color: "#00ff66",
    edge_color: "#00e5ff", rain_color: "#00ff66", color_variation: 0.15, edge_color_variation: 0.2, glow: 0.8 },
  "CYAN HUD": { box_color: "#00e5ff", text_color: "#d0fbff", hud_color: "#00e5ff", link_color: "#00e5ff",
    edge_color: "#7df9ff", rain_color: "#00e5ff", box_style: "full+corners", links: true },
  "BLUEPRINT": { obj_enabled: false, edge_enabled: true, edge_mode: "lines", node_labels: 0.08, glow: 0.5 },
  "FULL SYSTEM": { edge_enabled: true, edge_mode: "both", rain: true, links: true, show_velocity: true, show_size: true,
    data_lines: 2, glow: 0.8 },
};

// ------------------------------------------------------------ api
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).error || msg; } catch {}
    throw new Error(msg);
  }
  return r;
}

// ------------------------------------------------------------ controls
function buildControls() {
  const root = $("#groups");
  root.innerHTML = "";
  const closed = store.get("trakr.closed.v2", { edges: false, trails: true, post: true, hud: false, detection: true });
  for (const g of S.schema) {
    const el = document.createElement("div");
    el.className = "group" + (closed[g.group] ? " closed" : "");
    el.dataset.group = g.group;
    const head = document.createElement("div");
    head.className = "ghead";
    head.innerHTML = `<span class="caret">${closed[g.group] ? "+" : "-"}</span><span class="title">// ${g.title}</span>`;
    if (g.toggle) {
      const t = document.createElement("button");
      t.className = "btn tog";
      t.dataset.toggle = g.toggle;
      t.onclick = (e) => { e.stopPropagation(); setParam(g.toggle, !S.params[g.toggle]); syncControls(); };
      head.appendChild(t);
    }
    const reset = document.createElement("button");
    reset.className = "btn tog"; reset.textContent = "↺"; reset.title = "reset group";
    reset.onclick = (e) => {
      e.stopPropagation();
      for (const f of g.fields) S.params[f.key] = S.defaults[f.key];
      syncControls(); paramsChanged();
    };
    head.appendChild(reset);
    head.onclick = () => {
      el.classList.toggle("closed");
      closed[g.group] = el.classList.contains("closed");
      head.querySelector(".caret").textContent = closed[g.group] ? "+" : "-";
      store.set("trakr.closed.v2", closed);
    };
    const body = document.createElement("div");
    body.className = "gbody";
    for (const f of g.fields) {
      if (f.key === g.toggle) continue;
      body.appendChild(makeField(f));
    }
    el.append(head, body);
    root.appendChild(el);
  }
  syncControls();
}

function makeField(f) {
  const row = document.createElement("div");
  row.className = "row";
  row.dataset.key = f.key;
  const lab = document.createElement("label");
  lab.textContent = f.label;
  lab.title = `${f.key}  (double-click to reset)`;
  lab.ondblclick = () => { setParam(f.key, S.defaults[f.key]); syncControls(); };
  row.appendChild(lab);

  if (f.type === "range") {
    const r = document.createElement("input");
    r.type = "range"; r.min = f.min; r.max = f.max; r.step = f.step;
    const n = document.createElement("input");
    n.type = "number"; n.className = "num"; n.min = f.min; n.max = f.max; n.step = f.step;
    r.oninput = () => { n.value = r.value; setParam(f.key, +r.value); };
    n.onchange = () => { r.value = n.value; setParam(f.key, +n.value); };
    row.append(r, n);
  } else if (f.type === "bool") {
    row.classList.add("wide2");
    const l = document.createElement("label");
    l.className = "chk";
    l.innerHTML = `<input type="checkbox"><span class="box">OFF</span>`;
    const c = l.querySelector("input");
    c.onchange = () => { l.querySelector(".box").textContent = c.checked ? "ON" : "OFF"; setParam(f.key, c.checked); };
    row.appendChild(l);
  } else if (f.type === "color") {
    row.classList.add("wide2");
    const w = document.createElement("div");
    w.className = "colorwrap";
    const c = document.createElement("input"); c.type = "color";
    const t = document.createElement("input"); t.type = "text"; t.spellcheck = false;
    c.oninput = () => { t.value = c.value; setParam(f.key, c.value); };
    t.onchange = () => { if (/^#?[0-9a-f]{6}$/i.test(t.value)) { const v = t.value.startsWith("#") ? t.value : "#" + t.value; c.value = v; setParam(f.key, v); } };
    w.append(c, t);
    row.appendChild(w);
  } else if (f.type === "select") {
    row.classList.add("wide2");
    const s = document.createElement("select");
    for (const o of f.options) { const op = document.createElement("option"); op.value = o; op.textContent = o; s.appendChild(op); }
    s.onchange = () => setParam(f.key, typeof f.options[0] === "number" ? +s.value : s.value);
    row.appendChild(s);
  } else {
    row.classList.add("wide2");
    const t = document.createElement("input"); t.type = "text"; t.spellcheck = false;
    if (f.key === "classes") t.placeholder = "person, car, truck";
    let tt = null;
    t.oninput = () => { clearTimeout(tt); tt = setTimeout(() => setParam(f.key, t.value), 150); };
    t.onchange = () => { clearTimeout(tt); setParam(f.key, t.value); };
    row.appendChild(t);
  }
  return row;
}

function syncControls() {
  for (const row of document.querySelectorAll(".row[data-key]")) {
    const k = row.dataset.key, v = S.params[k];
    row.classList.toggle("changed", JSON.stringify(v) !== JSON.stringify(S.defaults[k]));
    const inputs = row.querySelectorAll("input, select");
    for (const i of inputs) {
      if (i.type === "checkbox") { i.checked = !!v; i.nextElementSibling.textContent = v ? "ON" : "OFF"; }
      else i.value = v;
    }
  }
  $("#exBg").value = S.params.background;
  for (const b of document.querySelectorAll("[data-toggle]")) {
    const on = !!S.params[b.dataset.toggle];
    b.textContent = on ? "ON" : "OFF";
    b.classList.toggle("active", on);
    b.closest(".group").classList.toggle("off", !on);
  }
}

function setParam(k, v) {
  S.params[k] = v;
  const row = document.querySelector(`.row[data-key="${k}"]`);
  if (row) row.classList.toggle("changed", JSON.stringify(v) !== JSON.stringify(S.defaults[k]));
  paramsChanged();
}

const DEVICE_NAMES = { mps: "APPLE GPU (MPS)", cuda: "NVIDIA GPU (CUDA)", cpu: "CPU" };
function updateDevice() {
  if (!S.devices) return;
  const want = S.params.device;
  const dev = want === "auto" ? S.autoDevice : (S.devices.includes(want) ? want : S.devices[0]);
  const note = want === "auto" ? " [auto]" : (dev !== want ? ` [${want} unavailable]` : "");
  $("#device").textContent = `DEVICE ${DEVICE_NAMES[dev] || dev}${note}`;
}

let pushT = null;
function paramsChanged() {
  updateDevice();
  store.set("trakr.params.v2", S.params);
  clearTimeout(pushT);
  if (S.playing) pushT = setTimeout(() => api("/api/params", S.params).catch(() => {}), 40);
  else renderStill();
}

// ------------------------------------------------------------ preview
async function renderStill() {
  if (!S.video) return;
  if (S.stillBusy) { S.stillPending = true; return; }
  S.stillBusy = true;
  $("#busy").textContent = "RENDERING_";
  try {
    const r = await api("/api/frame", { vid: S.video.id, f: S.frame, ph: S.ph, params: S.params });
    const ms = r.headers.get("X-Render-Ms");
    const blob = await r.blob();
    if (!S.playing) {
      const old = $("#view").src;
      $("#view").src = URL.createObjectURL(blob);
      if (old.startsWith("blob:")) URL.revokeObjectURL(old);
      $("#perf").textContent = `FRAME RENDER ${ms}ms`;
    }
  } catch (e) {
    $("#perf").textContent = "ERR " + e.message;
  } finally {
    S.stillBusy = false;
    $("#busy").textContent = "";
    if (S.stillPending) { S.stillPending = false; renderStill(); }
  }
}

let pollT = null;
async function play() {
  if (!S.video) return;
  S.playing = true;
  $("#play").textContent = "❚❚";
  await api("/api/params", S.params);
  const start = S.frame >= S.video.n - 1 ? 0 : S.frame;
  $("#view").src = `/api/stream?vid=${S.video.id}&f=${start}&ph=${S.ph}&t=${Date.now()}`;
  clearInterval(pollT);
  pollT = setInterval(async () => {
    try {
      const st = await (await api("/api/status")).json();
      if (!S.playing) return;
      S.frame = st.pos;
      updateTime();
      $("#perf").textContent = `STREAM ${st.fps} fps render`;
    } catch {}
  }, 200);
}

async function pause() {
  if (!S.playing) return;
  S.playing = false;
  clearInterval(pollT);
  $("#play").textContent = "▶";
  try { const st = await (await api("/api/stop", {})).json(); S.frame = st.pos; } catch {}
  updateTime();
  renderStill();
}

function seekTo(f) {
  if (!S.video) return;
  S.frame = Math.max(0, Math.min(S.video.n - 1, f));
  updateTime();
  if (S.playing) { pause(); } else renderStill();
}

function fmtTime(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor(sec / 60) % 60, s = Math.floor(sec) % 60, cs = Math.floor((sec % 1) * 100);
  return [h, m, s].map((x) => String(x).padStart(2, "0")).join(":") + "." + String(cs).padStart(2, "0");
}

function updateTime() {
  if (!S.video) return;
  $("#seek").value = S.frame;
  $("#tc").textContent = `${fmtTime(S.frame / S.video.fps)} / F${String(S.frame).padStart(6, "0")}`;
}

function updateRange() {
  const m = $("#rangeMark");
  if (!S.video || (S.inF === null && S.outF === null)) {
    m.style.display = "none"; $("#rangeInfo").textContent = "RANGE: FULL"; return;
  }
  const a = S.inF ?? 0, b = S.outF ?? S.video.n;
  m.style.display = "block";
  m.style.left = (a / S.video.n * 100) + "%";
  m.style.width = (Math.max(0, b - a) / S.video.n * 100) + "%";
  $("#rangeInfo").textContent = `RANGE: F${a} → F${b} (${fmtTime((b - a) / S.video.fps)})`;
  $("#exRange").value = "inout";
}

// ------------------------------------------------------------ video load
function setVideo(v) {
  pause();
  S.video = v; S.frame = 0; S.inF = S.outF = null;
  $("#seek").max = Math.max(0, v.n - 1);
  $("#meta").textContent = `${v.name}  ${v.w}x${v.h}  ${v.fps.toFixed(2)}fps  ${v.n}f`;
  $("#empty").style.display = "none";
  $("#view").style.display = "block";
  updateRange(); updateTime(); renderStill();
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) $("#meta").textContent = `UPLOADING ${Math.round(e.loaded / e.total * 100)}%`; };
  xhr.onload = () => {
    try {
      const d = JSON.parse(xhr.responseText);
      if (xhr.status !== 200) throw new Error(d.error || "upload failed");
      setVideo(d);
    } catch (e) { $("#meta").textContent = "ERR " + e.message; }
  };
  xhr.send(fd);
}

// ------------------------------------------------------------ presets
function presetList() {
  const user = store.get("trakr.presets", {});
  const sel = $("#presetSel");
  sel.innerHTML = "";
  for (const n of Object.keys(BUILTIN)) sel.add(new Option(n, "b:" + n));
  for (const n of Object.keys(user)) sel.add(new Option("★ " + n, "u:" + n));
}

function applyParams(p) {
  S.params = { ...S.defaults, ...p };
  syncControls(); paramsChanged();
}

// ------------------------------------------------------------ export
async function startExport() {
  if (!S.video) return;
  if (S.job && ["starting", "rendering"].includes(S.job.status)) {
    await api(`/api/export/${S.job.id}/cancel`, {});
    return;
  }
  const inout = $("#exRange").value === "inout";
  const body = {
    vid: S.video.id, params: S.params, out_h: $("#exRes").value, codec: $("#exCodec").value,
    crf: +$("#exCrf").value, preset: $("#exPreset").value,
    start: inout ? (S.inF ?? 0) : 0, end: inout ? (S.outF ?? S.video.n) : S.video.n,
  };
  const { id } = await (await api("/api/export", body)).json();
  S.job = { id, status: "starting" };
  $("#exGo").textContent = "■ CANCEL";
  $("#exGo").classList.add("danger");
  const t = setInterval(async () => {
    const j = await (await api(`/api/export/${id}`)).json();
    S.job = j;
    const pct = j.total ? j.done / j.total : 0;
    const bars = 28, fill = Math.round(pct * bars);
    const bar = "[" + "#".repeat(fill) + "-".repeat(bars - fill) + "]";
    const eta = j.eta ? fmtTime(j.eta).slice(0, 8) : "--:--:--";
    let txt = `${bar} ${(pct * 100).toFixed(1)}%\n${j.done}/${j.total}f  ${j.fps.toFixed(2)} fps  ETA ${eta}\n${j.size || ""} ${j.status.toUpperCase()}`;
    const prog = $("#exProg");
    if (j.status === "done") {
      prog.innerHTML = `${bar} 100%\n${j.size} DONE → <a href="/api/download/${id}">${j.file}</a>\n(saved in exports/)`;
    } else if (j.status === "error") {
      prog.innerHTML = `<span class="err">ERROR: ${j.error}</span>`;
    } else prog.textContent = txt;
    if (!["starting", "rendering"].includes(j.status)) {
      clearInterval(t);
      $("#exGo").textContent = "> RENDER";
      $("#exGo").classList.remove("danger");
    }
  }, 500);
}

// ------------------------------------------------------------ wire up
async function init() {
  const d = await (await api("/api/schema")).json();
  S.schema = d.schema;
  S.defaults = d.params;
  S.devices = d.devices;
  S.autoDevice = d.auto_device;
  S.params = { ...S.defaults, ...store.get("trakr.params.v2", {}) };
  buildControls();
  presetList();
  updateDevice();

  $("#file").onchange = (e) => e.target.files[0] && uploadFile(e.target.files[0]);
  $("#openPath").onclick = async () => {
    try { setVideo(await (await api("/api/open", { path: $("#path").value })).json()); }
    catch (e) { $("#meta").textContent = "ERR " + e.message; }
  };
  $("#path").onkeydown = (e) => { if (e.key === "Enter") $("#openPath").click(); };

  const vp = $("#viewport");
  vp.ondragover = (e) => { e.preventDefault(); vp.classList.add("drag"); };
  vp.ondragleave = () => vp.classList.remove("drag");
  vp.ondrop = (e) => { e.preventDefault(); vp.classList.remove("drag"); const f = e.dataTransfer.files[0]; if (f) uploadFile(f); };

  $("#play").onclick = () => (S.playing ? pause() : play());
  $("#prev").onclick = () => seekTo(S.frame - 1);
  $("#next").onclick = () => seekTo(S.frame + 1);
  let seekT = null;
  $("#seek").oninput = (e) => {
    if (S.playing) pause();
    S.frame = +e.target.value; updateTime();
    clearTimeout(seekT); seekT = setTimeout(renderStill, 60);
  };
  $("#setIn").onclick = () => { S.inF = S.frame; if (S.outF !== null && S.outF <= S.inF) S.outF = null; updateRange(); };
  $("#setOut").onclick = () => { S.outF = S.frame + 1; if (S.inF !== null && S.inF >= S.outF) S.inF = null; updateRange(); };
  $("#clearRange").onclick = () => { S.inF = S.outF = null; updateRange(); $("#exRange").value = "full"; };
  $("#ph").value = String(store.get("trakr.ph", 720));
  S.ph = +$("#ph").value;
  $("#ph").onchange = (e) => {
    S.ph = +e.target.value; store.set("trakr.ph", S.ph);
    if (S.playing) { pause().then(play); } else renderStill();
  };

  $("#presetLoad").onclick = () => {
    const v = $("#presetSel").value;
    if (v.startsWith("b:")) applyParams(BUILTIN[v.slice(2)]);
    else applyParams(store.get("trakr.presets", {})[v.slice(2)] || {});
  };
  $("#presetSave").onclick = () => {
    const name = prompt("Preset name:");
    if (!name) return;
    const user = store.get("trakr.presets", {});
    user[name] = { ...S.params };
    store.set("trakr.presets", user);
    presetList();
    $("#presetSel").value = "u:" + name;
  };
  $("#presetDel").onclick = () => {
    const v = $("#presetSel").value;
    if (!v.startsWith("u:")) return;
    const user = store.get("trakr.presets", {});
    delete user[v.slice(2)];
    store.set("trakr.presets", user);
    presetList();
  };
  $("#presetExport").onclick = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(S.params, null, 2)], { type: "application/json" }));
    a.download = "trakr-preset.json"; a.click();
  };
  $("#presetImport").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try { applyParams(JSON.parse(await f.text())); } catch { alert("Invalid preset JSON"); }
    e.target.value = "";
  };
  $("#resetAll").onclick = () => { if (confirm("Reset all parameters to defaults?")) applyParams({}); };
  $("#exBg").onchange = (e) => { setParam("background", e.target.value); syncControls(); };
  $("#exGo").onclick = () => startExport().catch((e) => ($("#exProg").textContent = "ERR " + e.message));

  document.addEventListener("keydown", (e) => {
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName) && e.target.type !== "range") return;
    if (e.code === "Space") { e.preventDefault(); $("#play").click(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); seekTo(S.frame - (e.shiftKey ? 10 : 1)); }
    else if (e.key === "ArrowRight") { e.preventDefault(); seekTo(S.frame + (e.shiftKey ? 10 : 1)); }
    else if (e.key === "i" || e.key === "I") $("#setIn").click();
    else if (e.key === "o" || e.key === "O") $("#setOut").click();
  });
}

init();
