const statusBox = document.getElementById('status');
const taskCardInput = document.getElementById('task-card');
const outputDirInput = document.getElementById('output-dir');

document.getElementById('run-btn').addEventListener('click', runReplay);
document.getElementById('refresh-btn').addEventListener('click', loadLatest);

async function runReplay() {
  setStatus('Running replay...');
  const payload = {
    task_card: taskCardInput.value,
    output_dir: outputDirInput.value,
  };
  const response = await fetch('/api/run_replay', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!data.ok) {
    setStatus(`Replay failed:\n${data.error}`);
    return;
  }
  renderProgram(data.program, data.summary);
  setStatus(`Replay complete. Output: ${data.program.output_dir}`);
}

async function loadLatest() {
  const taskId = 'tr-discover-replay-001';
  const url = `/api/program?task_id=${encodeURIComponent(taskId)}&output_dir=${encodeURIComponent(outputDirInput.value)}`;
  const response = await fetch(url);
  if (!response.ok) {
    setStatus(`No saved program found for ${taskId}.`);
    return;
  }
  const program = await response.json();
  renderProgram(program, null);
  setStatus(`Loaded latest program from ${program.output_dir}`);
}

function setStatus(message) {
  statusBox.textContent = message;
}

function renderProgram(program, summary) {
  const summaryRoot = document.getElementById('summary');
  const metrics = summary?.summary_metrics || program.summary_metrics || {};
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

  const stepsRoot = document.getElementById('steps');
  stepsRoot.innerHTML = '';
  (program.planned_steps || []).forEach(step => {
    const card = document.createElement('div');
    card.className = 'step';
    card.innerHTML = `
      <div class="status-badge">${step.status}</div>
      <div><strong>${step.title}</strong></div>
      <div>${step.objective}</div>
      <div><small>${(step.deliverables || []).join(', ')}</small></div>
    `;
    stepsRoot.appendChild(card);
  });

  const claimsRoot = document.getElementById('claims');
  claimsRoot.innerHTML = '';
  (program.claim_graph || []).forEach(claim => {
    const li = document.createElement('li');
    li.textContent = `[${claim.claim_type}] ${claim.claim_text}`;
    claimsRoot.appendChild(li);
  });

  const hypothesesRoot = document.getElementById('hypotheses');
  hypothesesRoot.innerHTML = '';
  (program.hypotheses || []).forEach(h => {
    const li = document.createElement('li');
    li.textContent = `${h.label}: ${h.statement}`;
    hypothesesRoot.appendChild(li);
  });

  const gapsRoot = document.getElementById('gaps');
  gapsRoot.innerHTML = '';
  const gaps = program.gap_candidates || [];
  if (!gaps.length) {
    gapsRoot.textContent = 'No ranked gaps.';
  } else {
    const table = document.createElement('table');
    table.className = 'table';
    table.innerHTML = '<thead><tr><th>Gap</th><th>Ω min</th><th>Ω max</th><th>TR</th><th>Score</th></tr></thead>';
    const body = document.createElement('tbody');
    gaps.forEach(g => {
      const row = document.createElement('tr');
      row.innerHTML = `<td>${g.band_index}</td><td>${Number(g.omega_min).toFixed(4)}</td><td>${Number(g.omega_max).toFixed(4)}</td><td>${(g.tr_frequencies || []).join(', ')}</td><td>${Number(g.overall_score || 0).toFixed(4)}</td>`;
      body.appendChild(row);
    });
    table.appendChild(body);
    gapsRoot.appendChild(table);
  }

  const artifactsRoot = document.getElementById('artifacts');
  artifactsRoot.innerHTML = '';
  (program.artifacts || []).forEach(artifact => {
    const li = document.createElement('li');
    const link = document.createElement('a');
    link.href = `/artifact?path=${encodeURIComponent(artifact.path)}`;
    link.target = '_blank';
    link.textContent = `${artifact.label} (${artifact.generated_by})`;
    li.appendChild(link);
    artifactsRoot.appendChild(li);
  });
}

fetch('/api/health').then(() => setStatus('Dashboard ready.')).catch(() => setStatus('Dashboard server not reachable.'));
