from __future__ import annotations

import math
from datetime import datetime

import streamlit as st

from core.theme import (
    apply_theme,
    capacity_ratio_html,
    capacity_ratio_legend_html,
    overall_status_card_html,
    status_text_html,
)
from core.utils import dataclass_to_dict, format_number, format_ratio

from .formulas import (
    AUTO_SHEAR_SPACING_INCREMENT_CM,
    calculate_default_ec_ksc,
    calculate_default_es_ksc,
    calculate_default_fr_ksc,
    calculate_full_design_results,
)
from .models import (
    BeamDesignInputSet,
    BeamGeometryInput,
    BeamType,
    DeflectionBeamType,
    DeflectionCheckInput,
    DesignCode,
    MaterialPropertiesInput,
    MaterialPropertyMode,
    MaterialPropertySetting,
    MaterialPropertySettings,
    NegativeBendingInput,
    PositiveBendingInput,
    ProjectMetadata,
    RebarGroupInput,
    RebarLayerInput,
    ReinforcementArrangementInput,
    ShearDesignInput,
    ShearSpacingMode,
    default_beam_design_inputs,
)
from .visualization import beam_section_specs, build_beam_section_svg, build_section_rebar_details, shared_drawing_transform
from .visualization import PhiFlexureChartState, build_flexural_phi_chart_svg


STEEL_GRADE_OPTIONS: list[object] = [2400, 3000, 4000, 5000, "Custom"]
BAR_DIAMETER_OPTIONS_WITH_EMPTY: list[object] = ["-", 6, 9, 10, 12, 16, 20, 25, 28, 32, 40, "Custom"]
BAR_DIAMETER_OPTIONS: list[object] = [6, 9, 10, 12, 16, 20, 25, 28, 32, 40, "Custom"]
PERSISTED_WORKSPACE_STATE_KEY = "_persisted_workspace_state"
LAST_RENDERED_PAGE_KEY = "_last_rendered_page"


@st.cache_data(show_spinner=False)
def load_default_inputs() -> BeamDesignInputSet:
    return default_beam_design_inputs()


def main() -> None:
    force_restore = st.session_state.get(LAST_RENDERED_PAGE_KEY) != "workspace"
    initialize_session_state(load_default_inputs(), force_restore=force_restore)
    st.session_state[LAST_RENDERED_PAGE_KEY] = "workspace"
    palette = apply_theme()

    left, right = st.columns([1.25, 1], gap="large")

    with left:
        st.markdown("<div class='workspace-panel'>", unsafe_allow_html=True)
        render_header()
        render_input_workspace()
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        try:
            inputs = build_inputs_from_state()
            results = calculate_full_design_results(inputs)
            st.session_state.current_design_inputs = inputs
            st.session_state.current_design_results = results
            render_summary_panel(inputs, results, palette)
        except ValueError as error:
            st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
            st.error(str(error))
            st.info("Adjust the reinforcement definition so that diameter and count are either both zero or both provided.")
            st.markdown("</div>", unsafe_allow_html=True)
    persist_session_state(load_default_inputs())


def initialize_session_state(default_inputs: BeamDesignInputSet, *, force_restore: bool = False) -> None:
    default_state = build_default_state(default_inputs)
    _restore_persisted_workspace_state(default_inputs, force_restore=force_restore)
    st.session_state.setdefault("project_date_auto_value", _current_timestamp_text())
    for key, value in default_state.items():
        st.session_state.setdefault(key, value)


def build_default_state(inputs: BeamDesignInputSet) -> dict[str, object]:
    state: dict[str, object] = {
        "beam_type": inputs.beam_type.value,
        "project_tag": inputs.metadata.tag,
        "project_name": inputs.metadata.project_name,
        "project_number": inputs.metadata.project_number,
        "project_engineer": inputs.metadata.engineer,
        "project_date_mode": "Auto",
        "project_date": inputs.metadata.design_date,
        "design_code": inputs.metadata.design_code.value,
        "fc_prime_ksc": inputs.materials.concrete_strength_ksc,
        "fy_grade_option": _steel_grade_option(inputs.materials.main_steel_yield_ksc),
        "fy_ksc": float(inputs.materials.main_steel_yield_ksc),
        "fvy_grade_option": _steel_grade_option(inputs.materials.shear_steel_yield_ksc),
        "fvy_ksc": float(inputs.materials.shear_steel_yield_ksc),
        "ec_mode": inputs.material_settings.ec.mode.value,
        "ec_manual_ksc": inputs.material_settings.ec.manual_value or calculate_default_ec_ksc(inputs.materials.concrete_strength_ksc),
        "es_mode": inputs.material_settings.es.mode.value,
        "es_manual_ksc": inputs.material_settings.es.manual_value or calculate_default_es_ksc(),
        "fr_mode": inputs.material_settings.fr.mode.value,
        "fr_manual_ksc": inputs.material_settings.fr.manual_value or calculate_default_fr_ksc(inputs.materials.concrete_strength_ksc),
        "width_cm": inputs.geometry.width_cm,
        "depth_cm": inputs.geometry.depth_cm,
        "cover_cm": inputs.geometry.cover_cm,
        "min_clear_spacing_cm": inputs.geometry.minimum_clear_spacing_cm,
        "positive_mu_kgm": inputs.positive_bending.factored_moment_kgm,
        "negative_mu_kgm": inputs.negative_bending.factored_moment_kgm,
        "vu_kg": inputs.shear.factored_shear_kg,
        "stirrup_diameter_option": _diameter_option(inputs.shear.stirrup_diameter_mm, allow_empty=False),
        "stirrup_diameter_mm": int(inputs.shear.stirrup_diameter_mm),
        "legs_per_plane": inputs.shear.legs_per_plane,
        "shear_spacing_mode": inputs.shear.spacing_mode.value,
        "shear_spacing_cm": inputs.shear.provided_spacing_cm,
        "deflection_beam_type": inputs.deflection.beam_type.value,
        "beam_type_factor_x": inputs.deflection.beam_type_factor_x,
        "span_length_m": inputs.deflection.span_length_m,
        "sustained_live_load_ratio": inputs.deflection.sustained_live_load_ratio,
        "midspan_dead_load_service_moment_kgm": inputs.deflection.midspan_dead_load_service_moment_kgm,
        "midspan_live_load_service_moment_kgm": inputs.deflection.midspan_live_load_service_moment_kgm,
        "support_dead_load_service_moment_kgm": inputs.deflection.support_dead_load_service_moment_kgm,
        "support_live_load_service_moment_kgm": inputs.deflection.support_live_load_service_moment_kgm,
        "immediate_deflection_limit_description": inputs.deflection.immediate_deflection_limit_description,
        "total_deflection_limit_description": inputs.deflection.total_deflection_limit_description,
    }

    for prefix, arrangement in {
        "pb_comp": inputs.positive_bending.compression_reinforcement,
        "pb_tens": inputs.positive_bending.tension_reinforcement,
        "nb_comp": inputs.negative_bending.compression_reinforcement,
        "nb_tens": inputs.negative_bending.tension_reinforcement,
    }.items():
        for layer_index, layer in enumerate(arrangement.layers(), start=1):
            state[f"{prefix}_layer_{layer_index}_group_a_diameter_option"] = _diameter_option(layer.group_a.diameter_mm, allow_empty=True)
            state[f"{prefix}_layer_{layer_index}_group_a_diameter"] = layer.group_a.diameter_mm or 0
            state[f"{prefix}_layer_{layer_index}_group_a_count"] = layer.group_a.count
            state[f"{prefix}_layer_{layer_index}_group_b_diameter_option"] = _diameter_option(layer.group_b.diameter_mm, allow_empty=True)
            state[f"{prefix}_layer_{layer_index}_group_b_diameter"] = layer.group_b.diameter_mm or 0
            state[f"{prefix}_layer_{layer_index}_group_b_count"] = layer.group_b.count
    return state


def reset_workspace(default_inputs: BeamDesignInputSet) -> None:
    st.session_state.project_date_auto_value = _current_timestamp_text()
    for key, value in build_default_state(default_inputs).items():
        st.session_state[key] = value
    persist_session_state(default_inputs)


def persist_session_state(default_inputs: BeamDesignInputSet) -> None:
    persisted_state: dict[str, object] = {}
    for key in _workspace_state_keys(default_inputs):
        if key in st.session_state:
            persisted_state[key] = st.session_state[key]
    st.session_state[PERSISTED_WORKSPACE_STATE_KEY] = persisted_state


def reset_material_property_settings() -> None:
    concrete_strength = float(st.session_state.fc_prime_ksc)
    st.session_state.ec_mode = MaterialPropertyMode.DEFAULT.value
    st.session_state.es_mode = MaterialPropertyMode.DEFAULT.value
    st.session_state.fr_mode = MaterialPropertyMode.DEFAULT.value
    st.session_state.ec_manual_ksc = calculate_default_ec_ksc(concrete_strength)
    st.session_state.es_manual_ksc = calculate_default_es_ksc()
    st.session_state.fr_manual_ksc = calculate_default_fr_ksc(concrete_strength)


def render_header() -> None:
    default_inputs = load_default_inputs()
    header_left, header_right = st.columns([1.2, 1], gap="medium")
    with header_left:
        st.markdown("<div class='hero-title'>Singly Reinforced Beam Analysis</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='hero-subtitle'>Standalone reinforced concrete beam design with live visualization, compact reporting, and transparent review flags.</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<span class='badge'>Code: {st.session_state.design_code}</span>"
            f"<span class='badge'>Beam Type: {st.session_state.beam_type}</span>"
            f"<span class='badge'>Default Setup: Simple Beam</span>",
            unsafe_allow_html=True,
        )
    with header_right:
        if st.button("Default", use_container_width=True):
            reset_workspace(default_inputs)
            st.rerun()
    st.markdown("<div class='app-shell'>", unsafe_allow_html=True)
    st.markdown(
        "<div class='small-note'>The application runs as a standalone design tool. Values stay in session while you navigate between pages and reset only when you press Default or restart the app.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def render_input_workspace() -> None:
    preview_inputs, preview_results = _preview_current_design_state()
    with st.expander("1. Project Info", expanded=True):
        project_left, project_right = st.columns(2, gap="medium")
        with project_left:
            st.text_input("Tag", key="project_tag", help="Beam tag or member mark from the project.")
            st.text_input("Project name", key="project_name")
            st.selectbox("Design code", options=[code.value for code in DesignCode], key="design_code")
        with project_right:
            st.text_input("Project number", key="project_number")
            st.text_input("Engineer", key="project_engineer")
            st.radio("Date", options=["Auto", "Manual"], horizontal=True, key="project_date_mode")
            if st.session_state.project_date_mode == "Manual":
                st.text_input("Date / time", key="project_date")
            else:
                st.caption(f"Current date / time: {st.session_state.project_date_auto_value}")

    with st.expander("2. Beam Type", expanded=True):
        st.radio(
            "Beam type",
            options=[beam_type.value for beam_type in BeamType],
            horizontal=True,
            key="beam_type",
            help="Simple Beam hides negative-moment design. Continuous Beam shows both positive and negative design workflows.",
        )
        st.caption("Simple Beam = positive-moment workflow only. Continuous Beam = positive and negative moment design.")

    with st.expander("3. Material Properties: f'c, fy, fvy", expanded=True):
        cols = st.columns(3, gap="medium")
        with cols[0]:
            st.number_input("f'c (ksc)", min_value=1.0, step=5.0, key="fc_prime_ksc", help="Concrete compressive strength.")
            _render_field_helper()
        with cols[1]:
            st.selectbox("fy (ksc)", options=STEEL_GRADE_OPTIONS, key="fy_grade_option", help="Main reinforcement yield strength.")
            _render_steel_grade_input("fy_grade_option", "fy_ksc", "fy custom (ksc)")
        with cols[2]:
            st.selectbox("fvy (ksc)", options=STEEL_GRADE_OPTIONS, key="fvy_grade_option", help="Shear reinforcement yield strength.")
            _render_steel_grade_input("fvy_grade_option", "fvy_ksc", "fvy custom (ksc)")

    with st.expander("4. Beam Geometry: b, h, covering", expanded=True):
        cols = st.columns(3, gap="medium")
        with cols[0]:
            st.number_input("b (cm)", min_value=1.0, step=1.0, key="width_cm")
            _render_field_helper()
        with cols[1]:
            st.number_input("h (cm)", min_value=1.0, step=1.0, key="depth_cm")
            _render_field_helper()
        with cols[2]:
            st.number_input("covering (cm)", min_value=0.0, step=0.5, key="cover_cm")
            _render_field_helper()
        spacing_cols = st.columns([1, 2], gap="medium")
        with spacing_cols[0]:
            st.number_input("min rebar spacing (cm)", min_value=0.1, step=0.1, key="min_clear_spacing_cm")
            _render_field_helper()

    with st.expander("5. Positive Moment Design", expanded=True):
        st.number_input("Mᵤ,positive (kg-m)", min_value=0.0, step=50.0, key="positive_mu_kgm")
        positive_tabs = st.tabs(
            [
                "Tension Reinforcement",
                "Compression Reinforcement",
            ]
        )
        with positive_tabs[0]:
            st.caption("Bottom reinforcement.")
            render_reinforcement_editor("pb_tens", "Tension Reinforcement", preview_inputs, preview_results, show_phi=True)
        with positive_tabs[1]:
            st.caption("Top reinforcement.")
            render_reinforcement_editor("pb_comp", "Compression Reinforcement", preview_inputs, preview_results, show_phi=False)

    if _selected_beam_type() == BeamType.CONTINUOUS:
        with st.expander("6. Negative Moment Design", expanded=True):
            st.number_input("Mᵤ,negative (kg-m)", min_value=0.0, step=50.0, key="negative_mu_kgm")
            negative_tabs = st.tabs(
                [
                    "Tension Reinforcement",
                    "Compression Reinforcement",
                ]
            )
            with negative_tabs[0]:
                st.caption("Top reinforcement.")
                render_reinforcement_editor("nb_tens", "Tension Reinforcement", preview_inputs, preview_results, show_phi=True)
            with negative_tabs[1]:
                st.caption("Bottom reinforcement.")
                render_reinforcement_editor("nb_comp", "Compression Reinforcement", preview_inputs, preview_results, show_phi=False)

    shear_section_label = "7. Shear Design" if _selected_beam_type() == BeamType.CONTINUOUS else "6. Shear Design"
    with st.expander(shear_section_label, expanded=True):
        _render_shear_header_feedback(preview_results)
        _render_shear_inputs()
        _render_shear_spacing_feedback()

def _render_shear_inputs() -> None:
    top_cols = st.columns(3, gap="medium")
    with top_cols[0]:
        st.markdown("<div class='input-field-label'>V<sub>u</sub> (kg)</div>", unsafe_allow_html=True)
        st.number_input("Vu (kg)", min_value=0.0, step=50.0, key="vu_kg", label_visibility="collapsed")
        _render_field_helper()
    with top_cols[1]:
        st.markdown("<div class='input-field-label'>Stirrup diameter (mm)</div>", unsafe_allow_html=True)
        st.selectbox(
            "Stirrup diameter (mm)",
            options=BAR_DIAMETER_OPTIONS,
            key="stirrup_diameter_option",
            label_visibility="collapsed",
        )
        _render_diameter_input("stirrup_diameter_option", "stirrup_diameter_mm", "Stirrup diameter custom (mm)", allow_empty=False)
    with top_cols[2]:
        st.markdown("<div class='input-field-label'>Legs per plane</div>", unsafe_allow_html=True)
        st.number_input("Legs per plane", min_value=1, step=1, key="legs_per_plane", label_visibility="collapsed")
        _render_field_helper()

    bottom_cols = st.columns([1.15, 1.85], gap="medium")
    with bottom_cols[0]:
        st.markdown("<div class='input-field-label'>Spacing mode</div>", unsafe_allow_html=True)
        st.radio(
            "Spacing mode",
            options=[mode.value for mode in ShearSpacingMode],
            key="shear_spacing_mode",
            horizontal=True,
            label_visibility="collapsed",
        )
    with bottom_cols[1]:
        st.markdown("<div class='input-field-label'>Spacing provided (cm)</div>", unsafe_allow_html=True)
        if st.session_state.shear_spacing_mode == ShearSpacingMode.MANUAL.value:
            st.number_input(
                "Spacing provided (cm)",
                min_value=0.1,
                step=AUTO_SHEAR_SPACING_INCREMENT_CM,
                key="shear_spacing_cm",
                label_visibility="collapsed",
            )
        else:
            st.caption(
                f"Auto selects a spacing not greater than the required spacing and rounds down to {AUTO_SHEAR_SPACING_INCREMENT_CM:.1f} cm steps."
            )


def render_reinforcement_editor(prefix: str, label: str, preview_inputs=None, preview_results=None, *, show_phi: bool = False) -> None:
    st.markdown(f"<div class='section-label'>{label}</div>", unsafe_allow_html=True)
    phi_note = _flexure_phi_note_for_prefix(prefix, preview_results) if show_phi else None
    if phi_note:
        st.markdown(
            "<div class='design-banner info'>"
            f"Current flexural &phi; factor = {phi_note}."
            "</div>",
            unsafe_allow_html=True,
        )
    as_total_note = _reinforcement_area_note_for_prefix(prefix, preview_inputs)
    if as_total_note:
        st.markdown(
            "<div class='design-banner info'>"
            f"{as_total_note}"
            "</div>",
            unsafe_allow_html=True,
        )
    if show_phi:
        for warning_note in _flexure_area_warnings_for_prefix(prefix, preview_inputs, preview_results):
            st.markdown(
                "<div class='design-banner fail'>"
                f"{warning_note}"
                "</div>",
                unsafe_allow_html=True,
            )
    spacing_results = _spacing_results_for_prefix(prefix, preview_results)
    for layer_index in range(1, 4):
        if layer_index > 1 and not _layer_has_any_bar_from_state(prefix, layer_index - 1):
            _reset_layer_state(prefix, layer_index)
            st.caption(f"Layer {layer_index}")
            st.info(f"Define Layer {layer_index - 1} first to enable Layer {layer_index}.")
            continue
        st.caption(f"Layer {layer_index}")
        cols = st.columns(3, gap="small")
        with cols[0]:
            st.markdown("<div class='input-field-label'>Corner Bar dia. (mm)</div>", unsafe_allow_html=True)
            st.selectbox(
                f"Layer {layer_index} Corner Bar dia. (mm)",
                options=BAR_DIAMETER_OPTIONS_WITH_EMPTY,
                key=f"{prefix}_layer_{layer_index}_group_a_diameter_option",
                label_visibility="collapsed",
            )
            _render_diameter_input(
                f"{prefix}_layer_{layer_index}_group_a_diameter_option",
                f"{prefix}_layer_{layer_index}_group_a_diameter",
                f"Layer {layer_index} Corner Bar custom dia. (mm)",
                allow_empty=True,
            )
        group_a_option = st.session_state[f"{prefix}_layer_{layer_index}_group_a_diameter_option"]
        st.session_state[f"{prefix}_layer_{layer_index}_group_a_count"] = 0 if group_a_option == "-" else 2
        with cols[1]:
            st.markdown("<div class='input-field-label'>Middle Bar dia. (mm)</div>", unsafe_allow_html=True)
            st.selectbox(
                f"Layer {layer_index} Middle Bar dia. (mm)",
                options=BAR_DIAMETER_OPTIONS_WITH_EMPTY,
                key=f"{prefix}_layer_{layer_index}_group_b_diameter_option",
                label_visibility="collapsed",
            )
            _render_diameter_input(
                f"{prefix}_layer_{layer_index}_group_b_diameter_option",
                f"{prefix}_layer_{layer_index}_group_b_diameter",
                f"Layer {layer_index} Middle Bar custom dia. (mm)",
                allow_empty=True,
            )
        with cols[2]:
            st.markdown("<div class='input-field-label'>Middle Bar count</div>", unsafe_allow_html=True)
            st.number_input(
                f"Layer {layer_index} Middle Bar count",
                min_value=0,
                step=1,
                key=f"{prefix}_layer_{layer_index}_group_b_count",
                label_visibility="collapsed",
            )
            _render_field_helper()
        if group_a_option != "-":
            _render_field_helper("Corner Bar is fixed at 2 bars per layer.")
        else:
            _render_field_helper()
        if st.session_state[f"{prefix}_layer_{layer_index}_group_a_count"] == 0 and st.session_state[f"{prefix}_layer_{layer_index}_group_b_count"] > 0:
            st.warning("Middle Bar requires Corner Bar in the same layer.")
        if spacing_results is not None:
            layer_spacing = spacing_results.layers()[layer_index - 1]
            if layer_spacing.status == "NOT OK":
                st.markdown(f"<div class='layer-inline-warning'>{layer_spacing.message}</div>", unsafe_allow_html=True)


def _preview_current_design_state():
    try:
        inputs = build_inputs_from_state()
        results = calculate_full_design_results(inputs)
        st.session_state.preview_design_inputs = inputs
        st.session_state.preview_design_results = results
    except ValueError:
        fallback_inputs = st.session_state.get("preview_design_inputs")
        fallback_results = st.session_state.get("preview_design_results")
        if fallback_inputs is not None and fallback_results is not None:
            return fallback_inputs, fallback_results
        fallback_inputs = st.session_state.get("current_design_inputs")
        fallback_results = st.session_state.get("current_design_results")
        if fallback_inputs is not None and fallback_results is not None:
            return fallback_inputs, fallback_results
        return None, None
    return inputs, results


def _spacing_results_for_prefix(prefix: str, preview_results):
    if preview_results is None:
        return None
    mapping = {
        "pb_comp": preview_results.beam_geometry.positive_compression_spacing,
        "pb_tens": preview_results.beam_geometry.positive_tension_spacing,
        "nb_comp": preview_results.beam_geometry.negative_compression_spacing,
        "nb_tens": preview_results.beam_geometry.negative_tension_spacing,
    }
    return mapping.get(prefix)


def _render_flexure_header_feedback(preview_inputs, preview_results, moment_case: str) -> None:
    return


def _flexure_phi_note_for_prefix(prefix: str, preview_results) -> str | None:
    if preview_results is None:
        return None
    if prefix.startswith("nb_"):
        if preview_results.negative_bending is None:
            return None
        return format_ratio(preview_results.negative_bending.phi, 3)
    return format_ratio(preview_results.positive_bending.phi, 3)


def _reinforcement_area_note_for_prefix(prefix: str, preview_inputs) -> str | None:
    total_area_cm2 = _reinforcement_area_from_state(prefix)
    return f"Current A<sub>s,total</sub> = {format_number(total_area_cm2)} cm<sup>2</sup>."


def _flexure_area_warnings_for_prefix(prefix: str, preview_inputs, preview_results) -> list[str]:
    if preview_inputs is None or preview_results is None:
        return []
    if prefix == "pb_tens":
        design_results = preview_results.positive_bending
    elif prefix == "nb_tens":
        design_results = preview_results.negative_bending
        if design_results is None:
            return []
    else:
        return []

    warnings: list[str] = []
    if design_results.as_provided_cm2 < design_results.as_min_cm2:
        warnings.append(
            f"Provided tension reinforcement area, A<sub>s,total</sub> = {format_number(design_results.as_provided_cm2)} cm<sup>2</sup>, "
            f"is less than the minimum required area, A<sub>s,min</sub> = {format_number(design_results.as_min_cm2)} cm<sup>2</sup>."
        )
    if (
        preview_inputs.metadata.design_code == DesignCode.ACI318_99
        and design_results.as_provided_cm2 > design_results.as_max_cm2
    ):
        warnings.append(
            f"Provided tension reinforcement area, A<sub>s,total</sub> = {format_number(design_results.as_provided_cm2)} cm<sup>2</sup>, "
            f"exceeds the maximum permitted area, A<sub>s,max</sub> = {format_number(design_results.as_max_cm2)} cm<sup>2</sup>."
        )
    return warnings


def _reinforcement_area_from_state(prefix: str) -> float:
    total_area_cm2 = 0.0
    for layer_index in range(1, 4):
        group_a_diameter_mm = _resolved_diameter_value(
            f"{prefix}_layer_{layer_index}_group_a_diameter_option",
            f"{prefix}_layer_{layer_index}_group_a_diameter",
            allow_empty=True,
        )
        if group_a_diameter_mm > 0:
            total_area_cm2 += _bar_area_cm2(group_a_diameter_mm) * 2
        group_b_diameter_mm = _resolved_diameter_value(
            f"{prefix}_layer_{layer_index}_group_b_diameter_option",
            f"{prefix}_layer_{layer_index}_group_b_diameter",
            allow_empty=True,
        )
        group_b_count = _int_state_value(f"{prefix}_layer_{layer_index}_group_b_count")
        if group_b_diameter_mm > 0 and group_b_count > 0:
            total_area_cm2 += _bar_area_cm2(group_b_diameter_mm) * group_b_count
    return total_area_cm2


def _layer_has_any_bar_from_state(prefix: str, layer_index: int) -> bool:
    group_a_diameter_mm = _resolved_diameter_value(
        f"{prefix}_layer_{layer_index}_group_a_diameter_option",
        f"{prefix}_layer_{layer_index}_group_a_diameter",
        allow_empty=True,
    )
    group_b_diameter_mm = _resolved_diameter_value(
        f"{prefix}_layer_{layer_index}_group_b_diameter_option",
        f"{prefix}_layer_{layer_index}_group_b_diameter",
        allow_empty=True,
    )
    group_b_count = _int_state_value(f"{prefix}_layer_{layer_index}_group_b_count")
    return group_a_diameter_mm > 0 or (group_b_diameter_mm > 0 and group_b_count > 0)


def _reset_layer_state(prefix: str, layer_index: int) -> None:
    st.session_state[f"{prefix}_layer_{layer_index}_group_a_diameter_option"] = "-"
    st.session_state[f"{prefix}_layer_{layer_index}_group_a_diameter"] = 0
    st.session_state[f"{prefix}_layer_{layer_index}_group_a_count"] = 0
    st.session_state[f"{prefix}_layer_{layer_index}_group_b_diameter_option"] = "-"
    st.session_state[f"{prefix}_layer_{layer_index}_group_b_diameter"] = 0
    st.session_state[f"{prefix}_layer_{layer_index}_group_b_count"] = 0


def _bar_area_cm2(diameter_mm: int) -> float:
    diameter_cm = diameter_mm / 10
    return math.pi * (diameter_cm**2) / 4


def _int_state_value(key: str) -> int:
    raw_value = st.session_state.get(key, 0)
    if raw_value in (None, ""):
        return 0
    return int(raw_value)


def _resolved_grade_value(option_key: str, value_key: str) -> float:
    selected = st.session_state.get(option_key)
    if selected == "Custom":
        return float(st.session_state.get(value_key, 0.0))
    return float(selected)


def _resolved_diameter_value(option_key: str, value_key: str, *, allow_empty: bool) -> int:
    selected = st.session_state.get(option_key)
    if selected == "Custom":
        return _int_state_value(value_key)
    if allow_empty and selected == "-":
        return 0
    return int(selected)


def _render_shear_header_feedback(preview_results) -> None:
    if preview_results is None:
        return
    shear = preview_results.shear
    st.markdown(
        "<div class='design-banner info'>"
        f"Current shear &phi; factor = {format_ratio(shear.phi, 3)}."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='design-banner info'>"
        f"Av = {format_number(shear.av_cm2)} cm<sup>2</sup> | "
        f"Av,min = {format_number(shear.av_min_cm2)} cm<sup>2</sup>."
        "</div>",
        unsafe_allow_html=True,
    )
    if shear.av_cm2 < shear.av_min_cm2:
        if st.session_state.design_code == DesignCode.ACI318_19.value:
            vc_action = "Vc is reduced using this factor." if shear.size_effect_applied else "Vc is unchanged because the factor is 1.000."
            st.markdown(
                "<div class='design-banner fail'>"
                f"ACI 318-19 size effect check: Av &lt; Av,min, so &lambda;<sub>s</sub> = {format_ratio(shear.size_effect_factor, 3)}. "
                f"{vc_action}"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div class='design-banner fail'>"
                "Av &lt; Av,min."
                "</div>",
                unsafe_allow_html=True,
            )
    if shear.section_change_required and shear.section_change_note:
        st.markdown(
            "<div class='design-banner fail'>"
            f"{shear.section_change_note}"
            "</div>",
            unsafe_allow_html=True,
        )


def _render_shear_spacing_feedback() -> None:
    try:
        inputs = build_inputs_from_state()
        results = calculate_full_design_results(inputs)
    except ValueError:
        st.caption("Complete the current input set to preview shear spacing limits.")
        return

    shear = results.shear
    min_spacing_cm = AUTO_SHEAR_SPACING_INCREMENT_CM
    upper_limit_cm = shear.required_spacing_cm
    if shear.spacing_mode == ShearSpacingMode.AUTO:
        st.info(
            f"Auto selected spacing = {format_number(shear.provided_spacing_cm)} cm "
            f"(required spacing <= {format_number(upper_limit_cm)} cm)."
        )
        return

    st.caption(
        f"Manual spacing range used by this app: {format_number(min_spacing_cm)} cm to "
        f"{format_number(upper_limit_cm)} cm."
    )
    if shear.provided_spacing_cm < min_spacing_cm:
        st.warning(
            f"Provided spacing {format_number(shear.provided_spacing_cm)} cm is below the current minimum "
            f"input range of {format_number(min_spacing_cm)} cm."
        )
    elif shear.provided_spacing_cm > upper_limit_cm:
        st.warning(
            f"Provided spacing {format_number(shear.provided_spacing_cm)} cm exceeds the required maximum "
            f"spacing of {format_number(upper_limit_cm)} cm."
        )
    else:
        st.success(f"Provided spacing {format_number(shear.provided_spacing_cm)} cm is within the current required range.")


def render_summary_panel(inputs: BeamDesignInputSet, results, palette) -> None:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    summary_section_number = 8 if inputs.has_negative_design else 7
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;align-items:center;gap:1rem;'>"
        f"<div><div class='hero-title' style='font-size:1.25rem;'>{summary_section_number}. Overall Summary</div>"
        f"<div class='hero-subtitle'>Live results update with every input change.</div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    section_specs = beam_section_specs(inputs)
    drawing_transform = shared_drawing_transform(inputs)
    section_columns = st.columns(len(section_specs), gap="medium")
    for column, (title, moment_case) in zip(section_columns, section_specs):
        with column:
            st.markdown(f"<div class='section-label'>{title} Section</div>", unsafe_allow_html=True)
            st.markdown(build_beam_section_svg(inputs, palette, moment_case, transform=drawing_transform), unsafe_allow_html=True)
            rebar_details = build_section_rebar_details(inputs, moment_case, results.shear.provided_spacing_cm)
            st.markdown(_section_rebar_detail_html(rebar_details), unsafe_allow_html=True)
    render_key_metrics(inputs, results, palette)
    render_warnings_and_flags(results)
    st.markdown("</div>", unsafe_allow_html=True)


def render_key_metrics(inputs: BeamDesignInputSet, results, palette) -> None:
    st.markdown(capacity_ratio_legend_html(), unsafe_allow_html=True)
    positive_moment_metrics = [
        ("M<sub>u</sub> / &phi;M<sub>n</sub>", capacity_ratio_html(results.positive_bending.ratio), "Moment capacity ratio"),
        ("A<sub>s,req</sub>", format_number(results.positive_bending.as_required_cm2), "cm<sup>2</sup>"),
        ("A<sub>s,prov</sub>", format_number(results.positive_bending.as_provided_cm2), results.positive_bending.as_status),
        (
            "A<sub>s,min</sub> / A<sub>s,max</sub>",
            f"{format_number(results.positive_bending.as_min_cm2)} / {format_number(results.positive_bending.as_max_cm2)}",
            "cm<sup>2</sup>",
        ),
        ("&rho;", format_ratio(results.positive_bending.rho_provided), "Provided reinforcement ratio"),
        ("&phi;M<sub>n</sub>", format_number(results.positive_bending.phi_mn_kgm), results.positive_bending.ratio_status),
    ]
    negative_moment_metrics: list[tuple[str, object, str]] = []
    if inputs.has_negative_design and results.negative_bending is not None:
        negative_moment_metrics = [
            ("M<sub>u</sub> / &phi;M<sub>n</sub>", capacity_ratio_html(results.negative_bending.ratio), "Moment capacity ratio"),
            ("A<sub>s,req</sub>", format_number(results.negative_bending.as_required_cm2), "cm<sup>2</sup>"),
            ("A<sub>s,prov</sub>", format_number(results.negative_bending.as_provided_cm2), results.negative_bending.as_status),
            (
                "A<sub>s,min</sub> / A<sub>s,max</sub>",
                f"{format_number(results.negative_bending.as_min_cm2)} / {format_number(results.negative_bending.as_max_cm2)}",
                "cm<sup>2</sup>",
            ),
            ("&rho;", format_ratio(results.negative_bending.rho_provided), "Provided reinforcement ratio"),
            ("&phi;M<sub>n</sub>", format_number(results.negative_bending.phi_mn_kgm), results.negative_bending.ratio_status),
        ]
    shear_metrics = [
        ("V<sub>u</sub> / &phi;V<sub>n</sub>", capacity_ratio_html(results.shear.capacity_ratio), "Shear capacity ratio"),
        ("V<sub>u</sub>", format_number(inputs.shear.factored_shear_kg), "kg"),
        ("V<sub>n</sub>", format_number(results.shear.vn_kg), "kg"),
        ("&phi;V<sub>n</sub>", format_number(results.shear.phi_vn_kg), results.shear.design_status),
        ("&phi;V<sub>c</sub>", format_number(results.shear.phi_vc_kg), "kg"),
        ("&phi;V<sub>s</sub>", format_number(results.shear.phi_vs_provided_kg), f"{results.shear.spacing_mode.value} spacing"),
        (
            "s<sub>stirrup</sub>",
            format_number(results.shear.provided_spacing_cm),
            f"{results.shear.spacing_mode.value} | s<sub>req</sub> <= {format_number(results.shear.required_spacing_cm)} cm",
        ),
        ("Spacing check", results.beam_geometry.positive_tension_spacing.overall_status, "Positive tension layers"),
    ]

    positive_chart_html = build_flexural_phi_chart_svg(
        palette,
        PhiFlexureChartState(
            title="Positive Moment Flexural φ",
            design_code=inputs.metadata.design_code,
            et=results.positive_bending.et,
            ety=results.positive_bending.ety,
            phi=results.positive_bending.phi,
        ),
    )
    _render_metric_group("Positive Moment", positive_moment_metrics, palette, extra_html=positive_chart_html)
    if negative_moment_metrics:
        negative_chart_html = build_flexural_phi_chart_svg(
            palette,
            PhiFlexureChartState(
                title="Negative Moment Flexural φ",
                design_code=inputs.metadata.design_code,
                et=results.negative_bending.et,
                ety=results.negative_bending.ety,
                phi=results.negative_bending.phi,
            ),
        )
        _render_metric_group("Negative Moment", negative_moment_metrics, palette, extra_html=negative_chart_html)
    _render_metric_group("Shear", shear_metrics, palette)
    overall_label = results.overall_status
    if overall_label == "DOES NOT MEET REQUIREMENTS":
        overall_label = "DOES NOT MEET DESIGN REQUIREMENTS"
    st.markdown(overall_status_card_html(overall_label, "", palette), unsafe_allow_html=True)


def _render_metric_group(title: str, metrics: list[tuple[str, object, str]], palette, extra_html: str = "") -> None:
    st.markdown(f"<div class='summary-group-title'>{title}</div>", unsafe_allow_html=True)
    for row_start in range(0, len(metrics), 3):
        row_metrics = metrics[row_start : row_start + 3]
        columns = st.columns(3, gap="small")
        for index, column in enumerate(columns):
            if index >= len(row_metrics):
                continue
            label, value, note = row_metrics[index]
            display_value = value
            if isinstance(value, str):
                normalized = value.upper()
                if normalized in {"PASS", "FAIL", "PASS WITH REVIEW", "OK", "DOES NOT MEET REQUIREMENTS"} or "NOT OK" in normalized:
                    display_value = status_text_html(value, palette)
            column.markdown(
                f"<div class='metric-card'><div class='metric-label'>{label}</div>"
                f"<div class='metric-value'>{display_value}</div>"
                f"<div class='metric-note'>{note}</div></div>",
                unsafe_allow_html=True,
            )
    if extra_html:
        st.markdown(extra_html, unsafe_allow_html=True)


def render_flexural_phi_summary(inputs: BeamDesignInputSet, results, palette) -> None:
    st.markdown("<div class='summary-group-title'>Flexural φ-Strain</div>", unsafe_allow_html=True)
    chart_states = [
        PhiFlexureChartState(
            title="Positive Moment Flexural φ",
            design_code=inputs.metadata.design_code,
            et=results.positive_bending.et,
            ety=results.positive_bending.ety,
            phi=results.positive_bending.phi,
        )
    ]
    if inputs.has_negative_design and results.negative_bending is not None:
        chart_states.append(
            PhiFlexureChartState(
                title="Negative Moment Flexural φ",
                design_code=inputs.metadata.design_code,
                et=results.negative_bending.et,
                ety=results.negative_bending.ety,
                phi=results.negative_bending.phi,
            )
        )

    chart_columns = st.columns(len(chart_states), gap="medium")
    for column, chart_state in zip(chart_columns, chart_states):
        with column:
            st.markdown(build_flexural_phi_chart_svg(palette, chart_state), unsafe_allow_html=True)


def render_warnings_and_flags(results) -> None:
    summary_tabs = st.tabs(["Warnings", "Review Flags", "Raw Results"])
    with summary_tabs[0]:
        if not results.warnings:
            st.success("No immediate reinforcement or spacing warnings.")
        for warning in results.warnings:
            st.warning(warning)
    with summary_tabs[1]:
        for flag in results.review_flags:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>{flag.title}</div>"
                f"<div class='metric-value' style='font-size:0.95rem'>{flag.message}</div>"
                f"<div class='metric-note'>{flag.severity.title()} | {flag.verification_status.value}</div></div>",
                unsafe_allow_html=True,
            )
    with summary_tabs[2]:
        st.json(dataclass_to_dict(results), expanded=False)


def build_inputs_from_state() -> BeamDesignInputSet:
    return BeamDesignInputSet(
        beam_type=BeamType(st.session_state.beam_type),
        metadata=ProjectMetadata(
            design_code=DesignCode(st.session_state.design_code),
            tag=str(st.session_state.project_tag),
            project_name=str(st.session_state.project_name),
            project_number=str(st.session_state.project_number),
            engineer=str(st.session_state.project_engineer),
            design_date=_resolved_project_date(),
        ),
        materials=MaterialPropertiesInput(
            concrete_strength_ksc=float(st.session_state.fc_prime_ksc),
            main_steel_yield_ksc=_resolved_grade_value("fy_grade_option", "fy_ksc"),
            shear_steel_yield_ksc=_resolved_grade_value("fvy_grade_option", "fvy_ksc"),
        ),
        material_settings=MaterialPropertySettings(
            ec=MaterialPropertySetting(
                mode=MaterialPropertyMode(st.session_state.ec_mode),
                manual_value=float(st.session_state.ec_manual_ksc),
            ),
            es=MaterialPropertySetting(
                mode=MaterialPropertyMode(st.session_state.es_mode),
                manual_value=float(st.session_state.es_manual_ksc),
            ),
            fr=MaterialPropertySetting(
                mode=MaterialPropertyMode(st.session_state.fr_mode),
                manual_value=float(st.session_state.fr_manual_ksc),
            ),
        ),
        geometry=BeamGeometryInput(
            width_cm=float(st.session_state.width_cm),
            depth_cm=float(st.session_state.depth_cm),
            cover_cm=float(st.session_state.cover_cm),
            minimum_clear_spacing_cm=float(st.session_state.min_clear_spacing_cm),
        ),
        positive_bending=PositiveBendingInput(
            factored_moment_kgm=float(st.session_state.positive_mu_kgm),
            compression_reinforcement=_build_arrangement_from_state("pb_comp"),
            tension_reinforcement=_build_arrangement_from_state("pb_tens"),
        ),
        shear=ShearDesignInput(
            factored_shear_kg=float(st.session_state.vu_kg),
            stirrup_diameter_mm=_resolved_diameter_value("stirrup_diameter_option", "stirrup_diameter_mm", allow_empty=False),
            legs_per_plane=int(st.session_state.legs_per_plane),
            spacing_mode=ShearSpacingMode(st.session_state.shear_spacing_mode),
            provided_spacing_cm=float(st.session_state.shear_spacing_cm),
        ),
        negative_bending=NegativeBendingInput(
            factored_moment_kgm=float(st.session_state.negative_mu_kgm),
            compression_reinforcement=_build_arrangement_from_state("nb_comp"),
            tension_reinforcement=_build_arrangement_from_state("nb_tens"),
        ),
        deflection=DeflectionCheckInput(
            beam_type=DeflectionBeamType(st.session_state.deflection_beam_type),
            beam_type_factor_x=float(st.session_state.beam_type_factor_x),
            span_length_m=float(st.session_state.span_length_m),
            sustained_live_load_ratio=float(st.session_state.sustained_live_load_ratio),
            midspan_dead_load_service_moment_kgm=float(st.session_state.midspan_dead_load_service_moment_kgm),
            midspan_live_load_service_moment_kgm=float(st.session_state.midspan_live_load_service_moment_kgm),
            support_dead_load_service_moment_kgm=float(st.session_state.support_dead_load_service_moment_kgm),
            support_live_load_service_moment_kgm=float(st.session_state.support_live_load_service_moment_kgm),
            immediate_deflection_limit_description=str(st.session_state.immediate_deflection_limit_description),
            total_deflection_limit_description=str(st.session_state.total_deflection_limit_description),
        ),
    )


def _build_arrangement_from_state(prefix: str) -> ReinforcementArrangementInput:
    layers: list[RebarLayerInput] = []
    for layer_index in range(1, 4):
        group_a_diameter_value = _resolved_diameter_value(
            f"{prefix}_layer_{layer_index}_group_a_diameter_option",
            f"{prefix}_layer_{layer_index}_group_a_diameter",
            allow_empty=True,
        )
        group_a_diameter = group_a_diameter_value or None
        group_a_count = 2 if group_a_diameter is not None else 0
        layers.append(
            RebarLayerInput(
                group_a=RebarGroupInput(
                    diameter_mm=group_a_diameter,
                    count=group_a_count,
                ),
                group_b=RebarGroupInput(
                    diameter_mm=_resolved_diameter_value(
                        f"{prefix}_layer_{layer_index}_group_b_diameter_option",
                        f"{prefix}_layer_{layer_index}_group_b_diameter",
                        allow_empty=True,
                    )
                    or None,
                    count=int(st.session_state[f"{prefix}_layer_{layer_index}_group_b_count"]),
                ),
            )
        )
    return ReinforcementArrangementInput(layer_1=layers[0], layer_2=layers[1], layer_3=layers[2])


def _selected_beam_type() -> BeamType:
    return BeamType(st.session_state.beam_type)


def _resolved_project_date() -> str:
    if st.session_state.project_date_mode == "Auto":
        return str(st.session_state.project_date_auto_value)
    return str(st.session_state.project_date)


def _current_timestamp_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _workspace_state_keys(default_inputs: BeamDesignInputSet) -> set[str]:
    return {"project_date_auto_value", *build_default_state(default_inputs).keys()}


def _restore_persisted_workspace_state(default_inputs: BeamDesignInputSet, *, force_restore: bool) -> None:
    persisted_state = st.session_state.get(PERSISTED_WORKSPACE_STATE_KEY)
    if not isinstance(persisted_state, dict):
        return
    for key in _workspace_state_keys(default_inputs):
        if key in persisted_state and (force_restore or key not in st.session_state):
            st.session_state[key] = persisted_state[key]


def _section_rebar_detail_html(details) -> str:
    top_lines = "".join(f"<div class='rebar-detail-line'>{line}</div>" for line in details.top_lines)
    bottom_lines = "".join(f"<div class='rebar-detail-line'>{line}</div>" for line in details.bottom_lines)
    return (
        "<div class='metric-card rebar-detail-card'>"
        "<div class='rebar-detail-row'><div class='metric-label'>Top Rebar</div>"
        f"<div class='rebar-detail-value'>{top_lines}</div></div>"
        "<div class='rebar-detail-row'><div class='metric-label'>Bottom Rebar</div>"
        f"<div class='rebar-detail-value'>{bottom_lines}</div></div>"
        "<div class='rebar-detail-row'><div class='metric-label'>Stirrup</div>"
        f"<div class='rebar-detail-value'><div class='rebar-detail-line'>{details.stirrup_line}</div></div></div>"
        "</div>"
    )


def _steel_grade_option(value: float) -> object:
    integer_value = int(round(value))
    if integer_value in {2400, 3000, 4000, 5000}:
        return integer_value
    return "Custom"


def _render_steel_grade_input(option_key: str, value_key: str, custom_label: str) -> None:
    selected = st.session_state[option_key]
    if selected == "Custom":
        st.number_input(custom_label, min_value=0.1, step=100.0, key=value_key)
        _render_field_helper("Custom value")
        return
    st.session_state[value_key] = float(selected)
    _render_field_helper(f"Selected value: {int(selected)} ksc")


def _diameter_option(value: int | None, *, allow_empty: bool) -> object:
    if value in {6, 9, 10, 12, 16, 20, 25, 28, 32, 40}:
        return value
    if allow_empty and (value is None or value == 0):
        return "-"
    return "Custom"


def _render_diameter_input(option_key: str, value_key: str, custom_label: str, *, allow_empty: bool) -> None:
    selected = st.session_state[option_key]
    if selected == "Custom":
        st.number_input(custom_label, min_value=1, step=1, key=value_key)
        _render_field_helper("Custom value")
        return
    if allow_empty and selected == "-":
        st.session_state[value_key] = 0
        _render_field_helper("No bar selected")
        return
    st.session_state[value_key] = int(selected)
    _render_field_helper(f"Selected value: {int(selected)} mm")


def _render_field_helper(text: str = "") -> None:
    helper_class = "field-helper" if text else "field-helper blank"
    content = text if text else "&nbsp;"
    st.markdown(f"<div class='{helper_class}'>{content}</div>", unsafe_allow_html=True)

