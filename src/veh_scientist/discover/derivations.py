"""Derivation cards for replaying the TR paper development path."""

from __future__ import annotations

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
