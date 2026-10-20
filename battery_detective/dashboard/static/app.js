"use strict";

const $ = (id) => document.getElementById(id);
const state = {status: null, timeline: null, preset: "6", start: 0, end: 0, selection: null, report: null, generation: 0, investigationGeneration: 0};
const svgNS = "http://www.w3.org/2000/svg";
const colors = ["#b8d7d6", "#b9c9d7", "#d6c6ad", "#c4cbb8", "#cfc6d6"];
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
const displayDate = (ts) => new Date(ts * 1000).toLocaleDateString([], {month: "short", day: "numeric"});
const number = (value, suffix = "", digits = 1) => value == null ? "—" : value.toFixed(digits) + suffix;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function svg(tag, attrs = {}, text) {
  const node = document.createElementNS(svgNS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text != null) node.textContent = text;
  return node;
}

function localInput(ts) {
  const date = new Date(ts * 1000);
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return shifted.toISOString().slice(0, 19);
}

function inputTime(id, original) {
  // Keep sub-second sample boundaries when the displayed input was not edited.
  if (original != null && $(id).value === localInput(original)) return original;
  const timestamp = new Date($(id).value).getTime() / 1000;
  if (!Number.isFinite(timestamp)) throw new Error("Choose both a start and end time.");
  return timestamp;
}

function error(message) {
  $("error").textContent = message || "";
  $("error").hidden = !message;
}

async function api(route, params) {
  const query = params ? "?" + new URLSearchParams(params) : "";
  const response = await fetch("/api/" + route + query, {cache: "no-store"});
  const data = await response.json();
  if (!response.ok || data.error) throw new Error(data.error || "Could not read measurements. Refresh to retry.");
  return data;
}

function threshold() {
  const value = Number($("threshold").value);
  if (!(value > 0 && value <= 100)) throw new Error("Choose a threshold from 1 to 100 percentage points/hour.");
  return value;
}

function validInterval(a, b) {
  const dt = b.timestamp - a.timestamp;
  return a.session_id === b.session_id && !b.gap_reason && b.elapsed_seconds != null && dt > 0 && dt <= b.interval_seconds * 1.5 && Math.abs(dt - b.elapsed_seconds) <= 2;
}

function setSelection(start, end) {
  state.selection = [start, end];
  $("selection-start").value = localInput(start);
  $("selection-end").value = localInput(end);
  $("selection-label").textContent = `${Math.round((end-start)/60)} min selected`;
  drawSelection();
}

function chartX(ts) { return 55 + (ts-state.start)/(state.end-state.start)*925; }

function drawSelection() {
  document.getElementById("selection-region")?.remove();
  if (!state.selection || !state.timeline?.samples.length) return;
  const left = Math.max(state.start, state.selection[0]);
  const right = Math.min(state.end, state.selection[1]);
  if (right > left) $("timeline-chart").append(svg("rect", {id: "selection-region", x: chartX(left), y: 20, width: chartX(right)-chartX(left), height: 295, class: "chart-selection"}));
}

function drawChart() {
  const root = $("timeline-chart");
  root.replaceChildren(svg("title", {}, "Battery percentage, CPU utilization, and sampled foreground apps"));
  const defs = svg("defs");
  const pattern = svg("pattern", {id: "gap-pattern", patternUnits: "userSpaceOnUse", width: 6, height: 6});
  pattern.append(svg("path", {d: "M-1 1 L1 -1 M0 6 L6 0 M5 7 L7 5", stroke: "#d6dfe4", "stroke-width": 1}));
  defs.append(pattern); root.append(defs);
  const rows = state.timeline.samples;
  const bands = [];
  for (let i = 1; i < rows.length; i++) {
    const a = rows[i-1], b = rows[i];
    const kind = !validInterval(a,b) ? "gap" : a.plugged === 1 && b.plugged === 1 ? "charge" : null;
    if (!kind) continue;
    const last = bands.at(-1);
    if (last && last.kind === kind && last.end === a.timestamp) last.end = b.timestamp;
    else bands.push({start: a.timestamp, end: b.timestamp, kind});
  }
  if (rows.length && rows[0].timestamp > state.start+90) bands.push({start: state.start, end: rows[0].timestamp, kind: "gap"});
  if (rows.length && state.end-rows.at(-1).timestamp > 90) bands.push({start: rows.at(-1).timestamp, end: state.end, kind: "gap"});
  for (const band of bands) root.append(svg("rect", {x: chartX(band.start), y: 20, width: chartX(band.end)-chartX(band.start), height: 270, fill: band.kind === "gap" ? "url(#gap-pattern)" : "#e7f3f2"}));
  for (const anomaly of state.timeline.anomalies) root.append(svg("rect", {x: chartX(anomaly.start), y: 20, width: chartX(anomaly.end)-chartX(anomaly.start), height: 177, class: "chart-anomaly"}));
  for (const value of [0,25,50,75,100]) {
    const y = 197-value*1.77;
    root.append(svg("line", {x1:55,y1:y,x2:980,y2:y,class:"chart-grid"}),svg("text",{x:42,y:y+4,"text-anchor":"end",class:"chart-label"},value+"%"));
  }
  root.append(svg("text",{x:55,y:225,class:"chart-category"},"System CPU"));
  for (const value of [0,100]) {
    const y = 290-value*.5;
    root.append(svg("line",{x1:55,y1:y,x2:980,y2:y,class:"chart-grid"}),svg("text",{x:42,y:y+3,"text-anchor":"end",class:"chart-label"},value+"%"));
  }
  for (const metric of ["battery_percent", "cpu_percent"]) {
    let path = "";
    rows.forEach((row,i) => {
      if (row[metric] == null) return;
      const previous = rows[i-1];
      const continuous = previous && previous[metric] != null && validInterval(previous,row) && (metric === "cpu_percent" || previous.plugged === row.plugged);
      const y = metric === "battery_percent" ? 197-row[metric]*1.77 : 290-row[metric]*.5;
      path += `${continuous?"L":"M"}${chartX(row.timestamp).toFixed(2)} ${y.toFixed(2)} `;
      if (!continuous && metric === "battery_percent") root.append(svg("circle",{cx:chartX(row.timestamp),cy:y,r:2,class:"chart-marker"}));
    });
    root.append(svg("path",{d:path,class:metric === "battery_percent" ? "battery-line":"cpu-line"}));
  }
  const appColors = new Map(), runs = [];
  for (let i = 1; i < rows.length; i++) {
    const a=rows[i-1], b=rows[i];
    if (!validInterval(a,b) || !a.foreground_name) continue;
    const name=a.foreground_name, key=a.foreground_bundle_id || name;
    if (!appColors.has(key)) appColors.set(key, colors[appColors.size%colors.length]);
    const last=runs.at(-1);
    if (last && last.key === key && last.end === a.timestamp) last.end=b.timestamp;
    else runs.push({start:a.timestamp,end:b.timestamp,name,key});
  }
  root.append(svg("text",{x:55,y:310,class:"chart-category"},"Foreground samples"));
  for (const run of runs) {
    const block = svg("rect",{x:chartX(run.start),y:318,width:Math.max(.5,chartX(run.end)-chartX(run.start)),height:9,rx:1,fill:appColors.get(run.key)});
    block.append(svg("title",{},`${run.name}: observations from ${clock(run.start)} to ${clock(run.end)}; switches between samples may be missed`));
    root.append(block);
  }
  for (let tick=0; tick<=6; tick++) {
    const ts=state.start+(state.end-state.start)*tick/6;
    root.append(svg("text",{x:chartX(ts),y:350,"text-anchor":tick===0?"start":tick===6?"end":"middle",class:"chart-label"},clock(ts)));
  }
  drawSelection();
}

function showSummary(report) {
  const latest = state.timeline.samples.at(-1);
  $("battery-reading").textContent = number(latest?.battery_percent,"%",0);
  $("power-reading").textContent = latest ? latest.plugged === 1 ? latest.charging === 1 ? "Charging" : "External power" : latest.plugged === 0 ? "On battery" : "Power state unknown" : "No reading";
  $("rate-reading").textContent = number(report.discharge.rate);
  $("cpu-reading").textContent = number(report.system_cpu,"%");
  $("coverage-reading").textContent = number(100*report.quality.covered_seconds/(state.end-state.start),"%",0);
  $("sample-reading").textContent = `${report.sample_count.toLocaleString()} samples in window`;
}

function renderInvestigation(data) {
  state.report = data;
  const report=data.investigation;
  $("download-report").disabled = !report.sample_count;
  const tbody=$("process-table"); tbody.replaceChildren();
  for (const process of report.processes) {
    const tr=element("tr"), name=element("td",process.name);
    name.append(element("small",`PID ${process.pid} · ${process.observations} intervals${process.background_observations === process.observations ? " · background" : ""}`));
    tr.append(name,element("td",number(process.cpu_seconds/60," min")),element("td",number(process.cpu_percent,"%")),element("td",number(process.peak_rss/1024/1024," MB",0)));
    tbody.append(tr);
  }
  if (!report.processes.length) {
    const tr=element("tr"), cell=element("td","No process deltas in this window. At least two continuous samples are needed.");
    cell.colSpan=4; tr.append(cell); tbody.append(tr);
  }
  $("foreground-list").replaceChildren(...report.foreground.map(app=>element("span",`${app.name} · ${app.observations} samples`)));
  if (!report.foreground.length) $("foreground-list").append(element("span","Foreground context unavailable"));
  const evidence=$("evidence"); evidence.replaceChildren();
  evidence.append(element("h4","What happened"));
  evidence.append(element("p",report.observations[0]?.text || "No measurements in this window.","finding"));
  evidence.append(element("h4","What changed"));
  evidence.append(element("p",report.baseline.rate == null ? "No qualifying discharge baseline in the preceding window." : `Preceding window: ${number(report.baseline.rate)} pp/h. Workloads are not matched.`));
  if (report.cpu_change != null) evidence.append(element("p",`System CPU changed by ${report.cpu_change>=0?"+":""}${number(report.cpu_change)} percentage points.`));
  const facts=element("ul");
  const supportingFacts = report.observations.filter(fact => fact.id === "C1" || fact.id.startsWith(report.contributors.length ? "D" : "P"));
  for (const fact of supportingFacts.slice(0,4)) {
    const li=element("li"); li.append(element("span",`[${fact.id}] `,"evidence-ref"),document.createTextNode(fact.text)); facts.append(li);
  }
  evidence.append(facts,element("h4","Potential explanations"));
  if (!report.hypotheses.length) evidence.append(element("p","Insufficient evidence to rank contributors to battery drain."));
  for (const hypothesis of report.hypotheses.slice(0,2)) evidence.append(element("p",`${hypothesis.text} [${hypothesis.evidence.join(", ")}]`));
  evidence.append(element("h4","Next experiment"),element("p",report.experiments[0]));
  const limits=element("details"), list=element("ul");
  limits.append(element("summary",`Limitations and data quality (${report.limitations.length})`));
  for (const limitation of report.limitations) list.append(element("li",limitation));
  limits.append(list); evidence.append(limits);
}

function clearInvestigation(message) {
  state.report = null;
  $("download-report").disabled = true;
  $("evidence").replaceChildren(element("p", message, "quiet"));
  const row = element("tr"), cell = element("td", message);
  cell.colSpan = 4; row.append(cell);
  $("process-table").replaceChildren(row);
  $("foreground-list").replaceChildren();
}

async function investigateSelection() {
  if (!state.selection) return;
  const generation=++state.investigationGeneration;
  const [start,end]=state.selection;
  clearInvestigation("Reading measurements for this selection…");
  $("selection-label").textContent="Analyzing…";
  $("download-report").disabled=true;
  try {
    const data=await api("investigate",{start,end,threshold:threshold()});
    if (generation !== state.investigationGeneration) return;
    renderInvestigation(data);
    $("selection-label").textContent=`${Math.round((end-start)/60)} min · ${data.investigation.sample_count} samples`;
    error("");
  } catch (err) { if (generation===state.investigationGeneration) { clearInvestigation("This selection could not be analyzed. Refresh to retry."); error(err.message); $("selection-label").textContent="Could not analyze this window"; } }
}

function renderAnomalies() {
  const target=$("anomaly-list"); target.replaceChildren();
  if (!state.timeline.anomalies.length) target.append(element("span","No sustained fast-drain periods detected in this window."));
  for (const anomaly of state.timeline.anomalies) {
    const button=element("button",`${clock(anomaly.start)}–${clock(anomaly.end)} · ${number(anomaly.rate)} pp/h`,"anomaly-button");
    button.type="button";
    button.addEventListener("click",()=>{setSelection(anomaly.start,anomaly.end); investigateSelection(); $("investigation").scrollIntoView({block:"start"});});
    target.append(button);
  }
}

async function loadWindow() {
  const generation=++state.generation;
  ++state.investigationGeneration;
  $("refresh").disabled=true;
  clearInvestigation("Loading measurements…");
  $("chart-panel").hidden=true;
  for (const id of ["battery-reading", "rate-reading", "cpu-reading", "coverage-reading"]) $(id).textContent="—";
  $("sample-reading").textContent="Reading history";
  error("");
  try {
    const requestedThreshold=threshold();
    const status=await api("status");
    if (generation!==state.generation) return;
    state.status=status;
    $("database-path").textContent=status.database;
    $("collect-command").textContent=`python -m battery_detective collect --db '${status.database.replaceAll("'", "'\\''")}'`;
    const synthetic=status.sources.includes("synthetic");
    $("demo-notice").hidden=!synthetic;
    const fresh=!synthetic && status.latest && status.now-status.latest < 100;
    $("collector-state").className="status"+(fresh?" fresh":"");
    $("collector-state").textContent=synthetic?"Synthetic history":status.latest?`${fresh?"Recent sample":"Last sample"} ${displayDate(status.latest)}, ${clock(status.latest)}`:"Collector has no samples";
    // Demo is historical by definition; live presets always refer to the present.
    const anchor=synthetic?status.latest:status.now;
    if (state.preset!=="custom") {
      state.end=anchor || status.now;
      if (state.preset==="today") { const date=new Date(state.end*1000); date.setHours(0,0,0,0); state.start=date.getTime()/1000; }
      else state.start=state.end-Number(state.preset)*3600;
    }
    $("date-label").textContent=new Date(state.end*1000).toLocaleDateString([],{weekday:"long",year:"numeric",month:"long",day:"numeric"});
    $("window-label").textContent=`${displayDate(state.start)}, ${clock(state.start)} – ${displayDate(state.end)}, ${clock(state.end)}`;
    $("window-start").value=localInput(state.start); $("window-end").value=localInput(state.end);
    if (!status.samples) {
      state.timeline={samples:[],anomalies:[]}; state.report=null; state.selection=null;
      $("empty-state").hidden=false; $("chart-panel").hidden=true; $("investigation").hidden=true;
      $("anomaly-list").replaceChildren(); $("download-report").disabled=true;
      error(""); return;
    }
    const params={start:state.start,end:state.end,threshold:requestedThreshold};
    const [timeline, summary]=await Promise.all([api("timeline",params),api("investigate",params)]);
    if (generation!==state.generation) return;
    state.timeline=timeline;
    $("empty-state").hidden=!!timeline.samples.length;
    $("chart-panel").hidden=!timeline.samples.length;
    $("investigation").hidden=!timeline.samples.length;
    $("latest-window").hidden=!!timeline.samples.length;
    $("empty-copy").textContent="Choose a window with recorded measurements, or start the collector and refresh.";
    showSummary(summary.investigation); renderAnomalies();
    if (timeline.samples.length) {
      const first=timeline.anomalies[0];
      // Select actual sample boundaries so the first interval isn't silently clipped.
      const selection=first?[first.start,first.end]:[timeline.samples[0].timestamp,timeline.samples.at(-1).timestamp];
      if (selection[1]<=selection[0]) selection[1]=selection[0]+60;
      setSelection(...selection); drawChart();
      await investigateSelection();
    }
  } catch (err) { if (generation===state.generation) error(err.message); }
  finally { if (generation===state.generation) $("refresh").disabled=false; }
}

for (const button of document.querySelectorAll("[data-preset]")) {
  button.addEventListener("click",()=>{
    state.preset=button.dataset.preset;
    document.querySelectorAll("[data-preset]").forEach(node=>{node.classList.toggle("selected",node===button);node.setAttribute("aria-pressed",String(node===button));});
    $("custom-range").hidden=state.preset!=="custom";
    if (state.preset!=="custom") loadWindow();
  });
}
$("custom-range").addEventListener("submit",event=>{event.preventDefault();try {state.start=inputTime("window-start",state.start);state.end=inputTime("window-end",state.end);loadWindow();}catch(err){error(err.message);}});
$("investigate-form").addEventListener("submit",event=>{event.preventDefault();try {const start=inputTime("selection-start",state.selection?.[0]),end=inputTime("selection-end",state.selection?.[1]);if(end<=start)throw new Error("Choose an end time after the start time.");setSelection(start,end);investigateSelection();}catch(err){error(err.message);}});
$("refresh").addEventListener("click",loadWindow);
$("threshold").addEventListener("change",loadWindow);
$("latest-window").addEventListener("click",()=>{state.preset="custom";state.end=state.status.latest;state.start=Math.max(state.status.first,state.end-6*3600);if(state.start===state.end)state.start-=60;$("custom-range").hidden=false;document.querySelectorAll("[data-preset]").forEach(node=>{const active=node.dataset.preset==="custom";node.classList.toggle("selected",active);node.setAttribute("aria-pressed",String(active));});loadWindow();});
$("download-report").addEventListener("click",()=>{
  if (!state.report) return;
  const url=URL.createObjectURL(new Blob([state.report.markdown],{type:"text/markdown;charset=utf-8"}));
  const link=element("a");link.href=url;link.download="battery-investigation.md";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
let dragStart=null;
function pointerTime(event) {
  const rect=$("timeline-chart").getBoundingClientRect();
  const fraction=Math.max(0,Math.min(1,((event.clientX-rect.left)/rect.width*1000-55)/925));
  const target=state.start+fraction*(state.end-state.start);
  return state.timeline.samples.reduce((closest,row)=>Math.abs(row.timestamp-target)<Math.abs(closest-target)?row.timestamp:closest,state.timeline.samples[0].timestamp);
}
$("timeline-chart").addEventListener("pointerdown",event=>{if(!state.timeline?.samples.length)return;dragStart=pointerTime(event);$("timeline-chart").setPointerCapture(event.pointerId);});
$("timeline-chart").addEventListener("pointermove",event=>{if(dragStart==null)return;const end=pointerTime(event);setSelection(Math.min(dragStart,end),Math.max(dragStart,end));});
$("timeline-chart").addEventListener("pointerup",event=>{if(dragStart==null)return;const end=pointerTime(event);if(end!==dragStart){setSelection(Math.min(dragStart,end),Math.max(dragStart,end));investigateSelection();}dragStart=null;});
$("timeline-chart").addEventListener("pointercancel",()=>{dragStart=null;});
$("chart-timezone").textContent=Intl.DateTimeFormat().resolvedOptions().timeZone;
document.querySelectorAll('input[type="datetime-local"]').forEach(input => { input.step = "1"; });
loadWindow();
