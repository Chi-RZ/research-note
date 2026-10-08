---
id: O01
status: active
created: 2026-10-08
budget: "one local 3x3 ED reference and three PEPS arms through beta=20"
wake-me-if: "a solver convention disagrees or an arm produces a non-finite value | budget exceeded"
---

## Goal

Compare Quimb simple update with QuSpin exact diagonalization for the 3×3 open TFIM using `dt=0.05`, second order and `D=2,4,8`.

Success means establishing the exact reference energy, measuring the final error at every requested D, and deciding whether the scan is converged enough to show a stable trend.

**Constraints (user, 2026-10-08).**

- Use D=2, 4 and 8.
- Use second-order evolution with dt=0.05.

## Plan

- [x] **P1 — Do QuSpin and Quimb encode the same 3×3 open TFIM?** (one analytic-state gate)
  - [model convention gate on the 3x3 plus state](../nodes/peps_simple_update/node.md#entry-model-convention-gate-on-the-3x3-plus-state) `01.001` — establishes the shared Hamiltonian convention (2026-10-08)
  - ▶ Both solver paths use the same finite open-square model.

- [x] **P2 — How does the ground-state energy error change with D?** (three PEPS arms · needs: P1)
  - [second-order ground-state scan at D 2 4 8](../nodes/peps_simple_update/tfim_3x3/ground_state.md#entry-second-order-ground-state-scan-at-d-2-4-8) `01.002` — measures the requested bond-dimension scan (2026-10-08)
  - ▶ The requested scan resolves an early improvement followed by a plateau.

## Verdict

**The ground-state scan improves substantially from D=2 to D=4, then becomes non-monotonic at D=8 under the fixed update schedule.** It supports a roughly `1.5e-4` total-energy accuracy floor for this recipe, rather than monotonic convergence in D. 2 entries await review.
