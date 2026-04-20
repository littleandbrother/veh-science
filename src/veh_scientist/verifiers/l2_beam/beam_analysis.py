"""
Step 1c-1d: Finite beam FEM analysis with piezoelectric coupling.

Reference: new_bc.m (complete FEM implementation).

This implements the full 1D Timoshenko FEM model:
  - Bilayer periodic beam with N cells
  - Piezoelectric patch on first cell
  - Base excitation (left-clamped) / right-free
  - Rayleigh damping + dielectric loss
  - Frequency sweep: voltage, power, transmission
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix, spdiags, eye as speye
from scipy.sparse.linalg import spsolve

from .tmm import (
    MaterialProperties,
    BeamGeometry,
    PiezoProperties,
    timoshenko_element_matrices,
)
from .dispersion import compute_beam_bandgaps, BeamBandgapResult


@dataclass(frozen=True)
class BeamForcedResponseResult:
    """Result of a frequency sweep on the finite beam."""

    f: NDArray[np.floating]                # frequency array [Hz]
    voltage: NDArray[np.floating]          # |V| [V]
    power: NDArray[np.floating]            # power [W]
    w_left: NDArray[np.floating]           # |w_L| [m]
    w_right: NDArray[np.floating]          # |w_R| [m]
    transmission_dB: NDArray[np.floating]  # 20*log10(|w_R/w_L|) [dB]


@dataclass(frozen=True)
class BeamHarvestingMetrics:
    """Key performance metrics for beam TR harvesting."""

    f_tr: float              # TR frequency [Hz]
    f_pb1: float             # first passband peak frequency [Hz]
    power_tr: float          # power at TR [W]
    power_pb1: float         # power at PB1 [W]
    pef: float               # Power Enhancement Factor
    voltage_tr: float        # voltage at TR [V]
    voltage_pb1: float       # voltage at PB1 [V]
    current_tr: float        # peak current at TR [A]
    current_pb1: float       # peak current at PB1 [A]
    rectified_current_tr: float   # rectified-average current at TR [A]
    rectified_current_pb1: float  # rectified-average current at PB1 [A]
    transmission_tr_dB: float     # transmission at TR [dB]
    eta_tr: float                 # first-cell energy localization ratio at TR [-]


@dataclass(frozen=True)
class _BeamSolveResult:
    """Single-frequency solution of the coupled beam-electrical system."""

    u_full: NDArray[np.complexfloating]
    voltage: float
    power: float
    w_left: float
    w_right: float
    transmission_dB: float


def _build_fem_system(
    mat_A: MaterialProperties,
    mat_B: MaterialProperties,
    geom: BeamGeometry,
    piezo: PiezoProperties,
    L_A: float,
    L_B: float,
    n_cells: int,
    boundary_mass_factor: float = 1.0,
    nel_A: int = 8,
    nel_B: int = 2,
) -> dict:
    """Assemble global K, M matrices and piezo coupling vector.

    Follows new_bc.m Part 2 exactly.

    Returns a dict with all assembled quantities.
    """
    a = L_A + L_B
    nel_cell = nel_A + nel_B
    Ne = n_cells * nel_cell
    Nn = Ne + 1
    Nd = 2 * Nn

    id_w = lambda n: 2 * n        # 0-indexed: node n → DOF 2*n (w)
    id_phi = lambda n: 2 * n + 1  # 0-indexed: node n → DOF 2*n+1 (phi)

    # Node positions
    x_node = np.linspace(0, n_cells * a, Nn)

    # Global matrices
    K = np.zeros((Nd, Nd))
    M = np.zeros((Nd, Nd))
    Kme = np.zeros(Nd)  # piezo coupling vector

    # Store element matrices for energy calculation
    Ke_list = []
    Me_list = []
    dof_list = []

    pz_x0 = 0.0
    pz_x1 = a  # piezo covers first cell

    for e in range(Ne):
        n1, n2 = e, e + 1
        Le = x_node[n2] - x_node[n1]
        xmid = 0.5 * (x_node[n1] + x_node[n2])
        x_in_cell = xmid % a

        # Material selection
        if x_in_cell < L_A:
            E, G, rho = mat_A.E, mat_A.G, mat_A.rho
        else:
            E, G, rho = mat_B.E, mat_B.G, mat_B.rho

        # Check if inside piezo patch
        in_patch = (xmid >= pz_x0) and (xmid <= pz_x1)

        if in_patch:
            b = geom.b
            hb = geom.h
            hp = piezo.h
            Eb = E
            Ep = piezo.E
            Ab = b * hb
            Ap = b * hp
            Ib = b * hb**3 / 12
            Ip = b * hp**3 / 12
            z_p = hb / 2 + hp / 2

            ybar = (Eb * Ab * 0 + Ep * Ap * z_p) / (Eb * Ab + Ep * Ap)
            EIeq = Eb * (Ib + Ab * (0 - ybar)**2) + Ep * (Ip + Ap * (z_p - ybar)**2)
            Ieff = EIeq / Eb
            rho_eff = (rho * Ab + piezo.rho * Ap) / Ab
        else:
            Ieff = geom.I
            rho_eff = rho

        Ke, Me_elem = timoshenko_element_matrices(E, G, rho_eff, geom.A, Ieff, Le, geom.ks)

        dofs = [id_w(n1), id_phi(n1), id_w(n2), id_phi(n2)]

        for ii in range(4):
            for jj in range(4):
                K[dofs[ii], dofs[jj]] += Ke[ii, jj]
                M[dofs[ii], dofs[jj]] += Me_elem[ii, jj]

        if in_patch:
            z_p_local = geom.h / 2 + piezo.h / 2
            theta_line = piezo.E * piezo.d31 * geom.b * (z_p_local - ybar)
            theta_e = theta_line * Le
            Kme_e = theta_e * np.array([0, -1, 0, 1])
            for ii in range(4):
                Kme[dofs[ii]] += Kme_e[ii]

        Ke_list.append(Ke)
        Me_list.append(Me_elem)
        dof_list.append(dofs)

    # Minimal TR proxy in the beam model:
    # apply the chain boundary-mass asymmetry δ to the first free A/B interface node,
    # rather than to the clamped boundary itself. This produces a materially stronger
    # finite-boundary perturbation than smearing density over the first A layer.
    boundary_node = nel_A
    boundary_w_dof = id_w(boundary_node)
    M[boundary_w_dof, boundary_w_dof] *= boundary_mass_factor

    # Boundary conditions: left clamp with prescribed base motion
    # (w(0)=u_base(omega), phi(0)=0).
    clamp_dofs = [id_w(0), id_phi(0)]
    unknown = [d for d in range(Nd) if d not in clamp_dofs]

    # Partition
    unk = np.array(unknown)
    clp = np.array(clamp_dofs)

    Kuu = K[np.ix_(unk, unk)]
    Kux = K[np.ix_(unk, clp)]
    Muu = M[np.ix_(unk, unk)]
    Mux = M[np.ix_(unk, clp)]
    Kme_u = Kme[unk]
    Kme_x = Kme[clp]

    # Piezo capacitance
    Cp = piezo.eps33T * geom.b * a / piezo.h

    return {
        "K": K, "M": M, "Kme": Kme,
        "Kuu": Kuu, "Kux": Kux, "Muu": Muu, "Mux": Mux,
        "Kme_u": Kme_u, "Kme_x": Kme_x,
        "Cp": Cp, "Nd": Nd, "Nn": Nn, "Ne": Ne,
        "x_node": x_node, "unknown": unk, "clamp_dofs": clp,
        "id_w": id_w, "id_phi": id_phi,
        "Ke_list": Ke_list, "Me_list": Me_list, "dof_list": dof_list,
        "nel_cell": nel_cell,
    }


def _solve_frequency_response(
    sys: dict,
    *,
    R_load: float,
    frequency_hz: float,
    excitation_type: str,
    excitation_amplitude: float,
    alpha_ray: float,
    beta_ray: float,
    tan_delta: float,
) -> _BeamSolveResult | None:
    """Solve the coupled beam-electrical system at a single frequency."""
    w = 2 * np.pi * frequency_hz
    if w < 1e-10:
        return None

    Kuu = sys["Kuu"]
    Kux = sys["Kux"]
    Muu = sys["Muu"]
    Mux = sys["Mux"]
    Kme_u = sys["Kme_u"]
    Kme_x = sys["Kme_x"]
    Cp = sys["Cp"]
    Nd = sys["Nd"]
    Nn = sys["Nn"]
    unk = sys["unknown"]
    id_w = sys["id_w"]
    id_phi = sys["id_phi"]

    if excitation_type == "acceleration":
        u0_actual = excitation_amplitude / w**2
    else:
        u0_actual = excitation_amplitude

    uxval = np.array([u0_actual, 0.0])
    Y_shunt = 1.0 / R_load

    Cuu = alpha_ray * Muu + beta_ray * Kuu
    Cux = alpha_ray * Mux + beta_ray * Kux
    Kdyn_uu = Kuu + 1j * w * Cuu - w**2 * Muu
    Kdyn_ux = Kux + 1j * w * Cux - w**2 * Mux

    Cp_complex = Cp * (1 - 1j * tan_delta) if tan_delta > 0 else Cp
    Kee = 1j * w * Cp_complex + Y_shunt

    n_unk = len(unk)
    Kc = np.zeros((n_unk + 1, n_unk + 1), dtype=complex)
    Kc[:n_unk, :n_unk] = Kdyn_uu
    Kc[:n_unk, n_unk] = Kme_u
    Kc[n_unk, :n_unk] = 1j * w * Kme_u
    Kc[n_unk, n_unk] = Kee

    Rc = np.zeros(n_unk + 1, dtype=complex)
    Rc[:n_unk] = -Kdyn_ux @ uxval
    Rc[n_unk] = -1j * w * (Kme_x @ uxval)

    col_norms = np.sqrt(np.sum(np.abs(Kc) ** 2, axis=0))
    col_norms[col_norms == 0] = 1
    Dcol = np.diag(1.0 / col_norms)
    Kcs = Kc @ Dcol

    tau = 1e-8 * np.linalg.norm(Kcs, "fro")
    normal_matrix = Kcs.conj().T @ Kcs + tau**2 * np.eye(Kcs.shape[1])
    normal_rhs = Kcs.conj().T @ Rc
    try:
        xs = np.linalg.solve(normal_matrix, normal_rhs)
    except np.linalg.LinAlgError:
        try:
            xs = np.linalg.lstsq(normal_matrix, normal_rhs, rcond=None)[0]
        except np.linalg.LinAlgError:
            return None

    Uc = Dcol @ xs
    uf = Uc[:-1]
    Vp = Uc[-1]

    u_full = np.zeros(Nd, dtype=complex)
    u_full[unk] = uf
    u_full[id_w(0)] = uxval[0]
    u_full[id_phi(0)] = uxval[1]

    w_left = float(np.abs(u_full[id_w(0)]))
    w_right = float(np.abs(u_full[id_w(Nn - 1)]))
    transmission_dB = float(
        20 * np.log10(np.maximum(w_right, 1e-30) / np.maximum(w_left, 1e-30))
    )
    voltage = float(np.abs(Vp))

    return _BeamSolveResult(
        u_full=u_full,
        voltage=voltage,
        power=float(voltage**2 / (2.0 * R_load)),
        w_left=w_left,
        w_right=w_right,
        transmission_dB=transmission_dB,
    )


def _compute_localization_ratio(
    u_full: NDArray[np.complexfloating],
    angular_frequency: float,
    sys: dict,
) -> float:
    """Compute eta = E(first cell) / E(total) from the solved beam state."""
    etot = 0.0
    efirst = 0.0
    first_cell_elements = sys["nel_cell"]

    for idx, (Ke, Me_elem, dofs) in enumerate(
        zip(sys["Ke_list"], sys["Me_list"], sys["dof_list"], strict=False)
    ):
        ue = u_full[dofs]
        e_kin = 0.25 * angular_frequency**2 * np.real(ue.conj().T @ Me_elem @ ue)
        e_str = 0.25 * np.real(ue.conj().T @ Ke @ ue)
        e_elem = max(float(e_kin + e_str), 0.0)
        etot += e_elem
        if idx < first_cell_elements:
            efirst += e_elem

    if etot <= 0:
        return 0.0
    return efirst / etot


def beam_frequency_sweep(
    mat_A: MaterialProperties,
    mat_B: MaterialProperties,
    geom: BeamGeometry,
    piezo: PiezoProperties,
    L_A: float,
    L_B: float,
    n_cells: int,
    R_load: float,
    f_array: NDArray[np.floating] | None = None,
    f_min: float = 0.0,
    f_max: float = 10000.0,
    n_points: int = 1000,
    excitation_type: str = "acceleration",
    excitation_amplitude: float = 9.81,
    zeta1: float = 0.005,
    zeta2: float = 0.008,
    tan_delta: float = 0.02,
    boundary_mass_factor: float = 1.0,
    nel_A: int = 8,
    nel_B: int = 2,
) -> BeamForcedResponseResult:
    """Full frequency sweep for a periodic Timoshenko beam with piezo.

    Follows new_bc.m Parts 2-4 exactly.

    Parameters
    ----------
    mat_A, mat_B : MaterialProperties
        Materials for layers A and B.
    geom : BeamGeometry
        Cross-section geometry.
    piezo : PiezoProperties
        Piezoelectric patch properties.
    L_A, L_B : float
        Layer lengths [m].
    n_cells : int
        Number of unit cells.
    R_load : float
        Load resistance [Ohm].
    f_array : ndarray, optional
        Frequency array [Hz].
    excitation_type : str
        "acceleration" (default) or "displacement".
    excitation_amplitude : float
        Fixed base acceleration a0 [m/s^2] for acceleration excitation,
        or prescribed base displacement u0 [m] for displacement excitation.
    zeta1, zeta2 : float
        Target modal damping ratios.
    tan_delta : float
        Dielectric loss tangent.

    Returns
    -------
    BeamForcedResponseResult
    """
    if f_array is None:
        f_array = np.linspace(f_min, f_max, n_points)

    # Build FEM system
    sys = _build_fem_system(
        mat_A,
        mat_B,
        geom,
        piezo,
        L_A,
        L_B,
        n_cells,
        boundary_mass_factor=boundary_mass_factor,
        nel_A=nel_A,
        nel_B=nel_B,
    )

    Nn = sys["Nn"]

    # Rayleigh damping coefficients
    f1_d = 0.25 * f_max
    f2_d = 0.80 * f_max
    w1_d = 2 * np.pi * f1_d
    w2_d = 2 * np.pi * f2_d
    Aab = np.array([[1/(2*w1_d), w1_d/2], [1/(2*w2_d), w2_d/2]])
    ab = np.linalg.solve(Aab, np.array([zeta1, zeta2]))
    alpha_ray = max(ab[0], 0)
    beta_ray = max(ab[1], 0)

    Nf = len(f_array)

    voltage_out = np.zeros(Nf)
    power_out = np.zeros(Nf)
    wL_out = np.zeros(Nf)
    wR_out = np.zeros(Nf)

    for k in range(Nf):
        solved = _solve_frequency_response(
            sys,
            R_load=R_load,
            frequency_hz=float(f_array[k]),
            excitation_type=excitation_type,
            excitation_amplitude=excitation_amplitude,
            alpha_ray=alpha_ray,
            beta_ray=beta_ray,
            tan_delta=tan_delta,
        )
        if solved is None:
            continue

        voltage_out[k] = solved.voltage
        power_out[k] = solved.power
        wL_out[k] = solved.w_left
        wR_out[k] = solved.w_right

    # Transmission
    transmission_dB = 20 * np.log10(
        np.maximum(wR_out, 1e-30) / np.maximum(wL_out, 1e-30)
    )

    return BeamForcedResponseResult(
        f=f_array,
        voltage=voltage_out,
        power=power_out,
        w_left=wL_out,
        w_right=wR_out,
        transmission_dB=transmission_dB,
    )


def compute_beam_harvesting_metrics(
    mat_A: MaterialProperties,
    mat_B: MaterialProperties,
    geom: BeamGeometry,
    piezo: PiezoProperties,
    L_A: float,
    L_B: float,
    n_cells: int,
    R_load: float,
    f_min: float = 0.0,
    f_max: float = 10000.0,
    n_points_bandgap: int = 600,
    n_points_sweep: int = 1000,
    target_band: tuple[float, float] | None = None,
    excitation_type: str = "acceleration",
    excitation_amplitude: float = 9.81,
    boundary_mass_factor: float = 1.0,
    **sweep_kwargs,
) -> BeamHarvestingMetrics:
    """Compute TR harvesting metrics for a periodic beam.

    1. Find bandgaps via TMM
    2. Do frequency sweep via FEM
    3. Find TR peak (max power in bandgap) and PB1 peak
    4. Compute PEF

    Returns
    -------
    BeamHarvestingMetrics
    """
    # Step 1: Bandgaps
    bg = compute_beam_bandgaps(mat_A, mat_B, geom, L_A, L_B, f_min, f_max, n_points_bandgap)

    # Step 2: Frequency sweep
    f_array = np.linspace(f_min, f_max, n_points_sweep)
    resp = beam_frequency_sweep(
        mat_A, mat_B, geom, piezo, L_A, L_B, n_cells, R_load,
        f_array=f_array,
        excitation_type=excitation_type,
        excitation_amplitude=excitation_amplitude,
        boundary_mass_factor=boundary_mass_factor,
        **sweep_kwargs,
    )

    # Step 3: Find TR and PB1 peaks
    selected_gaps = _select_relevant_gaps(bg.gaps, target_band)

    # TR: max power inside the selected bandgap(s)
    gap_mask = np.zeros(len(f_array), dtype=bool)
    for g_lo, g_hi in selected_gaps:
        gap_mask |= (f_array >= g_lo) & (f_array <= g_hi)

    if np.any(gap_mask):
        gap_power = resp.power * gap_mask
        i_tr = np.argmax(gap_power)
        f_tr = resp.f[i_tr]
        power_tr = resp.power[i_tr]
        voltage_tr = resp.voltage[i_tr]
        trans_tr = resp.transmission_dB[i_tr]
    else:
        f_tr = power_tr = voltage_tr = trans_tr = 0.0

    # PB1: max power below first bandgap
    if selected_gaps:
        pb_mask = f_array < selected_gaps[0][0]
    elif bg.gaps:
        pb_mask = f_array < bg.gaps[0][0]
    else:
        pb_mask = np.ones(len(f_array), dtype=bool)

    if np.any(pb_mask):
        pb_power = resp.power * pb_mask
        i_pb1 = np.argmax(pb_power)
        f_pb1 = resp.f[i_pb1]
        power_pb1 = resp.power[i_pb1]
        voltage_pb1 = resp.voltage[i_pb1]
    else:
        f_pb1 = power_pb1 = voltage_pb1 = 0.0

    pef = power_tr / power_pb1 if power_pb1 > 0 else 0.0
    current_tr = voltage_tr / R_load if R_load > 0 else 0.0
    current_pb1 = voltage_pb1 / R_load if R_load > 0 else 0.0
    rectified_current_tr = current_tr * (2.0 / np.pi)
    rectified_current_pb1 = current_pb1 * (2.0 / np.pi)
    eta_tr = 0.0

    if f_tr > 0:
        zeta1 = sweep_kwargs.get("zeta1", 0.005)
        zeta2 = sweep_kwargs.get("zeta2", 0.008)
        tan_delta = sweep_kwargs.get("tan_delta", 0.02)
        f1_d = 0.25 * f_max
        f2_d = 0.80 * f_max
        w1_d = 2 * np.pi * f1_d
        w2_d = 2 * np.pi * f2_d
        Aab = np.array([[1/(2*w1_d), w1_d/2], [1/(2*w2_d), w2_d/2]])
        ab = np.linalg.solve(Aab, np.array([zeta1, zeta2]))
        alpha_ray = max(ab[0], 0)
        beta_ray = max(ab[1], 0)
        tr_sys = _build_fem_system(
            mat_A,
            mat_B,
            geom,
            piezo,
            L_A,
            L_B,
            n_cells,
            boundary_mass_factor=boundary_mass_factor,
            nel_A=sweep_kwargs.get("nel_A", 8),
            nel_B=sweep_kwargs.get("nel_B", 2),
        )
        solved_tr = _solve_frequency_response(
            tr_sys,
            R_load=R_load,
            frequency_hz=float(f_tr),
            excitation_type=excitation_type,
            excitation_amplitude=excitation_amplitude,
            alpha_ray=alpha_ray,
            beta_ray=beta_ray,
            tan_delta=tan_delta,
        )
        if solved_tr is not None:
            eta_tr = _compute_localization_ratio(solved_tr.u_full, 2 * np.pi * f_tr, tr_sys)

    return BeamHarvestingMetrics(
        f_tr=float(f_tr),
        f_pb1=float(f_pb1),
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


def _select_relevant_gaps(
    gaps: list[tuple[float, float]],
    target_band: tuple[float, float] | None,
) -> list[tuple[float, float]]:
    """Prefer the bandgap(s) overlapping the task band, else use the global first gap."""
    if not gaps:
        return []
    if target_band is None:
        return [gaps[0]]

    band_lo, band_hi = target_band
    overlaps = [
        (g_lo, g_hi)
        for g_lo, g_hi in gaps
        if not (g_hi < band_lo or g_lo > band_hi)
    ]
    if overlaps:
        overlaps.sort(key=lambda gap: gap[0])
        return [overlaps[0]]
    return [gaps[0]]
