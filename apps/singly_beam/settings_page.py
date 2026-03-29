from __future__ import annotations

import streamlit as st

from core.theme import apply_theme
from core.utils import format_number

from .formulas import (
    DEFAULT_EC_LOGIC,
    DEFAULT_ES_LOGIC,
    DEFAULT_FR_LOGIC,
    calculate_material_properties,
)
from .models import MaterialPropertiesInput, MaterialPropertyMode, MaterialPropertySetting, MaterialPropertySettings
from .workspace_page import LAST_RENDERED_PAGE_KEY, initialize_session_state, load_default_inputs, persist_session_state, reset_material_property_settings


def main() -> None:
    default_inputs = load_default_inputs()
    initialize_session_state(default_inputs)
    st.session_state[LAST_RENDERED_PAGE_KEY] = "settings"
    apply_theme()

    st.markdown("<div class='hero-title'>Settings</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='hero-subtitle'>Configure Ec, Es, and fr overrides without changing the original built-in formulas unless Manual mode is selected.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='section-label'>Material Property Settings</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='small-note'>Default = use the application’s original built-in formula or value. "
        "Manual = override with a user-defined value. Ec and fr default values are calculated from the original formulas. "
        "Es default value uses the original built-in constant.</div>",
        unsafe_allow_html=True,
    )

    action_left, action_right = st.columns([0.8, 2.2], gap="medium")
    with action_left:
        if st.button("Default", use_container_width=True):
            reset_material_property_settings()
            st.rerun()
    with action_right:
        st.caption("Default restores the original current app behavior for Ec, Es, and fr.")

    render_material_property_setting(
        key_prefix="ec",
        label="Ec (Concrete Modulus of Elasticity)",
        units="ksc",
        default_logic=DEFAULT_EC_LOGIC,
        mode_key="ec_mode",
        manual_key="ec_manual_ksc",
    )
    render_material_property_setting(
        key_prefix="es",
        label="Es (Rebar Modulus of Elasticity)",
        units="ksc",
        default_logic=DEFAULT_ES_LOGIC,
        mode_key="es_mode",
        manual_key="es_manual_ksc",
    )
    render_material_property_setting(
        key_prefix="fr",
        label="fr (Concrete Modulus of Rupture)",
        units="ksc",
        default_logic=DEFAULT_FR_LOGIC,
        mode_key="fr_mode",
        manual_key="fr_manual_ksc",
    )
    persist_session_state(default_inputs)


def render_material_property_setting(
    *,
    key_prefix: str,
    label: str,
    units: str,
    default_logic: str,
    mode_key: str,
    manual_key: str,
) -> None:
    resolved = _resolved_material_results()
    value_map = {
        "ec": (
            resolved.ec_default_ksc,
            resolved.ec_ksc,
            resolved.ec_mode,
        ),
        "es": (
            resolved.es_default_ksc,
            resolved.es_ksc,
            resolved.es_mode,
        ),
        "fr": (
            resolved.fr_default_ksc,
            resolved.modulus_of_rupture_fr_ksc,
            resolved.fr_mode,
        ),
    }
    default_value, final_value, mode = value_map[key_prefix]
    with st.container(border=True):
        st.markdown(f"<div class='section-label'>{label}</div>", unsafe_allow_html=True)
        controls_left, controls_right = st.columns([1.2, 1], gap="medium")
        with controls_left:
            st.radio(
                "Mode",
                options=[MaterialPropertyMode.DEFAULT.value, MaterialPropertyMode.MANUAL.value],
                key=mode_key,
                horizontal=True,
                label_visibility="visible",
            )
            st.caption(f"Default logic: {default_logic}")
        with controls_right:
            st.number_input(
                f"{label} override ({units})",
                min_value=0.0001,
                step=1.0,
                key=manual_key,
                disabled=mode == MaterialPropertyMode.DEFAULT,
                help="Used only when Manual mode is selected.",
            )
            st.markdown(
                f"<div class='small-note'>Resolved value: <strong>{format_number(final_value)}</strong> {units}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='small-note'>Default value: {format_number(default_value)} {units} | Source: {mode.value}</div>",
                unsafe_allow_html=True,
            )
        if mode == MaterialPropertyMode.MANUAL:
            _render_reasonableness_note(key_prefix, final_value, units)


def _resolved_material_results():
    materials = MaterialPropertiesInput(
        concrete_strength_ksc=float(st.session_state.fc_prime_ksc),
        main_steel_yield_ksc=float(st.session_state.fy_ksc),
        shear_steel_yield_ksc=float(st.session_state.fvy_ksc),
    )
    settings = MaterialPropertySettings(
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
    )
    return calculate_material_properties(materials, settings)


def _render_reasonableness_note(key_prefix: str, value: float, units: str) -> None:
    warning_bounds = {
        "ec": (50_000.0, 500_000.0),
        "es": (1_000_000.0, 3_000_000.0),
        "fr": (5.0, 80.0),
    }
    lower, upper = warning_bounds[key_prefix]
    if not (lower <= value <= upper):
        st.warning(f"Manual value {format_number(value)} {units} is outside the usual range used by this app. Review before design use.")
