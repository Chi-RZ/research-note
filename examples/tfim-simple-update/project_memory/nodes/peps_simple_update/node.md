---
node: peps_simple_update
task: Validate the shared TFIM convention before using PEPS simple update
---

### Entry: model convention gate on the 3x3 plus state
- **Id:** 01.001
- **Status:** closed
- **Date:** 2026-10-08 13:00
- **Code:** `research-note@4948d89`
- **Motivation:** The analytic calculation found "the `+x` product state has energy `-hN=-27` for the 3×3 open TFIM"; do QuSpin and Quimb reproduce this value within `1e-12`?
- **Recipe:** {Lx: 3, Ly: 3, boundary: open, J: 1.0, h: 3.0, initial_state: +x product, tolerance: 1e-12}
- **Facts:** We evaluated the analytic state with both Hamiltonian implementations using [validate_model.py](../../../experiments/peps_simple_update/impl/validate_model.py); evidence [log](../../../experiments/peps_simple_update/tfim_3x3/gate/run.log) and [JSON](../../../experiments/peps_simple_update/tfim_3x3/gate/model.json).

  | route | energy | absolute difference between solvers |
  |---|---:|---:|
  | analytic | -27.000000000000000 | — |
  | QuSpin | -26.999999999999996 | 3.55e-15 |
  | Quimb | -27.000000000000000 | 3.55e-15 |

- **Conclusion:** The result shows the two implementations share the intended 12-bond open-square convention, because their `+x` energies differ by `3.55e-15`, below `1e-12`; this answers the motivation for this 3×3 model.
