"""Hypothesis-ladder builders for discover mode."""

from __future__ import annotations

from veh_scientist.interfaces import DiscoverTaskCard, HypothesisCard


def build_tr_hypothesis_ladder(task: DiscoverTaskCard) -> list[HypothesisCard]:
    """Return the canonical five-step truncation-resonance hypothesis ladder."""

    return [
        HypothesisCard(
            label="H1",
            statement="Non-periodic boundary conditions create a truncation resonance inside the bandgap of the corresponding infinite periodic system.",
            rationale="The replay should first prove that the bandgap and the finite-chain eigenproblem intersect at a boundary-localized root.",
            pass_criteria=(
                "Infinite-chain analysis identifies a stop band.",
                "Finite-chain resonance falls inside that stop band.",
            ),
            fail_criteria=(
                "No finite-chain resonance lies inside the bandgap.",
                "The candidate state collapses into a passband mode.",
            ),
            required_derivations=("dispersion_relation", "finite_chain_tr_criterion"),
            required_experiments=("bandgap_scan", "finite_chain_mode_scan"),
        ),
        HypothesisCard(
            label="H2",
            statement="The truncation resonance mode produces strong boundary localization and a near-boundary energy concentration ratio far above ordinary passband modes.",
            rationale="Localization is what makes the mode useful for harvesting instead of being just another finite-size resonance.",
            pass_criteria=(
                "Mode shape decays from the boundary into the bulk.",
                "Near-boundary energy ratio exceeds the passband baseline.",
            ),
            fail_criteria=(
                "Mode amplitude is delocalized across the entire chain.",
                "Energy ratio is not materially larger than the passband baseline.",
            ),
            required_derivations=("mode_energy_eta",),
            required_experiments=("mode_shape_extraction", "energy_localization_plot"),
        ),
        HypothesisCard(
            label="H3",
            statement="A piezoelectric port placed at the truncation-resonance hotspot yields co-located voltage and power peaks at the same frequency where transmission remains negative.",
            rationale="This is the central synergy claim: harvesting and suppression must occur at the same frequency rather than trading off against each other.",
            pass_criteria=(
                "Voltage or power peaks at the truncation resonance frequency.",
                "Transmission remains below 0 dB at the same frequency.",
            ),
            fail_criteria=(
                "Peak electrical output shifts away from the truncation-resonance frequency.",
                "The electrical interface destroys the bandgap suppression property.",
            ),
            required_derivations=("piezo_voltage_recovery", "complex_dynamic_stiffness"),
            required_experiments=("piezo_frequency_sweep", "co_located_harvesting_plot"),
        ),
        HypothesisCard(
            label="H4",
            statement="The roles of delta, alpha and beta, kappa2 and epsilon, and N separate cleanly into switch, tuners, matchers, and Q-factor sharpening controls.",
            rationale="A publishable framework needs interpretable parameter roles rather than a black-box optimum.",
            pass_criteria=(
                "delta toggles TR existence or disappearance.",
                "alpha and beta shift the usable gap and Omega_TR.",
                "kappa2 and epsilon shape impedance matching without redefining the mechanism.",
                "N sharpens the resonance while leaving the mechanism intact.",
            ),
            fail_criteria=(
                "Parameter roles are entangled beyond interpretation.",
                "TR disappears under modest changes to N or matching parameters.",
            ),
            required_derivations=("complex_dynamic_stiffness",),
            required_experiments=("delta_scan", "alpha_beta_map", "kappa_epsilon_map", "N_sweep"),
        ),
        HypothesisCard(
            label="H5",
            statement="The truncation-resonance mechanism and its harvesting/suppression synergy generalize from the diatomic chain to a periodic Timoshenko beam model.",
            rationale="The replay must end with model transfer, otherwise the result remains a lumped-model curiosity.",
            pass_criteria=(
                "Beam transfer-matrix analysis exhibits a stop band.",
                "Finite beam shows a boundary-localized in-gap resonance.",
                "Beam-level harvesting and attenuation remain co-located.",
            ),
            fail_criteria=(
                "Beam model does not admit an in-gap resonance near the target band.",
                "The continuous model loses the suppression/harvesting synergy.",
            ),
            required_derivations=("beam_transfer_matrix",),
            required_experiments=("beam_bandgap_scan", "beam_tr_validation"),
        ),
    ]
