from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DeflectionCodeVersion(str, Enum):
    ACI318_99 = "ACI 318-99"
    ACI318_11 = "ACI 318-11"
    ACI318_14 = "ACI 318-14"
    ACI318_19 = "ACI 318-19"


class DeflectionMemberType(str, Enum):
    SIMPLE_BEAM = "Simple beam"
    CONTINUOUS_BEAM = "Continuous beam"
    CANTILEVER_BEAM = "Cantilever beam"


class DeflectionSupportCondition(str, Enum):
    SIMPLE = "Simple"
    CONTINUOUS_2_SPANS = "Continuous, 2 spans"
    CONTINUOUS_3_OR_MORE_SPANS = "Continuous, 3 or more spans"
    CANTILEVER_PLACEHOLDER = "Cantilever placeholder"


class DeflectionIeMethod(str, Enum):
    MIDSPAN_ONLY = "Midspan Ie only"
    AVERAGED = "Averaged Ie (midspan + support)"
    WORST_CASE = "Conservative / Worst Case"


class AllowableDeflectionPreset(str, Enum):
    L_120 = "L/120"
    L_180 = "L/180"
    L_240 = "L/240"
    L_360 = "L/360"
    L_480 = "L/480"
    L_600 = "L/600"
    CUSTOM = "Custom"


class DeflectionVerificationStatus(str, Enum):
    VERIFIED = "Verified against implemented workflow"
    NEEDS_REVIEW = "Needs manual engineering review"


@dataclass(slots=True)
class AllowableDeflectionLimitInput:
    preset: AllowableDeflectionPreset = AllowableDeflectionPreset.L_240
    custom_denominator: int | None = None

    def __post_init__(self) -> None:
        if self.preset == AllowableDeflectionPreset.CUSTOM:
            if self.custom_denominator is None:
                raise ValueError("custom_denominator is required when the allowable limit preset is Custom.")
            if self.custom_denominator <= 0:
                raise ValueError("custom_denominator must be greater than zero.")
        elif self.custom_denominator is not None and self.custom_denominator <= 0:
            raise ValueError("custom_denominator must be greater than zero when provided.")


@dataclass(slots=True)
class DeflectionServiceLoadInput:
    dead_load_kgf_per_m: float = 0.0
    live_load_kgf_per_m: float = 0.0
    additional_sustained_load_kgf_per_m: float = 0.0
    sustained_live_load_ratio: float = 0.3
    support_dead_load_service_moment_kgm: float = 0.0
    support_live_load_service_moment_kgm: float = 0.0

    def __post_init__(self) -> None:
        _validate_non_negative(self.dead_load_kgf_per_m, "dead_load_kgf_per_m")
        _validate_non_negative(self.live_load_kgf_per_m, "live_load_kgf_per_m")
        _validate_non_negative(self.additional_sustained_load_kgf_per_m, "additional_sustained_load_kgf_per_m")
        _validate_non_negative(self.sustained_live_load_ratio, "sustained_live_load_ratio")
        if self.support_dead_load_service_moment_kgm > 0.0:
            raise ValueError("support_dead_load_service_moment_kgm must be zero or negative.")
        if self.support_live_load_service_moment_kgm > 0.0:
            raise ValueError("support_live_load_service_moment_kgm must be zero or negative.")
        if self.sustained_live_load_ratio > 1.0:
            raise ValueError("sustained_live_load_ratio must be between 0.0 and 1.0.")


@dataclass(slots=True)
class DeflectionSectionReinforcementInput:
    tension_as_cm2: float
    compression_as_cm2: float
    effective_depth_cm: float
    compression_depth_cm: float

    def __post_init__(self) -> None:
        _validate_positive(self.effective_depth_cm, "effective_depth_cm")
        _validate_non_negative(self.compression_depth_cm, "compression_depth_cm")
        _validate_non_negative(self.tension_as_cm2, "tension_as_cm2")
        _validate_non_negative(self.compression_as_cm2, "compression_as_cm2")
        if self.compression_depth_cm >= self.effective_depth_cm:
            raise ValueError("compression_depth_cm must be smaller than effective_depth_cm.")


@dataclass(slots=True)
class DeflectionDesignInput:
    code_version: DeflectionCodeVersion = DeflectionCodeVersion.ACI318_19
    member_type: DeflectionMemberType = DeflectionMemberType.SIMPLE_BEAM
    support_condition: DeflectionSupportCondition = DeflectionSupportCondition.SIMPLE
    allowable_limit: AllowableDeflectionLimitInput = field(default_factory=AllowableDeflectionLimitInput)
    ie_method: DeflectionIeMethod = DeflectionIeMethod.WORST_CASE
    span_length_m: float = 1.0
    long_term_factor_x: float = 2.0
    width_cm: float = 20.0
    depth_cm: float = 40.0
    gross_moment_of_inertia_cm4: float = 106666.66666666667
    concrete_strength_ksc: float = 240.0
    ec_ksc: float = 233928.194110928
    fr_ksc: float = 30.983866769659336
    modular_ratio_n: float = 8.720624753049812
    service_loads: DeflectionServiceLoadInput = field(default_factory=DeflectionServiceLoadInput)
    midspan_section: DeflectionSectionReinforcementInput = field(
        default_factory=lambda: DeflectionSectionReinforcementInput(
            tension_as_cm2=3.392920065876977,
            compression_as_cm2=2.261946710584651,
            effective_depth_cm=34.5,
            compression_depth_cm=5.5,
        )
    )
    support_section: DeflectionSectionReinforcementInput | None = None

    def __post_init__(self) -> None:
        _validate_positive(self.span_length_m, "span_length_m")
        _validate_positive(self.long_term_factor_x, "long_term_factor_x")
        _validate_positive(self.width_cm, "width_cm")
        _validate_positive(self.depth_cm, "depth_cm")
        _validate_positive(self.gross_moment_of_inertia_cm4, "gross_moment_of_inertia_cm4")
        _validate_positive(self.concrete_strength_ksc, "concrete_strength_ksc")
        _validate_positive(self.ec_ksc, "ec_ksc")
        _validate_positive(self.fr_ksc, "fr_ksc")
        _validate_positive(self.modular_ratio_n, "modular_ratio_n")
        if self.member_type == DeflectionMemberType.SIMPLE_BEAM and self.support_condition != DeflectionSupportCondition.SIMPLE:
            raise ValueError("Simple beam member type must use the Simple support condition.")
        if self.member_type == DeflectionMemberType.CONTINUOUS_BEAM and self.support_condition not in {
            DeflectionSupportCondition.CONTINUOUS_2_SPANS,
            DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS,
        }:
            raise ValueError("Continuous beam member type must use a continuous support condition.")
        if self.member_type == DeflectionMemberType.CANTILEVER_BEAM and self.support_condition != DeflectionSupportCondition.CANTILEVER_PLACEHOLDER:
            raise ValueError("Cantilever beam member type must use the cantilever placeholder support condition.")


@dataclass(frozen=True, slots=True)
class DeflectionCalculationStep:
    variable: str
    equation: str
    substitution: str
    result: str
    units: str
    clause: str
    note: str = ""
    status: str = ""


@dataclass(slots=True)
class DeflectionDesignResults:
    code_version: str
    member_type: str
    support_condition: str
    ie_method_selected: str
    ie_method_governing: str
    allowable_limit_label: str
    allowable_limit_denominator: int
    allowable_deflection_cm: float
    span_length_m: float
    load_basis_note: str
    status: str
    verification_status: DeflectionVerificationStatus
    pass_fail_summary: str
    note: str
    mockup_only: bool
    immediate_clause: str
    long_term_clause: str
    limit_clause: str
    service_dead_load_kgf_per_m: float
    service_live_load_kgf_per_m: float
    additional_sustained_load_kgf_per_m: float
    sustained_live_load_ratio: float
    service_sustained_load_kgf_per_m: float
    midspan_dead_load_service_moment_kgm: float
    midspan_live_load_service_moment_kgm: float
    support_dead_load_service_moment_kgm: float
    support_live_load_service_moment_kgm: float
    gross_moment_of_inertia_cm4: float
    midspan_cracking_moment_kgm: float
    support_cracking_moment_kgm: float | None
    midspan_cracked_neutral_axis_cm: float
    support_cracked_neutral_axis_cm: float | None
    midspan_cracked_inertia_cm4: float
    support_cracked_inertia_cm4: float | None
    ie_midspan_total_cm4: float
    ie_support_total_cm4: float | None
    ie_average_total_cm4: float | None
    ie_dead_cm4: float
    ie_total_cm4: float
    ie_sustained_cm4: float
    method_1_total_service_deflection_cm: float
    method_2_total_service_deflection_cm: float | None
    immediate_dead_deflection_cm: float
    immediate_total_deflection_cm: float
    immediate_live_deflection_cm: float
    sustained_initial_deflection_cm: float
    long_term_multiplier: float
    additional_long_term_deflection_cm: float
    total_service_deflection_cm: float
    calculated_deflection_cm: float
    capacity_ratio: float
    governing_result: str
    warnings: tuple[str, ...] = ()
    steps: tuple[DeflectionCalculationStep, ...] = ()


def _validate_positive(value: float, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")


def _validate_non_negative(value: float, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be zero or greater.")
