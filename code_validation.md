# Code Validation

## Scope

This repository now treats the beam strength workflow in two separate buckets:

- Audited for implemented scope:
  - flexure
  - shear, using the active beam-section depth selected by the current beam-type workflow
  - optional torsion
  - deflection, except for cantilever placeholder checks that remain mockup-only

The audited scope is limited to:

- rectangular reinforced-concrete beam sections
- nonprestressed members
- normalweight concrete
- the implemented beam-type section patterns: standalone cantilever, simple, simple plus cantilever, continuous, and continuous plus cantilever
- the ACI code families currently exposed by the app

## Clause Audit Matrix

| Module | Formula / Check | Governing clause basis | Status | Notes |
|---|---|---|---|---|
| Materials | `beta1` | ACI 318-99/11 `10.2.7.3`; ACI 318-14/19 `22.2.2.4.3` | Audited | Implemented directly in `engines/common/materials.py` |
| Moment | Flexural `phi` | ACI 318-99 Table `9.3.2`; ACI 318-11 Table `9.3.2.1`; ACI 318-14/19 Table `21.2.2` | Audited | Beam app uses nonprestressed flexure strain-transition logic |
| Moment | `rho_min` / `As,min` | ACI 318-99/11 `10.5.1`; ACI 318-14/19 `9.6.1.2` | Audited | Stored as ratio first, then converted to area |
| Moment | Upper reinforcement limit used as `rho_max` / `As,max` | ACI 318-99 Chapter `10` balanced-strain limit with `0.75 rho_bal`; ACI 318-11 Table `9.3.2.1` + Chapter `10`; ACI 318-14/19 Table `21.2.2` + Section `22.2` | Audited | This is a derived beam-design limit, not a native ACI symbol |
| Moment | `Mn`, `phiMn`, strain compatibility | ACI 318-99/11 Sections `10.2` and `10.3`; ACI 318-14/19/25 Sections `22.2` and `22.3` | Audited | Singly reinforced path is direct rectangular stress-block; app full-section `Doubly/AUTO` path uses a bar-depth strain-compatibility model from the compression face |
| Shear | Shear `phi` | ACI 318-99 Table `9.3.2`; ACI 318-11 Chapter `9`; ACI 318-14/19 Chapter `21` | Audited | App uses beam-member shear branch only |
| Shear | Base `Vc` expression | ACI 318-99 `11.3`; ACI 318-08/11 `11.2`; ACI 318-14 `22.5.5.1`; ACI 318-19/25 Table `22.5.5.1` | Audited | Current app keeps the simplified beam path used by the legacy workflow |
| Shear | `Av,min` and trigger | ACI 318-99 `11.5.5.1` and `11.5.5.3`; ACI 318-08/11 `11.4.6.1` and `11.4.6.3`; ACI 318-14/19/25 `9.6.3.1` | Audited | Trigger and minimum-area equation are checked separately |
| Shear | Stirrup spacing limits | ACI 318-99 `11.5.4`; ACI 318-08/11 `11.4.5`; ACI 318-14/19/25 `9.7.6.2` | Audited | Includes the app's AUTO spacing selection wrapper |
| Shear | `Vs,max` contribution limit | ACI 318-99 `11.5.6.8`; ACI 318-08/11 `11.4.7.2`; ACI 318-14/19/25 beam shear-strength limits in Chapter `9` / Chapter `22` | Audited | Implemented as the current beam section shear-steel cap |
| Shear | ACI 318-19/25 `lambda_s` size effect | ACI 318-19/25 Table `22.5.5.1` together with Section `9.6.3` | Audited | Applied only to the 2019/2025 branch |
| Shear | ACI 318-19/25 `Vc,max` cap | ACI 318-19/25 Table `22.5.5.1` | Audited | Applied only to the 2019/2025 branch |
| Torsion | Threshold torsion check | ACI 318-99 `11.6.1`; ACI 318-08/11 `11.5.1`; ACI 318-14/19/25 `22.7.4` | Audited | Clause map lives in `design/torsion` |
| Torsion | Cross-section torsion strength limit | ACI 318-99 `11.6.3.1`; ACI 318-08/11 `11.5.3.1`; ACI 318-14/19/25 `22.7.7` | Audited | Standard thin-walled tube method only |
| Torsion | Required transverse torsion steel | ACI 318-99 `11.6.3.3`; ACI 318-08/11 `11.5.3.3`; ACI 318-14/19/25 `22.7.6` | Audited | Closed stirrups only |
| Torsion | Required longitudinal torsion steel | ACI 318-99 `11.6.3.7`; ACI 318-08/11 `11.5.3.7`; ACI 318-14/19/25 `22.7.6` with minimums from `9.6.4.3` | Audited | Provided as total `Al` |
| Torsion | Minimum torsion steel | ACI 318-99 `11.6.5`; ACI 318-08/11 `11.5.5`; ACI 318-14/19/25 `9.6.4` | Audited | Implemented by code branch |
| Torsion | Torsion stirrup spacing limit | ACI 318-99 `11.6.6.1`; ACI 318-11 `11.5.6.1`; ACI 318-14/19/25 `9.7.6.3.3` | Audited | Shared closed-stirrup presentation remains app-specific |
| Torsion | Alternative procedure flag | ACI 318-19/25 `9.5.4.6` | Audited | Detection only; alternative procedure itself is not implemented |
| Deflection | Uniform-load immediate deflection workflow | ACI 318-99/11 `9.5.2`; ACI 318-14 `24.2.3`; ACI 318-19/25 `24.2.3` | Audited | Direct-calculation beam workflow with code-specific Ie routing |
| Deflection | Effective moment of inertia using cracked-section direct calculation | ACI 318-99/11 `9.5.2.3`; ACI 318-14 `24.2.3.5a`; ACI 318-19/25 Table `24.2.3.5` | Audited | ACI 318-19/25 path uses the Table `24.2.3.5` inverse Bischoff/Scanlon expression |
| Deflection | Long-term deflection multiplier | ACI 318-99/11 `9.5.2.5`; ACI 318-14/19/25 Chapter `24.2.4` | Audited for implemented workbook-based workflow | Uses the app's `x / (1 + 50 rho')` long-term multiplier input path |
| Deflection | User-selected allowable deflection limit | User-selected project serviceability limit | Audited | Engineer-selected `L / n` limit; app does not guess the project requirement |

## Hand-Calculation Appendix

The following benchmark cases were rechecked directly against the implemented formulas, not against another software package.

### 1. Shear benchmark: positive section governs

- Setup: ACI 318-19 default simple beam, `f'c = 240 ksc`, `fvy = 2400 ksc`, `b = 20 cm`, `Vu = 5000 kgf`, `phi = 0.75`
- Active shear basis: Positive section
- Geometry used in shear: `d = 34.50 cm`
- Stirrups used in the check: 2-legged `DB9` at `s = 15.0 cm`, so `Av = 1.272345 cm2`
- Manual check:
  - `Vc = 0.53 sqrt(fc') b d = 5665.400039 kg`
  - `Vs,max = 2.1 sqrt(fc') b d = 22447.811475 kg`
  - `Vs = Av fvy d / s = 7023.344536 kg`
  - `phiVn = phi [Vc + min(Vs, Vs,max)] = 9516.558431 kg`
- Program result: matches the manual values above

### 2. Shear benchmark: negative section governs

- Setup: ACI 318-19 continuous beam with heavier top negative reinforcement so the negative-region effective depth controls shear
- Active shear basis: Negative section
- Geometry used in shear: `d = 31.627778 cm`
- Stirrups used in the check: 2-legged `DB9` at `s = 15.0 cm`, so `Av = 1.272345 cm2`
- Manual check:
  - `Vc = 5193.739520 kg`
  - `Vs,max = 20578.967911 kg`
  - `Vs = 6438.631312 kg`
  - `phiVn = 8724.278124 kg`
- Program result: matches the manual values above

### 3. Shear benchmark: standalone cantilever / cantilever-negative governs

- Setup: ACI 318-19 standalone cantilever beam using the module default cantilever-negative section
- Active shear basis: Cantilever Negative section
- Geometry used in shear: `d = 34.30 cm`
- Stirrups used in the check: 2-legged `DB9` at `s = 15.0 cm`, so `Av = 1.272345 cm2`
- Manual check:
  - `Vc = 5632.557140 kg`
  - `Vs,max = 22317.679234 kg`
  - `Vs = 6982.629496 kg`
  - `phiVn = 9461.389977 kg`
- Program result: matches the manual values above

### 4. AUTO beam behavior borderline benchmark

- Setup: positive flexural section with `AUTO` beam behavior and compression reinforcement `2 + 4` bars of `DB32` in the first compression layer
- The app computes the AUTO contribution ratio as `R = 0.038731` or `3.8731%`
- This is a product heuristic, not a direct ACI section classification
- Manual logic check:
  - if `threshold = 3.85%`, then `R > threshold`, so AUTO should resolve to `Doubly`
  - if `threshold = 3.90%`, then `R < threshold`, so AUTO should resolve to `Singly`
- Program result:
  - threshold `3.85%` -> AUTO resolves to `Doubly`, `phiMn = 4172.456806 kg-m`
  - threshold `3.90%` -> AUTO resolves to `Singly`, `phiMn = 4010.855429 kg-m`

## Remaining Review Items

The following items are intentionally still marked for engineering review:

1. Cantilever deflection remains mockup-only in the current app.
2. Any member type outside the present scope, such as flanged sections, prestressed members, or special seismic detailing, remains outside this audit.

## Transparency Notes

- The audited scope above is clause-mapped in code comments and engine docstrings.
- Passing tests confirm the implemented formulas and current beam workflow remain internally consistent for the present rectangular-beam scope.
- This file does not expand the app scope beyond the items listed above.
