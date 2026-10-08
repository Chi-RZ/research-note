---
topic: open-questions
type: open
tags: [tensor-networks, tfim, validation]
status: compiled
updated: 2026-10-08
sources:
  - tag: "peps_simple_update/tfim_3x3: second-order ground-state scan at D 2 4 8"
    id: "01.002"
    hash: b5271c32adb26f42
  - tag: "peps_simple_update/tfim_3x3: second-order plus-state quench at D 2 4 8"
    id: "01.003"
    hash: ece2a7b7e83d2e4c
---

# Open questions

## Bond dimension beyond D=8

The fixed ground-state schedule reached a non-monotonic error plateau at D=8,
so the existing scan does not establish whether increasing D further restores
monotonic improvement. `peps_simple_update/tfim_3x3: second-order ground-state scan at D 2 4 8`

## Real-time error attribution

The transverse-magnetization trajectory improved through D=8 over the measured
window, but the result does not separate second-order timestep error from PEPS
truncation error. `peps_simple_update/tfim_3x3: second-order plus-state quench at D 2 4 8`

## Related

- [Simple-update validation](simple-update-validation.md) gives the method that exposed these limits.
- [Knowledge index](index.md) routes to the complete project taxonomy.
