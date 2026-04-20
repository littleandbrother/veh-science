// Mock Data Engine for VEH Scientist Cockpit

const agentConfig = {
    "User": { color: "#22c55e", icon: "ph-user", role: "Human Steering" },
    "Coordinator": { color: "#6366f1", icon: "ph-user-gear", role: "Target & Convergence" },
    "Mechanism": { color: "#10b981", icon: "ph-atom", role: "Physics Theory" },
    "Structure": { color: "#f59e0b", icon: "ph-bounding-box", role: "Topology" },
    "Critic": { color: "#ef4444", icon: "ph-warning", role: "Risk Analysis" },
    "Paper": { color: "#8b5cf6", icon: "ph-books", role: "Literature" },
    "Verifier Planner": { color: "#06b6d4", icon: "ph-flow-arrow", role: "Execution" }
};

const mockRounds = [
    {
        round: 1,
        status: "Completed",
        budgetStr: "6 / 6",
        bestCandidate: "None",
        messages: [
            { agent: "Coordinator", type: "system", content: "Round 1 started. Target: TR-based simultaneous suppression & harvesting. Recommend conservative initial exploration." },
            { agent: "Mechanism", type: "normal", content: "Let's start with a standard diatomic chain model to verify the core TR mechanism. Set `delta = 1.5` to break boundary symmetry and open a TR inside the first bandgap." },
            { agent: "Structure", type: "normal", content: "Agreed. I will parameterize a simple Al/Epoxy boundary mass to achieve `delta = 1.5`. We will attach a single piezo patch at the (1-2) cell interface.", refs: [{type: "paper", text: "Standard Diatomic Ref"}] },
            { agent: "Critic", type: "normal", content: "Warning: Pure boundary TR under fixed base acceleration often suffers from weak input coupling (low strain at boundary). Output power might be negligible." },
            { agent: "Paper", type: "normal", content: "Literature confirms this. Rosa et al. (2022) notes that while topologically protected, boundary strain relies heavily on system Q-factor.", refs: [{type: "paper", text: "Rosa 2022"}] },
            { agent: "Coordinator", type: "system", content: "Valid concern. Let's form Proposal #1 to test this exact hypothesis. If power is low, we verify Critic's intuition." }
        ],
        proposal: {
            title: "P1: Pure Boundary TR",
            params: [
                { name: "Structure", val: "Finite Chain (N=10)" },
                { name: "alpha, beta", val: "1.0, 0.5 (Bandgap: [Omega_A, Omega_B])" },
                { name: "delta", val: "1.5 (Mass Asymmetry)" },
                { name: "Piezo Loc", val: "Cell Interface (1-2)" }
            ],
            pros: ["Mathematically pure TR", "Guaranteed via Topology"],
            cons: ["Potential weak input coupling", "Narrow bandwidth"]
        },
        verification: {
            python: {
                status: "partial",
                metrics: [
                    { label: "TR Exists", val: "Yes", cls: "v-pass" },
                    { label: "Power Output", val: "Low (PEF < 10)", cls: "v-warn" },
                    { label: "Suppression", val: "Pass (T < -10dB)", cls: "v-pass" },
                    { label: "Baseline V.", val: "Fail (Worse than PB1)", cls: "v-fail" }
                ],
                details: "Bandgap observed. Boundary localization eta = 0.65. However, power enhancement factor (PEF) is only 8x compared to passband due to extremely localized strain.",
                log: "[10:24:12] Engine initialized. N=10, delta=1.5\n[10:24:13] Computing dispersion... Bandgap found [410, 950] Hz.\n[10:24:15] Solving dynamical matrix det A = 0... \n[10:24:16] Boundary mode isolated at Omega_TR = 0.85\n[10:24:16] Simulation complete."
            }
        },
        memory: {
            id: "M1",
            observation: "Pure TR under fixed acceleration yields low PEF.",
            interpretation: "Input coupling to boundary-localized mode is weak; vibration dissipates before reaching the harvesting cell.",
            failureType: "F1: Weak input coupling",
            nextStep: "Need a mechanism to bridge input energy to the boundary. Consider boundary tuning layer or near-boundary defect."
        }
    },
    {
        round: 2,
        status: "Completed",
        budgetStr: "5 / 6",
        bestCandidate: "P2: TR + Tuning Layer",
        messages: [
            { agent: "Coordinator", type: "system", content: "Round 2. Based on Round 1 failure (M1), we need to improve input coupling to the boundary mode.", refs: [{type: "memory", text: "M1: Weak input coupling"}] },
            { agent: "Structure", threaded: true, content: "I propose adding a boundary tuning layer (soft inclusion) before the boundary mass. This acts as a mechanical impedance matching network." },
            { agent: "Mechanism", threaded: true, content: "Yes! In the phason framework, this is equivalent to tuning the boundary phase `phi_r` independently to pull the TR frequency closer to the bandgap edge, expanding the mode shape." },
            { agent: "Verifier Planner", type: "normal", content: "Let's run this through L2 TMM to capture continuous beam effects. Python L1 might be too simplistic for the tuning layer." },
            { agent: "Coordinator", type: "system", content: "Formulating Proposal #2. Sending to L2 TMM (MATLAB)." }
        ],
        proposal: {
            title: "P2: TR + Tuning Layer",
            params: [
                { name: "Structure", val: "Bilayer Beam (Al/Epoxy)" },
                { name: "Tuning Layer", val: "Soft layer right before boundary" },
                { name: "delta", val: "1.5 (maintained)" },
                { name: "Piezo Loc", val: "Cell Interface (1-2)" }
            ],
            pros: ["Better strain at boundary", "Improved impedance matching"],
            cons: ["More complex fabrication", "TR mode might exit bandgap"]
        },
        verification: {
            python: { 
                status: "pass", 
                metrics: [{ label: "TR Exists", val: "Yes", cls: "v-pass"}],
                details: "Quick check passed.", log: "[10:25:01] Fast L1 verification..."
            },
            matlab: {
                status: "partial",
                metrics: [
                    { label: "TR Exists", val: "Yes (532 Hz)", cls: "v-pass" },
                    { label: "Power Output", val: "Improved (PEF = 45)", cls: "v-warn" },
                    { label: "Suppression", val: "Pass", cls: "v-pass" },
                    { label: "Baseline V.", val: "Borderline", cls: "v-warn" }
                ],
                details: "TMM verifies TR at 532Hz. PEF improved from 8 to 45. Mode shape shows wider boundary participation. Still slightly below the PEF=100 target for publication.",
                log: "Running TMM engine...\nTransfer matrix multiplication... done.\nDet search in range [300, 1000] Hz...\nFound roots at 532.5 Hz\nCalculating PEF..."
            }
        },
        memory: {
            id: "M2",
            observation: "Tuning layer improves PEF to 45x but doesn't reach the target.",
            interpretation: "Mode shape broadened, but amplitude is still limited by overall transmissibility of the bandgap.",
            failureType: "Partial Success: Tuning Layer effectiveness",
            nextStep: "Combine tuning layer with a near-boundary periodic defect to act as an energy funnel."
        }
    },
    {
        round: 3,
        status: "Discussing",
        budgetStr: "3 / 6",
        bestCandidate: "P2: TR + Tuning Layer",
        messages: [
            { agent: "Coordinator", type: "system", content: "Round 3. M2 showed promise. We need to push PEF > 100 while maintaining suppression." },
            { agent: "Mechanism", type: "normal", content: "We can synergize TR with a shallow defect mode. If we place an engineered defect right next to the boundary, it can couple with the TR mode.", refs: [{type: "memory", text: "M2: Partial Success"}] },
            { agent: "Critic", type: "normal", content: "If the defect crosses the TR frequency, they will hybridize. We might lose topological protection (C_g changes)." },
            { agent: "Coordinator", type: "system", content: "Drafting Proposal #3. Waiting for verification..." }
        ],
        proposal: {
            title: "P3: TR + Defect Funnel",
            params: [
                { name: "Structure", val: "Bilayer Beam with Cell 2 Defect" },
                { name: "Tuning", val: "Hybrid mode" },
                { name: "Defect loc", val: "Cell 2, +20% mass" }
            ],
            pros: ["Maximized strain via hybridization", "Energy funneling"],
            cons: ["Sensitivity to tolerances", "Potential loss of topological protection"]
        },
        verification: {
            python: { status: "missing" },
            matlab: { status: "missing" },
            comsol: { status: "missing" }
        },
        memory: null
    }
];

const mockRoundsMultiLLM = [
    {
        round: 1,
        status: "Completed",
        budgetStr: "6 / 6",
        bestCandidate: "None",
        messages: [
            {
                agent: "GPT-Scientist",
                type: "normal",
                content: "I propose a pure boundary TR approach under fixed acceleration to establish a baseline.",
                sections: {
                    "mechanism view": "Set <code>delta = 1.5</code> to break boundary symmetry and open a TR inside the first bandgap.",
                    "structure view": "Parameterize a simple Al/Epoxy boundary mass. Attach a single piezo patch at the (1-2) cell interface.",
                    "critique": "Pure boundary TR under fixed base acceleration often suffers from weak input coupling. Output power might be negligible.",
                    "paper grounding": "Rosa et al. (2022) notes that topologically protected boundary strain relies heavily on system Q-factor.",
                    "verification suggestion": "Run L1 Python on a 10-cell finite chain to measure PEF."
                }
            },
            {
                agent: "Claude-Scientist",
                type: "normal",
                content: "I agree with GPT's baseline proposal. Let's submit this as Proposal #1 to verify its strict bounds.",
                sections: {
                    "mechanism view": "Topological protection only guarantees existence, not excitability from a uniform base acceleration.",
                    "structure view": "No structure change needed for baseline.",
                    "critique": "If PEF is too low, we move to tuning layers or defects.",
                    "paper grounding": "Consistent with general localized mode excitation principles.",
                    "verification suggestion": "L1 Python is sufficient for this check."
                }
            },
            {
                agent: "Qwen-Scientist",
                type: "normal",
                content: "I partially disagree. Why start with a baseline we know will yield low power? We should immediately implement a tuning layer.",
                sections: {
                    "mechanism view": "Baseline TR has near-zero strain under uniform acceleration due to orthogonality.",
                    "structure view": "We should immediately add a soft epoxy tuning layer before the boundary.",
                    "critique": "Time and budget are wasted on measuring a known null result.",
                    "paper grounding": "Literature shows purely isolated boundary modes are un-excitable from the base.",
                    "verification suggestion": "Skip L1, move straight to L2 TMM."
                }
            },
            {
                agent: "Gemini-Scientist",
                type: "normal",
                content: "I must disagree with Qwen. Establishing a rigorous empirical baseline is crucial for any high-impact publication. I side with GPT.",
                sections: {
                    "mechanism view": "Baseline comparison provides the exact delta needed to prove the enhancement factor of subsequent steps.",
                    "structure view": "Keep the standard structure first.",
                    "critique": "Skipping the baseline weakens the paper's core narrative.",
                    "paper grounding": "Nature Communications usually demands a strict reference case to quantify enhancement.",
                    "verification suggestion": "L1 Python is fast enough to not drain our verification budget."
                }
            },
            {
                agent: "Grok-Scientist",
                type: "normal",
                content: "Agreed with Gemini. The scientific method demands baselines. Let's push Proposal 1 forward without overcomplicating it yet.",
                sections: {
                    "mechanism view": "Verify the basic mathematical existence of the topological mode at delta=1.5.",
                    "structure view": "Simple boundary mass is adequate.",
                    "critique": "We just need to confirm the mode exists before trying to optimize its coupling.",
                    "paper grounding": "Standard scientific method for metamaterial harvesting.",
                    "verification suggestion": "L1 is perfect to isolate the TR root."
                }
            },
            {
                agent: "Deepseek-Scientist",
                type: "normal",
                content: "Consensus reached on the baseline. We will execute. We must expect a low PEF as noted by GPT's critique, so prepare for Round 2 redesign.",
                sections: {
                    "mechanism view": "We are specifically looking for the exact frequency of the TR root.",
                    "structure view": "Standard Al/Epoxy chain.",
                    "critique": "Our true challenge will be redesigning the input path afterward.",
                    "paper grounding": "Confirms known boundary excitation limits in finite chains.",
                    "verification suggestion": "Execute L1 Python."
                }
            }
        ],
        proposal: mockRounds[0].proposal,
        verification: mockRounds[0].verification,
        memory: mockRounds[0].memory
    },
    {
        round: 2,
        status: "Completed",
        budgetStr: "6 / 6",
        bestCandidate: "P2: TR + Tuning Layer",
        messages: [
            {
                agent: "Deepseek-Scientist",
                type: "normal",
                content: "Following up on Round 1 failure to reach high PEF, we must now improve the input path.",
                sections: {
                    "mechanism view": "In the phason framework, adding a soft inclusion tunes the boundary phase independently to pull the TR closer to the edge.",
                    "structure view": "Add a boundary tuning layer (soft epoxy) before the boundary mass.",
                    "critique": "TR mode might exit the bandgap entirely if the tuning layer softens the boundary too much.",
                    "paper grounding": "Concept similar to impedance matching networks in classical acoustics.",
                    "verification suggestion": "Run L2 TMM (MATLAB) to capture continuous beam effects."
                },
                refs: [{type: "memory", text: "M1: Weak input coupling"}]
            },
            {
                agent: "Qwen-Scientist",
                type: "normal",
                content: "I strongly agree. This is exactly what I proposed early in Round 1. Changing the boundary phase will broaden the mode into the acceleration field.",
                sections: {
                    "mechanism view": "Broadening the mode shape increases mass participation, boosting the modal force from uniform base acceleration.",
                    "structure view": "A single extra epoxy block is sufficient.",
                    "critique": "Mode might become too delocalized, reducing the peak strain.",
                    "paper grounding": "Prior work on defect-mode broadening supports this approach.",
                    "verification suggestion": "L2 TMM will accurately show mode participation."
                }
            },
            {
                agent: "Claude-Scientist",
                type: "normal",
                content: "I have concerns. A soft tuning layer might shift the TR frequency outside the bandgap. Are we sure this won't break the topological protection?",
                sections: {
                    "mechanism view": "The added compliance acts as a perturbation that might drastically shift the Zak phase transition point.",
                    "structure view": "Soft epoxy layer might act as a parasitic resonator rather than an impedance matcher.",
                    "critique": "We risk losing the localization entirely and reverting to a standard standing wave.",
                    "paper grounding": "Careful impedance matching must maintain the global unit cell symmetries.",
                    "verification suggestion": "We must verify with L2 TMM to check the continuous beam det(A) root."
                }
            },
            {
                agent: "Gemini-Scientist",
                type: "normal",
                content: "Claude has a highly valid point. I disagree with a purely homogeneous soft layer. What if we use a graded stiffness layer to smoothly transition impedance?",
                sections: {
                    "mechanism view": "A gradient avoids abrupt reflections, keeping the mode pinned to the boundary.",
                    "structure view": "Functionally graded material (FGM) between the chain and the boundary.",
                    "critique": "Fabrication would require advanced 3D printing, severely limiting experimental viability.",
                    "paper grounding": "FGM acoustic metamaterials show superior input coupling without breaking topology.",
                    "verification suggestion": "L3 COMSOL required for graded materials."
                }
            },
            {
                agent: "Grok-Scientist",
                type: "normal",
                content: "A graded layer is way too hard to fabricate for macro-scale piezoelectric beams. I vote we reject Gemini's idea and stick to Deepseek's single soft layer, but keep it very thin.",
                sections: {
                    "mechanism view": "A thin layer acts as a phase tuner without fully breaking the bandgap impedance.",
                    "structure view": "Single thin layer of epoxy (approx 2mm) rather than a full cell width.",
                    "critique": "Performance gain might be modest compared to a continuous gradient, but it is achievable.",
                    "paper grounding": "Standard engineering compromise between theory and manufacture.",
                    "verification suggestion": "L2 TMM with a fractional layer thickness."
                }
            },
            {
                agent: "GPT-Scientist",
                type: "normal",
                content: "I agree with Grok. A single thin soft layer is an optimal compromise between fabrication reality and phase tuning. Let's form Proposal #2.",
                sections: {
                    "mechanism view": "Phase boundary shifts just enough to increase coupling without breaking the gap.",
                    "structure view": "Bilayer beam configuration, adding a 2mm epoxy layer.",
                    "critique": "We still might not reach the ambitious PEF > 100 target.",
                    "paper grounding": "Validated by standard bilayer chain literature.",
                    "verification suggestion": "Execute L2 TMM to find the new root."
                }
            }
        ],
        proposal: mockRounds[1].proposal,
        verification: mockRounds[1].verification,
        memory: mockRounds[1].memory
    },
    {
        round: 3,
        status: "Discussing",
        budgetStr: "6 / 6",
        bestCandidate: "P2: TR + Tuning Layer",
        messages: [
            {
                agent: "Qwen-Scientist",
                type: "normal",
                content: "M2 shows promise but we haven't reached the theoretical apex (PEF > 100). We should synergize TR with a shallow defect mode.",
                sections: {
                    "mechanism view": "If we place an engineered defect right next to the boundary, it can couple with the TR mode, creating a localization funnel.",
                    "structure view": "Modify Cell 2 mass to +20% as an engineered defect.",
                    "critique": "If the defect mode frequency crosses the TR frequency, they hybridize. We might lose topological protection entirely.",
                    "paper grounding": "Hybridization of defect modes and topological edge states (Liu et al.).",
                    "verification suggestion": "Requires L3 COMSOL to accurately model the 3D strain field."
                },
                refs: [{type: "memory", text: "M2: Partial Success"}]
            },
            {
                agent: "GPT-Scientist",
                type: "normal",
                content: "I must disagree with placing the defect directly next to the boundary (Cell 2). A strong defect there might completely swallow the TR mode.",
                sections: {
                    "mechanism view": "Near-field interaction between the topological boundary and a strong defect state can cause level repulsion.",
                    "structure view": "A +20% mass at Cell 2 is too aggressive.",
                    "critique": "The frequency split will push both modes into the bulk bands, destroying strain localization.",
                    "paper grounding": "Level repulsion in coupled acoustic resonators.",
                    "verification suggestion": "L3 COMSOL will easily show if the mode splits."
                }
            },
            {
                agent: "Claude-Scientist",
                type: "normal",
                content: "GPT is right. If hybridization is too strong, the mode splits and the Q-factor drops. I suggest placing the defect at cell 3 instead, to act as a weak scatterer.",
                sections: {
                    "mechanism view": "Cell 3 placement allows weak coupling through the evanescent tail of the TR mode.",
                    "structure view": "Move the +20% mass defect to Cell 3.",
                    "critique": "Coupling might be too weak to form an effective funnel.",
                    "paper grounding": "Evanescent coupling between distant defect states.",
                    "verification suggestion": "Run a parametric sweep in COMSOL over defect location."
                }
            },
            {
                agent: "Gemini-Scientist",
                type: "normal",
                content: "Placing it at cell 3 weakens the funneling effect too much! I support Qwen's cell 2 location, but we should make it a very small perturbation (+5%) to avoid mode splitting.",
                sections: {
                    "mechanism view": "A +5% mass defect shifts the local mode just enough to overlap with TR, without causing massive level repulsion.",
                    "structure view": "Keep defect at Cell 2, but reduce to +5% mass.",
                    "critique": "+5% mass might fall within experimental error or machining tolerances.",
                    "paper grounding": "Perturbation theory in discrete periodic structures.",
                    "verification suggestion": "L3 COMSOL with structural mechanics module."
                }
            },
            {
                agent: "Deepseek-Scientist",
                type: "normal",
                content: "Agreed with Gemini. A +5% mass defect at cell 2 will gently pull the extended tail of the TR mode without destroying its topological origin.",
                sections: {
                    "mechanism view": "Gentle gradient forces the mode energy to peak slightly deeper into the chain, exactly where the piezo is.",
                    "structure view": "Cell 2, +5% mass defect.",
                    "critique": "Must explicitly account for exact machining tolerances in L3.",
                    "paper grounding": "Synergizing topological boundaries with weak defects for enhanced harvesting.",
                    "verification suggestion": "L3 COMSOL."
                }
            },
            {
                agent: "Grok-Scientist",
                type: "normal",
                content: "Consensus formed around Proposal #3: TR + 5% Defect at Cell 2. This requires full 3D verification to observe the strain field on the piezo patch.",
                sections: {
                    "mechanism view": "Finalize the coupled mode shape.",
                    "structure view": "Final assembly structure.",
                    "critique": "This is our final attempt to breach PEF > 100 before we must reconsider the whole mechanism.",
                    "paper grounding": "State-of-the-art multi-defect topological metamaterial design.",
                    "verification suggestion": "Proceed to L3 COMSOL verification."
                }
            }
        ],
        proposal: mockRounds[2].proposal,
        verification: mockRounds[2].verification,
        memory: null
    }
];

const llmConfig = {
    "User": { color: "#22c55e", icon: "ph-user", role: "Human Steering" },
    "GPT-Scientist": { color: "#10a37f", icon: "ph-brain", role: "Unified Scaffold" },
    "Claude-Scientist": { color: "#D97757", icon: "ph-brain", role: "Unified Scaffold" },
    "Qwen-Scientist": { color: "#615ced", icon: "ph-brain", role: "Unified Scaffold" },
    "Gemini-Scientist": { color: "#1a73e8", icon: "ph-brain", role: "Unified Scaffold" },
    "Grok-Scientist": { color: "#9ca3af", icon: "ph-brain", role: "Unified Scaffold" },
    "Deepseek-Scientist": { color: "#4d50ff", icon: "ph-brain", role: "Unified Scaffold" }
};
