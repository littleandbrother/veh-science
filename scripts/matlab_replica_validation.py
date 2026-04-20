"""
Pure MATLAB-replica of voltage_dimeless.m in Python.

This script replicates the MATLAB code EXACTLY, using MATLAB variable names
and formulas, without going through our Python API. Then it compares the
results with our Python API to confirm they match.

If they match, it proves our Python API is equivalent to the MATLAB code.
"""

import sys, os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ═══════════════════════════════════════════════════════════════════════════
# PART 1: Pure MATLAB replica (variable names kept identical)
# ═══════════════════════════════════════════════════════════════════════════

n = 10
ca = 0.0003
ma = 0.05
k_a = 500
N = 2 * n
gamma = 4
delta = 2
alpha = 4
beta = 1.5
mu = np.sqrt(beta / alpha)
zeta1 = ca / (2 * np.sqrt(k_a * ma))
theta = 0.0002
Cp = 8e-9
R = 1e8
w_a = np.sqrt(k_a / ma)
j = 1j
eps = 1 / (R * Cp * w_a)
k_e = np.sqrt(theta**2 / (k_a * Cp))
U0 = 0.0001

omega_values = np.linspace(1e-6, np.pi, 10000)
voltage_matlab = np.zeros(len(omega_values))
kk_matlab = np.zeros(len(omega_values))


def Lattice_B_new_6_replica(n, beta, mu, Omega, zeta1, gamma, alpha, delta, eps, k_e, U0):
    """Exact replica of MATLAB Lattice_B_new_6.m"""
    j = 1j
    N = 2 * n
    A = np.zeros((N, N), dtype=complex)
    b = np.zeros(N, dtype=complex)

    for i in range(1, n):  # MATLAB i = 1:(n-1)
        row1 = 2 * i      # MATLAB row1 = 2*i (0-indexed: 2*i - 1)
        row2 = 2 * i + 1  # MATLAB row2 = 2*i+1 (0-indexed: 2*i)

        # MATLAB uses 1-based indexing; Python uses 0-based
        r1 = row1 - 1  # 0-based
        r2 = row2 - 1  # 0-based

        A[r1, 2*i - 1] = (1 + beta - alpha * mu**2 * Omega**2
                          + 2*j*mu*Omega*zeta1 + 2*j*mu*Omega*gamma*zeta1)
        A[r1, 2*i] = -(beta + 2*j*mu*Omega*gamma*zeta1)
        A[r1, 2*i - 2] = -(1 + 2*j*mu*Omega*zeta1)

        A[r2, 2*i] = (1 + beta - mu**2 * Omega**2
                      + 2*j*mu*Omega*zeta1 + 2*j*mu*Omega*gamma*zeta1)
        A[r2, 2*i - 1] = -(beta + 2*j*mu*Omega*gamma*zeta1)
        A[r2, 2*i + 1] = -(1 + 2*j*mu*Omega*zeta1)

    # Row 1 (0-indexed: row 0)
    A[0, 0] = (-j*delta*mu**3*Omega**3
               - (2*(1+gamma)*zeta1 + delta*eps)*mu**2*Omega**2
               + (1+beta-k_e**2 + 2*zeta1*(1+gamma)*eps)*j*mu*Omega
               + (1+beta)*eps)
    A[0, 1] = (2*zeta1*mu**2*Omega**2
               - (1-k_e**2 + 2*zeta1*eps)*j*mu*Omega
               - eps)
    b[0] = (-2*zeta1*gamma*mu**2*Omega**2
            + (beta + 2*zeta1*gamma*eps)*j*mu*Omega
            + beta*eps) * U0

    # Row 2 (0-indexed: row 1)
    A[1, 0] = (-j*delta*mu**3*Omega**3
               - 2*(1+gamma)*zeta1*mu**2*Omega**2
               + (1+beta-k_e**2 + 2*zeta1*eps)*j*mu*Omega
               + eps)
    A[1, 1] = ((2*zeta1 + alpha*eps)*mu**2*Omega**2
               - (1-k_e**2 + 2*zeta1*(1+gamma)*eps)*j*mu*Omega
               - (1+beta)*eps)
    A[1, 2] = 2*zeta1*gamma*eps*j*mu*Omega + beta*eps

    # Row N (0-indexed: N-1)
    A[N-1, N-1] = (2*j*mu*Omega*zeta1 + 2*j*mu*Omega*gamma*zeta1
                   + 1 + beta - alpha*mu**2*Omega**2)
    A[N-1, N-2] = -(2*j*mu*Omega*zeta1 + 1)

    U = np.linalg.lstsq(A, b, rcond=None)[0]
    Transmission = 20 * np.log10(max(abs(U[N-1] / U0), 1e-30))
    return Transmission, U


print("Computing MATLAB-replica frequency sweep ...")
for k in range(len(omega_values)):
    Omega = omega_values[k]
    if Omega < 1e-10:
        continue

    _, U_sol = Lattice_B_new_6_replica(n, beta, mu, Omega, zeta1, gamma, alpha, delta, eps, k_e, U0)

    kk_matlab[k] = abs(U_sol[N-1]) / abs(U0)

    A_n = (-j*mu**3*Omega**3*delta/eps
           - mu**2*Omega**2*(2*zeta1*(1+gamma))/eps
           + j*mu*Omega*(1+beta-k_e**2)/eps)
    A_n_plus_1 = -(-mu**2*Omega**2*2*zeta1/eps
                   + j*mu*Omega*(1-k_e**2)/eps)
    A_n_minus_1 = -(-mu**2*Omega**2*2*gamma*zeta1/eps
                    + j*mu*Omega*beta/eps)

    v_2n = (A_n*U_sol[0] + A_n_plus_1*U_sol[1] + A_n_minus_1*U0) / U0
    voltage_matlab[k] = abs(v_2n)

trans_matlab = 20 * np.log10(np.maximum(kk_matlab, 1e-30))
print("  Done.")

# ═══════════════════════════════════════════════════════════════════════════
# PART 2: Our Python API
# ═══════════════════════════════════════════════════════════════════════════

from veh_scientist.verifiers.l1_chain import frequency_sweep

# Convert to our API's omega_b-based parameters
omega_b = np.sqrt(k_a * beta / (ma * alpha))
kappa_sq_py = theta**2 / (k_a * beta * Cp)
epsilon_py = 1 / (R * Cp * omega_b)

print("Computing Python API frequency sweep ...")
resp = frequency_sweep(
    alpha=alpha, beta=beta, delta=delta, n_cells=n,
    kappa_sq=kappa_sq_py, epsilon=epsilon_py,
    zeta=zeta1, gamma=gamma,
    omega_range=omega_values,
    excitation_type="displacement",
    excitation_amplitude=U0,
)
print("  Done.")

# ═══════════════════════════════════════════════════════════════════════════
# PART 3: Point-by-point comparison
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 80)
print("POINT-BY-POINT COMPARISON: MATLAB-replica vs Python API")
print("=" * 80)

# Compare at selected frequencies
test_indices = [100, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 9500]

print(f"\n{'Omega':>8} | {'V_MATLAB':>14} {'V_Python':>14} {'V_err':>10} | "
      f"{'T_MATLAB':>10} {'T_Python':>10} {'T_err':>10}")
print("-" * 95)

max_v_err = 0.0
max_t_err = 0.0
n_compared = 0

for idx in test_indices:
    om = omega_values[idx]
    vm = voltage_matlab[idx]
    vp = resp.voltage[idx]
    tm = trans_matlab[idx]
    tp = resp.transmission_dB[idx]

    if vm > 1e-20:
        v_rel_err = abs(vm - vp) / vm
    else:
        v_rel_err = 0.0

    if abs(tm) > 0.01:
        t_rel_err = abs(tm - tp) / abs(tm)
    else:
        t_rel_err = abs(tm - tp)

    max_v_err = max(max_v_err, v_rel_err)
    max_t_err = max(max_t_err, t_rel_err)
    n_compared += 1

    print(f"{om:8.4f} | {vm:14.8f} {vp:14.8f} {v_rel_err:10.2e} | "
          f"{tm:10.2f} {tp:10.2f} {t_rel_err:10.2e}")

print("-" * 95)
print(f"Max voltage relative error: {max_v_err:.2e}")
print(f"Max transmission relative error: {max_t_err:.2e}")

# Full sweep comparison
nonzero = voltage_matlab > 1e-20
if np.any(nonzero):
    full_v_err = np.max(np.abs(voltage_matlab[nonzero] - resp.voltage[nonzero]) / voltage_matlab[nonzero])
    print(f"Full sweep max voltage relative error: {full_v_err:.2e}")

nonzero_t = np.abs(trans_matlab) > 0.01
if np.any(nonzero_t):
    full_t_err = np.max(np.abs(trans_matlab[nonzero_t] - resp.transmission_dB[nonzero_t]) / np.abs(trans_matlab[nonzero_t]))
    print(f"Full sweep max transmission relative error: {full_t_err:.2e}")

# ═══════════════════════════════════════════════════════════════════════════
# PART 4: Generate comparison figure
# ═══════════════════════════════════════════════════════════════════════════
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from veh_scientist.verifiers.l1_chain import compute_bandgap
gap = compute_bandgap(alpha, beta)

fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Top-left: Voltage comparison
ax = axes[0, 0]
ax.plot(omega_values, voltage_matlab, 'k-', lw=2, label='MATLAB replica')
ax.plot(omega_values, resp.voltage, 'r--', lw=1.5, label='Python API')
ax.axvspan(gap.lower, gap.upper, alpha=0.1, color='blue', label='Bandgap')
ax.set_ylabel('|V| (non-dim)')
ax.set_title('Voltage comparison')
ax.legend(fontsize=9)
ax.grid(alpha=0.3)

# Top-right: Voltage difference
ax = axes[0, 1]
v_diff = np.abs(voltage_matlab - resp.voltage)
ax.semilogy(omega_values, np.maximum(v_diff, 1e-30), 'k-', lw=1)
ax.axvspan(gap.lower, gap.upper, alpha=0.1, color='blue')
ax.set_ylabel('|V_MATLAB - V_Python|')
ax.set_title('Voltage absolute difference')
ax.grid(alpha=0.3)

# Bottom-left: Transmission comparison
ax = axes[1, 0]
ax.plot(omega_values, trans_matlab, 'k-', lw=2, label='MATLAB replica')
ax.plot(omega_values, resp.transmission_dB, 'r--', lw=1.5, label='Python API')
ax.axvspan(gap.lower, gap.upper, alpha=0.1, color='blue', label='Bandgap')
ax.axhline(0, color='gray', lw=0.5)
ax.set_ylabel('Transmission (dB)')
ax.set_xlabel('Ω')
ax.set_title('Transmission comparison')
ax.legend(fontsize=9)
ax.grid(alpha=0.3)

# Bottom-right: Transmission difference
ax = axes[1, 1]
t_diff = np.abs(trans_matlab - resp.transmission_dB)
ax.semilogy(omega_values, np.maximum(t_diff, 1e-30), 'k-', lw=1)
ax.axvspan(gap.lower, gap.upper, alpha=0.1, color='blue')
ax.set_ylabel('|T_MATLAB - T_Python| (dB)')
ax.set_xlabel('Ω')
ax.set_title('Transmission absolute difference')
ax.grid(alpha=0.3)

fig.suptitle(f'MATLAB vs Python cross-validation\n'
             f'α={alpha}, β={beta}, δ={delta}, γ={gamma}, ζ={zeta1}, '
             f'k_e²={k_e**2}, ε={eps}',
             fontsize=12)
fig.tight_layout()

outdir = "results/cross_validation"
os.makedirs(outdir, exist_ok=True)
fig.savefig(os.path.join(outdir, "matlab_vs_python.png"), dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"\nFigure saved to {outdir}/matlab_vs_python.png")

# Verdict
print("\n" + "=" * 80)
if full_v_err < 1e-6 and full_t_err < 1e-6:
    print("✅ VERDICT: Python API matches MATLAB replica to machine precision.")
    print("   The Python implementation is EQUIVALENT to the MATLAB code.")
elif full_v_err < 1e-3 and full_t_err < 1e-3:
    print("✅ VERDICT: Python API matches MATLAB replica within 0.1%.")
    print("   Minor numerical differences exist but are negligible.")
else:
    print(f"❌ VERDICT: Significant discrepancy detected.")
    print(f"   Voltage error: {full_v_err:.2e}, Transmission error: {full_t_err:.2e}")
print("=" * 80)
