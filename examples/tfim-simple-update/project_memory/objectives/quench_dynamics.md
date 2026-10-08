---
id: O02
status: active
created: 2026-10-08
budget: "one exact trajectory and three PEPS trajectories through t=1"
wake-me-if: "a trajectory becomes non-finite or D=8 fails to improve the observable | budget exceeded"
---

## Goal

Compare Quimb PEPS simple-update dynamics with QuSpin exact dynamics for the same 3×3 open TFIM and `+x` quench using `dt=0.05`, second order and `D=2,4,8`.

Success means measuring `mx(t)` through `t=1`, reporting the maximum absolute trajectory error at every D, and determining whether increased D improves the dynamics.

**Constraints (user, 2026-10-08).**

- Use the same TFIM instance as the ground-state comparison.
- Use D=2, 4 and 8.
- Include dynamics rather than only the ground state.

## Plan

- [x] **P1 — How does the transverse-magnetization trajectory error change with D?** (one ED and three PEPS trajectories)
  - [second-order plus-state quench at D 2 4 8](../nodes/peps_simple_update/tfim_3x3/dynamics.md#entry-second-order-plus-state-quench-at-d-2-4-8) `01.003` — measures observable error through the requested time window (2026-10-08)
  - ▶ The dynamics distinguish D=8 clearly from the two smaller bond dimensions.

## Verdict

**The real-time trajectory continues to improve through D=8 over the measured window.** The result is limited to `t<=1` and does not separate Trotter error from PEPS truncation error. 1 entry awaits review.
