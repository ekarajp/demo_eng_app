from __future__ import annotations

import math

from .models import (
    BeamDesignInputSet,
    BeamDesignResults,
    BeamGeometryInput,
    BeamGeometryResults,
    DeflectionCheckInput,
    DeflectionCheckResults,
    DesignCode,
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
ES_KSC = 2.04 * (10**6)
DEFAULT_EC_LOGIC = "Ec = 15100 * sqrt(fc')"
DEFAULT_ES_LOGIC = "Es = 2.04 * 10^6"
DEFAULT_FR_LOGIC = "fr = 2 * sqrt(fc')"
AUTO_SHEAR_SPACING_INCREMENT_CM = 2.5


def calculate_default_ec_ksc(fc_prime_ksc: float) -> float:
    return 15100 * math.sqrt(fc_prime_ksc)


def calculate_default_es_ksc() -> float:
    return ES_KSC


def calculate_default_fr_ksc(fc_prime_ksc: float) -> float:
    return 2 * math.sqrt(fc_prime_ksc)


def calculate_material_properties(
    materials: MaterialPropertiesInput,
    material_settings: MaterialPropertySettings | None = None,
) -> MaterialResults:
    concrete_strength = materials.concrete_strength_ksc
    settings = material_settings or MaterialPropertySettings()
    ec_default_ksc = calculate_default_ec_ksc(concrete_strength)
    es_default_ksc = calculate_default_es_ksc()
    fr_default_ksc = calculate_default_fr_ksc(concrete_strength)
    ec_ksc = ec_default_ksc if settings.ec.mode == MaterialPropertyMode.DEFAULT else _manual_property_value(settings.ec.manual_value)
    es_ksc = es_default_ksc if settings.es.mode == MaterialPropertyMode.DEFAULT else _manual_property_value(settings.es.manual_value)
    fr_ksc = fr_default_ksc if settings.fr.mode == MaterialPropertyMode.DEFAULT else _manual_property_value(settings.fr.manual_value)
    return MaterialResults(
        fc_prime_ksc=concrete_strength,
        fy_ksc=materials.main_steel_yield_ksc,
        fvy_ksc=materials.shear_steel_yield_ksc,
        ec_ksc=ec_ksc,
        es_ksc=es_ksc,
        modular_ratio_n=_safe_divide(es_ksc, ec_ksc),
        modulus_of_rupture_fr_ksc=fr_ksc,
        beta_1=_calculate_beta_1(concrete_strength),
        ec_mode=settings.ec.mode,
        es_mode=settings.es.mode,
        fr_mode=settings.fr.mode,
        ec_default_ksc=ec_default_ksc,
        es_default_ksc=es_default_ksc,
        fr_default_ksc=fr_default_ksc,
        ec_default_logic=DEFAULT_EC_LOGIC,
        es_default_logic=DEFAULT_ES_LOGIC,
        fr_default_logic=DEFAULT_FR_LOGIC,
    )


def calculate_reinforcement_spacing(
    geometry: BeamGeometryInput,
    reinforcement: ReinforcementArrangementInput,
    stirrup_diameter_mm: int,
) -> ReinforcementSpacingResults:
    layer_results: list[LayerSpacingResult] = []
    overall_status = "OK"

    for layer_index, layer in enumerate(reinforcement.layers(), start=1):
        diameters_cm = [_group_diameter_cm(group) for group in layer.groups()]
        total_bars = layer.total_bars
        spacing_cm = _calculate_layer_spacing_cm(geometry, layer, stirrup_diameter_mm)

        required_spacing_cm: float | None
        status: str
        message = ""
        if total_bars == 0:
            required_spacing_cm = None
            spacing_value = None
            status = "N/A"
        elif total_bars == 1:
            required_spacing_cm = None
            spacing_value = None
            status = "OK"
            message = "Single bar in layer; clear spacing check is not governing."
        else:
            required_spacing_cm = max(
                geometry.minimum_clear_spacing_cm,
                diameters_cm[0],
                diameters_cm[1],
            )
            spacing_value = spacing_cm
            status = "OK" if spacing_cm >= required_spacing_cm else "NOT OK"
            if status == "NOT OK":
                message = (
                    f"Provided clear spacing {spacing_cm:.2f} cm is less than "
                    f"required {required_spacing_cm:.2f} cm."
                )
                overall_status = "NOT OK"

        layer_results.append(
            LayerSpacingResult(
                layer_index=layer_index,
                group_a_diameter_mm=layer.group_a.diameter_mm,
                group_a_count=layer.group_a.count,
                group_b_diameter_mm=layer.group_b.diameter_mm,
                group_b_count=layer.group_b.count,
                spacing_cm=spacing_value,
                required_spacing_cm=required_spacing_cm,
                status=status,
                message=message,
            )
        )

    return ReinforcementSpacingResults(
        layer_1=layer_results[0],
        layer_2=layer_results[1],
        layer_3=layer_results[2],
        overall_status=overall_status,
    )


def calculate_beam_geometry(
    geometry: BeamGeometryInput,
    positive_bending: PositiveBendingInput,
    negative_bending: NegativeBendingInput,
    shear: ShearDesignInput,
    *,
    include_negative: bool = True,
) -> BeamGeometryResults:
    cover_plus_stirrup_cm = geometry.cover_cm + _diameter_cm(shear.stirrup_diameter_mm)

    positive_compression_centroid_cm = _calculate_centroid_from_face_cm(
        geometry,
        positive_bending.compression_reinforcement,
        shear.stirrup_diameter_mm,
        denominator_groups=((0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)),
    )
    positive_tension_centroid_from_bottom_cm = _calculate_centroid_from_face_cm(
        geometry,
        positive_bending.tension_reinforcement,
        shear.stirrup_diameter_mm,
        denominator_groups=((0, 0), (0, 1), (1, 0), (1, 1)),
    )

    negative_compression_centroid_cm: float | None = None
    negative_tension_centroid_from_top_cm: float | None = None
    d_minus_cm: float | None = None
    negative_compression_spacing: ReinforcementSpacingResults | None = None
    negative_tension_spacing: ReinforcementSpacingResults | None = None
    if include_negative:
        negative_compression_centroid_cm = _calculate_centroid_from_face_cm(
            geometry,
            negative_bending.compression_reinforcement,
            shear.stirrup_diameter_mm,
            denominator_groups=((0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)),
        )
        negative_tension_centroid_from_top_cm = _calculate_centroid_from_face_cm(
            geometry,
            negative_bending.tension_reinforcement,
            shear.stirrup_diameter_mm,
            denominator_groups=((0, 0), (0, 1), (1, 0), (1, 1)),
        )
        d_minus_cm = geometry.depth_cm - positive_compression_centroid_cm
        negative_compression_spacing = calculate_reinforcement_spacing(
            geometry,
            negative_bending.compression_reinforcement,
            shear.stirrup_diameter_mm,
        )
        negative_tension_spacing = calculate_reinforcement_spacing(
            geometry,
            negative_bending.tension_reinforcement,
            shear.stirrup_diameter_mm,
        )

    return BeamGeometryResults(
        section_area_cm2=geometry.width_cm * geometry.depth_cm,
        gross_moment_of_inertia_cm4=geometry.width_cm * (geometry.depth_cm**3) / 12,
        cover_plus_stirrup_cm=cover_plus_stirrup_cm,
        positive_compression_centroid_d_prime_cm=positive_compression_centroid_cm,
        positive_tension_centroid_from_bottom_d_cm=positive_tension_centroid_from_bottom_cm,
        negative_compression_centroid_from_bottom_cm=negative_compression_centroid_cm,
        negative_tension_centroid_from_top_cm=negative_tension_centroid_from_top_cm,
        d_plus_cm=geometry.depth_cm - positive_tension_centroid_from_bottom_cm,
        d_minus_cm=d_minus_cm,
        positive_compression_spacing=calculate_reinforcement_spacing(
            geometry,
            positive_bending.compression_reinforcement,
            shear.stirrup_diameter_mm,
        ),
        positive_tension_spacing=calculate_reinforcement_spacing(
            geometry,
            positive_bending.tension_reinforcement,
            shear.stirrup_diameter_mm,
        ),
        negative_compression_spacing=negative_compression_spacing,
        negative_tension_spacing=negative_tension_spacing,
    )


def calculate_positive_bending_design(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    positive_bending: PositiveBendingInput,
    design_inputs: BeamDesignInputSet,
) -> FlexuralDesignResults:
    material_results = calculate_material_properties(materials, design_inputs.material_settings)
    geometry_results = calculate_beam_geometry(
        geometry,
        design_inputs.positive_bending,
        design_inputs.negative_bending,
        design_inputs.shear,
        include_negative=design_inputs.has_negative_design,
    )
    d_plus_cm = geometry_results.d_plus_cm
    as_provided_cm2 = positive_bending.tension_reinforcement.total_area_cm2
    rho_provided = _safe_divide(as_provided_cm2, geometry.width_cm * d_plus_cm)
    a_cm = _safe_divide(
        as_provided_cm2 * materials.main_steel_yield_ksc,
        0.85 * materials.concrete_strength_ksc * geometry.width_cm,
    )
    c_cm = _safe_divide(a_cm, material_results.beta_1)
    dt_cm = (
        geometry.depth_cm
        - geometry.cover_cm
        - _diameter_cm(design_inputs.shear.stirrup_diameter_mm)
        - (_group_diameter_cm(positive_bending.tension_reinforcement.layer_1.group_a) / 2)
    )
    ety = _safe_divide(materials.main_steel_yield_ksc, material_results.es_ksc)
    et = _safe_divide(ECU * (dt_cm - c_cm), c_cm)
    phi = _calculate_flexural_phi(design_inputs.metadata.design_code, et, ety)
    ru_kg_per_cm2 = _safe_divide(
        positive_bending.factored_moment_kgm * 100,
        phi * geometry.width_cm * (d_plus_cm**2),
    )
    rho_required = _calculate_rho_required(
        materials.concrete_strength_ksc,
        materials.main_steel_yield_ksc,
        ru_kg_per_cm2,
    )
    rho_min = _calculate_rho_min(
        design_inputs.metadata.design_code,
        materials.concrete_strength_ksc,
        materials.main_steel_yield_ksc,
    )
    rho_max = _calculate_rho_max(
        design_inputs.metadata.design_code,
        materials.concrete_strength_ksc,
        materials.main_steel_yield_ksc,
        material_results.beta_1,
    )
    as_required_cm2 = rho_required * geometry.width_cm * d_plus_cm
    as_min_cm2 = rho_min * geometry.width_cm * d_plus_cm
    as_max_cm2 = rho_max * geometry.width_cm * d_plus_cm
    mn_kgm = as_provided_cm2 * materials.main_steel_yield_ksc * (d_plus_cm - (a_cm / 2)) / 100
    phi_mn_kgm = mn_kgm * phi
    ratio = _safe_divide(positive_bending.factored_moment_kgm, phi_mn_kgm)
    as_status = _calculate_as_status(rho_provided, rho_min, rho_max)
    ratio_status = "OK" if phi_mn_kgm >= positive_bending.factored_moment_kgm else "NOT OK"
    design_status = "PASS" if as_status == "OK" and ratio_status == "OK" else "FAIL"

    return FlexuralDesignResults(
        phi=phi,
        ru_kg_per_cm2=ru_kg_per_cm2,
        rho_required=rho_required,
        as_required_cm2=as_required_cm2,
        as_provided_cm2=as_provided_cm2,
        rho_provided=rho_provided,
        rho_min=rho_min,
        rho_max=rho_max,
        as_min_cm2=as_min_cm2,
        as_max_cm2=as_max_cm2,
        as_status=as_status,
        a_cm=a_cm,
        c_cm=c_cm,
        dt_cm=dt_cm,
        ety=ety,
        et=et,
        mn_kgm=mn_kgm,
        phi_mn_kgm=phi_mn_kgm,
        ratio=ratio,
        ratio_status=ratio_status,
        design_status=design_status,
    )


def calculate_shear_design(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    shear: ShearDesignInput,
    design_inputs: BeamDesignInputSet,
) -> ShearDesignResults:
    geometry_results = calculate_beam_geometry(
        geometry,
        design_inputs.positive_bending,
        design_inputs.negative_bending,
        design_inputs.shear,
        include_negative=design_inputs.has_negative_design,
    )
    phi_shear = _calculate_shear_phi(design_inputs.metadata.design_code)
    d_plus_cm = geometry_results.d_plus_cm
    sqrt_fc = math.sqrt(materials.concrete_strength_ksc)
    base_vc_kg = 0.53 * sqrt_fc * geometry.width_cm * d_plus_cm
    vs_max_kg = 2.1 * sqrt_fc * geometry.width_cm * d_plus_cm
    phi_vs_max_kg = phi_shear * vs_max_kg
    av_cm2 = (math.pi * (_diameter_cm(shear.stirrup_diameter_mm) ** 2) / 4) * shear.legs_per_plane
    av_min_per_spacing_cm = _calculate_av_min_per_spacing_cm(
        sqrt_fc,
        geometry.width_cm,
        materials.shear_steel_yield_ksc,
    )
    s_max_from_av_cm = min(
        _safe_divide(av_cm2 * materials.shear_steel_yield_ksc, 0.2 * sqrt_fc * geometry.width_cm),
        _safe_divide(av_cm2 * materials.shear_steel_yield_ksc, 3.5 * geometry.width_cm),
    )

    def _calculate_shear_state(vc_kg_value: float) -> tuple[float, float, float, float, float, float]:
        phi_vc_kg_value = phi_shear * vc_kg_value
        phi_vs_required_kg_value = max(shear.factored_shear_kg - phi_vc_kg_value, 0)
        nominal_vs_required_kg_value = _safe_divide(phi_vs_required_kg_value, phi_shear)
        if nominal_vs_required_kg_value <= 1.1 * sqrt_fc * geometry.width_cm * d_plus_cm:
            s_max_from_vs_cm_value = min(d_plus_cm / 2, 60)
        else:
            s_max_from_vs_cm_value = min(d_plus_cm / 4, 30)

        if phi_vs_required_kg_value == 0:
            strength_spacing_cm_value = math.inf
        else:
            strength_spacing_cm_value = _safe_divide(
                av_cm2 * materials.shear_steel_yield_ksc * d_plus_cm,
                nominal_vs_required_kg_value,
            )

        required_spacing_cm_value = min(strength_spacing_cm_value, s_max_from_av_cm, s_max_from_vs_cm_value)
        provided_spacing_cm_value = (
            _auto_select_spacing_cm(required_spacing_cm_value)
            if shear.spacing_mode == ShearSpacingMode.AUTO
            else shear.provided_spacing_cm
        )
        return (
            phi_vc_kg_value,
            phi_vs_required_kg_value,
            nominal_vs_required_kg_value,
            s_max_from_vs_cm_value,
            required_spacing_cm_value,
            provided_spacing_cm_value,
        )

    (
        phi_vc_kg,
        phi_vs_required_kg,
        nominal_vs_required_kg,
        s_max_from_vs_cm,
        required_spacing_cm,
        provided_spacing_cm,
    ) = _calculate_shear_state(base_vc_kg)

    av_min_cm2 = av_min_per_spacing_cm * provided_spacing_cm
    size_effect_factor = 1.0
    size_effect_applied = False
    vc_kg = base_vc_kg
    if (
        design_inputs.metadata.design_code == DesignCode.ACI318_19
        and av_cm2 < av_min_cm2 - 1e-9
    ):
        size_effect_factor = _calculate_aci318_19_size_effect_factor(d_plus_cm)
        size_effect_applied = size_effect_factor < 1.0 - 1e-9
        vc_kg = base_vc_kg * size_effect_factor
        (
            phi_vc_kg,
            phi_vs_required_kg,
            nominal_vs_required_kg,
            s_max_from_vs_cm,
            required_spacing_cm,
            provided_spacing_cm,
        ) = _calculate_shear_state(vc_kg)
        av_min_cm2 = av_min_per_spacing_cm * provided_spacing_cm

    vc_max_kg: float | None = None
    vc_capped_by_max = False
    if design_inputs.metadata.design_code == DesignCode.ACI318_19:
        vc_max_kg = _calculate_aci318_19_vc_max_kg(
            sqrt_fc,
            geometry.width_cm,
            d_plus_cm,
            size_effect_factor,
        )
        if vc_kg > vc_max_kg + 1e-9:
            vc_kg = vc_max_kg
            vc_capped_by_max = True
            (
                phi_vc_kg,
                phi_vs_required_kg,
                nominal_vs_required_kg,
                s_max_from_vs_cm,
                required_spacing_cm,
                provided_spacing_cm,
            ) = _calculate_shear_state(vc_kg)
            av_min_cm2 = av_min_per_spacing_cm * provided_spacing_cm

    vs_provided_kg = _safe_divide(av_cm2 * materials.shear_steel_yield_ksc * d_plus_cm, provided_spacing_cm)
    phi_vs_provided_kg = phi_shear * vs_provided_kg
    effective_vs_kg = min(vs_provided_kg, vs_max_kg)
    vn_kg = vc_kg + effective_vs_kg
    phi_vn_kg = phi_shear * vn_kg
    capacity_ratio = _safe_divide(shear.factored_shear_kg, phi_vn_kg)
    phi_vn_limit_kg = phi_vc_kg + phi_vs_max_kg

    spacing_ok = provided_spacing_cm <= required_spacing_cm + 1e-9
    strength_limit_ok = nominal_vs_required_kg <= vs_max_kg + 1e-9
    capacity_ok = phi_vn_kg >= shear.factored_shear_kg
    section_change_required = shear.factored_shear_kg > phi_vn_limit_kg + 1e-9
    design_status = "PASS" if spacing_ok and strength_limit_ok and capacity_ok else "FAIL"

    review_notes: list[str] = []
    section_change_note = ""
    if section_change_required:
        section_change_note = (
            "Applied shear exceeds the maximum design shear strength of the current section, even when the shear reinforcement contribution is limited to Vs,max. "
            "Increase the beam section and/or revise the section properties."
        )
        review_notes.append(section_change_note)
    if not strength_limit_ok:
        review_notes.append("Required shear reinforcement exceeds the current section limit. Increase section size or revise detailing.")
    if not spacing_ok:
        review_notes.append(
            f"Provided spacing {provided_spacing_cm:.2f} cm exceeds required spacing {required_spacing_cm:.2f} cm."
        )
    if av_cm2 < av_min_cm2 - 1e-9:
        review_notes.append(
            f"Av = {av_cm2:.3f} cm2 is less than Av,min = {av_min_cm2:.3f} cm2."
        )
        if design_inputs.metadata.design_code == DesignCode.ACI318_19:
            review_notes.append(
                f"ACI 318-19 size effect factor lambda_s = {size_effect_factor:.3f} was applied to Vc."
            )
    if vc_capped_by_max and vc_max_kg is not None:
        review_notes.append(
            f"ACI 318-19 Vc was limited to Vc,max = {vc_max_kg:.3f} kg."
        )
    if vs_provided_kg > vs_max_kg + 1e-9:
        review_notes.append("Provided stirrup spacing gives Vs above Vs,max; PhiVn is capped at the section shear limit.")
    review_note = " ".join(review_notes)

    return ShearDesignResults(
        phi=phi_shear,
        vc_kg=vc_kg,
        phi_vc_kg=phi_vc_kg,
        vc_max_kg=vc_max_kg,
        vc_capped_by_max=vc_capped_by_max,
        vs_max_kg=vs_max_kg,
        phi_vs_max_kg=phi_vs_max_kg,
        phi_vs_required_kg=phi_vs_required_kg,
        nominal_vs_required_kg=nominal_vs_required_kg,
        av_cm2=av_cm2,
        av_min_cm2=av_min_cm2,
        size_effect_factor=size_effect_factor,
        size_effect_applied=size_effect_applied,
        s_max_from_av_cm=s_max_from_av_cm,
        s_max_from_vs_cm=s_max_from_vs_cm,
        required_spacing_cm=required_spacing_cm,
        provided_spacing_cm=provided_spacing_cm,
        spacing_mode=shear.spacing_mode,
        vs_provided_kg=vs_provided_kg,
        phi_vs_provided_kg=phi_vs_provided_kg,
        vn_kg=vn_kg,
        phi_vn_kg=phi_vn_kg,
        stirrup_spacing_cm=provided_spacing_cm,
        capacity_ratio=capacity_ratio,
        design_status=design_status,
        section_change_required=section_change_required,
        section_change_note=section_change_note,
        review_note=review_note,
    )


def calculate_negative_bending_design(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    negative_bending: NegativeBendingInput,
    design_inputs: BeamDesignInputSet,
) -> FlexuralDesignResults:
    material_results = calculate_material_properties(materials, design_inputs.material_settings)
    geometry_results = calculate_beam_geometry(
        geometry,
        design_inputs.positive_bending,
        design_inputs.negative_bending,
        design_inputs.shear,
        include_negative=True,
    )
    d_plus_cm = geometry_results.d_plus_cm
    d_minus_cm = geometry_results.d_minus_cm
    if d_minus_cm is None:
        raise ValueError("Negative bending geometry is not available for the selected beam type.")
    as_provided_cm2 = negative_bending.tension_reinforcement.total_area_cm2
    rho_provided = _safe_divide(as_provided_cm2, geometry.width_cm * d_minus_cm)
    a_cm = _safe_divide(
        as_provided_cm2 * materials.main_steel_yield_ksc,
        0.85 * materials.concrete_strength_ksc * geometry.width_cm,
    )
    c_cm = _safe_divide(a_cm, material_results.beta_1)
    dt_cm = (
        geometry.depth_cm
        - geometry.cover_cm
        - _diameter_cm(design_inputs.shear.stirrup_diameter_mm)
        - (_group_diameter_cm(negative_bending.tension_reinforcement.layer_1.group_a) / 2)
    )
    ety = _safe_divide(materials.main_steel_yield_ksc, material_results.es_ksc)
    et = _safe_divide(ECU * (dt_cm - c_cm), c_cm)
    phi = _calculate_flexural_phi(design_inputs.metadata.design_code, et, ety)
    ru_kg_per_cm2 = _safe_divide(
        negative_bending.factored_moment_kgm * 100,
        phi * geometry.width_cm * (d_minus_cm**2),
    )
    rho_required = _calculate_rho_required(
        materials.concrete_strength_ksc,
        materials.main_steel_yield_ksc,
        ru_kg_per_cm2,
    )
    rho_min = _calculate_rho_min(
        design_inputs.metadata.design_code,
        materials.concrete_strength_ksc,
        materials.main_steel_yield_ksc,
    )
    rho_max = _calculate_rho_max(
        design_inputs.metadata.design_code,
        materials.concrete_strength_ksc,
        materials.main_steel_yield_ksc,
        material_results.beta_1,
    )
    as_required_cm2 = rho_required * geometry.width_cm * d_minus_cm
    as_min_cm2 = rho_min * geometry.width_cm * d_plus_cm
    as_max_cm2 = rho_max * geometry.width_cm * d_minus_cm
    mn_kgm = as_provided_cm2 * materials.main_steel_yield_ksc * (d_plus_cm - (a_cm / 2)) / 100
    phi_mn_kgm = mn_kgm * phi
    ratio = _safe_divide(negative_bending.factored_moment_kgm, phi_mn_kgm)
    as_status = _calculate_as_status(rho_provided, rho_min, rho_max)
    ratio_status = "OK" if phi_mn_kgm >= negative_bending.factored_moment_kgm else "NOT OK"
    design_status = "PASS" if as_status == "OK" and ratio_status == "OK" else "FAIL"
    review_note = (
        "Negative-moment block currently uses d+ for As_min and Mn rather than d-. "
        "Manual engineering review is required before using this result for issued design documents."
    )

    return FlexuralDesignResults(
        phi=phi,
        ru_kg_per_cm2=ru_kg_per_cm2,
        rho_required=rho_required,
        as_required_cm2=as_required_cm2,
        as_provided_cm2=as_provided_cm2,
        rho_provided=rho_provided,
        rho_min=rho_min,
        rho_max=rho_max,
        as_min_cm2=as_min_cm2,
        as_max_cm2=as_max_cm2,
        as_status=as_status,
        a_cm=a_cm,
        c_cm=c_cm,
        dt_cm=dt_cm,
        ety=ety,
        et=et,
        mn_kgm=mn_kgm,
        phi_mn_kgm=phi_mn_kgm,
        ratio=ratio,
        ratio_status=ratio_status,
        design_status=design_status,
        review_note=review_note,
    )


def calculate_deflection_check(
    materials: MaterialPropertiesInput,
    geometry: BeamGeometryInput,
    positive_bending: PositiveBendingInput,
    negative_bending: NegativeBendingInput,
    deflection: DeflectionCheckInput,
) -> DeflectionCheckResults:
    return DeflectionCheckResults(
        status="Needs manual engineering review",
        note=(
            "Deflection logic has not been fully reconstructed into code yet. "
            "Use a separate checked procedure until this module is completed."
        ),
        verification_status=VerificationStatus.NEEDS_REVIEW,
    )


def validate_spacing_warnings(
    geometry: BeamGeometryInput,
    positive_bending: PositiveBendingInput,
    negative_bending: NegativeBendingInput,
    shear: ShearDesignInput,
    *,
    include_negative: bool,
) -> list[str]:
    warning_messages: list[str] = []
    spacing_groups: dict[str, ReinforcementSpacingResults] = {
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
    design_inputs: BeamDesignInputSet,
    *,
    include_negative: bool,
) -> list[str]:
    warning_messages: list[str] = []
    positive_results = calculate_positive_bending_design(materials, geometry, positive_bending, design_inputs)

    if positive_results.as_status != "OK":
        warning_messages.append(
            "Positive bending reinforcement does not satisfy the required reinforcement area limits."
        )

    if include_negative:
        negative_results = calculate_negative_bending_design(materials, geometry, negative_bending, design_inputs)
        if negative_results.as_status != "OK":
            warning_messages.append(
                "Negative bending reinforcement does not satisfy the required reinforcement area limits."
            )
    return warning_messages


def validate_shear_warnings(
    design_inputs: BeamDesignInputSet,
    shear_results: ShearDesignResults,
) -> list[str]:
    warning_messages: list[str] = []
    if shear_results.section_change_required and shear_results.section_change_note:
        warning_messages.append(shear_results.section_change_note)
    if shear_results.phi_vn_kg < design_inputs.shear.factored_shear_kg and not shear_results.section_change_required:
        warning_messages.append(
            "Shear strength is insufficient because the applied shear force exceeds the design shear capacity, V_u > phi V_n."
        )
    if shear_results.review_note:
        warning_messages.extend(note for note in shear_results.review_note.split(". ") if note)
    return [message if message.endswith(".") else f"{message}." for message in warning_messages]


def calculate_full_design_results(design_inputs: BeamDesignInputSet) -> BeamDesignResults:
    include_negative = design_inputs.has_negative_design
    material_results = calculate_material_properties(design_inputs.materials, design_inputs.material_settings)
    geometry_results = calculate_beam_geometry(
        design_inputs.geometry,
        design_inputs.positive_bending,
        design_inputs.negative_bending,
        design_inputs.shear,
        include_negative=include_negative,
    )
    positive_results = calculate_positive_bending_design(
        design_inputs.materials,
        design_inputs.geometry,
        design_inputs.positive_bending,
        design_inputs,
    )
    shear_results = calculate_shear_design(
        design_inputs.materials,
        design_inputs.geometry,
        design_inputs.shear,
        design_inputs,
    )
    negative_results = None
    if include_negative:
        negative_results = calculate_negative_bending_design(
            design_inputs.materials,
            design_inputs.geometry,
            design_inputs.negative_bending,
            design_inputs,
        )
    deflection_results = calculate_deflection_check(
        design_inputs.materials,
        design_inputs.geometry,
        design_inputs.positive_bending,
        design_inputs.negative_bending,
        design_inputs.deflection,
    )
    warnings = [
        *validate_spacing_warnings(
            design_inputs.geometry,
            design_inputs.positive_bending,
            design_inputs.negative_bending,
            design_inputs.shear,
            include_negative=include_negative,
        ),
        *validate_reinforcement_area_warnings(
            design_inputs.materials,
            design_inputs.geometry,
            design_inputs.positive_bending,
            design_inputs.negative_bending,
            design_inputs,
            include_negative=include_negative,
        ),
        *validate_shear_warnings(design_inputs, shear_results),
    ]
    review_flags = _build_review_flags(negative_results, deflection_results)
    overall_status, overall_note = _calculate_overall_assessment(
        design_inputs,
        geometry_results,
        positive_results,
        shear_results,
        negative_results,
        review_flags,
    )
    return BeamDesignResults(
        materials=material_results,
        beam_geometry=geometry_results,
        positive_bending=positive_results,
        shear=shear_results,
        negative_bending=negative_results,
        deflection=deflection_results,
        warnings=warnings,
        review_flags=review_flags,
        overall_status=overall_status,
        overall_note=overall_note,
    )


def _build_review_flags(
    negative_results: FlexuralDesignResults | None,
    deflection_results: DeflectionCheckResults,
) -> list[ReviewFlag]:
    review_flags: list[ReviewFlag] = []
    if negative_results is not None and negative_results.review_note:
        review_flags.append(
            ReviewFlag(
                title="Negative moment alignment",
                severity="warning",
                message=negative_results.review_note,
                verification_status=VerificationStatus.NEEDS_REVIEW,
            )
        )
    review_flags.append(
        ReviewFlag(
            title="Code compliance statement",
            severity="warning",
            message=(
                "The implemented flexural and shear expressions follow ACI-style equations, "
                "but the governing code clauses have not been fully audited in this repository."
            ),
            verification_status=VerificationStatus.NEEDS_REVIEW,
        )
    )
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
    shear_results: ShearDesignResults,
    negative_results: FlexuralDesignResults | None,
    review_flags: list[ReviewFlag],
) -> tuple[str, str]:
    strength_failures: list[str] = []
    if positive_results.ratio_status != "OK":
        strength_failures.append("Positive flexural strength does not satisfy M_u <= phi M_n.")
    if negative_results is not None and negative_results.ratio_status != "OK":
        strength_failures.append("Negative flexural strength does not satisfy M_u <= phi M_n.")
    if shear_results.phi_vn_kg < design_inputs.shear.factored_shear_kg:
        if shear_results.section_change_required and shear_results.section_change_note:
            strength_failures.append(shear_results.section_change_note)
        else:
            strength_failures.append("Shear strength does not satisfy V_u <= phi V_n.")
    if shear_results.nominal_vs_required_kg > shear_results.vs_max_kg:
        strength_failures.append("Required shear reinforcement exceeds the permitted shear steel contribution.")
    if strength_failures:
        return "FAIL", " ".join(strength_failures)

    requirement_issues: list[str] = []
    if positive_results.as_status != "OK":
        requirement_issues.append("Positive tension reinforcement does not satisfy the required A_s limits.")
    if negative_results is not None and negative_results.as_status != "OK":
        requirement_issues.append("Negative tension reinforcement does not satisfy the required A_s limits.")
    spacing_results = [
        geometry_results.positive_tension_spacing,
        geometry_results.positive_compression_spacing,
    ]
    if geometry_results.negative_tension_spacing is not None:
        spacing_results.append(geometry_results.negative_tension_spacing)
    if geometry_results.negative_compression_spacing is not None:
        spacing_results.append(geometry_results.negative_compression_spacing)
    if any(spacing_result.overall_status != "OK" for spacing_result in spacing_results):
        requirement_issues.append("One or more reinforcement layers do not satisfy the minimum clear spacing requirement.")
    if shear_results.review_note:
        requirement_issues.append(shear_results.review_note)
    if requirement_issues:
        return "DOES NOT MEET REQUIREMENTS", " ".join(requirement_issues)

    if review_flags:
        return "PASS WITH REVIEW", "Strength and detailing checks pass, but additional engineering review items remain open."
    return "PASS", "All current strength and detailing checks are satisfied."


def _calculate_beta_1(fc_prime_ksc: float) -> float:
    if 0 < fc_prime_ksc <= 280:
        return 0.85
    return max(0.65, 0.85 - (0.05 * (fc_prime_ksc - 280) / 70))


def _calculate_flexural_phi(design_code: DesignCode, et: float, ety: float) -> float:
    if math.isnan(et):
        return math.nan
    if design_code == DesignCode.ACI318_99:
        return 0.9
    if design_code == DesignCode.ACI318_11:
        if et < 0.002:
            return 0.75
        if et <= 0.005:
            return 0.75 + ((et - 0.002) * 0.5)
        return 0.9
    if design_code == DesignCode.ACI318_14:
        if et < ety:
            return 0.75
        if et <= 0.005:
            return 0.75 + ((0.15 / (0.005 - ety)) * (et - ety))
        return 0.9
    if et < ety:
        return 0.75
    if et <= ety + 0.003:
        return 0.75 + ((0.15 / ((ety + 0.003) - ety)) * (et - ety))
    return 0.9


def calculate_flexural_phi_value(design_code: DesignCode, et: float, ety: float) -> float:
    return _calculate_flexural_phi(design_code, et, ety)


def flexural_phi_chart_supported(design_code: DesignCode) -> bool:
    return design_code != DesignCode.ACI318_99


def flexural_phi_chart_points(design_code: DesignCode, ety: float) -> list[tuple[float, float]]:
    if design_code == DesignCode.ACI318_99:
        return []
    if design_code == DesignCode.ACI318_11:
        return [(0.0, 0.75), (0.002, 0.75), (0.005, 0.9), (0.006, 0.9)]
    if design_code == DesignCode.ACI318_14:
        transition_end = 0.005
        return [(0.0, 0.75), (ety, 0.75), (transition_end, 0.9), (max(0.006, transition_end + 0.001), 0.9)]
    transition_end = ety + 0.003
    return [(0.0, 0.75), (ety, 0.75), (transition_end, 0.9), (max(0.006, transition_end + 0.001), 0.9)]


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
    if not math.isfinite(required_spacing_cm):
        return increment_cm
    snapped_spacing_cm = math.floor(required_spacing_cm / increment_cm) * increment_cm
    if snapped_spacing_cm > 0:
        return snapped_spacing_cm
    return required_spacing_cm


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
    if design_code == DesignCode.ACI318_99:
        return 0.75 * 0.85 * (fc_prime_ksc / fy_ksc) * beta_1 * (6120 / (6120 + fy_ksc))
    if design_code in {DesignCode.ACI318_11, DesignCode.ACI318_14}:
        return 0.36 * beta_1 * (fc_prime_ksc / fy_ksc)
    return 0.32 * beta_1 * (fc_prime_ksc / fy_ksc)


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
