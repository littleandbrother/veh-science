"""
MATLAB vs Python cross-validation script.

Uses the EXACT parameters from voltage_dimeless.m to verify our Python
implementation matches MATLAB output point-by-point.

MATLAB parameters (voltage_dimeless.m):
    n = 10
    ca = 0.0003
    ma = 0.05
    k_a = 500
    gamma = 4
    delta = 2
    alpha = 4        (m_b/m_a)
    beta = 1.5       (k_b/k_a)
    mu = sqrt(beta/alpha) = sqrt(1.5/4) = 0.6124...
    zeta1 = ca / (2*sqrt(k_a*ma)) = 0.0003 / (2*sqrt(25)) = 0.00003
    theta = 0.0002
    Cp = 8e-9
    R = 1e8
    w_a = sqrt(k_a/ma) = sqrt(10000) = 100
    eps = 1/(R*Cp*w_a) = 1/(100*8e-9*100) = 0.0125  (MATLAB w_a basis)
    k_e = sqrt(theta^2/(k_a*Cp)) => k_e^2 = 0.0002^2/(500*8e-9) = 0.01
    U0 = 0.0001  (fixed displacement)

Our Python parameters (omega_b basis):
    omega_b = sqrt(k_b/m_b) = sqrt(750/0.2) = sqrt(3750) = 61.237...
    kappa_sq = theta^2/(k_b*Cp) = 0.0002^2/(750*8e-9) = 0.006667
    epsilon = 1/(R*Cp*omega_b) = 1/(1e8*8e-9*61.237) = 0.02041...
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veh_scientist.verifiers.l1_chain import (
    compute_bandgap,
    dispersion_relation,
    analyze_finite_chain,
    frequency_sweep,
    compute_mode_shape_energy,
)
from veh_scientist.verifiers.l1_chain.piezo_harvesting import build_forced_response_matrix

# ── MATLAB exact parameters ──────────────────────────────────────────────
N_CELLS = 10
N = 2 * N_CELLS

# Physical
ca = 0.0003
ma = 0.05
k_a = 500.0
theta_dim = 0.0002
Cp = 8e-9
R = 1e8

# Non-dimensional (MATLAB naming)
alpha_m = 4.0        # m_b/m_a
beta_m  = 1.5        # k_b/k_a
delta_m = 2.0        # m_{a+}/m_a
gamma_m = 4.0        # c_b/c_a

m_b = ma * alpha_m   # 0.2
k_b = k_a * beta_m   # 750

mu_m = np.sqrt(beta_m / alpha_m)  # sqrt(1.5/4) = 0.6124...
w_a = np.sqrt(k_a / ma)           # 100.0
omega_b = np.sqrt(k_b / m_b)      # sqrt(3750)

zeta1_m = ca / (2 * np.sqrt(k_a * ma))  # 0.00003
eps_m = 1.0 / (R * Cp * w_a)            # 0.0125
k_e_sq_m = theta_dim**2 / (k_a * Cp)    # 0.01

U0_m = 0.0001  # fixed displacement

# Python-basis parameters
kappa_sq_p = theta_dim**2 / (k_b * Cp)    # = k_e_sq / beta
epsilon_p = 1.0 / (R * Cp * omega_b)      # = eps / mu

print("=" * 70)
print("PARAMETER VERIFICATION")
print("=" * 70)
print(f"  alpha = {alpha_m},  beta = {beta_m},  delta = {delta_m},  gamma = {gamma_m}")
print(f"  mu = {mu_m:.10f}")
print(f"  w_a = {w_a:.4f},  omega_b = {omega_b:.10f}")
print(f"  zeta1 = {zeta1_m:.10f}")
print(f"  MATLAB: k_e^2 = {k_e_sq_m:.10f},  eps = {eps_m:.10f}")
print(f"  Python: kappa_sq = {kappa_sq_p:.10f},  epsilon = {epsilon_p:.10f}")
print(f"  Verify: kappa_sq * beta = {kappa_sq_p * beta_m:.10f}  (should = k_e^2 = {k_e_sq_m:.10f})")
print(f"  Verify: epsilon * mu = {epsilon_p * mu_m:.10f}  (should = eps = {eps_m:.10f})")
print()

# ── Step 1: Verify bandgap ───────────────────────────────────────────────
gap = compute_bandgap(alpha_m, beta_m)
print("=" * 70)
print("STEP 1: BANDGAP VERIFICATION")
print("=" * 70)

# MATLAB dispersion (from para_test.m / FindBandgaps.m):
# Omega_acoustic at q=pi, Omega_optical at q=pi
q_pi = np.array([np.pi])
acoustic, optical = dispersion_relation(alpha_m, beta_m, q_pi)
print(f"  Bandgap: [{gap.lower:.10f}, {gap.upper:.10f}]")
print(f"  Acoustic(q=pi) = {acoustic[0]:.10f}")
print(f"  Optical(q=pi)  = {optical[0]:.10f}")
print()

# ── Step 2: Verify eigenfrequencies ──────────────────────────────────────
chain = analyze_finite_chain(alpha_m, beta_m, delta_m, N_CELLS)
print("=" * 70)
print("STEP 2: EIGENFREQUENCY VERIFICATION")
print("=" * 70)
print(f"  Found {len(chain.eigenfrequencies)} eigenfreqs (expected {N})")
print(f"  TR frequencies: {chain.tr_frequencies}")
print(f"  First 5 eigenfreqs: {chain.eigenfrequencies[:5]}")
print(f"  Last 5 eigenfreqs:  {chain.eigenfrequencies[-5:]}")
print()

# ── Step 3: Verify forced response matrix at a single frequency ──────────
# Pick Omega = 1.0 (inside bandgap for these params)
test_omega = 1.0
print("=" * 70)
print(f"STEP 3: MATRIX VERIFICATION at Omega = {test_omega}")
print("=" * 70)

A_py, b_py = build_forced_response_matrix(
    alpha_m, beta_m, delta_m, N_CELLS, test_omega,
    zeta1_m, kappa_sq_p, epsilon_p, gamma_m
)

# Manually compute MATLAB matrix entries for comparison
j = 1j
mu = mu_m
Omega = test_omega
zeta1 = zeta1_m
gamma = gamma_m
alpha = alpha_m
beta = beta_m
delta = delta_m
eps = eps_m
k_e = np.sqrt(k_e_sq_m)

# MATLAB A(1,1) from Lattice_B_new_6.m line 23:
A11_matlab = (-j*delta*mu**3*Omega**3
              - (2*(1+gamma)*zeta1 + delta*eps)*mu**2*Omega**2
              + (1+beta-k_e**2 + 2*zeta1*(1+gamma)*eps)*j*mu*Omega
              + (1+beta)*eps)

# MATLAB A(1,2) from line 24:
A12_matlab = (2*zeta1*mu**2*Omega**2
              - (1-k_e**2 + 2*zeta1*eps)*j*mu*Omega
              - eps)

# MATLAB b(1) from line 25:
b1_matlab = (-2*zeta1*gamma*mu**2*Omega**2
             + (beta + 2*zeta1*gamma*eps)*j*mu*Omega
             + beta*eps) * U0_m

print(f"  A[0,0] Python:  {A_py[0,0]}")
print(f"  A(1,1) MATLAB:  {A11_matlab}")
print(f"  Match: {np.isclose(A_py[0,0], A11_matlab)}")
print()
print(f"  A[0,1] Python:  {A_py[0,1]}")
print(f"  A(1,2) MATLAB:  {A12_matlab}")
print(f"  Match: {np.isclose(A_py[0,1], A12_matlab)}")
print()
print(f"  b[0] Python (U0=1):  {b_py[0]}")
print(f"  b(1) MATLAB (U0={U0_m}): {b1_matlab}")
print(f"  b[0]*U0 Python: {b_py[0]*U0_m}")
print(f"  Match: {np.isclose(b_py[0]*U0_m, b1_matlab)}")
print()

# Check internal row (e.g., row 3 = 2*i where i=1, 0-based row 2)
# MATLAB A(row1=2, 2*i=2): for i=1
# A(2, 2) = (1+beta - alpha*mu^2*Omega^2 + 2*j*mu*Omega*zeta1 + 2*j*mu*Omega*gamma*zeta1)
A_row2_col2_matlab = (1 + beta - alpha*mu**2*Omega**2
                      + 2*j*mu*Omega*zeta1
                      + 2*j*mu*Omega*gamma*zeta1)

# In Python, this corresponds to A[r1, r1] where r1 = 2*i for i=1 → r1=2
print(f"  A[2,2] Python:  {A_py[2,2]}")
print(f"  A(3,3) MATLAB:  {A_row2_col2_matlab}")
print(f"  Match: {np.isclose(A_py[2,2], A_row2_col2_matlab)}")
print()

# ── Step 4: Solve and compare displacement ───────────────────────────────
print("=" * 70)
print(f"STEP 4: DISPLACEMENT SOLUTION at Omega = {test_omega}")
print("=" * 70)

# Scale b by actual U0
b_scaled = b_py * U0_m
U_py, _, _, _ = np.linalg.lstsq(A_py, b_scaled, rcond=None)

print(f"  U[0] (mass 1, boundary): {U_py[0]}")
print(f"  U[1] (mass 2): {U_py[1]}")
print(f"  U[N-1] (mass {N}, last): {U_py[N-1]}")
print(f"  |U[0]| = {np.abs(U_py[0]):.10f}")
print(f"  |U[N-1]| = {np.abs(U_py[N-1]):.10f}")
print(f"  Transmission |U[N-1]/U0| = {np.abs(U_py[N-1])/U0_m:.6f}")
print(f"  Transmission dB = {20*np.log10(np.abs(U_py[N-1])/U0_m):.2f}")
print()

# Compute voltage (MATLAB formula from voltage_dimeless.m lines 45-51)
A_n = (-j*mu**3*Omega**3*delta/eps
       - mu**2*Omega**2*(2*zeta1*(1+gamma))/eps
       + j*mu*Omega*(1+beta-k_e**2)/eps)
A_n_plus_1 = -(-mu**2*Omega**2*2*zeta1/eps
               + j*mu*Omega*(1-k_e**2)/eps)
A_n_minus_1 = -(-mu**2*Omega**2*2*gamma*zeta1/eps
                + j*mu*Omega*beta/eps)

v_matlab = (A_n*U_py[0] + A_n_plus_1*U_py[1] + A_n_minus_1*U0_m) / U0_m
print(f"  Voltage (MATLAB formula): |v| = {np.abs(v_matlab):.10f}")

# Compare with our simplified voltage (Paper 1 Eq. 12)
gap_disp = U_py[0] - U_py[1]
V_simple = -j * Omega / (j * Omega + epsilon_p) * gap_disp
print(f"  Voltage (Paper 1 Eq.12): |V| = {np.abs(V_simple):.10f}")
print(f"  Note: These may differ because MATLAB uses the full coupled formula,")
print(f"        while Paper 1 Eq.12 is a simplified approximation.")
print()

# ── Step 5: Full frequency sweep comparison ──────────────────────────────
print("=" * 70)
print("STEP 5: FREQUENCY SWEEP (selected points)")
print("=" * 70)

test_omegas = [0.3, 0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5, 2.0]

for omega_test in test_omegas:
    A_t, b_t = build_forced_response_matrix(
        alpha_m, beta_m, delta_m, N_CELLS, omega_test,
        zeta1_m, kappa_sq_p, epsilon_p, gamma_m
    )
    b_t_scaled = b_t * U0_m
    U_t, _, _, _ = np.linalg.lstsq(A_t, b_t_scaled, rcond=None)

    trans = np.abs(U_t[N-1]) / U0_m
    trans_dB = 20 * np.log10(max(trans, 1e-30))

    gap_d = U_t[0] - U_t[1]
    V_t = -1j * omega_test / (1j * omega_test + epsilon_p) * gap_d
    voltage = np.abs(V_t)

    in_gap = "  [IN GAP]" if gap.lower < omega_test < gap.upper else ""

    print(f"  Ω={omega_test:.1f}: |V|={voltage:.6f}, T={trans_dB:.2f}dB, |U1|={np.abs(U_t[0]):.6f}, |U20|={np.abs(U_t[N-1]):.6f}{in_gap}")

print()
print("=" * 70)
print("CROSS-VALIDATION COMPLETE")
print("=" * 70)
print()
print("To verify against MATLAB, run voltage_dimeless.m in MATLAB and compare")
print("the voltage and transmission values at the same Omega points above.")
print("The matrix entries at Step 3 should match EXACTLY.")
