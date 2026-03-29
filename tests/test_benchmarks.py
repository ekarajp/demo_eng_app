import pytest

from apps.singly_beam.formulas import calculate_material_properties, calculate_positive_bending_design, calculate_shear_design
from apps.singly_beam.models import (
    BeamDesignInputSet,
    BeamGeometryInput,
    MaterialPropertiesInput,
    PositiveBendingInput,
    ProjectMetadata,
    ReinforcementArrangementInput,
    RebarGroupInput,
    RebarLayerInput,
    ShearDesignInput,
    ShearSpacingMode,
)


def test_material_benchmark_is_hand_traceable() -> None:
    materials = MaterialPropertiesInput(concrete_strength_ksc=280.0, main_steel_yield_ksc=4200.0, shear_steel_yield_ksc=4200.0)
    results = calculate_material_properties(materials)

    assert results.ec_ksc == pytest.approx(252671.32801329083)
    assert results.modulus_of_rupture_fr_ksc == pytest.approx(33.46640106136302)
    assert results.beta_1 == pytest.approx(0.85)


def test_positive_moment_benchmark() -> None:
    inputs = BeamDesignInputSet(
        metadata=ProjectMetadata(),
        materials=MaterialPropertiesInput(concrete_strength_ksc=240.0, main_steel_yield_ksc=4000.0, shear_steel_yield_ksc=4000.0),
        geometry=BeamGeometryInput(width_cm=25.0, depth_cm=50.0, cover_cm=4.0, minimum_clear_spacing_cm=2.5),
        positive_bending=PositiveBendingInput(
            factored_moment_kgm=2500.0,
            tension_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=20, count=2),
                    group_b=RebarGroupInput(diameter_mm=20, count=1),
                ),
            ),
        ),
        shear=ShearDesignInput(factored_shear_kg=2000.0, stirrup_diameter_mm=10, legs_per_plane=2),
    )

    results = calculate_positive_bending_design(inputs.materials, inputs.geometry, inputs.positive_bending, inputs)

    assert results.as_required_cm2 > 0
    assert results.as_provided_cm2 == pytest.approx(9.42477796076938)
    assert results.mn_kgm > inputs.positive_bending.factored_moment_kgm


def test_shear_benchmark_spacing_limit() -> None:
    inputs = BeamDesignInputSet(
        geometry=BeamGeometryInput(width_cm=30.0, depth_cm=60.0, cover_cm=4.0, minimum_clear_spacing_cm=2.5),
        shear=ShearDesignInput(
            factored_shear_kg=12000.0,
            stirrup_diameter_mm=10,
            legs_per_plane=2,
            spacing_mode=ShearSpacingMode.AUTO,
            provided_spacing_cm=15.0,
        ),
    )

    results = calculate_shear_design(inputs.materials, inputs.geometry, inputs.shear, inputs)

    assert results.required_spacing_cm <= results.s_max_from_av_cm
    assert results.required_spacing_cm <= results.s_max_from_vs_cm
    assert results.provided_spacing_cm <= results.required_spacing_cm
