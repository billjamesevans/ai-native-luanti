const MATERIALS = {
  "default:stone": "#8b92a9",
  "default:wood": "#a56a42",
  "default:glass": "#84dfff",
  "default:torch": "#ffd166",
  "default:water_source": "#4ea8ff",
  "default:leaves": "#69d66f",
  "default:tree": "#7b4d2a",
  "default:cobble": "#727b93",
  "default:mese": "#7a5cff",
  "default:mese_post_light": "#b58cff",
  "default:snowblock": "#f6f7fa",
  "fire:basic_flame": "#ff8a3d",
  "tnt:tnt": "#ff4f5e",
  "flowers:dandelion_yellow": "#ffe66d",
  "air": "#00000000"
};

const state = {
  world: new Map(),
  pendingPlan: null,
  audit: [],
  rollbackStack: []
};

const el = {
  prompt: document.getElementById("prompt"),
  preset: document.getElementById("preset"),
  generate: document.getElementById("generate"),
  approve: document.getElementById("approve"),
  undo: document.getElementById("undo"),
  exportJson: document.getElementById("export-json"),
  exportLua: document.getElementById("export-lua"),
  previewTitle: document.getElementById("preview-title"),
  planSummary: document.getElementById("plan-summary"),
  planList: document.getElementById("plan-list"),
  metrics: document.getElementById("metrics"),
  audit: document.getElementById("audit"),
  recipe: document.getElementById("recipe"),
  risk: document.getElementById("risk"),
  canvas: document.getElementById("world"),
  runtimeCommit: document.getElementById("runtime-commit"),
  runtimeState: document.getElementById("runtime-state"),
  operatorState: document.getElementById("operator-state"),
  servicesStatus: document.getElementById("services-status"),
  servicesDetail: document.getElementById("services-detail"),
  qualityStatus: document.getElementById("quality-status"),
  qualityDetail: document.getElementById("quality-detail"),
  adapterStatus: document.getElementById("adapter-status"),
  adapterDetail: document.getElementById("adapter-detail"),
  latestPlanStatus: document.getElementById("latest-plan-status"),
  latestPlanDetail: document.getElementById("latest-plan-detail"),
  evalStatus: document.getElementById("eval-status"),
  evalDetail: document.getElementById("eval-detail")
};

function hashText(text) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function rng(seed) {
  let t = seed >>> 0;
  return function() {
    t += 0x6D2B79F5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function key(pos) { return `${pos.x},${pos.y},${pos.z}`; }
function pos(x, y, z) { return {x, y, z}; }
function offset(p, dx=0, dy=0, dz=0) { return {x:p.x+dx, y:p.y+dy, z:p.z+dz}; }

function add(actions, p, node, reason) {
  actions.push({ action: "place_node", pos: p, node, reason });
}

function dedupe(actions) {
  const map = new Map();
  for (const a of actions) map.set(key(a.pos), a);
  return [...map.entries()]
    .sort((a, b) => a[0].localeCompare(b[0], undefined, {numeric: true}))
    .map(([, a]) => a);
}

function featuresFor(text) {
  const checks = [
    ["glacier", ["glacier", "alpine", "mountain"]],
    ["village", ["village", "town", "settlement"]],
    ["cabin", ["cabin", "house", "shelter"]],
    ["bridge", ["bridge"]],
    ["portal", ["portal", "gate"]],
    ["garden", ["garden", "flowers"]],
    ["water", ["lake", "river", "water"]],
    ["tower", ["tower", "lookout"]],
    ["fire", ["fire", "campfire", "flame"]],
    ["tnt", ["tnt", "explosive"]],
    ["lights", ["lantern", "light", "glowing"]]
  ];
  const features = [];
  for (const [feature, words] of checks) {
    if (words.some(w => text.includes(w))) features.push(feature);
  }
  return features.length ? features : ["starter_build"];
}

function cabin(actions, origin, w=5, d=4) {
  for (let x = 0; x < w; x++) for (let z = 0; z < d; z++) add(actions, offset(origin, x, 0, z), "default:stone", "cabin foundation");
  for (let y = 1; y <= 3; y++) {
    for (let x = 0; x < w; x++) for (let z = 0; z < d; z++) {
      const wall = x === 0 || x === w - 1 || z === 0 || z === d - 1;
      if (!wall) continue;
      const node = y === 2 && (x === Math.floor(w / 2) || z === Math.floor(d / 2)) ? "default:glass" : "default:wood";
      add(actions, offset(origin, x, y, z), node, "cabin wall");
    }
  }
  for (let x = -1; x <= w; x++) for (let z = -1; z <= d; z++) {
    if (x === -1 || x === w || z === -1 || z === d || (x + z) % 2 === 0) add(actions, offset(origin, x, 4, z), "default:wood", "cabin roof");
  }
  add(actions, offset(origin, Math.floor(w / 2), 1, 0), "air", "doorway");
  add(actions, offset(origin, Math.floor(w / 2), 2, 0), "air", "doorway");
}

function trail(actions, origin, length, axis="x") {
  for (let i = 0; i < length; i++) add(actions, offset(origin, axis === "x" ? i : 0, 0, axis === "z" ? i : 0), "default:cobble", "trail path");
}

function bridge(actions, origin, length=17, axis="x") {
  for (let i = 0; i < length; i++) {
    const p = offset(origin, axis === "x" ? i : 0, 0, axis === "z" ? i : 0);
    add(actions, p, "default:cobble", "bridge deck");
    if (i % 3 === 0) {
      add(actions, offset(p, 0, 1, 1), "default:torch", "bridge lantern");
      add(actions, offset(p, 0, 1, -1), "default:torch", "bridge lantern");
    }
  }
}

function lanterns(actions, origin, count=8, axis="x") {
  for (let i = 0; i < count; i++) add(actions, offset(origin, axis === "x" ? i * 3 : 0, 2, axis === "z" ? i * 3 : 0), "default:torch", "floating lantern");
}

function lake(actions, origin, w=8, d=5) {
  const cx = w / 2, cz = d / 2;
  for (let x = 0; x < w; x++) for (let z = 0; z < d; z++) {
    if (((x - cx) ** 2) / (cx ** 2) + ((z - cz) ** 2) / (cz ** 2) <= 1) add(actions, offset(origin, x, -1, z), "default:water_source", "alpine water");
  }
}

function pine(actions, origin) {
  for (let y = 0; y < 4; y++) add(actions, offset(origin, 0, y, 0), "default:tree", "pine trunk");
  for (const [y, r] of [[3,2],[4,1],[5,1]]) {
    for (let x = -r; x <= r; x++) for (let z = -r; z <= r; z++) {
      if (Math.abs(x) + Math.abs(z) <= r + 1) add(actions, offset(origin, x, y, z), "default:leaves", "pine canopy");
    }
  }
}

function portal(actions, origin) {
  for (let y = 0; y < 5; y++) {
    add(actions, offset(origin, 0, y, 0), "default:mese", "portal arch");
    add(actions, offset(origin, 4, y, 0), "default:mese", "portal arch");
  }
  for (let x = 0; x < 5; x++) add(actions, offset(origin, x, 5, 0), "default:mese", "portal arch");
  for (let x = 1; x < 4; x++) for (let y = 1; y < 5; y++) if ((x + y) % 2 === 0) add(actions, offset(origin, x, y, 0), "default:mese_post_light", "portal shimmer");
}

function garden(actions, origin, w=8, d=6) {
  for (let x = 0; x < w; x++) for (let z = 0; z < d; z++) {
    const edge = x === 0 || x === w - 1 || z === 0 || z === d - 1;
    add(actions, offset(origin, x, 0, z), edge ? "default:cobble" : "flowers:dandelion_yellow", "garden layout");
  }
}

function tower(actions, origin, height=8) {
  for (let y = 0; y < height; y++) for (const [x,z] of [[0,0],[2,0],[0,2],[2,2]]) add(actions, offset(origin, x, y, z), "default:stone", "tower support");
  for (let x = -1; x <= 3; x++) for (let z = -1; z <= 3; z++) add(actions, offset(origin, x, height, z), "default:stone", "lookout deck");
  add(actions, offset(origin, 1, height + 1, 1), "default:torch", "lookout beacon");
}

function singleFire(actions, origin) {
  add(actions, origin, "fire:basic_flame", "requested fire");
}

function campfire(actions, origin) {
  for (const [x, z] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) add(actions, offset(origin, x, 0, z), "default:cobble", "fire ring");
  add(actions, offset(origin, 0, 0, 0), "default:tree", "campfire fuel");
  add(actions, offset(origin, 0, 1, 0), "fire:basic_flame", "campfire flame");
}

function tntWall(actions, origin, width=9, height=4) {
  for (let x = 0; x < width; x++) {
    for (let y = 0; y < height; y++) {
      add(actions, offset(origin, x, y, 0), "tnt:tnt", "tnt wall");
    }
  }
}

function validate(actions, origin) {
  const issues = [];
  let risk = "low";
  if (actions.length > 512) issues.push(`Plan exceeds 512 node writes: ${actions.length}`);
  for (const a of actions) {
    const d = Math.sqrt((a.pos.x-origin.x)**2 + (a.pos.y-origin.y)**2 + (a.pos.z-origin.z)**2);
    if (d > 96) issues.push(`Action outside safe radius: ${key(a.pos)}`);
    if (a.node.includes("tnt") || a.node.includes("lava")) risk = "medium";
  }
  return { status: issues.length ? "blocked" : "ready", risk: issues.length ? "blocked" : risk, issues };
}

function createPlan(prompt) {
  const clean = prompt.trim().replace(/\s+/g, " ");
  const seed = hashText(clean);
  const rand = rng(seed);
  const text = clean.toLowerCase();
  const origin = pos(0, 16, 0);
  const actions = [];
  const onlyRequested = /\b(only|just)\b/.test(text);
  const wantsFire = /\b(fire|campfire|flame)\b/.test(text);
  const wantsTnt = /\btnt\b|\bexplosive\b/.test(text);
  const simpleOnly = onlyRequested && (wantsFire || wantsTnt);

  if (!simpleOnly) add(actions, origin, "default:cobble", "realm anchor");

  if (simpleOnly && wantsFire) singleFire(actions, origin);
  if (simpleOnly && wantsTnt) tntWall(actions, offset(origin, -4, 0, 0), 9, 4);

  if (!simpleOnly && (text.includes("glacier") || text.includes("mountain") || text.includes("alpine"))) {
    lake(actions, offset(origin, -8, 0, -8), 9, 5);
    trail(actions, offset(origin, -10, 0, 0), 20, "x");
    for (let i = 0; i < 10; i++) pine(actions, offset(origin, Math.floor(rand() * 25) - 12, 0, Math.floor(rand() * 25) - 12));
    cabin(actions, offset(origin, 5, 0, 5), 5, 4);
    tower(actions, offset(origin, -8, 0, 7), 5);
  }
  if (!simpleOnly && text.includes("village")) {
    [[-8,-4],[2,5],[9,-3]].forEach(([dx,dz]) => cabin(actions, offset(origin, dx, 0, dz), 5, 4));
    trail(actions, offset(origin, -10, 0, 0), 22, "x");
    trail(actions, offset(origin, 0, 0, -8), 18, "z");
    lanterns(actions, offset(origin, -8, 0, 0), 6, "x");
  }
  if (!simpleOnly && (text.includes("cabin") || text.includes("house") || text.includes("shelter"))) cabin(actions, offset(origin, 2, 0, 2), 6, 5);
  if (!simpleOnly && text.includes("bridge")) bridge(actions, offset(origin, -8, 0, 0), 17, "x");
  if (!simpleOnly && text.includes("portal")) portal(actions, offset(origin, 0, 0, -7));
  if (!simpleOnly && text.includes("garden")) garden(actions, offset(origin, -5, 0, 5), 8, 6);
  if (!simpleOnly && (text.includes("lake") || text.includes("river") || text.includes("water"))) lake(actions, offset(origin, -6, 0, -6), 8, 5);
  if (!simpleOnly && (text.includes("tower") || text.includes("lookout"))) tower(actions, offset(origin, 6, 0, -6), 8);
  if (!simpleOnly && (text.includes("lantern") || text.includes("light"))) lanterns(actions, offset(origin, -5, 0, -4), 8, "x");
  if (!simpleOnly && wantsFire) campfire(actions, offset(origin, -2, 0, -2));
  if (!simpleOnly && wantsTnt) tntWall(actions, offset(origin, -4, 0, 3), 9, text.includes("wall") ? 4 : 2);
  if (actions.length === 0 || (actions.length === 1 && actions[0].reason === "realm anchor")) {
    cabin(actions, offset(origin, 1, 0, 1), 4, 4);
    lanterns(actions, offset(origin, -3, 0, 0), 4, "x");
  }

  const finalActions = dedupe(actions);
  const safety = validate(finalActions, origin);
  const features = featuresFor(text);
  const materials = [...new Set(finalActions.map(a => a.node))].sort();
  return {
    schema_version: 1,
    plan_id: `plan:${seed.toString(16)}`,
    prompt: clean,
    summary: `Nova prepared a safe ${features.slice(0,4).join(", ")} plan with ${finalActions.length} node writes.`,
    seed,
    origin,
    features,
    materials,
    actions: finalActions,
    safety: { ...safety, requires_approval: true, rollback_policy: "snapshot" },
    approval: { status: "pending" },
    created_at: new Date().toISOString()
  };
}

function project(p) {
  const tile = 18;
  return {
    x: (p.x - p.z) * tile + el.canvas.width / 2,
    y: (p.x + p.z) * tile * 0.48 - p.y * tile * 0.82 + el.canvas.height * 0.58
  };
}

function shade(hex, amt) {
  const n = parseInt(hex.replace("#", ""), 16);
  let r = (n >> 16) + amt, g = ((n >> 8) & 255) + amt, b = (n & 255) + amt;
  r = Math.max(0, Math.min(255, r)); g = Math.max(0, Math.min(255, g)); b = Math.max(0, Math.min(255, b));
  return `rgb(${r},${g},${b})`;
}

function drawDiamond(ctx, x, y, w, h, color) {
  ctx.beginPath();
  ctx.moveTo(x, y - h);
  ctx.lineTo(x + w, y);
  ctx.lineTo(x, y + h);
  ctx.lineTo(x - w, y);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
}

function drawCube(ctx, p, node, ghost=false) {
  if (node === "air") return;
  const {x, y} = project(p);
  const w = 12, h = 6;
  const color = MATERIALS[node] || "#d7def8";
  ctx.globalAlpha = ghost ? 0.52 : 1;
  drawDiamond(ctx, x, y, w, h, shade(color, 16));
  ctx.beginPath(); ctx.moveTo(x - w, y); ctx.lineTo(x, y + h); ctx.lineTo(x, y + h + 12); ctx.lineTo(x - w, y + 12); ctx.closePath(); ctx.fillStyle = shade(color, -24); ctx.fill();
  ctx.beginPath(); ctx.moveTo(x + w, y); ctx.lineTo(x, y + h); ctx.lineTo(x, y + h + 12); ctx.lineTo(x + w, y + 12); ctx.closePath(); ctx.fillStyle = shade(color, -42); ctx.fill();
  ctx.globalAlpha = 1;
}

function render() {
  const ctx = el.canvas.getContext("2d");
  ctx.clearRect(0, 0, el.canvas.width, el.canvas.height);
  const grd = ctx.createLinearGradient(0, 0, 0, el.canvas.height);
  grd.addColorStop(0, "#070b18"); grd.addColorStop(1, "#0a1022");
  ctx.fillStyle = grd; ctx.fillRect(0, 0, el.canvas.width, el.canvas.height);
  ctx.strokeStyle = "rgba(78,168,255,.12)";
  for (let i = -30; i <= 30; i++) {
    const a = project(pos(i, 0, -30)); const b = project(pos(i, 0, 30));
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    const c = project(pos(-30, 0, i)); const d = project(pos(30, 0, i));
    ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(d.x, d.y); ctx.stroke();
  }
  const worldActions = [...state.world.entries()].map(([k, node]) => {
    const [x,y,z] = k.split(",").map(Number); return {pos: pos(x,y,z), node};
  });
  const ghost = state.pendingPlan ? state.pendingPlan.actions : [];
  [...worldActions, ...ghost].sort((a,b) => (a.pos.x+a.pos.z+a.pos.y) - (b.pos.x+b.pos.z+b.pos.y)).forEach(a => drawCube(ctx, a.pos, a.node, ghost.includes(a)));
}

function updateUI() {
  const plan = state.pendingPlan;
  el.approve.disabled = !(plan && plan.safety.status === "ready");
  el.exportJson.disabled = !plan;
  el.exportLua.disabled = !plan;
  el.undo.disabled = state.rollbackStack.length === 0;
  if (!plan) {
    el.previewTitle.textContent = "No plan yet";
    el.planSummary.textContent = "Waiting for prompt";
    el.metrics.innerHTML = "";
    el.planList.innerHTML = "";
    el.recipe.textContent = "";
    render();
    return;
  }
  el.previewTitle.textContent = plan.features.join(" + ");
  el.planSummary.textContent = plan.summary;
  el.risk.className = `risk ${plan.safety.risk}`;
  el.risk.textContent = plan.safety.risk.toUpperCase();
  el.metrics.innerHTML = `
    <div class="metric"><b>${plan.actions.length}</b><span>node writes</span></div>
    <div class="metric"><b>${plan.materials.length}</b><span>materials</span></div>
    <div class="metric"><b>${plan.safety.status}</b><span>safety gate</span></div>
  `;
  const grouped = {};
  for (const a of plan.actions) grouped[a.reason] = (grouped[a.reason] || 0) + 1;
  el.planList.innerHTML = Object.entries(grouped).map(([reason, count]) => `<li><strong>${reason}</strong><br>${count} planned changes</li>`).join("");
  el.recipe.textContent = JSON.stringify(plan, null, 2);
  render();
}

function log(event, message) {
  state.audit.unshift({event, message, time: new Date().toLocaleTimeString()});
  el.audit.innerHTML = state.audit.slice(0, 8).map(a => `<div class="audit-item"><strong>${a.event}</strong> ${a.time}<br>${a.message}</div>`).join("");
}

function safeText(value, fallback="unknown") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function setText(target, value, fallback="unknown") {
  if (!target) return;
  target.textContent = safeText(value, fallback);
}

function compactDate(value) {
  if (!value) return "no timestamp";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return safeText(value);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

function formatServiceDetail(services) {
  if (!services || typeof services !== "object") return "No service data";
  return ["family", "fork", "adapter", "studio"]
    .map(name => `${name} ${services[name]?.status || "unknown"}`)
    .join(" · ");
}

function renderLiveStatus(data) {
  const fork = data?.fork || {};
  const services = data?.services || {};
  const quality = data?.quality_gate || {};
  const promptEval = data?.prompt_eval || {};
  const adapter = data?.adapter_log || {};
  const latest = adapter.latest || {};
  const allActive = data?.services_all_active === true;
  const qualityStatus = quality.status || "unknown";
  const requestLogStatus = quality.request_log_gate_status || "unknown";
  const adapterCurrentOk = adapter.present && latest.ok === true && qualityStatus === "pass" && requestLogStatus === "pass";
  const mutationAuthority = latest.world_mutation_authority || "luanti";
  const directMutation = latest.direct_world_mutation === true || data?.direct_world_mutation_by_ai === true;

  setText(el.runtimeCommit, fork.commit || "local");
  setText(el.runtimeState, allActive ? "Live: services active" : "Live: attention needed");
  setText(el.operatorState, data?.live_bridge ? "Live bridge" : "Local");

  setText(el.servicesStatus, allActive ? "All active" : "Attention");
  setText(el.servicesDetail, formatServiceDetail(services));
  el.servicesStatus?.classList.toggle("status-ok", allActive);
  el.servicesStatus?.classList.toggle("status-warn", !allActive);

  setText(el.qualityStatus, qualityStatus);
  setText(
    el.qualityDetail,
    `gate ${quality.live_prompt_eval_status || "unknown"} · log ${requestLogStatus} · ${compactDate(quality.generated_at)}`
  );
  el.qualityStatus?.classList.toggle("status-ok", qualityStatus === "pass");
  el.qualityStatus?.classList.toggle("status-warn", qualityStatus !== "pass");

  setText(
    el.adapterStatus,
    adapter.present ? (adapterCurrentOk ? "Current pass" : "Needs review") : "No log"
  );
  setText(
    el.adapterDetail,
    latest.created_at || latest.selected_option_id
      ? `${latest.selected_option_id || "no option"} · recent ${adapter.recent_successes || 0}/${adapter.recent_window_entries || 0} · history ${adapter.successes || 0}/${adapter.total_entries || 0}`
      : "No public-safe request summary yet"
  );
  el.adapterStatus?.classList.toggle("status-ok", adapterCurrentOk);
  el.adapterStatus?.classList.toggle("status-warn", !adapterCurrentOk);

  setText(el.latestPlanStatus, latest.selected_option_id || "No selected plan");
  setText(
    el.latestPlanDetail,
    `authority=${mutationAuthority} · direct mutation=${directMutation ? "true" : "false"}`
  );

  const evalPass = promptEval.current_health === "pass";
  setText(
    el.evalStatus,
    promptEval.present ? `${promptEval.cases_passed || 0}/${promptEval.cases_total || 0} cases` : "No eval"
  );
  setText(
    el.evalDetail,
    promptEval.present
      ? `${promptEval.golden_prompts_passed || 0}/${promptEval.golden_prompts_total || 0} golden · agentic ${promptEval.agentic_tool_cases || 0}/${promptEval.agentic_tool_cases_required || 0} · no mutation ${promptEval.safety?.no_world_mutation === true ? "yes" : "unknown"}`
      : "No public-safe eval summary loaded"
  );
  el.evalStatus?.classList.toggle("status-ok", evalPass);
  el.evalStatus?.classList.toggle("status-warn", !evalPass);
}

function renderLiveStatusUnavailable() {
  setText(el.runtimeState, "Local static mode");
  setText(el.operatorState, "Local");
  setText(el.servicesStatus, "Offline");
  setText(el.servicesDetail, "Serve with studio/server.py for Pi telemetry");
  setText(el.qualityStatus, "Unavailable");
  setText(el.qualityDetail, "No live bridge response");
  setText(el.adapterStatus, "Unavailable");
  setText(el.adapterDetail, "No Agents SDK summary loaded");
  setText(el.latestPlanStatus, "Local planner");
  setText(el.latestPlanDetail, "Browser-only preview and export mode");
  setText(el.evalStatus, "Unavailable");
  setText(el.evalDetail, "No live golden prompt summary loaded");
}

async function loadLiveStatus() {
  if (window.location.protocol === "file:") {
    renderLiveStatusUnavailable();
    return;
  }
  try {
    const response = await fetch("/api/status", {cache: "no-store"});
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();
    if (data?.public_safe !== true || data?.live_bridge !== true) throw new Error("unsafe status payload");
    renderLiveStatus(data);
  } catch {
    renderLiveStatusUnavailable();
  }
}

function approvePlan() {
  const plan = state.pendingPlan;
  if (!plan || plan.safety.status !== "ready") return;
  const before = new Map();
  for (const a of plan.actions) before.set(key(a.pos), state.world.get(key(a.pos)) || null);
  for (const a of plan.actions) {
    if (a.node === "air") state.world.delete(key(a.pos));
    else state.world.set(key(a.pos), a.node);
  }
  const rollbackId = `rollback:${plan.plan_id}:${Date.now().toString(36)}`;
  state.rollbackStack.push({ rollbackId, before });
  plan.approval.status = "applied";
  log("plan.applied", `${plan.actions.length} changes applied. Rollback ready: ${rollbackId}`);
  state.pendingPlan = null;
  updateUI();
}

function undo() {
  const record = state.rollbackStack.pop();
  if (!record) return;
  for (const [k, node] of record.before.entries()) {
    if (node === null) state.world.delete(k);
    else state.world.set(k, node);
  }
  log("rollback.applied", `Restored ${record.before.size} node positions from ${record.rollbackId}.`);
  updateUI();
}

function exportBlob(name, content, type="application/json") {
  const blob = new Blob([content], {type});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

function luaForPlan(plan) {
  const placements = plan.actions
    .filter(a => a.node !== "air")
    .map(a => `  {pos={x=${a.pos.x}, y=${a.pos.y}, z=${a.pos.z}}, node_name=${JSON.stringify(a.node)}}`)
    .join(",\n");
  return `local PLAN_ID = ${JSON.stringify(plan.plan_id)}
local placements = {
${placements}
}
local task_counter = 0

local function runtime_core()
  local candidate = rawget(_G, "core") or minetest
  if type(candidate) ~= "table" then return nil end
  if type(candidate.ai_import_ops) ~= "table" then return nil end
  if type(candidate.ai_import_ops.queue_chunked_structure_apply_task) ~= "function" then return nil end
  if type(candidate.register_ai_agent) ~= "function" then return nil end
  return candidate
end

minetest.register_chatcommand("openrealm_generated_build", {
  description = "Queue generated OpenRealm plan through AI runtime",
  privs = {server = true},
  func = function(name)
    local api = runtime_core()
    if not api then
      return false, "OpenRealm AI runtime import queue is not available."
    end
    local agent_id = "openrealm_studio:generated_builder"
    if type(api.get_ai_agent) ~= "function" or not api.get_ai_agent(agent_id) then
      api.register_ai_agent({
        agent_id = agent_id,
        display_name = "OpenRealm Studio Generated Builder",
        owner = "openrealm",
        plugin = "openrealm_studio_export",
        capabilities = {
          ["import.assets"] = true,
          ["world.place"] = true,
          ["world.batch"] = true,
        },
      })
    end
    task_counter = task_counter + 1
    local task_id = "openrealm-studio:" .. PLAN_ID .. ":" .. tostring(task_counter)
    local chunk_size = math.max(1, math.min(32, #placements))
    local ok, err = pcall(api.ai_import_ops.queue_chunked_structure_apply_task, {
      task_id = task_id,
      agent_id = agent_id,
      owner = name,
      report_id = PLAN_ID,
      world_id = "openrealm-disposable-world",
      staging = true,
      explicit_approval = true,
      allow_mutation = true,
      rollback_policy = "chunked",
      mutation_class = "compat_import",
      operation_label = "openrealm.studio.structure.apply",
      placements = placements,
      chunk_size = chunk_size,
      max_node_writes_per_step = chunk_size,
      max_node_writes_total = ${plan.actions.length},
      max_mapblock_churn_total = ${plan.actions.length},
      source_reference = {
        reference_type = "openrealm_studio_plan",
        redacted_id = PLAN_ID,
        inventory_hash = PLAN_ID,
      },
    })
    if not ok then
      return false, "Failed to queue OpenRealm runtime task: " .. tostring(err)
    end
    return true, "OpenRealm generated plan queued as AI runtime task " .. task_id
  end,
})
`;
}

el.preset.addEventListener("change", () => { el.prompt.value = el.preset.value; });
el.generate.addEventListener("click", () => {
  state.pendingPlan = createPlan(el.prompt.value);
  log("plan.created", state.pendingPlan.summary);
  updateUI();
});
el.approve.addEventListener("click", approvePlan);
el.undo.addEventListener("click", undo);
el.exportJson.addEventListener("click", () => state.pendingPlan && exportBlob("openrealm_world_recipe.json", JSON.stringify(state.pendingPlan, null, 2)));
el.exportLua.addEventListener("click", () => state.pendingPlan && exportBlob("openrealm_generated_mod_init.lua", luaForPlan(state.pendingPlan), "text/plain"));

state.pendingPlan = createPlan(el.prompt.value);
log("studio.ready", "Local Nova planner loaded. Generate a plan, preview it, approve it, and undo it.");
updateUI();
loadLiveStatus();
window.setInterval(loadLiveStatus, 30000);
