"""
Piezoelectric coupling and energy harvesting for the finite diatomic chain.

Reference: Paper 1 Section 3, Eq. (9)-(13).
MATLAB reference: voltage_dimeless.m, Lattice_B_new_6.m, Energy_calculate1.m

Covers:
  - Forced response with piezoelectric port (Step 0d)
  - Mode shapes and energy concentration ratio eta (Step 0c)
  - Voltage, power, transmission, PEF calculation
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .dispersion import compute_bandgap
from .finite_chain import analyze_finite_chain


@dataclass(frozen=True)
class ForcedResponseResult:
    """Result of a frequency sweep with piezoelectric coupling."""

    omega: NDArray[np.floating]       # non-dimensional frequency array
    voltage: NDArray[np.floating]     # |V_tilde| (non-dimensional voltage)
    power: NDArray[np.floating]       # P = |V|^2 * epsilon
    transmission_dB: NDArray[np.floating]  # 20*log10(|U_N/U_0|)


@dataclass(frozen=True)
class ModeShapeResult:
    """Displacement pattern at a specific frequency."""

    omega: float
    displacements: NDArray[np.complexfloating]  # complex amplitudes U_i
    energy_per_mass: NDArray[np.floating]  # energy at each mass
    eta: float  # energy concentration ratio E_1 / E_total


@dataclass(frozen=True)
class HarvestingMetrics:
    """Key performance metrics for TR harvesting."""

    omega_tr: float           # TR frequency (non-dim)
    omega_pb1: float          # first passband peak frequency
    power_tr: float           # power at TR
    power_pb1: float          # power at PB1
    pef: float                # Power Enhancement Factor
    voltage_tr: float         # voltage at TR
    voltage_pb1: float        # voltage at PB1
    current_tr: float         # surrogate resistive current at TR
    current_pb1: float        # surrogate resistive current at PB1
    rectified_current_tr: float   # rectified-average current at TR
    rectified_current_pb1: float  # rectified-average current at PB1
    transmission_tr_dB: float # transmission at TR (dB)
    eta_tr: float             # energy concentration at TR


def build_forced_response_matrix(
    alpha: float,
    beta: float,
    delta: float,
    n_cells: int,
    omega: float,
    zeta: float,
    kappa_sq: float,
    epsilon: float,
    gamma: float = 1.0,
) -> tuple[NDArray[np.complexfloating], NDArray[np.complexfloating]]:
    """Build the augmented system matrix for forced response with piezo coupling.

    The piezoelectric port is across the (1-2) interface.
    Excitation: fixed-wall displacement U_0 applied via k_b spring to mass 1.

    Following MATLAB Lattice_B_new_6.m but with Paper 1 notation:
        alpha = m_b/m_a, beta = k_b/k_a, delta = m_{a+}/m_a
        mu = sqrt(beta/alpha) = omega_b * sqrt(m_a/k_a)
        kappa^2 = theta^2/(k_b*C_p)
        epsilon = 1/(R*C_p*omega_b)
        zeta = c_a/(2*sqrt(k_a*m_a))
        gamma = c_b/c_a (damping ratio between the two spring types)

    Parameters
    ----------
    alpha, beta, delta : float
        Chain parameters.
    n_cells : int
        Number of unit cells.
    omega : float
        Non-dimensional frequency Omega.
    zeta : float
        Damping ratio based on c_a.
    kappa_sq : float
        Electromechanical coupling factor kappa^2.
    epsilon : float
        Electrical damping ratio.
    gamma : float
        Ratio c_b/c_a of the two damping coefficients. Default 1.0.

    Returns
    -------
    A : ndarray, shape (2*n_cells, 2*n_cells)
        System matrix.
    b : ndarray, shape (2*n_cells,)
        Right-hand side (excitation from wall).
    """
    N = 2 * n_cells
    mu = np.sqrt(beta / alpha)
    j = 1j
    A = np.zeros((N, N), dtype=complex)
    b = np.zeros(N, dtype=complex)
    gamma_damp = gamma  # c_b/c_a ratio, independent from zeta

    # CRITICAL: Parameter basis conversion.
    # Our API uses omega_b = sqrt(k_b/m_b) as reference frequency:
    #   kappa_sq = theta^2 / (k_b * Cp)
    #   epsilon  = 1 / (R * Cp * omega_b)
    #
    # But the MATLAB matrix (Lattice_B_new_6.m) uses w_a = sqrt(k_a/m_a):
    #   k_e^2 = theta^2 / (k_a * Cp)
    #   eps    = 1 / (R * Cp * w_a)
    #
    # Conversion: mu = omega_b / w_a = sqrt(beta/alpha), so:
    #   k_e^2 = kappa_sq * beta    (since k_a = k_b/beta)
    #   eps   = epsilon * mu       (since w_a = omega_b/mu)
    k_e_sq = kappa_sq * beta
    eps = epsilon * mu

    # === Follow MATLAB Lattice_B_new_6.m execution order EXACTLY ===
    # MATLAB sets internal rows FIRST (loop), then overwrites rows 1,2 with
    # piezo coupling, then sets the last boundary row.

    # Step 1: Internal rows (MATLAB loop: for i = 1:(n-1))
    # MATLAB 1-indexed: row1 = 2*i, row2 = 2*i+1
    # Python 0-indexed: r1 = 2*i-1, r2 = 2*i
    for i in range(1, n_cells):
        r1 = 2 * i - 1  # 0-indexed row for m_b
        r2 = 2 * i      # 0-indexed row for m_a

        # MATLAB: A(row1, 2*i) = ..., A(row1, 2*i+1) = ..., A(row1, 2*i-1) = ...
        # 0-indexed: A[r1, 2*i-1], A[r1, 2*i], A[r1, 2*i-2]
        A[r1, 2*i - 1] = (
            1 + beta - alpha * mu**2 * omega**2
            + 2 * j * mu * omega * zeta
            + 2 * j * mu * omega * gamma_damp * zeta
        )
        A[r1, 2*i] = -(beta + 2 * j * mu * omega * gamma_damp * zeta)
        A[r1, 2*i - 2] = -(1 + 2 * j * mu * omega * zeta)

        # MATLAB: A(row2, 2*i+1) = ..., A(row2, 2*i) = ..., A(row2, 2*i+2) = ...
        # 0-indexed: A[r2, 2*i], A[r2, 2*i-1], A[r2, 2*i+1]
        A[r2, 2*i] = (
            1 + beta - mu**2 * omega**2
            + 2 * j * mu * omega * zeta
            + 2 * j * mu * omega * gamma_damp * zeta
        )
        A[r2, 2*i - 1] = -(beta + 2 * j * mu * omega * gamma_damp * zeta)
        if 2*i + 1 < N:
            A[r2, 2*i + 1] = -(1 + 2 * j * mu * omega * zeta)

    # Step 2: Overwrite Row 1 (0-indexed row 0) with piezo coupling
    A[0, 0] = (
        -j * delta * mu**3 * omega**3
        - (2 * (1 + gamma_damp) * zeta + delta * eps) * mu**2 * omega**2
        + (1 + beta - k_e_sq + 2 * zeta * (1 + gamma_damp) * eps) * j * mu * omega
        + (1 + beta) * eps
    )
    A[0, 1] = (
        2 * zeta * mu**2 * omega**2
        - (1 - k_e_sq + 2 * zeta * eps) * j * mu * omega
        - eps
    )

    # RHS
    U0 = 1.0
    b[0] = (
        -2 * zeta * gamma_damp * mu**2 * omega**2
        + (beta + 2 * zeta * gamma_damp * eps) * j * mu * omega
        + beta * eps
    ) * U0

    # Step 3: Overwrite Row 2 (0-indexed row 1) with piezo coupling
    A[1, 0] = (
        -j * delta * mu**3 * omega**3
        - 2 * (1 + gamma_damp) * zeta * mu**2 * omega**2
        + (1 + beta - k_e_sq + 2 * zeta * eps) * j * mu * omega
        + eps
    )
    A[1, 1] = (
        (2 * zeta + alpha * eps) * mu**2 * omega**2
        - (1 - k_e_sq + 2 * zeta * (1 + gamma_damp) * eps) * j * mu * omega
        - (1 + beta) * eps
    )
    if N > 2:
        A[1, 2] = 2 * zeta * gamma_damp * eps * j * mu * omega + beta * eps

    # Step 4: Last row (boundary, 0-indexed row N-1)
    A[N - 1, N - 1] = (
        2 * j * mu * omega * zeta
        + 2 * j * mu * omega * gamma_damp * zeta
        + 1 + beta - alpha * mu**2 * omega**2
    )
    A[N - 1, N - 2] = -(2 * j * mu * omega * zeta + 1)

    return A, b


def compute_voltage(
    alpha: float,
    beta: float,
    delta: float,
    omega: float,
    U: NDArray[np.complexfloating],
    zeta: float,
    kappa_sq: float,
    epsilon: float,
    U0: float = 1.0,
) -> complex:
    """Compute the non-dimensional voltage from displacement solution.

    From Paper 1 Eq. (12):
        V_tilde = -i*Omega/(i*Omega + epsilon) * (U_{a,1} - U_{b,2})

    But with the full coupling model from voltage_dimeless.m lines 45-51.
    """
    mu = np.sqrt(beta / alpha)
    j = 1j

    A_n = (
        -j * mu**3 * omega**3 * delta / epsilon
        - mu**2 * omega**2 * (2 * zeta * (1 + zeta)) / epsilon
        + j * mu * omega * (1 + beta - kappa_sq) / epsilon
    )
    A_n1 = -(
        -mu**2 * omega**2 * 2 * zeta / epsilon
        + j * mu * omega * (1 - kappa_sq) / epsilon
    )
    A_nm1 = -(
        -mu**2 * omega**2 * 2 * zeta * zeta / epsilon
        + j * mu * omega * beta / epsilon
    )

    V = (A_n * U[0] + A_n1 * U[1] + A_nm1 * U0) / U0
    return V


def frequency_sweep(
    alpha: float,
    beta: float,
    delta: float,
    n_cells: int,
    kappa_sq: float,
    epsilon: float,
    zeta: float = 0.003,
    gamma: float = 1.0,
    omega_range: NDArray[np.floating] | None = None,
    n_points: int = 10000,
    excitation_type: str = "acceleration",
    excitation_amplitude: float = 1.0,
) -> ForcedResponseResult:
    """Perform a frequency sweep computing voltage, power, and transmission.

    Parameters
    ----------
    alpha, beta, delta : float
        Chain parameters.
    n_cells : int
        Number of unit cells.
    kappa_sq : float
        Coupling factor kappa^2 = theta^2 / (k_b * C_p).
    epsilon : float
        Electrical damping ratio = 1 / (R * C_p * omega_b).
    zeta : float
        Mechanical damping ratio.
    gamma : float
        Damping ratio c_b/c_a.
    omega_range : ndarray, optional
        Frequency array. If None, uses linspace(0.01, pi, n_points).
    n_points : int
        Number of frequency points if omega_range not given.
    excitation_type : str
        "displacement" for fixed displacement U0 (MATLAB default),
        "acceleration" for fixed base acceleration a0 (standard VEH).
        With acceleration excitation, U0(Omega) = a0 / (mu^2 * Omega^2).
    excitation_amplitude : float
        Amplitude of excitation (U0 for displacement, a0 for acceleration).

    Returns
    -------
    ForcedResponseResult
    """
    if omega_range is None:
        omega_range = np.linspace(0.01, np.pi, n_points)

    N = 2 * n_cells
    mu = np.sqrt(beta / alpha)

    voltage = np.zeros(len(omega_range))
    power = np.zeros(len(omega_range))
    transmission_dB = np.zeros(len(omega_range))

    for k, omega in enumerate(omega_range):
        if omega < 1e-10:
            continue

        # Build matrix with U0=1 (unit excitation)
        A, b_vec = build_forced_response_matrix(
            alpha, beta, delta, n_cells, omega, zeta, kappa_sq, epsilon, gamma
        )

        # Determine actual U0 based on excitation type
        if excitation_type == "acceleration":
            # Fixed base acceleration a0: non-dim acceleration = mu^2 * Omega^2 * U0
            # So U0 = a0 / (mu^2 * Omega^2)
            U0 = excitation_amplitude / (mu**2 * omega**2)
        else:  # "displacement"
            U0 = excitation_amplitude

        # Scale b vector by actual U0 (matrix was built with U0=1)
        b_vec = b_vec * U0

        try:
            # Use lstsq to handle near-singular matrices at resonances
            U, residuals, rank, sv = np.linalg.lstsq(A, b_vec, rcond=None)
        except np.linalg.LinAlgError:
            continue

        # Voltage: use the full coupled formula from voltage_dimeless.m lines 45-51
        # This is more accurate than the simplified Paper 1 Eq. 12
        j = 1j
        mu_val = np.sqrt(beta / alpha)
        # Convert to MATLAB basis for voltage formula
        k_e_sq_v = kappa_sq * beta
        eps_v = epsilon * mu_val

        A_n = (-j * mu_val**3 * omega**3 * delta / eps_v
               - mu_val**2 * omega**2 * (2 * zeta * (1 + gamma)) / eps_v
               + j * mu_val * omega * (1 + beta - k_e_sq_v) / eps_v)
        A_n1 = -(-mu_val**2 * omega**2 * 2 * zeta / eps_v
                 + j * mu_val * omega * (1 - k_e_sq_v) / eps_v)
        A_nm1 = -(-mu_val**2 * omega**2 * 2 * gamma * zeta / eps_v
                  + j * mu_val * omega * beta / eps_v)

        v_full = (A_n * U[0] + A_n1 * U[1] + A_nm1 * U0) / U0
        voltage[k] = np.abs(v_full)

        # Power: P = |V|^2 * epsilon (non-dimensional)
        power[k] = voltage[k] ** 2 * epsilon

        # Transmission: |U_last / U_0|
        trans = np.abs(U[N - 1]) / max(U0, 1e-30)
        transmission_dB[k] = 20 * np.log10(max(trans, 1e-30))

    return ForcedResponseResult(
        omega=omega_range,
        voltage=voltage,
        power=power,
        transmission_dB=transmission_dB,
    )


def compute_mode_shape_energy(
    alpha: float,
    beta: float,
    delta: float,
    n_cells: int,
    omega: float,
    kappa_sq: float,
    epsilon: float,
    zeta: float = 0.003,
    gamma: float = 1.0,
) -> ModeShapeResult:
    """Compute mode shape and energy distribution at a given frequency.

    Energy follows MATLAB Energy_calculate1.m.

    Parameters
    ----------
    alpha, beta, delta, n_cells : float/int
        Chain parameters.
    omega : float
        Non-dimensional frequency.
    kappa_sq, epsilon, zeta : float
        Coupling and damping parameters.

    Returns
    -------
    ModeShapeResult
    """
    N = 2 * n_cells
    mu = np.sqrt(beta / alpha)
    U0 = 1.0

    A, b_vec = build_forced_response_matrix(
        alpha, beta, delta, n_cells, omega, zeta, kappa_sq, epsilon, gamma
    )
    # Use lstsq to handle near-singular matrices at/near resonances
    U, _, _, _ = np.linalg.lstsq(A, b_vec, rcond=None)

    # Energy per mass (cycle-averaged KE + PE)
    # Following Energy_calculate1.m
    E = np.zeros(N)
    for i in range(n_cells):
        ia = 2 * i      # m_a (or m_{a+} for i=0)
        ib = 2 * i + 1  # m_b

        if i == 0:
            # Boundary cell
            mass_a_factor = delta
            E[ia] = 0.5 * mass_a_factor * mu**2 * omega**2 * np.abs(U[ia])**2 \
                   + 0.5 * beta * np.abs(U[ia] - U0)**2
            E[ib] = 0.5 * alpha * mu**2 * omega**2 * np.abs(U[ib])**2 \
                   + 0.5 * np.abs(U[ib] - U[ia])**2
        elif i == n_cells - 1:
            # Last cell
            E[ia] = 0.5 * mu**2 * omega**2 * np.abs(U[ia])**2 \
                   + 0.5 * beta * np.abs(U[ia] - U[ia - 1])**2
            E[ib] = 0.5 * alpha * mu**2 * omega**2 * np.abs(U[ib])**2 \
                   + 0.5 * np.abs(U[ib] - U[ia])**2
        else:
            E[ia] = 0.5 * mu**2 * omega**2 * np.abs(U[ia])**2 \
                   + 0.5 * beta * np.abs(U[ia] - U[ia - 1])**2
            E[ib] = 0.5 * alpha * mu**2 * omega**2 * np.abs(U[ib])**2 \
                   + 0.5 * np.abs(U[ib] - U[ia])**2

    total_E = np.sum(E)
    # eta = energy in first cell / total energy
    E_first_cell = E[0] + E[1]
    eta = E_first_cell / total_E if total_E > 0 else 0.0

    return ModeShapeResult(
        omega=omega,
        displacements=U,
        energy_per_mass=E,
        eta=float(eta),
    )


def compute_harvesting_metrics(
    alpha: float,
    beta: float,
    delta: float,
    n_cells: int,
    kappa_sq: float,
    epsilon: float,
    zeta: float = 0.003,
    gamma: float = 1.0,
    n_points: int = 10000,
    excitation_type: str = "acceleration",
    excitation_amplitude: float = 1.0,
) -> HarvestingMetrics:
    """Compute all key harvesting metrics: PEF, eta, transmission at TR.

    Parameters
    ----------
    alpha, beta, delta, n_cells : float/int
        Chain parameters.
    kappa_sq, epsilon, zeta : float
        Electromechanical parameters.
    n_points : int
        Frequency resolution.

    Returns
    -------
    HarvestingMetrics
    """
    # Get bandgap and eigenfrequencies
    chain = analyze_finite_chain(alpha, beta, delta, n_cells)

    # Determine frequency range covering both bandgap and first passband
    if len(chain.eigenfrequencies) == 0:
        raise ValueError("No eigenfrequencies found")

    omega_max = max(chain.eigenfrequencies[-1] * 1.1, chain.bandgap.upper * 1.2) \
        if chain.bandgap.exists else chain.eigenfrequencies[-1] * 1.2
    omega_range = np.linspace(0.01, omega_max, n_points)

    # Frequency sweep
    resp = frequency_sweep(
        alpha, beta, delta, n_cells,
        kappa_sq, epsilon, zeta, gamma,
        omega_range=omega_range,
        excitation_type=excitation_type,
        excitation_amplitude=excitation_amplitude,
    )

    bandgap = chain.bandgap

    # Find TR peak: max power inside bandgap
    if bandgap.exists:
        gap_mask = (resp.omega >= bandgap.lower) & (resp.omega <= bandgap.upper)
        if np.any(gap_mask):
            gap_power = resp.power * gap_mask
            i_tr = np.argmax(gap_power)
            omega_tr = resp.omega[i_tr]
            power_tr = resp.power[i_tr]
            voltage_tr = resp.voltage[i_tr]
            trans_tr = resp.transmission_dB[i_tr]
        else:
            omega_tr = power_tr = voltage_tr = 0.0
            trans_tr = 0.0
    else:
        omega_tr = power_tr = voltage_tr = 0.0
        trans_tr = 0.0

    # Find PB1 peak: max power below bandgap lower edge
    if bandgap.exists:
        pb_mask = resp.omega < bandgap.lower
    else:
        pb_mask = np.ones(len(resp.omega), dtype=bool)

    if np.any(pb_mask):
        pb_power = resp.power * pb_mask
        i_pb1 = np.argmax(pb_power)
        omega_pb1 = resp.omega[i_pb1]
        power_pb1 = resp.power[i_pb1]
        voltage_pb1 = resp.voltage[i_pb1]
    else:
        omega_pb1 = power_pb1 = voltage_pb1 = 0.0

    # PEF
    pef = power_tr / power_pb1 if power_pb1 > 0 else 0.0

    # Surrogate current for the non-dimensional L1 model.
    # Since P = |V|^2 * epsilon in the current normalization,
    # the corresponding resistive current surrogate is I ~= |V| * epsilon.
    current_tr = voltage_tr * epsilon
    current_pb1 = voltage_pb1 * epsilon
    rectified_current_tr = current_tr * (2.0 / np.pi)
    rectified_current_pb1 = current_pb1 * (2.0 / np.pi)

    # Energy concentration at TR
    if omega_tr > 0:
        mode = compute_mode_shape_energy(
            alpha, beta, delta, n_cells, omega_tr,
            kappa_sq, epsilon, zeta, gamma,
        )
        eta_tr = mode.eta
    else:
        eta_tr = 0.0

    return HarvestingMetrics(
        omega_tr=float(omega_tr),
        omega_pb1=float(omega_pb1),
        power_tr=float(power_tr),
        power_pb1=float(power_pb1),
        pef=float(pef),
        voltage_tr=float(voltage_tr),
        voltage_pb1=float(voltage_pb1),
        current_tr=float(current_tr),
        current_pb1=float(current_pb1),
        rectified_current_tr=float(rectified_current_tr),
        rectified_current_pb1=float(rectified_current_pb1),
        transmission_tr_dB=float(trans_tr),
        eta_tr=float(eta_tr),
    )
