"""COMSOL mph wrapper for the continuous periodic piezo beam.

This module follows the local `comsol-mph-python-oracle` skill:
  - geometry before physics
  - base excitation via prescribed boundary displacement
  - physics-level `PiezoelectricMaterialModel`
  - `TerminalType = Circuit` with `Circuit + Resistor + ModelTerminalIV`
  - `InitializePiezoCoupling = 1`
  - study execution via `java.study(...).run()`
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
import time

import numpy as np


@dataclass(frozen=True)
class PeriodicBeamCOMSOLConfig:
    """Configuration for the periodic piezo beam COMSOL model."""

    n_cells: int = 5
    L_A: float = 0.08
    L_B: float = 0.02
    beam_width: float = 0.025
    beam_height: float = 0.005
    piezo_thickness: float = 0.0005

    E_A: float = 68.9e9
    nu_A: float = 0.33
    rho_A: float = 2700.0
    E_B: float = 2.4e9
    nu_B: float = 0.35
    rho_B: float = 1040.0

    piezo_E: float = 62.0e9
    piezo_nu: float = 0.30
    piezo_rho: float = 7500.0
    # Match the 1D Python/MATLAB beam model: d31-driven bending coupling and
    # scalar eps33T capacitance. Use a simplified stress-charge projection
    # rather than a full anisotropic PZT datasheet.
    piezo_e31: float = -16.988
    piezo_e33: float = 0.0
    piezo_e15: float = 0.0
    piezo_epsr_xy: float = 3400.0
    piezo_epsr_z: float = 3400.0

    load_resistance_ohm: float = 1.0e6
    a_exc: float = 9.81
    modal_damping: float = 0.0065
    dielectric_loss_tangent: float = 0.02

    f_min: float = 1.0
    f_max: float = 3000.0
    n_freq: int = 80
    n_eigs: int = 20


@dataclass
class _COMSOLSessionState:
    """Process-local COMSOL session with isolated runtime directories."""

    client: object
    server: object
    runtime_root: Path
    cores: int


_COMSOL_SESSION: _COMSOLSessionState | None = None


class PeriodicPiezoBeamCOMSOLOracle:
    """Thin lazy wrapper around a saved `.mph` periodic beam model."""

    def __init__(
        self,
        config: PeriodicBeamCOMSOLConfig,
        *,
        save_path: str | None = None,
        cores: int = 1,
    ):
        self.config = config
        self.save_path = save_path
        self.cores = cores

    def evaluate(self) -> dict:
        return build_and_run_periodic_beam(
            self.config,
            save_path=self.save_path,
            cores=self.cores,
        )


def build_and_run_periodic_beam(
    config: PeriodicBeamCOMSOLConfig,
    save_path: str | None = None,
    cores: int = 1,
) -> dict:
    """Build the COMSOL model, run eigenfrequency + frequency sweeps, and extract results."""
    client = _ensure_comsol_client(cores=cores)
    model = None
    try:
        model = client.create("periodic_piezo_beam")
        result = _build_and_solve(model, config)
        if save_path:
            model.save(save_path)
    finally:
        if model is not None:
            client.remove(model)

    return result


def _ensure_comsol_client(*, cores: int):
    """Start or reuse a process-local COMSOL client with isolated runtime state."""
    global _COMSOL_SESSION

    if _COMSOL_SESSION is not None:
        if _COMSOL_SESSION.cores != cores:
            raise RuntimeError(
                f"Existing COMSOL session uses { _COMSOL_SESSION.cores } core(s), "
                f"but {cores} core(s) were requested."
            )
        if _COMSOL_SESSION.server.running() and _COMSOL_SESSION.client.port:
            return _COMSOL_SESSION.client
        _cleanup_comsol_session()

    import mph

    runtime_root = Path(tempfile.mkdtemp(prefix="veh_comsol_"))
    server_args = _isolated_server_arguments(runtime_root)
    server = mph.Server(cores=cores, port=0, arguments=server_args)
    client = mph.Client(cores=cores, port=server.port)
    _COMSOL_SESSION = _COMSOLSessionState(
        client=client,
        server=server,
        runtime_root=runtime_root,
        cores=cores,
    )
    return client


def _isolated_server_arguments(runtime_root: Path) -> list[str]:
    """Direct COMSOL runtime state to a clean temporary workspace."""
    arguments: list[str] = []
    for name in ("configuration", "data", "tmpdir", "recoverydir"):
        path = runtime_root / name
        path.mkdir(parents=True, exist_ok=True)
        arguments.extend([f"-{name}", str(path)])
    return arguments


def _cleanup_comsol_session() -> None:
    """Release the process-local COMSOL session and remove temp directories."""
    global _COMSOL_SESSION

    session = _COMSOL_SESSION
    if session is None:
        return

    try:
        if getattr(session.client, "port", None):
            try:
                session.client.disconnect()
            except Exception:
                pass
        if session.server.running():
            try:
                session.server.stop()
            except Exception:
                pass
    finally:
        shutil.rmtree(session.runtime_root, ignore_errors=True)
        _COMSOL_SESSION = None


atexit.register(_cleanup_comsol_session)


def _build_and_solve(model, config: PeriodicBeamCOMSOLConfig) -> dict:
    java = model.java
    comp = java.component().create("comp1", True)
    geom = comp.geom().create("geom1", 3)
    a_cell = config.L_A + config.L_B

    p = java.param()
    p.set("L_A", f"{config.L_A}[m]")
    p.set("L_B", f"{config.L_B}[m]")
    p.set("a_cell", f"{a_cell}[m]")
    p.set("bw", f"{config.beam_width}[m]")
    p.set("hs", f"{config.beam_height}[m]")
    p.set("hp", f"{config.piezo_thickness}[m]")
    p.set("RL_ohm", f"{config.load_resistance_ohm}[ohm]")
    p.set("a_exc", f"{config.a_exc}[m/s^2]")
    p.set("zeta", str(config.modal_damping))
    p.set("eps_tand", str(config.dielectric_loss_tangent))
    p.set("loss_mult", "0")
    p.set("eps_loss_mult", "1")
    p.set("f_exc_hz", f"{0.5 * (config.f_min + config.f_max)}[Hz]")

    al_tags: list[str] = []
    ep_tags: list[str] = []
    x_cursor = 0.0
    for idx in range(config.n_cells):
        tag_a = f"blkA{idx + 1}"
        blk_a = geom.create(tag_a, "Block")
        blk_a.set("size", ["L_A", "bw", "hs"])
        blk_a.set("pos", [str(x_cursor), "0", "0"])
        blk_a.set("selresult", True)
        al_tags.append(tag_a)
        x_cursor += config.L_A

        tag_b = f"blkB{idx + 1}"
        blk_b = geom.create(tag_b, "Block")
        blk_b.set("size", ["L_B", "bw", "hs"])
        blk_b.set("pos", [str(x_cursor), "0", "0"])
        blk_b.set("selresult", True)
        ep_tags.append(tag_b)
        x_cursor += config.L_B

    blk_pzt = geom.create("blkPZT", "Block")
    blk_pzt.set("size", ["a_cell", "bw", "hp"])
    blk_pzt.set("pos", ["0", "0", "hs"])
    blk_pzt.set("selresult", True)
    geom.run("fin")

    al_domains = _selection_entities(comp, al_tags, 3)
    ep_domains = _selection_entities(comp, ep_tags, 3)
    pzt_domain = list(comp.selection("geom1_blkPZT_dom").entities(3))

    left_bnd = _box_bnd(comp, "sel_left", 0.0, 0.0, 0.0, config.beam_width, 0.0, config.beam_height + config.piezo_thickness)
    top_electrode = _box_bnd(comp, "sel_pzt_top", 0.0, a_cell, 0.0, config.beam_width, config.beam_height + config.piezo_thickness, config.beam_height + config.piezo_thickness)
    bottom_electrode = _box_bnd(comp, "sel_pzt_bottom", 0.0, a_cell, 0.0, config.beam_width, config.beam_height, config.beam_height)

    _assign_material(comp, "matA", "Aluminum", al_domains, config.E_A, config.nu_A, config.rho_A)
    _assign_material(comp, "matB", "Epoxy", ep_domains, config.E_B, config.nu_B, config.rho_B)
    _assign_material(comp, "matP", "PZT", pzt_domain, config.piezo_E, config.piezo_nu, config.piezo_rho)

    solid = comp.physics().create("solid", "SolidMechanics", "geom1")
    solid.selection().all()
    base_disp = solid.create("disp1", "Displacement2", 2)
    base_disp.selection().set(left_bnd)
    # Match the 1D beam boundary condition w(0)=u_base, phi(0)=0 by prescribing
    # the entire left composite cross-section as a rigid translated/clamped face.
    base_disp.set("Direction", ["prescribed", "prescribed", "prescribed"])
    base_disp.set("U0", ["0", "0", "0"])

    pzm = solid.create("pzm1", "PiezoelectricMaterialModel", 3)
    pzm.selection().set(pzt_domain)
    pzm.set("ConstitutiveRelation", "StressCharge")
    pzm.set("cE_mat", "userdef")
    pzm.set("eES_mat", "userdef")
    pzm.set("epsilonrS_mat", "userdef")
    pzm.set("cE", _scale_matrix_entries(_isotropic_stiffness_matrix(config.piezo_E, config.piezo_nu), "1+loss_mult"))
    pzm.set("eES", _column_major_ees(config.piezo_e31, config.piezo_e33, config.piezo_e15))
    pzm.set(
        "epsilonrS",
        [
            f"({config.piezo_epsr_xy})*(eps_loss_mult)", "0", "0",
            "0", f"({config.piezo_epsr_xy})*(eps_loss_mult)", "0",
            "0", "0", f"({config.piezo_epsr_z})*(eps_loss_mult)",
        ],
    )

    es = comp.physics().create("es", "Electrostatics", "geom1")
    es.selection().set(pzt_domain)
    es.create("ccnp1", "ChargeConservationPiezo", 3).selection().set(pzt_domain)
    es.create("gnd1", "Ground", 2).selection().set(bottom_electrode)
    term = es.create("term1", "Terminal", 2)
    term.selection().set(top_electrode)
    term.set("TerminalType", "Circuit")

    cir = comp.physics().create("cir", "Circuit", "geom1")
    res = cir.create("R1", "Resistor")
    res.set("R", "RL_ohm")
    res.set("Connections", ["0", "1"])
    term_i = cir.create("termI", "ModelTerminalIV")
    term_i.set("Connections", "1")
    term_i.set("V_src", "root.comp1.es.V0_1")

    pze = comp.multiphysics().create("pze1", "PiezoelectricEffect", 3)
    pze.set("Electrostatics_physics", "es")
    pze.set("InitializePiezoCoupling", "1")

    mesh = comp.mesh().create("mesh1")
    mesh.autoMeshSize(4)
    mesh.run()

    std_eig = java.study().create("std_eig")
    eig = std_eig.create("eig", "Eigenfrequency")
    eig.set("neigs", str(config.n_eigs))
    eig.set("shift", "f_exc_hz")
    eig.set("shiftactive", "on")
    eig.setSolveFor("/physics/solid", True)
    eig.setSolveFor("/physics/es", False)
    eig.setSolveFor("/physics/cir", False)
    p.set("loss_mult", "0")
    p.set("eps_loss_mult", "1")
    base_disp.set("U0", ["0", "0", "0"])
    eig_start = time.perf_counter()
    java.study("std_eig").run()
    solve_time_eig_s = time.perf_counter() - eig_start

    eig_dataset = model / "datasets" / model.datasets()[-1]
    eig_raw = np.asarray(model.evaluate("solid.freq", "Hz", eig_dataset)).reshape(-1).real
    eigenfreqs = [float(freq) for freq in eig_raw if float(freq) > 1.0]

    freq_values = np.linspace(config.f_min, config.f_max, config.n_freq)
    std_freq = java.study().create("std_freq")
    freq_step = std_freq.create("freq", "Frequency")
    freq_step.set("plist", " ".join(f"{freq:.6f}" for freq in freq_values))
    freq_step.setSolveFor("/physics/solid", True)
    freq_step.setSolveFor("/physics/es", True)
    freq_step.setSolveFor("/physics/cir", True)
    p.set("loss_mult", "2i*zeta")
    p.set("eps_loss_mult", "(1-1i*eps_tand)")
    base_disp.set("U0", ["0", "a_exc/(2*pi*freq)^2", "0"])
    freq_start = time.perf_counter()
    java.study("std_freq").run()
    solve_time_freq_s = time.perf_counter() - freq_start

    freq_dataset = model / "datasets" / model.datasets()[-1]
    v_terminal = np.asarray(model.evaluate("es.V0_1", "V", freq_dataset)).reshape(-1)
    power = np.abs(v_terminal) ** 2 / (2.0 * config.load_resistance_ohm)

    probe_eps = min(1.0e-6, 0.01 * a_cell)
    probe_coords = np.array(
        [
            [0.0, x_cursor],
            [0.5 * config.beam_width, 0.5 * config.beam_width],
            [0.5 * config.beam_height, 0.5 * config.beam_height],
        ],
        dtype=float,
    )
    left_disp = _evaluate_point_series(
        model,
        freq_dataset,
        expressions=("solid.v", "v"),
        unit="m",
        coordinates=probe_coords[:, :1],
        selection=[al_domains[0]],
    )
    right_disp = _evaluate_point_series(
        model,
        freq_dataset,
        expressions=("solid.v", "v"),
        unit="m",
        coordinates=probe_coords[:, 1:],
        selection=[ep_domains[-1]],
    )
    w_left = np.abs(left_disp[:, 0])
    w_right = np.abs(right_disp[:, 0])
    transmission_db = 20.0 * np.log10(np.maximum(w_right, np.finfo(float).tiny) / np.maximum(w_left, np.finfo(float).tiny))

    disp_raw = np.asarray(model.evaluate("solid.disp", "m", freq_dataset)).reshape(-1)
    if disp_raw.size % config.n_freq == 0 and disp_raw.size > 0:
        disp_matrix = np.abs(disp_raw.reshape(config.n_freq, -1))
        max_disp = np.max(disp_matrix, axis=1)
    else:
        max_disp = np.zeros(config.n_freq)

    return {
        "frequency_hz": freq_values,
        "eigenfrequencies_hz": np.asarray(eigenfreqs, dtype=float),
        "voltage_v": np.abs(v_terminal),
        "power_w": power,
        "max_disp_m": max_disp,
        "w_left_m": w_left,
        "w_right_m": w_right,
        "transmission_db": transmission_db,
        "f_sweep": freq_values,
        "max_disp_per_freq": max_disp,
        "solve_time_eig_s": solve_time_eig_s,
        "solve_time_freq_s": solve_time_freq_s,
        "config": config,
    }


def _assign_material(comp, tag: str, label: str, domains: list[int], young: float, nu: float, rho: float) -> None:
    mat = comp.material().create(tag, "Common")
    mat.label(label)
    mat.selection().set(domains)
    prop = mat.propertyGroup("def")
    prop.set("youngsmodulus", [f"{young}[Pa]"])
    prop.set("poissonsratio", [str(nu)])
    prop.set("density", [f"{rho}[kg/m^3]"])


def _selection_entities(comp, tags: list[str], dim: int) -> list[int]:
    entities: list[int] = []
    for tag in tags:
        entities.extend(list(comp.selection(f"geom1_{tag}_dom").entities(dim)))
    return entities


def _box_bnd(comp, name: str, xmin: float, xmax: float, ymin: float, ymax: float, zmin: float, zmax: float) -> list[int]:
    sel = comp.selection().create(name, "Box")
    sel.geom("geom1", 2)
    tol = 1.0e-6
    sel.set("xmin", str(xmin - tol))
    sel.set("xmax", str(xmax + tol))
    sel.set("ymin", str(ymin - tol))
    sel.set("ymax", str(ymax + tol))
    sel.set("zmin", str(zmin - tol))
    sel.set("zmax", str(zmax + tol))
    sel.set("condition", "allvertices")
    return list(sel.entities(2))


def _evaluate_point_series(
    model,
    dataset,
    *,
    expressions: tuple[str, ...],
    unit: str,
    coordinates: np.ndarray,
    selection: list[int],
) -> np.ndarray:
    """Evaluate a displacement field at one or more physical coordinates."""
    eval_feature = (model / "evaluations").create("Interp")
    java = eval_feature.java
    eval_feature.property("data", dataset)
    eval_feature.property("unit", unit)
    java.selection().set([int(entity) for entity in selection])
    java.setInterpolationCoordinates(np.asarray(coordinates, dtype=float).tolist())

    last_error: Exception | None = None
    for expression in expressions:
        try:
            eval_feature.property("expr", expression)
            values = np.asarray(java.getData())
            if java.isComplex():
                values = values.astype(complex) + 1j * np.asarray(java.getImagData())
            values = np.asarray(values).squeeze()
            if values.ndim == 1:
                if values.size % coordinates.shape[1] != 0:
                    raise RuntimeError(
                        f'Interpolated "{expression}" returned flat shape {values.shape}, '
                        f"which is incompatible with {coordinates.shape[1]} probe point(s)."
                    )
                values = values.reshape(-1, coordinates.shape[1])
            elif values.ndim == 2:
                if values.shape[1] == coordinates.shape[1]:
                    pass
                elif values.shape[0] == coordinates.shape[1]:
                    values = values.T
                else:
                    raise RuntimeError(
                        f'Interpolated "{expression}" returned shape {values.shape}, '
                        f"expected one axis to match {coordinates.shape[1]} probe point(s)."
                    )
            else:
                raise RuntimeError(
                    f'Interpolated "{expression}" returned shape {values.shape}, '
                    "expected at most two dimensions after squeezing."
                )
            eval_feature.remove()
            return values
        except Exception as exc:
            last_error = exc

    eval_feature.remove()
    raise RuntimeError(f"Failed to interpolate any of {expressions}.") from last_error


def _isotropic_stiffness_matrix(young: float, nu: float) -> list[list[str]]:
    lam = young * nu / ((1 + nu) * (1 - 2 * nu))
    mu = young / (2 * (1 + nu))
    matrix = [
        [lam + 2 * mu, lam, lam, 0.0, 0.0, 0.0],
        [lam, lam + 2 * mu, lam, 0.0, 0.0, 0.0],
        [lam, lam, lam + 2 * mu, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, mu, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, mu, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, mu],
    ]
    return [[str(value) for value in row] for row in matrix]


def _flatten_matrix(matrix: list[list[str]]) -> list[str]:
    return [item for row in matrix for item in row]


def _scale_matrix_entries(matrix: list[list[str]], multiplier: str) -> list[str]:
    scaled: list[str] = []
    for row in matrix:
        for entry in row:
            if entry == "0.0" or entry == "0":
                scaled.append("0")
            else:
                scaled.append(f"({entry})*({multiplier})")
    return scaled


def _column_major_ees(e31: float, e33: float, e15: float) -> list[str]:
    matrix = np.array(
        [
            [0.0, 0.0, 0.0, 0.0, e15, 0.0],
            [0.0, 0.0, 0.0, e15, 0.0, 0.0],
            [e31, e31, e33, 0.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    return [str(value) for value in matrix.flatten(order="F")]
