"""Compare second-order PEPS simple update with exact diagonalization."""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import quimb
import quimb.tensor as qtn
import quspin

from tfim_compare import ed_ground_energy, initial_peps, quimb_hamiltonian

LX = 3
LY = 3
NSITES = LX * LY
COUPLING = 1.0
FIELD = 3.0
DT = 0.05
BOND_DIMENSIONS = (2, 4, 8)
CHECKPOINTS = (50, 100, 200, 400)
CUTOFF = 1e-12

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent / "tfim_3x3" / "results"


def exact_peps_energy(psi, ham) -> float:
    """Contract the 3×3 PEPS exactly, so measurement adds no chi error."""
    energy = psi.compute_local_expectation_exact(ham.terms, optimize="greedy")
    return float(np.real_if_close(energy))


def simple_update_energies(bond_dimension: int, ham):
    """Evolve one D continuously and measure it at fixed beta checkpoints."""
    start = time.perf_counter()
    su = qtn.SimpleUpdate(
        initial_peps(LX, LY),
        ham,
        tau=DT,
        D=bond_dimension,
        cutoff=CUTOFF,
        ordering="sort",
        second_order_reflect=True,
        compute_energy_final=False,
        progbar=False,
    )
    rows = []
    previous = 0
    for steps in CHECKPOINTS:
        su.evolve(steps - previous)
        previous = steps
        psi = su.get_state(absorb_gauges=True)
        rows.append(
            {
                "steps": steps,
                "beta": steps * DT,
                "energy": exact_peps_energy(psi, ham),
                "max_bond": psi.max_bond(),
            }
        )
    return rows, time.perf_counter() - start


def plot(rows: list[dict]) -> None:
    """Plot the shape that the record's convergence conclusion cites."""
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    for steps in CHECKPOINTS:
        selected = [row for row in rows if row["steps"] == steps]
        ax.plot(
            [row["D"] for row in selected],
            [row["abs_error"] for row in selected],
            marker="o",
            label=rf"$\beta={steps * DT:g}$",
        )
    ax.set_yscale("log")
    ax.set_xticks(BOND_DIMENSIONS)
    ax.set_xlabel("PEPS bond dimension $D$")
    ax.set_ylabel(r"$|E_{SU} - E_{ED}|$")
    ax.set_title("3×3 OBC TFIM, second-order SU, dt=0.05")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    figure = OUTPUT / "convergence.svg"
    fig.savefig(figure)
    plt.close(fig)
    # Matplotlib's SVG path data carries trailing spaces. Strip them so a
    # regenerated scientific artifact passes the repository whitespace gate.
    text = figure.read_text(encoding="utf-8")
    figure.write_text(
        "\n".join(line.rstrip() for line in text.splitlines()) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ed_energy = ed_ground_energy(LX, LY, COUPLING, FIELD)
    print(f"ED energy = {ed_energy:.12f}; per site = {ed_energy / NSITES:.12f}")
    ham = quimb_hamiltonian(LX, LY, COUPLING, FIELD)
    rows = []
    for bond_dimension in BOND_DIMENSIONS:
        checkpoints, elapsed = simple_update_energies(bond_dimension, ham)
        for row in checkpoints:
            row.update(
                {
                    "D": bond_dimension,
                    "energy_per_site": row["energy"] / NSITES,
                    "abs_error": abs(row["energy"] - ed_energy),
                }
            )
            rows.append(row)
            print(json.dumps(row))
        print(f"D={bond_dimension} elapsed_seconds={elapsed:.3f}")

    payload = {
        "software": {"quimb": quimb.__version__, "quspin": quspin.__version__},
        "parameters": {
            "Lx": LX,
            "Ly": LY,
            "boundary": "open",
            "J": COUPLING,
            "h": FIELD,
            "dt": DT,
            "checkpoints": CHECKPOINTS,
            "ordering": "sort",
            "second_order_reflect": True,
            "initial_state": "+x product state",
            "cutoff": CUTOFF,
            "energy_measurement": "exact PEPS contraction",
        },
        "ed_energy": ed_energy,
        "rows": rows,
    }
    (OUTPUT / "convergence.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    plot(rows)


if __name__ == "__main__":
    main()
