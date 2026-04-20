"""
Step 0a verification plot: Dispersion relation of infinite diatomic chain.

Produces a figure comparable to Paper 1 Fig. 3 (left panel):
  - Acoustic and optical branches vs wavenumber q
  - Bandgap region shaded
  - Bandgap boundaries annotated

Parameters: alpha=0.75, beta=3.0 (from para_test.m / Paper 1)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import matplotlib.pyplot as plt

from veh_scientist.verifiers.l1_chain.dispersion import (
    compute_bandgap,
    dispersion_relation,
)


def main():
    # Paper 1 / para_test.m parameters
    alpha = 0.75  # m_b / m_a
    beta = 3.0  # k_b / k_a

    # Wavenumber range: first Brillouin zone
    q = np.linspace(0, np.pi, 500)

    # Compute dispersion
    acoustic, optical = dispersion_relation(alpha, beta, q)

    # Compute bandgap
    gap = compute_bandgap(alpha, beta)

    # --- Plot ---
    fig, ax = plt.subplots(1, 1, figsize=(7, 5))

    # Shade bandgap
    if gap.exists:
        ax.axhspan(gap.lower, gap.upper, alpha=0.15, color="blue", label="Band Gap")

    # Dispersion branches
    ax.plot(q / np.pi, acoustic, "b-", linewidth=2, label="Acoustic Branch")
    ax.plot(q / np.pi, optical, "r-", linewidth=2, label="Optical Branch")

    # Bandgap boundaries
    if gap.exists:
        ax.axhline(gap.lower, color="gray", linestyle="--", linewidth=0.8)
        ax.axhline(gap.upper, color="gray", linestyle="--", linewidth=0.8)
        ax.text(
            0.5,
            gap.center,
            f"Bandgap\n[{gap.lower:.3f}, {gap.upper:.3f}]",
            ha="center",
            va="center",
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
        )

    ax.set_xlabel("Wavenumber $qa/\\pi$", fontsize=12)
    ax.set_ylabel("Non-dimensional frequency $\\Omega$", fontsize=12)
    ax.set_title(
        f"Dispersion Relation — Infinite Diatomic Chain\n"
        f"$\\alpha$={alpha}, $\\beta$={beta}",
        fontsize=13,
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, max(optical) * 1.1)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, alpha=0.3)

    # Print summary
    print(f"Parameters: alpha={alpha}, beta={beta}")
    print(f"Acoustic branch: [{acoustic[0]:.6f}, {acoustic[-1]:.6f}]")
    print(f"Optical branch:  [{optical[-1]:.6f}, {optical[0]:.6f}]")
    print(f"Bandgap exists:  {gap.exists}")
    print(f"Bandgap:         [{gap.lower:.6f}, {gap.upper:.6f}]")
    print(f"Bandgap width:   {gap.width:.6f}")
    print()

    # Dimensional check with para_test.m values
    k_a = 500.0
    k_b = k_a * beta
    m_a = 0.05
    m_b = m_a * alpha
    omega_b = np.sqrt(k_b / m_b)
    print(f"Dimensional check (para_test.m):")
    print(f"  m_a={m_a}, m_b={m_b}, k_a={k_a}, k_b={k_b}")
    print(f"  omega_b = {omega_b:.4f} rad/s")
    print(f"  Bandgap: [{gap.lower * omega_b:.2f}, {gap.upper * omega_b:.2f}] rad/s")
    print(f"  Bandgap: [{gap.lower * omega_b / (2*np.pi):.2f}, {gap.upper * omega_b / (2*np.pi):.2f}] Hz")

    # Save
    outdir = "results/step_0a"
    os.makedirs(outdir, exist_ok=True)
    fig.savefig(os.path.join(outdir, "dispersion_relation.png"), dpi=200, bbox_inches="tight")
    fig.savefig(os.path.join(outdir, "dispersion_relation.pdf"), bbox_inches="tight")
    print(f"\nFigure saved to {outdir}/")
    plt.close(fig)


if __name__ == "__main__":
    main()
