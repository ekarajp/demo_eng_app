# Engineering App Suite

Multi-tool engineering software workspace built with Python and Streamlit.

## Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the software:

```bash
streamlit run main.py
```

## Current Tools

- `Singly Beam Analysis`
  Reinforced concrete singly reinforced beam analysis and design.
- `Doubly Beam Analysis`
  Coming Soon.
- `Beam Fiber Model`
  Coming Soon.

## Engine-First Structure

The beam-calculation logic is being separated from Streamlit into reusable engine packages.
`apps/` acts as the UI layer and `engines/` acts as the calculation layer.

```text
project_root/
|- main.py
|- README.md
|- requirements.txt
|- assets/
|- core/
|  |- navigation.py
|  |- shared_models.py
|  |- state_store.py
|  |- theme.py
|  `- utils.py
|- apps/
|  |- landing_page.py
|  |- singly_beam_app.py
|  |- doubly_beam_app.py
|  |- landing/
|  |- singly_beam/
|  `- doubly_beam/
|- engines/
|  |- common/
|  |  |- __init__.py
|  |  |- geometry.py
|  |  |- materials.py
|  |  |- result_objects.py
|  |  |- units.py
|  |  `- validation.py
|  |- moment/
|  |  |- __init__.py
|  |  |- calculator.py
|  |  |- checks.py
|  |  |- formulas.py
|  |  `- inputs.py
|  |- shear/
|  |  |- __init__.py
|  |  |- calculator.py
|  |  |- checks.py
|  |  |- formulas.py
|  |  `- inputs.py
|  `- torsion/
|     |- __init__.py
|     |- calculator.py
|     |- checks.py
|     |- formulas.py
|     `- inputs.py
`- tests/
```

## Engine Usage

### Moment engine

```python
from engines.common import (
    BeamSectionInput,
    DesignCode,
    MaterialPropertiesInput,
    RebarGroupInput,
    RebarLayerInput,
    ReinforcementArrangementInput,
)
from engines.moment import MomentBeamInput, MomentDesignCase, design_moment_beam

positive_compression = ReinforcementArrangementInput(
    layer_1=RebarLayerInput(group_a=RebarGroupInput(diameter_mm=12, count=2)),
)
positive_tension = ReinforcementArrangementInput(
    layer_1=RebarLayerInput(
        group_a=RebarGroupInput(diameter_mm=12, count=2),
        group_b=RebarGroupInput(diameter_mm=12, count=1),
    ),
)

results = design_moment_beam(
    MomentBeamInput(
        design_code=DesignCode.ACI318_19,
        materials=MaterialPropertiesInput(),
        geometry=BeamSectionInput(),
        stirrup_diameter_mm=9,
        factored_moment_kgm=4000.0,
        positive_compression_reinforcement=positive_compression,
        positive_tension_reinforcement=positive_tension,
        design_case=MomentDesignCase.POSITIVE,
    )
)
```

### Shear engine

```python
from engines.common import ShearSpacingMode
from engines.shear import ShearBeamInput, design_shear_beam

results = design_shear_beam(
    ShearBeamInput(
        design_code=DesignCode.ACI318_19,
        materials=MaterialPropertiesInput(),
        geometry=BeamSectionInput(),
        factored_shear_kg=5000.0,
        stirrup_diameter_mm=9,
        legs_per_plane=2,
        spacing_mode=ShearSpacingMode.AUTO,
        provided_spacing_cm=15.0,
        positive_compression_reinforcement=positive_compression,
        positive_tension_reinforcement=positive_tension,
    )
)
```

### Torsion engine

```python
from design.torsion import (
    TorsionDemandType,
    TorsionDesignCode,
    TorsionDesignInput,
    TorsionDesignMaterialInput,
    TorsionSectionGeometryInput,
)
from engines.torsion import TorsionBeamInput, design_torsion_beam

results = design_torsion_beam(
    TorsionBeamInput(
        design=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=2500.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=12.0,
        ),
        geometry=TorsionSectionGeometryInput(
            width_cm=20.0,
            depth_cm=65.0,
            cover_cm=4.0,
            stirrup_diameter_mm=9,
            stirrup_spacing_cm=10.0,
            stirrup_legs=2,
        ),
        materials=TorsionDesignMaterialInput(
            concrete_strength_ksc=240.0,
            transverse_steel_yield_ksc=2400.0,
            longitudinal_steel_yield_ksc=4000.0,
        ),
    )
)
```

### Deflection module

```python
from design.deflection import (
    AllowableDeflectionLimitInput,
    AllowableDeflectionPreset,
    DeflectionCodeVersion,
    DeflectionDesignInput,
    DeflectionMemberType,
    DeflectionServiceLoadInput,
    DeflectionSupportCondition,
    design_deflection_check,
)

results = design_deflection_check(
    DeflectionDesignInput(
        code_version=DeflectionCodeVersion.ACI318_14,
        member_type=DeflectionMemberType.SIMPLE_BEAM,
        support_condition=DeflectionSupportCondition.SIMPLE,
        allowable_limit=AllowableDeflectionLimitInput(
            preset=AllowableDeflectionPreset.L_360,
        ),
        span_length_m=4.0,
        service_loads=DeflectionServiceLoadInput(
            dead_load_kgf_per_m=300.0,
            live_load_kgf_per_m=200.0,
            sustained_live_load_ratio=0.3,
        ),
    )
)
```

## Notes

- `apps/singly_beam/formulas.py` now acts mainly as a compatibility layer that maps app models into reusable engine packages.
- `engines/moment` and `engines/shear` contain extracted reusable calculation logic.
- `engines/torsion` is scaffolded as the public engine path and currently delegates to the existing torsion implementation under `design/torsion`.
- `design/deflection` contains the reusable deflection workflow used by the Singly Beam app.
- The structure is prepared for future engines such as development length, columns, footings, and slabs.
- The deflection module is now implemented with code-specific paths for ACI 318-99/11/14/19, including the ACI 318-19 Table 24.2.3.5 effective-moment-of-inertia path for nonprestressed members.
