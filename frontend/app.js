// Application Logic for VEH Scientist Cockpit

let currentRoundIndex = 0;
let currentMode = "role";
let currentConfigMode = "role";
let dashboardState = {
    rounds: typeof mockRounds !== "undefined" ? mockRounds : [],
    multiLlmRounds: typeof mockRoundsMultiLLM !== "undefined" ? mockRoundsMultiLLM : [],
    taskTitle: "TR-Based Simultaneous Harvesting and Suppression",
    isRunning: true,
    motifs: [
        "TR + Tuning Layer",
        "Defect Funnel",
        "Bi-material Substrate",
        "Free-Clamped BC",
    ],
};
const CONFIG_SLOT_OPTIONS = {
    role: [
        { value: "mechanism", label: "Mechanism Agent" },
        { value: "structure", label: "Structure Agent" },
        { value: "critic", label: "Critic Agent" },
        { value: "paper", label: "Paper Agent" },
        { value: "verifier", label: "Verifier Planner" },
    ],
    llm: [
        { value: "gpt_scientist", label: "GPT-Scientist" },
        { value: "claude_scientist", label: "Claude-Scientist" },
        { value: "qwen_scientist", label: "Qwen-Scientist" },
        { value: "gemini_scientist", label: "Gemini-Scientist" },
        { value: "grok_scientist", label: "Grok-Scientist" },
        { value: "deepseek_scientist", label: "Deepseek-Scientist" },
    ],
};
const configState = {
    slotsByMode: { role: [], llm: [] },
};

document.addEventListener("DOMContentLoaded", async () => {
    await hydrateDashboard();
    renderMemoryPanel();
    renderRound(currentRoundIndex);
    
    // UI Event Listeners
    document.getElementById("prev-round").addEventListener("click", () => {
        if (currentRoundIndex > 0) {
            currentRoundIndex--;
            renderRound(currentRoundIndex);
        }
    });

    document.getElementById("next-round").addEventListener("click", () => {
        if (currentRoundIndex < getRoundsData().length - 1) {
            currentRoundIndex++;
            renderRound(currentRoundIndex);
        }
    });

    // Textarea Auto-resize
    const taskInput = document.getElementById("user-task-input");
    taskInput.addEventListener("input", function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    // Theme Toggle Logic
    const themeBtn = document.getElementById("theme-toggle");
    themeBtn.addEventListener("click", () => {
        if (document.body.getAttribute("data-theme") === "light") {
            document.body.removeAttribute("data-theme");
            themeBtn.innerHTML = '<i class="ph ph-sun"></i> Theme';
        } else {
            document.body.setAttribute("data-theme", "light");
            themeBtn.innerHTML = '<i class="ph ph-moon"></i> Theme';
        }
    });

    document.querySelector('.mode-toggle').addEventListener("click", (e) => {
        if (e.target.classList.contains('mode-btn')) {
            document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
            e.target.classList.add('active');
            currentMode = e.target.dataset.mode;
            renderRound(currentRoundIndex);
        }
    });

    // Configuration Modal Logic
    const configBtn = document.getElementById("config-btn");
    const configModal = document.getElementById("config-modal");
    const closeConfigBtn = document.getElementById("close-config-modal");
    const agentSelect = document.getElementById("config-agent-select");
    
    configBtn.addEventListener("click", async () => {
        try {
            await openConfigModal();
        } catch(e) {
            console.warn("Config API not available, using empty defaults", e);
        }
        configModal.classList.remove("hidden");
    });
    
    closeConfigBtn.addEventListener("click", () => {
        configModal.classList.add("hidden");
        document.getElementById("config-alert").classList.add("hidden");
    });

    // Close on clicking outside modal
    configModal.addEventListener("click", (e) => {
        if (e.target === configModal) {
            configModal.classList.add("hidden");
            document.getElementById("config-alert").classList.add("hidden");
        }
    });

    document.querySelector('.modal-tabs').addEventListener("click", (e) => {
        if (e.target.classList.contains('config-tab')) {
            document.querySelectorAll('.modal-tabs .config-tab').forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');
            currentConfigMode = e.target.dataset.configMode;
            renderConfigOptions(currentConfigMode);
            void loadConfigSlot(currentConfigMode, agentSelect.value);
        }
    });
    agentSelect.addEventListener("change", () => {
        void loadConfigSlot(currentConfigMode, agentSelect.value);
    });

    // Config Buttons Logic
    const testBtn = document.getElementById("test-config-btn");
    const saveBtn = document.getElementById("save-config-btn");
    const configAlert = document.getElementById("config-alert");

    testBtn.addEventListener("click", () => {
        void validateCurrentConfig();
    });

    saveBtn.addEventListener("click", () => {
        void saveCurrentConfig();
    });

    // Verification Tabs Logic
    document.querySelector('.verification-tabs').addEventListener("click", (e) => {
        if (e.target.classList.contains('tab-btn')) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            e.target.classList.add('active');
            const tabId = e.target.dataset.tab;
            const roundsData = getRoundsData();
            renderVerificationTab(tabId, roundsData[currentRoundIndex].verification);
        }
    });

    document.getElementById("send-user-input").addEventListener("click", submitUserInput);
    document.getElementById("run-toggle").addEventListener("click", toggleDiscussionState);
    document.getElementById("user-task-input").addEventListener("keydown", (event) => {
        if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
            event.preventDefault();
            submitUserInput();
        }
    });
    
    // Memory Reference Highlight
    document.addEventListener("click", (e) => {
        if (e.target.classList.contains("ref-pill") && e.target.classList.contains("memory")) {
            const memoryCards = document.querySelectorAll(".knowledge-card");
            memoryCards.forEach(c => {
                c.classList.remove("highlight");
                const idMatch = e.target.textContent.match(/M[-\w]+/);
                if (idMatch && idMatch[0] === c.dataset.id) {
                    c.classList.add("highlight");
                    // Scroll to view
                    c.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    setTimeout(() => c.classList.remove("highlight"), 2000);
                }
            });
        }
    });
});

async function hydrateDashboard() {
    try {
        const response = await fetch("./api/session?task=configs/tasks/tr_baseline.yaml&rounds=3");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        applyPayload(payload);
        currentRoundIndex = Math.min(currentRoundIndex, Math.max(getRoundsData().length - 1, 0));
    } catch (error) {
        console.warn("Falling back to bundled mock data:", error);
        dashboardState.multiLlmRounds = dashboardState.multiLlmRounds.length
            ? dashboardState.multiLlmRounds
            : dashboardState.rounds;
    }
}

function applyPayload(payload) {
    if (Array.isArray(payload.rounds) && payload.rounds.length > 0) {
        dashboardState.rounds = payload.rounds;
    }
    if (Array.isArray(payload.multiLlmRounds) && payload.multiLlmRounds.length > 0) {
        dashboardState.multiLlmRounds = payload.multiLlmRounds;
    } else {
        dashboardState.multiLlmRounds = dashboardState.rounds;
    }
    if (Array.isArray(payload.motifs) && payload.motifs.length > 0) {
        dashboardState.motifs = payload.motifs;
    }
    if (typeof payload.taskTitle === "string" && payload.taskTitle.trim()) {
        dashboardState.taskTitle = payload.taskTitle.trim();
    }
    if (typeof payload.isRunning === "boolean") {
        dashboardState.isRunning = payload.isRunning;
    }
    syncSessionChrome();
}

function getRoundsData() {
    const candidateData = currentMode === "llm"
        ? dashboardState.multiLlmRounds
        : dashboardState.rounds;
    return candidateData && candidateData.length ? candidateData : dashboardState.rounds;
}

function syncSessionChrome() {
    const titleNode = document.querySelector(".task-title");
    if (titleNode) {
        titleNode.textContent = `Task: ${dashboardState.taskTitle}`;
    }

    const stateBadge = document.getElementById("session-run-state");
    const toggleBtn = document.getElementById("run-toggle");
    if (stateBadge) {
        stateBadge.textContent = dashboardState.isRunning ? "Running" : "Paused";
        stateBadge.classList.toggle("running", dashboardState.isRunning);
        stateBadge.classList.toggle("paused", !dashboardState.isRunning);
    }
    if (toggleBtn) {
        toggleBtn.innerHTML = dashboardState.isRunning
            ? '<i class="ph ph-pause"></i> Pause Discussion'
            : '<i class="ph ph-play"></i> Resume Discussion';
        toggleBtn.classList.toggle("primary", dashboardState.isRunning);
    }
}

async function postSessionUpdate(path, payload) {
    const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload.error || `HTTP ${response.status}`);
    }
    const data = await response.json();
    applyPayload(data);
    renderMemoryPanel();
    renderRound(Math.min(currentRoundIndex, Math.max(getRoundsData().length - 1, 0)));
}

async function submitUserInput() {
    const input = document.getElementById("user-task-input");
    const setTask = document.getElementById("set-task-checkbox");
    const content = input.value.trim();
    if (!content) {
        return;
    }

    try {
        const roundData = getRoundsData()[currentRoundIndex];
        await postSessionUpdate("./api/session/message", {
            content,
            setAsTask: setTask.checked,
            roundId: roundData ? roundData.round : null,
        });
        input.value = "";
    } catch (error) {
        console.error("Failed to submit user input:", error);
    }
}

async function toggleDiscussionState() {
    try {
        const roundData = getRoundsData()[currentRoundIndex];
        await postSessionUpdate("./api/session/control", {
            action: dashboardState.isRunning ? "pause" : "start",
            roundId: roundData ? roundData.round : null,
        });
    } catch (error) {
        console.error("Failed to update session state:", error);
    }
}

function renderRound(index) {
    const roundsData = getRoundsData();
    if (!roundsData || roundsData.length === 0) {
        return;
    }
    const roundData = roundsData[index];
    
    // Update Controls
    document.getElementById("prev-round").disabled = (index === 0);
    document.getElementById("next-round").disabled = (
        index === roundsData.length - 1 || !dashboardState.isRunning
    );
    
    // Update Top Bar
    document.getElementById("current-round-number").textContent = roundData.round;
    document.getElementById("current-status").textContent = dashboardState.isRunning
        ? roundData.status
        : `Paused · ${roundData.status}`;
    document.getElementById("discussion-budget").textContent = roundData.budgetStr;
    document.getElementById("best-candidate-name").textContent = roundData.bestCandidate;
    
    // Update Status Dot (green for completed, yellow for discussing)
    const dot = document.querySelector('.status-dot');
    if (!dashboardState.isRunning) {
        dot.style.background = "var(--status-gray)";
        dot.style.animation = "none";
    } else if(roundData.status === "Completed") {
        dot.style.background = "var(--status-green)";
        dot.style.animation = "pulse 2s infinite";
    } else {
        dot.style.background = "var(--status-yellow)";
        dot.style.animation = "pulse 2s infinite";
    }

    // Update Flow Arrow
    const steps = document.querySelectorAll('.flow-arrow .step');
    steps.forEach(s => s.classList.remove('active'));
    if (roundData.status === "Discussing") steps[0].classList.add('active');
    else if (roundData.status === "Verifying") steps[1].classList.add('active');
    else steps[2].classList.add('active'); // Completed means memorized

    // Render Discussion
    const discussionContent = document.getElementById("discussion-content");
    discussionContent.innerHTML = "";
    roundData.messages.forEach(msg => {
        const configToUse = currentMode === "llm" ? llmConfig : agentConfig;
        const agInfo = configToUse[msg.agent]
            || agentConfig[msg.agent]
            || { color: "#9ca3af", icon: "ph-robot", role: "Agent" };
        
        const refsHtml = renderRefs(msg.refs);

        const html = `
            <div class="message-card ${msg.threaded ? 'threaded' : ''} ${msg.agent === 'User' ? 'user-message' : ''}">
                <div class="agent-avatar" style="background-color: ${agInfo.color}33; color: ${agInfo.color}">
                    <i class="ph ${agInfo.icon}"></i>
                </div>
                <div class="message-content" style="border-left: 3px solid ${agInfo.color}">
                    <div class="message-header">
                        <span class="agent-name" style="color: ${agInfo.color}">${escapeHtml(msg.agent)}</span>
                        ${msg.type === 'system' ? '' : `<span class="agent-role">${escapeHtml(agInfo.role)}</span>`}
                    </div>
                    <div class="message-body">${richText(msg.content)}</div>
                    ${refsHtml}
                </div>
            </div>
        `;
        discussionContent.insertAdjacentHTML("beforeend", html);
    });

    // Render Proposal Summary
    const proposalAnchor = document.getElementById("proposal-anchor");
    if (roundData.proposal) {
        const p = roundData.proposal;
        let rows = p.params.map(param => `<tr><th>${escapeHtml(param.name)}</th><td>${escapeHtml(param.val)}</td></tr>`).join("");
        proposalAnchor.innerHTML = `
            <div class="proposal-card">
                <div class="proposal-header" style="cursor: pointer; border-bottom: none; margin-bottom: 0; padding-bottom: 0;" onclick="this.nextElementSibling.classList.toggle('open'); this.querySelector('.toggle-icon').classList.toggle('ph-caret-down'); this.querySelector('.toggle-icon').classList.toggle('ph-caret-up');">
                    <h3><i class="ph ph-file-code"></i> Proposal Summary: ${escapeHtml(p.title)}</h3>
                    <i class="ph ph-caret-down toggle-icon" style="color: var(--text-secondary)"></i>
                </div>
                <div class="proposal-details">
                    <div style="height: 8px; border-bottom: 1px solid var(--border); margin-bottom: 12px;"></div>
                    <table class="param-table">
                        ${rows}
                    </table>
                    <div class="proposal-traits">
                        <div class="trait-box pros">
                            <h4>Expected Advantages</h4>
                            <ul style="padding-left:16px;">${p.pros.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
                        </div>
                        <div class="trait-box cons">
                            <h4>Risks / Fail Points</h4>
                            <ul style="padding-left:16px;">${p.cons.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
                        </div>
                    </div>
                </div>
            </div>
        `;
    } else {
        proposalAnchor.innerHTML = "";
    }

    // Scroll to top of discussion on round change
    const pContent = document.getElementById("discussion-content").parentElement;
    pContent.scrollTop = 0;

    // Reset Verification Tabs and Render Active ones
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    
    // Choose sensible default tab based on what data is available
    let idealTab = "python";
    if (roundData.verification && roundData.verification.matlab && roundData.verification.matlab.status !== "missing") {
        idealTab = "matlab";
    }
    
    const targetTab = document.querySelector(`.tab-btn[data-tab="${idealTab}"]`);
    if(targetTab) targetTab.classList.add('active');
    
    renderVerificationTab(idealTab, roundData.verification);
    syncSessionChrome();

    // Render Timeline Highlights
    document.querySelectorAll('.timeline-node').forEach(node => {
        if (parseInt(node.dataset.round) === roundData.round) {
            node.classList.add('active');
        } else {
            node.classList.remove('active');
        }
    });
}

function renderVerificationTab(tabId, verifData) {
    const container = document.getElementById("verification-content");
    if (!verifData || !verifData[tabId] || verifData[tabId].status === "missing") {
        container.innerHTML = `<div style="color: var(--text-secondary); text-align: center; padding: 40px; background:rgba(0,0,0,0.2); border-radius:8px;">No verification results generated yet for this tier.</div>`;
        return;
    }

    const data = verifData[tabId];
    
    let metricsHtml = data.metrics.map(m => `
        <div class="v-metric">
            <span class="label">${escapeHtml(m.label)}</span>
            <span class="value ${escapeHtml(m.cls)}">${escapeHtml(m.val)}</span>
        </div>
    `).join("");

    container.innerHTML = `
        <div class="verif-result-card ${data.status}">
            <div class="verif-summary" onclick="this.nextElementSibling.classList.toggle('open')">
                <div style="flex-grow:1; font-weight:600; display:flex; align-items:center; gap:8px;">
                    <i class="ph ${data.status === 'pass' ? 'ph-check-circle' : data.status === 'fail' ? 'ph-x-circle' : 'ph-warning-circle'}"></i> Result Summary
                </div>
                ${metricsHtml}
                <i class="ph ph-caret-down" style="color: var(--text-secondary)"></i>
            </div>
            <div class="verif-details open">
                <p>${richText(data.details)}</p>
                <div class="verif-log">${richText(data.log)}</div>
            </div>
        </div>
    `;
}

async function openConfigModal() {
    currentConfigMode = getActiveConfigMode();
    await refreshConfigMode(currentConfigMode);
}

async function refreshConfigMode(mode) {
    renderConfigOptions(mode);
    await loadConfigSlot(mode, document.getElementById("config-agent-select").value);
}

function getActiveConfigMode() {
    const active = document.querySelector(".modal-tabs .config-tab.active");
    return active ? active.dataset.configMode : "role";
}

function renderConfigOptions(mode) {
    const agentSelect = document.getElementById("config-agent-select");
    const options = CONFIG_SLOT_OPTIONS[mode] || [];
    const previous = agentSelect.value;
    agentSelect.innerHTML = options
        .map(option => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`)
        .join("");
    if (options.some(option => option.value === previous)) {
        agentSelect.value = previous;
    }
}

async function loadConfigSlot(mode, slotId) {
    try {
        const response = await fetch(`./api/config?mode=${encodeURIComponent(mode)}&slotId=${encodeURIComponent(slotId)}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        configState.slotsByMode[mode] = payload.slots || [];
        fillConfigForm(payload.slot);
    } catch(err) {
        fillConfigForm({ config: { provider: "openai" } });
    }
}

function fillConfigForm(slotPayload) {
    const config = (slotPayload && slotPayload.config) || {};
    document.getElementById("config-api-format").value = config.provider || "openai";
    document.getElementById("config-base-url").value = config.baseUrl || "";
    document.getElementById("config-api-key").value = "";
    document.getElementById("config-model-name").value = config.modelName || "";
    const applyCheckbox = document.getElementById("config-apply-to-mode");
    applyCheckbox.checked = true;

    const alert = document.getElementById("config-alert");
    if (config.hasCredentials && config.apiKeyMasked) {
        alert.className = "config-alert success";
        alert.textContent = `Saved config detected. API Key: ${config.apiKeyMasked}`;
    } else {
        alert.classList.add("hidden");
        alert.textContent = "";
    }
}

function currentConfigPayload() {
    return {
        slotId: document.getElementById("config-agent-select").value,
        provider: document.getElementById("config-api-format").value,
        baseUrl: document.getElementById("config-base-url").value.trim(),
        apiKey: document.getElementById("config-api-key").value.trim(),
        modelName: document.getElementById("config-model-name").value.trim(),
        enabled: true,
        applyToMode: document.getElementById("config-apply-to-mode").checked,
    };
}

async function validateCurrentConfig() {
    const alert = document.getElementById("config-alert");
    const testBtn = document.getElementById("test-config-btn");
    const payload = currentConfigPayload();
    alert.classList.remove("hidden", "error", "success");
    testBtn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Testing...';
    try {
        const response = await fetch("./api/config/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        alert.className = "config-alert success";
        alert.textContent = `Connection successful: ${data.message}`;
    } catch (error) {
        alert.className = "config-alert error";
        alert.textContent = `Connection failed: ${error.message}`;
    } finally {
        testBtn.innerHTML = '<i class="ph ph-plugs-connected"></i> Validate';
    }
}

async function saveCurrentConfig() {
    const alert = document.getElementById("config-alert");
    const saveBtn = document.getElementById("save-config-btn");
    const configModal = document.getElementById("config-modal");
    const payload = currentConfigPayload();
    saveBtn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Saving...';
    try {
        const response = await fetch("./api/config/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        configState.slotsByMode[data.mode] = data.slots || [];
        alert.className = "config-alert success";
        alert.textContent = `Saved ${data.savedSlots.length} slot(s). The next dashboard refresh will use this connection.`;
        await hydrateDashboard();
        renderMemoryPanel();
        renderRound(Math.min(currentRoundIndex, Math.max(getRoundsData().length - 1, 0)));
        setTimeout(() => {
            configModal.classList.add("hidden");
            alert.classList.add("hidden");
        }, 1200);
    } catch (error) {
        alert.className = "config-alert error";
        alert.textContent = `Save failed: ${error.message}`;
    } finally {
        saveBtn.innerHTML = '<i class="ph ph-floppy-disk"></i> Save & Apply';
    }
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function richText(value) {
    return escapeHtml(value).replaceAll("\n", "<br>");
}

function renderRefs(refs) {
    if (!refs || !refs.length) {
        return "";
    }
    const pills = refs.map(ref => (
        `<span class="ref-pill ${escapeHtml(ref.type)}">` +
        `<i class="ph ${ref.type === "memory" ? "ph-brain" : "ph-file"}"></i> ` +
        `${escapeHtml(ref.text)}` +
        `</span>`
    )).join("");
    return `<div class="message-refs">${pills}</div>`;
}

function renderMemoryPanel() {
    // Memory timeline
    const timeline = document.getElementById("round-timeline");
    timeline.innerHTML = "";
    dashboardState.rounds.forEach(r => {
        if (!r.memory && r.round !== 3) return;
        let bodyHtml = r.memory ? `
            <strong>Observation:</strong> ${richText(r.memory.observation)}<br>
            <span style="color: var(--status-yellow); display:inline-block; margin-top:4px;"><strong>Detected:</strong> ${escapeHtml(r.memory.failureType)}</span>
        ` : '<span style="color:var(--text-secondary);font-style:italic;">In progress...</span>';

        timeline.insertAdjacentHTML("beforeend", `
            <div class="timeline-node" data-round="${r.round}">
                <div class="round-card">
                    <div class="round-card-header">
                        <span>Round ${r.round}</span>
                        <span class="rc-tag">Mechanism</span>
                    </div>
                    <div class="round-card-body">${bodyHtml}</div>
                </div>
            </div>
        `);
    });

    // Knowledge Cards
    const kc = document.getElementById("knowledge-cards");
    kc.innerHTML = "";
    dashboardState.rounds.filter(r => r.memory).forEach(r => {
        kc.insertAdjacentHTML("beforeend", `
            <div class="knowledge-card" data-id="${escapeHtml(r.memory.id)}">
                <strong style="display:block; margin-bottom:8px; color:var(--text-primary); border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:4px;">${escapeHtml(r.memory.id)} Knowledge</strong>
                <div class="kc-row"><div class="kc-label">Observation</div><div class="kc-val">${richText(r.memory.observation)}</div></div>
                <div class="kc-row"><div class="kc-label">Interpretation</div><div class="kc-val">${richText(r.memory.interpretation)}</div></div>
                <div class="kc-row"><div class="kc-label">Next Step</div><div class="kc-val" style="color: #a5b4fc">${richText(r.memory.nextStep)}</div></div>
            </div>
        `);
    });

    // Motifs
    const tagsContainer = document.getElementById("design-motifs");
    tagsContainer.innerHTML = "";
    const tags = dashboardState.motifs;
    tags.forEach(t => {
        tagsContainer.insertAdjacentHTML("beforeend", `<span class="motif-tag"><i class="ph ph-star-four"></i> ${escapeHtml(t)}</span>`);
    });
}
