const taskCardInput = document.getElementById('task-card');
const outputDirInput = document.getElementById('output-dir');
const taskMeta = document.getElementById('task-meta');
const statusEl = document.getElementById('status');

const runButton = document.getElementById('run-btn');
const refreshButton = document.getElementById('refresh-btn');
const rebuildReportButton = document.getElementById('rebuild-report-btn');
const smokeButton = document.getElementById('smoke-btn');
const runsButton = document.getElementById('runs-btn');
const noteButton = document.getElementById('note-btn');
const discussionRefreshButton = document.getElementById('discussion-refresh-btn');

let currentTask = null;
let currentProgram = null;

runButton.addEventListener('click', runReplay);
refreshButton.addEventListener('click', loadLatest);
rebuildReportButton.addEventListener('click', rebuildReport);
smokeButton.addEventListener('click', runSmoke);
runsButton.addEventListener('click', loadRuns);
noteButton.addEventListener('click', addHumanNote);
discussionRefreshButton.addEventListener('click', refreshDiscussion);

function setStatus(message) {
  statusEl.textContent = message;
}

function artifactUrl(path) {
  return `/artifact?path=${encodeURIComponent(path)}`;
}

function postJson(url, payload) {
  return fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }).then(async resp => ({...(await resp.json()), _status: resp.status, _okHttp: resp.ok}));
}

function createLink(path, text) {
  const link = document.createElement('a');
  link.href = artifactUrl(path);
  link.target = '_blank';
  link.textContent = text;
  return link;
}

function findArtifact(program, basenameOrLabel) {
  if (!program?.artifacts?.length) return null;
  return program.artifacts.find(artifact => (
    artifact.label === basenameOrLabel
    || artifact.path.endsWith(`/${basenameOrLabel}`)
    || artifact.path.endsWith(`\\${basenameOrLabel}`)
  )) || null;
}

function appendArtifactLink(container, program, basenameOrLabel, text) {
  const artifact = findArtifact(program, basenameOrLabel);
  if (!artifact) return;
  if (container.childNodes.length) container.appendChild(document.createTextNode(' '));
  container.appendChild(createLink(artifact.path, text || artifact.label));
}

function safeNumber(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '';
  return Number(value).toFixed(digits);
}

async function init() {
  try {
    const response = await fetch('/api/defaults');
    const data = await response.json();
    if (!data.ok) {
      setStatus(`Failed to load defaults:\n${data.error}`);
      return;
    }
    currentTask = data.task;
    taskCardInput.value = data.default_task_card;
    outputDirInput.value = data.default_output_dir;
    renderTaskMeta(data.task);
    await loadRuns();
    setStatus('Defaults loaded.');
  } catch (error) {
    setStatus(`Initialization failed:\n${error}`);
  }
}

function renderTaskMeta(task) {
  taskMeta.innerHTML = '';
  const lines = [
    `Task ID: ${task.task_id}`,
    `Mode: ${task.discovery_mode}`,
    `Mechanism: ${task.mechanism_focus}`,
    `Allowed tools: ${(task.allowed_tools || []).join(', ')}`,
  ];
  if (task.research_question) {
    lines.push(`Question: ${task.research_question}`);
  }
  lines.forEach(text => {
    const div = document.createElement('div');
    div.textContent = text;
    taskMeta.appendChild(div);
  });
  renderAnchors(task.l3_anchors || []);
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
  currentTask = currentTask || data.program;
  currentProgram = data.program;
  renderProgram(data.program, data.summary);
  setStatus(`Replay completed. task_id=${data.program.task_id}, stage=${data.program.stage}`);
  await loadRuns();
}

async function loadLatest() {
  try {
    if (!currentTask) await init();
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
  if (!currentTask) await init();
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
  if (currentProgram) await loadLatest();
}

async function runSmoke() {
  if (!currentTask) await init();
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
  if (currentProgram) currentProgram.smoke_summary = data.smoke_summary;
  renderSmoke(data.smoke_summary);
  setStatus(`Smoke complete. overall_pass=${data.smoke_summary.overall_pass}`);
}

async function refreshDiscussion() {
  if (!currentTask) await init();
  const response = await fetch(`/api/discussion?task_id=${encodeURIComponent(currentTask.task_id)}&output_dir=${encodeURIComponent(outputDirInput.value)}&task_card=${encodeURIComponent(taskCardInput.value)}`);
  const data = await response.json();
  if (!data.ok) {
    setStatus(`Discussion refresh failed:\n${data.error}`);
    return;
  }
  if (currentProgram) {
    currentProgram.discussion_bundle = data.discussion_bundle;
    currentProgram.collaboration_log = data.collaboration_log || [];
  }
  renderDiscussion(data.discussion_bundle || {}, currentProgram);
  setStatus('Discussion refreshed.');
}

async function addHumanNote() {
  if (!currentTask) await init();
  const author = document.getElementById('note-author').value || 'human';
  const topic = document.getElementById('note-topic').value || 'note';
  const content = document.getElementById('note-content').value.trim();
  const refs = document.getElementById('note-refs').value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean);
  if (!content) {
    setStatus('Human note is empty.');
    return;
  }
  setStatus('Adding human note...');
  const data = await postJson('/api/discussion_note', {
    task_card: taskCardInput.value,
    output_dir: outputDirInput.value,
    task_id: currentTask?.task_id,
    author,
    topic,
    content,
    references: refs,
  });
  if (!data.ok) {
    setStatus(`Add note failed:\n${data.error}`);
    return;
  }
  document.getElementById('note-content').value = '';
  await loadLatest();
  setStatus(`Human note added. total=${data.result.n_human_messages}`);
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
  table.innerHTML = '<thead><tr><th>Task ID</th><th>Stage</th><th>Updated</th><th>Best gap anchor</th><th>Best calibrated Hz</th><th>Calibration source</th><th>Memory records</th><th>Figures</th><th>Smoke</th><th>Action</th></tr></thead>';
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
      <td>${run.best_gap_calibrated_hz ?? ''}</td>
      <td>${run.calibration_source || ''}</td>
      <td>${run.negative_memory_records ?? ''}</td>
      <td>${run.publication_main_figures ?? ''}</td>
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
  renderCalibration(program.calibration_summary || {}, program);
  renderAppendix(program.appendix_summary || {}, program);
  renderMechanisms(program.mechanism_portfolio || {}, program);
  renderLibrary(program.solver_library || {}, program);
  renderGaps(program.gap_candidates || []);
  renderMemory(program.negative_memory || {}, program);
  renderPublication(program.publication_bundle || {}, program);
  renderDiscussion(program.discussion_bundle || {}, program);
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
    ['Mechanism entries', program.solver_library?.entries?.length ?? 0],
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

function renderCalibration(calibrationSummary, program) {
  const root = document.getElementById('calibration');
  root.innerHTML = '';
  if (!calibrationSummary || !Object.keys(calibrationSummary).length) {
    root.textContent = 'No calibration summary loaded.';
    return;
  }
  const errors = calibrationSummary.errors || {};
  const residualModel = calibrationSummary.residual_model || {};
  const list = document.createElement('ul');
  const items = [
    ['Source', calibrationSummary.source],
    ['Confidence', safeNumber(calibrationSummary.confidence, 4)],
    ['Pre RMSE (Hz)', safeNumber(errors.pre_rmse_hz)],
    ['Post RMSE (Hz)', safeNumber(errors.post_rmse_hz)],
    ['Pre stopband MAE (Hz)', safeNumber(errors.pre_stopband_mae_hz)],
    ['Post stopband MAE (Hz)', safeNumber(errors.post_stopband_mae_hz)],
    ['Residual bias (Hz)', safeNumber(residualModel.residual_bias_hz)],
    ['Base σ (Hz)', safeNumber(residualModel.base_sigma_hz)],
    ['LOO RMSE (Hz)', safeNumber(residualModel.leave_one_out_rmse_hz)],
    ['Extrapolation slope', safeNumber(residualModel.penalty_slope_hz_per_span)],
    ['Candidate rows', calibrationSummary.candidate_uncertainty?.length ?? 0],
  ];
  items.forEach(([label, value]) => {
    const li = document.createElement('li');
    li.textContent = `${label}: ${value}`;
    list.appendChild(li);
  });
  root.appendChild(list);
  const links = document.createElement('div');
  links.className = 'link-row';
  appendArtifactLink(links, program, 'Calibration summary', 'calibration_summary.json');
  appendArtifactLink(links, program, 'Calibrated L2 summary', 'calibrated_l2_summary.json');
  appendArtifactLink(links, program, 'Uncertainty model', 'uncertainty_model.json');
  appendArtifactLink(links, program, 'Candidate uncertainty', 'candidate_uncertainty.csv');
  appendArtifactLink(links, program, 'Frequency calibration', 'frequency_calibration.png');
  appendArtifactLink(links, program, 'Stopband calibration', 'stopband_calibration.png');
  appendArtifactLink(links, program, 'Uncertainty calibration', 'uncertainty_calibration.png');
  root.appendChild(links);
}

function renderAppendix(appendixSummary, program) {
  const root = document.getElementById('appendix');
  root.innerHTML = '';
  if (!appendixSummary || !Object.keys(appendixSummary).length) {
    root.textContent = 'No appendix summary loaded.';
    return;
  }
  const list = document.createElement('ul');
  const entries = [
    ['Cards', appendixSummary.n_cards ?? 0],
    ['Symbols', appendixSummary.n_symbols ?? 0],
    ['All checks pass', appendixSummary.all_checks_pass],
    ['Trace groups', appendixSummary.n_trace_groups ?? 0],
    ['Limit cases', appendixSummary.n_limit_cases ?? 0],
    ['Solver cross-checks', appendixSummary.n_solver_cross_checks ?? 0],
  ];
  entries.forEach(([label, value]) => {
    const li = document.createElement('li');
    li.textContent = `${label}: ${value}`;
    list.appendChild(li);
  });
  root.appendChild(list);
  const links = document.createElement('div');
  links.className = 'link-row';
  appendArtifactLink(links, program, 'Appendix package', 'appendix_package.md');
  appendArtifactLink(links, program, 'Appendix bundle', 'appendix_bundle.tex');
  appendArtifactLink(links, program, 'Derivation traces', 'derivation_traces.json');
  appendArtifactLink(links, program, 'Symbol table', 'symbol_table.json');
  root.appendChild(links);
}

function renderMechanisms(portfolio, program) {
  const root = document.getElementById('mechanisms');
  root.innerHTML = '';
  if (!portfolio || !portfolio.entries?.length) {
    root.textContent = 'No mechanism portfolio loaded.';
    return;
  }
  const rec = portfolio.recommended_path || {};
  const intro = document.createElement('p');
  intro.innerHTML = `<strong>Primary:</strong> ${rec.primary || ''} &nbsp; <strong>Secondary:</strong> ${(rec.secondary || []).join(', ') || '—'}`;
  root.appendChild(intro);
  if (rec.rationale?.length) {
    const rationale = document.createElement('ul');
    rec.rationale.forEach(line => {
      const li = document.createElement('li');
      li.textContent = line;
      rationale.appendChild(li);
    });
    root.appendChild(rationale);
  }
  const table = document.createElement('table');
  table.className = 'table';
  table.innerHTML = '<thead><tr><th>Mechanism</th><th>Maturity</th><th>Fit</th><th>Target-band</th><th>Calibration confidence</th><th>Review pass</th><th>Risks</th></tr></thead>';
  const body = document.createElement('tbody');
  portfolio.entries.forEach(entry => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${entry.display_name} (${entry.mechanism_key})</td>
      <td>${entry.maturity}</td>
      <td>${entry.fit_score}</td>
      <td>${entry.target_band_score}</td>
      <td>${entry.calibration_confidence}</td>
      <td>${entry.review_pass}</td>
      <td>${(entry.risks || []).join('; ')}</td>
    `;
    body.appendChild(row);
  });
  table.appendChild(body);
  root.appendChild(table);
  const links = document.createElement('div');
  links.className = 'link-row';
  appendArtifactLink(links, program, 'Mechanism portfolio', 'mechanism_portfolio.json');
  appendArtifactLink(links, program, 'Mechanism roadmap', 'mechanism_combo_roadmap.md');
  root.appendChild(links);
}

function renderLibrary(library, program) {
  const root = document.getElementById('library');
  root.innerHTML = '';
  if (!library || !library.comparison?.length) {
    root.textContent = 'No solver library loaded.';
    return;
  }
  const summary = document.createElement('p');
  summary.innerHTML = `<strong>Entries:</strong> ${library.entries?.length || 0} &nbsp; <strong>Calibration source:</strong> ${library.calibration_source || ''}`;
  root.appendChild(summary);
  const table = document.createElement('table');
  table.className = 'table';
  table.innerHTML = '<thead><tr><th>Mechanism</th><th>Maturity</th><th>Status</th><th>Best Hz</th><th>Localization</th><th>Harvestability</th><th>Suppression</th><th>Target-band</th><th>Review pass</th></tr></thead>';
  const body = document.createElement('tbody');
  library.comparison.forEach(row => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${row.mechanism_key}</td>
      <td>${row.maturity}</td>
      <td>${row.solver_status}</td>
      <td>${safeNumber(row.best_frequency_hz)}</td>
      <td>${safeNumber(row.localization_score, 4)}</td>
      <td>${safeNumber(row.harvestability_proxy, 4)}</td>
      <td>${safeNumber(row.suppression_proxy, 4)}</td>
      <td>${safeNumber(row.target_band_score, 4)}</td>
      <td>${row.review_pass}</td>
    `;
    body.appendChild(tr);
  });
  table.appendChild(body);
  root.appendChild(table);
  const links = document.createElement('div');
  links.className = 'link-row';
  appendArtifactLink(links, program, 'Mechanism solver library', 'mechanism_solver_library.json');
  appendArtifactLink(links, program, 'Mechanism solver comparison', 'mechanism_solver_comparison.csv');
  appendArtifactLink(links, program, 'Mechanism codegen bundle', 'mechanism_codegen_bundle.tar.gz');
  root.appendChild(links);
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
  table.innerHTML = '<thead><tr><th>Gap</th><th>Ω min</th><th>Ω max</th><th>TR</th><th>Raw Hz</th><th>Calibrated Hz</th><th>σ (Hz)</th><th>CI</th><th>Extrapolation</th><th>Uncertainty score</th><th>Anchor</th><th>Score</th></tr></thead>';
  const body = document.createElement('tbody');
  gaps.forEach(g => {
    const ci = g.confidence_interval_hz ? `${safeNumber(g.confidence_interval_hz[0])} – ${safeNumber(g.confidence_interval_hz[1])}` : '';
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${g.band_index}</td>
      <td>${safeNumber(g.omega_min, 4)}</td>
      <td>${safeNumber(g.omega_max, 4)}</td>
      <td>${(g.tr_frequencies || []).join(', ')}</td>
      <td>${safeNumber(g.raw_frequency_hz)}</td>
      <td>${safeNumber(g.calibrated_frequency_hz)}</td>
      <td>${safeNumber(g.uncertainty_sigma_hz)}</td>
      <td>${ci}</td>
      <td>${safeNumber(g.extrapolation_penalty, 4)}</td>
      <td>${safeNumber(g.uncertainty_score, 4)}</td>
      <td>${g.matched_anchor_label || ''}</td>
      <td>${safeNumber(g.overall_score, 4)}</td>
    `;
    body.appendChild(row);
  });
  table.appendChild(body);
  root.appendChild(table);
}

function renderMemory(memory, program) {
  const root = document.getElementById('memory');
  root.innerHTML = '';
  if (!memory || !memory.summary) {
    root.textContent = 'No negative-result memory loaded.';
    return;
  }
  const list = document.createElement('ul');
  Object.entries(memory.summary).forEach(([key, value]) => {
    const li = document.createElement('li');
    li.textContent = `${key}: ${value}`;
    list.appendChild(li);
  });
  root.appendChild(list);
  const table = document.createElement('table');
  table.className = 'table';
  table.innerHTML = '<thead><tr><th>Category</th><th>Label</th><th>Severity</th><th>Lesson</th><th>Action</th></tr></thead>';
  const body = document.createElement('tbody');
  (memory.records || []).forEach(record => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${record.category}</td>
      <td>${record.label}</td>
      <td>${record.severity}</td>
      <td>${record.lesson}</td>
      <td>${record.recommended_action}</td>
    `;
    body.appendChild(row);
  });
  table.appendChild(body);
  root.appendChild(table);
  const links = document.createElement('div');
  links.className = 'link-row';
  appendArtifactLink(links, program, 'Negative-result memory', 'negative_result_memory.json');
  appendArtifactLink(links, program, 'Negative-result memory (csv)', 'negative_result_memory.csv');
  appendArtifactLink(links, program, 'Negative-result memory (markdown)', 'negative_result_memory.md');
  root.appendChild(links);
}

function renderPublication(bundle, program) {
  const root = document.getElementById('publication');
  root.innerHTML = '';
  if (!bundle || !Object.keys(bundle).length) {
    root.textContent = 'No publication bundle loaded.';
    return;
  }
  const list = document.createElement('ul');
  list.innerHTML = `
    <li>Main figures: ${bundle.main_figures?.length ?? 0}</li>
    <li>Ablation gap rows: ${bundle.ablation_tables?.counts?.gap_rows ?? 0}</li>
    <li>Ablation calibration rows: ${bundle.ablation_tables?.counts?.calibration_rows ?? 0}</li>
    <li>Ablation mechanism rows: ${bundle.ablation_tables?.counts?.mechanism_rows ?? 0}</li>
    <li>Reviewer claim rows: ${bundle.reviewer_manifest?.n_claim_rows ?? 0}</li>
  `;
  root.appendChild(list);
  if (bundle.main_figures?.length) {
    const figs = document.createElement('table');
    figs.className = 'table';
    figs.innerHTML = '<thead><tr><th>Figure</th><th>Caption</th><th>Section</th><th>File</th></tr></thead>';
    const body = document.createElement('tbody');
    bundle.main_figures.forEach(fig => {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${fig.figure_id}</td>
        <td>${fig.caption}</td>
        <td>${fig.section}</td>
        <td><a href="${artifactUrl(fig.path)}" target="_blank">open</a></td>
      `;
      body.appendChild(row);
    });
    figs.appendChild(body);
    root.appendChild(figs);
  }
  const links = document.createElement('div');
  links.className = 'link-row';
  appendArtifactLink(links, program, 'Publication bundle', 'publication_bundle.json');
  appendArtifactLink(links, program, 'Main figures index', 'main_figures.json');
  appendArtifactLink(links, program, 'Ablation tables', 'ablation_tables.md');
  appendArtifactLink(links, program, 'Reproducibility package', 'reproducibility_package.tar.gz');
  appendArtifactLink(links, program, 'Reviewer artifact manifest', 'reviewer_artifact_manifest.json');
  root.appendChild(links);
}

function renderDiscussion(bundle, program) {
  const root = document.getElementById('discussion');
  root.innerHTML = '';
  if (!bundle || !Object.keys(bundle).length) {
    root.textContent = 'No discussion bundle loaded.';
    return;
  }
  const meta = document.createElement('p');
  meta.innerHTML = `<strong>Primary mechanism:</strong> ${bundle.primary_mechanism || ''} &nbsp; <strong>Best gap:</strong> ${bundle.best_gap || ''}`;
  root.appendChild(meta);

  const generated = document.createElement('div');
  generated.innerHTML = '<h3>Generated roles</h3>';
  const genList = document.createElement('ul');
  (bundle.generated_messages || []).forEach(msg => {
    const li = document.createElement('li');
    li.textContent = `${msg.role} (${msg.topic}): ${msg.content}`;
    genList.appendChild(li);
  });
  generated.appendChild(genList);
  root.appendChild(generated);

  const prompts = document.createElement('div');
  prompts.innerHTML = '<h3>Prompt pack</h3>';
  const promptList = document.createElement('ul');
  (bundle.prompt_pack || []).forEach(prompt => {
    const li = document.createElement('li');
    li.textContent = `${prompt.role}: ${prompt.prompt}`;
    promptList.appendChild(li);
  });
  prompts.appendChild(promptList);
  root.appendChild(prompts);

  const humanBlock = document.createElement('div');
  humanBlock.innerHTML = '<h3>Human notes</h3>';
  const humanList = document.createElement('ul');
  (bundle.human_messages || []).forEach(msg => {
    const refs = (msg.references || []).length ? ` [refs: ${(msg.references || []).join(', ')}]` : '';
    const li = document.createElement('li');
    li.textContent = `${msg.author || 'human'} (${msg.topic}): ${msg.content}${refs}`;
    humanList.appendChild(li);
  });
  if (!(bundle.human_messages || []).length) {
    const li = document.createElement('li');
    li.textContent = 'No human notes yet.';
    humanList.appendChild(li);
  }
  humanBlock.appendChild(humanList);
  root.appendChild(humanBlock);

  const links = document.createElement('div');
  links.className = 'link-row';
  appendArtifactLink(links, program, 'Discussion bundle', 'discussion_bundle.json');
  appendArtifactLink(links, program, 'Multi-LLM prompt pack', 'multi_llm_prompt_pack.json');
  root.appendChild(links);
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
    const artifactLinks = (run.artifact_paths || []).map(path => `<a href="${artifactUrl(path)}" target="_blank">artifact</a>`).join(' ');
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
    link.href = artifactUrl(artifact.path);
    link.target = '_blank';
    link.textContent = `${artifact.label} (${artifact.generated_by})`;
    li.appendChild(link);
    root.appendChild(li);
  });
}

init();
