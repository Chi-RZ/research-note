"""Compare a second-order PEPS quench with exact real-time evolution."""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import quimb as qu
from quimb.tensor.circuit.peps import CircuitPEPSSimpleUpdate
from quspin.basis import spin_basis_general
from quspin.operators import hamiltonian
from scipy.sparse.linalg import expm_multiply

from tfim_compare import quspin_hamiltonian, square_bonds

LX = 3
LY = 3
NSITES = LX * LY
COUPLING = 1.0
FIELD = 3.0
DT = 0.05
T_MAX = 1.0
MEASURE_EVERY = 2
BOND_DIMENSIONS = (2, 4, 8)
CUTOFF = 1e-12

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent / "tfim_3x3" / "dynamics"


def exact_trajectory(times: np.ndarray) -> np.ndarray:
    """Return exact transverse magnetization after the ``+x`` quench."""
    ham = quspin_hamiltonian(LX, LY, COUPLING, FIELD)
    basis = spin_basis_general(N=NSITES, pauli=1)
    mx_op = hamiltonian(
        [["x", [[1.0 / NSITES, site] for site in range(NSITES)]]],
        [],
        basis=basis,
        dtype=np.float64,
        check_herm=False,
        check_symm=False,
        check_pcon=False,
    )
    psi0 = np.ones(basis.Ns, dtype=np.complex128) / np.sqrt(basis.Ns)
    states = expm_multiply(
        -1j * ham.tocsr(),
        psi0,
        start=float(times[0]),
        stop=float(times[-1]),
        num=len(times),
        endpoint=True,
    )
    return np.asarray(
        [np.vdot(psi, mx_op.dot(psi)).real for psi in states], dtype=float
    )


def gates():
    """Return the two factors of one Strang-split time step."""
    x = qu.pauli("X")
    z = qu.pauli("Z")
    x_half = qu.expm(1j * FIELD * DT / 2 * x)
    zz_full = qu.expm(1j * COUPLING * DT * qu.kron(z, z))
    return x, x_half, zz_full


def magnetization(circuit, x) -> float:
    """Exactly contract the finite PEPS measurement."""
    terms = {(site,): x for site in range(NSITES)}
    value = circuit.psi.compute_local_expectation_exact(terms, optimize="greedy")
    return float(np.real_if_close(value / NSITES))


def simple_update_trajectory(bond_dimension: int, measurement_steps: set[int]):
    """Apply second-order gates and retain bonds up to ``bond_dimension``."""
    x, x_half, zz_full = gates()
    circuit = CircuitPEPSSimpleUpdate(
        N=NSITES,
        edges=square_bonds(LX, LY),
        max_bond=bond_dimension,
        cutoff=CUTOFF,
        # Without local renormalization the simple-update gauges overflow
        # during repeated real-time gates even though each gate is unitary.
        renorm=True,
    )
    for site in range(NSITES):
        circuit.apply_gate(qu.hadamard(), site)

    rows = [{"step": 0, "time": 0.0, "mx": magnetization(circuit, x)}]
    total_steps = round(T_MAX / DT)
    for step in range(1, total_steps + 1):
        for site in range(NSITES):
            circuit.apply_gate(x_half, site)
        for site_a, site_b in square_bonds(LX, LY):
            circuit.apply_gate(zz_full, site_a, site_b)
        for site in range(NSITES):
            circuit.apply_gate(x_half, site)
        if step in measurement_steps:
            rows.append(
                {
                    "step": step,
                    "time": step * DT,
                    "mx": magnetization(circuit, x),
                }
            )
    return rows


def save_plot(rows: list[dict], exact_rows: list[dict]) -> None:
    figure = OUTPUT / "magnetization.svg"
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.plot(
        [row["time"] for row in exact_rows],
        [row["mx"] for row in exact_rows],
        color="black",
        linewidth=2,
        label="QuSpin ED",
    )
    for bond_dimension in BOND_DIMENSIONS:
        selected = [row for row in rows if row["D"] == bond_dimension]
        ax.plot(
            [row["time"] for row in selected],
            [row["mx"] for row in selected],
            marker="o",
            markersize=3,
            label=f"Quimb D={bond_dimension}",
        )
    ax.set_xlabel("time")
    ax.set_ylabel(r"$m_x(t)$")
    ax.set_title("3×3 OBC TFIM quench, second order, dt=0.05")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(figure)
    plt.close(fig)
    text = figure.read_text(encoding="utf-8")
    figure.write_text(
        "\n".join(line.rstrip() for line in text.splitlines()) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    total_steps = round(T_MAX / DT)
    measurement_steps = set(range(0, total_steps + 1, MEASURE_EVERY))
    times = np.asarray(sorted(step * DT for step in measurement_steps))
    exact_mx = exact_trajectory(times)
    exact_rows = [
        {"time": float(t), "mx": float(mx)} for t, mx in zip(times, exact_mx)
    ]

    rows = []
    summaries = []
    for bond_dimension in BOND_DIMENSIONS:
        start = time.perf_counter()
        trajectory = simple_update_trajectory(bond_dimension, measurement_steps)
        for row, exact in zip(trajectory, exact_rows):
            row.update(
                {
                    "D": bond_dimension,
                    "mx_ed": exact["mx"],
                    "abs_error": abs(row["mx"] - exact["mx"]),
                }
            )
            rows.append(row)
            print(json.dumps(row))
        summary = {
            "D": bond_dimension,
            "max_abs_error": max(row["abs_error"] for row in trajectory),
            "final_mx": trajectory[-1]["mx"],
            "elapsed_seconds": time.perf_counter() - start,
        }
        summaries.append(summary)
        print(json.dumps(summary))

    payload = {
        "parameters": {
            "Lx": LX,
            "Ly": LY,
            "boundary": "open",
            "J": COUPLING,
            "h": FIELD,
            "initial_state": "+x product state",
            "dt": DT,
            "t_max": T_MAX,
            "measure_every_steps": MEASURE_EVERY,
            "trotter": "second-order X/ZZ/X Strang split",
            "cutoff": CUTOFF,
            "measurement": "exact PEPS contraction",
        },
        "exact": exact_rows,
        "rows": rows,
        "summaries": summaries,
    }
    (OUTPUT / "magnetization.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    save_plot(rows, exact_rows)


if __name__ == "__main__":
    main()
