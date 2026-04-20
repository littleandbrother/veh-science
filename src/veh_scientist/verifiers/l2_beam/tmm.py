"""
Step 1a: Timoshenko beam Transfer Matrix Method (TMM).

Reference: Paper 1 Section 4, Eq. (14)-(22).
MATLAB reference: new_bc.m, function timo_layer_T.

The state vector is y(x) = [w, phi, V, M]^T where:
    w   = transverse displacement
    phi = rotation angle
    V   = shear force
    M   = bending moment

The state-space equation: dy/dx = A(omega) * y(x)
Transfer matrix: T(L, omega) = expm(A(omega) * L)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm


@dataclass(frozen=True)
class MaterialProperties:
    """Material properties for a beam layer.

    Attributes
    ----------
    E : float
        Young's modulus [Pa].
    rho : float
        Density [kg/m^3].
    nu : float
        Poisson's ratio [-].
    """

    E: float
    rho: float
    nu: float

    @property
    def G(self) -> float:
        """Shear modulus [Pa]."""
        return self.E / (2 * (1 + self.nu))


@dataclass(frozen=True)
class BeamGeometry:
    """Cross-section geometry of the beam.

    Attributes
    ----------
    b : float
        Width [m].
    h : float
        Height/thickness [m].
    ks : float
        Shear correction factor (5/6 for rectangular).
    """

    b: float
    h: float
    ks: float = 5.0 / 6.0

    @property
    def A(self) -> float:
        """Cross-sectional area [m^2]."""
        return self.b * self.h

    @property
    def I(self) -> float:
        """Second moment of area [m^4]."""
        return self.b * self.h**3 / 12.0


@dataclass(frozen=True)
class PiezoProperties:
    """Piezoelectric patch properties.

    Attributes
    ----------
    h : float
        Patch thickness [m].
    rho : float
        Patch density [kg/m^3].
    d31 : float
        Piezoelectric charge constant [m/V].
    E : float
        Patch Young's modulus [Pa].
    eps33T : float
        Permittivity at constant stress [F/m].
    """

    h: float
    rho: float
    d31: float
    E: float
    eps33T: float


def timo_layer_transfer_matrix(
    mat: MaterialProperties,
    geom: BeamGeometry,
    L: float,
    omega: float,
) -> NDArray[np.complexfloating]:
    """Compute the 4x4 transfer matrix for a uniform Timoshenko beam segment.

    Follows MATLAB timo_layer_T exactly.

    Parameters
    ----------
    mat : MaterialProperties
        Material of this layer.
    geom : BeamGeometry
        Cross-section geometry.
    L : float
        Length of the segment [m].
    omega : float
        Angular frequency [rad/s].

    Returns
    -------
    T : ndarray, shape (4, 4), complex
        Transfer matrix such that y(L) = T * y(0).
    """
    E = mat.E
    G = mat.G
    rho = mat.rho
    A = geom.A
    I = geom.I
    ks = geom.ks
    kGA = ks * G * A

    # State-space system matrix A(omega)
    # dy/dx = Am * y, where y = [w, phi, V, M]^T
    Am = np.array([
        [0,            1,      1/kGA,      0       ],
        [0,            0,      0,          1/(E*I) ],
        [-omega**2*rho*A, 0,   0,          0       ],
        [0, -omega**2*rho*I,  -1,          0       ],
    ], dtype=complex)

    return expm(Am * L)


def timoshenko_element_matrices(
    E: float,
    G: float,
    rho: float,
    A: float,
    I: float,
    L: float,
    ks: float,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Compute Timoshenko FEM element stiffness and mass matrices.

    2-node element with DOFs (w, phi) per node → 4x4 matrices.
    Follows MATLAB timoshenko_element_matrices exactly.

    Returns
    -------
    Ke : ndarray, shape (4, 4)
        Element stiffness matrix.
    Me : ndarray, shape (4, 4)
        Element consistent mass matrix.
    """
    phi_param = (12 * E * I) / (ks * G * A * L**2)

    Ke = (E * I / (L**3 * (1 + phi_param))) * np.array([
        [12,      6*L,          -12,      6*L],
        [6*L,     (4+phi_param)*L**2, -6*L, (2-phi_param)*L**2],
        [-12,     -6*L,          12,      -6*L],
        [6*L,     (2-phi_param)*L**2, -6*L, (4+phi_param)*L**2],
    ])

    m1 = rho * A * L / 420
    m2 = rho * I * L / 420

    Me_t = m1 * np.array([
        [156,  22*L,   54,  -13*L],
        [22*L, 4*L**2, 13*L, -3*L**2],
        [54,   13*L,   156, -22*L],
        [-13*L, -3*L**2, -22*L, 4*L**2],
    ])

    Me_r = m2 * np.array([
        [36,   3*L,   -36,   3*L],
        [3*L,  4*L**2, -3*L, -1*L**2],
        [-36,  -3*L,   36,   -3*L],
        [3*L,  -1*L**2, -3*L, 4*L**2],
    ])

    return Ke, Me_t + Me_r
