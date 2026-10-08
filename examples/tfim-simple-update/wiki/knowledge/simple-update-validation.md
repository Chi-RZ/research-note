---
topic: simple-update-validation
type: method
tags: [exact-diagonalization, tensor-networks, tfim, validation]
status: compiled
updated: 2026-10-08
sources:
  - tag: "peps_simple_update: model convention gate on the 3x3 plus state"
    id: "01.001"
    hash: 73114566b5f7a966
  - tag: "peps_simple_update/tfim_3x3: second-order ground-state scan at D 2 4 8"
    id: "01.002"
    hash: b5271c32adb26f42
  - tag: "peps_simple_update/tfim_3x3: second-order plus-state quench at D 2 4 8"
    id: "01.003"
    hash: ece2a7b7e83d2e4c
---

# Simple-update validation

## Establish the shared model first

An exact-to-PEPS comparison needs an analytic state gate before either
convergence scan is interpreted. For the open 3×3 TFIM, the `+x` state showed
that the QuSpin and Quimb Hamiltonians used the same 12-bond convention to
within `3.55e-15`. `peps_simple_update: model convention gate on the 3x3 plus state`

## Validate each target quantity

A larger PEPS bond dimension did not guarantee a lower final ground-state
energy under one fixed simple-update schedule. The energy error improved by
about fivefold from D=2 to D=4, then reached a non-monotonic plateau near
`1.5e-4` at D=8. `peps_simple_update/tfim_3x3: second-order ground-state scan at D 2 4 8`

The same bond-dimension scan gave a different answer for real-time transverse
magnetization: its maximum trajectory error continued to fall through D=8.
Ground-state convergence therefore cannot stand in for a dynamics validation,
even when both calculations use the same model and bond dimensions.
`peps_simple_update/tfim_3x3: second-order plus-state quench at D 2 4 8`

## Procedure and cost

The reusable procedure has three parts: establish a cheap state whose expected
value is known in both implementations, compute an exact reference for the
target quantity, and repeat the approximate calculation across the requested
bond dimensions. Each new objective pays for its own reference trajectory or
energy and its own D scan because convergence is quantity-dependent.
`peps_simple_update: model convention gate on the 3x3 plus state`
`peps_simple_update/tfim_3x3: second-order ground-state scan at D 2 4 8`
`peps_simple_update/tfim_3x3: second-order plus-state quench at D 2 4 8`

The current procedure establishes behavior only for the tested schedule and
window. Its remaining limits are tracked in [Open questions](open-questions.md).
`peps_simple_update/tfim_3x3: second-order ground-state scan at D 2 4 8`
`peps_simple_update/tfim_3x3: second-order plus-state quench at D 2 4 8`

## Related

- [Open questions](open-questions.md) identifies which convergence claims this method has not settled.
- [Knowledge index](index.md) routes to the complete project taxonomy.
