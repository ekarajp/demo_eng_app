# Code Validation

## Scope

This repository now treats the beam strength workflow in two separate buckets:

- Audited for implemented scope:
  - flexure
  - shear
  - optional torsion
  - deflection, except for cantilever mockup-only placeholders

The audited scope is limited to:

- rectangular reinforced-concrete beam sections
- nonprestressed members
- normalweight concrete
- the ACI code families currently exposed by the app

## Clause Audit Matrix

| Module | Formula / Check | Governing clause basis | Status | Notes |
|---|---|---|---|---|
| Materials | `beta1` | ACI 318-99/11 `10.2.7.3`; ACI 318-14/19 `22.2.2.4.3` | Audited | Implemented directly in `engines/common/materials.py` |
| Moment | Flexural `phi` | ACI 318-99 Table `9.3.2`; ACI 318-11 Table `9.3.2.1`; ACI 318-14/19 Table `21.2.2` | Audited | Beam app uses nonprestressed flexure strain-transition logic |
| Moment | `rho_min` / `As,min` | ACI 318-99/11 `10.5.1`; ACI 318-14/19 `9.6.1.2` | Audited | Stored as ratio first, then converted to area |
| Moment | Upper reinforcement limit used as `rho_max` / `As,max` | ACI 318-99 Chapter `10` balanced-strain limit with `0.75 rho_bal`; ACI 318-11 Table `9.3.2.1` + Chapter `10`; ACI 318-14/19 Table `21.2.2` + Section `22.2` | Audited | This is a derived beam-design limit, not a native ACI symbol |
| Moment | `Mn`, `phiMn`, strain compatibility | ACI 318-99/11 Sections `10.2` and `10.3`; ACI 318-14/19 Sections `22.2` and `22.3` | Audited | Rectangular stress-block assumptions only |
| Shear | Shear `phi` | ACI 318-99 Table `9.3.2`; ACI 318-11 Chapter `9`; ACI 318-14/19 Chapter `21` | Audited | App uses beam-member shear branch only |
| Shear | Base `Vc` expression | ACI 318-99/11 `11.3`; ACI 318-14 `22.5.5.1`; ACI 318-19 Table `22.5.5.1` | Audited | Current app keeps the simplified beam path used by the legacy workflow |
| Shear | `Av,min` | ACI 318-99/11 `11.4.6.3`; ACI 318-14/19 `9.6.3` | Audited | Evaluated at the provided spacing used by the app |
| Shear | Stirrup spacing limits | ACI 318-99/11 `11.4.5`; ACI 318-14/19 `9.7.6.2` | Audited | Includes the app's AUTO spacing selection wrapper |
| Shear | `Vs,max` contribution limit | ACI 318-99/11 `11.4.7.2`; ACI 318-14/19 beam shear-strength limits in Chapter `9` / Chapter `22` | Audited | Implemented as the current beam section shear-steel cap |
| Shear | ACI 318-19 `lambda_s` size effect | ACI 318-19 Table `22.5.5.1` and ACI FAQ on Table `22.5.5.1` with `Av < Av,min` and Section `9.6.3` | Audited | Applied only to the 2019 branch |
| Shear | ACI 318-19 `Vc,max` cap | ACI 318-19 Table `22.5.5.1` | Audited | Applied only to the 2019 branch |
| Torsion | Threshold torsion check | ACI 318-99 `11.6.1`; ACI 318-11 `11.5.1`; ACI 318-14/19 `22.7.4` | Audited | Clause map lives in `design/torsion` |
| Torsion | Cross-section torsion strength limit | ACI 318-99 `11.6.3.1`; ACI 318-11 `11.5.3.1`; ACI 318-14/19 `22.7.7` | Audited | Standard thin-walled tube method only |
| Torsion | Required transverse torsion steel | ACI 318-99 `11.6.3.3`; ACI 318-11 `11.5.3.3`; ACI 318-14/19 `22.7.6` | Audited | Closed stirrups only |
| Torsion | Required longitudinal torsion steel | ACI 318-99 `11.6.3.7`; ACI 318-11 `11.5.3.7`; ACI 318-14/19 `22.7.6` with minimums from `9.6.4.3` | Audited | Provided as total `Al` |
| Torsion | Minimum torsion steel | ACI 318-99 `11.6.5`; ACI 318-11 `11.5.5`; ACI 318-14/19 `9.6.4` | Audited | Implemented by code branch |
| Torsion | Torsion stirrup spacing limit | ACI 318-99 `11.6.6.1`; ACI 318-11 `11.5.6.1`; ACI 318-14/19 `25.7.1.2` | Audited | Shared closed-stirrup presentation remains app-specific |
| Torsion | Alternative procedure flag | ACI 318-19 `9.5.4.6` | Audited | Detection only; alternative procedure itself is not implemented |
| Deflection | Uniform-load immediate deflection workflow | ACI 318-99/11 `9.5.2`; ACI 318-14 `24.2.3`; ACI 318-19 `24.2.3` | Audited | Direct-calculation beam workflow with code-specific Ie routing |
| Deflection | Effective moment of inertia using cracked-section direct calculation | ACI 318-99/11 `9.5.2.3`; ACI 318-14 `24.2.3.5a`; ACI 318-19 Table `24.2.3.5` | Audited | ACI 318-19 path uses the Table `24.2.3.5` inverse Bischoff/Scanlon expression |
| Deflection | Long-term deflection multiplier | ACI 318-99/11 `9.5.2.5`; ACI 318-14/19 Chapter `24.2.4` | Audited for implemented workbook-based workflow | Uses the app's `x / (1 + 50 rho')` long-term multiplier input path |
| Deflection | User-selected allowable deflection limit | User-selected project serviceability limit | Audited | Engineer-selected `L / n` limit; app does not guess the project requirement |

## Remaining Review Items

The following items are intentionally still marked for engineering review:

1. Cantilever deflection remains mockup-only in the current app.
2. Any member type outside the present scope, such as flanged sections, prestressed members, or special seismic detailing, remains outside this audit.

## Transparency Notes

- The audited scope above is clause-mapped in code comments and engine docstrings.
- Passing tests confirm the implemented formulas and current beam workflow remain internally consistent.
- This file does not expand the app scope beyond the items listed above.
