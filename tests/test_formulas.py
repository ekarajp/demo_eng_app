import pytest

from apps.rc_beam.formulas import (
    _auto_select_spacing_cm,
    _combined_shear_torsion_cross_section_clause,
    _shear_minimum_clause_reference,
    _shear_reinforcement_clause_reference,
    _shear_strength_clause_reference,
    _torsion_cross_section_clause_reference,
    _torsion_spacing_clause_reference,
    calculate_beam_geometry,
    calculate_full_design_results,
    calculate_material_properties,
    calculate_negative_bending_design,
    calculate_positive_bending_design,
    calculate_reinforcement_spacing,
    calculate_shear_design,
    flexural_phi_chart_points,
)
from apps.rc_beam.report_builder import build_report_sections
from apps.rc_beam.report_builder import build_print_report_sections
from apps.rc_beam.models import (
    BeamBehaviorMode,
    BeamDesignInputSet,
    BeamType,
    DeflectionCheckInput,
    MaterialPropertyMode,
    MaterialPropertySetting,
    MaterialPropertySettings,
    NegativeBendingInput,
    PositiveBendingInput,
    RebarGroupInput,
    RebarLayerInput,
    ReinforcementArrangementInput,
    ShearDesignInput,
    ShearSpacingMode,
)
from design.deflection import DeflectionCodeVersion, DeflectionMemberType, DeflectionSupportCondition
from design.torsion import TorsionDemandType, TorsionDesignCode, TorsionDesignInput
from engines.common import DesignCode


def _heavy_beam_behavior_inputs(mode: BeamBehaviorMode) -> BeamDesignInputSet:
    return BeamDesignInputSet(
        beam_behavior_mode=mode,
        positive_bending=PositiveBendingInput(
            factored_moment_kgm=4000.0,
            compression_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=25, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=2),
                ),
                layer_2=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=25, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=2),
                ),
            ),
            tension_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=25, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=2),
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
        ),
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


def test_beam_geometry_includes_third_tension_layer_in_effective_depth() -> None:
    inputs = BeamDesignInputSet(
        positive_bending=PositiveBendingInput(
            tension_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=20, count=2),
                    group_b=RebarGroupInput(),
                ),
                layer_2=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=20, count=2),
                    group_b=RebarGroupInput(),
                ),
                layer_3=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=20, count=2),
                    group_b=RebarGroupInput(),
                ),
            ),
        )
    )

    results = calculate_beam_geometry(
        inputs.geometry,
        inputs.positive_bending,
        inputs.negative_bending,
        inputs.shear,
        include_negative=inputs.has_negative_design,
    )

    assert results.positive_tension_centroid_from_bottom_d_cm == pytest.approx(10.4)
    assert results.d_plus_cm == pytest.approx(29.6)


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
    assert results.as_max_cm2 == pytest.approx(11.272067733990145)
    assert results.mn_kgm == pytest.approx(4456.506032607666)
    assert results.phi_mn_kgm == pytest.approx(4010.8554293468997)
    assert results.ratio == pytest.approx(0.9972934877513979)
    assert results.design_status == "PASS"


def test_auto_beam_behavior_defaults_to_compression_ignored_mode_when_contribution_is_small() -> None:
    inputs = BeamDesignInputSet()

    results = calculate_positive_bending_design(
        inputs.materials,
        inputs.geometry,
        inputs.positive_bending,
        inputs,
    )

    assert results.beam_behavior_mode == BeamBehaviorMode.AUTO.value
    assert results.effective_beam_behavior == BeamBehaviorMode.SINGLY.value
    assert results.auto_result == BeamBehaviorMode.SINGLY.value
    assert results.behavior_contribution_ratio_r > 0.0
    assert results.behavior_contribution_ratio_r < results.behavior_threshold_r
    assert results.behavior_threshold_r == pytest.approx(0.05)


def test_auto_beam_behavior_classifies_full_flexure_mode_when_compression_steel_is_significant() -> None:
    inputs = _heavy_beam_behavior_inputs(BeamBehaviorMode.AUTO)

    results = calculate_positive_bending_design(
        inputs.materials,
        inputs.geometry,
        inputs.positive_bending,
        inputs,
    )

    assert results.beam_behavior_mode == BeamBehaviorMode.AUTO.value
    assert results.effective_beam_behavior == BeamBehaviorMode.DOUBLY.value
    assert results.auto_result == BeamBehaviorMode.DOUBLY.value
    assert results.mn_full_kgm > results.mn_single_kgm
    assert results.behavior_contribution_ratio_r == pytest.approx(1.0)
    assert results.behavior_contribution_ratio_r > results.behavior_threshold_r


def test_explicit_beam_behavior_modes_override_auto_classification() -> None:
    compression_ignored_inputs = _heavy_beam_behavior_inputs(BeamBehaviorMode.SINGLY)
    full_flexure_inputs = _heavy_beam_behavior_inputs(BeamBehaviorMode.DOUBLY)

    compression_ignored_results = calculate_positive_bending_design(
        compression_ignored_inputs.materials,
        compression_ignored_inputs.geometry,
        compression_ignored_inputs.positive_bending,
        compression_ignored_inputs,
    )
    full_flexure_results = calculate_positive_bending_design(
        full_flexure_inputs.materials,
        full_flexure_inputs.geometry,
        full_flexure_inputs.positive_bending,
        full_flexure_inputs,
    )

    assert compression_ignored_results.effective_beam_behavior == BeamBehaviorMode.SINGLY.value
    assert compression_ignored_results.auto_result == ""
    assert compression_ignored_results.mn_kgm == pytest.approx(compression_ignored_results.mn_single_kgm)
    assert full_flexure_results.effective_beam_behavior == BeamBehaviorMode.DOUBLY.value
    assert full_flexure_results.auto_result == ""
    assert full_flexure_results.mn_kgm == pytest.approx(full_flexure_results.mn_full_kgm)
    assert full_flexure_results.mn_kgm > compression_ignored_results.mn_kgm


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


def test_auto_spacing_is_recomputed_from_combined_shear_and_torsion_demand() -> None:
    inputs = BeamDesignInputSet(
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=500.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_bar_diameter_mm=16,
            provided_longitudinal_bar_count=4,
            provided_longitudinal_bar_fy_ksc=4000.0,
        )
    )

    results = calculate_full_design_results(inputs)

    assert results.combined_shear_torsion.active is True
    assert results.combined_shear_torsion.spacing_limit_reason == "Torsion maximum stirrup spacing"
    assert results.combined_shear_torsion.required_spacing_cm == pytest.approx(10.55)
    assert results.shear.provided_spacing_cm == pytest.approx(10.0)
    assert results.combined_shear_torsion.stirrup_spacing_cm == pytest.approx(10.0)


def test_manual_spacing_can_fail_combined_shear_and_torsion_spacing_limit() -> None:
    inputs = BeamDesignInputSet(
        shear=ShearDesignInput(
            factored_shear_kg=5000.0,
            stirrup_diameter_mm=9,
            legs_per_plane=2,
            spacing_mode=ShearSpacingMode.MANUAL,
            provided_spacing_cm=15.0,
        ),
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=500.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_bar_diameter_mm=16,
            provided_longitudinal_bar_count=4,
            provided_longitudinal_bar_fy_ksc=4000.0,
        ),
    )

    results = calculate_full_design_results(inputs)

    assert results.combined_shear_torsion.active is True
    assert results.combined_shear_torsion.required_spacing_cm == pytest.approx(10.55)
    assert results.combined_shear_torsion.stirrup_spacing_cm == pytest.approx(15.0)
    assert results.combined_shear_torsion.design_status == "FAIL"


def test_combined_shear_torsion_uses_nonzero_shear_interaction_component() -> None:
    inputs = BeamDesignInputSet(
        shear=ShearDesignInput(
            factored_shear_kg=5000.0,
            stirrup_diameter_mm=9,
            legs_per_plane=2,
            spacing_mode=ShearSpacingMode.MANUAL,
            provided_spacing_cm=15.0,
        ),
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=500.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_bar_diameter_mm=16,
            provided_longitudinal_bar_count=4,
            provided_longitudinal_bar_fy_ksc=4000.0,
        ),
    )

    results = calculate_full_design_results(inputs)

    expected_shear_component = (
        results.shear.nominal_vs_required_kg
        / (inputs.materials.shear_steel_yield_ksc * results.beam_geometry.d_plus_cm * 10.0)
    ) * 100.0

    assert results.combined_shear_torsion.shear_required_transverse_mm2_per_mm == pytest.approx(expected_shear_component)
    assert results.combined_shear_torsion.shear_required_transverse_mm2_per_mm > 0.10429860706608919
    assert results.combined_shear_torsion.capacity_ratio == pytest.approx(
        results.combined_shear_torsion.combined_required_transverse_mm2_per_mm
        / results.combined_shear_torsion.provided_transverse_mm2_per_mm
    )


def test_combined_shear_torsion_section_limit_can_govern_before_shared_stirrup_ratio() -> None:
    inputs = BeamDesignInputSet(
        shear=ShearDesignInput(
            factored_shear_kg=12000.0,
            stirrup_diameter_mm=16,
            legs_per_plane=4,
            spacing_mode=ShearSpacingMode.MANUAL,
            provided_spacing_cm=5.0,
        ),
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=2000.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=12.0,
            provided_longitudinal_bar_diameter_mm=20,
            provided_longitudinal_bar_count=8,
            provided_longitudinal_bar_fy_ksc=4000.0,
        ),
    )

    results = calculate_full_design_results(inputs)
    combined = results.combined_shear_torsion

    assert combined.active is True
    assert combined.capacity_ratio < 1.0
    assert combined.cross_section_limit_check_applied is True
    assert combined.cross_section_limit_ratio > 1.0
    assert combined.design_status == "FAIL"
    assert "section-strength check" in combined.design_status_note


def test_flexural_phi_chart_uses_aci_minimum_phi_floor() -> None:
    assert flexural_phi_chart_points(BeamDesignInputSet().metadata.design_code, 0.002)[0][1] == pytest.approx(0.65)


def test_report_builder_uses_strain_compatibility_equation_for_et() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_full_design_results(inputs)
    sections = build_report_sections(inputs, results)
    positive_section = next(section for section in sections if section.title == "Middle Moment Design")
    et_row = next(row for row in positive_section.rows if row.variable == "et")

    assert et_row.equation == "ecu * (dt - c) / c"
    assert " - " in et_row.substitution


def test_report_builder_marks_doubly_flexure_rows_as_compatibility_based() -> None:
    inputs = _heavy_beam_behavior_inputs(BeamBehaviorMode.DOUBLY)
    results = calculate_full_design_results(inputs)
    sections = build_report_sections(inputs, results)
    positive_section = next(section for section in sections if section.title == "Middle Moment Design")
    mn_row = next(row for row in positive_section.rows if row.variable == "Mn")

    assert results.positive_bending.effective_beam_behavior == BeamBehaviorMode.DOUBLY.value
    assert "compatibility" in mn_row.equation.lower()


def test_print_report_marks_doubly_flexure_summary_as_compatibility_based() -> None:
    inputs = _heavy_beam_behavior_inputs(BeamBehaviorMode.DOUBLY)
    results = calculate_full_design_results(inputs)
    sections = build_print_report_sections(inputs, results)
    positive_section = next(section for section in sections if section.title == "Middle Moment Design")
    mn_row = positive_section.rows[-1]

    assert "compatibility" in mn_row.equation.lower()


def test_dt_uses_extreme_tension_bar_diameter_when_group_b_is_larger() -> None:
    inputs = BeamDesignInputSet(
        positive_bending=PositiveBendingInput(
            tension_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=16, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=1),
                ),
            ),
        )
    )

    results = calculate_positive_bending_design(
        inputs.materials,
        inputs.geometry,
        inputs.positive_bending,
        inputs,
    )

    expected_dt_cm = (
        inputs.geometry.depth_cm
        - inputs.geometry.cover_cm
        - (inputs.shear.stirrup_diameter_mm / 10.0)
        - (25 / 20.0)
    )
    assert results.dt_cm == pytest.approx(expected_dt_cm)


def test_auto_spacing_is_not_reduced_below_5_cm() -> None:
    assert _auto_select_spacing_cm(4.2) == pytest.approx(5.0)
    assert _auto_select_spacing_cm(2.5) == pytest.approx(5.0)


def test_passing_torsion_design_does_not_trigger_requirement_status_from_basis_note() -> None:
    inputs = BeamDesignInputSet(
        beam_type=BeamType.SIMPLE,
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=500.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_bar_diameter_mm=16,
            provided_longitudinal_bar_count=4,
            provided_longitudinal_bar_fy_ksc=4000.0,
        ),
    )

    results = calculate_full_design_results(inputs)

    assert results.combined_shear_torsion.active is True
    assert results.combined_shear_torsion.design_status == "PASS"
    assert results.overall_status != "DOES NOT MEET REQUIREMENTS"


def test_negative_bending_matches_current_negative_logic() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_negative_bending_design(
        inputs.materials,
        inputs.geometry,
        inputs.negative_bending,
        inputs,
    )

    assert results.as_required_cm2 == pytest.approx(5.253522874809101)
    assert results.as_provided_cm2 == pytest.approx(6.031857894892403)
    assert results.as_min_cm2 == pytest.approx(2.4010000000000002)
    assert results.as_max_cm2 == pytest.approx(11.2067224137931)


def test_full_design_results_build_cantilever_negative_section_results() -> None:
    standalone = calculate_full_design_results(BeamDesignInputSet(beam_type=BeamType.STANDALONE_CANTILEVER))
    simple_with_cantilever = calculate_full_design_results(
        BeamDesignInputSet(beam_type=BeamType.SIMPLE, include_cantilever_span=True)
    )
    continuous_with_cantilever = calculate_full_design_results(
        BeamDesignInputSet(beam_type=BeamType.CONTINUOUS, include_cantilever_span=True)
    )

    assert standalone.negative_bending is None
    assert standalone.cantilever_negative_bending is not None
    assert simple_with_cantilever.negative_bending is None
    assert simple_with_cantilever.cantilever_negative_bending is not None
    assert continuous_with_cantilever.negative_bending is not None
    assert continuous_with_cantilever.cantilever_negative_bending is not None


def test_standalone_cantilever_does_not_emit_inactive_positive_section_warnings() -> None:
    inputs = BeamDesignInputSet(
        beam_type=BeamType.STANDALONE_CANTILEVER,
        positive_bending=PositiveBendingInput(
            tension_reinforcement=ReinforcementArrangementInput(),
            compression_reinforcement=ReinforcementArrangementInput(),
        ),
    )

    results = calculate_full_design_results(inputs)

    assert all("Positive bending reinforcement" not in warning for warning in results.warnings)
    assert "Positive tension reinforcement does not satisfy the required A_s limits." not in results.overall_note


def test_standalone_cantilever_uses_cantilever_negative_section_for_shear_basis() -> None:
    inputs = BeamDesignInputSet(beam_type=BeamType.STANDALONE_CANTILEVER)

    results = calculate_full_design_results(inputs)

    assert results.shear.design_section_key == "cantilever_negative"
    assert results.shear.design_section_label == "Cantilever Negative Section"
    assert results.shear.effective_depth_cm == pytest.approx(results.beam_geometry.d_plus_cm)
    assert results.overall_status == "PASS"


def test_shear_design_selects_shallower_negative_section_when_it_controls() -> None:
    inputs = BeamDesignInputSet(
        beam_type=BeamType.CONTINUOUS,
        negative_bending=NegativeBendingInput(
            tension_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=25, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=3),
                ),
                layer_2=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=25, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=2),
                ),
            ),
        ),
    )

    results = calculate_full_design_results(inputs)

    assert results.beam_geometry.d_minus_cm is not None
    assert results.shear.design_section_key == "negative"
    assert results.shear.effective_depth_cm == pytest.approx(results.beam_geometry.d_minus_cm)
    assert results.shear.effective_depth_cm < results.beam_geometry.d_plus_cm


def test_full_results_expose_review_flags_and_overall_status() -> None:
    results = calculate_full_design_results(BeamDesignInputSet())

    assert results.overall_status == "PASS"
    assert len(results.review_flags) == 0


def test_full_results_include_deflection_without_forcing_review_flag() -> None:
    results = calculate_full_design_results(
        BeamDesignInputSet(
            consider_deflection=True,
            deflection=DeflectionCheckInput(
                design_code=DeflectionCodeVersion.ACI318_14,
                member_type=DeflectionMemberType.SIMPLE_BEAM,
                support_condition=DeflectionSupportCondition.SIMPLE,
                span_length_m=4.0,
                service_dead_load_kgf_per_m=300.0,
                service_live_load_kgf_per_m=200.0,
                sustained_live_load_ratio=0.3,
            ),
        )
    )

    assert results.overall_status == "PASS"
    assert len(results.review_flags) == 0
    assert results.deflection.status == "PASS"


def test_simple_beam_omits_negative_results() -> None:
    inputs = BeamDesignInputSet(beam_type=BeamType.SIMPLE)

    results = calculate_full_design_results(inputs)

    assert results.negative_bending is None
    assert results.beam_geometry.d_minus_cm is None


def test_simple_beam_support_moment_auto_uses_l_over_4_ratio() -> None:
    inputs = BeamDesignInputSet(beam_type=BeamType.SIMPLE)
    inputs.positive_bending.factored_moment_kgm = 3600.0

    assert inputs.resolved_simple_support_moment_kgm == pytest.approx(2700.0)
    assert inputs.active_mu_region_mappings == (
        ("Mu_max", "middle", "Middle Section"),
        ("Mu at Support - L/4", "support", "Support Section"),
    )
    assert inputs.active_vu_region_mappings == (
        ("support", "Support Vu", "support", "Support Section"),
        ("middle", "Middle-region Vu", "middle", "Middle Section"),
    )


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


def test_formula_warning_clause_helpers_use_verified_references() -> None:
    assert _shear_strength_clause_reference(DesignCode.ACI318_99) == "ACI 318-99 11.3 together with 11.5"
    assert _shear_strength_clause_reference(DesignCode.ACI318_11) == "ACI 318-11 11.2 together with 11.4"
    assert _shear_reinforcement_clause_reference(DesignCode.ACI318_99) == "ACI 318-99 11.5.4 and 11.5.6"
    assert _shear_minimum_clause_reference(DesignCode.ACI318_99) == "ACI 318-99 11.5.5.1 and 11.5.5.3"
    assert _shear_minimum_clause_reference(DesignCode.ACI318_11) == "ACI 318-11 11.4.6.1 and 11.4.6.3"
    assert _torsion_spacing_clause_reference("ACI 318-14") == "ACI 318-14 9.7.6.3.3"
    assert _torsion_spacing_clause_reference("ACI 318-19") == "ACI 318-19 9.7.6.3.3"
    assert _torsion_cross_section_clause_reference("ACI 318-14") == "ACI 318-14 22.7.7.1"
    assert _torsion_cross_section_clause_reference("ACI 318-19") == "ACI 318-19 22.7.7.1"
    assert _combined_shear_torsion_cross_section_clause(DesignCode.ACI318_11) == "ACI 318-11 11.5.3.1"


def test_alternative_torsion_procedure_note_does_not_downgrade_overall_status() -> None:
    inputs = BeamDesignInputSet(
        beam_type=BeamType.SIMPLE,
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=1200.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=8.0,
        ),
    )
    inputs.geometry.width_cm = 20.0
    inputs.geometry.depth_cm = 70.0
    inputs.positive_bending.factored_moment_kgm = 0.0
    inputs.shear.factored_shear_kg = 0.0
    inputs.positive_bending.tension_reinforcement = ReinforcementArrangementInput(
        layer_1=RebarLayerInput(
            group_a=RebarGroupInput(diameter_mm=20, count=2),
            group_b=RebarGroupInput(),
        )
    )

    results = calculate_full_design_results(inputs)

    assert any("alternative torsion design procedure" in warning for warning in results.warnings)
    assert results.overall_status == "PASS"
