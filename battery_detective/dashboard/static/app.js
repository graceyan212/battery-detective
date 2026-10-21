"use strict";

const $ = (id) => document.getElementById(id);
const state = {status: null, timeline: null, preset: "6", start: 0, end: 0, selection: null, report: null, generation: 0, investigationGeneration: 0, chartWidth: 1000, showAllProcesses: false};
const svgNS = "http://www.w3.org/2000/svg";
const colors = ["#c2d2ee", "#bed9d7", "#ead9b9", "#d6cdeb", "#d2dbe4"];
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
const displayDate = (ts) => new Date(ts * 1000).toLocaleDateString([], {month: "short", day: "numeric"});
const number = (value, suffix = "", digits = 1) => value == null ? "Unavailable" : value.toFixed(digits) + suffix;

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

function chartX(ts) { return 42 + (ts-state.start)/(state.end-state.start)*(state.chartWidth-54); }

function drawSelection() {
  document.getElementById("selection-region")?.remove();
  if (!state.selection || !state.timeline?.samples.length) return;
  const left = Math.max(state.start, state.selection[0]);
  const right = Math.min(state.end, state.selection[1]);
  if (right > left) $("timeline-chart").append(svg("rect", {id: "selection-region", x: chartX(left), y: 20, width: chartX(right)-chartX(left), height: 295, class: "chart-selection"}));
}

function drawChart() {
  if (!state.timeline?.samples.length || $("chart-panel").hidden) return;
  const root = $("timeline-chart");
  state.chartWidth = Math.max(280, root.getBoundingClientRect().width);
  root.setAttribute("viewBox", `0 0 ${state.chartWidth} 360`);
  const right = state.chartWidth - 12;
  root.replaceChildren(svg("title", {}, "Battery level, processor use, and apps seen in front"));
  const defs = svg("defs");
  const pattern = svg("pattern", {id: "gap-pattern", patternUnits: "userSpaceOnUse", width: 6, height: 6});
  pattern.append(svg("path", {d: "M-1 1 L1 -1 M0 6 L6 0 M5 7 L7 5", stroke: "#d3dce9", "stroke-width": 1}));
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
  for (const band of bands) root.append(svg("rect", {x: chartX(band.start), y: 20, width: chartX(band.end)-chartX(band.start), height: 270, fill: band.kind === "gap" ? "url(#gap-pattern)" : "var(--chart-charge)"}));
  for (const anomaly of state.timeline.anomalies) root.append(svg("rect", {x: chartX(anomaly.start), y: 20, width: chartX(anomaly.end)-chartX(anomaly.start), height: 177, class: "chart-anomaly"}));
  for (const value of [0,25,50,75,100]) {
    const y = 197-value*1.77;
    root.append(svg("line", {x1:42,y1:y,x2:right,y2:y,class:"chart-grid"}),svg("text",{x:31,y:y+4,"text-anchor":"end",class:"chart-label"},value+"%"));
  }
  root.append(svg("text",{x:42,y:225,class:"chart-category"},"Processor use"));
  for (const value of [0,100]) {
    const y = 290-value*.5;
    root.append(svg("line",{x1:42,y1:y,x2:right,y2:y,class:"chart-grid"}),svg("text",{x:31,y:y+3,"text-anchor":"end",class:"chart-label"},value+"%"));
  }
  for (const metric of ["battery_percent", "cpu_percent"]) {
    let path = "";
    const segments = [];
    rows.forEach((row,i) => {
      if (row[metric] == null) return;
      const previous = rows[i-1];
      const continuous = previous && previous[metric] != null && validInterval(previous,row) && (metric === "cpu_percent" || previous.plugged === row.plugged);
      const y = metric === "battery_percent" ? 197-row[metric]*1.77 : 290-row[metric]*.5;
      path += `${continuous?"L":"M"}${chartX(row.timestamp).toFixed(2)} ${y.toFixed(2)} `;
      if (!continuous) segments.push([]);
      segments.at(-1).push([chartX(row.timestamp), y]);
      if (!continuous && metric === "battery_percent") root.append(svg("circle",{cx:chartX(row.timestamp),cy:y,r:2,class:"chart-marker"}));
    });
    if (metric === "battery_percent") {
      for (const points of segments) {
        if (points.length < 2) continue;
        const area = `M${points[0][0]} 197 ` + points.map(([x,y])=>`L${x} ${y}`).join(" ") + ` L${points.at(-1)[0]} 197 Z`;
        root.append(svg("path", {d:area, class:"battery-area"}));
      }
    }
    root.append(svg("path",{d:path,class:metric === "battery_percent" ? "battery-line":"cpu-line"}));
  }
  const lastBattery = rows.filter(row => row.battery_percent != null).at(-1);
  if (lastBattery) {
    const endpoint = svg("circle", {cx: chartX(lastBattery.timestamp), cy: 197-lastBattery.battery_percent*1.77, r: 4.5, class: "battery-endpoint"});
    endpoint.append(svg("title", {}, `${lastBattery.battery_percent}% at ${clock(lastBattery.timestamp)}`));
    root.append(endpoint);
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
  root.append(svg("text",{x:42,y:310,class:"chart-category"},"Apps seen in front"));
  for (const run of runs) {
    const block = svg("rect",{x:chartX(run.start),y:318,width:Math.max(.5,chartX(run.end)-chartX(run.start)),height:9,rx:1,fill:appColors.get(run.key)});
    block.append(svg("title",{},`${run.name}: observations from ${clock(run.start)} to ${clock(run.end)}; switches between samples may be missed`));
    root.append(block);
  }
  const ticks = state.chartWidth < 500 ? 3 : 6;
  for (let tick=0; tick<=ticks; tick++) {
    const ts=state.start+(state.end-state.start)*tick/ticks;
    root.append(svg("text",{x:chartX(ts),y:350,"text-anchor":tick===0?"start":tick===ticks?"end":"middle",class:"chart-label"},clock(ts)));
  }
  drawSelection();
}

function showSummary(report) {
  const latest = state.timeline.samples.at(-1);
  $("battery-reading").textContent = number(latest?.battery_percent,"%",0);
  $("power-reading").textContent = latest ? (latest.plugged === 1 ? latest.charging === 1 ? "Charging" : "Plugged in" : latest.plugged === 0 ? "On battery" : "Power source unknown") + " · latest in window" : "No battery reading";
  $("rate-reading").textContent = report.discharge.rate == null ? "Not enough data" : number(report.discharge.rate);
  $("rate-caption").textContent = report.discharge.rate == null ? "Needs 10 unplugged minutes & a 2-point drop" : "Percentage points, while unplugged";
  $("cpu-reading").textContent = report.system_cpu == null ? "Not enough data" : number(report.system_cpu,"%");
  $("coverage-reading").textContent = number(100*report.quality.covered_seconds/(state.end-state.start),"%",0);
  $("sample-reading").textContent = `${report.sample_count.toLocaleString()} readings in this window`;
  $("rate-reading").classList.toggle("unavailable", report.discharge.rate == null);
  $("cpu-reading").classList.toggle("unavailable", report.system_cpu == null);
  $("battery-reading").classList.toggle("unavailable", latest?.battery_percent == null);
}

function renderProcesses(report) {
  const tbody=$("process-table"); tbody.replaceChildren();
  const processes = state.showAllProcesses ? report.processes : report.processes.slice(0, 5);
  for (const process of processes) {
    const tr=element("tr"), name=element("td",process.name);
    name.append(element("small",`ID ${process.pid}${process.background_observations === process.observations ? " · seen in background" : ""}`));
    tr.append(name,element("td",number(process.cpu_seconds/60," min")),element("td",number(process.cpu_percent,"%")),element("td",number(process.peak_rss/1_000_000," MB",0)));
    tbody.append(tr);
  }
  if (!report.processes.length) {
    const tr=element("tr"), cell=element("td","Not enough activity readings yet. We need two consecutive readings to calculate processor work.");
    cell.colSpan=4; tr.append(cell); tbody.append(tr);
  }
  $("show-processes").hidden = report.processes.length <= 5;
  $("show-processes").textContent = state.showAllProcesses ? "Show top 5" : `Show top ${report.processes.length}`;
  $("show-processes").setAttribute("aria-expanded", String(state.showAllProcesses));
}

function renderInvestigation(data) {
  state.report = data;
  const report=data.investigation;
  state.showAllProcesses = false;
  $("download-report").disabled = !report.sample_count;
  renderProcesses(report);
  $("foreground-list").replaceChildren(...report.foreground.map(app=>element("span",`${app.name} · ${app.observations} readings`)));
  if (!report.foreground.length) $("foreground-list").append(element("span","No app-in-front readings available"));
  const evidence=$("evidence"); evidence.replaceChildren();
  if (report.discharge.rate != null) {
    evidence.append(element("p",`${number(report.discharge.loss,"",Number.isInteger(report.discharge.loss) ? 0 : 1)} battery points used in ${Math.round(report.discharge.duration_seconds/60)} minutes.`,"finding"));
    evidence.append(element("p",`An average of ${number(report.discharge.rate)} percentage points/hour across recorded unplugged periods. Gaps and charging time are excluded.`,"finding-rate"));
  } else {
    evidence.append(element("p",report.sample_count ? "More unplugged time is needed." : "No readings in this period.","finding"));
    evidence.append(element("p","A battery-use estimate needs at least 10 continuous unplugged minutes and a drop of 2 percentage points. Charging and gaps are excluded.","finding-rate"));
  }
  const top = report.contributors[0];
  if (top) {
    evidence.append(element("h4","A possible contributor"));
    const explanation=element("p");
    explanation.append(element("span",top.name,"suspect-name"),document.createTextNode(" did the most recorded processor work during this battery drop. It may have contributed, but these readings cannot tell us its exact battery use."));
    evidence.append(explanation);
  } else evidence.append(element("p","There isn't enough evidence to name a possible contributor."));
  evidence.append(element("p",report.baseline.rate == null ? "There isn't enough earlier unplugged data for a comparison." : `The preceding period averaged ${number(report.baseline.rate)} points/hour. It may have involved different work.`,"comparison"));
  const next=element("div",null,"next-step");
  next.append(element("h4","Try next"),element("p",top ? "If you can pause the related app or workload, repeat a similar unplugged session for at least 15 minutes. Keep brightness and network conditions similar, then compare the battery drop." : "Keep recording during a longer unplugged session, then select that period to compare battery use and activity."));
  if (state.status?.mode === "snapshot" && !report.sample_count) {
    next.lastElementChild.textContent = "Choose a period within this saved recording, or use Reset view to return to the recorded history.";
  }
  evidence.append(next);
  const measurements=element("details"), facts=element("ul");
  measurements.append(element("summary","See supporting measurements"));
  for (const fact of report.observations) {
    const li=element("li"); li.append(element("span",`[${fact.id}] `,"evidence-ref"),document.createTextNode(fact.text)); facts.append(li);
  }
  measurements.append(facts); evidence.append(measurements);
  const limits=element("details"), list=element("ul");
  limits.append(element("summary",`What these readings can't tell you (${report.limitations.length})`));
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
  $("show-processes").hidden = true;
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
    $("selection-label").textContent=`${Math.round((end-start)/60)} min · ${data.investigation.sample_count} readings`;
    error("");
  } catch (err) { if (generation===state.investigationGeneration) { clearInvestigation("This selection could not be analyzed. Refresh to retry."); error(err.message); $("selection-label").textContent="Could not analyze this window"; } }
}

function renderAnomalies() {
  const target=$("anomaly-list"); target.replaceChildren();
  if (!state.timeline.anomalies.length) target.append(element("span","No sustained fast-drain periods detected in this window."));
  for (const anomaly of state.timeline.anomalies) {
    const button=element("button",`Fast drain: ${clock(anomaly.start)}–${clock(anomaly.end)} · ${number(anomaly.rate)} points/hour`,"anomaly-button");
    button.type="button";
    button.addEventListener("click",()=>{setSelection(anomaly.start,anomaly.end); investigateSelection(); $("investigation").scrollIntoView({block:"start"});});
    target.append(button);
  }
}

function showSourceContext(status) {
  const saved = status.mode === "snapshot";
  $("database-path").textContent = saved ? "" : status.database;
  $("collect-command").hidden = saved;
  $("collect-command").textContent = saved ? "" : `python -m battery_detective collect --db '${status.database.replaceAll("'", "'\\''")}'`;
  document.querySelector(".data-location").hidden = saved;
  $("refresh-label").textContent = saved ? "Reset view" : "Refresh";
  $("cpu-caption").textContent = saved ? "Average across the recorded Mac" : "Average across your Mac";
  if (saved) {
    $("storage-description").textContent = "Saved recording. This page does not monitor your device.";
    $("guide-intro").querySelector("p").textContent = "These measurements were recorded on a Mac and shared as a saved session. The collector samples battery and activity every 60 seconds by default. This page explores that recording; it does not read your device or receive new measurements.";
    const source = $("guide-drain").querySelector(".source");
    source.textContent = "Calculated with Python analysis of the saved recording. This is a rate of battery change, not a measurement of an individual app's power.";
    $("guide-sensors").lastElementChild.textContent = "Reports use fixed calculations, not an AI model. Possible contributors are ranked by observed CPU work during valid unplugged periods. Correlation means two things happened together; it does not prove that one caused the other.";
  }
}

async function loadWindow() {
  const generation=++state.generation;
  ++state.investigationGeneration;
  $("refresh").disabled=true;
  clearInvestigation("Loading measurements…");
  $("chart-panel").hidden=true;
  for (const id of ["battery-reading", "rate-reading", "cpu-reading", "coverage-reading"]) {
    $(id).textContent="…";
    $(id).classList.remove("unavailable");
  }
  $("power-reading").textContent="Checking battery readings";
  $("rate-caption").textContent="Percentage points, while unplugged";
  $("sample-reading").textContent="Reading history";
  error("");
  try {
    const requestedThreshold=threshold();
    const status=await api("status");
    if (generation!==state.generation) return;
    state.status=status;
    showSourceContext(status);
    const saved=status.mode === "snapshot";
    const synthetic=status.sources.includes("synthetic");
    $("demo-notice").hidden=!synthetic;
    const fresh=!saved && !synthetic && status.latest && status.now-status.latest < 100;
    $("collector-state").className="status"+(fresh?" fresh":"");
    $("collector-state").textContent=saved?`Saved recording · ${displayDate(status.recording.end)}`:synthetic?"Example history":status.latest?`Last reading ${displayDate(status.latest)}, ${clock(status.latest)}`:"No readings yet";
    // Shared recordings remain anchored to the exported window as time passes.
    const anchor=saved?status.recording.end:synthetic?status.latest:status.now;
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
      for (const id of ["battery-reading", "rate-reading", "cpu-reading", "coverage-reading"]) {
        $(id).textContent="Not yet"; $(id).classList.add("unavailable");
      }
      $("power-reading").textContent="Waiting for the first reading";
      $("sample-reading").textContent="No recorded history";
      $("empty-copy").textContent="Start the collector in a terminal, then refresh this page. Opening the dashboard alone does not start recording.";
      $("latest-window").hidden=true;
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
    $("empty-copy").textContent="There are no readings in this period. Choose another window or show your latest recorded history.";
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
$("refresh").addEventListener("click",()=>{
  if (state.status?.mode === "snapshot") {
    document.querySelector('[data-preset="6"]').click();
  } else loadWindow();
});
$("threshold").addEventListener("change",loadWindow);
$("latest-window").addEventListener("click",()=>{state.preset="custom";state.end=state.status.latest;state.start=Math.max(state.status.first,state.end-6*3600);if(state.start===state.end)state.start-=60;$("custom-range").hidden=false;document.querySelectorAll("[data-preset]").forEach(node=>{const active=node.dataset.preset==="custom";node.classList.toggle("selected",active);node.setAttribute("aria-pressed",String(active));});loadWindow();});
$("download-report").addEventListener("click",()=>{
  if (!state.report) return;
  const url=URL.createObjectURL(new Blob([state.report.markdown],{type:"text/markdown;charset=utf-8"}));
  const link=element("a");link.href=url;link.download="battery-investigation.md";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
let drag=null;
function pointerTime(event) {
  const rect=$("timeline-chart").getBoundingClientRect();
  const fraction=Math.max(0,Math.min(1,((event.clientX-rect.left)/rect.width*state.chartWidth-42)/(state.chartWidth-54)));
  const target=state.start+fraction*(state.end-state.start);
  return state.timeline.samples.reduce((closest,row)=>Math.abs(row.timestamp-target)<Math.abs(closest-target)?row.timestamp:closest,state.timeline.samples[0].timestamp);
}
function cancelDrag() {
  if (!drag) return;
  setSelection(...drag.selection);
  $("selection-label").textContent=drag.label;
  drag=null;
}
$("timeline-chart").addEventListener("pointerdown",event=>{
  if (!state.timeline?.samples.length || !state.selection || drag) return;
  drag={start:pointerTime(event), selection:[...state.selection], label:$("selection-label").textContent};
  $("timeline-chart").setPointerCapture(event.pointerId);
});
$("timeline-chart").addEventListener("pointermove",event=>{
  if (!drag) return;
  const end=pointerTime(event);
  setSelection(Math.min(drag.start,end),Math.max(drag.start,end));
});
$("timeline-chart").addEventListener("pointerup",event=>{
  if (!drag) return;
  const start=drag.start, end=pointerTime(event);
  if (end===start) { cancelDrag(); return; }
  drag=null;
  setSelection(Math.min(start,end),Math.max(start,end));
  investigateSelection();
});
$("timeline-chart").addEventListener("pointercancel",cancelDrag);
$("timeline-chart").addEventListener("lostpointercapture",cancelDrag);
$("chart-timezone").textContent=Intl.DateTimeFormat().resolvedOptions().timeZone;
document.querySelectorAll('input[type="datetime-local"]').forEach(input => { input.step = "1"; });

$("show-processes").addEventListener("click", () => {
  if (!state.report) return;
  state.showAllProcesses = !state.showAllProcesses;
  renderProcesses(state.report.investigation);
});

const guide = $("measurement-dialog");
let guideTrigger = null;
document.querySelectorAll("[data-help]").forEach(button => {
  button.addEventListener("click", () => {
    guideTrigger = button;
    guide.showModal();
    document.body.classList.add("guide-open");
    const section = $("guide-" + button.dataset.help);
    section.focus({preventScroll: true});
    section.scrollIntoView({block: "start"});
  });
});
$("close-guide").addEventListener("click", () => guide.close());
guide.addEventListener("close", () => {
  document.body.classList.remove("guide-open");
  guideTrigger?.focus({preventScroll: true});
});
let resizeFrame;
new ResizeObserver(() => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(drawChart);
}).observe($("chart-panel"));
loadWindow();
