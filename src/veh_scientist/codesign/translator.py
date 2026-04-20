"""Translate L1-style candidate families into realizable L2 beam models."""

from __future__ import annotations

from dataclasses import dataclass
import math

from veh_scientist.interfaces.schemas import CandidateDesignFamily, TaskCard
from veh_scientist.verifiers.l2_beam import compute_beam_bandgaps
from veh_scientist.verifiers.l2_beam.tmm import (
    BeamGeometry,
    MaterialProperties,
    PiezoProperties,
)


@dataclass(frozen=True)
class BeamRealization:
    """Concrete beam model derived from a candidate family."""

    mat_A: MaterialProperties
    mat_B: MaterialProperties
    geom: BeamGeometry
    piezo: PiezoProperties
    L_A: float
    L_B: float
    n_cells: int
    R_load: float
    boundary_mass_factor: float
    assumptions: tuple[str, ...]


class CandidateToBeamTranslator:
    """Approximate inverse map from chain parameters to beam parameters.

    This is intentionally explicit about its assumptions. The current L2 beam
    model supports material contrast, cell lengths, piezo patch, and a finite
    boundary mass asymmetry. It does not claim an exact analytical inversion
    from `(alpha, beta, delta, N)` to beam geometry.
    """

    def __init__(self, task: TaskCard, *, tune_geometry: bool = False):
        self.task = task
        self.tune_geometry = tune_geometry

    def translate(self, candidate: CandidateDesignFamily) -> BeamRealization:
        """Build an approximate L2 beam realization for the candidate."""
        mat_A = _material_from_name(candidate.structure.material_A, fallback="aluminum")

        total_length = self.task.envelope_constraints.total_length_m or 1.0
        n_cells = max(candidate.structure.N, 5)
        cell_pitch = total_length / n_cells

        frac_A = _segment_fraction_from_beta(candidate.structure.beta)
        L_A = cell_pitch * frac_A
        L_B = cell_pitch - L_A
        derived_B = _derive_contrast_layer(
            reference=mat_A,
            alpha=max(candidate.structure.alpha, 1e-3),
            beta=max(candidate.structure.beta, 1e-3),
            L_A=L_A,
            L_B=L_B,
        )
        hinted_B = _material_from_name(candidate.structure.material_B, fallback="epoxy")
        mat_B = _stabilize_contrast_layer(
            reference=mat_A,
            derived=derived_B,
            hinted=hinted_B,
            alpha=max(candidate.structure.alpha, 1e-3),
            beta=max(candidate.structure.beta, 1e-3),
        )

        geom = _geometry_from_task(self.task)
        if self.tune_geometry:
            geom = _tune_geometry_to_frequency(
                task=self.task,
                mat_A=mat_A,
                mat_B=mat_B,
                geom=geom,
                L_A=L_A,
                L_B=L_B,
            )
        piezo = _piezo_from_task(self.task, geom, cell_pitch)
        R_load = _load_from_task(self.task)

        realized_alpha = (mat_B.rho * L_B) / max(mat_A.rho * L_A, 1e-30)
        realized_beta = (mat_B.E / L_B) / max(mat_A.E / L_A, 1e-30)

        assumptions = (
            (
                "Mapped alpha and beta into beam-segment density/modulus with "
                f"m ~ rho*L and k ~ E/L proxies (realized alpha={realized_alpha:.3f}, "
                f"realized beta={realized_beta:.3f})."
            ),
            (
                f"Set beam thickness to h={geom.h:.4e} m from task envelope limits."
                if not self.tune_geometry
                else f"Tuned beam thickness to h={geom.h:.4e} m so the first L2 bandgap tracks the task frequency window."
            ),
            "Mapped delta to a finite-beam boundary mass factor at the first free A/B interface node.",
            "Used the requested/fallback A-layer material as a reference and derived the B-layer contrast from the chain ratios.",
        )

        return BeamRealization(
            mat_A=mat_A,
            mat_B=mat_B,
            geom=geom,
            piezo=piezo,
            L_A=L_A,
            L_B=L_B,
            n_cells=n_cells,
            R_load=R_load,
            boundary_mass_factor=min(max(candidate.structure.delta, 0.2), 5.0),
            assumptions=assumptions,
        )


def _material_from_name(name: str, fallback: str) -> MaterialProperties:
    lookup = {
        "aluminum": MaterialProperties(E=68.9e9, rho=2700, nu=0.33),
        "epoxy": MaterialProperties(E=2.4e9, rho=1040, nu=0.35),
        "abs": MaterialProperties(E=2.4e9, rho=1040, nu=0.35),
        "steel": MaterialProperties(E=200e9, rho=7850, nu=0.30),
        "brass": MaterialProperties(E=110e9, rho=8500, nu=0.34),
    }
    key = (name or fallback).strip().lower()
    return lookup.get(key, lookup[fallback])


def _segment_fraction_from_beta(beta: float) -> float:
    """Choose a moderate A/B length split that keeps beta realizable.

    Using k ~ E/L, a very small beta would otherwise force extreme material
    properties if L_A and L_B were fixed. We bias the softer segment to be
    slightly longer, but keep the split moderate so the finite beam remains
    manufacturable and the mapping stays stable.
    """
    beta = max(beta, 1e-6)
    frac_A = 0.5 + 0.12 * math.tanh(math.log(beta))
    return min(max(frac_A, 0.35), 0.65)


def _derive_contrast_layer(
    reference: MaterialProperties,
    alpha: float,
    beta: float,
    L_A: float,
    L_B: float,
) -> MaterialProperties:
    """Derive a contrast layer that approximately preserves chain alpha/beta."""
    rho_B = alpha * reference.rho * L_A / max(L_B, 1e-12)
    E_B = beta * reference.E * L_B / max(L_A, 1e-12)

    rho_B = min(max(rho_B, 400.0), 12000.0)
    E_B = min(max(E_B, 0.5e9), 300e9)
    nu_B = min(max(reference.nu + 0.02, 0.25), 0.38)

    return MaterialProperties(E=E_B, rho=rho_B, nu=nu_B)


def _stabilize_contrast_layer(
    *,
    reference: MaterialProperties,
    derived: MaterialProperties,
    hinted: MaterialProperties,
    alpha: float,
    beta: float,
) -> MaterialProperties:
    """Pull the derived layer toward a contrast material so the beam keeps a usable bandgap."""
    prefer_softer = beta <= 1.0
    prefer_lighter = alpha <= 1.0

    target_E = min(derived.E, hinted.E) if prefer_softer else max(derived.E, hinted.E)
    target_rho = min(derived.rho, hinted.rho) if prefer_lighter else max(derived.rho, hinted.rho)

    E_B = derived.E if math.isclose(derived.E, target_E) else math.sqrt(derived.E * target_E)
    rho_B = derived.rho if math.isclose(derived.rho, target_rho) else math.sqrt(derived.rho * target_rho)

    E_B = min(max(E_B, 0.5e9), 300e9)
    rho_B = min(max(rho_B, 400.0), 12000.0)
    return MaterialProperties(E=E_B, rho=rho_B, nu=hinted.nu if hinted else reference.nu)


def _geometry_from_task(task: TaskCard) -> BeamGeometry:
    area_limit = task.envelope_constraints.max_cross_section_m2
    width = 0.025
    if area_limit:
        height = min(max(area_limit / width, 0.0025), 0.0100)
    else:
        height = 0.005
    return BeamGeometry(b=width, h=height, ks=5.0 / 6.0)


def _tune_geometry_to_frequency(
    *,
    task: TaskCard,
    mat_A: MaterialProperties,
    mat_B: MaterialProperties,
    geom: BeamGeometry,
    L_A: float,
    L_B: float,
) -> BeamGeometry:
    """Coarsely rescale beam thickness so the first bandgap stays near the task band.

    This translator is used in proposal generation and mechanism screening, so it
    should be materially cheaper than the downstream L2/L3 verifiers. A single
    coarse bandgap estimate is sufficient here.
    """
    f_low, f_high = task.frequency_target.band_of_interest
    target_center = task.frequency_target.primary_target_frequency or (0.5 * (f_low + f_high))
    if target_center <= 0:
        return geom

    area_limit = task.envelope_constraints.max_cross_section_m2
    min_h = 5.0e-4
    max_h = 0.012 if area_limit is None else max(min(area_limit / geom.b, 0.012), min_h)
    bg = compute_beam_bandgaps(
        mat_A,
        mat_B,
        geom,
        L_A,
        L_B,
        1.0,
        max(target_center * 3.0, 1800.0),
        48,
    )
    if not bg.gaps:
        return geom

    gap_lo, gap_hi = bg.gaps[0]
    current_center = 0.5 * (gap_lo + gap_hi)
    if current_center <= 0:
        return geom

    if f_low <= current_center <= f_high:
        return geom

    scale = target_center / current_center
    new_h = min(max(geom.h * scale, min_h), max_h)
    if abs(new_h - geom.h) / max(geom.h, 1e-12) < 0.05:
        return geom
    return BeamGeometry(b=geom.b, h=new_h, ks=geom.ks)


def _piezo_from_task(task: TaskCard, geom: BeamGeometry, cell_pitch: float) -> PiezoProperties:
    if task.envelope_constraints.piezo_volume_m3:
        thickness = task.envelope_constraints.piezo_volume_m3 / max(geom.b * cell_pitch, 1e-12)
        thickness = min(max(thickness, 2.0e-4), 1.5e-3)
    else:
        thickness = 5.0e-4

    return PiezoProperties(
        h=thickness,
        rho=7500,
        d31=-274e-12,
        E=62e9,
        eps33T=3400 * 8.854e-12,
    )


def _load_from_task(task: TaskCard) -> float:
    if task.harvesting_requirements.load_value is not None:
        return task.harvesting_requirements.load_value
    if task.harvesting_requirements.target_output == "current":
        return 1.0e4
    if task.harvesting_requirements.target_output == "voltage":
        return 1.0e7
    return 1.0e6
