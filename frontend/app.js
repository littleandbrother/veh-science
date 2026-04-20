const statusBox = document.getElementById('status');
const taskCardInput = document.getElementById('task-card');
const outputDirInput = document.getElementById('output-dir');
const taskMeta = document.getElementById('task-meta');

let currentTask = null;
let currentProgram = null;

const runBtn = document.getElementById('run-btn');
const refreshBtn = document.getElementById('refresh-btn');
const rebuildReportBtn = document.getElementById('rebuild-report-btn');
const smokeBtn = document.getElementById('smoke-btn');
const runsBtn = document.getElementById('runs-btn');

runBtn.addEventListener('click', runReplay);
refreshBtn.addEventListener('click', loadLatest);
rebuildReportBtn.addEventListener('click', rebuildReport);
smokeBtn.addEventListener('click', runSmoke);
runsBtn.addEventListener('click', loadRuns);

async function init() {
  try {
    const response = await fetch('/api/defaults');
    const data = await response.json();
    if (data.ok) {
      currentTask = data.task;
      taskCardInput.value = data.default_task_card;
      outputDirInput.value = data.default_output_dir;
      renderTaskMeta(currentTask);
      renderAnchors(currentTask.l3_anchors || []);
    }
    await loadRuns();
    setStatus('Dashboard ready.');
  } catch (error) {
    setStatus(`Dashboard init failed:\n${error}`);
  }
}

function setStatus(message) {
  statusBox.textContent = message;
}

function renderTaskMeta(task) {
  if (!task) {
    taskMeta.textContent = '';
    return;
  }
  const anchors = (task.l3_anchors || []).map(anchor => `${anchor.label}@${anchor.frequency_hz}Hz`).join(', ');
  taskMeta.innerHTML = `
    <div><strong>task_id:</strong> ${task.task_id}</div>
    <div><strong>mode:</strong> ${task.discovery_mode}</div>
    <div><strong>allowed tools:</strong> ${(task.allowed_tools || []).join(', ')}</div>
    <div><strong>L3 anchors:</strong> ${anchors || 'none'}</div>
  `;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  return response.json();
}

async function runReplay() {
  setStatus('Running replay...');
  const data = await postJson('/api/run_replay', {
    task_card: taskCardInput.value,
    output_dir: outputDirInput.value,
  });
  if (!data.ok) {
    setStatus(`Replay failed:\n${data.error}`);
    return;
  }
  currentProgram = data.program;
  renderProgram(data.program, data.summary);
  await loadRuns();
  setStatus(`Replay complete. Output: ${data.program.output_dir}`);
}

async function loadLatest() {
  try {
    if (!currentTask) {
      await init();
    }
    const taskId = currentTask?.task_id;
    const url = `/api/program?task_id=${encodeURIComponent(taskId)}&output_dir=${encodeURIComponent(outputDirInput.value)}&task_card=${encodeURIComponent(taskCardInput.value)}`;
    const response = await fetch(url);
    const data = await response.json();
    if (!response.ok) {
      setStatus(`Load latest failed:\n${data.error}`);
      return;
    }
    currentProgram = data;
    renderProgram(data, null);
    setStatus(`Loaded latest program from ${data.output_dir}`);
  } catch (error) {
    setStatus(`Load latest failed:\n${error}`);
  }
}

async function rebuildReport() {
  if (!currentTask) {
    await init();
  }
  setStatus('Rebuilding report...');
  const data = await postJson('/api/rebuild_report', {
    task_card: taskCardInput.value,
    output_dir: outputDirInput.value,
    task_id: currentTask?.task_id,
  });
  if (!data.ok) {
    setStatus(`Rebuild report failed:\n${data.error}`);
    return;
  }
  setStatus(`Report rebuilt: ${data.bundle.report}`);
  if (currentProgram) {
    await loadLatest();
  }
}

async function runSmoke() {
  if (!currentTask) {
    await init();
  }
  setStatus('Running smoke...');
  const data = await postJson('/api/run_smoke', {
    task_card: taskCardInput.value,
    output_dir: outputDirInput.value,
    task_id: currentTask?.task_id,
  });
  if (!data.ok) {
    setStatus(`Smoke failed:\n${data.error}`);
    return;
  }
  renderSmoke(data.smoke_summary);
  setStatus(`Smoke complete. overall_pass=${data.smoke_summary.overall_pass}`);
  if (currentProgram) {
    currentProgram.smoke_summary = data.smoke_summary;
  }
}

async function loadRuns() {
  const response = await fetch(`/api/runs?output_dir=${encodeURIComponent(outputDirInput.value)}`);
  const data = await response.json();
  if (!data.ok) {
    setStatus(`Run listing failed:\n${data.error}`);
    return;
  }
  renderRuns(data.runs || []);
}

function renderRuns(runs) {
  const root = document.getElementById('runs');
  root.innerHTML = '';
  if (!runs.length) {
    root.textContent = 'No runs found.';
    return;
  }
  const table = document.createElement('table');
  table.className = 'table';
  table.innerHTML = '<thead><tr><th>Task ID</th><th>Stage</th><th>Updated</th><th>Best gap anchor</th><th>Smoke</th><th>Action</th></tr></thead>';
  const body = document.createElement('tbody');
  runs.forEach(run => {
    const row = document.createElement('tr');
    const button = document.createElement('button');
    button.textContent = 'Open';
    button.addEventListener('click', async () => {
      currentTask = currentTask || {task_id: run.task_id};
      const response = await fetch(`/api/program?task_id=${encodeURIComponent(run.task_id)}&output_dir=${encodeURIComponent(outputDirInput.value)}`);
      const program = await response.json();
      currentProgram = program;
      renderProgram(program, null);
      setStatus(`Loaded run ${run.task_id}`);
    });
    row.innerHTML = `
      <td>${run.task_id}</td>
      <td>${run.stage}</td>
      <td>${run.updated_at || ''}</td>
      <td>${run.best_gap_anchor || ''}</td>
      <td>${run.smoke_pass === undefined ? '' : run.smoke_pass}</td>
      <td></td>
    `;
    row.lastElementChild.appendChild(button);
    body.appendChild(row);
  });
  table.appendChild(body);
  root.appendChild(table);
}

function renderProgram(program, summary) {
  currentProgram = program;
  const metrics = summary?.summary_metrics || program.summary_metrics || {};
  renderSummary(program, metrics);
  renderSteps(program.planned_steps || []);
  renderClaims(program.claim_graph || []);
  renderHypotheses(program.hypotheses || []);
  renderGaps(program.gap_candidates || []);
  renderToolRuns(program.tool_runs || []);
  renderArtifacts(program.artifacts || []);
  renderSmoke(program.smoke_summary || {});
  if (!currentTask || currentTask.task_id !== program.task_id) {
    currentTask = currentTask || {task_id: program.task_id};
  }
}

function renderSummary(program, metrics) {
  const summaryRoot = document.getElementById('summary');
  summaryRoot.innerHTML = '';
  const list = document.createElement('ul');
  const baseItems = [
    ['Task ID', program.task_id],
    ['Stage', program.stage],
    ['Documents', program.corpus_manifest?.length ?? 0],
    ['Claims', program.claim_graph?.length ?? 0],
    ['Hypotheses', program.hypotheses?.length ?? 0],
    ['Ranked gaps', program.gap_candidates?.length ?? 0],
  ];
  for (const [label, value] of baseItems) {
    const li = document.createElement('li');
    li.textContent = `${label}: ${value}`;
    list.appendChild(li);
  }
  Object.entries(metrics).forEach(([key, value]) => {
    const li = document.createElement('li');
    li.textContent = `${key}: ${value}`;
    list.appendChild(li);
  });
  summaryRoot.appendChild(list);
}

function renderSteps(steps) {
  const root = document.getElementById('steps');
  root.innerHTML = '';
  steps.forEach(step => {
    const card = document.createElement('div');
    card.className = 'step';
    card.innerHTML = `
      <div class="status-badge ${step.status}">${step.status}</div>
      <div><strong>${step.title}</strong></div>
      <div>${step.objective}</div>
      <div><small>${(step.deliverables || []).join(', ')}</small></div>
    `;
    root.appendChild(card);
  });
}

function renderAnchors(anchors) {
  const root = document.getElementById('anchors');
  root.innerHTML = '';
  if (!anchors.length) {
    root.textContent = 'No L3 anchors configured.';
    return;
  }
  const table = document.createElement('table');
  table.className = 'table';
  table.innerHTML = '<thead><tr><th>Label</th><th>Band</th><th>Frequency (Hz)</th><th>Stopband</th><th>Target power (mW)</th><th>PEF</th></tr></thead>';
  const body = document.createElement('tbody');
  anchors.forEach(anchor => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${anchor.label}</td>
      <td>${anchor.band_index ?? ''}</td>
      <td>${anchor.frequency_hz}</td>
      <td>${anchor.stopband_hz ? anchor.stopband_hz.join(' – ') : ''}</td>
      <td>${anchor.target_power_mw ?? ''}</td>
      <td>${anchor.target_pef ?? ''}</td>
    `;
    body.appendChild(row);
  });
  table.appendChild(body);
  root.appendChild(table);
}

function renderClaims(claims) {
  const root = document.getElementById('claims');
  root.innerHTML = '';
  claims.forEach(claim => {
    const li = document.createElement('li');
    li.textContent = `[${claim.claim_type}] ${claim.claim_text}`;
    root.appendChild(li);
  });
}

function renderHypotheses(hypotheses) {
  const root = document.getElementById('hypotheses');
  root.innerHTML = '';
  hypotheses.forEach(h => {
    const li = document.createElement('li');
    li.textContent = `${h.label}: ${h.statement}`;
    root.appendChild(li);
  });
}

function renderGaps(gaps) {
  const root = document.getElementById('gaps');
  root.innerHTML = '';
  if (!gaps.length) {
    root.textContent = 'No ranked gaps.';
    return;
  }
  const table = document.createElement('table');
  table.className = 'table';
  table.innerHTML = '<thead><tr><th>Gap</th><th>Ω min</th><th>Ω max</th><th>TR</th><th>Raw Hz</th><th>Anchored Hz</th><th>Anchor</th><th>Score</th></tr></thead>';
  const body = document.createElement('tbody');
  gaps.forEach(g => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${g.band_index}</td>
      <td>${Number(g.omega_min).toFixed(4)}</td>
      <td>${Number(g.omega_max).toFixed(4)}</td>
      <td>${(g.tr_frequencies || []).join(', ')}</td>
      <td>${g.raw_frequency_hz === null || g.raw_frequency_hz === undefined ? '' : Number(g.raw_frequency_hz).toFixed(3)}</td>
      <td>${g.anchored_frequency_hz === null || g.anchored_frequency_hz === undefined ? '' : Number(g.anchored_frequency_hz).toFixed(3)}</td>
      <td>${g.matched_anchor_label || ''}</td>
      <td>${Number(g.overall_score || 0).toFixed(4)}</td>
    `;
    body.appendChild(row);
  });
  table.appendChild(body);
  root.appendChild(table);
}

function renderToolRuns(toolRuns) {
  const root = document.getElementById('tool-runs');
  root.innerHTML = '';
  if (!toolRuns.length) {
    root.textContent = 'No tool runs.';
    return;
  }
  const table = document.createElement('table');
  table.className = 'table';
  table.innerHTML = '<thead><tr><th>Tool</th><th>Purpose</th><th>Status</th><th>Artifacts</th><th>Notes</th></tr></thead>';
  const body = document.createElement('tbody');
  toolRuns.forEach(run => {
    const row = document.createElement('tr');
    const artifactLinks = (run.artifact_paths || []).map(path => `<a href="/artifact?path=${encodeURIComponent(path)}" target="_blank">artifact</a>`).join(' ');
    row.innerHTML = `
      <td>${run.tool}</td>
      <td>${run.purpose}</td>
      <td>${run.status}</td>
      <td>${artifactLinks}</td>
      <td>${run.notes || ''}</td>
    `;
    body.appendChild(row);
  });
  table.appendChild(body);
  root.appendChild(table);
}

function renderSmoke(smokeSummary) {
  const root = document.getElementById('smoke');
  root.innerHTML = '';
  if (!smokeSummary || !smokeSummary.checks) {
    root.textContent = 'No smoke summary loaded.';
    return;
  }
  const banner = document.createElement('div');
  banner.className = `banner ${smokeSummary.overall_pass ? 'pass' : 'fail'}`;
  banner.textContent = `overall_pass: ${smokeSummary.overall_pass}`;
  root.appendChild(banner);
  const list = document.createElement('ul');
  smokeSummary.checks.forEach(check => {
    const li = document.createElement('li');
    li.textContent = `${check.passed ? 'PASS' : 'FAIL'} — ${check.name}: ${check.details}`;
    list.appendChild(li);
  });
  root.appendChild(list);
}

function renderArtifacts(artifacts) {
  const root = document.getElementById('artifacts');
  root.innerHTML = '';
  artifacts.forEach(artifact => {
    const li = document.createElement('li');
    const link = document.createElement('a');
    link.href = `/artifact?path=${encodeURIComponent(artifact.path)}`;
    link.target = '_blank';
    link.textContent = `${artifact.label} (${artifact.generated_by})`;
    li.appendChild(link);
    root.appendChild(li);
  });
}

init();
