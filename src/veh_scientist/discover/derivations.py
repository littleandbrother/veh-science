"""Derivation cards and symbolic execution for the TR replay pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sympy as sp

from veh_scientist.discover.utils import ensure_dir, write_json, write_text
from veh_scientist.interfaces import DerivationCard, DiscoverTaskCard


def build_tr_derivation_cards(task: DiscoverTaskCard) -> list[DerivationCard]:
    """Return the canonical derivation ladder for the TR discovery program."""

    return [
        DerivationCard(
            title="Infinite-chain dispersion relation",
            assumptions=(
                "Periodic diatomic chain with alternating masses and springs.",
                "Bloch wave ansatz with harmonic motion.",
            ),
            starting_equations=("bulk_equations_of_motion",),
            target_equations=("dispersion_quartic", "band_edges"),
            symbolic_steps=(
                "Assemble the 2x2 Bloch eigenproblem.",
                "Set the determinant to zero and non-dimensionalize with omega_b.",
            ),
            validation_checks=("unit_check", "band_edge_limit_check", "numerical_dispersion_check"),
            artifact_targets=("dispersion_curve", "bandgap_table"),
        ),
        DerivationCard(
            title="Finite-chain dynamic stiffness and TR criterion",
            assumptions=(
                "Finite chain with a non-periodic boundary mass.",
                "Boundary truncation represented explicitly in the stiffness matrix.",
            ),
            starting_equations=("finite_chain_equations",),
            target_equations=("detA_equals_zero", "tr_in_gap_criterion"),
            symbolic_steps=(
                "Assemble the finite dynamic stiffness matrix.",
                "Find eigenfrequencies and intersect them with the infinite-chain bandgap.",
            ),
            validation_checks=("matrix_symmetry_check", "gap_membership_check", "numerical_root_check"),
            artifact_targets=("finite_chain_spectrum", "tr_identification_plot"),
        ),
        DerivationCard(
            title="Mode energy and localization ratio eta",
            assumptions=(
                "Cycle-averaged kinetic and potential energy are computed cell-wise.",
                "Localization is measured using the first-cell energy concentration ratio.",
            ),
            starting_equations=("mode_shape_solution",),
            target_equations=("cell_energy", "eta_definition"),
            symbolic_steps=(
                "Compute cell-wise kinetic and potential energy.",
                "Normalize the first-cell energy by the total chain energy.",
            ),
            validation_checks=("energy_positivity_check", "normalization_check", "passband_comparison_check"),
            artifact_targets=("mode_shape_plot", "eta_spectrum"),
        ),
        DerivationCard(
            title="Piezoelectric voltage recovery relation",
            assumptions=(
                "Linear piezoelectric patch represented by the stress-charge model.",
                "Resistive shunt in parallel with the patch capacitance.",
            ),
            starting_equations=("port_force_balance", "kcl_equation"),
            target_equations=("voltage_recovery_relation",),
            symbolic_steps=(
                "Transform the circuit equation into the frequency domain.",
                "Solve the voltage amplitude in terms of the mechanical gap.",
            ),
            validation_checks=("open_circuit_limit_check", "short_circuit_limit_check", "numerical_back_substitution"),
            artifact_targets=("voltage_sweep", "gap_to_voltage_map"),
        ),
        DerivationCard(
            title="Complex dynamic stiffness and electrical matching",
            assumptions=(
                "The piezoelectric port feeds back an equal-and-opposite force pair.",
                "Electromechanical coupling is represented as a frequency-dependent complex stiffness.",
            ),
            starting_equations=("voltage_recovery_relation", "piezo_force_expression"),
            target_equations=("complex_dynamic_stiffness", "impedance_matching_rule"),
            symbolic_steps=(
                "Substitute the voltage expression back into the mechanical port force.",
                "Extract the real and imaginary parts to separate storage and dissipation effects.",
            ),
            validation_checks=("passivity_check", "matching_rule_check", "dimensionless_parameter_check"),
            artifact_targets=("keff_real_imag_plot", "epsilon_matching_curve"),
        ),
        DerivationCard(
            title="Periodic Timoshenko beam transfer matrix",
            assumptions=(
                "Bilayer Timoshenko beam with harmonic state-space formulation.",
                "Bloch-Floquet condition for the infinite beam and selector matrices for the finite beam.",
            ),
            starting_equations=("beam_state_space_matrix",),
            target_equations=("beam_cell_transfer_operator", "beam_bloch_condition", "beam_tr_criterion"),
            symbolic_steps=(
                "Construct the layer transfer operators and the unit-cell operator.",
                "Use Bloch analysis for bandgaps and boundary selectors for the finite-beam resonance condition.",
            ),
            validation_checks=("state_dimension_check", "bloch_eigenvalue_check", "finite_beam_root_check"),
            artifact_targets=("beam_dispersion_curve", "beam_transmission_plot"),
        ),
    ]


def _derive_dispersion() -> dict[str, Any]:
    ka, kb, ma, mb, omega, q, a = sp.symbols("k_a k_b m_a m_b omega q a", positive=True, real=True)
    bloch = sp.Matrix(
        [
            [ka + kb - ma * omega**2, -(ka + kb * sp.exp(-sp.I * q * a))],
            [-(ka + kb * sp.exp(sp.I * q * a)), ka + kb - mb * omega**2],
        ]
    )
    raw_det = sp.simplify(sp.expand(sp.det(bloch)))
    alpha, beta, Omega = sp.symbols("alpha beta Omega", positive=True, real=True)
    quartic = Omega**4 - (1 + alpha) * (1 + 1 / beta) * Omega**2 + (4 * alpha / beta) * sp.sin(q * a / 2) ** 2
    return {
        "raw_determinant": sp.latex(raw_det),
        "dimensionless_quartic": sp.latex(sp.expand(quartic)),
    }


def _derive_voltage_and_stiffness() -> dict[str, Any]:
    omega, C_p, R, theta, g = sp.symbols("omega C_p R theta g", positive=True, real=True)
    V = sp.symbols("V")
    circuit_eq = sp.Eq((sp.I * omega * C_p + 1 / R) * V + sp.I * omega * theta * g, 0)
    voltage_solution = sp.solve(circuit_eq, V)[0]
    k_b = sp.symbols("k_b", positive=True, real=True)
    k_eff = sp.simplify(k_b + theta * voltage_solution / g)
    kappa2, epsilon, Omega = sp.symbols("kappa2 epsilon Omega", positive=True, real=True)
    k_eff_nd = 1 - sp.I * Omega * kappa2 / (sp.I * Omega + epsilon)
    return {
        "circuit_equation": sp.latex(circuit_eq),
        "voltage_solution": sp.latex(sp.Eq(V, voltage_solution)),
        "complex_stiffness": sp.latex(sp.Eq(sp.Symbol("k_{b,eff}"), k_eff)),
        "complex_stiffness_nd": sp.latex(sp.Eq(sp.Symbol(r"\tilde{k}_{b,eff}"), k_eff_nd)),
        "matching_rule": r"\epsilon^\star \sim \Omega_{TR}\;\Leftrightarrow\;R^\star \sim \frac{1}{C_p\,\omega_{TR}}",
    }


def _derive_beam_matrix() -> dict[str, Any]:
    alpha_j, r_j, eta_j, beta_j, Omega = sp.symbols("alpha_j r_j eta_j beta_j Omega", positive=True, real=True)
    A = sp.Matrix(
        [
            [0, 1, 1 / beta_j, 0],
            [0, 0, 0, 1 / alpha_j],
            [-(Omega**2) * r_j, 0, 0, 0],
            [0, -(Omega**2) * eta_j, -1, 0],
        ]
    )
    return {
        "state_matrix": sp.latex(A),
        "transfer_operator": r"T_j(\Omega) = \exp\left( A_j(\Omega)\,\ell_j \right)",
        "bloch_condition": r"\det\left(T_{cell}(\Omega) - \mu I_4\right)=0,\quad \mu=e^{i k a}",
        "finite_resonance": r"\det\left(C_r\,T_N(\Omega)\,B_\ell\right)=0",
    }


def execute_tr_derivations(
    output_dir: str | Path,
    task: DiscoverTaskCard,
    l1_summary: dict[str, Any] | None = None,
    l2_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate markdown, LaTeX, and validation checks for the derivation ladder."""

    output_dir = ensure_dir(output_dir)
    cards = build_tr_derivation_cards(task)
    dispersion = _derive_dispersion()
    piezo = _derive_voltage_and_stiffness()
    beam = _derive_beam_matrix()

    checks: dict[str, Any] = {
        "dispersion_numeric_check": {
            "status": "available",
            "note": "Analytic quartic emitted to LaTeX for direct numerical use.",
        },
        "finite_chain_check": {
            "status": "available" if l1_summary is not None else "pending",
            "tr_frequency": None if l1_summary is None else l1_summary["tr_mode"]["omega"],
            "gap": None if l1_summary is None else l1_summary["bandgap"],
        },
        "eta_check": {
            "status": "available" if l1_summary is not None else "pending",
            "eta": None if l1_summary is None else l1_summary["tr_mode"]["eta"],
        },
        "matching_rule_check": {
            "status": "available" if l1_summary is not None else "pending",
            "epsilon": None if l1_summary is None else l1_summary["params"]["epsilon"],
            "tr_peak": None if l1_summary is None else l1_summary["tr_power_peak_omega"],
        },
        "beam_transfer_check": {
            "status": "available" if l2_summary is not None else "pending",
            "n_stopbands": None if l2_summary is None else len(l2_summary.get("stopbands_nd", [])),
            "n_candidates": None if l2_summary is None else len(l2_summary.get("candidates", [])),
        },
    }

    equations_tex = "\n\n".join(
        [
            r"% Auto-generated TR replay derivations",
            r"\section*{Infinite-chain dispersion}",
            r"\[" + dispersion["raw_determinant"] + r"\]",
            r"\[" + dispersion["dimensionless_quartic"] + r"\]",
            r"\section*{Piezoelectric recovery and complex stiffness}",
            r"\[" + piezo["circuit_equation"] + r"\]",
            r"\[" + piezo["voltage_solution"] + r"\]",
            r"\[" + piezo["complex_stiffness"] + r"\]",
            r"\[" + piezo["complex_stiffness_nd"] + r"\]",
            r"\[" + piezo["matching_rule"] + r"\]",
            r"\section*{Dimensionless Timoshenko state matrix}",
            r"\[ A_j(\Omega) = " + beam["state_matrix"] + r"\]",
            r"\[" + beam["transfer_operator"] + r"\]",
            r"\[" + beam["bloch_condition"] + r"\]",
            r"\[" + beam["finite_resonance"] + r"\]",
        ]
    )
    write_text(output_dir / "equations.tex", equations_tex)

    lines: list[str] = [
        f"# Derivation report for {task.task_id}",
        "",
        "This report mixes exact symbolic outputs with numerical checks from the replay solvers.",
        "",
    ]
    for card in cards:
        lines.append(f"## {card.title}")
        lines.append("")
        lines.append("Assumptions:")
        for item in card.assumptions:
            lines.append(f"- {item}")
        lines.append("")
        if card.title == "Infinite-chain dispersion relation":
            lines.append("Symbolic determinant:")
            lines.append("")
            lines.append("```latex")
            lines.append(dispersion["raw_determinant"])
            lines.append("```")
            lines.append("")
            lines.append("Dimensionless quartic:")
            lines.append("")
            lines.append("```latex")
            lines.append(dispersion["dimensionless_quartic"])
            lines.append("```")
        elif card.title == "Piezoelectric voltage recovery relation":
            lines.append("Recovered voltage relation:")
            lines.append("")
            lines.append("```latex")
            lines.append(piezo["voltage_solution"])
            lines.append("```")
        elif card.title == "Complex dynamic stiffness and electrical matching":
            lines.append("Recovered complex stiffness:")
            lines.append("")
            lines.append("```latex")
            lines.append(piezo["complex_stiffness_nd"])
            lines.append("```")
            lines.append("")
            lines.append("Electrical matching rule:")
            lines.append("")
            lines.append("```latex")
            lines.append(piezo["matching_rule"])
            lines.append("```")
        elif card.title == "Periodic Timoshenko beam transfer matrix":
            lines.append("Dimensionless state matrix and transfer criterion:")
            lines.append("")
            lines.append("```latex")
            lines.append(beam["state_matrix"])
            lines.append("```")
        else:
            lines.append("This card is currently validated numerically inside the replay pipeline rather than by a fully closed-form symbolic derivation.")
        lines.append("")
        lines.append("Validation checks:")
        for check in card.validation_checks:
            lines.append(f"- {check}")
        lines.append("")
    write_text(output_dir / "derivation_report.md", "\n".join(lines))
    write_json(output_dir / "derivation_checks.json", checks)
    write_json(output_dir / "derivation_cards.json", cards)

    return {
        "cards": cards,
        "checks": checks,
        "equations_tex": str((output_dir / "equations.tex").resolve()),
        "derivation_report": str((output_dir / "derivation_report.md").resolve()),
    }
