from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from design.deflection import (
    AllowableDeflectionLimitInput,
    AllowableDeflectionPreset,
    DeflectionCodeVersion,
    DeflectionIeMethod,
    DeflectionMemberType,
    DeflectionSupportCondition,
)
from design.torsion import TorsionDesignInput, TorsionDesignResults


class DesignCode(str, Enum):
    ACI318_99 = "ACI318-99, EIT 1008-38"
    ACI318_11 = "ACI318-11"
    ACI318_14 = "ACI318-14"
    ACI318_19 = "ACI318-19"


class BeamType(str, Enum):
    SIMPLE = "Simple Beam"
    CONTINUOUS = "Continuous Beam"


class DeflectionBeamType(str, Enum):
    SINGLE_SPAN = "คานช่วงเดียว"
    EDGE_CONTINUOUS = "คานต่อเนื่องตัวริม"
    INTERIOR_CONTINUOUS = "คานต่อเนื่องตัวกลาง"
    CANTILEVER = "คานยื่น"


class VerificationStatus(str, Enum):
    VERIFIED_CODE = "Verified against code"
    NEEDS_REVIEW = "Needs manual engineering review"


class MaterialPropertyMode(str, Enum):
    DEFAULT = "Default"
    MANUAL = "Manual"


class ShearSpacingMode(str, Enum):
    AUTO = "Auto"
    MANUAL = "Manual"


@dataclass(slots=True)
class ProjectMetadata:
    design_code: DesignCode = DesignCode.ACI318_19
    tag: str = ""
    project_name: str = ""
    project_number: str = ""
    engineer: str = ""
    design_date: str = ""

    def __post_init__(self) -> None:
        self.tag = self.tag.strip()
        self.project_name = self.project_name.strip()
        self.project_number = self.project_number.strip()
        self.engineer = self.engineer.strip()
        self.design_date = self.design_date.strip()


@dataclass(slots=True)
class MaterialPropertiesInput:
    concrete_strength_ksc: float = 240.0
    main_steel_yield_ksc: float = 4000.0
    shear_steel_yield_ksc: float = 2400.0

    def __post_init__(self) -> None:
        _validate_positive(self.concrete_strength_ksc, "concrete_strength_ksc")
        _validate_positive(self.main_steel_yield_ksc, "main_steel_yield_ksc")
        _validate_positive(self.shear_steel_yield_ksc, "shear_steel_yield_ksc")


@dataclass(slots=True)
class MaterialPropertySetting:
    mode: MaterialPropertyMode = MaterialPropertyMode.DEFAULT
    manual_value: float | None = None

    def __post_init__(self) -> None:
        if self.mode == MaterialPropertyMode.MANUAL:
            if self.manual_value is None:
                raise ValueError("manual_value must be provided when mode is Manual.")
            _validate_positive(self.manual_value, "manual_value")
        elif self.manual_value is not None:
            _validate_positive(self.manual_value, "manual_value")


@dataclass(slots=True)
class MaterialPropertySettings:
    ec: MaterialPropertySetting = field(default_factory=MaterialPropertySetting)
    es: MaterialPropertySetting = field(default_factory=MaterialPropertySetting)
    fr: MaterialPropertySetting = field(default_factory=MaterialPropertySetting)


@dataclass(slots=True)
class BeamGeometryInput:
    width_cm: float = 20.0
    depth_cm: float = 40.0
    cover_cm: float = 4.0
    minimum_clear_spacing_cm: float = 2.5

    def __post_init__(self) -> None:
        _validate_positive(self.width_cm, "width_cm")
        _validate_positive(self.depth_cm, "depth_cm")
        _validate_non_negative(self.cover_cm, "cover_cm")
        _validate_positive(self.minimum_clear_spacing_cm, "minimum_clear_spacing_cm")
        if self.cover_cm >= self.depth_cm:
            raise ValueError("cover_cm must be smaller than depth_cm.")


@dataclass(slots=True)
class RebarGroupInput:
    diameter_mm: int | None = None
    count: int = 0

    def __post_init__(self) -> None:
        if self.diameter_mm == 0:
            self.diameter_mm = None
        if self.count < 0:
            raise ValueError("count must be zero or greater.")
        if self.diameter_mm is not None and self.diameter_mm < 0:
            raise ValueError("diameter_mm must be positive when provided.")
        if self.count == 0 and self.diameter_mm is None:
            return
        if self.count == 0 or self.diameter_mm is None:
            raise ValueError("diameter_mm and count must both be provided for a rebar group.")

    @property
    def diameter_cm(self) -> float:
        if self.diameter_mm is None:
            return 0.0
        return self.diameter_mm / 10

    @property
    def area_cm2(self) -> float:
        if self.diameter_mm is None or self.count == 0:
            return 0.0
        return (math.pi * (self.diameter_cm**2) / 4) * self.count


@dataclass(slots=True)
class RebarLayerInput:
    group_a: RebarGroupInput = field(default_factory=RebarGroupInput)
    group_b: RebarGroupInput = field(default_factory=RebarGroupInput)

    def __post_init__(self) -> None:
        if self.group_a.count not in {0, 2}:
            raise ValueError("group_a count must be 0 or 2 because group_a represents corner bars.")
        if self.group_b.count > 0 and self.group_a.count != 2:
            raise ValueError("group_a corner bars must be provided when group_b middle bars are used.")

    def groups(self) -> tuple[RebarGroupInput, RebarGroupInput]:
        return (self.group_a, self.group_b)

    def expanded_diameters_mm(self) -> list[int]:
        diameters: list[int] = []
        for group in self.groups():
            if group.diameter_mm is None:
                continue
            diameters.extend([group.diameter_mm] * group.count)
        return diameters

    @property
    def total_bars(self) -> int:
        return self.group_a.count + self.group_b.count

    @property
    def area_cm2(self) -> float:
        return self.group_a.area_cm2 + self.group_b.area_cm2


@dataclass(slots=True)
class ReinforcementArrangementInput:
    layer_1: RebarLayerInput = field(default_factory=RebarLayerInput)
    layer_2: RebarLayerInput = field(default_factory=RebarLayerInput)
    layer_3: RebarLayerInput = field(default_factory=RebarLayerInput)

    def layers(self) -> tuple[RebarLayerInput, RebarLayerInput, RebarLayerInput]:
        return (self.layer_1, self.layer_2, self.layer_3)

    @property
    def total_area_cm2(self) -> float:
        return sum(layer.area_cm2 for layer in self.layers())


@dataclass(slots=True)
class PositiveBendingInput:
    factored_moment_kgm: float = 4000.0
    compression_reinforcement: ReinforcementArrangementInput = field(
        default_factory=lambda: ReinforcementArrangementInput(
            layer_1=RebarLayerInput(group_a=RebarGroupInput(diameter_mm=12, count=2)),
        )
    )
    tension_reinforcement: ReinforcementArrangementInput = field(
        default_factory=lambda: ReinforcementArrangementInput(
            layer_1=RebarLayerInput(
                group_a=RebarGroupInput(diameter_mm=12, count=2),
                group_b=RebarGroupInput(diameter_mm=12, count=1),
            ),
        )
    )

    def __post_init__(self) -> None:
        _validate_non_negative(self.factored_moment_kgm, "factored_moment_kgm")


@dataclass(slots=True)
class ShearDesignInput:
    factored_shear_kg: float = 5000.0
    stirrup_diameter_mm: int = 9
    legs_per_plane: int = 2
    spacing_mode: ShearSpacingMode = ShearSpacingMode.AUTO
    provided_spacing_cm: float = 15.0

    def __post_init__(self) -> None:
        _validate_non_negative(self.factored_shear_kg, "factored_shear_kg")
        _validate_positive(self.stirrup_diameter_mm, "stirrup_diameter_mm")
        _validate_positive(self.legs_per_plane, "legs_per_plane")
        _validate_positive(self.provided_spacing_cm, "provided_spacing_cm")


@dataclass(slots=True)
class NegativeBendingInput:
    factored_moment_kgm: float = 6000.0
    compression_reinforcement: ReinforcementArrangementInput = field(
        default_factory=lambda: ReinforcementArrangementInput(
            layer_1=RebarLayerInput(group_a=RebarGroupInput(diameter_mm=12, count=2)),
        )
    )
    tension_reinforcement: ReinforcementArrangementInput = field(
        default_factory=lambda: ReinforcementArrangementInput(
            layer_1=RebarLayerInput(
                group_a=RebarGroupInput(diameter_mm=16, count=2),
                group_b=RebarGroupInput(diameter_mm=16, count=1),
            ),
        )
    )

    def __post_init__(self) -> None:
        _validate_non_negative(self.factored_moment_kgm, "factored_moment_kgm")


@dataclass(slots=True)
class DeflectionCheckInput:
    design_code: DeflectionCodeVersion = DeflectionCodeVersion.ACI318_19
    member_type: DeflectionMemberType = DeflectionMemberType.SIMPLE_BEAM
    support_condition: DeflectionSupportCondition = DeflectionSupportCondition.SIMPLE
    allowable_limit_preset: AllowableDeflectionPreset = AllowableDeflectionPreset.L_240
    allowable_limit_custom_denominator: int | None = None
    ie_method: DeflectionIeMethod = DeflectionIeMethod.WORST_CASE
    long_term_factor_x: float = 2.0
    service_dead_load_kgf_per_m: float = 0.0
    service_live_load_kgf_per_m: float = 0.0
    additional_sustained_load_kgf_per_m: float = 0.0
    beam_type: DeflectionBeamType = DeflectionBeamType.SINGLE_SPAN
    beam_type_factor_x: float = 2.0
    span_length_m: float = 1.0
    sustained_live_load_ratio: float = 0.3
    midspan_dead_load_service_moment_kgm: float = 30059.0
    midspan_live_load_service_moment_kgm: float = 18590.0
    support_dead_load_service_moment_kgm: float = 0.0
    support_live_load_service_moment_kgm: float = 0.0
    immediate_deflection_limit_description: str = (
        "à¸žà¸·à¹‰à¸™à¸—à¸µà¹ˆà¹„à¸¡à¹ˆà¸£à¸­à¸‡à¸£à¸±à¸šà¸«à¸£à¸·à¸­à¸•à¸´à¸”à¸à¸±à¸šà¸ªà¹ˆà¸§à¸™à¸—à¸µà¹ˆà¸¡à¸´à¹ƒà¸Šà¹ˆà¹‚à¸„à¸£à¸‡à¸ªà¸£à¹‰à¸²à¸‡à¸—à¸µà¹ˆà¸„à¸²à¸”à¸§à¹ˆà¸²à¸ˆà¸°à¹€à¸à¸´à¸”à¸à¸²à¸£à¹€à¸ªà¸µà¸¢à¸«à¸²à¸¢à¸ˆà¸²à¸à¸à¸²à¸£à¹à¸­à¹ˆà¸™à¸•à¸±à¸§à¸¡à¸²à¸à¹€à¸à¸´à¸™à¸„à¸§à¸£"
    )
    total_deflection_limit_description: str = (
        "à¸«à¸¥à¸±à¸‡à¸„à¸²à¸«à¸£à¸·à¸­à¸žà¸·à¹‰à¸™à¸—à¸µà¹ˆà¸£à¸­à¸‡à¸£à¸±à¸šà¸«à¸£à¸·à¸­à¸•à¸´à¸”à¸à¸±à¸šà¸ªà¹ˆà¸§à¸™à¸—à¸µà¹ˆà¸¡à¸´à¹ƒà¸Šà¹ˆà¹‚à¸„à¸£à¸‡à¸ªà¸£à¹‰à¸²à¸‡à¸—à¸µà¹ˆà¸„à¸²à¸”à¸§à¹ˆà¸²à¸ˆà¸°à¹„à¸¡à¹ˆà¹€à¸à¸´à¸”à¸à¸²à¸£à¹€à¸ªà¸µà¸¢à¸«à¸²à¸¢à¸ˆà¸²à¸à¸à¸²à¸£à¹à¸­à¹ˆà¸™à¸•à¸±à¸§à¸¡à¸²à¸à¹€à¸à¸´à¸™à¸„à¸§à¸£"
    )

    def __post_init__(self) -> None:
        _validate_positive(self.long_term_factor_x, "long_term_factor_x")
        _validate_positive(self.beam_type_factor_x, "beam_type_factor_x")
        _validate_positive(self.span_length_m, "span_length_m")
        _validate_non_negative(self.service_dead_load_kgf_per_m, "service_dead_load_kgf_per_m")
        _validate_non_negative(self.service_live_load_kgf_per_m, "service_live_load_kgf_per_m")
        _validate_non_negative(self.additional_sustained_load_kgf_per_m, "additional_sustained_load_kgf_per_m")
        _validate_non_negative(self.sustained_live_load_ratio, "sustained_live_load_ratio")
        _validate_non_negative(self.midspan_dead_load_service_moment_kgm, "midspan_dead_load_service_moment_kgm")
        _validate_non_negative(self.midspan_live_load_service_moment_kgm, "midspan_live_load_service_moment_kgm")
        if self.support_dead_load_service_moment_kgm > 0.0:
            raise ValueError("support_dead_load_service_moment_kgm must be zero or negative.")
        if self.support_live_load_service_moment_kgm > 0.0:
            raise ValueError("support_live_load_service_moment_kgm must be zero or negative.")
        if self.sustained_live_load_ratio > 1.0:
            raise ValueError("sustained_live_load_ratio must be between 0.0 and 1.0.")
        if self.allowable_limit_preset == AllowableDeflectionPreset.CUSTOM:
            if self.allowable_limit_custom_denominator is None or self.allowable_limit_custom_denominator <= 0:
                raise ValueError("allowable_limit_custom_denominator must be provided when the preset is Custom.")
        self.immediate_deflection_limit_description = self.immediate_deflection_limit_description.strip()
        self.total_deflection_limit_description = self.total_deflection_limit_description.strip()

    @property
    def allowable_limit(self) -> AllowableDeflectionLimitInput:
        return AllowableDeflectionLimitInput(
            preset=self.allowable_limit_preset,
            custom_denominator=self.allowable_limit_custom_denominator,
        )


@dataclass(slots=True)
class BeamDesignInputSet:
    beam_type: BeamType = BeamType.SIMPLE
    consider_deflection: bool = False
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    materials: MaterialPropertiesInput = field(default_factory=MaterialPropertiesInput)
    geometry: BeamGeometryInput = field(default_factory=BeamGeometryInput)
    positive_bending: PositiveBendingInput = field(default_factory=PositiveBendingInput)
    shear: ShearDesignInput = field(default_factory=ShearDesignInput)
    torsion: TorsionDesignInput = field(default_factory=TorsionDesignInput)
    negative_bending: NegativeBendingInput = field(default_factory=NegativeBendingInput)
    deflection: DeflectionCheckInput = field(default_factory=DeflectionCheckInput)
    material_settings: MaterialPropertySettings = field(default_factory=MaterialPropertySettings)

    @property
    def has_negative_design(self) -> bool:
        return self.beam_type == BeamType.CONTINUOUS


@dataclass(slots=True)
class LayerSpacingResult:
    layer_index: int
    group_a_diameter_mm: int | None
    group_a_count: int
    group_b_diameter_mm: int | None
    group_b_count: int
    spacing_cm: float | None
    required_spacing_cm: float | None
    status: str
    message: str = ""


@dataclass(slots=True)
class ReinforcementSpacingResults:
    layer_1: LayerSpacingResult
    layer_2: LayerSpacingResult
    layer_3: LayerSpacingResult
    overall_status: str

    def layers(self) -> tuple[LayerSpacingResult, LayerSpacingResult, LayerSpacingResult]:
        return (self.layer_1, self.layer_2, self.layer_3)


@dataclass(slots=True)
class MaterialResults:
    fc_prime_ksc: float
    fy_ksc: float
    fvy_ksc: float
    ec_ksc: float
    es_ksc: float
    modular_ratio_n: float
    modulus_of_rupture_fr_ksc: float
    beta_1: float
    ec_mode: MaterialPropertyMode
    es_mode: MaterialPropertyMode
    fr_mode: MaterialPropertyMode
    ec_default_ksc: float
    es_default_ksc: float
    fr_default_ksc: float
    ec_default_logic: str
    es_default_logic: str
    fr_default_logic: str


@dataclass(slots=True)
class BeamGeometryResults:
    section_area_cm2: float
    gross_moment_of_inertia_cm4: float
    cover_plus_stirrup_cm: float
    positive_compression_centroid_d_prime_cm: float
    positive_tension_centroid_from_bottom_d_cm: float
    negative_compression_centroid_from_bottom_cm: float | None
    negative_tension_centroid_from_top_cm: float | None
    d_plus_cm: float
    d_minus_cm: float | None
    positive_compression_spacing: ReinforcementSpacingResults
    positive_tension_spacing: ReinforcementSpacingResults
    negative_compression_spacing: ReinforcementSpacingResults | None
    negative_tension_spacing: ReinforcementSpacingResults | None


@dataclass(slots=True)
class FlexuralDesignResults:
    phi: float
    ru_kg_per_cm2: float
    rho_required: float
    as_required_cm2: float
    as_provided_cm2: float
    rho_provided: float
    rho_min: float
    rho_max: float
    as_min_cm2: float
    as_max_cm2: float
    as_status: str
    a_cm: float
    c_cm: float
    dt_cm: float
    ety: float
    et: float
    mn_kgm: float
    phi_mn_kgm: float
    ratio: float
    ratio_status: str
    design_status: str
    review_note: str = ""


@dataclass(slots=True)
class ShearDesignResults:
    phi: float
    vc_kg: float
    phi_vc_kg: float
    vc_max_kg: float | None
    vc_capped_by_max: bool
    vs_max_kg: float
    phi_vs_max_kg: float
    phi_vs_required_kg: float
    nominal_vs_required_kg: float
    av_cm2: float
    av_min_cm2: float
    size_effect_factor: float
    size_effect_applied: bool
    s_max_from_av_cm: float
    s_max_from_vs_cm: float
    required_spacing_cm: float
    provided_spacing_cm: float
    spacing_mode: ShearSpacingMode
    vs_provided_kg: float
    phi_vs_provided_kg: float
    vn_kg: float
    phi_vn_kg: float
    stirrup_spacing_cm: float
    capacity_ratio: float
    design_status: str
    section_change_required: bool = False
    section_change_note: str = ""
    review_note: str = ""


@dataclass(slots=True)
class CombinedShearTorsionResults:
    active: bool
    torsion_ignored: bool
    ignore_message: str
    vu_kg: float
    tu_kgfm: float
    shear_required_transverse_mm2_per_mm: float
    torsion_required_transverse_mm2_per_mm: float
    combined_required_transverse_mm2_per_mm: float
    provided_transverse_mm2_per_mm: float
    governing_case: str
    capacity_ratio: float
    design_status: str
    stirrup_diameter_mm: int
    stirrup_legs: int
    stirrup_spacing_cm: float
    summary_note: str = ""
    required_spacing_cm: float = 0.0
    spacing_limit_reason: str = ""


@dataclass(slots=True)
class DeflectionCheckResults:
    status: str
    note: str
    verification_status: VerificationStatus
    code_version: str = ""
    member_type: str = ""
    support_condition: str = ""
    ie_method_selected: str = ""
    ie_method_governing: str = ""
    allowable_limit_label: str = ""
    allowable_limit_denominator: int = 0
    allowable_deflection_cm: float = 0.0
    span_length_m: float = 0.0
    load_basis_note: str = ""
    pass_fail_summary: str = ""
    mockup_only: bool = False
    immediate_clause: str = ""
    long_term_clause: str = ""
    limit_clause: str = ""
    service_dead_load_kgf_per_m: float = 0.0
    service_live_load_kgf_per_m: float = 0.0
    additional_sustained_load_kgf_per_m: float = 0.0
    sustained_live_load_ratio: float = 0.0
    service_sustained_load_kgf_per_m: float = 0.0
    midspan_dead_load_service_moment_kgm: float = 0.0
    midspan_live_load_service_moment_kgm: float = 0.0
    support_dead_load_service_moment_kgm: float = 0.0
    support_live_load_service_moment_kgm: float = 0.0
    gross_moment_of_inertia_cm4: float = 0.0
    midspan_cracking_moment_kgm: float = 0.0
    support_cracking_moment_kgm: float | None = None
    midspan_cracked_neutral_axis_cm: float = 0.0
    support_cracked_neutral_axis_cm: float | None = None
    midspan_cracked_inertia_cm4: float = 0.0
    support_cracked_inertia_cm4: float | None = None
    ie_midspan_total_cm4: float = 0.0
    ie_support_total_cm4: float | None = None
    ie_average_total_cm4: float | None = None
    ie_dead_cm4: float = 0.0
    ie_total_cm4: float = 0.0
    ie_sustained_cm4: float = 0.0
    method_1_total_service_deflection_cm: float = 0.0
    method_2_total_service_deflection_cm: float | None = None
    immediate_dead_deflection_cm: float = 0.0
    immediate_total_deflection_cm: float = 0.0
    immediate_live_deflection_cm: float = 0.0
    sustained_initial_deflection_cm: float = 0.0
    long_term_multiplier: float = 0.0
    additional_long_term_deflection_cm: float = 0.0
    total_service_deflection_cm: float = 0.0
    calculated_deflection_cm: float = 0.0
    capacity_ratio: float = 0.0
    governing_result: str = ""
    warnings: tuple[str, ...] = ()
    steps: tuple[object, ...] = ()


@dataclass(slots=True)
class ReviewFlag:
    title: str
    severity: str
    message: str
    verification_status: VerificationStatus


@dataclass(slots=True)
class BeamDesignResults:
    materials: MaterialResults
    beam_geometry: BeamGeometryResults
    positive_bending: FlexuralDesignResults
    shear: ShearDesignResults
    torsion: TorsionDesignResults
    combined_shear_torsion: CombinedShearTorsionResults
    negative_bending: FlexuralDesignResults | None
    deflection: DeflectionCheckResults
    warnings: list[str]
    review_flags: list[ReviewFlag]
    overall_status: str
    overall_note: str = ""


def default_beam_design_inputs() -> BeamDesignInputSet:
    return BeamDesignInputSet(
        beam_type=BeamType.SIMPLE,
        metadata=ProjectMetadata(design_code=DesignCode.ACI318_19, tag=""),
        materials=MaterialPropertiesInput(
            concrete_strength_ksc=240.0,
            main_steel_yield_ksc=4000.0,
            shear_steel_yield_ksc=2400.0,
        ),
        geometry=BeamGeometryInput(
            width_cm=20.0,
            depth_cm=40.0,
            cover_cm=4.0,
            minimum_clear_spacing_cm=2.5,
        ),
        positive_bending=PositiveBendingInput(
            factored_moment_kgm=4000.0,
            compression_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(group_a=RebarGroupInput(diameter_mm=12, count=2)),
            ),
            tension_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=12, count=2),
                    group_b=RebarGroupInput(diameter_mm=12, count=1),
                ),
            ),
        ),
        shear=ShearDesignInput(
            factored_shear_kg=5000.0,
            stirrup_diameter_mm=9,
            legs_per_plane=2,
            spacing_mode=ShearSpacingMode.AUTO,
            provided_spacing_cm=15.0,
        ),
    )


def _validate_positive(value: float, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")


def _validate_non_negative(value: float, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be zero or greater.")
