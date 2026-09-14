# Benchmark knowledge — verification strategies by task type

Read by `/benchmark` when planning. One entry per task type: what the
rigorous reference is, which checks actually catch bugs, and the order to
run them in.

This file is the AGENT layer's accumulated verification experience, pooled
across every project family that shares this framework — an entry whose task
type this project never meets simply goes unread, and costs nothing. Domain
BINDINGS (role names, the environment roster) live in project files; hard-won
strategy lives here.

## Decoder benchmarks (stabilizer codes, DEM-based)
- **Decoder-platform benchmark** (new DEM builders / decoder registrations, no ED
  reference): verify in three stages — (1) DEM invariants by pytest (shapes,
  2k observables, priors, annotations); (2) classical-anchor sanity via *internal
  ordering* (bp < bposd-weak < bposd-strong) — absolute published/lab LERs only
  transfer within the SAME noise convention, never across code_capacity vs
  depolarizing; (3) learned decoder: trained vs untrained vs classical reference
  on *identical* eval shots (same seed). (Q-001a)
- **Universal decoder gate — two codes.** EVERY new decoder node's first page
  is the correctness gate: **repetition_code_capacity(d=3) AND
  steane_code_capacity(d=3), both at p=0.05, 500_000 shots**, before any
  research environment. Both ML optima are exactly computable, so the pass
  criterion is a hard number, not a judgement call. Per cell: measured block
  LER must be **>= the analytic ML optimum** (below is impossible -> a leak in
  the decoder or a bound error, report loudly) **and ~ it** (>> means broken or
  undertrained). The two codes check different things and neither is sufficient
  alone: **repetition** exercises single-sector plumbing on a trivial chain
  (majority vote / MWPM is the exact optimum, ml_optimum 0.00725); **Steane**
  adds two anticommuting sectors + real message passing on a non-graphlike
  Tanner graph with 2 observables (exhaustive ML block bound, ml_optimum
  0.08125) — it catches a broken Z path or failed message passing that
  repetition passes. Its value is that the problem is easy enough that
  "undertrained" stops being a credible excuse: a decoder that misses the
  optimum here is *wrong*, which is the one thing LER on a hard code cannot
  tell you — there, a bad number is degenerate between a code bug, weak
  training, and an architecture ceiling. Gate first, measure second.
  (2026-07-22)

## PEPS/MPS-SMA excitation machinery at enumerable size (<= 16 spins)

Reference ladder, cheapest-first — each rung catches a different class of bug:
1. **Amplitude identity**: rebuild the pipeline's own amplitudes by an
   independent route and compare (e.g. `M0 @ t` from an identity-basis
   enumeration vs `PEPS.amp_shift_basis`). Catches index-order and
   tensor-flattening errors, which otherwise look like physics. Expect 1e-15.
2. **Local matrices vs the TN route at EXACT settings** (`effect_N`/`effect_H`
   with `max_bond=None`), never against stored production matrices: at chi=64 /
   `max_separation=1` the production boundary contraction sits ~1e-6 from exact
   at 4x4 D=4, so a stored-matrix comparison measures the approximation, not
   your code. Report that gap, gate on the exact one.
3. **Translation covariance** of enumerated eff_N under the FULL 2D group
   (Z_Lx x Z_Ly), and confirm the 1D roll (Z_N) FAILS — the positive control
   alone does not distinguish them (Q-002a).
4. **Element-wise reproduction** of a stored exact-enumeration eff_H/eff_N,
   with the M-vs-M^T orientation checked explicitly before declaring any
   discrepancy (Q-002a storage-convention gotcha).
5. **ED floor per momentum sector** on ABSOLUTE energies. Carry `k_eff >= 2`:
   at a k that also hosts the ground state, a level below the sector's SECOND
   ED eigenvalue means GS contamination, not a good result.
6. **tol sensitivity, then freeze**: enumerated (noise-free) matrices tolerate
   tol -> 1e-10..1e-12; the aggressive cuts needed for sampled data (3e-1)
   move the band by ~5e-2 and will swamp whatever effect you are hunting.
   Sweep once, freeze the value, and record what the loose cut costs.

For a scheme whose whole claim is an operator identity (e.g. "dressing the
basis == rotating H"), verify that identity NUMERICALLY at full system size by
computing both sides independently — it is the one check that certifies the
idea rather than the implementation.
