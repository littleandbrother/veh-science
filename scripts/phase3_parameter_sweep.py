"""
Phase 3: Parameter sweep and failure mode verification for L1 chain model.

Includes:
  - δ sweep: verify V-shaped voltage response (TR on/off switch)
  - (α, β) heatmap: bandgap and TR frequency tuning
  - (κ², ε) sweep: impedance matching verification
  - Failure mode F1-F10 checking
"""

import sys, os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from veh_scientist.verifiers.l1_chain import (
    compute_bandgap,
    analyze_finite_chain,
    frequency_sweep,
    compute_harvesting_metrics,
)

OUTDIR = "results/phase3"
os.makedirs(OUTDIR, exist_ok=True)

# ── Reference parameters ─────────────────────────────────────────────────
ALPHA = 0.75
BETA = 3.0
N_CELLS = 10
KAPPA_SQ = 0.0075
EPSILON = 6.25
ZETA = 0.003
GAMMA = 1.0

# ═══════════════════════════════════════════════════════════════════════════
# Step 3a: δ sweep — V-shaped voltage response
# ═══════════════════════════════════════════════════════════════════════════
print("Step 3a: δ sweep ...")
delta_vals = np.linspace(0.1, 4.0, 40)
gap = compute_bandgap(ALPHA, BETA)
omega_max = gap.upper * 1.5
omega_sweep = np.linspace(0.01, omega_max, 3000)

v_at_tr = []
for d in delta_vals:
    resp = frequency_sweep(
        ALPHA, BETA, d, N_CELLS, KAPPA_SQ, EPSILON, ZETA, GAMMA,
        omega_range=omega_sweep, excitation_type="acceleration",
    )
    gap_mask = (omega_sweep >= gap.lower) & (omega_sweep <= gap.upper)
    v_at_tr.append(np.max(resp.voltage * gap_mask))

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(delta_vals, v_at_tr, 'ko-', ms=4, lw=1.5)
ax.axvline(1.0, color='red', ls='--', lw=1, label='δ=1 (no TR)')
ax.set_xlabel("δ (boundary asymmetry)")
ax.set_ylabel("Max in-gap |V|")
ax.set_title("Step 3a: δ sweep — V-shaped voltage response\n(acceleration excitation)")
ax.legend()
ax.grid(alpha=0.3)
fig.savefig(os.path.join(OUTDIR, "step3a_delta_sweep.png"), bbox_inches='tight', dpi=150)
plt.close(fig)
print("  Done. Saved step3a_delta_sweep.png")

# ═══════════════════════════════════════════════════════════════════════════
# Step 3b: (α, β) heatmap — bandgap width
# ═══════════════════════════════════════════════════════════════════════════
print("Step 3b: (α, β) bandgap width heatmap ...")
alpha_vals = np.linspace(0.3, 3.0, 20)
beta_vals = np.linspace(0.3, 5.0, 20)
gap_width = np.zeros((len(alpha_vals), len(beta_vals)))

for i, a in enumerate(alpha_vals):
    for j, b in enumerate(beta_vals):
        g = compute_bandgap(a, b)
        gap_width[i, j] = g.width if g.exists else 0.0

fig, ax = plt.subplots(figsize=(8, 6))
im = ax.pcolormesh(beta_vals, alpha_vals, gap_width, shading='auto', cmap='viridis')
fig.colorbar(im, ax=ax, label='Bandgap width (Ω)')
ax.set_xlabel("β (k_b/k_a)")
ax.set_ylabel("α (m_b/m_a)")
ax.set_title("Step 3b: Bandgap width vs (α, β)")
ax.plot(BETA, ALPHA, 'r*', ms=15, label=f'Reference (α={ALPHA}, β={BETA})')
ax.legend()
fig.savefig(os.path.join(OUTDIR, "step3b_alpha_beta_heatmap.png"), bbox_inches='tight', dpi=150)
plt.close(fig)
print("  Done. Saved step3b_alpha_beta_heatmap.png")

# ═══════════════════════════════════════════════════════════════════════════
# Step 3c: ε sweep — impedance matching
# ═══════════════════════════════════════════════════════════════════════════
print("Step 3c: ε sweep (impedance matching) ...")
epsilon_vals = np.logspace(-2, 2, 30)
delta_ref = 0.5
power_at_tr = []

for eps_val in epsilon_vals:
    resp = frequency_sweep(
        ALPHA, BETA, delta_ref, N_CELLS, KAPPA_SQ, eps_val, ZETA, GAMMA,
        omega_range=omega_sweep, excitation_type="acceleration",
    )
    gap_mask = (omega_sweep >= gap.lower) & (omega_sweep <= gap.upper)
    max_power = np.max(resp.power * gap_mask)
    power_at_tr.append(max_power)

# Find optimal epsilon
i_opt = np.argmax(power_at_tr)
eps_opt = epsilon_vals[i_opt]

# TR frequency for comparison
chain = analyze_finite_chain(ALPHA, BETA, delta_ref, N_CELLS)
omega_tr = chain.tr_frequencies[0] if len(chain.tr_frequencies) > 0 else gap.center

fig, ax = plt.subplots(figsize=(8, 5))
ax.semilogx(epsilon_vals, power_at_tr, 'ko-', ms=4, lw=1.5)
ax.axvline(eps_opt, color='red', ls='--', lw=1, label=f'ε_opt={eps_opt:.3f}')
ax.axvline(omega_tr, color='blue', ls=':', lw=1, label=f'Ω_TR={omega_tr:.3f}')
ax.set_xlabel("ε = 1/(R·Cp·ωb)")
ax.set_ylabel("Max in-gap power")
ax.set_title(f"Step 3c: Impedance matching\nε* ≈ Ω_TR prediction: ε*={eps_opt:.3f}, Ω_TR={omega_tr:.3f}")
ax.legend()
ax.grid(alpha=0.3)
fig.savefig(os.path.join(OUTDIR, "step3c_epsilon_sweep.png"), bbox_inches='tight', dpi=150)
plt.close(fig)
print(f"  Done. ε_opt={eps_opt:.4f}, Ω_TR={omega_tr:.4f}. Saved step3c_epsilon_sweep.png")

# ═══════════════════════════════════════════════════════════════════════════
# Step 3d: Failure mode checks
# ═══════════════════════════════════════════════════════════════════════════
print("\nStep 3d: Failure mode verification ...")
print("=" * 60)

# F1: TR pulled out of bandgap by electrical coupling
print("F1: TR pulled out of bandgap by electrical coupling")
# Check with strong coupling
kappa_strong = 0.1
resp_strong = frequency_sweep(
    ALPHA, BETA, delta_ref, N_CELLS, kappa_strong, EPSILON, ZETA, GAMMA,
    omega_range=omega_sweep, excitation_type="acceleration",
)
gap_mask = (omega_sweep >= gap.lower) & (omega_sweep <= gap.upper)
has_tr_in_gap = np.max(resp_strong.voltage * gap_mask) > 0
print(f"  κ²={kappa_strong}: TR still in gap? {'✅ Yes' if has_tr_in_gap else '⚠️ No — F1 triggered'}")

# F2: Insufficient boundary localization (delta close to 1)
print("F2: Insufficient boundary localization")
chain_d09 = analyze_finite_chain(ALPHA, BETA, 0.9, N_CELLS)
n_tr_d09 = len(chain_d09.tr_frequencies)
print(f"  δ=0.9: {n_tr_d09} TR modes found {'✅' if n_tr_d09 > 0 else '⚠️ F2 triggered'}")

# F3: TR peak too narrow
print("F3: TR peak bandwidth check")
resp_ref = frequency_sweep(
    ALPHA, BETA, delta_ref, N_CELLS, KAPPA_SQ, EPSILON, ZETA, GAMMA,
    omega_range=omega_sweep, excitation_type="acceleration",
)
gap_mask_ref = (omega_sweep >= gap.lower) & (omega_sweep <= gap.upper)
v_gap = resp_ref.voltage * gap_mask_ref
i_peak = np.argmax(v_gap)
v_peak = v_gap[i_peak]
threshold = v_peak / np.sqrt(2)
above = np.where(v_gap >= threshold)[0]
if len(above) > 1:
    bw = omega_sweep[above[-1]] - omega_sweep[above[0]]
    print(f"  -3dB bandwidth = {bw:.5f} Ω {'✅ OK' if bw > 0.001 else '⚠️ Very narrow — F3'}")
else:
    print("  ⚠️ Cannot measure bandwidth — F3 may be triggered")

# F6: Manufacturing tolerance (parameter perturbation)
print("F6: Manufacturing tolerance (±5% perturbation)")
np.random.seed(42)
n_trials = 5
tr_found_count = 0
for trial in range(n_trials):
    # Perturb alpha and beta by ±5%
    a_pert = ALPHA * (1 + 0.05 * (2*np.random.random() - 1))
    b_pert = BETA * (1 + 0.05 * (2*np.random.random() - 1))
    chain_pert = analyze_finite_chain(a_pert, b_pert, delta_ref, N_CELLS)
    if len(chain_pert.tr_frequencies) > 0:
        tr_found_count += 1

print(f"  TR found in {tr_found_count}/{n_trials} perturbed cases {'✅' if tr_found_count == n_trials else '⚠️ F6'}")

print("\n" + "=" * 60)
print("Phase 3 complete. Results in", OUTDIR)
print("=" * 60)
