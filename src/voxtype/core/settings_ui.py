"""Self-contained Settings UI page (HTML/CSS/JS).

Served by the engine's FastAPI server at GET /settings.
Auto-generates form controls from the Pydantic JSON Schema.
"""

from __future__ import annotations

SETTINGS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VoxType Settings</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#1a1a2e;--bg2:#16213e;--bg3:#0f3460;
  --fg:#e0e0e0;--fg2:#999;--accent:#e94560;--accent2:#0f3460;
  --input-bg:#16213e;--input-border:#2a3a5e;--input-focus:#e94560;
  --success:#4caf50;--error:#f44336;--warn:#ff9800;
  --radius:6px;--font:system-ui,-apple-system,sans-serif;
}
body{font-family:var(--font);background:var(--bg);color:var(--fg);
  display:flex;min-height:100vh}
a{color:var(--accent)}

/* Sidebar */
.sidebar{width:200px;background:var(--bg2);padding:16px 0;flex-shrink:0;
  border-right:1px solid var(--input-border);position:sticky;top:0;height:100vh;
  overflow-y:auto}
.sidebar h1{font-size:16px;padding:0 16px 12px;color:var(--accent);
  border-bottom:1px solid var(--input-border);margin-bottom:8px;font-weight:600}
.sidebar .version{font-size:11px;color:var(--fg2);font-weight:normal}
.tab-btn{display:block;width:100%;text-align:left;padding:8px 16px;
  background:none;border:none;color:var(--fg2);cursor:pointer;font-size:13px;
  font-family:var(--font);transition:all .15s}
.tab-btn:hover{background:var(--accent2);color:var(--fg)}
.tab-btn.active{color:var(--accent);background:rgba(233,69,96,.1);
  border-right:2px solid var(--accent)}

/* Main */
.main{flex:1;padding:24px 32px;max-width:720px;overflow-y:auto}
.main h2{font-size:18px;margin-bottom:4px}
.main .section-desc{color:var(--fg2);font-size:13px;margin-bottom:20px}

/* Banner */
.banner{display:none;background:var(--accent2);border:1px solid var(--accent);
  border-radius:var(--radius);padding:10px 16px;margin-bottom:20px;
  font-size:13px;align-items:center;gap:12px}
.banner.show{display:flex}
.banner button{background:var(--accent);color:#fff;border:none;
  border-radius:var(--radius);padding:6px 14px;cursor:pointer;font-size:12px;
  font-family:var(--font);white-space:nowrap}

/* Fields */
.field{margin-bottom:16px;padding:10px 12px;border-radius:var(--radius);
  transition:background .15s}
.field:hover{background:rgba(255,255,255,.03)}
.field.dirty{background:rgba(233,69,96,.05);border-left:2px solid var(--accent)}
.field-header{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.field-label{font-size:13px;font-weight:500}
.field-key{font-size:11px;color:var(--fg2);font-family:monospace}
.field-desc{font-size:12px;color:var(--fg2);margin-bottom:6px}
.field-default{font-size:11px;color:var(--fg2);margin-top:2px}
.field-env{font-size:10px;color:var(--fg2);font-family:monospace;opacity:.6}
.field-error{font-size:12px;color:var(--error);margin-top:4px;display:none}

/* Inputs */
input[type=text],input[type=number],select{
  width:100%;max-width:360px;padding:6px 10px;background:var(--input-bg);
  border:1px solid var(--input-border);border-radius:var(--radius);
  color:var(--fg);font-size:13px;font-family:var(--font);outline:none;
  transition:border-color .15s}
input:focus,select:focus{border-color:var(--input-focus)}

/* Toggle */
.toggle{position:relative;width:40px;height:22px;flex-shrink:0}
.toggle input{opacity:0;width:0;height:0}
.toggle .slider{position:absolute;inset:0;background:var(--input-border);
  border-radius:11px;cursor:pointer;transition:background .2s}
.toggle .slider::before{content:"";position:absolute;width:16px;height:16px;
  left:3px;bottom:3px;background:#fff;border-radius:50%;transition:transform .2s}
.toggle input:checked+.slider{background:var(--accent)}
.toggle input:checked+.slider::before{transform:translateX(18px)}

/* Complex field */
.complex-note{font-size:12px;color:var(--fg2);padding:8px 12px;
  background:var(--input-bg);border-radius:var(--radius);
  border:1px dashed var(--input-border)}

/* Save bar */
.save-bar{position:sticky;bottom:0;background:var(--bg2);
  border-top:1px solid var(--input-border);padding:12px 0;margin-top:24px;
  display:flex;align-items:center;gap:12px}
.save-bar button{background:var(--accent);color:#fff;border:none;
  border-radius:var(--radius);padding:8px 24px;cursor:pointer;font-size:13px;
  font-family:var(--font);font-weight:500;transition:opacity .15s}
.save-bar button:disabled{opacity:.4;cursor:default}
.save-bar .status{font-size:12px;color:var(--fg2)}
.save-bar .status.ok{color:var(--success)}
.save-bar .status.err{color:var(--error)}

/* Loading */
.loading{text-align:center;padding:60px;color:var(--fg2)}

/* Responsive */
@media(max-width:640px){
  .sidebar{width:140px}
  .main{padding:16px}
}
</style>
</head>
<body>

<nav class="sidebar">
  <h1>VoxType <span class="version" id="version"></span></h1>
  <div id="tabs"></div>
</nav>

<div class="main" id="main">
  <div class="loading">Loading settings...</div>
</div>

<script>
const TABS = [
  {id:"general", label:"General", sections:[""], desc:"General settings"},
  {id:"audio", label:"Audio", sections:["audio"], desc:"Audio capture and feedback"},
  {id:"stt", label:"Speech Recognition", sections:["stt"], desc:"Whisper STT settings"},
  {id:"tts", label:"Text-to-Speech", sections:["tts"], desc:"TTS engine settings"},
  {id:"hotkey", label:"Hotkey", sections:["hotkey"], desc:"Toggle listening key"},
  {id:"output", label:"Output", sections:["output"], desc:"Text output mode and typing"},
  {id:"server", label:"Server", sections:["server"], desc:"OpenVIP HTTP server"},
  {id:"advanced", label:"Advanced", sections:["client","logging","stats","daemon","pipeline"],
   desc:"Client, logging, daemon, pipeline settings"},
];

// Complex fields shown as read-only
const COMPLEX_KEYS = new Set([
  "audio.sounds","keyboard.shortcuts","pipeline.submit_filter.triggers","agent_types","default_agent_type"
]);
const SKIP_KEYS = new Set(["keyboard.shortcuts"]);

let schema = null, values = null, keys = null, dirty = {};

async function load() {
  const r = await fetch("/settings/schema");
  const data = await r.json();
  schema = data.schema;
  values = data.values;
  keys = data.keys;
  document.getElementById("version").textContent = data.version || "";
  renderTabs();
  showTab(TABS[0].id);
}

function renderTabs() {
  const el = document.getElementById("tabs");
  el.innerHTML = TABS.map(t =>
    `<button class="tab-btn" data-tab="${t.id}">${t.label}</button>`
  ).join("");
  el.querySelectorAll(".tab-btn").forEach(btn =>
    btn.addEventListener("click", () => showTab(btn.dataset.tab))
  );
}

function showTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.tab === tabId)
  );
  const tab = TABS.find(t => t.id === tabId);
  if (!tab) return;
  const main = document.getElementById("main");
  main.innerHTML = `
    <h2>${tab.label}</h2>
    <div class="section-desc">${tab.desc}</div>
    <div class="banner" id="banner">
      <span>Changes saved. Restart the engine for changes to take effect.</span>
      <button onclick="restartEngine()">Restart Engine</button>
    </div>
    <div id="fields"></div>
    <div class="save-bar">
      <button id="saveBtn" onclick="saveAll()" disabled>Save Changes</button>
      <span class="status" id="saveStatus"></span>
    </div>
  `;
  renderFields(tab);
}

function renderFields(tab) {
  const container = document.getElementById("fields");
  const relevant = keys.filter(k => {
    if (SKIP_KEYS.has(k.key)) return false;
    if (tab.id === "general") return !k.key.includes(".");
    const section = k.key.split(".")[0];
    return tab.sections.includes(section);
  });
  if (!relevant.length) {
    container.innerHTML = '<div class="complex-note">No configurable fields in this section.</div>';
    return;
  }
  container.innerHTML = relevant.map(k => renderField(k)).join("");
}

function renderField(k) {
  const isComplex = isComplexField(k);
  const val = getCurrentValue(k.key);
  const fieldSchema = getFieldSchema(k.key);
  const enumValues = fieldSchema?.enum || null;
  const fieldType = fieldSchema?.type || k.type;
  const isDirty = k.key in dirty;

  let input;
  if (isComplex) {
    input = `<div class="complex-note">Complex value — edit in config.toml</div>`;
  } else if (k.type === "bool") {
    const checked = val ? "checked" : "";
    input = `<label class="toggle">
      <input type="checkbox" ${checked} onchange="onChange('${k.key}',this.checked)">
      <span class="slider"></span>
    </label>`;
  } else if (enumValues) {
    const opts = enumValues.map(v =>
      `<option value="${v}" ${v===val?"selected":""}>${v}</option>`
    ).join("");
    input = `<select onchange="onChange('${k.key}',this.value)">${opts}</select>`;
  } else if (fieldType === "integer" || fieldType === "number" || k.type === "int" || k.type === "float") {
    const step = (fieldType === "number" || k.type === "float") ? "0.01" : "1";
    input = `<input type="number" step="${step}" value="${val ?? ""}"
      onchange="onChange('${k.key}',this.value)">`;
  } else {
    input = `<input type="text" value="${val ?? ""}"
      onchange="onChange('${k.key}',this.value)">`;
  }

  const defStr = k.default !== null && k.default !== undefined && !isComplex
    ? `<div class="field-default">Default: <code>${JSON.stringify(k.default)}</code></div>` : "";
  const envStr = k.env_var ? `<div class="field-env">${k.env_var}</div>` : "";

  return `<div class="field${isDirty?" dirty":""}" id="field-${k.key.replace(/\\./g,"-")}">
    <div class="field-header">
      <span class="field-label">${k.description || k.key}</span>
      <span class="field-key">${k.key}</span>
    </div>
    ${defStr}
    ${input}
    ${envStr}
    <div class="field-error" id="err-${k.key.replace(/\\./g,"-")}"></div>
  </div>`;
}

function isComplexField(k) {
  for (const ck of COMPLEX_KEYS) {
    if (k.key === ck || k.key.startsWith(ck + ".")) return true;
  }
  if (k.type === "dict" || k.type === "list") return true;
  return false;
}

function getCurrentValue(key) {
  if (key in dirty) return dirty[key];
  const parts = key.split(".");
  let obj = values;
  for (const p of parts) {
    if (obj == null) return null;
    obj = obj[p];
  }
  return obj;
}

function getFieldSchema(key) {
  const parts = key.split(".");
  if (parts.length === 1) {
    return schema.properties?.[parts[0]] || null;
  }
  const sectionName = parts[0];
  const fieldName = parts.slice(1).join(".");
  // Find the section $ref
  const sectionProp = schema.properties?.[sectionName];
  if (!sectionProp) return null;
  const ref = sectionProp.$ref || sectionProp.allOf?.[0]?.$ref;
  if (!ref) return null;
  const defName = ref.split("/").pop();
  const def = schema.$defs?.[defName];
  if (!def) return null;
  // Handle nested (pipeline.submit_filter.enabled)
  if (parts.length === 3) {
    const subProp = def.properties?.[parts[1]];
    if (!subProp) return null;
    const subRef = subProp.$ref || subProp.allOf?.[0]?.$ref;
    if (!subRef) return null;
    const subDef = schema.$defs?.[subRef.split("/").pop()];
    return subDef?.properties?.[parts[2]] || null;
  }
  return def.properties?.[fieldName] || null;
}

function onChange(key, value) {
  // Convert types
  const k = keys.find(x => x.key === key);
  if (k?.type === "int") value = parseInt(value, 10);
  else if (k?.type === "float") value = parseFloat(value);
  dirty[key] = value;
  // Mark field dirty
  const el = document.getElementById("field-" + key.replace(/\\./g, "-"));
  if (el) el.classList.add("dirty");
  // Enable save
  const btn = document.getElementById("saveBtn");
  if (btn) btn.disabled = false;
  const status = document.getElementById("saveStatus");
  if (status) { status.textContent = ""; status.className = "status"; }
}

async function saveAll() {
  const btn = document.getElementById("saveBtn");
  const status = document.getElementById("saveStatus");
  btn.disabled = true;
  status.textContent = "Saving...";
  status.className = "status";

  let errors = 0;
  for (const [key, value] of Object.entries(dirty)) {
    try {
      const r = await fetch("/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({key, value: String(value)})
      });
      if (!r.ok) {
        const data = await r.json();
        showFieldError(key, data.detail || "Invalid value");
        errors++;
      }
    } catch (e) {
      showFieldError(key, e.message);
      errors++;
    }
  }

  if (errors === 0) {
    dirty = {};
    document.querySelectorAll(".field.dirty").forEach(f => f.classList.remove("dirty"));
    status.textContent = "Saved!";
    status.className = "status ok";
    document.getElementById("banner")?.classList.add("show");
    // Reload values
    const r = await fetch("/settings/schema");
    const data = await r.json();
    values = data.values;
  } else {
    status.textContent = `${errors} error(s)`;
    status.className = "status err";
    btn.disabled = false;
  }
}

function showFieldError(key, msg) {
  const el = document.getElementById("err-" + key.replace(/\\./g, "-"));
  if (el) { el.textContent = msg; el.style.display = "block"; }
}

async function restartEngine() {
  try {
    await fetch("/control", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({command: "engine.shutdown"})
    });
    document.getElementById("banner").innerHTML =
      '<span>Engine is restarting... This page will stop working until the engine is back.</span>';
  } catch (e) {
    // Expected — engine shuts down
  }
}

load();
</script>
</body>
</html>
"""

def get_settings_html() -> str:
    """Return the self-contained Settings UI HTML page."""
    return SETTINGS_HTML
