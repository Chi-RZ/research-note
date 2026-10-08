"""Gate the shared 3x3 Hamiltonian convention against an analytic state."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from tfim_compare import initial_peps, quimb_hamiltonian, quspin_hamiltonian, square_bonds

LX = 3
LY = 3
NSITES = LX * LY
COUPLING = 1.0
FIELD = 3.0
EXPECTED_PLUS_ENERGY = -FIELD * NSITES

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent / "tfim_3x3" / "gate"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    quspin_ham = quspin_hamiltonian(LX, LY, COUPLING, FIELD)
    plus = np.ones(quspin_ham.Ns, dtype=np.complex128) / np.sqrt(quspin_ham.Ns)
    quspin_energy = float(np.vdot(plus, quspin_ham.dot(plus)).real)

    quimb_ham = quimb_hamiltonian(LX, LY, COUPLING, FIELD)
    quimb_energy = float(
        np.real_if_close(
            initial_peps(LX, LY).compute_local_expectation_exact(
                quimb_ham.terms, optimize="greedy"
            )
        )
    )
    payload = {
        "Lx": LX,
        "Ly": LY,
        "boundary": "open",
        "bonds": len(square_bonds(LX, LY)),
        "expected_plus_energy": EXPECTED_PLUS_ENERGY,
        "quspin_plus_energy": quspin_energy,
        "quimb_plus_energy": quimb_energy,
        "solver_difference": abs(quspin_energy - quimb_energy),
    }
    print(json.dumps(payload))
    (OUTPUT / "model.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
