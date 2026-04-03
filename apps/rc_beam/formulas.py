from __future__ import annotations

from dataclasses import replace
import math

from design.deflection import (
    DeflectionDesignInput as EngineDeflectionDesignInput,
    DeflectionMemberType as EngineDeflectionMemberType,
    DeflectionSectionReinforcementInput as EngineDeflectionSectionReinforcementInput,
    DeflectionServiceLoadInput as EngineDeflectionServiceLoadInput,
    DeflectionSupportCondition as EngineDeflectionSupportCondition,
    design_deflection_check,
)
from design.torsion import (
    TorsionDesignResults,
    TorsionDesignMaterialInput,
    TorsionSectionGeometryInput,
)
from design.torsion.torsion_units import kgf_m_to_n_mm, ksc_to_mpa
from engines.common import (
    DEFAULT_EC_LOGIC as ENGINE_DEFAULT_EC_LOGIC,
    DEFAULT_ES_LOGIC as ENGINE_DEFAULT_ES_LOGIC,
    DEFAULT_FR_LOGIC as ENGINE_DEFAULT_FR_LOGIC,
    BeamGeometryInputData as EngineBeamGeometryInputData,
    BeamSectionInput as EngineBeamSectionInput,
    DesignCode as EngineDesignCode,
    MaterialPropertiesInput as EngineMaterialPropertiesInput,
    MaterialPropertyMode as EngineMaterialPropertyMode,
    MaterialPropertySetting as EngineMaterialPropertySetting,
    MaterialPropertySettings as EngineMaterialPropertySettings,
    RebarGroupInput as EngineRebarGroupInput,
    RebarLayerInput as EngineRebarLayerInput,
    ReinforcementArrangementInput as EngineReinforcementArrangementInput,
    ShearSpacingMode as EngineShearSpacingMode,
    calculate_beam_geometry as calculate_engine_beam_geometry,
    calculate_default_ec_ksc as calculate_engine_default_ec_ksc,
    calculate_default_es_ksc as calculate_engine_default_es_ksc,
    calculate_default_fr_ksc as calculate_engine_default_fr_ksc,
    calculate_material_properties as calculate_engine_material_properties,
    calculate_reinforcement_spacing as calculate_engine_reinforcement_spacing,
)
from engines.moment import MomentBeamInput, MomentDesignCase, design_moment_beam
from engines.shear import ShearBeamInput, design_shear_beam
from engines.torsion import TorsionBeamInput, design_torsion_beam

from .models import (
    BeamBehaviorMode,
    BeamDesignInputSet,
    BeamDesignResults,
    BeamGeometryInput,
    BeamGeometryResults,
    BeamType,
    CombinedShearTorsionResults,
    DeflectionCheckInput,
    DeflectionCheckResults,
    DesignCode,
    DemandInputMode,
    FlexuralDesignResults,
    LayerSpacingResult,
    MaterialPropertiesInput,
    MaterialPropertyMode,
    MaterialPropertySettings,
    MaterialResults,
    NegativeBendingInput,
    PositiveBendingInput,
    RebarGroupInput,
    RebarLayerInput,
    ReinforcementArrangementInput,
    ReinforcementSpacingResults,
    ReviewFlag,
    ShearDesignInput,
    ShearDesignResults,
    ShearSpacingMode,
    VerificationStatus,
)


ECU = 0.003
DEFAULT_EC_LOGIC = ENGINE_DEFAULT_EC_LOGIC
DEFAULT_ES_LOGIC = ENGINE_DEFAULT_ES_LOGIC
DEFAULT_FR_LOGIC = ENGINE_DEFAULT_FR_LOGIC
ES_KSC = calculate_engine_default_es_ksc()
AUTO_SHEAR_SPACING_INCREMENT_CM = 2.5


def calculate_default_ec_ksc(fc_prime_ksc: float) -> float:
    return calculate_engine_default_ec_ksc(fc_prime_ksc)


def calculate_default_es_ksc() -> float:
    return calculate_engine_default_es_ksc()


def calculate_default_fr_ksc(fc_prime_ksc: float) -> float:
    return calculate_engine_default_fr_ksc(fc_prime_ksc)


def calculate_material_properties(
    materials: MaterialPropertiesInput,
    material_settings: MaterialPropertySettings | None = None,
) -> MaterialResults:
    engine_results = calculate_engine_material_properties(
        _to_engine_materials(materials),
        _to_engine_material_settings(material_settings or MaterialPropertySettings()),
    )
    return _to_app_material_results(engine_results)


def calculate_reinforcement_spacing(
    geometry: BeamGeometryInput,
    reinforcement: ReinforcementArrangementInput,
    stirrup_diameter_mm: int,
) -> ReinforcementSpacingResults:
    engine_results = calculate_engine_reinforcement_spacing(
        _to_engine_geometry(geometry),
        _to_engine_reinforcement(reinforcement),
        stirrup_diameter_mm,
    )
    return _to_app_spacing_results(engine_results)


def calculate_beam_geometry(
    geometry: BeamGeometryInput,
    positive_bending: PositiveBendingInput,
    negative_bending: NegativeBendingInput,
    shear: ShearDesignInput,
    *,
    include_negative: bool = True,
) -> BeamGeometryResults:
    engine_results = calculate_engine_beam_geometry(
        EngineBeamGeometryInputData(
            geometry=_to_engine_geometry(geometry),
            positive_compression_reinforcement=_to_engine_reinforcement(positive_bending.compression_reinforcement),
            positive_tension_reinforcement=_to_engine_reinforcement(positive_bending.tension_reinforcement),
            stirrup_diameter_mm=shear.stirrup_diameter_mm,
            negative_compression_reinforcement=_to_engine_reinforcement(negative_bending.compression_reinforcement),
            negative_tension_reinforcement=_to_engine_reinforcement(negative_bending.tension_reinforcement),
            include_negative=include_negative,
        )
    )
    return _to_app_beam_geometry_results(engine_results)


def _positive_style_bending_input(negative_bending: NegativeBendingInput) -> PositiveBendingInput:
    return PositiveBendingInput(
        factored_moment_kgm=negative_bending.factored_moment_kgm,
        compression_reinforcement=negative_bending.compression_reinforcement,
        tension_reinforcement=negative_bending.tension_reinforcement,
    )


def _resolved_simple_support_bending_input(design_inputs: BeamDesignInputSet) -> PositiveBendingInput:
    return PositiveBendingInput(
        factored_moment_kgm=design_inputs.resolved_simple_support_moment_kgm,
        compression_reinforcement=design_inputs.simple_support_bending.compression_reinforcement,
        tension_reinforcement=design_inputs.simple_support_bending.tension_reinforcement,
    )


def _resolve_primary_geometry_inputs(
    design_inputs: BeamDesignInputSet,
) -> tuple[PositiveBendingInput, NegativeBendingInput, bool]:
    if design_inputs.has_positive_design:
        positive_bending = design_inputs.positive_bending
    else:
        positive_bending = _positive_style_bending_input(design_inputs.cantilever_negative_bending)
    negative_bending = design_inputs.negative_bending if design_inputs.has_support_negative_design else NegativeBendingInput()
    return positive_bending, negative_bending, design_inputs.has_support_negative_design


def _section_depth_from_positive_style_input(
    geometry: BeamGeometryInput,
    section_bending: PositiveBendingInput,
    shear: ShearDesignInput,
) -> float:
    geometry_results = calculate_beam_geometry(
        geometry,
        section_bending,
        NegativeBendingInput(),
        shear,
        include_negative=False,
    )
    return geometry_results.d_plus_cm


def _calculate_positive_oriented_bending_design(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    section_bending: PositiveBendingInput,
    design_inputs: BeamDesignInputSet,
) -> FlexuralDesignResults:
    engine_results = design_moment_beam(
        MomentBeamInput(
            design_code=_to_engine_design_code(design_inputs.metadata.design_code),
            materials=_to_engine_materials(materials),
            geometry=_to_engine_geometry(geometry),
            stirrup_diameter_mm=design_inputs.shear.stirrup_diameter_mm,
            factored_moment_kgm=section_bending.factored_moment_kgm,
            positive_compression_reinforcement=_to_engine_reinforcement(section_bending.compression_reinforcement),
            positive_tension_reinforcement=_to_engine_reinforcement(section_bending.tension_reinforcement),
            negative_compression_reinforcement=_to_engine_reinforcement(design_inputs.negative_bending.compression_reinforcement),
            negative_tension_reinforcement=_to_engine_reinforcement(design_inputs.negative_bending.tension_reinforcement),
            material_settings=_to_engine_material_settings(design_inputs.material_settings),
            design_case=MomentDesignCase.POSITIVE,
        )
    )
    material_results = calculate_material_properties(materials, design_inputs.material_settings)
    geometry_results = calculate_beam_geometry(
        geometry,
        section_bending,
        design_inputs.negative_bending,
        design_inputs.shear,
        include_negative=design_inputs.has_negative_design,
    )
    return _apply_beam_behavior_to_flexural_results(
        base_results=_to_app_moment_results(engine_results),
        design_inputs=design_inputs,
        material_results=material_results,
        geometry_results=geometry_results,
        tension_reinforcement=section_bending.tension_reinforcement,
        compression_reinforcement=section_bending.compression_reinforcement,
        factored_moment_kgm=section_bending.factored_moment_kgm,
        effective_depth_cm=geometry_results.d_plus_cm,
        compression_depth_cm=geometry_results.positive_compression_centroid_d_prime_cm,
        compression_face="top",
    )


def _positive_style_bending_for_section(
    design_inputs: BeamDesignInputSet,
    section_key: str,
) -> PositiveBendingInput:
    if section_key == "support":
        return _resolved_simple_support_bending_input(design_inputs)
    if section_key in {"middle", "positive"}:
        return design_inputs.positive_bending
    if section_key == "negative":
        return _positive_style_bending_input(design_inputs.negative_bending)
    if section_key == "cantilever_negative":
        return _positive_style_bending_input(design_inputs.cantilever_negative_bending)
    return design_inputs.positive_bending


def _resolve_span_region_shear(
    shear: ShearDesignInput,
) -> tuple[float, bool, str]:
    if shear.span_region_mode == DemandInputMode.AUTO:
        reduction_ratio = abs(1.0 - (2.0 * shear.span_region_relative_position))
        factored_shear_kg = shear.resolved_support_factored_shear_kg * reduction_ratio
        return (
            factored_shear_kg,
            True,
            (
                "Auto-calculated from support Vu using uniform-load linear shear reduction "
                f"at x/L = {shear.span_region_relative_position:.2f}."
            ),
        )
    return (
        shear.resolved_span_region_factored_shear_kg,
        False,
        f"Manual span-region shear at x/L = {shear.span_region_relative_position:.2f}.",
    )


def _resolve_shear_region_demands(
    design_inputs: BeamDesignInputSet,
    shear: ShearDesignInput,
) -> tuple[tuple[str, str, str, str, float, bool, str], ...]:
    demands: list[tuple[str, str, str, str, float, bool, str]] = []
    span_region_vu_kg, span_region_auto, span_region_note = _resolve_span_region_shear(shear)
    for region_key, region_label, section_key, section_label in design_inputs.active_vu_region_mappings:
        if region_key == "support":
            demands.append(
                (
                    region_key,
                    region_label,
                    section_key,
                    section_label,
                    shear.resolved_support_factored_shear_kg,
                    False,
                    "Support-region shear demand.",
                )
            )
        elif region_key in {"middle", "span_region"}:
            demands.append(
                (
                    region_key,
                    region_label,
                    section_key,
                    section_label,
                    span_region_vu_kg,
                    span_region_auto,
                    span_region_note,
                )
            )
        else:
            demands.append(
                (
                    region_key,
                    region_label,
                    section_key,
                    section_label,
                    shear.resolved_cantilever_factored_shear_kg,
                    False,
                    "Cantilever-region shear demand.",
                )
            )
    return tuple(demands)


def _calculate_shear_design_for_region(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    shear: ShearDesignInput,
    design_inputs: BeamDesignInputSet,
    *,
    region_key: str,
    region_label: str,
    section_key: str,
    section_label: str,
    factored_shear_kg: float,
    auto_calculated: bool,
    location_note: str,
) -> ShearDesignResults:
    design_section_bending = _positive_style_bending_for_section(design_inputs, section_key)
    effective_depth_cm = _section_depth_from_positive_style_input(geometry, design_section_bending, shear)
    region_shear = replace(shear, factored_shear_kg=factored_shear_kg)
    engine_results = design_shear_beam(
        ShearBeamInput(
            design_code=_to_engine_design_code(design_inputs.metadata.design_code),
            materials=_to_engine_materials(materials),
            geometry=_to_engine_geometry(geometry),
            factored_shear_kg=region_shear.factored_shear_kg,
            stirrup_diameter_mm=region_shear.stirrup_diameter_mm,
            legs_per_plane=region_shear.legs_per_plane,
            spacing_mode=_to_engine_shear_spacing_mode(region_shear.spacing_mode),
            provided_spacing_cm=region_shear.provided_spacing_cm,
            positive_compression_reinforcement=_to_engine_reinforcement(design_section_bending.compression_reinforcement),
            positive_tension_reinforcement=_to_engine_reinforcement(design_section_bending.tension_reinforcement),
            negative_compression_reinforcement=_to_engine_reinforcement(ReinforcementArrangementInput()),
            negative_tension_reinforcement=_to_engine_reinforcement(ReinforcementArrangementInput()),
            include_negative_geometry=False,
        )
    )
    return replace(
        _to_app_shear_results(engine_results),
        region_key=region_key,
        region_label=region_label,
        input_factored_shear_kg=factored_shear_kg,
        auto_calculated=auto_calculated,
        location_note=location_note,
        design_section_key=section_key,
        design_section_label=section_label,
        effective_depth_cm=effective_depth_cm,
    )


def calculate_shear_design_regions(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    shear: ShearDesignInput,
    design_inputs: BeamDesignInputSet,
) -> tuple[ShearDesignResults, tuple[ShearDesignResults, ...]]:
    region_results = tuple(
        _calculate_shear_design_for_region(
            materials,
            geometry,
            shear,
            design_inputs,
            region_key=region_key,
            region_label=region_label,
            section_key=section_key,
            section_label=section_label,
            factored_shear_kg=factored_shear_kg,
            auto_calculated=auto_calculated,
            location_note=location_note,
        )
        for region_key, region_label, section_key, section_label, factored_shear_kg, auto_calculated, location_note in _resolve_shear_region_demands(
            design_inputs,
            shear,
        )
    )
    if not region_results:
        fallback = _calculate_shear_design_for_region(
            materials,
            geometry,
            shear,
            design_inputs,
            region_key="support",
            region_label="Support Vu",
            section_key="positive",
            section_label="Positive Section",
            factored_shear_kg=shear.factored_shear_kg,
            auto_calculated=False,
            location_note="Fallback shear region.",
        )
        return fallback, (fallback,)
    governing = max(region_results, key=lambda result: result.capacity_ratio)
    return governing, region_results


def calculate_positive_bending_design(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    positive_bending: PositiveBendingInput,
    design_inputs: BeamDesignInputSet,
) -> FlexuralDesignResults:
    return _calculate_positive_oriented_bending_design(materials, geometry, positive_bending, design_inputs)


def calculate_shear_design(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    shear: ShearDesignInput,
    design_inputs: BeamDesignInputSet,
) -> ShearDesignResults:
    governing_result, _ = calculate_shear_design_regions(materials, geometry, shear, design_inputs)
    return governing_result


def calculate_negative_bending_design(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    negative_bending: NegativeBendingInput,
    design_inputs: BeamDesignInputSet,
) -> FlexuralDesignResults:
    return _calculate_negative_oriented_bending_design(
        materials,
        geometry,
        negative_bending,
        design_inputs,
    )


def calculate_cantilever_negative_bending_design(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    cantilever_negative_bending: NegativeBendingInput,
    design_inputs: BeamDesignInputSet,
) -> FlexuralDesignResults:
    return _calculate_negative_oriented_bending_design(
        materials,
        geometry,
        cantilever_negative_bending,
        design_inputs,
    )


def _calculate_negative_oriented_bending_design(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    negative_bending: NegativeBendingInput,
    design_inputs: BeamDesignInputSet,
) -> FlexuralDesignResults:
    engine_results = design_moment_beam(
        MomentBeamInput(
            design_code=_to_engine_design_code(design_inputs.metadata.design_code),
            materials=_to_engine_materials(materials),
            geometry=_to_engine_geometry(geometry),
            stirrup_diameter_mm=design_inputs.shear.stirrup_diameter_mm,
            factored_moment_kgm=negative_bending.factored_moment_kgm,
            positive_compression_reinforcement=_to_engine_reinforcement(design_inputs.positive_bending.compression_reinforcement),
            positive_tension_reinforcement=_to_engine_reinforcement(design_inputs.positive_bending.tension_reinforcement),
            negative_compression_reinforcement=_to_engine_reinforcement(negative_bending.compression_reinforcement),
            negative_tension_reinforcement=_to_engine_reinforcement(negative_bending.tension_reinforcement),
            material_settings=_to_engine_material_settings(design_inputs.material_settings),
            design_case=MomentDesignCase.NEGATIVE_LEGACY,
        )
    )
    material_results = calculate_material_properties(materials, design_inputs.material_settings)
    geometry_results = calculate_beam_geometry(
        geometry,
        design_inputs.positive_bending,
        negative_bending,
        design_inputs.shear,
        include_negative=True,
    )
    if geometry_results.d_minus_cm is None or geometry_results.negative_compression_centroid_from_bottom_cm is None:
        return _to_app_moment_results(engine_results)
    return _apply_beam_behavior_to_flexural_results(
        base_results=_to_app_moment_results(engine_results),
        design_inputs=design_inputs,
        material_results=material_results,
        geometry_results=geometry_results,
        tension_reinforcement=negative_bending.tension_reinforcement,
        compression_reinforcement=negative_bending.compression_reinforcement,
        factored_moment_kgm=negative_bending.factored_moment_kgm,
        effective_depth_cm=geometry_results.d_minus_cm,
        compression_depth_cm=geometry_results.negative_compression_centroid_from_bottom_cm,
        compression_face="bottom",
    )


def _resolve_deflection_member_configuration(
    design_inputs: BeamDesignInputSet,
) -> tuple[EngineDeflectionMemberType, EngineDeflectionSupportCondition]:
    if design_inputs.beam_type == BeamType.STANDALONE_CANTILEVER:
        return (
            EngineDeflectionMemberType.CANTILEVER_BEAM,
            EngineDeflectionSupportCondition.CANTILEVER_PLACEHOLDER,
        )
    if design_inputs.beam_type == BeamType.CONTINUOUS:
        if design_inputs.deflection.support_condition in {
            EngineDeflectionSupportCondition.CONTINUOUS_2_SPANS,
            EngineDeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS,
        }:
            return (EngineDeflectionMemberType.CONTINUOUS_BEAM, design_inputs.deflection.support_condition)
        return (
            EngineDeflectionMemberType.CONTINUOUS_BEAM,
            EngineDeflectionSupportCondition.CONTINUOUS_2_SPANS,
        )
    return (
        EngineDeflectionMemberType.SIMPLE_BEAM,
        EngineDeflectionSupportCondition.SIMPLE,
    )


def calculate_deflection_check(
    design_inputs: BeamDesignInputSet,
    material_results: MaterialResults,
    geometry_results: BeamGeometryResults,
) -> DeflectionCheckResults:
    resolved_member_type, resolved_support_condition = _resolve_deflection_member_configuration(design_inputs)
    beam_self_weight_dead_load_kgf_per_m = (
        (design_inputs.geometry.width_cm / 100.0) * (design_inputs.geometry.depth_cm / 100.0) * 2400.0
    )
    support_section = None
    if resolved_support_condition in {
        EngineDeflectionSupportCondition.CONTINUOUS_2_SPANS,
        EngineDeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS,
    }:
        if geometry_results.d_minus_cm is None or geometry_results.negative_compression_centroid_from_bottom_cm is None:
            raise ValueError("Continuous-beam deflection checks require negative-moment reinforcement geometry.")
        support_section = EngineDeflectionSectionReinforcementInput(
            tension_as_cm2=design_inputs.negative_bending.tension_reinforcement.total_area_cm2,
            compression_as_cm2=design_inputs.negative_bending.compression_reinforcement.total_area_cm2,
            effective_depth_cm=geometry_results.d_minus_cm,
            compression_depth_cm=geometry_results.negative_compression_centroid_from_bottom_cm,
        )

    engine_results = design_deflection_check(
        EngineDeflectionDesignInput(
            code_version=design_inputs.deflection.design_code,
            member_type=resolved_member_type,
            support_condition=resolved_support_condition,
            ie_method=design_inputs.deflection.ie_method,
            allowable_limit=design_inputs.deflection.allowable_limit,
            span_length_m=design_inputs.deflection.span_length_m,
            long_term_factor_x=design_inputs.deflection.long_term_factor_x,
            width_cm=design_inputs.geometry.width_cm,
            depth_cm=design_inputs.geometry.depth_cm,
            gross_moment_of_inertia_cm4=geometry_results.gross_moment_of_inertia_cm4,
            concrete_strength_ksc=design_inputs.materials.concrete_strength_ksc,
            ec_ksc=material_results.ec_ksc,
            fr_ksc=material_results.modulus_of_rupture_fr_ksc,
            modular_ratio_n=material_results.modular_ratio_n,
            service_loads=EngineDeflectionServiceLoadInput(
                dead_load_kgf_per_m=beam_self_weight_dead_load_kgf_per_m,
                live_load_kgf_per_m=design_inputs.deflection.service_live_load_kgf_per_m,
                additional_sustained_load_kgf_per_m=design_inputs.deflection.additional_sustained_load_kgf_per_m,
                sustained_live_load_ratio=design_inputs.deflection.sustained_live_load_ratio,
                support_dead_load_service_moment_kgm=design_inputs.deflection.support_dead_load_service_moment_kgm,
                support_live_load_service_moment_kgm=design_inputs.deflection.support_live_load_service_moment_kgm,
            ),
            midspan_section=EngineDeflectionSectionReinforcementInput(
                tension_as_cm2=design_inputs.positive_bending.tension_reinforcement.total_area_cm2,
                compression_as_cm2=design_inputs.positive_bending.compression_reinforcement.total_area_cm2,
                effective_depth_cm=geometry_results.d_plus_cm,
                compression_depth_cm=geometry_results.positive_compression_centroid_d_prime_cm,
            ),
            support_section=support_section,
        )
    )
    return _to_app_deflection_results(engine_results)


def _deflection_not_considered_result() -> DeflectionCheckResults:
    return DeflectionCheckResults(
        status="Not considered",
        note="Deflection was not included in this calculation run.",
        verification_status=VerificationStatus.VERIFIED_CODE,
    )


def validate_spacing_warnings(
    geometry: BeamGeometryInput,
    positive_bending: PositiveBendingInput,
    negative_bending: NegativeBendingInput,
    cantilever_negative_bending: NegativeBendingInput,
    shear: ShearDesignInput,
    simple_support_bending,
    *,
    include_positive: bool,
    include_simple_support: bool,
    include_negative: bool,
    include_cantilever_negative: bool,
) -> list[str]:
    warning_messages: list[str] = []
    spacing_groups: dict[str, ReinforcementSpacingResults] = {}
    if include_positive:
        spacing_groups.update(
            {
                "Positive compression": calculate_reinforcement_spacing(
                    geometry,
                    positive_bending.compression_reinforcement,
                    shear.stirrup_diameter_mm,
                ),
                "Positive tension": calculate_reinforcement_spacing(
                    geometry,
                    positive_bending.tension_reinforcement,
                    shear.stirrup_diameter_mm,
                ),
            }
        )
    if include_negative:
        spacing_groups.update(
            {
                "Negative compression": calculate_reinforcement_spacing(
                    geometry,
                    negative_bending.compression_reinforcement,
                    shear.stirrup_diameter_mm,
                ),
                "Negative tension": calculate_reinforcement_spacing(
                    geometry,
                    negative_bending.tension_reinforcement,
                    shear.stirrup_diameter_mm,
                ),
            }
        )
    if include_simple_support:
        spacing_groups.update(
            {
                "Support compression": calculate_reinforcement_spacing(
                    geometry,
                    simple_support_bending.compression_reinforcement,
                    shear.stirrup_diameter_mm,
                ),
                "Support tension": calculate_reinforcement_spacing(
                    geometry,
                    simple_support_bending.tension_reinforcement,
                    shear.stirrup_diameter_mm,
                ),
            }
        )
    if include_cantilever_negative:
        spacing_groups.update(
            {
                "Cantilever negative compression": calculate_reinforcement_spacing(
                    geometry,
                    cantilever_negative_bending.compression_reinforcement,
                    shear.stirrup_diameter_mm,
                ),
                "Cantilever negative tension": calculate_reinforcement_spacing(
                    geometry,
                    cantilever_negative_bending.tension_reinforcement,
                    shear.stirrup_diameter_mm,
                ),
            }
        )

    for label, spacing_results in spacing_groups.items():
        for layer in spacing_results.layers():
            if layer.status == "NOT OK":
                warning_messages.append(
                    f"{label} reinforcement, Layer {layer.layer_index}, does not satisfy the minimum clear spacing requirement."
                )
    return warning_messages


def validate_reinforcement_area_warnings(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    positive_bending: PositiveBendingInput,
    negative_bending: NegativeBendingInput,
    cantilever_negative_bending: NegativeBendingInput,
    design_inputs: BeamDesignInputSet,
    simple_support_bending,
    *,
    include_positive: bool,
    include_simple_support: bool,
    include_negative: bool,
    include_cantilever_negative: bool,
) -> list[str]:
    warning_messages: list[str] = []
    as_clause = _flexural_as_clause_reference(design_inputs.metadata.design_code)

    if include_positive:
        positive_results = calculate_positive_bending_design(materials, geometry, positive_bending, design_inputs)
        if positive_results.as_status != "OK":
            warning_messages.append(
                "Positive bending reinforcement does not satisfy the required reinforcement area limits. "
                f"{_format_aci_warning_reference(as_clause)}. This does not satisfy the A_s limit requirements."
            )

    if include_negative:
        negative_results = calculate_negative_bending_design(materials, geometry, negative_bending, design_inputs)
        if negative_results.as_status != "OK":
            warning_messages.append(
                "Negative bending reinforcement does not satisfy the required reinforcement area limits. "
                f"{_format_aci_warning_reference(as_clause)}. This does not satisfy the A_s limit requirements."
            )
    if include_simple_support:
        support_results = _calculate_positive_oriented_bending_design(
            materials,
            geometry,
            PositiveBendingInput(
                factored_moment_kgm=design_inputs.resolved_simple_support_moment_kgm,
                compression_reinforcement=simple_support_bending.compression_reinforcement,
                tension_reinforcement=simple_support_bending.tension_reinforcement,
            ),
            design_inputs,
        )
        if support_results.as_status != "OK":
            warning_messages.append(
                "Support bending reinforcement does not satisfy the required reinforcement area limits. "
                f"{_format_aci_warning_reference(as_clause)}. This does not satisfy the A_s limit requirements."
            )
    if include_cantilever_negative:
        cantilever_results = calculate_cantilever_negative_bending_design(
            materials,
            geometry,
            cantilever_negative_bending,
            design_inputs,
        )
        if cantilever_results.as_status != "OK":
            warning_messages.append(
                "Cantilever negative bending reinforcement does not satisfy the required reinforcement area limits. "
                f"{_format_aci_warning_reference(as_clause)}. This does not satisfy the A_s limit requirements."
            )
    return warning_messages


def validate_shear_warnings(
    design_inputs: BeamDesignInputSet,
    shear_results: ShearDesignResults,
) -> list[str]:
    warning_messages: list[str] = []
    shear_strength_clause = _shear_strength_clause_reference(design_inputs.metadata.design_code)
    shear_reinf_clause = _shear_reinforcement_clause_reference(design_inputs.metadata.design_code)
    if shear_results.section_change_required and shear_results.section_change_note:
        warning_messages.append(
            f"{shear_results.section_change_note.rstrip('.')} "
            f"{_format_aci_warning_reference(shear_reinf_clause)}. This exceeds the permitted shear reinforcement contribution."
        )
    if shear_results.phi_vn_kg < shear_results.input_factored_shear_kg and not shear_results.section_change_required:
        warning_messages.append(
            "Shear strength is insufficient because the applied shear force exceeds the design shear capacity, V_u > phi V_n. "
            f"{_format_aci_warning_reference(shear_strength_clause)}. This does not satisfy the beam shear strength requirements."
        )
    if shear_results.review_note:
        for note in shear_results.review_note.split(". "):
            if not note:
                continue
            warning_messages.append(_formalize_shear_note(note, design_inputs.metadata.design_code))
    return [message if message.endswith(".") else f"{message}." for message in warning_messages]


def validate_torsion_warnings(torsion_results: TorsionDesignResults) -> list[str]:
    return [_formalize_torsion_warning(message, torsion_results) for message in torsion_results.warnings]


def validate_combined_shear_torsion_warnings(combined_results: CombinedShearTorsionResults) -> list[str]:
    if not combined_results.active or combined_results.design_status == "PASS":
        return []
    if combined_results.design_status_note:
        return [combined_results.design_status_note]
    return ["Combined shear-and-torsion design does not satisfy the implemented shared closed-stirrup check."]


def validate_deflection_warnings(
    deflection_results: DeflectionCheckResults,
    *,
    consider_deflection: bool,
) -> list[str]:
    if not consider_deflection:
        return []
    warnings: list[str] = []
    if deflection_results.status == "FAIL":
        warnings.append(
            f"{deflection_results.pass_fail_summary} "
            f"{_format_aci_warning_reference(deflection_results.limit_clause)}. "
            "This does not satisfy the selected serviceability deflection limit."
        )
    elif deflection_results.mockup_only:
        warnings.append(deflection_results.note)
    for warning in deflection_results.warnings:
        if warning == deflection_results.pass_fail_summary:
            continue
        if "licensed code text" in warning:
            warnings.append(f"{warning.rstrip('.')} This should be confirmed by the design engineer.")
        elif "load-free" in warning or "live load is zero" in warning:
            warnings.append(f"{warning.rstrip('.')} This is an input-condition notice for the serviceability check.")
        elif warning == deflection_results.note:
            warnings.append(warning)
        else:
            warnings.append(
                f"{warning.rstrip('.')} {_format_aci_warning_reference(deflection_results.long_term_clause)}. "
                "This should be confirmed by the design engineer."
            )
    return warnings


def _compose_combined_shear_torsion_results(
    design_inputs: BeamDesignInputSet,
    geometry_results: BeamGeometryResults,
    shear_results: ShearDesignResults,
    torsion_results: TorsionDesignResults,
) -> CombinedShearTorsionResults:
    if not torsion_results.enabled:
        return CombinedShearTorsionResults(
            active=False,
            torsion_ignored=False,
            ignore_message="",
            vu_kg=shear_results.input_factored_shear_kg,
            tu_kgfm=design_inputs.torsion.factored_torsion_kgfm,
            shear_required_transverse_mm2_per_mm=0.0,
            torsion_required_transverse_mm2_per_mm=0.0,
            combined_required_transverse_mm2_per_mm=0.0,
            provided_transverse_mm2_per_mm=0.0,
            governing_case="Shear",
            capacity_ratio=0.0,
            design_status="PASS",
            stirrup_diameter_mm=design_inputs.shear.stirrup_diameter_mm,
            stirrup_legs=design_inputs.shear.legs_per_plane,
            stirrup_spacing_cm=shear_results.provided_spacing_cm,
            summary_note="",
            required_spacing_cm=shear_results.required_spacing_cm,
            spacing_limit_reason="Shear only",
            design_status_note="",
        )

    if torsion_results.can_neglect_torsion:
        ignore_message = (
            f"Tu = {design_inputs.torsion.factored_torsion_kgfm:.3f} kgf-m < "
            f"Tth = {torsion_results.threshold_torsion_kgfm:.3f} kgf-m, so torsion may be ignored."
        )
        return CombinedShearTorsionResults(
            active=False,
            torsion_ignored=True,
            ignore_message=ignore_message,
            vu_kg=shear_results.input_factored_shear_kg,
            tu_kgfm=design_inputs.torsion.factored_torsion_kgfm,
            shear_required_transverse_mm2_per_mm=0.0,
            torsion_required_transverse_mm2_per_mm=0.0,
            combined_required_transverse_mm2_per_mm=0.0,
            provided_transverse_mm2_per_mm=0.0,
            governing_case="Torsion ignored",
            capacity_ratio=0.0,
            design_status="PASS",
            stirrup_diameter_mm=design_inputs.shear.stirrup_diameter_mm,
            stirrup_legs=design_inputs.shear.legs_per_plane,
            stirrup_spacing_cm=shear_results.provided_spacing_cm,
            summary_note=ignore_message,
            required_spacing_cm=shear_results.required_spacing_cm,
            spacing_limit_reason="Torsion ignored",
            design_status_note="",
        )

    d_mm = shear_results.effective_depth_cm * 10.0
    # Convert the shear demand to the same shared-stirrup basis used elsewhere in this block: mm2/mm.
    # fy is entered in kgf/cm2, so the raw Av/s result is first obtained in cm2/mm and then converted to mm2/mm.
    shear_required_transverse_mm2_per_mm = _safe_divide(
        shear_results.nominal_vs_required_kg,
        design_inputs.materials.shear_steel_yield_ksc * d_mm,
    ) * 100.0
    # Shared-stirrup summary basis:
    # - shear demand is expressed as total vertical-leg area per spacing, Av/s
    # - torsion At/s is converted to the same shared closed-stirrup basis by multiplying by the number of vertical legs
    # - Capacity Ratio (Shear + Torsion) = combined required transverse reinforcement / provided transverse reinforcement
    torsion_required_transverse_mm2_per_mm = (
        torsion_results.transverse_reinf_required_mm2_per_mm * design_inputs.shear.legs_per_plane
    )
    combined_required_transverse_mm2_per_mm = (
        shear_required_transverse_mm2_per_mm + torsion_required_transverse_mm2_per_mm
    )
    required_spacing_cm, spacing_limit_reason = _combined_required_spacing_limit_cm(
        shear_results,
        torsion_results,
        combined_required_transverse_mm2_per_mm,
    )
    provided_transverse_mm2_per_mm = _safe_divide(
        shear_results.av_cm2 * 100.0,
        shear_results.provided_spacing_cm * 10.0,
    )
    capacity_ratio = _safe_divide(
        combined_required_transverse_mm2_per_mm,
        provided_transverse_mm2_per_mm,
    )
    (
        cross_section_limit_check_applied,
        shear_section_stress_mpa,
        torsion_section_stress_mpa,
        cross_section_limit_lhs_mpa,
        cross_section_limit_rhs_mpa,
        cross_section_limit_ratio,
        cross_section_limit_clause,
        cross_section_ok,
    ) = _evaluate_combined_shear_torsion_cross_section_limit(
        design_inputs,
        geometry_results,
        shear_results,
        torsion_results,
    )

    governing_values = {
        "Shear": shear_required_transverse_mm2_per_mm,
        "Torsion": torsion_required_transverse_mm2_per_mm,
        "Shear + Torsion": combined_required_transverse_mm2_per_mm,
    }
    governing_case = max(governing_values, key=governing_values.get)
    design_status = "PASS"
    design_status_note = ""
    if cross_section_limit_check_applied and not cross_section_ok:
        governing_case = "Combined section limit"
        design_status = "FAIL"
        design_status_note = (
            "Combined shear and torsion exceed the implemented solid-section stress limit. "
            f"{_format_aci_warning_reference(cross_section_limit_clause)}. "
            "This does not satisfy the combined section-strength check."
        )
    elif capacity_ratio > 1.0 + 1e-9:
        design_status = "FAIL"
        combined_clause = _combined_transverse_reinforcement_clause(
            design_inputs.metadata.design_code,
            torsion_results,
        )
        design_status_note = (
            "Shared closed stirrup reinforcement does not satisfy the combined shear-and-torsion transverse reinforcement demand. "
            f"{_format_aci_warning_reference(combined_clause)}. "
            "This does not satisfy the implemented combined transverse reinforcement demand."
        )
    summary_note = (
        "Capacity Ratio (Shear + Torsion) = "
        "(shear-only required transverse reinforcement + torsion-only required transverse reinforcement) / "
        "provided transverse reinforcement of the shared closed stirrup."
    )
    if cross_section_limit_check_applied:
        summary_note += (
            " Solid rectangular sections are also checked using the combined shear-torsion section-stress limit "
            f"from {cross_section_limit_clause}."
        )
    return CombinedShearTorsionResults(
        active=True,
        torsion_ignored=False,
        ignore_message="",
        vu_kg=shear_results.input_factored_shear_kg,
        tu_kgfm=design_inputs.torsion.factored_torsion_kgfm,
        shear_required_transverse_mm2_per_mm=shear_required_transverse_mm2_per_mm,
        torsion_required_transverse_mm2_per_mm=torsion_required_transverse_mm2_per_mm,
        combined_required_transverse_mm2_per_mm=combined_required_transverse_mm2_per_mm,
        provided_transverse_mm2_per_mm=provided_transverse_mm2_per_mm,
        governing_case=governing_case,
        capacity_ratio=capacity_ratio,
        design_status=design_status,
        stirrup_diameter_mm=design_inputs.shear.stirrup_diameter_mm,
        stirrup_legs=design_inputs.shear.legs_per_plane,
        stirrup_spacing_cm=shear_results.provided_spacing_cm,
        summary_note=summary_note,
        required_spacing_cm=required_spacing_cm,
        spacing_limit_reason=spacing_limit_reason,
        cross_section_limit_check_applied=cross_section_limit_check_applied,
        cross_section_limit_lhs_mpa=cross_section_limit_lhs_mpa,
        cross_section_limit_rhs_mpa=cross_section_limit_rhs_mpa,
        cross_section_limit_ratio=cross_section_limit_ratio,
        cross_section_limit_clause=cross_section_limit_clause,
        shear_section_stress_mpa=shear_section_stress_mpa,
        torsion_section_stress_mpa=torsion_section_stress_mpa,
        design_status_note=design_status_note,
    )


def calculate_full_design_results(design_inputs: BeamDesignInputSet) -> BeamDesignResults:
    include_negative = design_inputs.has_support_negative_design
    include_simple_support = design_inputs.has_simple_support_design
    include_simple_support_checks = include_simple_support and design_inputs.resolved_simple_support_moment_kgm > 1e-9
    include_cantilever_negative = design_inputs.has_cantilever_negative_design
    material_results = calculate_material_properties(design_inputs.materials, design_inputs.material_settings)
    geometry_positive_bending, geometry_negative_bending, include_negative_geometry = _resolve_primary_geometry_inputs(design_inputs)
    geometry_results = calculate_beam_geometry(
        design_inputs.geometry,
        geometry_positive_bending,
        geometry_negative_bending,
        design_inputs.shear,
        include_negative=include_negative_geometry,
    )
    positive_results = calculate_positive_bending_design(
        design_inputs.materials,
        design_inputs.geometry,
        design_inputs.positive_bending,
        design_inputs,
    )
    support_results = None
    if include_simple_support:
        support_results = _calculate_positive_oriented_bending_design(
            design_inputs.materials,
            design_inputs.geometry,
            _resolved_simple_support_bending_input(design_inputs),
            design_inputs,
        )
    shear_results, shear_region_results = calculate_shear_design_regions(
        design_inputs.materials,
        design_inputs.geometry,
        design_inputs.shear,
        design_inputs,
    )
    torsion_results = design_torsion_beam(
        TorsionBeamInput(
            design=design_inputs.torsion,
            geometry=TorsionSectionGeometryInput(
                width_cm=design_inputs.geometry.width_cm,
                depth_cm=design_inputs.geometry.depth_cm,
                cover_cm=design_inputs.geometry.cover_cm,
                stirrup_diameter_mm=design_inputs.shear.stirrup_diameter_mm,
                stirrup_spacing_cm=shear_results.provided_spacing_cm,
                stirrup_legs=design_inputs.shear.legs_per_plane,
            ),
            materials=TorsionDesignMaterialInput(
                concrete_strength_ksc=design_inputs.materials.concrete_strength_ksc,
                transverse_steel_yield_ksc=design_inputs.materials.shear_steel_yield_ksc,
                longitudinal_steel_yield_ksc=design_inputs.torsion.provided_longitudinal_bar_fy_ksc,
            ),
        )
    )
    if design_inputs.torsion.enabled and not torsion_results.can_neglect_torsion:
        resolved_shared_spacing_cm = _resolve_shared_stirrup_spacing_cm(
            design_inputs,
            geometry_results,
            shear_results,
            torsion_results,
        )
        if abs(resolved_shared_spacing_cm - shear_results.provided_spacing_cm) > 1e-9:
            adjusted_shear = replace(
                design_inputs.shear,
                spacing_mode=ShearSpacingMode.MANUAL,
                provided_spacing_cm=resolved_shared_spacing_cm,
            )
            shear_results, shear_region_results = calculate_shear_design_regions(
                design_inputs.materials,
                design_inputs.geometry,
                adjusted_shear,
                design_inputs,
            )
            torsion_results = design_torsion_beam(
                TorsionBeamInput(
                    design=design_inputs.torsion,
                    geometry=TorsionSectionGeometryInput(
                        width_cm=design_inputs.geometry.width_cm,
                        depth_cm=design_inputs.geometry.depth_cm,
                        cover_cm=design_inputs.geometry.cover_cm,
                        stirrup_diameter_mm=design_inputs.shear.stirrup_diameter_mm,
                        stirrup_spacing_cm=shear_results.provided_spacing_cm,
                        stirrup_legs=design_inputs.shear.legs_per_plane,
                    ),
                    materials=TorsionDesignMaterialInput(
                        concrete_strength_ksc=design_inputs.materials.concrete_strength_ksc,
                        transverse_steel_yield_ksc=design_inputs.materials.shear_steel_yield_ksc,
                        longitudinal_steel_yield_ksc=design_inputs.torsion.provided_longitudinal_bar_fy_ksc,
                    ),
                )
            )
    combined_shear_torsion_results = _compose_combined_shear_torsion_results(
        design_inputs,
        geometry_results,
        shear_results,
        torsion_results,
    )
    negative_results = None
    if include_negative:
        negative_results = calculate_negative_bending_design(
            design_inputs.materials,
            design_inputs.geometry,
            design_inputs.negative_bending,
            design_inputs,
        )
    cantilever_negative_results = None
    if include_cantilever_negative:
        cantilever_negative_results = calculate_cantilever_negative_bending_design(
            design_inputs.materials,
            design_inputs.geometry,
            design_inputs.cantilever_negative_bending,
            design_inputs,
        )
    deflection_results = (
        calculate_deflection_check(
            design_inputs,
            material_results,
            geometry_results,
        )
        if design_inputs.consider_deflection
        else _deflection_not_considered_result()
    )
    warnings = [
        *validate_spacing_warnings(
            design_inputs.geometry,
            design_inputs.positive_bending,
            design_inputs.negative_bending,
            design_inputs.cantilever_negative_bending,
            design_inputs.shear,
            simple_support_bending=design_inputs.simple_support_bending,
            include_positive=design_inputs.has_positive_design,
            include_simple_support=include_simple_support_checks,
            include_negative=include_negative,
            include_cantilever_negative=include_cantilever_negative,
        ),
        *validate_reinforcement_area_warnings(
            design_inputs.materials,
            design_inputs.geometry,
            design_inputs.positive_bending,
            design_inputs.negative_bending,
            design_inputs.cantilever_negative_bending,
            design_inputs,
            simple_support_bending=design_inputs.simple_support_bending,
            include_positive=design_inputs.has_positive_design,
            include_simple_support=include_simple_support_checks,
            include_negative=include_negative,
            include_cantilever_negative=include_cantilever_negative,
        ),
        *validate_shear_warnings(design_inputs, shear_results),
        *validate_torsion_warnings(torsion_results),
        *validate_combined_shear_torsion_warnings(combined_shear_torsion_results),
        *validate_deflection_warnings(deflection_results, consider_deflection=design_inputs.consider_deflection),
    ]
    warnings = [_formalize_general_warning(message, design_inputs.metadata.design_code) for message in warnings]
    review_flags = _build_review_flags(negative_results, deflection_results, consider_deflection=design_inputs.consider_deflection)
    overall_status, overall_note = _calculate_overall_assessment(
        design_inputs,
        geometry_results,
        positive_results,
        support_results if include_simple_support_checks else None,
        shear_results,
        torsion_results,
        combined_shear_torsion_results,
        negative_results,
        cantilever_negative_results,
        deflection_results,
        review_flags,
    )
    return BeamDesignResults(
        materials=material_results,
        beam_geometry=geometry_results,
        positive_bending=positive_results,
        support_bending=support_results,
        shear=shear_results,
        shear_regions=shear_region_results,
        torsion=torsion_results,
        combined_shear_torsion=combined_shear_torsion_results,
        negative_bending=negative_results,
        cantilever_negative_bending=cantilever_negative_results,
        deflection=deflection_results,
        warnings=warnings,
        review_flags=review_flags,
        overall_status=overall_status,
        overall_note=overall_note,
    )


def _to_engine_design_code(code: DesignCode) -> EngineDesignCode:
    return EngineDesignCode[code.name]


def _to_engine_materials(materials: MaterialPropertiesInput) -> EngineMaterialPropertiesInput:
    return EngineMaterialPropertiesInput(
        concrete_strength_ksc=materials.concrete_strength_ksc,
        main_steel_yield_ksc=materials.main_steel_yield_ksc,
        shear_steel_yield_ksc=materials.shear_steel_yield_ksc,
    )


def _to_engine_material_settings(settings: MaterialPropertySettings) -> EngineMaterialPropertySettings:
    return EngineMaterialPropertySettings(
        ec=EngineMaterialPropertySetting(
            mode=EngineMaterialPropertyMode[settings.ec.mode.name],
            manual_value=settings.ec.manual_value,
        ),
        es=EngineMaterialPropertySetting(
            mode=EngineMaterialPropertyMode[settings.es.mode.name],
            manual_value=settings.es.manual_value,
        ),
        fr=EngineMaterialPropertySetting(
            mode=EngineMaterialPropertyMode[settings.fr.mode.name],
            manual_value=settings.fr.manual_value,
        ),
    )


def _to_engine_geometry(geometry: BeamGeometryInput) -> EngineBeamSectionInput:
    return EngineBeamSectionInput(
        width_cm=geometry.width_cm,
        depth_cm=geometry.depth_cm,
        cover_cm=geometry.cover_cm,
        minimum_clear_spacing_cm=geometry.minimum_clear_spacing_cm,
    )


def _to_engine_reinforcement(reinforcement: ReinforcementArrangementInput) -> EngineReinforcementArrangementInput:
    return EngineReinforcementArrangementInput(
        layer_1=_to_engine_layer(reinforcement.layer_1),
        layer_2=_to_engine_layer(reinforcement.layer_2),
        layer_3=_to_engine_layer(reinforcement.layer_3),
    )


def _to_engine_layer(layer: RebarLayerInput) -> EngineRebarLayerInput:
    return EngineRebarLayerInput(
        group_a=_to_engine_group(layer.group_a),
        group_b=_to_engine_group(layer.group_b),
    )


def _to_engine_group(group: RebarGroupInput) -> EngineRebarGroupInput:
    return EngineRebarGroupInput(diameter_mm=group.diameter_mm, count=group.count)


def _to_engine_shear_spacing_mode(mode: ShearSpacingMode) -> EngineShearSpacingMode:
    return EngineShearSpacingMode[mode.name]


def _to_app_material_results(engine_results) -> MaterialResults:
    return MaterialResults(
        fc_prime_ksc=engine_results.fc_prime_ksc,
        fy_ksc=engine_results.fy_ksc,
        fvy_ksc=engine_results.fvy_ksc,
        ec_ksc=engine_results.ec_ksc,
        es_ksc=engine_results.es_ksc,
        modular_ratio_n=engine_results.modular_ratio_n,
        modulus_of_rupture_fr_ksc=engine_results.modulus_of_rupture_fr_ksc,
        beta_1=engine_results.beta_1,
        ec_mode=MaterialPropertyMode[engine_results.ec_mode.name],
        es_mode=MaterialPropertyMode[engine_results.es_mode.name],
        fr_mode=MaterialPropertyMode[engine_results.fr_mode.name],
        ec_default_ksc=engine_results.ec_default_ksc,
        es_default_ksc=engine_results.es_default_ksc,
        fr_default_ksc=engine_results.fr_default_ksc,
        ec_default_logic=engine_results.ec_default_logic,
        es_default_logic=engine_results.es_default_logic,
        fr_default_logic=engine_results.fr_default_logic,
    )


def _to_app_spacing_results(engine_results) -> ReinforcementSpacingResults:
    return ReinforcementSpacingResults(
        layer_1=_to_app_layer_spacing_result(engine_results.layer_1),
        layer_2=_to_app_layer_spacing_result(engine_results.layer_2),
        layer_3=_to_app_layer_spacing_result(engine_results.layer_3),
        overall_status=engine_results.overall_status,
    )


def _to_app_layer_spacing_result(engine_result) -> LayerSpacingResult:
    return LayerSpacingResult(
        layer_index=engine_result.layer_index,
        group_a_diameter_mm=engine_result.group_a_diameter_mm,
        group_a_count=engine_result.group_a_count,
        group_b_diameter_mm=engine_result.group_b_diameter_mm,
        group_b_count=engine_result.group_b_count,
        spacing_cm=engine_result.spacing_cm,
        required_spacing_cm=engine_result.required_spacing_cm,
        status=engine_result.status,
        message=engine_result.message,
    )


def _to_app_beam_geometry_results(engine_results) -> BeamGeometryResults:
    return BeamGeometryResults(
        section_area_cm2=engine_results.section_area_cm2,
        gross_moment_of_inertia_cm4=engine_results.gross_moment_of_inertia_cm4,
        cover_plus_stirrup_cm=engine_results.cover_plus_stirrup_cm,
        positive_compression_centroid_d_prime_cm=engine_results.positive_compression_centroid_d_prime_cm,
        positive_tension_centroid_from_bottom_d_cm=engine_results.positive_tension_centroid_from_bottom_d_cm,
        negative_compression_centroid_from_bottom_cm=engine_results.negative_compression_centroid_from_bottom_cm,
        negative_tension_centroid_from_top_cm=engine_results.negative_tension_centroid_from_top_cm,
        d_plus_cm=engine_results.d_plus_cm,
        d_minus_cm=engine_results.d_minus_cm,
        positive_compression_spacing=_to_app_spacing_results(engine_results.positive_compression_spacing),
        positive_tension_spacing=_to_app_spacing_results(engine_results.positive_tension_spacing),
        negative_compression_spacing=(
            _to_app_spacing_results(engine_results.negative_compression_spacing)
            if engine_results.negative_compression_spacing is not None
            else None
        ),
        negative_tension_spacing=(
            _to_app_spacing_results(engine_results.negative_tension_spacing)
            if engine_results.negative_tension_spacing is not None
            else None
        ),
    )


def _to_app_moment_results(engine_results) -> FlexuralDesignResults:
    return FlexuralDesignResults(
        phi=engine_results.phi,
        ru_kg_per_cm2=engine_results.ru_kg_per_cm2,
        rho_required=engine_results.rho_required,
        as_required_cm2=engine_results.as_required_cm2,
        as_provided_cm2=engine_results.as_provided_cm2,
        rho_provided=engine_results.rho_provided,
        rho_min=engine_results.rho_min,
        rho_max=engine_results.rho_max,
        as_min_cm2=engine_results.as_min_cm2,
        as_max_cm2=engine_results.as_max_cm2,
        as_status=engine_results.as_status,
        a_cm=engine_results.a_cm,
        c_cm=engine_results.c_cm,
        dt_cm=engine_results.dt_cm,
        ety=engine_results.ety,
        et=engine_results.et,
        mn_kgm=engine_results.mn_kgm,
        phi_mn_kgm=engine_results.phi_mn_kgm,
        ratio=engine_results.ratio,
        ratio_status=engine_results.ratio_status,
        design_status=engine_results.design_status,
        review_note=engine_results.review_note,
    )


def _apply_beam_behavior_to_flexural_results(
    *,
    base_results: FlexuralDesignResults,
    design_inputs: BeamDesignInputSet,
    material_results: MaterialResults,
    geometry_results: BeamGeometryResults,
    tension_reinforcement: ReinforcementArrangementInput,
    compression_reinforcement: ReinforcementArrangementInput,
    factored_moment_kgm: float,
    effective_depth_cm: float,
    compression_depth_cm: float,
    compression_face: str,
) -> FlexuralDesignResults:
    full_results = _calculate_full_section_flexural_results(
        design_inputs=design_inputs,
        material_results=material_results,
        tension_reinforcement=tension_reinforcement,
        compression_reinforcement=compression_reinforcement,
        factored_moment_kgm=factored_moment_kgm,
        effective_depth_cm=effective_depth_cm,
        compression_depth_cm=compression_depth_cm,
        compression_face=compression_face,
        dt_cm=base_results.dt_cm,
        ety=base_results.ety,
        as_status=base_results.as_status,
    )
    mn_single_kgm = base_results.mn_kgm
    mn_full_kgm = full_results["mn_kgm"] if full_results is not None else mn_single_kgm
    contribution_ratio_r = _beam_behavior_contribution_ratio(mn_single_kgm, mn_full_kgm)
    threshold_r = max(0.0, min(1.0, design_inputs.auto_beam_behavior_threshold_ratio))
    auto_result = BeamBehaviorMode.SINGLY.value
    if contribution_ratio_r > threshold_r:
        auto_result = BeamBehaviorMode.DOUBLY.value

    selected_mode = design_inputs.beam_behavior_mode
    effective_mode = {
        BeamBehaviorMode.SINGLY: BeamBehaviorMode.SINGLY.value,
        BeamBehaviorMode.AUTO: auto_result,
        BeamBehaviorMode.DOUBLY: BeamBehaviorMode.DOUBLY.value,
    }[selected_mode]
    use_full_results = effective_mode == BeamBehaviorMode.DOUBLY.value and full_results is not None

    if not use_full_results:
        return replace(
            base_results,
            beam_behavior_mode=selected_mode.value,
            effective_beam_behavior=effective_mode,
            auto_result=auto_result if selected_mode == BeamBehaviorMode.AUTO else "",
            behavior_contribution_ratio_r=contribution_ratio_r,
            behavior_threshold_r=threshold_r,
            mn_single_kgm=mn_single_kgm,
            mn_full_kgm=mn_full_kgm,
        )

    return replace(
        base_results,
        phi=full_results["phi"],
        a_cm=full_results["a_cm"],
        c_cm=full_results["c_cm"],
        et=full_results["et"],
        mn_kgm=full_results["mn_kgm"],
        phi_mn_kgm=full_results["phi_mn_kgm"],
        ratio=full_results["ratio"],
        ratio_status=full_results["ratio_status"],
        design_status=full_results["design_status"],
        beam_behavior_mode=selected_mode.value,
        effective_beam_behavior=effective_mode,
        auto_result=auto_result if selected_mode == BeamBehaviorMode.AUTO else "",
        behavior_contribution_ratio_r=contribution_ratio_r,
        behavior_threshold_r=threshold_r,
        mn_single_kgm=mn_single_kgm,
        mn_full_kgm=mn_full_kgm,
    )


def _calculate_full_section_flexural_results(
    *,
    design_inputs: BeamDesignInputSet,
    material_results: MaterialResults,
    tension_reinforcement: ReinforcementArrangementInput,
    compression_reinforcement: ReinforcementArrangementInput,
    factored_moment_kgm: float,
    effective_depth_cm: float,
    compression_depth_cm: float,
    compression_face: str,
    dt_cm: float,
    ety: float,
    as_status: str,
) -> dict[str, float | str] | None:
    tension_bars = _reinforcement_bar_depths_from_compression_face(
        tension_reinforcement,
        design_inputs.geometry,
        design_inputs.shear.stirrup_diameter_mm,
        compression_face=compression_face,
        arrangement_face="bottom" if compression_face == "top" else "top",
    )
    compression_bars = _reinforcement_bar_depths_from_compression_face(
        compression_reinforcement,
        design_inputs.geometry,
        design_inputs.shear.stirrup_diameter_mm,
        compression_face=compression_face,
        arrangement_face=compression_face,
    )
    if not tension_bars or not compression_bars:
        return None

    width_cm = design_inputs.geometry.width_cm
    concrete_strength_ksc = design_inputs.materials.concrete_strength_ksc
    steel_yield_ksc = design_inputs.materials.main_steel_yield_ksc
    beta_1 = material_results.beta_1

    def steel_stress_ksc(strain: float) -> float:
        if not math.isfinite(strain) or abs(strain) <= 1e-12:
            return 0.0
        elastic_stress_ksc = material_results.es_ksc * abs(strain)
        return math.copysign(min(steel_yield_ksc, elastic_stress_ksc), strain)

    def equilibrium(c_cm: float) -> float:
        a_cm = beta_1 * c_cm
        concrete_compression_kg = 0.85 * concrete_strength_ksc * width_cm * a_cm
        steel_force_kg = 0.0
        for bar_area_cm2, bar_depth_cm in [*compression_bars, *tension_bars]:
            steel_strain = _safe_divide(ECU * (c_cm - bar_depth_cm), c_cm)
            steel_force_kg += bar_area_cm2 * steel_stress_ksc(steel_strain)
        return concrete_compression_kg + steel_force_kg

    lower_c_cm = 1e-6
    upper_c_cm = max(design_inputs.geometry.depth_cm * 2.0, effective_depth_cm * 2.0, 1.0)
    while equilibrium(upper_c_cm) < 0.0 and upper_c_cm < design_inputs.geometry.depth_cm * 128.0:
        upper_c_cm *= 2.0
    if equilibrium(upper_c_cm) < 0.0:
        return None

    # Solve steel-concrete force equilibrium without changing the existing beam engine.
    for _ in range(80):
        middle_c_cm = (lower_c_cm + upper_c_cm) / 2.0
        if equilibrium(middle_c_cm) >= 0.0:
            upper_c_cm = middle_c_cm
        else:
            lower_c_cm = middle_c_cm

    c_cm = upper_c_cm
    a_cm = beta_1 * c_cm
    concrete_compression_kg = 0.85 * concrete_strength_ksc * width_cm * a_cm
    steel_moment_kgcm = 0.0
    for bar_area_cm2, bar_depth_cm in [*compression_bars, *tension_bars]:
        steel_strain = _safe_divide(ECU * (c_cm - bar_depth_cm), c_cm)
        steel_force_kg = bar_area_cm2 * steel_stress_ksc(steel_strain)
        steel_moment_kgcm += steel_force_kg * bar_depth_cm
    mn_kgm = abs((concrete_compression_kg * (a_cm / 2.0) + steel_moment_kgcm) / 100.0)
    if not math.isfinite(mn_kgm) or mn_kgm <= 0.0:
        return None

    dt_cm = max(depth_cm for _, depth_cm in tension_bars)
    et = _safe_divide(ECU * (dt_cm - c_cm), c_cm)
    phi = _calculate_flexural_phi(design_inputs.metadata.design_code, et, ety)
    phi_mn_kgm = mn_kgm * phi
    ratio = _safe_divide(factored_moment_kgm, phi_mn_kgm)
    ratio_status = "OK" if phi_mn_kgm >= factored_moment_kgm else "NOT OK"
    design_status = "PASS" if as_status == "OK" and ratio_status == "OK" else "FAIL"
    return {
        "phi": phi,
        "a_cm": a_cm,
        "c_cm": c_cm,
        "et": et,
        "mn_kgm": mn_kgm,
        "phi_mn_kgm": phi_mn_kgm,
        "ratio": ratio,
        "ratio_status": ratio_status,
        "design_status": design_status,
    }


def _beam_behavior_contribution_ratio(mn_single_kgm: float, mn_full_kgm: float) -> float:
    if not math.isfinite(mn_full_kgm) or mn_full_kgm <= 0.0:
        return 0.0
    if not math.isfinite(mn_single_kgm):
        return 1.0
    return max(0.0, min(1.0, _safe_divide(mn_full_kgm - mn_single_kgm, mn_full_kgm)))


def _reinforcement_bar_depths_from_compression_face(
    reinforcement: ReinforcementArrangementInput,
    geometry: BeamGeometryInput,
    stirrup_diameter_mm: int,
    *,
    compression_face: str,
    arrangement_face: str,
) -> list[tuple[float, float]]:
    bars: list[tuple[float, float]] = []
    for layer_index, layer in enumerate(reinforcement.layers()):
        base_distance_cm = _layer_base_distance_cm(geometry, reinforcement, stirrup_diameter_mm, layer_index)
        for group in layer.groups():
            if group.count == 0 or group.diameter_mm is None:
                continue
            centroid_from_arrangement_face_cm = base_distance_cm + (_group_diameter_cm(group) / 2.0)
            if arrangement_face == compression_face:
                depth_from_compression_face_cm = centroid_from_arrangement_face_cm
            else:
                depth_from_compression_face_cm = geometry.depth_cm - centroid_from_arrangement_face_cm
            single_bar_area_cm2 = _safe_divide(group.area_cm2, group.count)
            for _ in range(group.count):
                bars.append((single_bar_area_cm2, depth_from_compression_face_cm))
    return bars


def _to_app_shear_results(engine_results) -> ShearDesignResults:
    return ShearDesignResults(
        phi=engine_results.phi,
        vc_kg=engine_results.vc_kg,
        phi_vc_kg=engine_results.phi_vc_kg,
        vc_max_kg=engine_results.vc_max_kg,
        vc_capped_by_max=engine_results.vc_capped_by_max,
        vs_max_kg=engine_results.vs_max_kg,
        phi_vs_max_kg=engine_results.phi_vs_max_kg,
        phi_vs_required_kg=engine_results.phi_vs_required_kg,
        nominal_vs_required_kg=engine_results.nominal_vs_required_kg,
        av_cm2=engine_results.av_cm2,
        av_min_cm2=engine_results.av_min_cm2,
        minimum_reinforcement_trigger_kg=engine_results.minimum_reinforcement_trigger_kg,
        minimum_reinforcement_required=engine_results.minimum_reinforcement_required,
        size_effect_factor=engine_results.size_effect_factor,
        size_effect_applied=engine_results.size_effect_applied,
        s_max_from_av_cm=engine_results.s_max_from_av_cm,
        s_max_from_vs_cm=engine_results.s_max_from_vs_cm,
        required_spacing_cm=engine_results.required_spacing_cm,
        provided_spacing_cm=engine_results.provided_spacing_cm,
        spacing_mode=ShearSpacingMode[engine_results.spacing_mode.name],
        vs_provided_kg=engine_results.vs_provided_kg,
        phi_vs_provided_kg=engine_results.phi_vs_provided_kg,
        vn_kg=engine_results.vn_kg,
        phi_vn_kg=engine_results.phi_vn_kg,
        stirrup_spacing_cm=engine_results.stirrup_spacing_cm,
        capacity_ratio=engine_results.capacity_ratio,
        design_status=engine_results.design_status,
        section_change_required=engine_results.section_change_required,
        section_change_note=engine_results.section_change_note,
        review_note=engine_results.review_note,
    )


def _to_app_deflection_results(engine_results) -> DeflectionCheckResults:
    verification_status = (
        VerificationStatus.NEEDS_REVIEW
        if getattr(engine_results, "verification_status", "").value == "Needs manual engineering review"
        else VerificationStatus.VERIFIED_CODE
    )
    return DeflectionCheckResults(
        status=engine_results.status,
        note=engine_results.note,
        verification_status=verification_status,
        code_version=engine_results.code_version,
        member_type=engine_results.member_type,
        support_condition=engine_results.support_condition,
        ie_method_selected=engine_results.ie_method_selected,
        ie_method_governing=engine_results.ie_method_governing,
        allowable_limit_label=engine_results.allowable_limit_label,
        allowable_limit_denominator=engine_results.allowable_limit_denominator,
        allowable_deflection_cm=engine_results.allowable_deflection_cm,
        span_length_m=engine_results.span_length_m,
        load_basis_note=engine_results.load_basis_note,
        pass_fail_summary=engine_results.pass_fail_summary,
        mockup_only=engine_results.mockup_only,
        immediate_clause=engine_results.immediate_clause,
        long_term_clause=engine_results.long_term_clause,
        limit_clause=engine_results.limit_clause,
        service_dead_load_kgf_per_m=engine_results.service_dead_load_kgf_per_m,
        service_live_load_kgf_per_m=engine_results.service_live_load_kgf_per_m,
        additional_sustained_load_kgf_per_m=engine_results.additional_sustained_load_kgf_per_m,
        sustained_live_load_ratio=engine_results.sustained_live_load_ratio,
        service_sustained_load_kgf_per_m=engine_results.service_sustained_load_kgf_per_m,
        midspan_dead_load_service_moment_kgm=engine_results.midspan_dead_load_service_moment_kgm,
        midspan_live_load_service_moment_kgm=engine_results.midspan_live_load_service_moment_kgm,
        support_dead_load_service_moment_kgm=engine_results.support_dead_load_service_moment_kgm,
        support_live_load_service_moment_kgm=engine_results.support_live_load_service_moment_kgm,
        gross_moment_of_inertia_cm4=engine_results.gross_moment_of_inertia_cm4,
        midspan_cracking_moment_kgm=engine_results.midspan_cracking_moment_kgm,
        support_cracking_moment_kgm=engine_results.support_cracking_moment_kgm,
        midspan_cracked_neutral_axis_cm=engine_results.midspan_cracked_neutral_axis_cm,
        support_cracked_neutral_axis_cm=engine_results.support_cracked_neutral_axis_cm,
        midspan_cracked_inertia_cm4=engine_results.midspan_cracked_inertia_cm4,
        support_cracked_inertia_cm4=engine_results.support_cracked_inertia_cm4,
        ie_midspan_total_cm4=engine_results.ie_midspan_total_cm4,
        ie_support_total_cm4=engine_results.ie_support_total_cm4,
        ie_average_total_cm4=engine_results.ie_average_total_cm4,
        ie_dead_cm4=engine_results.ie_dead_cm4,
        ie_total_cm4=engine_results.ie_total_cm4,
        ie_sustained_cm4=engine_results.ie_sustained_cm4,
        method_1_total_service_deflection_cm=engine_results.method_1_total_service_deflection_cm,
        method_2_total_service_deflection_cm=engine_results.method_2_total_service_deflection_cm,
        immediate_dead_deflection_cm=engine_results.immediate_dead_deflection_cm,
        immediate_total_deflection_cm=engine_results.immediate_total_deflection_cm,
        immediate_live_deflection_cm=engine_results.immediate_live_deflection_cm,
        sustained_initial_deflection_cm=engine_results.sustained_initial_deflection_cm,
        long_term_multiplier=engine_results.long_term_multiplier,
        additional_long_term_deflection_cm=engine_results.additional_long_term_deflection_cm,
        total_service_deflection_cm=engine_results.total_service_deflection_cm,
        calculated_deflection_cm=engine_results.calculated_deflection_cm,
        capacity_ratio=engine_results.capacity_ratio,
        governing_result=engine_results.governing_result,
        warnings=engine_results.warnings,
        steps=engine_results.steps,
    )


def _build_review_flags(
    negative_results: FlexuralDesignResults | None,
    deflection_results: DeflectionCheckResults,
    *,
    consider_deflection: bool,
) -> list[ReviewFlag]:
    review_flags: list[ReviewFlag] = []
    if not consider_deflection or deflection_results.verification_status != VerificationStatus.NEEDS_REVIEW:
        return review_flags
    review_flags.append(
        ReviewFlag(
            title="Deflection module",
            severity="warning",
            message=deflection_results.note,
            verification_status=VerificationStatus.NEEDS_REVIEW,
        )
    )
    return review_flags


def _calculate_overall_assessment(
    design_inputs: BeamDesignInputSet,
    geometry_results: BeamGeometryResults,
    positive_results: FlexuralDesignResults,
    support_results: FlexuralDesignResults | None,
    shear_results: ShearDesignResults,
    torsion_results: TorsionDesignResults,
    combined_shear_torsion_results: CombinedShearTorsionResults,
    negative_results: FlexuralDesignResults | None,
    cantilever_negative_results: FlexuralDesignResults | None,
    deflection_results: DeflectionCheckResults,
    review_flags: list[ReviewFlag],
) -> tuple[str, str]:
    strength_failures: list[str] = []
    if design_inputs.has_positive_design and positive_results.ratio_status != "OK":
        strength_failures.append("Positive flexural strength does not satisfy M_u <= phi M_n.")
    if support_results is not None and support_results.ratio_status != "OK":
        strength_failures.append("Support flexural strength does not satisfy M_u <= phi M_n.")
    if negative_results is not None and negative_results.ratio_status != "OK":
        strength_failures.append("Negative flexural strength does not satisfy M_u <= phi M_n.")
    if cantilever_negative_results is not None and cantilever_negative_results.ratio_status != "OK":
        strength_failures.append("Cantilever negative flexural strength does not satisfy M_u <= phi M_n.")
    if shear_results.phi_vn_kg < shear_results.input_factored_shear_kg:
        if shear_results.section_change_required and shear_results.section_change_note:
            strength_failures.append(shear_results.section_change_note)
        else:
            strength_failures.append("Shear strength does not satisfy V_u <= phi V_n.")
    if shear_results.nominal_vs_required_kg > shear_results.vs_max_kg:
        strength_failures.append("Required shear reinforcement exceeds the permitted shear steel contribution.")
    if combined_shear_torsion_results.active and combined_shear_torsion_results.design_status == "FAIL":
        strength_failures.append(
            combined_shear_torsion_results.design_status_note
            or "Shared closed stirrup reinforcement does not satisfy the combined shear-and-torsion transverse reinforcement demand."
        )
    elif torsion_results.enabled and not torsion_results.can_neglect_torsion and torsion_results.status == "FAIL":
        strength_failures.append(torsion_results.pass_fail_summary)
    if strength_failures:
        return "FAIL", " ".join(strength_failures)

    requirement_issues: list[str] = []
    if design_inputs.has_positive_design and positive_results.as_status != "OK":
        requirement_issues.append("Positive tension reinforcement does not satisfy the required A_s limits.")
    if support_results is not None and support_results.as_status != "OK":
        requirement_issues.append("Support tension reinforcement does not satisfy the required A_s limits.")
    if negative_results is not None and negative_results.as_status != "OK":
        requirement_issues.append("Negative tension reinforcement does not satisfy the required A_s limits.")
    if cantilever_negative_results is not None and cantilever_negative_results.as_status != "OK":
        requirement_issues.append("Cantilever negative tension reinforcement does not satisfy the required A_s limits.")
    spacing_results: list[ReinforcementSpacingResults] = []
    if design_inputs.has_positive_design:
        spacing_results.extend(
            [
                geometry_results.positive_tension_spacing,
                geometry_results.positive_compression_spacing,
            ]
        )
    if design_inputs.has_simple_support_design:
        spacing_results.extend(
            [
                calculate_reinforcement_spacing(
                    design_inputs.geometry,
                    design_inputs.simple_support_bending.tension_reinforcement,
                    design_inputs.shear.stirrup_diameter_mm,
                ),
                calculate_reinforcement_spacing(
                    design_inputs.geometry,
                    design_inputs.simple_support_bending.compression_reinforcement,
                    design_inputs.shear.stirrup_diameter_mm,
                ),
            ]
        )
    if geometry_results.negative_tension_spacing is not None:
        spacing_results.append(geometry_results.negative_tension_spacing)
    if geometry_results.negative_compression_spacing is not None:
        spacing_results.append(geometry_results.negative_compression_spacing)
    if design_inputs.has_cantilever_negative_design:
        cantilever_spacing_results = [
            calculate_reinforcement_spacing(
                design_inputs.geometry,
                design_inputs.cantilever_negative_bending.tension_reinforcement,
                design_inputs.shear.stirrup_diameter_mm,
            ),
            calculate_reinforcement_spacing(
                design_inputs.geometry,
                design_inputs.cantilever_negative_bending.compression_reinforcement,
                design_inputs.shear.stirrup_diameter_mm,
            ),
        ]
        spacing_results.extend(cantilever_spacing_results)
    if any(spacing_result.overall_status != "OK" for spacing_result in spacing_results):
        requirement_issues.append("One or more reinforcement layers do not satisfy the minimum clear spacing requirement.")
    if shear_results.review_note:
        requirement_issues.append(shear_results.review_note)
    # combined.summary_note is an explanatory basis note for report/UI only.
    # It is not itself a design warning and must not drive the overall status.
    if torsion_results.enabled and torsion_results.warnings:
        requirement_issues.extend(
            warning for warning in torsion_results.warnings if _is_requirement_torsion_warning(warning)
        )
    if design_inputs.consider_deflection and deflection_results.status == "FAIL":
        requirement_issues.append(deflection_results.pass_fail_summary)
    if requirement_issues:
        return "DOES NOT MEET REQUIREMENTS", " ".join(requirement_issues)

    if review_flags:
        return "PASS WITH REVIEW", "Strength and detailing checks pass, but additional engineering review items remain open."
    return "PASS", "All current strength and detailing checks are satisfied."


def _flexural_as_clause_reference(design_code: DesignCode) -> str:
    if design_code in {DesignCode.ACI318_99, DesignCode.ACI318_08, DesignCode.ACI318_11}:
        return f"{_design_code_label(design_code)} 10.5.1"
    return f"{_design_code_label(design_code)} 9.6.1.2"


def _shear_strength_clause_reference(design_code: DesignCode) -> str:
    if design_code == DesignCode.ACI318_99:
        return "ACI 318-99 11.3 together with 11.5"
    if design_code in {DesignCode.ACI318_08, DesignCode.ACI318_11}:
        return f"{_design_code_label(design_code)} 11.2 together with 11.4"
    if design_code == DesignCode.ACI318_14:
        return "ACI 318-14 22.5.5.1 and 9.7.6.2"
    if design_code == DesignCode.ACI318_19:
        return "ACI 318-19 Table 22.5.5.1 and 9.7.6.2"
    return "ACI 318-25 Table 22.5.5.1 and 9.7.6.2"


def _shear_reinforcement_clause_reference(design_code: DesignCode) -> str:
    if design_code == DesignCode.ACI318_99:
        return "ACI 318-99 11.5.4 and 11.5.6"
    if design_code in {DesignCode.ACI318_08, DesignCode.ACI318_11}:
        return f"{_design_code_label(design_code)} 11.4.5 and 11.4.7"
    if design_code == DesignCode.ACI318_14:
        return "ACI 318-14 Chapter 9 and Chapter 22 beam shear-strength limits"
    if design_code == DesignCode.ACI318_19:
        return "ACI 318-19 Chapter 9 and Table 22.5.5.1"
    return "ACI 318-25 Chapter 9 and Table 22.5.5.1"


def _shear_minimum_clause_reference(design_code: DesignCode) -> str:
    if design_code == DesignCode.ACI318_99:
        return "ACI 318-99 11.5.5.1 and 11.5.5.3"
    if design_code in {DesignCode.ACI318_08, DesignCode.ACI318_11}:
        return f"{_design_code_label(design_code)} 11.4.6.1 and 11.4.6.3"
    return f"{_design_code_label(design_code)} 9.6.3"


def _design_code_label(design_code: DesignCode) -> str:
    mapping = {
        DesignCode.ACI318_99: "ACI 318-99",
        DesignCode.ACI318_08: "ACI 318-08",
        DesignCode.ACI318_11: "ACI 318-11",
        DesignCode.ACI318_14: "ACI 318-14",
        DesignCode.ACI318_19: "ACI 318-19",
        DesignCode.ACI318_25: "ACI 318-25",
    }
    return mapping[design_code]


def _format_aci_warning_reference(reference: str) -> str:
    normalized = reference.strip()
    if not normalized.startswith("ACI 318-"):
        return normalized

    _, code, remainder = normalized.split(" ", 2)
    code_label = f"ACI{code}"

    def _format_part(part: str) -> str:
        part = part.strip()
        if not part:
            return ""
        if part.startswith("ACI 318-"):
            return _format_aci_warning_reference(part)
        if part[0].isdigit():
            return f"{code_label} - Clause {part}"
        if part.startswith("Clause ") or part.startswith("Table ") or part.startswith("Chapter "):
            return f"{code_label} - {part}"
        return f"{code_label} - {part}"

    if " together with " in remainder:
        left, right = remainder.split(" together with ", 1)
        return f"{_format_part(left)} together with {_format_part(right)}"
    if " and " in remainder:
        left, right = remainder.split(" and ", 1)
        return f"{_format_part(left)} and {_format_part(right)}"
    return _format_part(remainder)


def _torsion_spacing_clause_reference(code_version: str) -> str:
    mapping = {
        "ACI 318-99": "ACI 318-99 11.6.6.1",
        "ACI 318-08": "ACI 318-08 11.5.6.1",
        "ACI 318-11": "ACI 318-11 11.5.6.1",
        "ACI 318-14": "ACI 318-14 9.7.6.3.3",
        "ACI 318-19": "ACI 318-19 9.7.6.3.3",
        "ACI 318-25": "ACI 318-25 9.7.6.3.3",
    }
    return mapping.get(code_version, code_version)


def _torsion_cross_section_clause_reference(code_version: str) -> str:
    mapping = {
        "ACI 318-99": "ACI 318-99 11.6.3.1",
        "ACI 318-08": "ACI 318-08 11.5.3.1",
        "ACI 318-11": "ACI 318-11 11.5.3.1",
        "ACI 318-14": "ACI 318-14 22.7.7.1",
        "ACI 318-19": "ACI 318-19 22.7.7.1",
        "ACI 318-25": "ACI 318-25 22.7.7.1",
    }
    return mapping.get(code_version, code_version)


def _combined_transverse_reinforcement_clause(
    design_code: DesignCode,
    torsion_results: TorsionDesignResults,
) -> str:
    shear_clause = _shear_reinforcement_clause_reference(design_code)
    torsion_clause = (
        torsion_results.transverse_reinf_required_governing
        or f"{torsion_results.code_version} torsion transverse reinforcement provisions"
    )
    return f"{shear_clause} together with {torsion_clause}"


def _formalize_shear_note(message: str, design_code: DesignCode) -> str:
    normalized = message.strip().rstrip(".")
    if "Av" in normalized or "lambda_s" in normalized:
        clause = _shear_minimum_clause_reference(design_code)
        if design_code in {DesignCode.ACI318_19, DesignCode.ACI318_25}:
            clause = f"{clause} together with {_design_code_label(design_code)} Table 22.5.5.1"
        return (
            f"{normalized}. {_format_aci_warning_reference(clause)}. This does not satisfy the minimum shear reinforcement trigger/check basis."
        )
    return (
        f"{normalized}. {_format_aci_warning_reference(_shear_reinforcement_clause_reference(design_code))}. "
        "This does not satisfy the applicable shear detailing requirements."
    )


def _formalize_torsion_warning(message: str, torsion_results: TorsionDesignResults) -> str:
    normalized = message.strip().rstrip(".")
    code = torsion_results.code_version
    if "required At/s" in normalized:
        clause = torsion_results.transverse_reinf_required_governing or f"{code} torsion transverse reinforcement provisions"
        normalized = normalized.replace("At/s", "A_t/s")
        return f"{normalized}. {_format_aci_warning_reference(clause)}. This does not satisfy the required torsion transverse reinforcement provisions."
    if "required Al" in normalized:
        clause = torsion_results.longitudinal_reinf_required_governing or f"{code} torsion longitudinal reinforcement provisions"
        normalized = normalized.replace("Al", "A_l")
        return f"{normalized}. {_format_aci_warning_reference(clause)}. This does not satisfy the required torsion longitudinal reinforcement provisions."
    if "maximum spacing permitted for torsion" in normalized:
        return f"{normalized}. {_format_aci_warning_reference(_torsion_spacing_clause_reference(code))}. This does not satisfy the maximum permitted torsion stirrup spacing."
    if "cross-sectional limit check" in normalized:
        return f"{normalized}. {_format_aci_warning_reference(_torsion_cross_section_clause_reference(code))}. This does not satisfy the torsional cross-sectional strength requirement."
    if "Closed stirrups are required" in normalized:
        return f"{normalized}. This does not satisfy the detailing assumptions of the implemented torsion procedure and is not suitable for practical construction."
    if "Compatibility torsion" in normalized:
        return f"{normalized}. This is an analysis assumption notice and should be confirmed by the design engineer."
    if "alternative torsion design procedure" in normalized:
        return f"{normalized}. This is an informational code note and not a design failure."
    return f"{normalized}."


def _is_requirement_torsion_warning(message: str) -> bool:
    normalized = message.strip()
    informational_markers = (
        "Compatibility torsion is evaluated",
        "alternative torsion design procedure",
    )
    return not any(marker in normalized for marker in informational_markers)


def _formalize_general_warning(message: str, design_code: DesignCode) -> str:
    normalized = message.strip()
    if "minimum clear spacing requirement" in normalized:
        return (
            f"{normalized.rstrip('.')} This does not satisfy the specified minimum clear spacing requirement "
            "and is not suitable for practical construction."
        )
    return normalized if normalized.endswith(".") else f"{normalized}."


def _calculate_beta_1(fc_prime_ksc: float) -> float:
    if 0 < fc_prime_ksc <= 280:
        return 0.85
    return max(0.65, 0.85 - (0.05 * (fc_prime_ksc - 280) / 70))


def _calculate_flexural_phi(design_code: DesignCode, et: float, ety: float) -> float:
    if math.isnan(et):
        return math.nan
    if design_code == DesignCode.ACI318_99:
        return 0.9
    if design_code in {DesignCode.ACI318_08, DesignCode.ACI318_11, DesignCode.ACI318_14}:
        if et <= ety:
            return 0.65
        if et <= 0.005:
            return 0.65 + ((0.25 / (0.005 - ety)) * (et - ety))
        return 0.9
    if et <= ety:
        return 0.65
    if et <= ety + 0.003:
        return 0.65 + ((0.25 / 0.003) * (et - ety))
    return 0.9


def calculate_flexural_phi_value(design_code: DesignCode, et: float, ety: float) -> float:
    return _calculate_flexural_phi(design_code, et, ety)


def flexural_phi_chart_supported(design_code: DesignCode) -> bool:
    return design_code != DesignCode.ACI318_99


def flexural_phi_chart_points(design_code: DesignCode, ety: float) -> list[tuple[float, float]]:
    if design_code == DesignCode.ACI318_99:
        return []
    if design_code == DesignCode.ACI318_08:
        return [(0.0, 0.65), (0.002, 0.65), (0.005, 0.9), (0.006, 0.9)]
    if design_code == DesignCode.ACI318_11:
        return [(0.0, 0.65), (0.002, 0.65), (0.005, 0.9), (0.006, 0.9)]
    if design_code == DesignCode.ACI318_14:
        transition_end = 0.005
        return [(0.0, 0.65), (ety, 0.65), (transition_end, 0.9), (max(0.006, transition_end + 0.001), 0.9)]
    transition_end = ety + 0.003
    return [(0.0, 0.65), (ety, 0.65), (transition_end, 0.9), (max(0.006, transition_end + 0.001), 0.9)]


def _calculate_shear_phi(design_code: DesignCode) -> float:
    if design_code == DesignCode.ACI318_99:
        return 0.85
    return 0.75


def _calculate_aci318_19_size_effect_factor(d_cm: float) -> float:
    d_in = d_cm / 2.54
    return min(math.sqrt(2 / (1 + (d_in / 10))), 1.0)


def _calculate_aci318_19_vc_max_kg(
    sqrt_fc: float,
    width_cm: float,
    d_cm: float,
    size_effect_factor: float,
    lambda_concrete: float = 1.0,
) -> float:
    return 1.33 * lambda_concrete * size_effect_factor * sqrt_fc * width_cm * d_cm


def _calculate_av_min_per_spacing_cm(sqrt_fc: float, width_cm: float, fy_ksc: float) -> float:
    return max(
        _safe_divide(0.2 * sqrt_fc * width_cm, fy_ksc),
        _safe_divide(3.5 * width_cm, fy_ksc),
    )


def _auto_select_spacing_cm(required_spacing_cm: float, increment_cm: float = AUTO_SHEAR_SPACING_INCREMENT_CM) -> float:
    minimum_auto_spacing_cm = 5.0
    if not math.isfinite(required_spacing_cm):
        return max(increment_cm, minimum_auto_spacing_cm)
    snapped_spacing_cm = math.floor(required_spacing_cm / increment_cm) * increment_cm
    if snapped_spacing_cm > 0:
        return max(snapped_spacing_cm, minimum_auto_spacing_cm)
    return max(required_spacing_cm, minimum_auto_spacing_cm)


def _resolve_shared_stirrup_spacing_cm(
    design_inputs: BeamDesignInputSet,
    geometry_results: BeamGeometryResults,
    shear_results: ShearDesignResults,
    torsion_results: TorsionDesignResults,
) -> float:
    required_spacing_cm, _ = _combined_required_spacing_limit_cm(
        shear_results,
        torsion_results,
        _combined_required_transverse_mm2_per_mm(design_inputs, geometry_results, shear_results, torsion_results),
    )
    if design_inputs.shear.spacing_mode == ShearSpacingMode.AUTO:
        return _auto_select_spacing_cm(required_spacing_cm)
    return design_inputs.shear.provided_spacing_cm


def _combined_required_transverse_mm2_per_mm(
    design_inputs: BeamDesignInputSet,
    geometry_results: BeamGeometryResults,
    shear_results: ShearDesignResults,
    torsion_results: TorsionDesignResults,
) -> float:
    d_mm = shear_results.effective_depth_cm * 10.0
    # Keep the shear component on the same mm2/mm basis as the torsion component for shared-stirrup interaction.
    shear_required_transverse_mm2_per_mm = _safe_divide(
        shear_results.nominal_vs_required_kg,
        design_inputs.materials.shear_steel_yield_ksc * d_mm,
    ) * 100.0
    torsion_required_transverse_mm2_per_mm = (
        torsion_results.transverse_reinf_required_mm2_per_mm * design_inputs.shear.legs_per_plane
    )
    return shear_required_transverse_mm2_per_mm + torsion_required_transverse_mm2_per_mm


def _combined_required_spacing_limit_cm(
    shear_results: ShearDesignResults,
    torsion_results: TorsionDesignResults,
    combined_required_transverse_mm2_per_mm: float,
) -> tuple[float, str]:
    spacing_candidates = [
        (
            _safe_divide(shear_results.av_cm2 * 100.0, combined_required_transverse_mm2_per_mm) / 10.0,
            "Combined shear + torsion transverse reinforcement demand",
        ),
        (shear_results.s_max_from_av_cm, "Shear code spacing limit from Av"),
        (shear_results.s_max_from_vs_cm, "Shear code spacing limit from Vs"),
        (torsion_results.max_spacing_mm / 10.0, "Torsion maximum stirrup spacing"),
    ]
    valid_candidates = [(value, reason) for value, reason in spacing_candidates if math.isfinite(value) and value > 0]
    if not valid_candidates:
        return (shear_results.required_spacing_cm, "No valid combined spacing limit")
    return min(valid_candidates, key=lambda item: item[0])


def _evaluate_combined_shear_torsion_cross_section_limit(
    design_inputs: BeamDesignInputSet,
    geometry_results: BeamGeometryResults,
    shear_results: ShearDesignResults,
    torsion_results: TorsionDesignResults,
) -> tuple[bool, float, float, float, float, float, str, bool]:
    if design_inputs.metadata.design_code not in {
        DesignCode.ACI318_08,
        DesignCode.ACI318_11,
        DesignCode.ACI318_14,
        DesignCode.ACI318_19,
        DesignCode.ACI318_25,
    }:
        return (False, 0.0, 0.0, 0.0, 0.0, 0.0, "", True)

    width_cm = design_inputs.geometry.width_cm
    d_cm = shear_results.effective_depth_cm
    if width_cm <= 0.0 or d_cm <= 0.0:
        return (False, 0.0, 0.0, 0.0, 0.0, 0.0, "", True)

    # ACI 318-14/19/25 22.7.7.1 combines the solid-section shear stress from Vu
    # with the torsional stress from Tu using an RSS stress limit. The current
    # beam app scope is a solid rectangular section using the same d basis as shear.
    shear_stress_mpa = ksc_to_mpa(_safe_divide(shear_results.input_factored_shear_kg, width_cm * d_cm))
    vc_stress_mpa = ksc_to_mpa(_safe_divide(shear_results.vc_kg, width_cm * d_cm))
    tu_nmm = kgf_m_to_n_mm(design_inputs.torsion.factored_torsion_kgfm)
    torsion_stress_mpa = tu_nmm * torsion_results.ph_mm / (1.7 * (torsion_results.aoh_mm2**2))
    lhs_mpa = math.hypot(shear_stress_mpa, torsion_stress_mpa)
    rhs_mpa = 0.75 * (
        vc_stress_mpa + (0.66 * math.sqrt(ksc_to_mpa(design_inputs.materials.concrete_strength_ksc)))
    )
    ratio = _safe_divide(lhs_mpa, rhs_mpa)
    clause = _combined_shear_torsion_cross_section_clause(design_inputs.metadata.design_code)
    return (
        True,
        shear_stress_mpa,
        torsion_stress_mpa,
        lhs_mpa,
        rhs_mpa,
        ratio,
        clause,
        lhs_mpa <= rhs_mpa + 1e-9,
    )


def _combined_shear_torsion_cross_section_clause(design_code: DesignCode) -> str:
    if design_code == DesignCode.ACI318_08:
        return "ACI 318-08 11.5.3.1"
    if design_code == DesignCode.ACI318_11:
        return "ACI 318-11 11.5.3.1"
    if design_code == DesignCode.ACI318_14:
        return "ACI 318-14 22.7.7.1"
    if design_code == DesignCode.ACI318_19:
        return "ACI 318-19 22.7.7.1"
    if design_code == DesignCode.ACI318_25:
        return "ACI 318-25 22.7.7.1"
    return ""


def _calculate_rho_required(fc_prime_ksc: float, fy_ksc: float, ru_kg_per_cm2: float) -> float:
    discriminant = 1 - ((2 * ru_kg_per_cm2) / (0.85 * fc_prime_ksc))
    if discriminant < 0:
        return math.nan
    return 0.85 * (fc_prime_ksc / fy_ksc) * (1 - math.sqrt(discriminant))


def _calculate_rho_min(design_code: DesignCode, fc_prime_ksc: float, fy_ksc: float) -> float:
    if design_code == DesignCode.ACI318_99:
        return 14 / fy_ksc
    return max((14 / fy_ksc), (0.8 * math.sqrt(fc_prime_ksc) / fy_ksc))


def _calculate_rho_max(
    design_code: DesignCode,
    fc_prime_ksc: float,
    fy_ksc: float,
    beta_1: float,
) -> float:
    epsilon_y = fy_ksc / 2040000.0
    if design_code == DesignCode.ACI318_99:
        rho_balanced = 0.85 * beta_1 * (fc_prime_ksc / fy_ksc) * (0.003 / (0.003 + epsilon_y))
        return 0.75 * rho_balanced
    if design_code in {DesignCode.ACI318_08, DesignCode.ACI318_11, DesignCode.ACI318_14}:
        return 0.85 * beta_1 * (fc_prime_ksc / fy_ksc) * (0.003 / (0.003 + 0.005))
    return 0.85 * beta_1 * (fc_prime_ksc / fy_ksc) * (0.003 / (0.006 + epsilon_y))


def _calculate_centroid_from_face_cm(
    geometry: BeamGeometryInput,
    reinforcement: ReinforcementArrangementInput,
    stirrup_diameter_mm: int,
    denominator_groups: tuple[tuple[int, int], ...],
) -> float:
    numerator = 0.0
    layers = reinforcement.layers()

    for layer_index, layer in enumerate(layers):
        base_distance_cm = _layer_base_distance_cm(
            geometry,
            reinforcement,
            stirrup_diameter_mm,
            layer_index,
        )
        for group in layer.groups():
            numerator += (base_distance_cm + (_group_diameter_cm(group) / 2)) * group.count

    denominator = 0
    for layer_index, group_index in denominator_groups:
        layer = layers[layer_index]
        group = layer.groups()[group_index]
        denominator += group.count

    return _safe_divide(numerator, denominator)


def _layer_base_distance_cm(
    geometry: BeamGeometryInput,
    reinforcement: ReinforcementArrangementInput,
    stirrup_diameter_mm: int,
    layer_index: int,
) -> float:
    base_distance_cm = geometry.cover_cm + _diameter_cm(stirrup_diameter_mm)
    layers = reinforcement.layers()

    for previous_index in range(layer_index):
        previous_layer = layers[previous_index]
        previous_diameter_a_cm = _group_diameter_cm(previous_layer.group_a)
        previous_diameter_b_cm = _group_diameter_cm(previous_layer.group_b)
        base_distance_cm += max(previous_diameter_a_cm, previous_diameter_b_cm) + max(
            geometry.minimum_clear_spacing_cm,
            previous_diameter_a_cm,
            previous_diameter_b_cm,
        )

    return base_distance_cm


def _calculate_layer_spacing_cm(
    geometry: BeamGeometryInput,
    layer: RebarLayerInput,
    stirrup_diameter_mm: int,
) -> float:
    total_bars = layer.total_bars
    if total_bars <= 1:
        return math.nan
    clear_width_cm = geometry.width_cm - (geometry.cover_cm * 2) - (_diameter_cm(stirrup_diameter_mm) * 2)
    occupied_width_cm = (
        _group_diameter_cm(layer.group_a) * layer.group_a.count
        + _group_diameter_cm(layer.group_b) * layer.group_b.count
    )
    return (clear_width_cm - occupied_width_cm) / (total_bars - 1)


def _calculate_as_status(rho_provided: float, rho_min: float, rho_max: float) -> str:
    if rho_min <= rho_provided <= rho_max:
        return "OK"
    if rho_provided <= rho_min:
        return "NOT OK As < As min"
    return "NOT OK As > As max"


def _group_diameter_cm(group: RebarGroupInput) -> float:
    return _diameter_cm(group.diameter_mm)


def _diameter_cm(diameter_mm: int | None) -> float:
    if diameter_mm is None:
        return 0.0
    return diameter_mm / 10


def _manual_property_value(value: float | None) -> float:
    if value is None:
        raise ValueError("Manual material property value is missing.")
    return value


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return math.nan
    return numerator / denominator
