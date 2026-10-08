# TFIM: Quimb simple update against QuSpin ED

This is a small, real research-note project with two objectives: ground-state
convergence and quench dynamics. Both compare PEPS simple update with exact
diagonalization for the open 3×3 transverse-field Ising model

\[
H=-J\sum_{\langle i,j\rangle} Z_i Z_j-h\sum_i X_i,
\qquad J=1,\quad h=3.
\]

QuSpin supplies the exact ground-state energy with `spin_basis_general`; the
basis labels nine spins and the coupling list supplies the 12 bonds of the 3×3
square. Quimb starts every run from the
same `+x` product state and performs imaginary-time simple update with
`dt=0.05`, fixed gate ordering and `second_order_reflect=True`. The PEPS energy
is contracted exactly on the 3×3 lattice, so the comparison does not contain a
boundary-contraction approximation.

## Reproduce it

```bash
uv sync
uv run pytest -q
uv run python -u experiments/peps_simple_update/impl/run_convergence.py \
  | tee experiments/peps_simple_update/tfim_3x3/results/run.log
uv run python -u experiments/peps_simple_update/impl/run_dynamics.py \
  | tee experiments/peps_simple_update/tfim_3x3/dynamics/run.log
```

The committed `uv.lock` pins Quimb, QuSpin and every transitive dependency.
`networkx` is explicit because Quimb's gate ordering imports it at runtime.

## Ground-state result

At the final checkpoint, β=20:

| D | Simple-update energy | absolute error from ED |
|---:|---:|---:|
| 2 | -28.073522020467 | 6.7687e-4 |
| 4 | -28.074065259227 | 1.3363e-4 |
| 8 | -28.074047747662 | 1.5114e-4 |

The exact energy is `-28.074198890889`. Increasing D from 2 to 4 reduces the
error by about 5×. D=4 and D=8 then form a roughly 1.5e-4 plateau rather than a
monotonic sequence. This is useful behavior for the example: larger D expands
the PEPS representation, but simple update is an approximate optimizer, so a
fixed update schedule does not guarantee a lower final variational energy.

## Dynamics result

The dynamics objective quenches the same `+x` product state under the same
Hamiltonian to `t=1`. It uses a second-order `X/ZZ/X` Strang split with
`dt=0.05`, compares transverse magnetization `m_x(t)` with exact QuSpin
evolution, and scans `D=2,4,8`.

| D | maximum absolute error in `m_x(t)` | `m_x(1)` |
|---:|---:|---:|
| 2 | 4.7704e-2 | 0.950179 |
| 4 | 2.5553e-2 | 0.954015 |
| 8 | 4.1395e-3 | 0.924323 |

The exact value at `t=1` is `0.928462`. Unlike the ground-state scan, the
real-time trajectory shows a clear improvement through D=8. See the committed
trajectory and figure under
`experiments/peps_simple_update/tfim_3x3/dynamics/`.

The research record under `project_memory/` keeps both goals, their recipes,
evidence, figures and conclusions. The topic-oriented `wiki/` demonstrates
how reviewed conclusions from separate objectives become shared knowledge.
