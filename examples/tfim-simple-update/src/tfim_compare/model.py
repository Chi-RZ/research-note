"""One TFIM convention shared by the QuSpin and Quimb calculations."""

from __future__ import annotations


def square_bonds(lx: int, ly: int) -> tuple[tuple[int, int], ...]:
    """Return nearest-neighbor bonds for an ``lx`` by ``ly`` open square."""
    bonds = []
    for i in range(lx):
        for j in range(ly):
            site = i * ly + j
            if i + 1 < lx:
                bonds.append((site, (i + 1) * ly + j))
            if j + 1 < ly:
                bonds.append((site, i * ly + j + 1))
    return tuple(bonds)


def ed_ground_energy(lx: int, ly: int, coupling: float, field: float) -> float:
    """Ground energy of ``-J sum ZZ - h sum X`` from QuSpin."""
    ham = quspin_hamiltonian(lx, ly, coupling, field)
    return float(ham.eigsh(k=1, which="SA", return_eigenvectors=False)[0])


def quspin_hamiltonian(lx: int, ly: int, coupling: float, field: float):
    """Return the full-basis QuSpin Hamiltonian for the open square."""
    import numpy as np
    from quspin.basis import spin_basis_general
    from quspin.operators import hamiltonian

    nsites = lx * ly
    # ``spin_basis_general`` makes it explicit that the basis itself has no
    # one-dimensional geometry. The 3x3 square is defined by the bond list.
    basis = spin_basis_general(N=nsites, pauli=1)
    static = [
        ["zz", [[-coupling, a, b] for a, b in square_bonds(lx, ly)]],
        ["x", [[-field, site] for site in range(nsites)]],
    ]
    return hamiltonian(
        static,
        [],
        basis=basis,
        dtype=np.float64,
        check_herm=False,
        check_symm=False,
        check_pcon=False,
    )
def quimb_hamiltonian(lx: int, ly: int, coupling: float, field: float):
    """The same Hamiltonian as a Quimb ``LocalHam2D``."""
    import quimb as qu
    import quimb.tensor as qtn

    x = qu.pauli("X")
    z = qu.pauli("Z")
    return qtn.LocalHam2D(
        lx,
        ly,
        -coupling * qu.kron(z, z),
        H1=-field * x,
        cyclic=False,
    )


def initial_peps(lx: int, ly: int):
    """Return the deterministic ``+x`` product state used for every D."""
    import numpy as np
    import quimb.tensor as qtn

    plus = np.array([1.0, 1.0]) / np.sqrt(2.0)
    return qtn.PEPS.product_state(
        {(i, j): plus.copy() for i in range(lx) for j in range(ly)}
    )
