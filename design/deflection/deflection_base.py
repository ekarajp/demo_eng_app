from __future__ import annotations

from dataclasses import dataclass
import math

from .deflection_inputs import (
    DeflectionCalculationStep,
    DeflectionDesignInput,
    DeflectionDesignResults,
    DeflectionIeMethod,
    DeflectionMemberType,
    DeflectionSectionReinforcementInput,
    DeflectionSupportCondition,
    DeflectionVerificationStatus,
)
from .deflection_limits import allowable_deflection_cm, allowable_limit_denominator, allowable_limit_label


@dataclass(frozen=True, slots=True)
class DeflectionClauseMap:
    immediate_deflection: str
    effective_inertia: str
    long_term: str
    allowable_limit: str


@dataclass(frozen=True, slots=True)
class DeflectionWorkflowOptions:
    immediate_method: str
    repo_baseline_note: str = ""


@dataclass(frozen=True, slots=True)
class _SectionResponse:
    cracking_moment_kgm: float
    cracked_neutral_axis_cm: float
    cracked_inertia_cm4: float


@dataclass(frozen=True, slots=True)
class _ImmediateCase:
    section_moment_kgm: float
    effective_inertia_cm4: float
    midspan_effective_inertia_cm4: float
    average_effective_inertia_cm4: float | None
    support_effective_inertia_cm4: float | None
    deflection_cm: float


@dataclass(frozen=True, slots=True)
class _MethodDeflectionEvaluation:
    method: DeflectionIeMethod
    dead_case: _ImmediateCase
    total_case: _ImmediateCase
    sustained_case: _ImmediateCase
    immediate_live_deflection_cm: float
    additional_long_term_deflection_cm: float
    total_service_deflection_cm: float


def calculate_deflection_design(
    design_input: DeflectionDesignInput,
    clauses: DeflectionClauseMap,
    workflow: DeflectionWorkflowOptions,
) -> DeflectionDesignResults:
    if design_input.member_type == DeflectionMemberType.CANTILEVER_BEAM:
        denominator = allowable_limit_denominator(design_input.allowable_limit)
        allowable_cm = allowable_deflection_cm(design_input.span_length_m, design_input.allowable_limit)
        note = "Mockup only / reserved for future cantilever module expansion."
        return DeflectionDesignResults(
            code_version=design_input.code_version.value,
            member_type=design_input.member_type.value,
            support_condition=design_input.support_condition.value,
            ie_method_selected=design_input.ie_method.value,
            ie_method_governing=design_input.ie_method.value,
            allowable_limit_label=allowable_limit_label(design_input.allowable_limit),
            allowable_limit_denominator=denominator,
            allowable_deflection_cm=allowable_cm,
            span_length_m=design_input.span_length_m,
            load_basis_note="Cantilever workflow is reserved for a future dedicated cantilever module.",
            status="MOCKUP ONLY",
            verification_status=DeflectionVerificationStatus.NEEDS_REVIEW,
            pass_fail_summary=note,
            note=note,
            mockup_only=True,
            immediate_clause=clauses.immediate_deflection,
            long_term_clause=clauses.long_term,
            limit_clause=clauses.allowable_limit,
            service_dead_load_kgf_per_m=design_input.service_loads.dead_load_kgf_per_m,
            service_live_load_kgf_per_m=design_input.service_loads.live_load_kgf_per_m,
            additional_sustained_load_kgf_per_m=design_input.service_loads.additional_sustained_load_kgf_per_m,
            sustained_live_load_ratio=design_input.service_loads.sustained_live_load_ratio,
            service_sustained_load_kgf_per_m=0.0,
            midspan_dead_load_service_moment_kgm=0.0,
            midspan_live_load_service_moment_kgm=0.0,
            support_dead_load_service_moment_kgm=0.0,
            support_live_load_service_moment_kgm=0.0,
            gross_moment_of_inertia_cm4=design_input.gross_moment_of_inertia_cm4,
            midspan_cracking_moment_kgm=0.0,
            support_cracking_moment_kgm=None,
            midspan_cracked_neutral_axis_cm=0.0,
            support_cracked_neutral_axis_cm=None,
            midspan_cracked_inertia_cm4=0.0,
            support_cracked_inertia_cm4=None,
            ie_midspan_total_cm4=0.0,
            ie_support_total_cm4=None,
            ie_average_total_cm4=None,
            ie_dead_cm4=0.0,
            ie_total_cm4=0.0,
            ie_sustained_cm4=0.0,
            method_1_total_service_deflection_cm=0.0,
            method_2_total_service_deflection_cm=None,
            immediate_dead_deflection_cm=0.0,
            immediate_total_deflection_cm=0.0,
            immediate_live_deflection_cm=0.0,
            sustained_initial_deflection_cm=0.0,
            long_term_multiplier=0.0,
            additional_long_term_deflection_cm=0.0,
            total_service_deflection_cm=0.0,
            calculated_deflection_cm=0.0,
            capacity_ratio=0.0,
            governing_result="Cantilever workflow is not implemented in this module.",
            warnings=(note,),
            steps=(),
        )

    limit_denominator = allowable_limit_denominator(design_input.allowable_limit)
    allowable_cm = allowable_deflection_cm(design_input.span_length_m, design_input.allowable_limit)

    sustained_load_kgf_per_m = (
        design_input.service_loads.dead_load_kgf_per_m
        + design_input.service_loads.additional_sustained_load_kgf_per_m
        + (design_input.service_loads.live_load_kgf_per_m * design_input.service_loads.sustained_live_load_ratio)
    )
    total_load_kgf_per_m = (
        design_input.service_loads.dead_load_kgf_per_m
        + design_input.service_loads.live_load_kgf_per_m
        + design_input.service_loads.additional_sustained_load_kgf_per_m
    )

    midspan_dead_moment = _midspan_moment_kgm(
        design_input.service_loads.dead_load_kgf_per_m,
        design_input.span_length_m,
        design_input.support_condition,
    )
    midspan_total_moment = _midspan_moment_kgm(
        total_load_kgf_per_m,
        design_input.span_length_m,
        design_input.support_condition,
    )
    midspan_sustained_moment = _midspan_moment_kgm(
        sustained_load_kgf_per_m,
        design_input.span_length_m,
        design_input.support_condition,
    )
    midspan_live_moment = max(midspan_total_moment - midspan_dead_moment, 0.0)

    support_dead_moment = design_input.service_loads.support_dead_load_service_moment_kgm
    support_total_moment = support_dead_moment + design_input.service_loads.support_live_load_service_moment_kgm
    support_sustained_moment = support_dead_moment + (
        design_input.service_loads.support_live_load_service_moment_kgm * design_input.service_loads.sustained_live_load_ratio
    )

    midspan_section = _resolve_cracked_section(
        design_input.width_cm,
        design_input.depth_cm,
        design_input.gross_moment_of_inertia_cm4,
        design_input.fr_ksc,
        design_input.modular_ratio_n,
        design_input.midspan_section,
    )
    support_section = None
    if design_input.support_condition in {
        DeflectionSupportCondition.CONTINUOUS_2_SPANS,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS,
    }:
        if design_input.support_section is None:
            raise ValueError("support_section is required for continuous-beam deflection checks.")
        support_section = _resolve_cracked_section(
            design_input.width_cm,
            design_input.depth_cm,
            design_input.gross_moment_of_inertia_cm4,
            design_input.fr_ksc,
            design_input.modular_ratio_n,
            design_input.support_section,
        )

    midspan_method = _evaluate_deflection_method(
        design_input,
        workflow,
        midspan_section,
        support_section,
        DeflectionIeMethod.MIDSPAN_ONLY,
        midspan_dead_moment,
        support_dead_moment,
        design_input.service_loads.dead_load_kgf_per_m,
        midspan_total_moment,
        support_total_moment,
        total_load_kgf_per_m,
        midspan_sustained_moment,
        support_sustained_moment,
        sustained_load_kgf_per_m,
    )
    averaged_method = None
    if design_input.support_condition in {
        DeflectionSupportCondition.CONTINUOUS_2_SPANS,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS,
    }:
        averaged_method = _evaluate_deflection_method(
            design_input,
            workflow,
            midspan_section,
            support_section,
            DeflectionIeMethod.AVERAGED,
            midspan_dead_moment,
            support_dead_moment,
            design_input.service_loads.dead_load_kgf_per_m,
            midspan_total_moment,
            support_total_moment,
            total_load_kgf_per_m,
            midspan_sustained_moment,
            support_sustained_moment,
            sustained_load_kgf_per_m,
        )
    selected_method, governing_eval = calc_governing_deflection(
        design_input.ie_method,
        midspan_method,
        averaged_method,
    )
    dead_case = governing_eval.dead_case
    total_case = governing_eval.total_case
    sustained_case = governing_eval.sustained_case

    compression_ratio = _compression_ratio(
        design_input.midspan_section.compression_as_cm2,
        design_input.width_cm,
        design_input.midspan_section.effective_depth_cm,
    )
    long_term_multiplier = max(
        design_input.long_term_factor_x / (1.0 + (50.0 * compression_ratio)),
        1.0,
    )
    additional_long_term_deflection_cm = governing_eval.additional_long_term_deflection_cm
    immediate_live_deflection_cm = governing_eval.immediate_live_deflection_cm
    total_service_deflection_cm = governing_eval.total_service_deflection_cm
    capacity_ratio = _safe_divide(total_service_deflection_cm, allowable_cm)
    status = "PASS" if capacity_ratio <= 1.0 + 1e-9 else "FAIL"
    governing_result = f"Total service deflection vs. selected allowable limit; governing Ie method = {selected_method.value}"
    if design_input.ie_method == DeflectionIeMethod.WORST_CASE and averaged_method is not None:
        load_basis_note = (
            "For conservative design, the larger deflection from the two Ie evaluation methods is used. "
            "Method 1 uses Ie at midspan only. Method 2 uses the averaged Ie between midspan and support."
        )
    elif selected_method == DeflectionIeMethod.AVERAGED:
        load_basis_note = (
            "Immediate deflection is calculated using the averaged Ie between the representative midspan and support sections."
        )
    else:
        load_basis_note = "Immediate deflection is calculated using Ie at midspan only."
    note = (
        f"Method 1 deflection = {midspan_method.total_service_deflection_cm:.4f} cm; "
        f"Method 2 deflection = {averaged_method.total_service_deflection_cm:.4f} cm; "
        f"governing method = {selected_method.value}; "
        f"allowable deflection = {allowable_cm:.4f} cm."
        if averaged_method is not None
        else f"Immediate total deflection = {total_case.deflection_cm:.4f} cm; "
        f"long-term additional deflection = {additional_long_term_deflection_cm:.4f} cm; "
        f"allowable deflection = {allowable_cm:.4f} cm."
    )
    pass_fail_summary = (
        "Calculated service deflection is within the selected allowable limit."
        if status == "PASS"
        else "Calculated service deflection exceeds the selected allowable limit."
    )

    warnings: list[str] = []
    if total_case.deflection_cm == 0.0 and total_load_kgf_per_m == 0.0:
        warnings.append("Service dead load and service live load are both zero; the deflection check is load-free.")
    if design_input.service_loads.sustained_live_load_ratio > 0.0 and design_input.service_loads.live_load_kgf_per_m == 0.0:
        warnings.append("A sustained live-load ratio was entered, but the service live load is zero.")
    if workflow.repo_baseline_note:
        warnings.append(workflow.repo_baseline_note)
    if status == "FAIL":
        warnings.append(
            f"Calculated service deflection = {total_service_deflection_cm:.4f} cm exceeds the selected allowable deflection = {allowable_cm:.4f} cm."
        )

    steps = _build_steps(
        design_input,
        clauses,
        workflow,
        limit_denominator,
        allowable_cm,
        sustained_load_kgf_per_m,
        midspan_section,
        support_section,
        midspan_dead_moment,
        midspan_total_moment,
        midspan_sustained_moment,
        support_dead_moment,
        support_total_moment,
        support_sustained_moment,
        midspan_method,
        averaged_method,
        selected_method,
        dead_case,
        total_case,
        sustained_case,
        long_term_multiplier,
        additional_long_term_deflection_cm,
        immediate_live_deflection_cm,
        total_service_deflection_cm,
        capacity_ratio,
    )

    return DeflectionDesignResults(
        code_version=design_input.code_version.value,
        member_type=design_input.member_type.value,
        support_condition=design_input.support_condition.value,
        ie_method_selected=design_input.ie_method.value,
        ie_method_governing=selected_method.value,
        allowable_limit_label=allowable_limit_label(design_input.allowable_limit),
        allowable_limit_denominator=limit_denominator,
        allowable_deflection_cm=allowable_cm,
        span_length_m=design_input.span_length_m,
        load_basis_note=load_basis_note,
        status=status,
        verification_status=DeflectionVerificationStatus.VERIFIED,
        pass_fail_summary=pass_fail_summary,
        note=note,
        mockup_only=False,
        immediate_clause=clauses.immediate_deflection,
        long_term_clause=clauses.long_term,
        limit_clause=clauses.allowable_limit,
        service_dead_load_kgf_per_m=design_input.service_loads.dead_load_kgf_per_m,
        service_live_load_kgf_per_m=design_input.service_loads.live_load_kgf_per_m,
        additional_sustained_load_kgf_per_m=design_input.service_loads.additional_sustained_load_kgf_per_m,
        sustained_live_load_ratio=design_input.service_loads.sustained_live_load_ratio,
        service_sustained_load_kgf_per_m=sustained_load_kgf_per_m,
        midspan_dead_load_service_moment_kgm=midspan_dead_moment,
        midspan_live_load_service_moment_kgm=midspan_live_moment,
        support_dead_load_service_moment_kgm=support_dead_moment,
        support_live_load_service_moment_kgm=design_input.service_loads.support_live_load_service_moment_kgm,
        gross_moment_of_inertia_cm4=design_input.gross_moment_of_inertia_cm4,
        midspan_cracking_moment_kgm=midspan_section.cracking_moment_kgm,
        support_cracking_moment_kgm=support_section.cracking_moment_kgm if support_section is not None else None,
        midspan_cracked_neutral_axis_cm=midspan_section.cracked_neutral_axis_cm,
        support_cracked_neutral_axis_cm=support_section.cracked_neutral_axis_cm if support_section is not None else None,
        midspan_cracked_inertia_cm4=midspan_section.cracked_inertia_cm4,
        support_cracked_inertia_cm4=support_section.cracked_inertia_cm4 if support_section is not None else None,
        ie_midspan_total_cm4=total_case.midspan_effective_inertia_cm4,
        ie_support_total_cm4=total_case.support_effective_inertia_cm4,
        ie_average_total_cm4=total_case.average_effective_inertia_cm4,
        ie_dead_cm4=dead_case.effective_inertia_cm4,
        ie_total_cm4=total_case.effective_inertia_cm4,
        ie_sustained_cm4=sustained_case.effective_inertia_cm4,
        method_1_total_service_deflection_cm=midspan_method.total_service_deflection_cm,
        method_2_total_service_deflection_cm=(
            averaged_method.total_service_deflection_cm if averaged_method is not None else None
        ),
        immediate_dead_deflection_cm=dead_case.deflection_cm,
        immediate_total_deflection_cm=total_case.deflection_cm,
        immediate_live_deflection_cm=immediate_live_deflection_cm,
        sustained_initial_deflection_cm=sustained_case.deflection_cm,
        long_term_multiplier=long_term_multiplier,
        additional_long_term_deflection_cm=additional_long_term_deflection_cm,
        total_service_deflection_cm=total_service_deflection_cm,
        calculated_deflection_cm=total_service_deflection_cm,
        capacity_ratio=capacity_ratio,
        governing_result=governing_result,
        warnings=tuple(warnings),
        steps=tuple(steps),
    )


def _resolve_cracked_section(
    width_cm: float,
    depth_cm: float,
    gross_moment_of_inertia_cm4: float,
    fr_ksc: float,
    modular_ratio_n: float,
    reinforcement: DeflectionSectionReinforcementInput,
) -> _SectionResponse:
    y_t_cm = depth_cm / 2.0
    cracking_moment_kgm = (fr_ksc * gross_moment_of_inertia_cm4 / y_t_cm) / 100.0
    if reinforcement.tension_as_cm2 <= 0.0:
        return _SectionResponse(
            cracking_moment_kgm=cracking_moment_kgm,
            cracked_neutral_axis_cm=depth_cm / 2.0,
            cracked_inertia_cm4=gross_moment_of_inertia_cm4,
        )

    b_factor = width_cm / (modular_ratio_n * reinforcement.tension_as_cm2)
    r_factor = ((modular_ratio_n - 1.0) * reinforcement.compression_as_cm2) / (
        modular_ratio_n * reinforcement.tension_as_cm2
    )
    radical = (
        2.0
        * reinforcement.effective_depth_cm
        * b_factor
        * (1.0 + (r_factor * reinforcement.compression_depth_cm / reinforcement.effective_depth_cm))
        + ((1.0 + r_factor) ** 2)
    )
    cracked_neutral_axis_cm = (math.sqrt(radical) - (1.0 + r_factor)) / b_factor
    cracked_inertia_cm4 = (
        (width_cm * (cracked_neutral_axis_cm**3)) / 3.0
        + (modular_ratio_n * reinforcement.tension_as_cm2 * ((reinforcement.effective_depth_cm - cracked_neutral_axis_cm) ** 2))
        + (
            (modular_ratio_n - 1.0)
            * reinforcement.compression_as_cm2
            * ((cracked_neutral_axis_cm - reinforcement.compression_depth_cm) ** 2)
        )
    )
    return _SectionResponse(
        cracking_moment_kgm=cracking_moment_kgm,
        cracked_neutral_axis_cm=cracked_neutral_axis_cm,
        cracked_inertia_cm4=cracked_inertia_cm4,
    )


def _midspan_moment_kgm(
    service_load_kgf_per_m: float,
    span_length_m: float,
    support_condition: DeflectionSupportCondition,
) -> float:
    coefficient = {
        DeflectionSupportCondition.SIMPLE: 1.0 / 8.0,
        DeflectionSupportCondition.CONTINUOUS_2_SPANS: 9.0 / 128.0,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS: 1.0 / 24.0,
        DeflectionSupportCondition.CANTILEVER_PLACEHOLDER: 1.0 / 2.0,
    }[support_condition]
    return coefficient * service_load_kgf_per_m * (span_length_m**2)


def _immediate_case(
    design_input: DeflectionDesignInput,
    workflow: DeflectionWorkflowOptions,
    midspan_section: _SectionResponse,
    support_section: _SectionResponse | None,
    ie_method: DeflectionIeMethod,
    midspan_moment_kgm: float,
    support_moment_kgm: float,
    service_load_kgf_per_m: float,
) -> _ImmediateCase:
    midspan_ie = calc_ie_midspan(
        workflow.immediate_method,
        design_input.gross_moment_of_inertia_cm4,
        midspan_section.cracked_inertia_cm4,
        midspan_section.cracking_moment_kgm,
        midspan_moment_kgm,
    )
    average_ie: float | None = None
    support_ie: float | None = None
    if design_input.support_condition in {
        DeflectionSupportCondition.CONTINUOUS_2_SPANS,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS,
    } and support_section is None:
        raise ValueError("Continuous-beam support condition requires support-section stiffness data.")
    effective_inertia_cm4 = midspan_ie
    if support_section is not None:
        support_ie = calc_ie_support(
            workflow.immediate_method,
            design_input.gross_moment_of_inertia_cm4,
            support_section.cracked_inertia_cm4,
            support_section.cracking_moment_kgm,
            support_moment_kgm,
        )
        average_ie = calc_ie_average(midspan_ie, support_ie)
        if ie_method == DeflectionIeMethod.AVERAGED and average_ie is not None:
            effective_inertia_cm4 = average_ie

    deflection_cm = calc_deflection_with_ie(
        service_load_kgf_per_m,
        design_input.span_length_m,
        design_input.ec_ksc,
        effective_inertia_cm4,
        design_input.support_condition,
    )
    return _ImmediateCase(
        section_moment_kgm=midspan_moment_kgm,
        effective_inertia_cm4=effective_inertia_cm4,
        midspan_effective_inertia_cm4=midspan_ie,
        average_effective_inertia_cm4=average_ie,
        support_effective_inertia_cm4=support_ie,
        deflection_cm=deflection_cm,
    )


def _evaluate_deflection_method(
    design_input: DeflectionDesignInput,
    workflow: DeflectionWorkflowOptions,
    midspan_section: _SectionResponse,
    support_section: _SectionResponse | None,
    ie_method: DeflectionIeMethod,
    midspan_dead_moment: float,
    support_dead_moment: float,
    dead_load_kgf_per_m: float,
    midspan_total_moment: float,
    support_total_moment: float,
    total_load_kgf_per_m: float,
    midspan_sustained_moment: float,
    support_sustained_moment: float,
    sustained_load_kgf_per_m: float,
) -> _MethodDeflectionEvaluation:
    dead_case = _immediate_case(
        design_input,
        workflow,
        midspan_section,
        support_section,
        ie_method,
        midspan_dead_moment,
        support_dead_moment,
        dead_load_kgf_per_m,
    )
    total_case = _immediate_case(
        design_input,
        workflow,
        midspan_section,
        support_section,
        ie_method,
        midspan_total_moment,
        support_total_moment,
        total_load_kgf_per_m,
    )
    sustained_case = _immediate_case(
        design_input,
        workflow,
        midspan_section,
        support_section,
        ie_method,
        midspan_sustained_moment,
        support_sustained_moment,
        sustained_load_kgf_per_m,
    )
    compression_ratio = _compression_ratio(
        design_input.midspan_section.compression_as_cm2,
        design_input.width_cm,
        design_input.midspan_section.effective_depth_cm,
    )
    long_term_multiplier = max(
        design_input.long_term_factor_x / (1.0 + (50.0 * compression_ratio)),
        1.0,
    )
    additional_long_term_deflection_cm = sustained_case.deflection_cm * long_term_multiplier
    immediate_live_deflection_cm = max(total_case.deflection_cm - sustained_case.deflection_cm, 0.0)
    total_service_deflection_cm = immediate_live_deflection_cm + additional_long_term_deflection_cm
    return _MethodDeflectionEvaluation(
        method=ie_method,
        dead_case=dead_case,
        total_case=total_case,
        sustained_case=sustained_case,
        immediate_live_deflection_cm=immediate_live_deflection_cm,
        additional_long_term_deflection_cm=additional_long_term_deflection_cm,
        total_service_deflection_cm=total_service_deflection_cm,
    )


def calc_ie_midspan(
    method: str,
    gross_moment_of_inertia_cm4: float,
    cracked_moment_of_inertia_cm4: float,
    cracking_moment_kgm: float,
    applied_service_moment_kgm: float,
) -> float:
    return _effective_inertia_cm4(
        method,
        gross_moment_of_inertia_cm4,
        cracked_moment_of_inertia_cm4,
        cracking_moment_kgm,
        applied_service_moment_kgm,
    )


def calc_ie_support(
    method: str,
    gross_moment_of_inertia_cm4: float,
    cracked_moment_of_inertia_cm4: float,
    cracking_moment_kgm: float,
    applied_service_moment_kgm: float,
) -> float:
    return _effective_inertia_cm4(
        method,
        gross_moment_of_inertia_cm4,
        cracked_moment_of_inertia_cm4,
        cracking_moment_kgm,
        applied_service_moment_kgm,
    )


def calc_ie_average(midspan_ie_cm4: float, support_ie_cm4: float | None) -> float | None:
    if support_ie_cm4 is None:
        return None
    return (midspan_ie_cm4 + support_ie_cm4) / 2.0


def calc_deflection_with_ie(
    service_load_kgf_per_m: float,
    span_length_m: float,
    ec_ksc: float,
    effective_inertia_cm4: float,
    support_condition: DeflectionSupportCondition,
) -> float:
    return _uniform_load_deflection_cm(
        service_load_kgf_per_m,
        span_length_m,
        ec_ksc,
        effective_inertia_cm4,
        support_condition,
    )


def calc_governing_deflection(
    selected_method: DeflectionIeMethod,
    midspan_method: _MethodDeflectionEvaluation,
    averaged_method: _MethodDeflectionEvaluation | None,
) -> tuple[DeflectionIeMethod, _MethodDeflectionEvaluation]:
    if averaged_method is None or selected_method == DeflectionIeMethod.MIDSPAN_ONLY:
        return DeflectionIeMethod.MIDSPAN_ONLY, midspan_method
    if selected_method == DeflectionIeMethod.AVERAGED:
        return DeflectionIeMethod.AVERAGED, averaged_method
    if averaged_method.total_service_deflection_cm > midspan_method.total_service_deflection_cm:
        return DeflectionIeMethod.AVERAGED, averaged_method
    return DeflectionIeMethod.MIDSPAN_ONLY, midspan_method


def _effective_inertia_cm4(
    method: str,
    gross_moment_of_inertia_cm4: float,
    cracked_moment_of_inertia_cm4: float,
    cracking_moment_kgm: float,
    applied_service_moment_kgm: float,
) -> float:
    applied_moment_magnitude_kgm = abs(applied_service_moment_kgm)
    if applied_moment_magnitude_kgm <= 0.0:
        return gross_moment_of_inertia_cm4
    ratio = min(cracking_moment_kgm / applied_moment_magnitude_kgm, 1.0)
    if method == "branson":
        return min(
            ((ratio**3) * gross_moment_of_inertia_cm4) + ((1.0 - (ratio**3)) * cracked_moment_of_inertia_cm4),
            gross_moment_of_inertia_cm4,
        )
    if method == "aci318_19_table_24_2_3_5":
        # ACI 318-19 Table 24.2.3.5 adopts the inverse Bischoff/Scanlon expression
        # for nonprestressed members. Ie = Ig when Ma <= (2/3)Mcr.
        reduced_cracking_moment_kgm = (2.0 / 3.0) * cracking_moment_kgm
        if applied_moment_magnitude_kgm <= reduced_cracking_moment_kgm:
            return gross_moment_of_inertia_cm4
        reduced_ratio = min(reduced_cracking_moment_kgm / applied_moment_magnitude_kgm, 1.0)
        denominator = 1.0 - ((reduced_ratio**2) * (1.0 - (cracked_moment_of_inertia_cm4 / gross_moment_of_inertia_cm4)))
        if denominator <= 0.0:
            return gross_moment_of_inertia_cm4
        return min(cracked_moment_of_inertia_cm4 / denominator, gross_moment_of_inertia_cm4)
    raise ValueError(f"Unsupported immediate deflection method: {method}.")


def _effective_inertia_equation_text(method: str) -> str:
    if method == "branson":
        return "Ie = (Mcr/Ma)^3 Ig + [1 - (Mcr/Ma)^3] Icr"
    if method == "aci318_19_table_24_2_3_5":
        return "Ie = Icr / [1 - ((2/3 Mcr)/Ma)^2 (1 - Icr/Ig)]"
    return method


def _uniform_load_deflection_cm(
    service_load_kgf_per_m: float,
    span_length_m: float,
    ec_ksc: float,
    effective_inertia_cm4: float,
    support_condition: DeflectionSupportCondition,
) -> float:
    if service_load_kgf_per_m <= 0.0:
        return 0.0
    load_kgf_per_cm = service_load_kgf_per_m / 100.0
    span_length_cm = span_length_m * 100.0
    coefficient = {
        DeflectionSupportCondition.SIMPLE: 5.0 / 384.0,
        DeflectionSupportCondition.CONTINUOUS_2_SPANS: 1.0 / 185.0,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS: 1.0 / 384.0,
        DeflectionSupportCondition.CANTILEVER_PLACEHOLDER: 1.0 / 8.0,
    }[support_condition]
    return coefficient * load_kgf_per_cm * (span_length_cm**4) / (ec_ksc * effective_inertia_cm4)


def _compression_ratio(compression_as_cm2: float, width_cm: float, effective_depth_cm: float) -> float:
    if compression_as_cm2 <= 0.0:
        return 0.0
    return compression_as_cm2 / (width_cm * effective_depth_cm)


def _build_steps(
    design_input: DeflectionDesignInput,
    clauses: DeflectionClauseMap,
    workflow: DeflectionWorkflowOptions,
    limit_denominator: int,
    allowable_cm: float,
    sustained_load_kgf_per_m: float,
    midspan_section: _SectionResponse,
    support_section: _SectionResponse | None,
    midspan_dead_moment: float,
    midspan_total_moment: float,
    midspan_sustained_moment: float,
    support_dead_moment: float,
    support_total_moment: float,
    support_sustained_moment: float,
    midspan_method: _MethodDeflectionEvaluation,
    averaged_method: _MethodDeflectionEvaluation | None,
    selected_method: DeflectionIeMethod,
    dead_case: _ImmediateCase,
    total_case: _ImmediateCase,
    sustained_case: _ImmediateCase,
    long_term_multiplier: float,
    additional_long_term_deflection_cm: float,
    immediate_live_deflection_cm: float,
    total_service_deflection_cm: float,
    capacity_ratio: float,
) -> list[DeflectionCalculationStep]:
    steps = [
        DeflectionCalculationStep(
            variable="Allowable deflection",
            equation="Delta_allow = L / limit",
            substitution=f"({design_input.span_length_m:.3f} m x 100) / {limit_denominator}",
            result=f"{allowable_cm:.4f}",
            units="cm",
            clause=clauses.allowable_limit,
        ),
        DeflectionCalculationStep(
            variable="Mcr, midspan",
            equation="Mcr = fr * Ig / yt",
            substitution=f"{design_input.fr_ksc:.4f} x {design_input.gross_moment_of_inertia_cm4:.4f} / ({design_input.depth_cm / 2.0:.4f}) / 100",
            result=f"{midspan_section.cracking_moment_kgm:.4f}",
            units="kgf-m",
            clause=clauses.effective_inertia,
        ),
        DeflectionCalculationStep(
            variable="Icr, midspan",
            equation="Transformed cracked-section inertia",
            substitution=f"x = {midspan_section.cracked_neutral_axis_cm:.4f} cm",
            result=f"{midspan_section.cracked_inertia_cm4:.4f}",
            units="cm^4",
            clause=clauses.effective_inertia,
        ),
    ]
    if support_section is not None:
        steps.extend(
            [
                DeflectionCalculationStep(
                    variable="Mcr, support",
                    equation="Mcr = fr * Ig / yt",
                    substitution=f"{design_input.fr_ksc:.4f} x {design_input.gross_moment_of_inertia_cm4:.4f} / ({design_input.depth_cm / 2.0:.4f}) / 100",
                    result=f"{support_section.cracking_moment_kgm:.4f}",
                    units="kgf-m",
                    clause=clauses.effective_inertia,
                ),
                DeflectionCalculationStep(
                    variable="Icr, support",
                    equation="Transformed cracked-section inertia",
                    substitution=f"x = {support_section.cracked_neutral_axis_cm:.4f} cm",
                    result=f"{support_section.cracked_inertia_cm4:.4f}",
                    units="cm^4",
                    clause=clauses.effective_inertia,
                ),
            ]
        )
    steps.extend(
        [
            DeflectionCalculationStep(
                variable="Service loads",
                equation="wDL, wLL, wsus",
                substitution=(
                    f"wDL = {design_input.service_loads.dead_load_kgf_per_m:.4f}, "
                    f"wLL = {design_input.service_loads.live_load_kgf_per_m:.4f}, "
                    f"wSUS = {sustained_load_kgf_per_m:.4f}"
                ),
                result=f"{sustained_load_kgf_per_m:.4f}",
                units="kgf/m",
                clause=clauses.immediate_deflection,
                note=design_input.support_condition.value,
            ),
            DeflectionCalculationStep(
                variable="Service moments",
                equation="Uniform-load service moments",
                substitution=(
                    f"Mmid,DL = {midspan_dead_moment:.4f}; Mmid,total = {midspan_total_moment:.4f}; "
                    f"Mmid,sus = {midspan_sustained_moment:.4f}"
                ),
                result=f"{midspan_total_moment:.4f}",
                units="kgf-m",
                clause=clauses.immediate_deflection,
            ),
        ]
    )
    if support_section is not None:
        steps.append(
            DeflectionCalculationStep(
                variable="Support moments",
                equation="Representative negative support moments for Ie,avg candidate",
                substitution=(
                    f"Msup,DL = {support_dead_moment:.4f}; Msup,total = {support_total_moment:.4f}; "
                    f"Msup,sus = {support_sustained_moment:.4f}"
                ),
                result=f"{support_total_moment:.4f}",
                units="kgf-m",
                clause=clauses.immediate_deflection,
                note="Used to calculate Ie at support and the averaged-Ie method candidate.",
            )
        )
    ie_steps: list[DeflectionCalculationStep] = [
        DeflectionCalculationStep(
            variable="Ie, DL",
            equation=_effective_inertia_equation_text(workflow.immediate_method),
            substitution="-",
            result=f"{dead_case.effective_inertia_cm4:.4f}",
            units="cm^4",
            clause=clauses.effective_inertia,
            note=(
                f"Ie,midspan = {dead_case.midspan_effective_inertia_cm4:.4f}; "
                f"Ie,avg = {dead_case.average_effective_inertia_cm4:.4f}; "
                f"selected = {selected_method.value}"
                if dead_case.average_effective_inertia_cm4 is not None
                else f"selected = {selected_method.value}"
            ),
        ),
        DeflectionCalculationStep(
            variable="Ie, total",
            equation=_effective_inertia_equation_text(workflow.immediate_method),
            substitution="-",
            result=f"{total_case.effective_inertia_cm4:.4f}",
            units="cm^4",
            clause=clauses.effective_inertia,
            note=(
                f"Ie,midspan = {total_case.midspan_effective_inertia_cm4:.4f}; "
                f"Ie,avg = {total_case.average_effective_inertia_cm4:.4f}; "
                f"selected = {selected_method.value}"
                if total_case.average_effective_inertia_cm4 is not None
                else f"selected = {selected_method.value}"
            ),
        ),
        DeflectionCalculationStep(
            variable="Ie, sustained",
            equation=_effective_inertia_equation_text(workflow.immediate_method),
            substitution="-",
            result=f"{sustained_case.effective_inertia_cm4:.4f}",
            units="cm^4",
            clause=clauses.effective_inertia,
            note=(
                f"Ie,midspan = {sustained_case.midspan_effective_inertia_cm4:.4f}; "
                f"Ie,avg = {sustained_case.average_effective_inertia_cm4:.4f}; "
                f"selected = {selected_method.value}"
                if sustained_case.average_effective_inertia_cm4 is not None
                else f"selected = {selected_method.value}"
            ),
        ),
        DeflectionCalculationStep(
            variable="Immediate deflection, total",
            equation="Uniform-load elastic deflection",
            substitution="-",
            result=f"{total_case.deflection_cm:.4f}",
            units="cm",
            clause=clauses.immediate_deflection,
            note=f"Selected Ie method = {selected_method.value}",
        ),
    ]
    if averaged_method is not None:
        ie_steps.extend(
            [
                DeflectionCalculationStep(
                    variable="Deflection Method 1",
                    equation="Midspan Ie only",
                    substitution="-",
                    result=f"{midspan_method.total_service_deflection_cm:.4f}",
                    units="cm",
                    clause=clauses.immediate_deflection,
                ),
                DeflectionCalculationStep(
                    variable="Deflection Method 2",
                    equation="Averaged Ie (midspan + support)",
                    substitution="-",
                    result=f"{averaged_method.total_service_deflection_cm:.4f}",
                    units="cm",
                    clause=clauses.immediate_deflection,
                ),
                DeflectionCalculationStep(
                    variable="Governing deflection method",
                    equation="Use larger deflection",
                    substitution=(
                        f"max({midspan_method.total_service_deflection_cm:.4f}, "
                        f"{averaged_method.total_service_deflection_cm:.4f})"
                    ),
                    result=selected_method.value,
                    units="-",
                    clause=clauses.immediate_deflection,
                    note="For conservative design, the larger deflection from the two Ie evaluation methods is used.",
                ),
            ]
        )
    steps.extend(
        ie_steps
        + [
            DeflectionCalculationStep(
                variable="Long-term multiplier",
                equation="lambda = x / (1 + 50 rho')",
                substitution=f"{design_input.long_term_factor_x:.4f} / (1 + 50 x compression steel ratio)",
                result=f"{long_term_multiplier:.4f}",
                units="-",
                clause=clauses.long_term,
            ),
            DeflectionCalculationStep(
                variable="Additional long-term deflection",
                equation="Delta_LT = lambda * Delta_sustained",
                substitution=f"{long_term_multiplier:.4f} x {sustained_case.deflection_cm:.4f}",
                result=f"{additional_long_term_deflection_cm:.4f}",
                units="cm",
                clause=clauses.long_term,
            ),
            DeflectionCalculationStep(
                variable="Immediate live deflection",
                equation="Delta_live = Delta_total - Delta_sustained",
                substitution=f"{total_case.deflection_cm:.4f} - {sustained_case.deflection_cm:.4f}",
                result=f"{immediate_live_deflection_cm:.4f}",
                units="cm",
                clause=clauses.long_term,
            ),
            DeflectionCalculationStep(
                variable="Total service deflection",
                equation="Delta_total_service = Delta_live + Delta_LT",
                substitution=f"{immediate_live_deflection_cm:.4f} + {additional_long_term_deflection_cm:.4f}",
                result=f"{total_service_deflection_cm:.4f}",
                units="cm",
                clause=clauses.long_term,
            ),
            DeflectionCalculationStep(
                variable="Capacity ratio (Deflection)",
                equation="Delta_calc / Delta_allow",
                substitution=f"{total_service_deflection_cm:.4f} / {allowable_cm:.4f}",
                result=f"{capacity_ratio:.4f}",
                units="-",
                clause=clauses.allowable_limit,
                status="PASS" if capacity_ratio <= 1.0 + 1e-9 else "FAIL",
            ),
        ]
    )
    return steps


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return math.nan
    return numerator / denominator
