# Knowledge schema

This schema was derived from the three closed TFIM benchmark entries on
2026-10-08. Sources are routed into the pages below; new sources do not create
pages unless the user approves a schema change.

## Declared page types

- `method` — a reusable procedure, including its requirements and cost.
- `open` — unresolved questions and known limits.

## Controlled tags

- `exact-diagonalization`
- `tensor-networks`
- `tfim`
- `validation`

## Declared pages

| page | type | coverage | admission signal |
|---|---|---|---|
| [Simple-update validation](simple-update-validation.md) | `method` | Validate a finite-PEPS simple-update calculation against exact diagonalization across model convention, ground state and dynamics. | Three closed questions share one validation procedure. |
| [Open questions](open-questions.md) | `open` | Track the convergence and error-separation limits left unresolved by the benchmark. | Two closed conclusions state explicit boundaries. |

## Deliberately retained as tags

`tfim` names the present benchmark family rather than a standalone concept
page. `exact-diagonalization` and `tensor-networks` identify the two numerical
families but currently support one shared validation method, not separate
concept pages.
