import pytest

from apps.singly_beam.formulas import (
    calculate_beam_geometry,
    calculate_full_design_results,
    calculate_material_properties,
    calculate_negative_bending_design,
    calculate_positive_bending_design,
    calculate_reinforcement_spacing,
    calculate_shear_design,
)
from apps.singly_beam.models import (
    BeamDesignInputSet,
    BeamType,
    MaterialPropertyMode,
    MaterialPropertySetting,
    MaterialPropertySettings,
    PositiveBendingInput,
    RebarGroupInput,
    RebarLayerInput,
    ReinforcementArrangementInput,
    ShearDesignInput,
    ShearSpacingMode,
)


def test_rebar_group_rejects_incomplete_definition() -> None:
    with pytest.raises(ValueError):
        RebarGroupInput(diameter_mm=20, count=0)


def test_rebar_layer_requires_two_corner_bars_when_corner_bars_are_used() -> None:
    with pytest.raises(ValueError):
        RebarLayerInput(
            group_a=RebarGroupInput(diameter_mm=20, count=3),
            group_b=RebarGroupInput(),
        )


def test_rebar_layer_rejects_middle_bars_without_corner_bars() -> None:
    with pytest.raises(ValueError):
        RebarLayerInput(
            group_a=RebarGroupInput(),
            group_b=RebarGroupInput(diameter_mm=16, count=2),
        )


def test_material_properties_match_standalone_defaults() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_material_properties(inputs.materials)

    assert results.ec_ksc == pytest.approx(233928.194110928)
    assert results.es_ksc == pytest.approx(2040000.0)
    assert results.modular_ratio_n == pytest.approx(8.720624753049812)
    assert results.modulus_of_rupture_fr_ksc == pytest.approx(30.983866769659336)
    assert results.beta_1 == pytest.approx(0.85)


def test_beam_geometry_matches_standalone_defaults() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_beam_geometry(
        inputs.geometry,
        inputs.positive_bending,
        inputs.negative_bending,
        inputs.shear,
        include_negative=inputs.has_negative_design,
    )

    assert results.section_area_cm2 == pytest.approx(800)
    assert results.gross_moment_of_inertia_cm4 == pytest.approx(106666.66666666667)
    assert results.positive_compression_centroid_d_prime_cm == pytest.approx(5.5)
    assert results.positive_tension_centroid_from_bottom_d_cm == pytest.approx(5.5)
    assert results.d_plus_cm == pytest.approx(34.5)
    assert results.d_minus_cm is None


def test_spacing_results_match_default_behavior() -> None:
    inputs = BeamDesignInputSet()
    spacing = calculate_reinforcement_spacing(
        inputs.geometry,
        inputs.positive_bending.tension_reinforcement,
        inputs.shear.stirrup_diameter_mm,
    )

    assert spacing.layer_1.spacing_cm == pytest.approx(3.3)
    assert spacing.layer_1.status == "OK"
    assert spacing.layer_2.status == "N/A"
    assert spacing.layer_3.status == "N/A"


def test_positive_bending_matches_standalone_defaults() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_positive_bending_design(
        inputs.materials,
        inputs.geometry,
        inputs.positive_bending,
        inputs,
    )

    assert results.phi == pytest.approx(0.9)
    assert results.as_required_cm2 == pytest.approx(3.383248620248353)
    assert results.as_provided_cm2 == pytest.approx(3.392920065876977)
    assert results.as_min_cm2 == pytest.approx(2.415)
    assert results.as_max_cm2 == pytest.approx(11.260800000000001)
    assert results.mn_kgm == pytest.approx(4456.506032607666)
    assert results.phi_mn_kgm == pytest.approx(4010.8554293468997)
    assert results.ratio == pytest.approx(0.9972934877513979)
    assert results.design_status == "PASS"


def test_positive_bending_phi_changes_when_added_tension_layers_increase_neutral_axis_depth() -> None:
    base_inputs = BeamDesignInputSet()
    heavy_tension_inputs = BeamDesignInputSet(
        positive_bending=PositiveBendingInput(
            factored_moment_kgm=base_inputs.positive_bending.factored_moment_kgm,
            compression_reinforcement=base_inputs.positive_bending.compression_reinforcement,
            tension_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=12, count=2),
                    group_b=RebarGroupInput(diameter_mm=12, count=1),
                ),
                layer_2=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=25, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=2),
                ),
                layer_3=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=25, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=2),
                ),
            ),
        )
    )

    base_results = calculate_positive_bending_design(
        base_inputs.materials,
        base_inputs.geometry,
        base_inputs.positive_bending,
        base_inputs,
    )
    heavy_results = calculate_positive_bending_design(
        heavy_tension_inputs.materials,
        heavy_tension_inputs.geometry,
        heavy_tension_inputs.positive_bending,
        heavy_tension_inputs,
    )

    assert heavy_results.as_provided_cm2 > base_results.as_provided_cm2
    assert heavy_results.c_cm > base_results.c_cm
    assert heavy_results.phi < base_results.phi


def test_shear_matches_standalone_defaults() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_shear_design(
        inputs.materials,
        inputs.geometry,
        inputs.shear,
        inputs,
    )

    assert results.phi == pytest.approx(0.75)
    assert results.vc_kg == pytest.approx(5665.40003883221)
    assert results.phi_vc_kg == pytest.approx(4249.050029124158)
    assert results.vc_max_kg == pytest.approx(1.33 * (240.0 ** 0.5) * 20.0 * 34.5)
    assert results.vc_capped_by_max is False
    assert results.vs_max_kg == pytest.approx(22447.81147461819)
    assert results.phi_vs_max_kg == pytest.approx(16835.858605963644)
    assert results.required_spacing_cm == pytest.approx(17.25)
    assert results.provided_spacing_cm == pytest.approx(15.0)
    assert results.vs_provided_kg == pytest.approx(7023.3445363653445)
    assert results.phi_vs_provided_kg == pytest.approx(5267.508402274007)
    assert results.vn_kg == pytest.approx(12688.744575197554)
    assert results.phi_vn_kg == pytest.approx(9516.558431398164)
    assert results.stirrup_spacing_cm == pytest.approx(15.0)
    assert results.capacity_ratio == pytest.approx(0.5254000210310699)
    assert results.av_cm2 == pytest.approx(1.2723450247038663)
    assert results.av_min_cm2 == pytest.approx(0.4375)
    assert results.size_effect_factor == pytest.approx(1.0)
    assert results.size_effect_applied is False
    assert results.design_status == "PASS"


def test_shear_auto_spacing_rounds_down_to_2p5_cm_steps() -> None:
    inputs = BeamDesignInputSet()

    results = calculate_shear_design(inputs.materials, inputs.geometry, inputs.shear, inputs)

    assert results.spacing_mode == ShearSpacingMode.AUTO
    assert results.required_spacing_cm == pytest.approx(17.25)
    assert results.provided_spacing_cm == pytest.approx(15.0)


def test_shear_manual_spacing_changes_phi_vs_and_can_fail_spacing_check() -> None:
    inputs = BeamDesignInputSet(
        shear=ShearDesignInput(
            factored_shear_kg=5000.0,
            stirrup_diameter_mm=9,
            legs_per_plane=2,
            spacing_mode=ShearSpacingMode.MANUAL,
            provided_spacing_cm=20.0,
        )
    )

    results = calculate_shear_design(inputs.materials, inputs.geometry, inputs.shear, inputs)

    assert results.spacing_mode == ShearSpacingMode.MANUAL
    assert results.required_spacing_cm == pytest.approx(17.25)
    assert results.provided_spacing_cm == pytest.approx(20.0)
    assert results.phi_vs_provided_kg == pytest.approx(3950.631301705505)
    assert results.phi_vn_kg == pytest.approx(8199.681330829662)
    assert results.capacity_ratio == pytest.approx(0.6097797948806492)
    assert results.design_status == "FAIL"
    assert "exceeds required spacing" in results.review_note


def test_aci318_19_shear_applies_size_effect_when_av_is_less_than_avmin() -> None:
    inputs = BeamDesignInputSet(
        shear=ShearDesignInput(
            factored_shear_kg=5000.0,
            stirrup_diameter_mm=9,
            legs_per_plane=2,
            spacing_mode=ShearSpacingMode.MANUAL,
            provided_spacing_cm=50.0,
        )
    )

    results = calculate_shear_design(inputs.materials, inputs.geometry, inputs.shear, inputs)

    expected_size_effect = (2 / (1 + ((34.5 / 2.54) / 10))) ** 0.5

    assert results.av_cm2 < results.av_min_cm2
    assert results.av_min_cm2 == pytest.approx(1.4583333333333335)
    assert results.size_effect_applied is True
    assert results.size_effect_factor == pytest.approx(expected_size_effect)
    assert results.vc_max_kg == pytest.approx(1.33 * expected_size_effect * (240.0 ** 0.5) * 20.0 * 34.5)
    assert results.vc_capped_by_max is False
    assert "Av =" in results.review_note
    assert "lambda_s" in results.review_note


def test_shear_flags_when_section_size_must_be_increased() -> None:
    inputs = BeamDesignInputSet(
        shear=ShearDesignInput(
            factored_shear_kg=30000.0,
            stirrup_diameter_mm=9,
            legs_per_plane=2,
            spacing_mode=ShearSpacingMode.AUTO,
            provided_spacing_cm=15.0,
        )
    )

    results = calculate_shear_design(inputs.materials, inputs.geometry, inputs.shear, inputs)

    assert results.design_status == "FAIL"
    assert results.section_change_required is True
    assert "Increase the beam section" in results.section_change_note


def test_negative_bending_matches_current_negative_logic() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_negative_bending_design(
        inputs.materials,
        inputs.geometry,
        inputs.negative_bending,
        inputs,
    )

    assert results.as_required_cm2 == pytest.approx(5.2177444959509245)
    assert results.as_provided_cm2 == pytest.approx(6.031857894892403)
    assert results.as_min_cm2 == pytest.approx(2.415)
    assert results.as_max_cm2 == pytest.approx(11.260800000000001)
    assert results.mn_kgm == pytest.approx(7610.565666242187)
    assert results.phi_mn_kgm == pytest.approx(6849.509099617969)
    assert results.ratio == pytest.approx(0.875975184898236)
    assert "d+" in results.review_note


def test_full_results_expose_review_flags_and_overall_status() -> None:
    results = calculate_full_design_results(BeamDesignInputSet())

    assert results.overall_status == "PASS WITH REVIEW"
    assert len(results.review_flags) >= 2


def test_simple_beam_omits_negative_results() -> None:
    inputs = BeamDesignInputSet(beam_type=BeamType.SIMPLE)

    results = calculate_full_design_results(inputs)

    assert results.negative_bending is None
    assert results.beam_geometry.d_minus_cm is None


def test_material_property_default_modes_preserve_existing_behavior() -> None:
    inputs = BeamDesignInputSet()

    default_results = calculate_material_properties(inputs.materials, inputs.material_settings)

    assert default_results.ec_ksc == pytest.approx(233928.194110928)
    assert default_results.es_ksc == pytest.approx(2040000.0)
    assert default_results.modulus_of_rupture_fr_ksc == pytest.approx(30.983866769659336)
    assert default_results.ec_mode == MaterialPropertyMode.DEFAULT
    assert default_results.es_mode == MaterialPropertyMode.DEFAULT
    assert default_results.fr_mode == MaterialPropertyMode.DEFAULT


def test_material_property_manual_overrides_apply_independently() -> None:
    inputs = BeamDesignInputSet(
        material_settings=MaterialPropertySettings(
            ec=MaterialPropertySetting(mode=MaterialPropertyMode.MANUAL, manual_value=300000.0),
            es=MaterialPropertySetting(mode=MaterialPropertyMode.DEFAULT),
            fr=MaterialPropertySetting(mode=MaterialPropertyMode.MANUAL, manual_value=35.0),
        )
    )

    results = calculate_material_properties(inputs.materials, inputs.material_settings)

    assert results.ec_ksc == pytest.approx(300000.0)
    assert results.es_ksc == pytest.approx(2040000.0)
    assert results.modulus_of_rupture_fr_ksc == pytest.approx(35.0)
    assert results.modular_ratio_n == pytest.approx(6.8)
    assert results.ec_mode == MaterialPropertyMode.MANUAL
    assert results.es_mode == MaterialPropertyMode.DEFAULT
    assert results.fr_mode == MaterialPropertyMode.MANUAL
