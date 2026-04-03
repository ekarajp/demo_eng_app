from __future__ import annotations

import math
from textwrap import dedent
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from design.deflection import (
    AllowableDeflectionPreset,
    DeflectionCodeVersion,
    DeflectionIeMethod,
    DeflectionMemberType,
    DeflectionSupportCondition,
)
from design.deflection.deflection_report import deflection_workspace_summary_lines
from design.torsion import TorsionDemandType, TorsionDesignCode, TorsionDesignInput
from design.torsion.torsion_report import torsion_workspace_summary_lines
from core.theme import (
    LIGHT_THEME,
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
    BeamBehaviorMode,
    BeamDesignInputSet,
    BeamGeometryInput,
    BeamType,
    DemandInputMode,
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
    SimpleSupportBendingInput,
    default_beam_design_inputs,
)
from .visualization import (
    available_moment_cases,
    beam_section_specs,
    build_beam_section_svg,
    build_section_rebar_details,
    shared_drawing_transform,
    torsion_bar_drawable_capacity,
    torsion_bar_spacing_warning,
)
from .visualization import PhiFlexureChartState, build_flexural_phi_chart_svg


STEEL_GRADE_OPTIONS: list[object] = [2400, 3000, 4000, 5000, "Custom"]
BAR_DIAMETER_OPTIONS_WITH_EMPTY: list[object] = ["-", 6, 9, 10, 12, 16, 20, 25, 28, 32, 40, "Custom"]
BAR_DIAMETER_OPTIONS: list[object] = [6, 9, 10, 12, 16, 20, 25, 28, 32, 40, "Custom"]
PERSISTED_WORKSPACE_STATE_KEY = "_persisted_workspace_state"
LAST_RENDERED_PAGE_KEY = "_last_rendered_page"
TORSION_INPUT_BACKUP_KEY = "_torsion_input_backup"
DEFLECTION_DEFAULTS_VERSION_KEY = "_deflection_defaults_version"
DEFLECTION_DEFAULTS_VERSION = 3
DEFLECTION_FIRST_ENABLE_KEY = "_deflection_first_enable_applied"
CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY = "_continuous_negative_defaults_applied"
NEGATIVE_REBAR_INPUT_BACKUP_KEY = "_negative_rebar_input_backup"
DEFLECTION_IE_METHOD_BACKUP_KEY = "_deflection_ie_method_backup"
DEFLECTION_SUPPORT_INPUT_BACKUP_KEY = "_deflection_support_input_backup"
DEFLECTION_SUPPORT_INPUT_VISIBLE_KEY = "_deflection_support_input_visible"
NORMAL_WEIGHT_CONCRETE_UNIT_WEIGHT_KGF_PER_M3 = 2400.0
DEFLECTION_SUPPORT_MOMENT_MODE_OPTIONS = ("Auto", "Manual")
TORSION_DEMAND_TYPE_INFO_TEXT = (
    "Use 'equilibrium torsion' when torsion is required to maintain static equilibrium of the member "
    "or structural system.\n\n"
    "Use 'compatibility torsion' when torsion arises primarily from deformation compatibility in an "
    "indeterminate structure and is not essential to overall equilibrium.\n\n"
    "Therefore, if the torsion type is uncertain, 'equilibrium torsion' should be selected, as it is "
    "the safer and more conservative design assumption."
)
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
        render_input_workspace_extended()
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
    _initialize_deflection_defaults_once(default_state)
    st.session_state.setdefault(DEFLECTION_FIRST_ENABLE_KEY, bool(st.session_state.get("consider_deflection", False)))
    st.session_state.setdefault(CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY, False)


def build_default_state(inputs: BeamDesignInputSet) -> dict[str, object]:
    state: dict[str, object] = {
        "beam_type": inputs.beam_type.value,
        "include_cantilever_span": inputs.include_cantilever_span,
        "beam_behavior_mode": inputs.beam_behavior_mode.value,
        "auto_beam_behavior_threshold_percent": inputs.auto_beam_behavior_threshold_ratio * 100.0,
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
        "support_mu_mode": inputs.simple_support_bending.moment_mode.value,
        "support_mu_kgm": inputs.simple_support_bending.factored_moment_kgm,
        "negative_mu_kgm": inputs.negative_bending.factored_moment_kgm,
        "vu_kg": inputs.shear.factored_shear_kg,
        "support_vu_kg": inputs.shear.resolved_support_factored_shear_kg,
        "span_vu_mode": inputs.shear.span_region_mode.value,
        "span_vu_kg": inputs.shear.resolved_span_region_factored_shear_kg,
        "span_vu_position_ratio": inputs.shear.span_region_relative_position,
        "cantilever_vu_kg": inputs.shear.resolved_cantilever_factored_shear_kg,
        "stirrup_diameter_option": _diameter_option(inputs.shear.stirrup_diameter_mm, allow_empty=False),
        "stirrup_diameter_mm": int(inputs.shear.stirrup_diameter_mm),
        "legs_per_plane": inputs.shear.legs_per_plane,
        "shear_spacing_mode": inputs.shear.spacing_mode.value,
        "shear_spacing_cm": inputs.shear.provided_spacing_cm,
        "include_torsion_design": inputs.torsion.enabled,
        "torsion_tu_kgfm": inputs.torsion.factored_torsion_kgfm,
        "torsion_demand_type": inputs.torsion.demand_type.value,
        "torsion_longitudinal_diameter_option": _diameter_option(inputs.torsion.provided_longitudinal_bar_diameter_mm, allow_empty=True),
        "torsion_longitudinal_diameter_mm": int(inputs.torsion.provided_longitudinal_bar_diameter_mm or 0),
        "torsion_longitudinal_fy_grade_option": _steel_grade_option(inputs.torsion.provided_longitudinal_bar_fy_ksc),
        "torsion_longitudinal_fy_ksc": float(inputs.torsion.provided_longitudinal_bar_fy_ksc),
        "torsion_longitudinal_count": inputs.torsion.provided_longitudinal_bar_count,
        "consider_deflection": inputs.consider_deflection,
        "deflection_design_code": inputs.deflection.design_code.value,
        "deflection_member_type": inputs.deflection.member_type.value,
        "deflection_support_condition": inputs.deflection.support_condition.value,
        "deflection_ie_method": inputs.deflection.ie_method.value,
        "deflection_allowable_limit_preset": inputs.deflection.allowable_limit_preset.value,
        "deflection_allowable_limit_custom_denominator": inputs.deflection.allowable_limit_custom_denominator or 500,
        "deflection_long_term_factor_x": inputs.deflection.long_term_factor_x,
        "deflection_service_dead_load_kgf_per_m": inputs.deflection.service_dead_load_kgf_per_m,
        "deflection_service_live_load_kgf_per_m": inputs.deflection.service_live_load_kgf_per_m,
        "deflection_additional_sustained_load_kgf_per_m": inputs.deflection.additional_sustained_load_kgf_per_m,
        "deflection_sustained_live_load_ratio": inputs.deflection.sustained_live_load_ratio,
        "deflection_support_moment_mode": "Auto",
        "deflection_support_dead_load_service_moment_kgm": inputs.deflection.support_dead_load_service_moment_kgm,
        "deflection_support_live_load_service_moment_kgm": inputs.deflection.support_live_load_service_moment_kgm,
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
        "sb_comp": inputs.simple_support_bending.compression_reinforcement,
        "sb_tens": inputs.simple_support_bending.tension_reinforcement,
        "nb_comp": inputs.negative_bending.compression_reinforcement,
        "nb_tens": inputs.negative_bending.tension_reinforcement,
        "cb_comp": inputs.cantilever_negative_bending.compression_reinforcement,
        "cb_tens": inputs.cantilever_negative_bending.tension_reinforcement,
    }.items():
        for layer_index, layer in enumerate(arrangement.layers(), start=1):
            state[f"{prefix}_layer_{layer_index}_group_a_diameter_option"] = _diameter_option(layer.group_a.diameter_mm, allow_empty=True)
            state[f"{prefix}_layer_{layer_index}_group_a_diameter"] = layer.group_a.diameter_mm or 0
            state[f"{prefix}_layer_{layer_index}_group_a_count"] = layer.group_a.count
            state[f"{prefix}_layer_{layer_index}_group_b_diameter_option"] = _diameter_option(layer.group_b.diameter_mm, allow_empty=True)
            state[f"{prefix}_layer_{layer_index}_group_b_diameter"] = layer.group_b.diameter_mm or 0
            state[f"{prefix}_layer_{layer_index}_group_b_count"] = layer.group_b.count
    for prefix in ("nb_tens", "nb_comp"):
        state[f"{prefix}_layer_1_group_a_diameter_option"] = 12
        state[f"{prefix}_layer_1_group_a_diameter"] = 12
        state[f"{prefix}_layer_1_group_a_count"] = 2
        state[f"{prefix}_layer_1_group_b_diameter_option"] = "-"
        state[f"{prefix}_layer_1_group_b_diameter"] = 0
        state[f"{prefix}_layer_1_group_b_count"] = 0
        for layer_index in (2, 3):
            state[f"{prefix}_layer_{layer_index}_group_a_diameter_option"] = "-"
            state[f"{prefix}_layer_{layer_index}_group_a_diameter"] = 0
            state[f"{prefix}_layer_{layer_index}_group_a_count"] = 0
            state[f"{prefix}_layer_{layer_index}_group_b_diameter_option"] = "-"
            state[f"{prefix}_layer_{layer_index}_group_b_diameter"] = 0
            state[f"{prefix}_layer_{layer_index}_group_b_count"] = 0
    state["cantilever_negative_mu_kgm"] = inputs.cantilever_negative_bending.factored_moment_kgm
    for prefix in ("cb_tens", "cb_comp"):
        state[f"{prefix}_layer_1_group_a_diameter_option"] = 12
        state[f"{prefix}_layer_1_group_a_diameter"] = 12
        state[f"{prefix}_layer_1_group_a_count"] = 2
        state[f"{prefix}_layer_1_group_b_diameter_option"] = "-"
        state[f"{prefix}_layer_1_group_b_diameter"] = 0
        state[f"{prefix}_layer_1_group_b_count"] = 0
        for layer_index in (2, 3):
            state[f"{prefix}_layer_{layer_index}_group_a_diameter_option"] = "-"
            state[f"{prefix}_layer_{layer_index}_group_a_diameter"] = 0
            state[f"{prefix}_layer_{layer_index}_group_a_count"] = 0
            state[f"{prefix}_layer_{layer_index}_group_b_diameter_option"] = "-"
            state[f"{prefix}_layer_{layer_index}_group_b_diameter"] = 0
            state[f"{prefix}_layer_{layer_index}_group_b_count"] = 0
    return state


def reset_workspace(default_inputs: BeamDesignInputSet) -> None:
    st.session_state.project_date_auto_value = _current_timestamp_text()
    for key, value in build_default_state(default_inputs).items():
        st.session_state[key] = value
    st.session_state[DEFLECTION_FIRST_ENABLE_KEY] = bool(st.session_state.get("consider_deflection", False))
    st.session_state[CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY] = False
    st.session_state[NEGATIVE_REBAR_INPUT_BACKUP_KEY] = {}
    st.session_state[DEFLECTION_IE_METHOD_BACKUP_KEY] = None
    st.session_state[DEFLECTION_SUPPORT_INPUT_BACKUP_KEY] = {}
    st.session_state[DEFLECTION_SUPPORT_INPUT_VISIBLE_KEY] = False
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
    st.session_state.auto_beam_behavior_threshold_percent = 5.0
    st.session_state.ec_manual_ksc = calculate_default_ec_ksc(concrete_strength)
    st.session_state.es_manual_ksc = calculate_default_es_ksc()
    st.session_state.fr_manual_ksc = calculate_default_fr_ksc(concrete_strength)


def render_header() -> None:
    default_inputs = load_default_inputs()
    header_left, header_right = st.columns([1.2, 1], gap="medium")
    with header_left:
        st.markdown("<div class='hero-title'>Reinforced Concrete Beam Analysis</div>", unsafe_allow_html=True)
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
            options=_beam_type_ui_options(),
            horizontal=True,
            key="beam_type",
            on_change=_handle_beam_type_change,
            help="Simple Beam hides negative-moment design. Continuous Beam shows both positive and negative design workflows.",
        )
        st.caption("Simple Beam = positive-moment workflow only. Continuous Beam = positive and negative moment design.")
        behavior_label_col, behavior_help_col = st.columns([0.88, 0.12], gap="small")
        with behavior_label_col:
            st.markdown("<div class='input-field-label'>Beam Behavior</div>", unsafe_allow_html=True)
        with behavior_help_col:
            _render_info_button(
                "Beam Behavior:\n"
                "- Singly: Ignore compression steel contribution for flexural strength classification\n"
                "- Auto: Classify as Singly or Doubly based on compression steel contribution ratio R\n"
                "- Doubly: Always include compression steel contribution\n\n"
                "These labels describe flexural behavior only; they are not module names.",
                label="?",
            )
        st.radio(
            "Beam Behavior",
            options=[mode.value for mode in BeamBehaviorMode],
            horizontal=True,
            key="beam_behavior_mode",
            label_visibility="collapsed",
        )
        st.checkbox("Include Torsion Design", key="include_torsion_design", on_change=_handle_include_torsion_design_change)
        st.checkbox("Consider Deflection", key="consider_deflection", on_change=_handle_consider_deflection_change)

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

    shear_section_label = _shear_design_section_label(st.session_state.include_torsion_design, _selected_beam_type())
    with st.expander(shear_section_label, expanded=True):
        _render_shear_header_feedback(preview_results)
        _render_shear_inputs()
        _render_shear_spacing_feedback()
        if st.session_state.include_torsion_design:
            _render_torsion_section(preview_results)
    if st.session_state.consider_deflection:
        with st.expander(_deflection_section_label(_selected_beam_type()), expanded=True):
            _render_deflection_section(preview_results)


def render_input_workspace_extended() -> None:
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
            options=_beam_type_ui_options(),
            horizontal=True,
            key="beam_type",
            on_change=_handle_beam_type_change,
            help="Select the flexural section pattern to expose the required design sections for this member or design region.",
        )
        if _selected_beam_type() in {BeamType.SIMPLE, BeamType.CONTINUOUS}:
            st.checkbox("Include Cantilever Span", key="include_cantilever_span")
        st.caption(
            "Standalone Cantilever Beam = cantilever negative section only. "
            "Simple Beam = positive section, with optional cantilever negative section. "
            "Continuous Beam = positive and support negative sections, with optional cantilever negative section."
        )
        behavior_label_col, behavior_help_col = st.columns([0.88, 0.12], gap="small")
        with behavior_label_col:
            st.markdown("<div class='input-field-label'>Beam Behavior</div>", unsafe_allow_html=True)
        with behavior_help_col:
            _render_info_button(
                "Beam Behavior:\n"
                "- Singly: Ignore compression steel contribution for flexural strength classification\n"
                "- Auto: Classify as Singly or Doubly based on compression steel contribution ratio R\n"
                "- Doubly: Always include compression steel contribution\n\n"
                "These labels describe flexural behavior only; they are not module names.",
                label="?",
            )
        st.radio(
            "Beam Behavior",
            options=[mode.value for mode in BeamBehaviorMode],
            horizontal=True,
            key="beam_behavior_mode",
            label_visibility="collapsed",
        )
        st.checkbox("Include Torsion Design", key="include_torsion_design", on_change=_handle_include_torsion_design_change)
        st.checkbox("Consider Deflection", key="consider_deflection", on_change=_handle_consider_deflection_change)

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

    for expander_title, config in _flexural_editor_configs():
        with st.expander(expander_title, expanded=True):
            if "moment_mode_key" in config:
                st.radio(
                    "Moment input mode",
                    options=[mode.value for mode in DemandInputMode],
                    key=config["moment_mode_key"],
                    horizontal=True,
                )
                if st.session_state[config["moment_mode_key"]] == DemandInputMode.MANUAL.value:
                    st.number_input(config["moment_label"], min_value=0.0, step=50.0, key=config["moment_key"])
                else:
                    auto_support_mu = float(st.session_state.positive_mu_kgm) * 0.75
                    st.metric("Auto Mu at Support - L/4 (kg-m)", format_number(auto_support_mu))
                    st.caption(config["moment_mode_auto_note"])
            else:
                st.number_input(config["moment_label"], min_value=0.0, step=50.0, key=config["moment_key"])
            flexure_tabs = st.tabs(["Tension Reinforcement", "Compression Reinforcement"])
            with flexure_tabs[0]:
                st.caption(config["tension_caption"])
                render_reinforcement_editor(
                    config["tension_prefix"],
                    "Tension Reinforcement",
                    preview_inputs,
                    preview_results,
                    show_phi=True,
                )
            with flexure_tabs[1]:
                st.caption(config["compression_caption"])
                render_reinforcement_editor(
                    config["compression_prefix"],
                    "Compression Reinforcement",
                    preview_inputs,
                    preview_results,
                    show_phi=False,
                )

    shear_section_label = _shear_design_section_label(st.session_state.include_torsion_design, _selected_beam_type())
    with st.expander(shear_section_label, expanded=True):
        _render_shear_header_feedback(preview_results)
        _render_shear_inputs()
        _render_shear_spacing_feedback()
        if st.session_state.include_torsion_design:
            _render_torsion_section(preview_results)
    if st.session_state.consider_deflection:
        with st.expander(_deflection_section_label(_selected_beam_type()), expanded=True):
            _render_deflection_section(preview_results)


def _flexural_editor_configs() -> list[tuple[str, dict[str, str]]]:
    sections: list[dict[str, str]] = []
    beam_type = _selected_beam_type()
    if beam_type == BeamType.SIMPLE:
        sections.append(
            {
                "title": "Middle Section",
                "moment_label": "Mu_max (kg-m)",
                "moment_key": "positive_mu_kgm",
                "tension_prefix": "pb_tens",
                "compression_prefix": "pb_comp",
                "tension_caption": "Bottom reinforcement.",
                "compression_caption": "Top reinforcement.",
            }
        )
        sections.append(
            {
                "title": "Support Section",
                "moment_label": "Mu, support - L/4 (kg-m)",
                "moment_key": "support_mu_kgm",
                "moment_mode_key": "support_mu_mode",
                "moment_mode_auto_note": "Auto-calculated from the simple beam moment diagram at x/L = 0.25.",
                "tension_prefix": "sb_tens",
                "compression_prefix": "sb_comp",
                "tension_caption": "Bottom reinforcement.",
                "compression_caption": "Top reinforcement.",
            }
        )
    elif beam_type != BeamType.STANDALONE_CANTILEVER:
        sections.append(
            {
                "title": "Positive Section",
                "moment_label": "Mu, positive (kg-m)",
                "moment_key": "positive_mu_kgm",
                "tension_prefix": "pb_tens",
                "compression_prefix": "pb_comp",
                "tension_caption": "Bottom reinforcement.",
                "compression_caption": "Top reinforcement.",
            }
        )
    if beam_type == BeamType.CONTINUOUS:
        sections.append(
            {
                "title": "Negative Section",
                "moment_label": "Mu, negative (kg-m)",
                "moment_key": "negative_mu_kgm",
                "tension_prefix": "nb_tens",
                "compression_prefix": "nb_comp",
                "tension_caption": "Top reinforcement.",
                "compression_caption": "Bottom reinforcement.",
            }
        )
    if beam_type == BeamType.STANDALONE_CANTILEVER or _selected_include_cantilever_span():
        sections.append(
            {
                "title": "Cantilever Negative Section",
                "moment_label": "Mu, cantilever negative (kg-m)",
                "moment_key": "cantilever_negative_mu_kgm",
                "tension_prefix": "cb_tens",
                "compression_prefix": "cb_comp",
                "tension_caption": "Top reinforcement.",
                "compression_caption": "Bottom reinforcement.",
            }
        )
    return [(f"{index}. {section['title']}", section) for index, section in enumerate(sections, start=5)]

def _render_shear_inputs() -> None:
    beam_type = _selected_beam_type()
    include_cantilever = _selected_include_cantilever_span()
    vu_regions = _active_vu_region_specs(beam_type, include_cantilever)
    for region_key, region_label, section_label in vu_regions:
        st.markdown(f"<div class='section-label'>{region_label} &rarr; {section_label}</div>", unsafe_allow_html=True)
        if region_key == "support":
            st.number_input(region_label, min_value=0.0, step=50.0, key="support_vu_kg")
        elif region_key in {"middle", "span_region"}:
            st.radio(
                f"{region_label} mode",
                options=[mode.value for mode in DemandInputMode],
                key="span_vu_mode",
                horizontal=True,
            )
            st.number_input(
                "Interior span position x/L",
                min_value=0.25,
                max_value=0.75,
                step=0.05,
                key="span_vu_position_ratio",
            )
            if st.session_state.span_vu_mode == DemandInputMode.MANUAL.value:
                st.number_input(region_label, min_value=0.0, step=50.0, key="span_vu_kg")
            else:
                auto_vu = float(st.session_state.support_vu_kg) * abs(1.0 - (2.0 * float(st.session_state.span_vu_position_ratio)))
                st.metric(f"Auto {region_label} (kg)", format_number(auto_vu))
                st.caption("Auto-calculated from support Vu using uniform-load linear reduction.")
        else:
            st.number_input(region_label, min_value=0.0, step=50.0, key="cantilever_vu_kg")

    top_cols = st.columns(3 if st.session_state.include_torsion_design else 2, gap="medium")
    column_index = 0
    if st.session_state.include_torsion_design:
        with top_cols[0]:
            st.markdown("<div class='input-field-label'>T<sub>u</sub> (kgf-m)</div>", unsafe_allow_html=True)
            st.number_input("Tu (kgf-m)", min_value=0.0, step=10.0, key="torsion_tu_kgfm", label_visibility="collapsed")
            _render_field_helper("Factored torsion")
        column_index = 1
    with top_cols[column_index]:
        st.markdown("<div class='input-field-label'>Stirrup diameter (mm)</div>", unsafe_allow_html=True)
        st.selectbox(
            "Stirrup diameter (mm)",
            options=BAR_DIAMETER_OPTIONS,
            key="stirrup_diameter_option",
            label_visibility="collapsed",
        )
        _render_diameter_input("stirrup_diameter_option", "stirrup_diameter_mm", "Stirrup diameter custom (mm)", allow_empty=False)
    with top_cols[column_index + 1]:
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


def _render_torsion_section(preview_results) -> None:
    st.markdown("<div class='section-label'>Torsion</div>", unsafe_allow_html=True)
    if preview_results is None:
        st.caption("Complete the current input set to preview torsion design results.")
        return

    torsion = preview_results.torsion
    combined = preview_results.combined_shear_torsion
    if not _torsion_detail_inputs_required(preview_results):
        st.markdown(
            f"<div class='design-banner info'>{combined.ignore_message}</div>",
            unsafe_allow_html=True,
        )
        return

    try:
        current_inputs = _build_inputs_for_torsion_capacity_preview()
        drawable_counts = [torsion_bar_drawable_capacity(current_inputs, moment_case) for moment_case in available_moment_cases(current_inputs)]
        max_drawable_al_count = min(drawable_counts) if drawable_counts else 0
    except ValueError:
        max_drawable_al_count = 0

    st.markdown(
        f"<div class='design-banner info'>Uses Design Code: {st.session_state.design_code}</div>",
        unsafe_allow_html=True,
    )

    top_input_cols = st.columns(3, gap="medium")
    with top_input_cols[0]:
        st.markdown("<div class='input-field-label'>Al bars dia (mm)</div>", unsafe_allow_html=True)
        st.selectbox(
            "Al bars dia (mm)",
            options=BAR_DIAMETER_OPTIONS_WITH_EMPTY,
            key="torsion_longitudinal_diameter_option",
            label_visibility="collapsed",
        )
        _render_diameter_input(
            "torsion_longitudinal_diameter_option",
            "torsion_longitudinal_diameter_mm",
            "Al bars dia custom (mm)",
            allow_empty=True,
        )
    with top_input_cols[1]:
        st.markdown("<div class='input-field-label'>Al fyl (ksc)</div>", unsafe_allow_html=True)
        st.selectbox(
            "Al fyl (ksc)",
            options=STEEL_GRADE_OPTIONS,
            key="torsion_longitudinal_fy_grade_option",
            label_visibility="collapsed",
        )
        _render_steel_grade_input("torsion_longitudinal_fy_grade_option", "torsion_longitudinal_fy_ksc", "Al fyl custom (ksc)")
    with top_input_cols[2]:
        st.markdown("<div class='input-field-label'>Al count</div>", unsafe_allow_html=True)
        if max_drawable_al_count >= 0 and st.session_state.torsion_longitudinal_count > max_drawable_al_count:
            st.session_state.torsion_longitudinal_count = max_drawable_al_count
        st.number_input(
            "Al count",
            min_value=0,
            max_value=max_drawable_al_count,
            step=1,
            key="torsion_longitudinal_count",
            label_visibility="collapsed",
        )
        _render_field_helper(f"Maximum drawable Al count = {max_drawable_al_count}")
        if max_drawable_al_count == 0 and st.session_state.torsion_longitudinal_diameter_mm > 0:
            _render_warning_banner(
                "No drawable Al bar position is available for the current section and spacing rules. "
                "This does not satisfy the specified placement and clear-spacing requirements and is not suitable for practical construction."
            )
        elif st.session_state.torsion_longitudinal_count >= max_drawable_al_count > 0:
            _render_warning_banner(
                f"Reached maximum of drawable Al bars for the current section layout: {max_drawable_al_count} bars. "
                "Any additional Al bar would violate the specified clear-spacing requirement and would not be suitable for practical construction."
            )

    bottom_cols = st.columns(3, gap="medium")
    with bottom_cols[0]:
        provided_al_cm2 = _torsion_longitudinal_area_from_state()
        st.markdown("<div class='input-field-label'>Provided Al</div>", unsafe_allow_html=True)
        st.caption(f"{format_number(provided_al_cm2)} cm²")
        _render_field_helper("Calculated from dia and count")
    with bottom_cols[1]:
        st.markdown("<div class='input-field-label'>Torsion demand type</div>", unsafe_allow_html=True)
        st.radio(
            "Torsion demand type",
            options=[demand_type.value for demand_type in TorsionDemandType],
            key="torsion_demand_type",
            horizontal=True,
            label_visibility="collapsed",
        )
    with bottom_cols[2]:
        _render_torsion_demand_type_info()

    if combined.active:
        st.markdown("<div class='section-label'>Shear & Torsion</div>", unsafe_allow_html=True)
        combined_lines = [
            f"Vu = {format_number(combined.vu_kg)} kgf | Tu = {format_number(combined.tu_kgfm)} kgf-m",
            f"Transverse req. = shear {combined.shear_required_transverse_mm2_per_mm:.6f} + torsion {combined.torsion_required_transverse_mm2_per_mm:.6f} = {combined.combined_required_transverse_mm2_per_mm:.6f} mm<sup>2</sup>/mm",
            f"Transverse prov. = {combined.provided_transverse_mm2_per_mm:.6f} mm<sup>2</sup>/mm | Capacity Ratio (Shear + Torsion) = {format_ratio(combined.capacity_ratio, 3)}",
            f"Shared stirrups = \u03d5{combined.stirrup_diameter_mm} mm / {combined.stirrup_legs} legs @ {format_number(combined.stirrup_spacing_cm)} cm | {combined.design_status}",
        ]
        if combined.cross_section_limit_check_applied:
            combined_lines.append(
                "Combined section limit = "
                f"{combined.cross_section_limit_lhs_mpa:.3f} / {combined.cross_section_limit_rhs_mpa:.3f} MPa "
                f"(ratio {format_ratio(combined.cross_section_limit_ratio, 3)})"
            )
        for line in combined_lines:
            st.markdown(f"<div class='design-banner info'>{line}</div>", unsafe_allow_html=True)
        st.markdown("<div class='section-label'>Longitudinal Torsion Steel</div>", unsafe_allow_html=True)
        st.markdown(
            (
                "<div class='design-banner info'>"
                f"Al,req = {format_number(torsion.longitudinal_reinf_required_mm2 / 100.0)} cm<sup>2</sup> | "
                f"Al,prov = {format_number(torsion.longitudinal_reinf_provided_mm2 / 100.0)} cm<sup>2</sup> | "
                f"fyl = {format_number(_resolved_grade_value('torsion_longitudinal_fy_grade_option', 'torsion_longitudinal_fy_ksc'))} ksc"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    for line in torsion_workspace_summary_lines(torsion):
        st.markdown(f"<div class='design-banner info'>{line}</div>", unsafe_allow_html=True)
    if torsion.demand_type == TorsionDemandType.COMPATIBILITY:
        st.markdown(
            "<div class='design-banner info'>Compatibility torsion is shown using the entered Tu; redistribution is not implemented.</div>",
            unsafe_allow_html=True,
        )
    for warning in torsion.warnings:
        _render_warning_banner(_formalize_torsion_warning_text(warning, torsion))
    current_inputs = build_inputs_from_state()
    spacing_warnings = [
        torsion_bar_spacing_warning(current_inputs, moment_case)
        for moment_case in available_moment_cases(current_inputs)
    ]
    for spacing_warning in spacing_warnings:
        if spacing_warning:
            _render_warning_banner(_formalize_constructability_warning_text(spacing_warning))


def _render_deflection_section(preview_results) -> None:
    _ensure_deflection_support_state()
    st.caption(
        "Select the serviceability limit that applies to the project. The engineer remains responsible for choosing "
        "the appropriate limit based on use, finishes, partitions, and project requirements."
    )
    support_options = _deflection_support_options_for_member_type(st.session_state.deflection_member_type)
    top_cols = st.columns([1.0, 1.0], gap="medium")
    with top_cols[0]:
        st.markdown("<div class='input-field-label'>Design code</div>", unsafe_allow_html=True)
        st.caption(f"Uses Project Info code: {st.session_state.design_code}")
    if len(support_options) > 1:
        with top_cols[1]:
            st.selectbox(
                "Support condition",
                options=support_options,
                key="deflection_support_condition",
            )
    else:
        with top_cols[1]:
            st.markdown("<div class='input-field-label'>Support condition</div>", unsafe_allow_html=True)
            st.caption(support_options[0])
    if st.session_state.deflection_support_condition in {
        DeflectionSupportCondition.CONTINUOUS_2_SPANS.value,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS.value,
    }:
        ie_method_cols = st.columns([1.0, 0.28], gap="medium")
        with ie_method_cols[0]:
            st.selectbox(
                "Deflection Ie method",
                options=[method.value for method in DeflectionIeMethod],
                key="deflection_ie_method",
                on_change=_handle_deflection_ie_method_change,
            )
        with ie_method_cols[1]:
            _render_info_button(_deflection_ie_method_info_text())
    else:
        st.markdown("<div class='input-field-label'>Deflection Ie method</div>", unsafe_allow_html=True)
        st.caption(DeflectionIeMethod.MIDSPAN_ONLY.value)

    load_cols = st.columns([1.0, 1.0, 1.0, 1.0, 0.28], gap="medium")
    with load_cols[0]:
        st.number_input(
            "DL (kgf/m)",
            value=float(_automatic_deflection_dead_load_from_state()),
            step=10.0,
            disabled=True,
        )
    with load_cols[1]:
        st.number_input(
            "SDL (kgf/m)",
            min_value=0.0,
            step=10.0,
            key="deflection_additional_sustained_load_kgf_per_m",
        )
    with load_cols[2]:
        st.number_input("Service LL (kgf/m)", min_value=0.0, step=10.0, key="deflection_service_live_load_kgf_per_m")
    with load_cols[3]:
        st.number_input(
            "Sustained LL ratio",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            key="deflection_sustained_live_load_ratio",
        )
    with load_cols[4]:
        _render_info_button(_deflection_service_load_info_text())

    parameter_cols = st.columns([1.0, 1.0, 0.28, 1.1, 0.28], gap="medium")
    with parameter_cols[0]:
        st.number_input("Span length L (m)", min_value=0.01, step=0.1, key="span_length_m")
    with parameter_cols[1]:
        if "deflection_long_term_factor_x" not in st.session_state:
            st.session_state.deflection_long_term_factor_x = 2.0
        st.number_input(
            "Long-term factor x",
            min_value=0.1,
            step=0.1,
            key="deflection_long_term_factor_x",
        )
    with parameter_cols[2]:
        _render_info_button(_deflection_long_term_x_info_text())
    with parameter_cols[3]:
        st.selectbox(
            "Allowable Deflection Limit",
            options=[preset.value for preset in AllowableDeflectionPreset],
            key="deflection_allowable_limit_preset",
        )
    with parameter_cols[4]:
        _render_info_button(_deflection_limit_info_text())

    limit_detail_cols = st.columns([2.28, 1.0, 1.0], gap="medium")
    with limit_detail_cols[0]:
        st.markdown("&nbsp;", unsafe_allow_html=True)
    with limit_detail_cols[1]:
        if st.session_state.deflection_allowable_limit_preset == AllowableDeflectionPreset.CUSTOM.value:
            st.number_input(
                "Custom denominator",
                min_value=1,
                step=10,
                key="deflection_allowable_limit_custom_denominator",
            )
        else:
            st.markdown("<div class='input-field-label'>Selected ratio</div>", unsafe_allow_html=True)
            st.caption(st.session_state.deflection_allowable_limit_preset)
    with limit_detail_cols[2]:
        denominator = (
            int(st.session_state.deflection_allowable_limit_custom_denominator)
            if st.session_state.deflection_allowable_limit_preset == AllowableDeflectionPreset.CUSTOM.value
            else int(st.session_state.deflection_allowable_limit_preset.split("/")[1])
        )
        allowable_cm = (float(st.session_state.span_length_m) * 100.0) / denominator
        st.markdown("<div class='input-field-label'>Allowable deflection</div>", unsafe_allow_html=True)
        st.caption(f"{format_number(allowable_cm)} cm")

    if st.session_state.deflection_support_condition in {
        DeflectionSupportCondition.CONTINUOUS_2_SPANS.value,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS.value,
    }:
        if st.session_state.deflection_ie_method != DeflectionIeMethod.MIDSPAN_ONLY.value:
            _enter_deflection_support_input_visibility()
            support_header_cols = st.columns([1.0, 0.28], gap="medium")
            with support_header_cols[0]:
                st.selectbox(
                    "Support moment input",
                    options=list(DEFLECTION_SUPPORT_MOMENT_MODE_OPTIONS),
                    key="deflection_support_moment_mode",
                    on_change=_backup_deflection_support_input_state,
                )
            with support_header_cols[1]:
                _render_info_button(_deflection_support_moment_info_text())
            support_dead_moment_kgm, support_live_moment_kgm = _resolved_deflection_support_moments_from_state()
            support_mode = st.session_state.get("deflection_support_moment_mode", "Auto")
            support_cols = st.columns([1.0, 1.0], gap="medium")
            with support_cols[0]:
                if support_mode == "Auto":
                    st.session_state["deflection_support_dead_load_service_moment_auto_display"] = float(support_dead_moment_kgm)
                    st.number_input(
                        "Negative support moment, DL service (kg-m)",
                        key="deflection_support_dead_load_service_moment_auto_display",
                        step=10.0,
                        disabled=True,
                    )
                else:
                    st.number_input(
                        "Negative support moment, DL service (kg-m)",
                        max_value=0.0,
                        step=10.0,
                        key="deflection_support_dead_load_service_moment_kgm",
                        on_change=_backup_deflection_support_input_state,
                    )
            with support_cols[1]:
                if support_mode == "Auto":
                    st.session_state["deflection_support_live_load_service_moment_auto_display"] = float(support_live_moment_kgm)
                    st.number_input(
                        "Negative support moment, LL service (kg-m)",
                        key="deflection_support_live_load_service_moment_auto_display",
                        step=10.0,
                        disabled=True,
                    )
                else:
                    st.number_input(
                        "Negative support moment, LL service (kg-m)",
                        max_value=0.0,
                        step=10.0,
                        key="deflection_support_live_load_service_moment_kgm",
                        on_change=_backup_deflection_support_input_state,
                    )
            if support_mode == "Auto":
                st.caption(
                    "Auto mode uses representative negative continuous-support moments from the current span and service loads. "
                    "Dead-type support moment uses -(DL_auto + SDL); live support moment uses -Service LL."
                )
            else:
                st.caption(
                    "Manual mode overrides the auto-estimated values. Enter the negative moment value at continuous "
                    "support for the representative span being checked."
                )
        else:
            _leave_deflection_support_input_visibility()
            st.caption("Midspan Ie only mode does not use support moments in the deflection calculation.")
    else:
        _leave_deflection_support_input_visibility()

    # Recompute directly from the latest session-state values in this section.
    # Do not fall back to older preview results here because stale serviceability
    # output is more misleading than showing no preview when current inputs are invalid.
    try:
        current_inputs = build_inputs_from_state()
        preview_results = calculate_full_design_results(current_inputs)
        st.session_state.preview_design_inputs = current_inputs
        st.session_state.preview_design_results = preview_results
    except ValueError:
        preview_results = None
    _render_deflection_diagram_fragment(_deflection_reference_diagram_html(preview_results), height=300)

    if preview_results is None:
        st.caption("Complete the current input set to preview deflection results.")
        return

    deflection = preview_results.deflection
    for line in deflection_workspace_summary_lines(deflection):
        st.markdown(f"<div class='design-banner info'>{line}</div>", unsafe_allow_html=True)
    if deflection.load_basis_note:
        st.markdown(f"<div class='design-banner info'>{deflection.load_basis_note}</div>", unsafe_allow_html=True)
    if deflection.ie_method_selected:
        method_banner = (
            f"Selected Ie method = {deflection.ie_method_selected}"
            if deflection.ie_method_selected == deflection.ie_method_governing or not deflection.ie_method_governing
            else f"Selected Ie method = {deflection.ie_method_selected} | Governing method = {deflection.ie_method_governing}"
        )
        st.markdown(f"<div class='design-banner info'>{method_banner}</div>", unsafe_allow_html=True)
    if deflection.support_condition in {
        DeflectionSupportCondition.CONTINUOUS_2_SPANS.value,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS.value,
    }:
        st.markdown(
            "<div class='design-banner info'>"
            f"Support moments for I<sub>e,avg</sub> candidate: M<sub>sup,DL</sub> = {format_number(deflection.support_dead_load_service_moment_kgm)} kg-m, "
            f"M<sub>sup,LL</sub> = {format_number(deflection.support_live_load_service_moment_kgm)} kg-m."
            "</div>",
            unsafe_allow_html=True,
        )
    for warning in deflection.warnings:
        if "licensed code text" in warning:
            _render_warning_banner(f"{warning} This should be confirmed by the design engineer.")
        elif "load-free" in warning or "live load is zero" in warning:
            st.markdown(f"<div class='design-banner info'>{warning}</div>", unsafe_allow_html=True)
        else:
            _render_warning_banner(warning)



def _deflection_section_label(beam_type: BeamType) -> str:
    return f"{_deflection_section_number()}. Deflection Check"


def _deflection_support_options_for_member_type(member_type_value: str) -> list[str]:
    member_type = DeflectionMemberType(member_type_value)
    if member_type == DeflectionMemberType.SIMPLE_BEAM:
        return [DeflectionSupportCondition.SIMPLE.value]
    if member_type == DeflectionMemberType.CONTINUOUS_BEAM:
        return [
            DeflectionSupportCondition.CONTINUOUS_2_SPANS.value,
            DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS.value,
        ]
    return [DeflectionSupportCondition.CANTILEVER_PLACEHOLDER.value]


def _deflection_member_type_options(beam_type: BeamType) -> list[str]:
    if beam_type == BeamType.STANDALONE_CANTILEVER:
        return [DeflectionMemberType.CANTILEVER_BEAM.value]
    if beam_type == BeamType.SIMPLE:
        return [DeflectionMemberType.SIMPLE_BEAM.value]
    return [DeflectionMemberType.CONTINUOUS_BEAM.value]


def _sync_deflection_support_condition() -> None:
    options = _deflection_support_options_for_member_type(st.session_state.deflection_member_type)
    if st.session_state.get("deflection_support_condition") not in options:
        st.session_state.deflection_support_condition = options[0]


def _sync_deflection_member_controls() -> None:
    st.session_state.deflection_member_type = _deflection_member_type_options(_selected_beam_type())[0]
    _sync_deflection_support_condition()


def _handle_beam_type_change() -> None:
    _handle_deflection_ie_method_for_beam_type_change()
    _handle_negative_rebar_state_for_beam_type_change()
    _apply_first_continuous_negative_rebar_defaults()
    _sync_deflection_member_controls()


def _apply_continuous_negative_rebar_defaults() -> None:
    for prefix in ("nb_tens", "nb_comp"):
        st.session_state[f"{prefix}_layer_1_group_a_diameter_option"] = 12
        st.session_state[f"{prefix}_layer_1_group_a_diameter"] = 12
        st.session_state[f"{prefix}_layer_1_group_a_count"] = 2
        st.session_state[f"{prefix}_layer_1_group_b_diameter_option"] = "-"
        st.session_state[f"{prefix}_layer_1_group_b_diameter"] = 0
        st.session_state[f"{prefix}_layer_1_group_b_count"] = 0
        for layer_index in (2, 3):
            st.session_state[f"{prefix}_layer_{layer_index}_group_a_diameter_option"] = "-"
            st.session_state[f"{prefix}_layer_{layer_index}_group_a_diameter"] = 0
            st.session_state[f"{prefix}_layer_{layer_index}_group_a_count"] = 0
            st.session_state[f"{prefix}_layer_{layer_index}_group_b_diameter_option"] = "-"
            st.session_state[f"{prefix}_layer_{layer_index}_group_b_diameter"] = 0
            st.session_state[f"{prefix}_layer_{layer_index}_group_b_count"] = 0


def _apply_first_continuous_negative_rebar_defaults() -> None:
    if _selected_beam_type() != BeamType.CONTINUOUS:
        return
    if _restore_negative_rebar_input_backup():
        st.session_state[CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY] = True
        return
    if st.session_state.get(CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY, False):
        return
    _apply_continuous_negative_rebar_defaults()
    st.session_state[CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY] = True


def _negative_rebar_input_state_keys() -> tuple[str, ...]:
    keys: list[str] = []
    for prefix in ("nb_tens", "nb_comp"):
        for layer_index in range(1, 4):
            keys.extend(
                [
                    f"{prefix}_layer_{layer_index}_group_a_diameter_option",
                    f"{prefix}_layer_{layer_index}_group_a_diameter",
                    f"{prefix}_layer_{layer_index}_group_a_count",
                    f"{prefix}_layer_{layer_index}_group_b_diameter_option",
                    f"{prefix}_layer_{layer_index}_group_b_diameter",
                    f"{prefix}_layer_{layer_index}_group_b_count",
                ]
            )
    keys.append("negative_mu_kgm")
    return tuple(keys)


def _handle_negative_rebar_state_for_beam_type_change() -> None:
    if _selected_beam_type() == BeamType.CONTINUOUS:
        return
    st.session_state[NEGATIVE_REBAR_INPUT_BACKUP_KEY] = {
        key: st.session_state[key]
        for key in _negative_rebar_input_state_keys()
        if key in st.session_state
    }


def _restore_negative_rebar_input_backup() -> bool:
    backup_state = st.session_state.get(NEGATIVE_REBAR_INPUT_BACKUP_KEY)
    if not isinstance(backup_state, dict) or not backup_state:
        return False
    for key, value in backup_state.items():
        st.session_state[key] = value
    return True


def _backup_deflection_ie_method_for_continuous() -> None:
    method_value = st.session_state.get("deflection_ie_method")
    if method_value in {method.value for method in DeflectionIeMethod}:
        st.session_state[DEFLECTION_IE_METHOD_BACKUP_KEY] = method_value


def _restore_deflection_ie_method_for_continuous() -> bool:
    method_value = st.session_state.get(DEFLECTION_IE_METHOD_BACKUP_KEY)
    if method_value not in {method.value for method in DeflectionIeMethod}:
        return False
    st.session_state["deflection_ie_method"] = method_value
    return True


def _handle_deflection_ie_method_for_beam_type_change() -> None:
    if _selected_beam_type() == BeamType.CONTINUOUS:
        _restore_deflection_ie_method_for_continuous()
        return
    _backup_deflection_ie_method_for_continuous()


def _deflection_support_input_state_keys() -> tuple[str, ...]:
    return (
        "deflection_support_moment_mode",
        "deflection_support_dead_load_service_moment_kgm",
        "deflection_support_live_load_service_moment_kgm",
    )


def _backup_deflection_support_input_state() -> None:
    st.session_state[DEFLECTION_SUPPORT_INPUT_BACKUP_KEY] = {
        key: st.session_state[key]
        for key in _deflection_support_input_state_keys()
        if key in st.session_state
    }


def _restore_deflection_support_input_backup() -> bool:
    backup_state = st.session_state.get(DEFLECTION_SUPPORT_INPUT_BACKUP_KEY)
    if not isinstance(backup_state, dict) or not backup_state:
        return False
    for key, value in backup_state.items():
        st.session_state[key] = value
    return True


def _handle_deflection_ie_method_change() -> None:
    if st.session_state.get("deflection_ie_method") == DeflectionIeMethod.MIDSPAN_ONLY.value:
        _backup_deflection_support_input_state()


def _enter_deflection_support_input_visibility() -> None:
    if st.session_state.get(DEFLECTION_SUPPORT_INPUT_VISIBLE_KEY, False):
        return
    _restore_deflection_support_input_backup()
    st.session_state[DEFLECTION_SUPPORT_INPUT_VISIBLE_KEY] = True


def _leave_deflection_support_input_visibility() -> None:
    if not st.session_state.get(DEFLECTION_SUPPORT_INPUT_VISIBLE_KEY, False):
        return
    _backup_deflection_support_input_state()
    st.session_state[DEFLECTION_SUPPORT_INPUT_VISIBLE_KEY] = False


def _apply_first_enable_deflection_defaults(default_state: dict[str, object]) -> None:
    for key in (
        "deflection_sustained_live_load_ratio",
        "span_length_m",
        "deflection_long_term_factor_x",
        "deflection_allowable_limit_preset",
        "deflection_ie_method",
    ):
        st.session_state[key] = default_state[key]


def _handle_consider_deflection_change() -> None:
    if not bool(st.session_state.get("consider_deflection", False)):
        return
    if st.session_state.get(DEFLECTION_FIRST_ENABLE_KEY, False):
        return
    _apply_first_enable_deflection_defaults(build_default_state(load_default_inputs()))
    _sync_deflection_member_controls()
    st.session_state[DEFLECTION_FIRST_ENABLE_KEY] = True


def _ensure_deflection_support_state() -> None:
    if "deflection_member_type" not in st.session_state:
        return
    _sync_deflection_member_controls()


def _deflection_reference_diagram_html(
    preview_results=None,
    *,
    summary_mode: bool = False,
    palette=None,
    support_condition_override: str | None = None,
) -> str:
    palette = palette or LIGHT_THEME
    support_color = "#111111"
    calculated_curve_color = "#0b5cab"
    support_condition = support_condition_override or st.session_state.deflection_support_condition
    width = 520.0
    height = 172.0
    beam_y = 68.0
    left_x = 44.0
    right_x = 476.0
    span_width = right_x - left_x
    support_positions: list[float]
    highlight_positions: list[float]
    span_amplitudes: list[float]
    title = "Deflection Reference Diagram"
    note = "Highlighted point shows the deflection check location used by this module."
    calculated_deflection_cm = 0.0
    allowable_deflection_cm = 0.0
    vertical_scale_note = "Reference plot only."
    if preview_results is not None:
        calculated_deflection_cm = float(preview_results.deflection.total_service_deflection_cm)
        allowable_deflection_cm = float(preview_results.deflection.allowable_deflection_cm)
    base_amplitude = 18.0
    limit_amplitude = 30.0
    if allowable_deflection_cm > 0:
        governing_deflection_cm = max(calculated_deflection_cm, allowable_deflection_cm, 1e-9)
        # Auto-scale the vertical plot so small service deflections still read clearly on screen.
        base_amplitude = 12.0 + (24.0 * (calculated_deflection_cm / governing_deflection_cm))
        limit_amplitude = 12.0 + (24.0 * (allowable_deflection_cm / governing_deflection_cm))
        vertical_scale_note = (
            f"Vertical deflected shape is exaggerated for visibility. Total service deflection = "
            f"{format_number(calculated_deflection_cm)} cm, allowable = {format_number(allowable_deflection_cm)} cm."
        )

    if support_condition == DeflectionSupportCondition.SIMPLE.value:
        support_positions = [left_x, right_x]
        highlight_positions = [left_x + (span_width / 2.0)]
        span_amplitudes = [base_amplitude]
        note = "Simple beam: maximum deflection is checked at midspan."
    elif support_condition == DeflectionSupportCondition.CONTINUOUS_2_SPANS.value:
        support_positions = [left_x, left_x + (span_width / 2.0), right_x]
        highlight_positions = [left_x + (span_width * 0.25), left_x + (span_width * 0.75)]
        span_amplitudes = [base_amplitude * 0.88, base_amplitude * 0.88]
        note = "Continuous 2 spans: the module checks both Ie at midspan and representative Ie,avg, then uses the larger deflection."
    elif support_condition == DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS.value:
        support_positions = [left_x, left_x + (span_width / 3.0), left_x + (2.0 * span_width / 3.0), right_x]
        highlight_positions = [left_x + (span_width / 2.0)]
        span_amplitudes = [base_amplitude * 0.72, base_amplitude, base_amplitude * 0.72]
        note = "Continuous 3 or more spans: the module checks both Ie at the interior representative span midspan and representative Ie,avg, then uses the larger deflection."
    else:
        support_positions = [left_x, right_x]
        highlight_positions = [left_x + (span_width / 2.0)]
        span_amplitudes = [base_amplitude]
        note = "Mockup only / reserved for future cantilever module expansion."

    support_markup: list[str] = []
    for support_x in support_positions:
        support_markup.append(
            f"<polygon class='deflection-support-triangle' "
            f"points='{support_x - 12:.2f},{beam_y + 26:.2f} {support_x + 12:.2f},{beam_y + 26:.2f} {support_x:.2f},{beam_y - 0.6:.2f}' "
            f"fill='{support_color}' stroke='{support_color}' stroke-width='2.0' "
            f"style='fill:{support_color};stroke:{support_color};stroke-width:2.0' />"
        )
    highlight_markup = []
    # The dashed deflected shape is drawn as a quadratic Bezier for each span.
    # At the span midpoint (t = 0.5), the curve ordinate is beam_y + amplitude / 2.
    highlight_y_positions: list[float] = []
    if support_condition == DeflectionSupportCondition.SIMPLE.value:
        highlight_y_positions = [beam_y + (span_amplitudes[0] / 2.0)]
    elif support_condition == DeflectionSupportCondition.CONTINUOUS_2_SPANS.value:
        highlight_y_positions = [beam_y + (span_amplitudes[0] / 2.0), beam_y + (span_amplitudes[1] / 2.0)]
    elif support_condition == DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS.value:
        highlight_y_positions = [beam_y + (span_amplitudes[1] / 2.0)]
    else:
        highlight_y_positions = [beam_y + (span_amplitudes[0] / 2.0)]
    for highlight_x, highlight_y in zip(highlight_positions, highlight_y_positions):
        delta_label = f"&#916;max = {format_number(calculated_deflection_cm)} cm" if calculated_deflection_cm > 0 else "&#916;max"
        label_y = highlight_y + 20.0
        label_x = highlight_x - 34.0
        highlight_markup.append(
            f"<line class='deflection-highlight-guide' x1='{highlight_x:.2f}' y1='{beam_y - 22:.2f}' x2='{highlight_x:.2f}' y2='{highlight_y - 8:.2f}' "
            f"stroke='{palette.fail}' stroke-width='1.4' stroke-dasharray='4 3' "
            f"style='stroke:{palette.fail};stroke-width:1.4;stroke-dasharray:4 3' />"
            f"<circle class='deflection-highlight-ring' cx='{highlight_x:.2f}' cy='{highlight_y:.2f}' r='7' fill='none' stroke='{palette.fail}' stroke-width='2.2' "
            f"style='fill:none;stroke:{palette.fail};stroke-width:2.2' />"
            f"<circle class='deflection-highlight-dot' cx='{highlight_x:.2f}' cy='{highlight_y:.2f}' r='3.2' fill='{palette.fail}' style='fill:{palette.fail}' />"
            f"<rect x='{label_x - 3:.2f}' y='{label_y - 11.5:.2f}' width='82' height='16' rx='6' fill='{palette.surface}' fill-opacity='0.92' />"
            f"<text x='{label_x:.2f}' y='{label_y:.2f}' font-size='10.5' font-weight='700' fill='{palette.fail}'>{delta_label}</text>"
        )
    span_labels = []
    for index in range(len(support_positions) - 1):
        start_x = support_positions[index]
        end_x = support_positions[index + 1]
        span_labels.append(
            f"<text x='{(start_x + end_x) / 2.0:.2f}' y='{beam_y - 16:.2f}' text-anchor='middle' font-size='10.5' fill='{palette.muted_text}'>Span {index + 1}</text>"
        )
    deflected_shape_segments = [f"M {support_positions[0]:.2f} {beam_y:.2f}"]
    for index, amplitude in enumerate(span_amplitudes):
        start_x = support_positions[index]
        end_x = support_positions[index + 1]
        mid_x = (start_x + end_x) / 2.0
        deflected_shape_segments.append(f"Q {mid_x:.2f} {beam_y + amplitude:.2f}, {end_x:.2f} {beam_y:.2f}")
    deflected_shape_path = " ".join(deflected_shape_segments)
    limit_shape_segments = [f"M {support_positions[0]:.2f} {beam_y:.2f}"]
    for index, amplitude in enumerate(span_amplitudes):
        start_x = support_positions[index]
        end_x = support_positions[index + 1]
        mid_x = (start_x + end_x) / 2.0
        if support_condition == DeflectionSupportCondition.CONTINUOUS_2_SPANS.value:
            reference_amplitude = limit_amplitude * 0.88
        elif support_condition == DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS.value:
            reference_amplitude = [limit_amplitude * 0.72, limit_amplitude, limit_amplitude * 0.72][index]
        else:
            reference_amplitude = limit_amplitude
        limit_shape_segments.append(f"Q {mid_x:.2f} {beam_y + reference_amplitude:.2f}, {end_x:.2f} {beam_y:.2f}")
    limit_shape_path = " ".join(limit_shape_segments)
    legend_html = ""
    deflected_stroke_opacity = "1.0" if summary_mode else "0.82"
    limit_path_html = ""
    max_point_note_html = ""
    note_text = note
    if summary_mode:
        legend_html = (
            "<div class='metric-note' style='display:flex;gap:1rem;justify-content:center;align-items:center;margin-top:0.35rem'>"
            f"<span style='display:inline-flex;align-items:center;gap:0.35rem'><span style='width:18px;height:0;border-top:2px dashed {calculated_curve_color};display:inline-block'></span>Calculated deflection shape</span>"
            f"<span style='display:inline-flex;align-items:center;gap:0.35rem'><span style='width:18px;height:0;border-top:2px dashed {palette.fail};display:inline-block'></span>Allowable limit shape</span>"
            "</div>"
        )
        limit_path_html = (
            f"<path d=\"{limit_shape_path}\" fill=\"none\" stroke=\"{palette.fail}\" "
            f"stroke-width=\"2.2\" stroke-opacity=\"0.72\" stroke-dasharray=\"5 4\" />"
        )
        note_text = "Reference comparison between calculated deflection shape and allowable limit shape."
    else:
        max_point_note_html = (
            f"<text x=\"{width / 2.0:.2f}\" y=\"{height - 20:.2f}\" text-anchor=\"middle\" "
            f"font-size=\"11\" font-weight=\"600\" fill=\"{palette.fail}\">Max deflection check point</text>"
        )
    highlight_markup_content = "".join(highlight_markup) if not summary_mode else ""

    return dedent(f"""
    <div style="margin-top:0.85rem;padding:0.95rem 1rem 0.8rem 1rem;border-radius:16px;border:1px solid {palette.border};background:linear-gradient(160deg,{palette.surface},{palette.surface_alt});box-sizing:border-box;">
      <div style="color:{palette.text};font-size:1rem;font-weight:700;margin-bottom:0.5rem;">{title}</div>
      <svg width="100%" viewBox="0 0 {width:.0f} {height:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Deflection reference diagram" preserveAspectRatio="xMidYMid meet" style="width:100%;max-width:{width:.0f}px;height:auto;display:block;margin:0 auto;overflow:visible">
        <rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" rx="14" fill="{palette.surface_alt}" />
        <line x1="{left_x:.2f}" y1="{beam_y:.2f}" x2="{right_x:.2f}" y2="{beam_y:.2f}" stroke="{palette.text}" stroke-width="4.2" stroke-linecap="round" style="stroke:{palette.text};stroke-width:4.2" />
        <path d="{deflected_shape_path}" fill="none" stroke="{calculated_curve_color}" stroke-width="2.8" stroke-opacity="{deflected_stroke_opacity}" stroke-dasharray="7 5" style="fill:none;stroke:{calculated_curve_color};stroke-width:2.8;stroke-opacity:{deflected_stroke_opacity};stroke-dasharray:7 5" />
        {limit_path_html}
        {''.join(support_markup)}
        {''.join(span_labels)}
        {highlight_markup_content}
        {max_point_note_html}
      </svg>
      {legend_html}
      <div style="color:{palette.text};opacity:0.94;font-size:0.82rem;line-height:1.38;margin-top:0.45rem;">{note_text} {vertical_scale_note}</div>
    </div>
    """).strip()


def _selected_deflection_code_for_info() -> DeflectionCodeVersion:
    return _deflection_design_code_from_main_code(DesignCode(st.session_state.design_code))


def _deflection_code_heading_for_info() -> str:
    mapping = {
        DeflectionCodeVersion.ACI318_99: "ACI318-99 - Clause 9.5",
        DeflectionCodeVersion.ACI318_08: "ACI318-08 - Clause 9.5",
        DeflectionCodeVersion.ACI318_11: "ACI318-11 - Clause 9.5",
        DeflectionCodeVersion.ACI318_14: "ACI318-14 - Chapter 24",
        DeflectionCodeVersion.ACI318_19: "ACI318-19 - Chapter 24",
        DeflectionCodeVersion.ACI318_25: "ACI318-25 - Chapter 24",
    }
    return mapping[_selected_deflection_code_for_info()]


def _render_html_fragment(html: str, *, height: int) -> None:
    del height
    st.markdown(html, unsafe_allow_html=True)


def _render_deflection_diagram_fragment(html: str, *, height: int) -> None:
    components.html(html, height=height, scrolling=False)


def _render_overall_deflection_diagram(results) -> None:
    _render_html_fragment(
        _deflection_reference_diagram_html(results, summary_mode=True, palette=LIGHT_THEME),
        height=300,
    )


def _deflection_long_term_clause_for_info() -> str:
    mapping = {
        DeflectionCodeVersion.ACI318_99: "ACI318-99 - Clause 9.5.2.5",
        DeflectionCodeVersion.ACI318_08: "ACI318-08 - Clause 9.5.2.5",
        DeflectionCodeVersion.ACI318_11: "ACI318-11 - Clause 9.5.2.5",
        DeflectionCodeVersion.ACI318_14: "ACI318-14 - Clause 24.2.4",
        DeflectionCodeVersion.ACI318_19: "ACI318-19 - Clause 24.2.4",
        DeflectionCodeVersion.ACI318_25: "ACI318-25 - Clause 24.2.4",
    }
    return mapping[_selected_deflection_code_for_info()]


def _deflection_immediate_clause_for_info() -> str:
    mapping = {
        DeflectionCodeVersion.ACI318_99: "ACI318-99 - Clause 9.5.2 and Clause 9.5.2.3",
        DeflectionCodeVersion.ACI318_08: "ACI318-08 - Clause 9.5.2 and Clause 9.5.2.3",
        DeflectionCodeVersion.ACI318_11: "ACI318-11 - Clause 9.5.2 and Clause 9.5.2.3",
        DeflectionCodeVersion.ACI318_14: "ACI318-14 - Clause 24.2.3 together with Clause 24.2.3.5",
        DeflectionCodeVersion.ACI318_19: "ACI318-19 - Clause 24.2.3 together with Table 24.2.3.5",
        DeflectionCodeVersion.ACI318_25: "ACI318-25 - Clause 24.2.3 together with Table 24.2.3.5",
    }
    return mapping[_selected_deflection_code_for_info()]


def _deflection_limit_info_text() -> str:
    return (
        f"Code reference\n{_deflection_code_heading_for_info()}\n\n"
        "Code-based note:\n"
        f"- {_deflection_code_heading_for_info()} gives the serviceability framework for deflection checks in the selected code version.\n"
        "- In this module, the allowable limit ratio is selected by the engineer; the app does not auto-assign a project limit from the code text.\n\n"
        "Allowable Deflection Limit is selected by the engineer for the project serviceability requirement.\n\n"
        "Available limits in this app:\n"
        "- L/120\n"
        "- L/180\n"
        "- L/240 (default)\n"
        "- L/360\n"
        "- L/480\n"
        "- L/600\n"
        "- Custom\n\n"
        "Typical engineering use of common limits:\n"
        "- The use cases below are engineering guidance in this app and are not directly assigned to these exact ratios by the selected ACI code text.\n"
        "- L/120: very lenient limit; temporary work or noncritical visual serviceability cases.\n"
        "- L/180: light serviceability control where visible deflection is acceptable.\n"
        "- L/240: common general building limit where moderate deflection control is needed.\n"
        "- L/360: typical limit where finishes, partitions, or user comfort require tighter control.\n"
        "- L/480: tighter architectural/serviceability control for more sensitive finishes.\n"
        "- L/600: very strict serviceability target for highly sensitive finishes or appearance requirements.\n"
        "- Custom: use the project-specific requirement when specified by the design criteria.\n\n"
        "Meaning of L in this module:\n"
        "- Simple beam: L = serviceability span length of the simple span being checked.\n"
        "- Continuous, 2 spans: L = serviceability span length of the representative span being checked.\n"
        "- Continuous, 3 or more spans: L = serviceability span length of the representative interior span being checked.\n"
        "- Cantilever placeholder: reserved for future module expansion.\n\n"
        "The app does not assume which project limit governs. The engineer should choose the limit appropriate "
        "for occupancy, finishes, partitions, code interpretation, and project requirements."
    )


def _deflection_service_load_info_text() -> str:
    return (
        f"Code reference\n{_deflection_immediate_clause_for_info()} together with {_deflection_long_term_clause_for_info()}\n\n"
        "Span length L is the serviceability span used in the deflection calculation. Default at startup = 1.0 m.\n\n"
        "DL is calculated automatically from the beam self-weight in this app:\n"
        "DL_auto = b_w x h x gamma_c\n"
        f"with b_w and h in m, and gamma_c = {NORMAL_WEIGHT_CONCRETE_UNIT_WEIGHT_KGF_PER_M3:.0f} kgf/m^3.\n\n"
        "Service LL is the unfactored service live load used for deflection.\n\n"
        "SDL means Additional sustained dead load. It is extra sustained dead load not already included in the beam "
        "self-weight, such as superimposed dead load, permanent equipment, or other long-duration dead load.\n\n"
        "Long-term sustained load used by this module:\n"
        "w_sustained = DL_auto + SDL + (Sustained LL ratio x Service LL)\n\n"
        f"Code reference\n{_deflection_long_term_clause_for_info()}\n\n"
        "Sustained LL ratio is the portion of service live load treated as sustained for the long-term deflection check.\n\n"
        "Input range in this app = 0.00 to 1.00. Startup default in this app = 0.30.\n\n"
        "This is not the same as SDL. SDL is entered directly as kgf/m, while Sustained LL ratio is only the sustained "
        "fraction of Service LL.\n\n"
        "Use a larger value when a greater portion of live load is expected to remain for long duration. Use a smaller "
        "value when most live load is transient.\n\n"
        "The automatic beam self-weight model above is an app load assumption for serviceability input. It is not a "
        "directly prescribed load-calculation clause in ACI.\n\n"
        "This automatic DL is used only in Deflection Check. Strength design for Mu and Vu remains based on the "
        "user-entered factored actions."
    )


def _deflection_long_term_x_info_text() -> str:
    return (
        f"Code reference\n{_deflection_long_term_clause_for_info()}\n\n"
        "Long-term factor x is the time-dependent multiplier used by this app in the additional long-term deflection check.\n\n"
        "Recommended starting values in this workflow:\n"
        "- x = 1.0 for little or no additional long-term amplification\n"
        "- x = 1.4 for moderate sustained loading\n"
        "- x = 2.0 for long-duration sustained loading and conservative design review\n\n"
        "Startup default in this app = 2.0.\n\n"
        "The selected ACI code defines the long-term deflection check framework under the reference above. The engineer "
        "should choose x to match the intended sustained loading duration and service condition."
    )


def _deflection_support_moment_info_text() -> str:
    return (
        f"Code reference\n{_deflection_immediate_clause_for_info()}\n\n"
        "Support service moments are used in the continuous-span Ie,avg candidate in this module.\n\n"
        "Auto mode estimates representative negative support moments for the current workflow.\n"
        "- Continuous, 2 spans: Msup = -wL^2/8\n"
        "- Continuous, 3 or more spans: Msup = -wL^2/12\n\n"
        "In Auto mode, the dead-type support moment uses w = DL_auto + SDL and the live-load support moment uses "
        "w = Service LL, both shown as negative hogging moments.\n\n"
        "Manual mode allows direct entry of negative support moments from the service-load analysis model used for the "
        "continuous beam.\n\n"
        "For continuous spans, this module checks both Ie at midspan and representative Ie,avg, then uses the larger "
        "deflection result."
    )


def _deflection_ie_method_info_text() -> str:
    return (
        f"Code reference\n{_deflection_immediate_clause_for_info()}\n\n"
        "This selector controls how effective moment of inertia is used in the continuous-beam deflection check.\n\n"
        "- Midspan Ie only: use Ie from the midspan section only.\n"
        "- Averaged Ie (midspan + support): calculate Ie at midspan and support, then use the arithmetic average.\n"
        "- Conservative / Worst Case: calculate both methods and use the larger deflection for design.\n\n"
        "For conservative design, the larger deflection from the two Ie evaluation methods is used."
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
        _sync_layer_group_counts_from_selected_diameters(prefix, layer_index)
        group_a_option = st.session_state[f"{prefix}_layer_{layer_index}_group_a_diameter_option"]
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
            _render_warning_banner(
                "Middle Bar requires Corner Bar in the same layer. "
                "This does not satisfy the specified layer arrangement requirement and is not suitable for practical construction."
            )
        if spacing_results is not None:
            layer_spacing = spacing_results.layers()[layer_index - 1]
            if layer_spacing.status == "NOT OK":
                st.markdown(
                    f"<div class='layer-inline-warning'>{_warning_text_to_html(_formalize_constructability_warning_text(layer_spacing.message))}</div>",
                    unsafe_allow_html=True,
                )


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
            f"is less than the minimum required area, A<sub>s,min</sub> = {format_number(design_results.as_min_cm2)} cm<sup>2</sup>. "
            f"{_format_aci_warning_reference_for_ui(_flexural_as_clause_reference_for_ui(preview_inputs.metadata.design_code))}. This does not satisfy the required A<sub>s</sub> limit."
        )
    if (
        preview_inputs.metadata.design_code == DesignCode.ACI318_99
        and design_results.as_provided_cm2 > design_results.as_max_cm2
    ):
        warnings.append(
            f"Provided tension reinforcement area, A<sub>s,total</sub> = {format_number(design_results.as_provided_cm2)} cm<sup>2</sup>, "
            f"exceeds the maximum permitted area, A<sub>s,max</sub> = {format_number(design_results.as_max_cm2)} cm<sup>2</sup>. "
            f"{_format_aci_warning_reference_for_ui(_flexural_as_clause_reference_for_ui(preview_inputs.metadata.design_code))}. This does not satisfy the required A<sub>s</sub> limit."
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
    shear_regions = getattr(preview_results, "shear_regions", ())
    st.markdown(
        "<div class='design-banner info'>"
        f"Current shear &phi; factor = {format_ratio(shear.phi, 3)}."
        "</div>",
        unsafe_allow_html=True,
    )
    if shear_regions:
        mapping_lines = [
            f"{region.region_label} -> {region.design_section_label} ({region.design_status})"
            for region in shear_regions
        ]
        st.markdown(
            "<div class='design-banner info'>"
            f"Governing shear region: {shear.region_label} using {shear.design_section_label}. "
            + " | ".join(mapping_lines)
            + "</div>",
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
        if st.session_state.design_code in {DesignCode.ACI318_19.value, DesignCode.ACI318_25.value}:
            selected_code = DesignCode(st.session_state.design_code)
            vc_action = "Vc is reduced using this factor." if shear.size_effect_applied else "Vc is unchanged because the factor is 1.000."
            st.markdown(
                "<div class='design-banner fail'>"
                f"{_design_code_label_for_ui(selected_code)} size effect check: A<sub>v</sub> &lt; A<sub>v,min</sub>, so &lambda;<sub>s</sub> = {format_ratio(shear.size_effect_factor, 3)}. "
                f"{vc_action} {_format_aci_warning_reference_for_ui(_shear_min_clause_reference_for_ui(selected_code) + f' together with {_design_code_label_for_ui(selected_code)} Table 22.5.5.1')}. "
                "This does not satisfy the minimum shear reinforcement requirement."
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div class='design-banner fail'>"
                f"A<sub>v</sub> &lt; A<sub>v,min</sub>. {_format_aci_warning_reference_for_ui(_shear_min_clause_reference_for_ui(DesignCode(st.session_state.design_code)))}. "
                "This does not satisfy the minimum shear reinforcement requirement."
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
    combined = results.combined_shear_torsion
    min_spacing_cm = AUTO_SHEAR_SPACING_INCREMENT_CM
    upper_limit_cm = combined.required_spacing_cm if combined.active else shear.required_spacing_cm
    governing_reason = combined.spacing_limit_reason if combined.active else "Shear required spacing"
    provided_spacing_cm = combined.stirrup_spacing_cm if combined.active else shear.provided_spacing_cm
    if shear.spacing_mode == ShearSpacingMode.AUTO:
        descriptor = "combined shear + torsion" if combined.active else "required"
        st.info(
            f"Auto selected spacing = {format_number(provided_spacing_cm)} cm "
            f"({descriptor} spacing <= {format_number(upper_limit_cm)} cm; governed by {governing_reason})."
        )
        return

    st.caption(
        f"Manual spacing range used by this app: {format_number(min_spacing_cm)} cm to "
        f"{format_number(upper_limit_cm)} cm."
    )
    if provided_spacing_cm < min_spacing_cm:
        _render_warning_banner(
            f"Provided spacing {format_number(provided_spacing_cm)} cm is below the current minimum "
            f"input range of {format_number(min_spacing_cm)} cm. This does not satisfy the specified input requirement and is not suitable for practical construction."
        )
    elif provided_spacing_cm > upper_limit_cm:
        _render_warning_banner(
            f"Provided spacing {format_number(provided_spacing_cm)} cm does not meet the required maximum "
            f"spacing of {format_number(upper_limit_cm)} cm. Governing limit: {governing_reason}. "
            f"{_format_aci_warning_reference_for_ui(_shear_spacing_clause_reference_for_ui(DesignCode(st.session_state.design_code), combined.active))}. "
            "This does not satisfy the permitted stirrup spacing requirement."
        )
    else:
        st.success(
            f"Provided spacing {format_number(provided_spacing_cm)} cm is within the current required range "
            f"(governed by {governing_reason})."
        )


def render_summary_panel(inputs: BeamDesignInputSet, results, palette) -> None:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    summary_section_number = 8 if inputs.has_negative_design else 7
    if inputs.consider_deflection:
        summary_section_number += 1
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
            stirrup_spacing_cm = results.combined_shear_torsion.stirrup_spacing_cm if results.combined_shear_torsion.active else results.shear.provided_spacing_cm
            rebar_details = build_section_rebar_details(inputs, moment_case, stirrup_spacing_cm)
            st.markdown(_section_rebar_detail_html(rebar_details), unsafe_allow_html=True)
    render_key_metrics(inputs, results, palette)
    render_warnings_and_flags(results)
    st.markdown("</div>", unsafe_allow_html=True)


def render_key_metrics(inputs: BeamDesignInputSet, results, palette) -> None:
    st.markdown(capacity_ratio_legend_html(), unsafe_allow_html=True)
    positive_moment_metrics = [
        ("Beam Behavior", results.positive_bending.beam_behavior_mode, _beam_behavior_summary_note(results.positive_bending)),
        ("Auto Result", results.positive_bending.auto_result or "-", _beam_behavior_auto_note(results.positive_bending)),
        ("R / Threshold", _beam_behavior_ratio_pair(results.positive_bending), "Contribution ratio / Auto threshold"),
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
            ("Beam Behavior", results.negative_bending.beam_behavior_mode, _beam_behavior_summary_note(results.negative_bending)),
            ("Auto Result", results.negative_bending.auto_result or "-", _beam_behavior_auto_note(results.negative_bending)),
            ("R / Threshold", _beam_behavior_ratio_pair(results.negative_bending), "Contribution ratio / Auto threshold"),
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
    combined_metrics: list[tuple[str, object, str]] = []
    combined = results.combined_shear_torsion
    if combined.active:
        combined_metrics = [
            (
                "Capacity Ratio (Shear + Torsion)",
                capacity_ratio_html(combined.capacity_ratio),
                "Combined required transverse reinforcement / provided transverse reinforcement",
            ),
            ("V<sub>u</sub>", format_number(combined.vu_kg), "kgf"),
            ("T<sub>u</sub>", format_number(combined.tu_kgfm), "kgf-m"),
            (
                "Section stress ratio",
                capacity_ratio_html(combined.cross_section_limit_ratio) if combined.cross_section_limit_check_applied else "-",
                combined.cross_section_limit_clause or "Combined section limit not applied",
            ),
            (
                "Req. transverse",
                f"{combined.combined_required_transverse_mm2_per_mm:.6f}",
                "mm<sup>2</sup>/mm",
            ),
            (
                "Prov. transverse",
                f"{combined.provided_transverse_mm2_per_mm:.6f}",
                "mm<sup>2</sup>/mm",
            ),
            (
                "Stirrups",
                f"&phi;{combined.stirrup_diameter_mm} mm / {combined.stirrup_legs} legs @ {format_number(combined.stirrup_spacing_cm)} cm",
                combined.design_status,
            ),
            ("Pass / Fail", combined.design_status, "Shared closed stirrup check"),
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
    if combined.active:
        _render_metric_group(
            "Shear & Torsion",
            combined_metrics,
            palette,
            extra_html=_build_shear_torsion_interaction_diagram_html(combined, palette, results.torsion),
        )
    else:
        _render_metric_group("Shear", shear_metrics, palette)
        if inputs.torsion.enabled and combined.torsion_ignored:
            st.markdown(
                f"<div class='design-banner info'>{combined.ignore_message}</div>",
                unsafe_allow_html=True,
            )
        elif inputs.torsion.enabled:
            torsion_metrics = [
                ("T<sub>u</sub>", format_number(results.torsion.tu_kgfm), "kgf-m"),
                ("Threshold", format_number(results.torsion.threshold_torsion_kgfm), "kgf-m"),
                ("Status", results.torsion.status, _torsion_warning_summary(results.torsion)),
            ]
            _render_metric_group("Torsion", torsion_metrics, palette)
    if inputs.consider_deflection:
        deflection_metrics = [
            ("Ie method", results.deflection.ie_method_governing or results.deflection.ie_method_selected, results.deflection.ie_method_selected),
            ("Allowable deflection", format_number(results.deflection.allowable_deflection_cm), "cm"),
            ("Calculated deflection", format_number(results.deflection.calculated_deflection_cm), "cm"),
            (
                "Capacity Ratio (Deflection)",
                capacity_ratio_html(results.deflection.capacity_ratio),
                "Calculated / Allowable",
            ),
            ("Immediate total", format_number(results.deflection.immediate_total_deflection_cm), "cm"),
            ("Long-term additional", format_number(results.deflection.additional_long_term_deflection_cm), "cm"),
            ("Pass / Fail", results.deflection.status, results.deflection.pass_fail_summary or results.deflection.note),
        ]
        if results.deflection.method_2_total_service_deflection_cm is not None:
            deflection_metrics.insert(3, ("Method 1", format_number(results.deflection.method_1_total_service_deflection_cm), "cm"))
            deflection_metrics.insert(4, ("Method 2", format_number(results.deflection.method_2_total_service_deflection_cm), "cm"))
        _render_metric_group(
            "Deflection",
            deflection_metrics,
            palette,
        )
        _render_overall_deflection_diagram(results)
    overall_label = results.overall_status
    if overall_label == "DOES NOT MEET REQUIREMENTS":
        overall_label = "DOES NOT MEET DESIGN REQUIREMENTS"
    st.markdown(overall_status_card_html(overall_label, "", palette), unsafe_allow_html=True)


def render_summary_panel(inputs: BeamDesignInputSet, results, palette) -> None:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    summary_section_number = 6 + len(inputs.active_flexural_sections)
    if inputs.consider_deflection:
        summary_section_number += 1
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;align-items:center;gap:1rem;'>"
        f"<div><div class='hero-title' style='font-size:1.25rem;'>{summary_section_number}. Overall Summary</div>"
        f"<div class='hero-subtitle'>Live results update with every input change.</div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    summary_lines = [f"Beam Type: {inputs.beam_type.value}"]
    if inputs.beam_type in {BeamType.SIMPLE, BeamType.CONTINUOUS}:
        summary_lines.append(f"Include Cantilever Span: {'Yes' if inputs.include_cantilever_span else 'No'}")
    summary_lines.append(f"Sections: {', '.join(label for _, label in inputs.active_flexural_sections)}")
    for line in summary_lines:
        st.markdown(f"<div class='design-banner info'>{line}</div>", unsafe_allow_html=True)
    section_specs = beam_section_specs(inputs)
    drawing_transform = shared_drawing_transform(inputs)
    section_columns = st.columns(len(section_specs), gap="medium")
    for column, (title, moment_case) in zip(section_columns, section_specs):
        with column:
            st.markdown(f"<div class='section-label'>{title} Section</div>", unsafe_allow_html=True)
            st.markdown(build_beam_section_svg(inputs, palette, moment_case, transform=drawing_transform), unsafe_allow_html=True)
            stirrup_spacing_cm = results.combined_shear_torsion.stirrup_spacing_cm if results.combined_shear_torsion.active else results.shear.provided_spacing_cm
            rebar_details = build_section_rebar_details(inputs, moment_case, stirrup_spacing_cm)
            st.markdown(_section_rebar_detail_html(rebar_details), unsafe_allow_html=True)
    render_key_metrics(inputs, results, palette)
    render_warnings_and_flags(results)
    st.markdown("</div>", unsafe_allow_html=True)


def _flexural_metric_rows(flexural_result) -> list[tuple[str, object, str]]:
    return [
        ("Beam Behavior", flexural_result.beam_behavior_mode, _beam_behavior_summary_note(flexural_result)),
        ("Auto Result", flexural_result.auto_result or "-", _beam_behavior_auto_note(flexural_result)),
        ("R / Threshold", _beam_behavior_ratio_pair(flexural_result), "Contribution ratio / Auto threshold"),
        ("M<sub>u</sub> / &phi;M<sub>n</sub>", capacity_ratio_html(flexural_result.ratio), "Moment capacity ratio"),
        ("A<sub>s,req</sub>", format_number(flexural_result.as_required_cm2), "cm<sup>2</sup>"),
        ("A<sub>s,prov</sub>", format_number(flexural_result.as_provided_cm2), flexural_result.as_status),
        ("A<sub>s,min</sub> / A<sub>s,max</sub>", f"{format_number(flexural_result.as_min_cm2)} / {format_number(flexural_result.as_max_cm2)}", "cm<sup>2</sup>"),
        ("&rho;", format_ratio(flexural_result.rho_provided), "Provided reinforcement ratio"),
        ("&phi;M<sub>n</sub>", format_number(flexural_result.phi_mn_kgm), flexural_result.ratio_status),
    ]


def render_key_metrics(inputs: BeamDesignInputSet, results, palette) -> None:
    st.markdown(capacity_ratio_legend_html(), unsafe_allow_html=True)
    flexural_groups: list[tuple[str, object]] = []
    if inputs.has_positive_design:
        flexural_groups.append(("Positive Moment", results.positive_bending))
    if inputs.has_support_negative_design and results.negative_bending is not None:
        flexural_groups.append(("Negative Moment", results.negative_bending))
    if inputs.has_cantilever_negative_design and results.cantilever_negative_bending is not None:
        flexural_groups.append(("Cantilever Negative Moment", results.cantilever_negative_bending))
    shear_metrics = [
        ("V<sub>u</sub> / &phi;V<sub>n</sub>", capacity_ratio_html(results.shear.capacity_ratio), "Shear capacity ratio"),
        ("V<sub>u</sub>", format_number(inputs.shear.factored_shear_kg), "kg"),
        ("V<sub>n</sub>", format_number(results.shear.vn_kg), "kg"),
        ("&phi;V<sub>n</sub>", format_number(results.shear.phi_vn_kg), results.shear.design_status),
        ("&phi;V<sub>c</sub>", format_number(results.shear.phi_vc_kg), "kg"),
        ("&phi;V<sub>s</sub>", format_number(results.shear.phi_vs_provided_kg), f"{results.shear.spacing_mode.value} spacing"),
        ("s<sub>stirrup</sub>", format_number(results.shear.provided_spacing_cm), f"{results.shear.spacing_mode.value} | s<sub>req</sub> <= {format_number(results.shear.required_spacing_cm)} cm"),
        ("Spacing check", results.beam_geometry.positive_tension_spacing.overall_status, "Positive tension layers"),
    ]
    combined_metrics: list[tuple[str, object, str]] = []
    combined = results.combined_shear_torsion
    if combined.active:
        combined_metrics = [
            ("Capacity Ratio (Shear + Torsion)", capacity_ratio_html(combined.capacity_ratio), "Combined required transverse reinforcement / provided transverse reinforcement"),
            ("V<sub>u</sub>", format_number(combined.vu_kg), "kgf"),
            ("T<sub>u</sub>", format_number(combined.tu_kgfm), "kgf-m"),
            ("Section stress ratio", capacity_ratio_html(combined.cross_section_limit_ratio) if combined.cross_section_limit_check_applied else "-", combined.cross_section_limit_clause or "Combined section limit not applied"),
            ("Req. transverse", f"{combined.combined_required_transverse_mm2_per_mm:.6f}", "mm<sup>2</sup>/mm"),
            ("Prov. transverse", f"{combined.provided_transverse_mm2_per_mm:.6f}", "mm<sup>2</sup>/mm"),
            ("Stirrups", f"&phi;{combined.stirrup_diameter_mm} mm / {combined.stirrup_legs} legs @ {format_number(combined.stirrup_spacing_cm)} cm", combined.design_status),
            ("Pass / Fail", combined.design_status, "Shared closed stirrup check"),
        ]
    for group_title, flexural_result in flexural_groups:
        chart_html = build_flexural_phi_chart_svg(
            palette,
            PhiFlexureChartState(
                title=f"{group_title} Flexural Ï†",
                design_code=inputs.metadata.design_code,
                et=flexural_result.et,
                ety=flexural_result.ety,
                phi=flexural_result.phi,
            ),
        )
        _render_metric_group(group_title, _flexural_metric_rows(flexural_result), palette, extra_html=chart_html)
    if combined.active:
        _render_metric_group("Shear & Torsion", combined_metrics, palette, extra_html=_build_shear_torsion_interaction_diagram_html(combined, palette, results.torsion))
    else:
        _render_metric_group("Shear", shear_metrics, palette)
        if inputs.torsion.enabled and combined.torsion_ignored:
            st.markdown(f"<div class='design-banner info'>{combined.ignore_message}</div>", unsafe_allow_html=True)
        elif inputs.torsion.enabled:
            torsion_metrics = [("T<sub>u</sub>", format_number(results.torsion.tu_kgfm), "kgf-m"), ("Threshold", format_number(results.torsion.threshold_torsion_kgfm), "kgf-m"), ("Status", results.torsion.status, _torsion_warning_summary(results.torsion))]
            _render_metric_group("Torsion", torsion_metrics, palette)
    if inputs.consider_deflection:
        deflection_metrics = [
            ("Ie method", results.deflection.ie_method_governing or results.deflection.ie_method_selected, results.deflection.ie_method_selected),
            ("Allowable deflection", format_number(results.deflection.allowable_deflection_cm), "cm"),
            ("Calculated deflection", format_number(results.deflection.calculated_deflection_cm), "cm"),
            ("Capacity Ratio (Deflection)", capacity_ratio_html(results.deflection.capacity_ratio), "Calculated / Allowable"),
            ("Immediate total", format_number(results.deflection.immediate_total_deflection_cm), "cm"),
            ("Long-term additional", format_number(results.deflection.additional_long_term_deflection_cm), "cm"),
            ("Pass / Fail", results.deflection.status, results.deflection.pass_fail_summary or results.deflection.note),
        ]
        if results.deflection.method_2_total_service_deflection_cm is not None:
            deflection_metrics.insert(3, ("Method 1", format_number(results.deflection.method_1_total_service_deflection_cm), "cm"))
            deflection_metrics.insert(4, ("Method 2", format_number(results.deflection.method_2_total_service_deflection_cm), "cm"))
        _render_metric_group("Deflection", deflection_metrics, palette)
        _render_overall_deflection_diagram(results)
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
        if "deflection-reference-diagram-card" in extra_html:
            _render_html_fragment(extra_html, height=300)
        else:
            st.markdown(extra_html, unsafe_allow_html=True)


def _build_shear_torsion_interaction_diagram_html(combined, palette, torsion_results=None) -> str:
    if not combined.active or combined.provided_transverse_mm2_per_mm <= 0:
        return ""

    # Shared closed-stirrup interaction check:
    # x = shear-required transverse reinforcement / provided transverse reinforcement
    # y = torsion-required transverse reinforcement / provided transverse reinforcement
    # Pass condition = x + y <= 1.0
    shear_ratio = combined.shear_required_transverse_mm2_per_mm / combined.provided_transverse_mm2_per_mm
    torsion_ratio = combined.torsion_required_transverse_mm2_per_mm / combined.provided_transverse_mm2_per_mm
    combined_ratio = shear_ratio + torsion_ratio
    axis_limit = min(max(1.1, shear_ratio, torsion_ratio, combined_ratio) * 1.1, 2.5)

    width = 320.0
    height = 240.0
    padding_left = 48.0
    padding_right = 18.0
    padding_top = 18.0
    padding_bottom = 42.0
    plot_width = width - padding_left - padding_right
    plot_height = height - padding_top - padding_bottom

    def sx(value: float) -> float:
        return padding_left + (value / axis_limit) * plot_width

    def sy(value: float) -> float:
        return padding_top + plot_height - (value / axis_limit) * plot_height

    status_color = palette.ok if combined.design_status == "PASS" else palette.fail
    pass_fill = palette.ok if combined.design_status == "PASS" else palette.warning
    demand_x = min(shear_ratio, axis_limit)
    demand_y = min(torsion_ratio, axis_limit)
    x_ticks = [0.0, 0.5, 1.0, axis_limit]
    y_ticks = [0.0, 0.5, 1.0, axis_limit]

    x_tick_markup = []
    for tick in x_ticks:
        tick_x = sx(tick)
        x_tick_markup.append(
            f"<line x1='{tick_x:.2f}' y1='{padding_top + plot_height:.2f}' x2='{tick_x:.2f}' y2='{padding_top + plot_height + 5:.2f}' stroke='{palette.muted_text}' stroke-width='1' />"
            f"<text x='{tick_x:.2f}' y='{height - 12:.2f}' text-anchor='middle' font-size='9.5' fill='{palette.muted_text}'>{tick:.2f}</text>"
        )
    y_tick_markup = []
    for tick in y_ticks:
        tick_y = sy(tick)
        y_tick_markup.append(
            f"<line x1='{padding_left - 5:.2f}' y1='{tick_y:.2f}' x2='{padding_left:.2f}' y2='{tick_y:.2f}' stroke='{palette.muted_text}' stroke-width='1' />"
            f"<text x='{padding_left - 8:.2f}' y='{tick_y + 3:.2f}' text-anchor='end' font-size='9.5' fill='{palette.muted_text}'>{tick:.2f}</text>"
        )

    pass_region_points = (
        f"{sx(0.0):.2f},{sy(0.0):.2f} "
        f"{sx(0.0):.2f},{sy(1.0):.2f} "
        f"{sx(1.0):.2f},{sy(0.0):.2f}"
    )
    demand_point_x = sx(demand_x)
    demand_point_y = sy(demand_y)

    warning_html = ""
    torsion_warning_text = _torsion_warning_summary(torsion_results)
    if torsion_results is not None and torsion_warning_text and torsion_warning_text != torsion_results.pass_fail_summary:
        warning_html = f"<div class='design-banner fail'>{torsion_warning_text}</div>"

    solid_section_graph_html = ""
    if combined.cross_section_limit_check_applied and combined.cross_section_limit_rhs_mpa > 0:
        solid_axis_limit = min(
            max(
                1.0,
                combined.shear_section_stress_mpa / combined.cross_section_limit_rhs_mpa,
                combined.torsion_section_stress_mpa / combined.cross_section_limit_rhs_mpa,
            ) * 1.15,
            2.5,
        )
        solid_width = width
        solid_height = height
        solid_padding_left = padding_left
        solid_padding_right = padding_right
        solid_padding_top = 18.0
        solid_padding_bottom = 42.0
        solid_plot_width = solid_width - solid_padding_left - solid_padding_right
        solid_plot_height = solid_height - solid_padding_top - solid_padding_bottom

        def ssx(value: float) -> float:
            return solid_padding_left + (value / solid_axis_limit) * solid_plot_width

        def ssy(value: float) -> float:
            return solid_padding_top + solid_plot_height - (value / solid_axis_limit) * solid_plot_height

        solid_ticks = [0.0, 0.5, 1.0, solid_axis_limit]
        solid_x_tick_markup = []
        solid_y_tick_markup = []
        for tick in solid_ticks:
            tick_x = ssx(tick)
            tick_y = ssy(tick)
            solid_x_tick_markup.append(
                f"<line x1='{tick_x:.2f}' y1='{solid_padding_top + solid_plot_height:.2f}' x2='{tick_x:.2f}' y2='{solid_padding_top + solid_plot_height + 5:.2f}' stroke='{palette.muted_text}' stroke-width='1' />"
                f"<text x='{tick_x:.2f}' y='{solid_height - 12:.2f}' text-anchor='middle' font-size='9.5' fill='{palette.muted_text}'>{tick:.2f}</text>"
            )
            solid_y_tick_markup.append(
                f"<line x1='{solid_padding_left - 5:.2f}' y1='{tick_y:.2f}' x2='{solid_padding_left:.2f}' y2='{tick_y:.2f}' stroke='{palette.muted_text}' stroke-width='1' />"
                f"<text x='{solid_padding_left - 8:.2f}' y='{tick_y + 3:.2f}' text-anchor='end' font-size='9.5' fill='{palette.muted_text}'>{tick:.2f}</text>"
            )

        curve_points = []
        for index in range(51):
            x_value = solid_axis_limit * index / 50.0
            if x_value <= 1.0:
                y_value = math.sqrt(max(1.0 - (x_value**2), 0.0))
            else:
                y_value = 0.0
            curve_points.append(f"{ssx(x_value):.2f},{ssy(y_value):.2f}")
        solid_curve_points = " ".join(curve_points)
        solid_demand_x = min(combined.shear_section_stress_mpa / combined.cross_section_limit_rhs_mpa, solid_axis_limit)
        solid_demand_y = min(combined.torsion_section_stress_mpa / combined.cross_section_limit_rhs_mpa, solid_axis_limit)
        solid_demand_point_x = ssx(solid_demand_x)
        solid_demand_point_y = ssy(solid_demand_y)

        solid_section_graph_html = f"""
    <div class="metric-card" style="margin-top:0.85rem;">
      <div class="section-label">Solid Section Combined Section-Limit Diagram</div>
      <svg width="100%" style="display:block;max-width:{solid_width:.0f}px;margin:0 auto;" viewBox="0 0 {solid_width:.0f} {solid_height:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Solid-section combined section-limit diagram">
        <rect x="0" y="0" width="{solid_width:.0f}" height="{solid_height:.0f}" rx="14" fill="{palette.surface_alt}" />
        <rect x="{solid_padding_left:.2f}" y="{solid_padding_top:.2f}" width="{solid_plot_width:.2f}" height="{solid_plot_height:.2f}" rx="12" fill="{palette.surface}" stroke="{palette.border}" stroke-width="1.3" />
        <line x1="{solid_padding_left:.2f}" y1="{solid_padding_top + solid_plot_height:.2f}" x2="{solid_padding_left + solid_plot_width:.2f}" y2="{solid_padding_top + solid_plot_height:.2f}" stroke="{palette.text}" stroke-width="1.8" />
        <line x1="{solid_padding_left:.2f}" y1="{solid_padding_top + solid_plot_height:.2f}" x2="{solid_padding_left:.2f}" y2="{solid_padding_top:.2f}" stroke="{palette.text}" stroke-width="1.8" />
        <polyline points="{solid_curve_points}" fill="none" stroke="{palette.text}" stroke-width="2" stroke-dasharray="5 4" />
        {''.join(solid_x_tick_markup)}
        {''.join(solid_y_tick_markup)}
        <line x1="{solid_demand_point_x:.2f}" y1="{solid_padding_top + solid_plot_height:.2f}" x2="{solid_demand_point_x:.2f}" y2="{solid_demand_point_y:.2f}" stroke="{status_color}" stroke-width="1.4" stroke-opacity="0.7" stroke-dasharray="4 4" />
        <line x1="{solid_padding_left:.2f}" y1="{solid_demand_point_y:.2f}" x2="{solid_demand_point_x:.2f}" y2="{solid_demand_point_y:.2f}" stroke="{status_color}" stroke-width="1.4" stroke-opacity="0.7" stroke-dasharray="4 4" />
        <circle cx="{solid_demand_point_x:.2f}" cy="{solid_demand_point_y:.2f}" r="5.5" fill="{status_color}" stroke="{palette.surface}" stroke-width="2" />
        <text x="{solid_demand_point_x + 8:.2f}" y="{solid_demand_point_y - 8:.2f}" font-size="10" font-weight="600" fill="{status_color}">Demand point</text>
        <text x="{solid_padding_left + solid_plot_width / 2:.2f}" y="{solid_height - 2:.2f}" text-anchor="middle" font-size="10.5" font-weight="600" fill="{palette.text}">Shear stress / limit stress</text>
        <text x="14" y="{solid_padding_top + solid_plot_height / 2:.2f}" text-anchor="middle" font-size="10.5" font-weight="600" fill="{palette.text}" transform="rotate(-90 14 {solid_padding_top + solid_plot_height / 2:.2f})">Torsion stress / limit stress</text>
      </svg>
      <div class="metric-note">
        Solid-section check uses (x<sup>2</sup> + y<sup>2</sup>)<sup>1/2</sup> &le; 1.00 on the section-stress basis.
        Demand point = ({combined.shear_section_stress_mpa / combined.cross_section_limit_rhs_mpa:.3f}, {combined.torsion_section_stress_mpa / combined.cross_section_limit_rhs_mpa:.3f}),
        combined ratio = {combined.cross_section_limit_ratio:.3f}.
      </div>
    </div>
"""

    return f"""
    <div class="metric-card">
      <div class="section-label">Shear&ndash;Torsion Interaction Diagram</div>
      <svg width="100%" style="display:block;max-width:{width:.0f}px;margin:0 auto;" viewBox="0 0 {width:.0f} {height:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Shear-Torsion interaction diagram">
        <rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" rx="14" fill="{palette.surface_alt}" />
        <rect x="{padding_left:.2f}" y="{padding_top:.2f}" width="{plot_width:.2f}" height="{plot_height:.2f}" rx="12" fill="{palette.surface}" stroke="{palette.border}" stroke-width="1.3" />
        <polygon points="{pass_region_points}" fill="{pass_fill}" fill-opacity="0.14" />
        <line x1="{sx(0.0):.2f}" y1="{sy(1.0):.2f}" x2="{sx(1.0):.2f}" y2="{sy(0.0):.2f}" stroke="{palette.text}" stroke-width="2" stroke-dasharray="5 4" />
        <line x1="{padding_left:.2f}" y1="{padding_top + plot_height:.2f}" x2="{padding_left + plot_width:.2f}" y2="{padding_top + plot_height:.2f}" stroke="{palette.text}" stroke-width="1.8" />
        <line x1="{padding_left:.2f}" y1="{padding_top + plot_height:.2f}" x2="{padding_left:.2f}" y2="{padding_top:.2f}" stroke="{palette.text}" stroke-width="1.8" />
        {''.join(x_tick_markup)}
        {''.join(y_tick_markup)}
        <line x1="{demand_point_x:.2f}" y1="{padding_top + plot_height:.2f}" x2="{demand_point_x:.2f}" y2="{demand_point_y:.2f}" stroke="{status_color}" stroke-width="1.4" stroke-opacity="0.7" stroke-dasharray="4 4" />
        <line x1="{padding_left:.2f}" y1="{demand_point_y:.2f}" x2="{demand_point_x:.2f}" y2="{demand_point_y:.2f}" stroke="{status_color}" stroke-width="1.4" stroke-opacity="0.7" stroke-dasharray="4 4" />
        <circle cx="{demand_point_x:.2f}" cy="{demand_point_y:.2f}" r="5.5" fill="{status_color}" stroke="{palette.surface}" stroke-width="2" />
        <text x="{demand_point_x + 8:.2f}" y="{demand_point_y - 8:.2f}" font-size="10" font-weight="600" fill="{status_color}">Demand point</text>
        <text x="{padding_left + plot_width / 2:.2f}" y="{height - 2:.2f}" text-anchor="middle" font-size="10.5" font-weight="600" fill="{palette.text}">Shear ratio</text>
        <text x="14" y="{padding_top + plot_height / 2:.2f}" text-anchor="middle" font-size="10.5" font-weight="600" fill="{palette.text}" transform="rotate(-90 14 {padding_top + plot_height / 2:.2f})">Torsion ratio</text>
      </svg>
      <div class="metric-note">
        Interaction check uses x + y &le; 1.00 on the shared closed-stirrup basis.
        Demand point = ({shear_ratio:.3f}, {torsion_ratio:.3f}),
        combined ratio = {combined_ratio:.3f}.
      </div>
    </div>
    {solid_section_graph_html}
    {warning_html}
    """


def _torsion_warning_summary(torsion_results) -> str:
    if torsion_results is None:
        return ""
    if torsion_results.warnings:
        return " ".join(torsion_results.warnings)
    return torsion_results.pass_fail_summary


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
    tab_labels = ["Warnings"]
    if results.review_flags:
        tab_labels.append("Review Flags")
    tab_labels.append("Raw Results")
    summary_tabs = st.tabs(tab_labels)
    with summary_tabs[0]:
        if not results.warnings:
            st.success("No immediate reinforcement or spacing warnings.")
        for warning in results.warnings:
            _render_warning_banner(warning)
    raw_tab_index = 1
    if results.review_flags:
        with summary_tabs[1]:
            for flag in results.review_flags:
                st.markdown(
                    f"<div class='metric-card'><div class='metric-label'>{flag.title}</div>"
                    f"<div class='metric-value' style='font-size:0.95rem'>{flag.message}</div>"
                    f"<div class='metric-note'>{flag.severity.title()} | {flag.verification_status.value}</div></div>",
                    unsafe_allow_html=True,
                )
        raw_tab_index = 2
    with summary_tabs[raw_tab_index]:
        st.json(dataclass_to_dict(results), expanded=False)


def build_inputs_from_state() -> BeamDesignInputSet:
    main_steel_yield_ksc = _resolved_grade_value("fy_grade_option", "fy_ksc")
    shear_steel_yield_ksc = _resolved_grade_value("fvy_grade_option", "fvy_ksc")
    torsion_longitudinal_fy_ksc = _resolved_grade_value("torsion_longitudinal_fy_grade_option", "torsion_longitudinal_fy_ksc")
    automatic_deflection_dead_load_kgf_per_m = _automatic_deflection_dead_load_from_state()
    resolved_support_dead_moment_kgm, resolved_support_live_moment_kgm = _resolved_deflection_support_moments_from_state()
    resolved_deflection_ie_method = _resolved_deflection_ie_method_from_state()
    return BeamDesignInputSet(
        beam_type=BeamType(st.session_state.beam_type),
        include_cantilever_span=bool(st.session_state.get("include_cantilever_span", False)),
        beam_behavior_mode=BeamBehaviorMode(st.session_state.beam_behavior_mode),
        auto_beam_behavior_threshold_ratio=_clamp_beam_behavior_threshold_ratio(
            float(st.session_state.auto_beam_behavior_threshold_percent) / 100.0
        ),
        consider_deflection=bool(st.session_state.consider_deflection),
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
            main_steel_yield_ksc=main_steel_yield_ksc,
            shear_steel_yield_ksc=shear_steel_yield_ksc,
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
        simple_support_bending=SimpleSupportBendingInput(
            moment_mode=DemandInputMode(st.session_state.get("support_mu_mode", DemandInputMode.AUTO.value)),
            factored_moment_kgm=float(st.session_state.get("support_mu_kgm", 0.0)),
            compression_reinforcement=_build_arrangement_from_state("sb_comp"),
            tension_reinforcement=_build_arrangement_from_state("sb_tens"),
        ),
        shear=ShearDesignInput(
            factored_shear_kg=float(st.session_state.get("support_vu_kg", st.session_state.vu_kg)),
            support_factored_shear_kg=float(st.session_state.get("support_vu_kg", st.session_state.vu_kg)),
            span_region_factored_shear_kg=float(st.session_state.get("span_vu_kg", st.session_state.get("support_vu_kg", st.session_state.vu_kg))),
            cantilever_factored_shear_kg=float(st.session_state.get("cantilever_vu_kg", st.session_state.get("support_vu_kg", st.session_state.vu_kg))),
            span_region_mode=DemandInputMode(st.session_state.get("span_vu_mode", DemandInputMode.AUTO.value)),
            span_region_relative_position=float(st.session_state.get("span_vu_position_ratio", 0.25)),
            stirrup_diameter_mm=_resolved_diameter_value("stirrup_diameter_option", "stirrup_diameter_mm", allow_empty=False),
            legs_per_plane=int(st.session_state.legs_per_plane),
            spacing_mode=ShearSpacingMode(st.session_state.shear_spacing_mode),
            provided_spacing_cm=float(st.session_state.shear_spacing_cm),
        ),
        torsion=TorsionDesignInput(
            enabled=bool(st.session_state.include_torsion_design),
            factored_torsion_kgfm=float(st.session_state.torsion_tu_kgfm),
            design_code=_torsion_design_code_from_main_code(DesignCode(st.session_state.design_code)),
            demand_type=TorsionDemandType(st.session_state.torsion_demand_type),
            provided_longitudinal_steel_cm2=_torsion_longitudinal_area_from_state(),
            provided_longitudinal_bar_diameter_mm=(
                _resolved_diameter_value(
                    "torsion_longitudinal_diameter_option",
                    "torsion_longitudinal_diameter_mm",
                    allow_empty=True,
                )
                or None
            ),
            provided_longitudinal_bar_count=int(st.session_state.torsion_longitudinal_count),
            provided_longitudinal_bar_fy_ksc=torsion_longitudinal_fy_ksc,
        ),
        negative_bending=NegativeBendingInput(
            factored_moment_kgm=float(st.session_state.negative_mu_kgm),
            compression_reinforcement=_build_arrangement_from_state("nb_comp"),
            tension_reinforcement=_build_arrangement_from_state("nb_tens"),
        ),
        cantilever_negative_bending=NegativeBendingInput(
            factored_moment_kgm=float(st.session_state.cantilever_negative_mu_kgm),
            compression_reinforcement=_build_arrangement_from_state("cb_comp"),
            tension_reinforcement=_build_arrangement_from_state("cb_tens"),
        ),
        deflection=DeflectionCheckInput(
            design_code=_deflection_design_code_from_main_code(DesignCode(st.session_state.design_code)),
            member_type=DeflectionMemberType(st.session_state.deflection_member_type),
            support_condition=DeflectionSupportCondition(st.session_state.deflection_support_condition),
            ie_method=resolved_deflection_ie_method,
            allowable_limit_preset=AllowableDeflectionPreset(st.session_state.deflection_allowable_limit_preset),
            allowable_limit_custom_denominator=int(st.session_state.deflection_allowable_limit_custom_denominator),
            long_term_factor_x=float(st.session_state.deflection_long_term_factor_x),
            beam_type=DeflectionBeamType(st.session_state.deflection_beam_type),
            beam_type_factor_x=float(st.session_state.beam_type_factor_x),
            span_length_m=float(st.session_state.span_length_m),
            service_dead_load_kgf_per_m=automatic_deflection_dead_load_kgf_per_m,
            service_live_load_kgf_per_m=float(st.session_state.deflection_service_live_load_kgf_per_m),
            additional_sustained_load_kgf_per_m=float(st.session_state.deflection_additional_sustained_load_kgf_per_m),
            sustained_live_load_ratio=float(st.session_state.deflection_sustained_live_load_ratio),
            support_dead_load_service_moment_kgm=resolved_support_dead_moment_kgm,
            support_live_load_service_moment_kgm=resolved_support_live_moment_kgm,
            midspan_dead_load_service_moment_kgm=float(st.session_state.midspan_dead_load_service_moment_kgm),
            midspan_live_load_service_moment_kgm=float(st.session_state.midspan_live_load_service_moment_kgm),
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


def _beam_type_ui_options() -> list[str]:
    return [
        BeamType.SIMPLE.value,
        BeamType.CONTINUOUS.value,
        BeamType.STANDALONE_CANTILEVER.value,
    ]


def _selected_include_cantilever_span() -> bool:
    if _selected_beam_type() not in {BeamType.SIMPLE, BeamType.CONTINUOUS}:
        return False
    return bool(st.session_state.get("include_cantilever_span", False))


def _active_flexural_section_specs_from_state() -> list[tuple[str, str]]:
    return _active_flexural_section_specs(_selected_beam_type(), _selected_include_cantilever_span())


def _active_flexural_section_specs(beam_type: BeamType, include_cantilever_span: bool) -> list[tuple[str, str]]:
    if beam_type == BeamType.STANDALONE_CANTILEVER:
        return [("Cantilever Negative Section", "cantilever_negative")]
    if beam_type == BeamType.SIMPLE:
        sections = [
            ("Middle Section", "middle"),
            ("Support Section", "support"),
        ]
        if include_cantilever_span:
            sections.append(("Cantilever Negative Section", "cantilever_negative"))
        return sections
    sections = [
        ("Positive Section", "positive"),
        ("Negative Section", "negative"),
    ]
    if include_cantilever_span:
        sections.append(("Cantilever Negative Section", "cantilever_negative"))
    return sections


def _shear_section_number() -> int:
    return _shear_section_number_for(_selected_beam_type(), _selected_include_cantilever_span())


def _shear_section_number_for(beam_type: BeamType, include_cantilever_span: bool) -> int:
    return 5 + len(_active_flexural_section_specs(beam_type, include_cantilever_span))


def _active_vu_region_specs(beam_type: BeamType, include_cantilever_span: bool) -> list[tuple[str, str, str]]:
    if beam_type == BeamType.STANDALONE_CANTILEVER:
        return [("cantilever", "Cantilever Vu", "Cantilever Negative Section")]
    if beam_type == BeamType.SIMPLE:
        regions = [
            ("support", "Support Vu", "Support Section"),
            ("middle", "Middle-region Vu", "Middle Section"),
        ]
        if include_cantilever_span:
            regions.append(("cantilever", "Cantilever Vu", "Cantilever Negative Section"))
        return regions
    regions = [
        ("support", "Support Vu", "Negative Section"),
        ("span_region", "Span-region Vu", "Positive Section"),
    ]
    if include_cantilever_span:
        regions.append(("cantilever", "Cantilever Vu", "Cantilever Negative Section"))
    return regions


def _deflection_section_number() -> int:
    return _shear_section_number() + 1


def _shear_design_section_label(include_torsion: bool, beam_type: BeamType) -> str:
    include_cantilever_span = False
    if "include_cantilever_span" in st.session_state:
        include_cantilever_span = bool(st.session_state.get("include_cantilever_span", False))
    section_number = _shear_section_number_for(beam_type, include_cantilever_span if beam_type in {BeamType.SIMPLE, BeamType.CONTINUOUS} else False)
    if include_torsion:
        return f"{section_number}. Shear & Torsion Design"
    return f"{section_number}. Shear Design"


def _torsion_detail_inputs_required(preview_results) -> bool:
    if preview_results is None:
        return True
    return not preview_results.combined_shear_torsion.torsion_ignored


def _resolved_project_date() -> str:
    if st.session_state.project_date_mode == "Auto":
        return str(st.session_state.project_date_auto_value)
    return str(st.session_state.project_date)


def _current_timestamp_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _clamp_beam_behavior_threshold_ratio(value: float) -> float:
    return max(0.0, min(1.0, value))


def _beam_behavior_ratio_pair(results) -> str:
    return (
        f"{format_number(results.behavior_contribution_ratio_r * 100.0)}% / "
        f"{format_number(results.behavior_threshold_r * 100.0)}%"
    )


def _beam_behavior_summary_note(results) -> str:
    if results.beam_behavior_mode == BeamBehaviorMode.AUTO.value:
        return f"Auto Result: {results.auto_result or results.effective_beam_behavior}"
    return f"Effective: {results.effective_beam_behavior}"


def _beam_behavior_auto_note(results) -> str:
    if results.beam_behavior_mode != BeamBehaviorMode.AUTO.value:
        return "Only used when Beam Behavior = Auto"
    return f"Effective flexural classification: {results.effective_beam_behavior}"


def _torsion_design_code_from_main_code(design_code: DesignCode) -> TorsionDesignCode:
    return TorsionDesignCode[design_code.name]


def _deflection_design_code_from_main_code(design_code: DesignCode) -> DeflectionCodeVersion:
    return DeflectionCodeVersion[f"{design_code.name}"]


def _torsion_longitudinal_area_from_state() -> float:
    diameter_mm = _resolved_diameter_value(
        "torsion_longitudinal_diameter_option",
        "torsion_longitudinal_diameter_mm",
        allow_empty=True,
    )
    count = _int_state_value("torsion_longitudinal_count")
    if diameter_mm <= 0 or count <= 0:
        return 0.0
    return _bar_area_cm2(diameter_mm) * count


def _automatic_deflection_dead_load_kgf_per_m_from_dimensions(width_cm: float, depth_cm: float) -> float:
    width_m = width_cm / 100.0
    depth_m = depth_cm / 100.0
    return width_m * depth_m * NORMAL_WEIGHT_CONCRETE_UNIT_WEIGHT_KGF_PER_M3


def _automatic_deflection_dead_load_from_state() -> float:
    return _automatic_deflection_dead_load_kgf_per_m_from_dimensions(
        float(st.session_state.width_cm),
        float(st.session_state.depth_cm),
    )


def _deflection_support_moment_coefficient(support_condition: DeflectionSupportCondition) -> float:
    return {
        DeflectionSupportCondition.CONTINUOUS_2_SPANS: 1.0 / 8.0,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS: 1.0 / 12.0,
    }.get(support_condition, 0.0)


def _auto_deflection_support_moments_from_state() -> tuple[float, float]:
    support_condition = DeflectionSupportCondition(st.session_state.deflection_support_condition)
    coefficient = _deflection_support_moment_coefficient(support_condition)
    if coefficient <= 0.0:
        return 0.0, 0.0
    span_length_m = float(st.session_state.span_length_m)
    dead_like_load_kgf_per_m = (
        _automatic_deflection_dead_load_from_state()
        + float(st.session_state.get("deflection_additional_sustained_load_kgf_per_m", 0.0))
    )
    live_load_kgf_per_m = float(st.session_state.get("deflection_service_live_load_kgf_per_m", 0.0))
    return (
        -(coefficient * dead_like_load_kgf_per_m * (span_length_m**2)),
        -(coefficient * live_load_kgf_per_m * (span_length_m**2)),
    )


def _resolved_deflection_support_moments_from_state() -> tuple[float, float]:
    support_condition = DeflectionSupportCondition(st.session_state.deflection_support_condition)
    if support_condition not in {
        DeflectionSupportCondition.CONTINUOUS_2_SPANS,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS,
    }:
        return 0.0, 0.0
    if st.session_state.get("deflection_support_moment_mode", "Auto") == "Auto":
        return _auto_deflection_support_moments_from_state()
    return (
        float(st.session_state.get("deflection_support_dead_load_service_moment_kgm", 0.0)),
        float(st.session_state.get("deflection_support_live_load_service_moment_kgm", 0.0)),
    )


def _resolved_deflection_ie_method_from_state() -> DeflectionIeMethod:
    support_condition = DeflectionSupportCondition(st.session_state.deflection_support_condition)
    if support_condition not in {
        DeflectionSupportCondition.CONTINUOUS_2_SPANS,
        DeflectionSupportCondition.CONTINUOUS_3_OR_MORE_SPANS,
    }:
        return DeflectionIeMethod.MIDSPAN_ONLY
    return DeflectionIeMethod(st.session_state.get("deflection_ie_method", DeflectionIeMethod.WORST_CASE.value))


def _workspace_state_keys(default_inputs: BeamDesignInputSet) -> set[str]:
    return {"project_date_auto_value", *build_default_state(default_inputs).keys()}


def _deflection_state_keys(default_state: dict[str, object]) -> tuple[str, ...]:
    return tuple(key for key in default_state if key.startswith("deflection_") or key in {"span_length_m"})


def _initialize_deflection_defaults_once(default_state: dict[str, object]) -> None:
    if st.session_state.get(DEFLECTION_DEFAULTS_VERSION_KEY) == DEFLECTION_DEFAULTS_VERSION:
        return
    for key in _deflection_state_keys(default_state):
        st.session_state[key] = default_state[key]
    st.session_state[DEFLECTION_DEFAULTS_VERSION_KEY] = DEFLECTION_DEFAULTS_VERSION


def _sync_layer_group_counts_from_selected_diameters(prefix: str, layer_index: int) -> None:
    group_a_option = st.session_state.get(f"{prefix}_layer_{layer_index}_group_a_diameter_option", "-")
    st.session_state[f"{prefix}_layer_{layer_index}_group_a_count"] = 0 if group_a_option == "-" else 2

    group_b_option = st.session_state.get(f"{prefix}_layer_{layer_index}_group_b_diameter_option", "-")
    if group_b_option == "-":
        st.session_state[f"{prefix}_layer_{layer_index}_group_b_count"] = 0


def _flexural_as_clause_reference_for_ui(design_code: DesignCode) -> str:
    if design_code in {DesignCode.ACI318_99, DesignCode.ACI318_08, DesignCode.ACI318_11}:
        return f"{_design_code_label_for_ui(design_code)} 10.5.1"
    return f"{_design_code_label_for_ui(design_code)} 9.6.1.2"


def _shear_min_clause_reference_for_ui(design_code: DesignCode) -> str:
    if design_code in {DesignCode.ACI318_99, DesignCode.ACI318_08, DesignCode.ACI318_11}:
        return f"{_design_code_label_for_ui(design_code)} 11.4.6.3"
    return f"{_design_code_label_for_ui(design_code)} 9.6.3"


def _shear_spacing_clause_reference_for_ui(design_code: DesignCode, torsion_active: bool) -> str:
    if torsion_active:
        if design_code == DesignCode.ACI318_99:
            return "ACI 318-99 11.4.5 together with 11.6.6.1"
        if design_code == DesignCode.ACI318_08:
            return "ACI 318-08 11.4.5 together with 11.5.6.1"
        if design_code == DesignCode.ACI318_11:
            return "ACI 318-11 11.4.5 together with 11.5.6.1"
        return f"{_design_code_label_for_ui(design_code)} 9.7.6.2 together with 9.7.6.3.3"
    if design_code in {DesignCode.ACI318_99, DesignCode.ACI318_08, DesignCode.ACI318_11}:
        return f"{_design_code_label_for_ui(design_code)} 11.4.5"
    return f"{_design_code_label_for_ui(design_code)} 9.7.6.2"


def _design_code_label_for_ui(design_code: DesignCode) -> str:
    mapping = {
        DesignCode.ACI318_99: "ACI 318-99",
        DesignCode.ACI318_08: "ACI 318-08",
        DesignCode.ACI318_11: "ACI 318-11",
        DesignCode.ACI318_14: "ACI 318-14",
        DesignCode.ACI318_19: "ACI 318-19",
        DesignCode.ACI318_25: "ACI 318-25",
    }
    return mapping[design_code]


def _format_aci_warning_reference_for_ui(reference: str) -> str:
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
            return _format_aci_warning_reference_for_ui(part)
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


def _torsion_spacing_clause_reference_for_ui(code_version: str) -> str:
    mapping = {
        "ACI 318-99": "ACI 318-99 11.6.6.1",
        "ACI 318-08": "ACI 318-08 11.5.6.1",
        "ACI 318-11": "ACI 318-11 11.5.6.1",
        "ACI 318-14": "ACI 318-14 9.7.6.3.3",
        "ACI 318-19": "ACI 318-19 9.7.6.3.3",
        "ACI 318-25": "ACI 318-25 9.7.6.3.3",
    }
    return mapping.get(code_version, code_version)


def _torsion_cross_section_clause_reference_for_ui(code_version: str) -> str:
    mapping = {
        "ACI 318-99": "ACI 318-99 11.6.3.1",
        "ACI 318-08": "ACI 318-08 11.5.3.1",
        "ACI 318-11": "ACI 318-11 11.5.3.1",
        "ACI 318-14": "ACI 318-14 22.7.7.1",
        "ACI 318-19": "ACI 318-19 22.7.7.1",
        "ACI 318-25": "ACI 318-25 22.7.7.1",
    }
    return mapping.get(code_version, code_version)


def _formalize_constructability_warning_text(message: str) -> str:
    normalized = message.strip().rstrip(".")
    return (
        f"{normalized}. This does not satisfy the specified minimum clear spacing requirement "
        "and is not suitable for practical construction."
    )


def _formalize_torsion_warning_text(message: str, torsion_results) -> str:
    normalized = message.strip().rstrip(".")
    if "required At/s" in normalized:
        clause = torsion_results.transverse_reinf_required_governing or f"{torsion_results.code_version} torsion transverse reinforcement provisions"
        normalized = normalized.replace("At/s", "A_t/s")
        return f"{normalized}. {_format_aci_warning_reference_for_ui(clause)}. This does not satisfy the required torsion transverse reinforcement provisions."
    if "required Al" in normalized:
        clause = torsion_results.longitudinal_reinf_required_governing or f"{torsion_results.code_version} torsion longitudinal reinforcement provisions"
        normalized = normalized.replace("Al", "A_l")
        return f"{normalized}. {_format_aci_warning_reference_for_ui(clause)}. This does not satisfy the required torsion longitudinal reinforcement provisions."
    if "maximum spacing permitted for torsion" in normalized:
        return f"{normalized}. {_format_aci_warning_reference_for_ui(_torsion_spacing_clause_reference_for_ui(torsion_results.code_version))}. This does not satisfy the maximum permitted torsion stirrup spacing."
    if "cross-sectional limit check" in normalized:
        return f"{normalized}. {_format_aci_warning_reference_for_ui(_torsion_cross_section_clause_reference_for_ui(torsion_results.code_version))}. This does not satisfy the torsional cross-sectional strength requirement."
    if "alternative torsion design procedure" in normalized:
        return f"{normalized}. This is an informational code note and not a design failure."
    return f"{normalized}. This should be reviewed by the design engineer."


def _render_warning_banner(message: str) -> None:
    st.markdown(
        f"<div class='design-banner fail'>{_warning_text_to_html(message)}</div>",
        unsafe_allow_html=True,
    )


def _warning_text_to_html(message: str) -> str:
    html = (
        message.replace("<=", "&le;")
        .replace(">=", "&ge;")
        .replace(" < ", " &lt; ")
        .replace(" > ", " &gt; ")
    )
    replacements = [
        ("A_s,total", "A<sub>s,total</sub>"),
        ("A_s,min", "A<sub>s,min</sub>"),
        ("A_s,max", "A<sub>s,max</sub>"),
        ("A_s", "A<sub>s</sub>"),
        ("A_v,min", "A<sub>v,min</sub>"),
        ("A_v", "A<sub>v</sub>"),
        ("A_l", "A<sub>l</sub>"),
        ("A_t/s", "A<sub>t</sub>/s"),
        ("At/s", "A<sub>t</sub>/s"),
        ("V_u", "V<sub>u</sub>"),
        ("V_n", "V<sub>n</sub>"),
        ("V_c", "V<sub>c</sub>"),
        ("V_s", "V<sub>s</sub>"),
        ("M_u", "M<sub>u</sub>"),
        ("M_n", "M<sub>n</sub>"),
        ("phi", "&phi;"),
        ("lambda_s", "&lambda;<sub>s</sub>"),
        ("f'c", "f&#8242;<sub>c</sub>"),
        ("cm2", "cm<sup>2</sup>"),
    ]
    for old, new in replacements:
        html = html.replace(old, new)
    return html


def _torsion_input_state_keys() -> tuple[str, ...]:
    return (
        "torsion_tu_kgfm",
        "torsion_demand_type",
        "torsion_longitudinal_diameter_option",
        "torsion_longitudinal_diameter_mm",
        "torsion_longitudinal_fy_grade_option",
        "torsion_longitudinal_fy_ksc",
        "torsion_longitudinal_count",
    )


def _handle_include_torsion_design_change() -> None:
    if bool(st.session_state.get("include_torsion_design")):
        _restore_torsion_input_backup()
        return
    st.session_state[TORSION_INPUT_BACKUP_KEY] = {
        key: st.session_state[key]
        for key in _torsion_input_state_keys()
        if key in st.session_state
    }


def _restore_torsion_input_backup() -> None:
    backup_state = st.session_state.get(TORSION_INPUT_BACKUP_KEY)
    if not isinstance(backup_state, dict):
        return
    for key, value in backup_state.items():
        st.session_state[key] = value


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
    torsion_side_lines = "".join(f"<div class='rebar-detail-line'>{line}</div>" for line in details.torsion_side_lines)
    torsion_warning_html = ""
    if details.torsion_warning:
        torsion_warning_html = f"<div class='rebar-detail-line' style='color:#d92d20;font-weight:700'>{details.torsion_warning}</div>"
    return (
        "<div class='metric-card rebar-detail-card'>"
        "<div class='rebar-detail-row'><div class='metric-label'>Top Rebar</div>"
        f"<div class='rebar-detail-value'>{top_lines}</div></div>"
        "<div class='rebar-detail-row'><div class='metric-label'>Bottom Rebar</div>"
        f"<div class='rebar-detail-value'>{bottom_lines}</div></div>"
        "<div class='rebar-detail-row'><div class='metric-label'>Stirrup</div>"
        f"<div class='rebar-detail-value'><div class='rebar-detail-line'>{details.stirrup_line}</div></div></div>"
        "<div class='rebar-detail-row'><div class='metric-label'>Torsion Surface Bars</div>"
        f"<div class='rebar-detail-value'>{torsion_side_lines}{torsion_warning_html}</div></div>"
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


def _build_inputs_for_torsion_capacity_preview() -> BeamDesignInputSet:
    diameter_mm = _resolved_diameter_value(
        "torsion_longitudinal_diameter_option",
        "torsion_longitudinal_diameter_mm",
        allow_empty=True,
    )
    original_count = int(st.session_state.torsion_longitudinal_count)
    if diameter_mm > 0 and original_count == 0:
        st.session_state.torsion_longitudinal_count = 1
    try:
        return build_inputs_from_state()
    finally:
        st.session_state.torsion_longitudinal_count = original_count


def _render_torsion_demand_type_info() -> None:
    popover = getattr(st, "popover", None)
    if callable(popover):
        with popover("Info"):
            st.markdown(TORSION_DEMAND_TYPE_INFO_TEXT)
        return
    with st.expander("Info"):
        st.markdown(TORSION_DEMAND_TYPE_INFO_TEXT)


def _render_info_button(text: str, *, label: str = "i") -> None:
    popover = getattr(st, "popover", None)
    if callable(popover):
        with popover(label):
            st.markdown(text)
        return
    with st.expander(label):
        st.markdown(text)

