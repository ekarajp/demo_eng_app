import pytest

from apps.singly_beam.formulas import calculate_full_design_results
from apps.singly_beam.models import BeamDesignInputSet, BeamType, DeflectionCheckInput
from apps.singly_beam.report_builder import build_report_sections
from design.deflection import (
    AllowableDeflectionLimitInput,
    AllowableDeflectionPreset,
    DeflectionCodeVersion,
    DeflectionDesignInput,
    DeflectionIeMethod,
    DeflectionMemberType,
    DeflectionSectionReinforcementInput,
    DeflectionServiceLoadInput,
    DeflectionSupportCondition,
    design_deflection_check,
)


def _simple_deflection_input(code_version: DeflectionCodeVersion) -> DeflectionDesignInput:
    return DeflectionDesignInput(
        code_version=code_version,
        member_type=DeflectionMemberType.SIMPLE_BEAM,
        support_condition=DeflectionSupportCondition.SIMPLE,
        span_length_m=4.0,
        service_loads=DeflectionServiceLoadInput(
            dead_load_kgf_per_m=300.0,
            live_load_kgf_per_m=200.0,
            sustained_live_load_ratio=0.3,
        ),
    )


@pytest.mark.parametrize(
    "code_version",
    [
        DeflectionCodeVersion.ACI318_99,
        DeflectionCodeVersion.ACI318_11,
        DeflectionCodeVersion.ACI318_14,
        DeflectionCodeVersion.ACI318_19,
    ],
)
def test_each_deflection_code_version_runs_independently(code_version: DeflectionCodeVersion) -> None:
    results = design_deflection_check(_simple_deflection_input(code_version))

    assert results.code_version == code_version.value
    assert results.member_type == "Simple beam"
    assert results.support_condition == "Simple"
    assert results.steps


def test_continuous_ie_method_selection_runs_all_modes_and_worst_case_chooses_larger_deflection() -> None:
    shared_kwargs = dict(
        code_version=DeflectionCodeVersion.ACI318_19,
        member_type=DeflectionMemberType.CONTINUOUS_BEAM,
        support_condition=DeflectionSupportCondition.CONTINUOUS_2_SPANS,
        span_length_m=10.0,
        service_loads=DeflectionServiceLoadInput(
            dead_load_kgf_per_m=300.0,
            live_load_kgf_per_m=300.0,
            additional_sustained_load_kgf_per_m=0.0,
            sustained_live_load_ratio=0.3,
            support_dead_load_service_moment_kgm=-1000000.0,
            support_live_load_service_moment_kgm=-1000000.0,
        ),
        support_section=DeflectionSectionReinforcementInput(
            tension_as_cm2=1.0,
            compression_as_cm2=2.261946710584651,
            effective_depth_cm=34.1,
            compression_depth_cm=5.9,
        ),
    )

    midspan_results = design_deflection_check(
        DeflectionDesignInput(ie_method=DeflectionIeMethod.MIDSPAN_ONLY, **shared_kwargs)
    )
    averaged_results = design_deflection_check(
        DeflectionDesignInput(ie_method=DeflectionIeMethod.AVERAGED, **shared_kwargs)
    )
    worst_case_results = design_deflection_check(
        DeflectionDesignInput(ie_method=DeflectionIeMethod.WORST_CASE, **shared_kwargs)
    )

    assert midspan_results.ie_method_governing == DeflectionIeMethod.MIDSPAN_ONLY.value
    assert averaged_results.ie_method_governing == DeflectionIeMethod.AVERAGED.value
    assert averaged_results.ie_average_total_cm4 is not None
    assert worst_case_results.method_2_total_service_deflection_cm is not None
    assert worst_case_results.total_service_deflection_cm == pytest.approx(
        max(
            midspan_results.total_service_deflection_cm,
            averaged_results.total_service_deflection_cm,
        )
    )
    assert worst_case_results.ie_method_governing == DeflectionIeMethod.AVERAGED.value
    assert "larger deflection" in worst_case_results.load_basis_note.lower()


def test_app_level_deflection_respects_selected_ie_method() -> None:
    def _run(method: DeflectionIeMethod):
        return calculate_full_design_results(
            BeamDesignInputSet(
                beam_type=BeamType.CONTINUOUS,
                consider_deflection=True,
                deflection=DeflectionCheckInput(
                    design_code=DeflectionCodeVersion.ACI318_19,
                    member_type=DeflectionMemberType.CONTINUOUS_BEAM,
                    support_condition=DeflectionSupportCondition.CONTINUOUS_2_SPANS,
                    ie_method=method,
                    span_length_m=10.0,
                    service_live_load_kgf_per_m=300.0,
                    support_dead_load_service_moment_kgm=-1000000.0,
                    support_live_load_service_moment_kgm=-1000000.0,
                ),
            )
        ).deflection

    midspan = _run(DeflectionIeMethod.MIDSPAN_ONLY)
    averaged = _run(DeflectionIeMethod.AVERAGED)
    worst = _run(DeflectionIeMethod.WORST_CASE)

    assert midspan.ie_method_selected == DeflectionIeMethod.MIDSPAN_ONLY.value
    assert averaged.ie_method_selected == DeflectionIeMethod.AVERAGED.value
    assert worst.ie_method_selected == DeflectionIeMethod.WORST_CASE.value
    assert midspan.total_service_deflection_cm != averaged.total_service_deflection_cm
    assert worst.total_service_deflection_cm == pytest.approx(
        max(midspan.total_service_deflection_cm, averaged.total_service_deflection_cm)
    )


def test_allowable_limit_dropdown_and_custom_limit_work() -> None:
    default_results = design_deflection_check(
        DeflectionDesignInput(
            code_version=DeflectionCodeVersion.ACI318_14,
            member_type=DeflectionMemberType.SIMPLE_BEAM,
            support_condition=DeflectionSupportCondition.SIMPLE,
            span_length_m=6.0,
            allowable_limit=AllowableDeflectionLimitInput(preset=AllowableDeflectionPreset.L_240),
            service_loads=DeflectionServiceLoadInput(dead_load_kgf_per_m=100.0, live_load_kgf_per_m=60.0),
        )
    )
    custom_results = design_deflection_check(
        DeflectionDesignInput(
            code_version=DeflectionCodeVersion.ACI318_14,
            member_type=DeflectionMemberType.SIMPLE_BEAM,
            support_condition=DeflectionSupportCondition.SIMPLE,
            span_length_m=6.0,
            allowable_limit=AllowableDeflectionLimitInput(
                preset=AllowableDeflectionPreset.CUSTOM,
                custom_denominator=500,
            ),
            service_loads=DeflectionServiceLoadInput(dead_load_kgf_per_m=100.0, live_load_kgf_per_m=60.0),
        )
    )

    assert default_results.allowable_limit_label == "L/240"
    assert default_results.allowable_deflection_cm == pytest.approx(2.5)
    assert custom_results.allowable_limit_label == "L/500"
    assert custom_results.allowable_deflection_cm == pytest.approx(1.2)


def test_zero_service_loads_produce_explicit_input_notice() -> None:
    results = design_deflection_check(
        DeflectionDesignInput(
            code_version=DeflectionCodeVersion.ACI318_11,
            member_type=DeflectionMemberType.SIMPLE_BEAM,
            support_condition=DeflectionSupportCondition.SIMPLE,
            span_length_m=4.0,
            service_loads=DeflectionServiceLoadInput(dead_load_kgf_per_m=0.0, live_load_kgf_per_m=0.0),
        )
    )

    assert any("load-free" in warning for warning in results.warnings)


def test_existing_beam_data_is_reused_by_app_level_deflection_check() -> None:
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

    assert results.deflection.gross_moment_of_inertia_cm4 == pytest.approx(results.beam_geometry.gross_moment_of_inertia_cm4)
    assert results.deflection.service_dead_load_kgf_per_m == pytest.approx(192.0)
    assert results.deflection.immediate_total_deflection_cm == pytest.approx(0.05236649667885304)
    assert results.deflection.total_service_deflection_cm == pytest.approx(0.07654906113796456)
    assert results.deflection.status == "PASS"


def test_deflection_section_is_added_to_report_when_enabled() -> None:
    inputs = BeamDesignInputSet(
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

    results = calculate_full_design_results(inputs)
    sections = build_report_sections(inputs, results)

    assert "Deflection Check" in [section.title for section in sections]


def test_aci318_19_deflection_path_no_longer_emits_repo_baseline_warning() -> None:
    results = design_deflection_check(_simple_deflection_input(DeflectionCodeVersion.ACI318_19))

    assert not any("licensed code text" in warning for warning in results.warnings)


def test_aci318_19_deflection_uses_distinct_ie_expression_from_aci318_14() -> None:
    shared_input = dict(
        member_type=DeflectionMemberType.CONTINUOUS_BEAM,
        support_condition=DeflectionSupportCondition.CONTINUOUS_2_SPANS,
        ie_method=DeflectionIeMethod.MIDSPAN_ONLY,
        span_length_m=8.0,
        service_loads=DeflectionServiceLoadInput(
            dead_load_kgf_per_m=350.0,
            live_load_kgf_per_m=250.0,
            sustained_live_load_ratio=0.3,
            support_dead_load_service_moment_kgm=-2000.0,
            support_live_load_service_moment_kgm=-1200.0,
        ),
        midspan_section=DeflectionSectionReinforcementInput(
            tension_as_cm2=3.0,
            compression_as_cm2=1.2,
            effective_depth_cm=34.5,
            compression_depth_cm=5.5,
        ),
        support_section=DeflectionSectionReinforcementInput(
            tension_as_cm2=2.5,
            compression_as_cm2=1.2,
            effective_depth_cm=34.5,
            compression_depth_cm=5.5,
        ),
    )

    aci14_results = design_deflection_check(
        DeflectionDesignInput(code_version=DeflectionCodeVersion.ACI318_14, **shared_input)
    )
    aci19_results = design_deflection_check(
        DeflectionDesignInput(code_version=DeflectionCodeVersion.ACI318_19, **shared_input)
    )

    assert aci14_results.ie_total_cm4 != pytest.approx(aci19_results.ie_total_cm4)
    assert aci19_results.immediate_clause == "ACI318-19 - Clause 24.2.3"
    assert aci19_results.immediate_live_deflection_cm != pytest.approx(aci14_results.immediate_live_deflection_cm)


def test_cantilever_option_is_mockup_only() -> None:
    results = design_deflection_check(
        DeflectionDesignInput(
            code_version=DeflectionCodeVersion.ACI318_19,
            member_type=DeflectionMemberType.CANTILEVER_BEAM,
            support_condition=DeflectionSupportCondition.CANTILEVER_PLACEHOLDER,
            span_length_m=3.0,
        )
    )

    assert results.mockup_only is True
    assert results.status == "MOCKUP ONLY"
    assert "Mockup only" in results.note


def test_invalid_geometry_or_negative_inputs_raise_validation_errors() -> None:
    with pytest.raises(ValueError):
        DeflectionDesignInput(
            code_version=DeflectionCodeVersion.ACI318_14,
            member_type=DeflectionMemberType.SIMPLE_BEAM,
            support_condition=DeflectionSupportCondition.SIMPLE,
            span_length_m=-1.0,
        )

    with pytest.raises(ValueError):
        DeflectionCheckInput(
            design_code=DeflectionCodeVersion.ACI318_14,
            member_type=DeflectionMemberType.SIMPLE_BEAM,
            support_condition=DeflectionSupportCondition.SIMPLE,
            span_length_m=4.0,
            sustained_live_load_ratio=1.2,
        )


def test_support_moments_can_govern_continuous_beam_deflection_through_ie_average_check() -> None:
    zero_results = design_deflection_check(
        DeflectionDesignInput(
            code_version=DeflectionCodeVersion.ACI318_19,
            member_type=DeflectionMemberType.CONTINUOUS_BEAM,
            support_condition=DeflectionSupportCondition.CONTINUOUS_2_SPANS,
            span_length_m=10.0,
            service_loads=DeflectionServiceLoadInput(
                dead_load_kgf_per_m=300.0,
                live_load_kgf_per_m=300.0,
                additional_sustained_load_kgf_per_m=0.0,
                sustained_live_load_ratio=0.3,
                support_dead_load_service_moment_kgm=0.0,
                support_live_load_service_moment_kgm=0.0,
            ),
            support_section=DeflectionSectionReinforcementInput(
                tension_as_cm2=1.0,
                compression_as_cm2=2.261946710584651,
                effective_depth_cm=34.1,
                compression_depth_cm=5.9,
            ),
        )
    )
    high_results = design_deflection_check(
        DeflectionDesignInput(
            code_version=DeflectionCodeVersion.ACI318_19,
            member_type=DeflectionMemberType.CONTINUOUS_BEAM,
            support_condition=DeflectionSupportCondition.CONTINUOUS_2_SPANS,
            span_length_m=10.0,
            service_loads=DeflectionServiceLoadInput(
                dead_load_kgf_per_m=300.0,
                live_load_kgf_per_m=300.0,
                additional_sustained_load_kgf_per_m=0.0,
                sustained_live_load_ratio=0.3,
                support_dead_load_service_moment_kgm=-1000000.0,
                support_live_load_service_moment_kgm=-1000000.0,
            ),
            support_section=DeflectionSectionReinforcementInput(
                tension_as_cm2=1.0,
                compression_as_cm2=2.261946710584651,
                effective_depth_cm=34.1,
                compression_depth_cm=5.9,
            ),
        )
    )

    assert high_results.total_service_deflection_cm > zero_results.total_service_deflection_cm
    assert "larger deflection" in high_results.load_basis_note.lower()
    assert any(step.variable == "Governing deflection method" and step.result == DeflectionIeMethod.AVERAGED.value for step in high_results.steps)
