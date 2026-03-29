# Code Validation

## Scope

This project reconstructs the engineering workflow from `Beam Test.xlsx` into Python code. The implementation prioritizes:

- workbook traceability
- explicit engineering warnings
- maintainable modular structure

The repository does **not** claim full code compliance. Any formula not independently checked against the governing design standard is marked accordingly.

## Governing Assumptions Used

- Flexural and shear expressions follow the workbook logic and ACI-style equations embedded in the spreadsheet.
- Units are preserved exactly as the workbook uses them:
  - stress in `ksc`
  - moments in `kg-m`
  - forces in `kg`
  - dimensions in `cm` and `mm`
- Negative-moment design reproduces workbook behavior even where that behavior is suspicious.

## Verification Status Matrix

| Formula / Check | Implemented Logic | Source | Status | Notes |
|---|---|---|---|---|
| `Ec = 15100 * sqrt(fc')` | Direct Python implementation | Workbook | Verified against Excel only | Matches workbook outputs |
| `Es = 2.04 * 10^6` | Constant | Workbook | Verified against Excel only | Matches workbook outputs |
| `n = Es / Ec` | Direct Python implementation | Workbook | Verified against Excel only | Matches workbook outputs |
| `fr = 2 * sqrt(fc')` | Direct Python implementation | Workbook | Verified against Excel only | Matches workbook outputs |
| `beta1` transition logic | Workbook branch logic | Workbook / ACI-style expression | Needs manual engineering review | Clause-level review still required |
| Reinforcement centroid logic | Layer-by-layer centroid from face | Workbook | Verified against Excel only | Matches workbook defaults and workbook outputs |
| Clear spacing checks | Layer-by-layer clear spacing | Workbook | Verified against Excel only | Warning messages implemented |
| Positive `rho_min` / `rho_max` | Code-year branch logic | Workbook / ACI-style expression | Needs manual engineering review | Workbook matched, external clause audit pending |
| Positive `As_required` / `As_provided` | Direct Python implementation | Workbook | Verified against Excel only | Matches workbook outputs |
| Positive `Mn` / `phiMn` | Direct Python implementation | Workbook | Verified against Excel only | Matches workbook outputs |
| Shear `Vc`, `phiVc`, `Av`, spacing limits | Direct Python implementation | Workbook / ACI-style expression | Needs manual engineering review | Workbook matched, code clauses not fully audited |
| Negative `As_required` / `As_provided` | Direct Python implementation | Workbook | Verified against Excel only | Matches workbook outputs |
| Negative `As_min` | Uses `d+` per workbook | Workbook | Needs manual engineering review | Suspicious for real design work |
| Negative `Mn` / `phiMn` | Uses `d+` per workbook | Workbook | Needs manual engineering review | Reproduced intentionally for traceability |
| Deflection block | Placeholder only | Workbook | Needs manual engineering review | Not reconstructed yet |

## Discrepancies Between Workbook Logic and Preferred Engineering Interpretation

1. Negative-moment `As_min` uses `d+` from the positive block in the workbook.
2. Negative-moment `Mn` also uses `d+` in the workbook instead of a clearly independent negative effective depth.
3. Deflection is present in the workbook but not yet fully reconstructed in code.

## Checks Included in the Codebase

- material property calculations
- beta1 logic
- reinforcement centroid logic
- effective depth calculations
- reinforcement area limits
- flexural strength calculations
- shear reinforcement spacing calculations
- workbook comparison report
- regression-style tests for workbook defaults

## Items Requiring Manual Engineering Review

- clause-by-clause confirmation for each ACI code branch
- negative-moment workbook quirks
- deflection logic
- any project-specific detailing checks beyond workbook scope

## Transparency Notes

- The UI and report explicitly surface review flags.
- The verifier compares Python outputs to Excel outputs without hardcoding final Excel answers.
- Passing tests only means the Python code matches the current implementation intent; it does not certify design compliance.
