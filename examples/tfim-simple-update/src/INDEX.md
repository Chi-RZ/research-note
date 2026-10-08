# Capability Index

## Domain libraries

| Library | Import | Source to inspect | What it covers |
|---|---|---|---|
| Quimb 1.15.0 | `import quimb.tensor as qtn` | `qtn.SimpleUpdate`, `qtn.LocalHam2D` | PEPS construction, second-order simple update and exact 3×3 contraction |
| QuSpin 1.0.1 | `from quspin.operators import hamiltonian` | `spin_basis_general`, `hamiltonian` | Geometry-neutral full-basis ED; the 3×3 square comes from the coupling list |

## Modules

| Module | API | What it does |
|---|---|---|
| `tfim_compare.model` | `square_bonds`, `quspin_hamiltonian`, `ed_ground_energy`, `quimb_hamiltonian`, `initial_peps` | Defines one open-boundary TFIM convention for ground-state and real-time comparisons |
