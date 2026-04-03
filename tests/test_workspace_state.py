from __future__ import annotations

import apps.rc_beam.workspace_page as workspace_page
from apps.rc_beam.models import BeamBehaviorMode, BeamType, CombinedShearTorsionResults
from core.theme import LIGHT_THEME
from design.deflection import (
    AllowableDeflectionPreset,
    DeflectionCodeVersion,
    DeflectionIeMethod,
    DeflectionMemberType,
    DeflectionSupportCondition,
)
from design.torsion import TorsionDesignCode
from design.torsion.torsion_base import TorsionDemandType, TorsionDesignResults


def test_initialize_session_state_restores_persisted_values(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = {
        workspace_page.PERSISTED_WORKSPACE_STATE_KEY: {
            "beam_type": "Continuous Beam",
            "width_cm": 35.0,
            "project_date_auto_value": "2026-03-29 10:15",
        }
    }

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page.initialize_session_state(default_inputs)

    assert session_state["beam_type"] == "Continuous Beam"
    assert session_state["width_cm"] == 35.0
    assert session_state["project_date_auto_value"] == "2026-03-29 10:15"
    assert "depth_cm" in session_state


def test_initialize_session_state_force_restores_values_when_returning_from_other_page(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = {
        "width_cm": 1.0,
        "min_clear_spacing_cm": 0.1,
        workspace_page.PERSISTED_WORKSPACE_STATE_KEY: {
            "width_cm": 30.0,
            "min_clear_spacing_cm": 3.5,
        },
    }

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page.initialize_session_state(default_inputs, force_restore=True)

    assert session_state["width_cm"] == 30.0
    assert session_state["min_clear_spacing_cm"] == 3.5


def test_initialize_session_state_resets_deflection_defaults_on_first_start(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = {
        workspace_page.PERSISTED_WORKSPACE_STATE_KEY: {
            "deflection_long_term_factor_x": 0.1,
            "span_length_m": 8.0,
            "deflection_allowable_limit_preset": "L/360",
            "deflection_sustained_live_load_ratio": 0.9,
        }
    }

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page.initialize_session_state(default_inputs)

    assert session_state["deflection_long_term_factor_x"] == 2.0
    assert session_state["span_length_m"] == 1.0
    assert session_state["deflection_allowable_limit_preset"] == "L/240"
    assert session_state["deflection_sustained_live_load_ratio"] == 0.3
    assert session_state["deflection_ie_method"] == "Conservative / Worst Case"


def test_initialize_session_state_resets_deflection_defaults_when_version_changes(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = {
        "deflection_long_term_factor_x": 0.1,
        "span_length_m": 8.0,
        "deflection_allowable_limit_preset": "L/360",
        "deflection_sustained_live_load_ratio": 0.9,
        workspace_page.DEFLECTION_DEFAULTS_VERSION_KEY: 1,
    }

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page.initialize_session_state(default_inputs)

    assert session_state["deflection_long_term_factor_x"] == 2.0
    assert session_state["span_length_m"] == 1.0
    assert session_state["deflection_allowable_limit_preset"] == "L/240"
    assert session_state["deflection_sustained_live_load_ratio"] == 0.3
    assert session_state[workspace_page.DEFLECTION_DEFAULTS_VERSION_KEY] == workspace_page.DEFLECTION_DEFAULTS_VERSION


def test_initialize_session_state_does_not_override_existing_values_during_workspace_rerun(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = {
        "width_cm": 28.0,
        workspace_page.PERSISTED_WORKSPACE_STATE_KEY: {
            "width_cm": 20.0,
        },
    }

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page.initialize_session_state(default_inputs, force_restore=False)

    assert session_state["width_cm"] == 28.0


def test_build_default_state_sets_continuous_negative_rebar_startup_defaults() -> None:
    default_inputs = workspace_page.load_default_inputs()
    state = workspace_page.build_default_state(default_inputs)

    assert state["nb_tens_layer_1_group_a_diameter_option"] == 12
    assert state["nb_tens_layer_1_group_a_diameter"] == 12
    assert state["nb_tens_layer_1_group_a_count"] == 2
    assert state["nb_tens_layer_1_group_b_diameter_option"] == "-"
    assert state["nb_tens_layer_1_group_b_count"] == 0
    assert state["nb_comp_layer_1_group_a_diameter_option"] == 12
    assert state["nb_comp_layer_1_group_a_diameter"] == 12
    assert state["nb_comp_layer_1_group_a_count"] == 2
    assert state["nb_comp_layer_1_group_b_diameter_option"] == "-"
    assert state["nb_comp_layer_1_group_b_count"] == 0
    assert state["nb_tens_layer_2_group_a_diameter_option"] == "-"
    assert state["nb_comp_layer_3_group_b_count"] == 0
    assert state["deflection_ie_method"] == "Conservative / Worst Case"


def test_build_default_state_sets_beam_behavior_defaults() -> None:
    default_inputs = workspace_page.load_default_inputs()

    state = workspace_page.build_default_state(default_inputs)

    assert state["beam_behavior_mode"] == BeamBehaviorMode.AUTO.value
    assert state["auto_beam_behavior_threshold_percent"] == 5.0


def test_handle_beam_type_change_preserves_user_negative_rebar_inputs(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["beam_type"] = "Continuous Beam"
    session_state[workspace_page.CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY] = True
    session_state["nb_tens_layer_1_group_a_diameter_option"] = 20
    session_state["nb_tens_layer_1_group_a_diameter"] = 20
    session_state["nb_tens_layer_1_group_a_count"] = 4
    session_state["nb_comp_layer_1_group_a_diameter_option"] = 16
    session_state["nb_comp_layer_1_group_a_diameter"] = 16
    session_state["nb_comp_layer_1_group_a_count"] = 3

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._handle_beam_type_change()

    assert session_state["nb_tens_layer_1_group_a_diameter_option"] == 20
    assert session_state["nb_tens_layer_1_group_a_diameter"] == 20
    assert session_state["nb_tens_layer_1_group_a_count"] == 4
    assert session_state["nb_comp_layer_1_group_a_diameter_option"] == 16
    assert session_state["nb_comp_layer_1_group_a_diameter"] == 16
    assert session_state["nb_comp_layer_1_group_a_count"] == 3


def test_handle_beam_type_change_applies_continuous_negative_rebar_defaults_on_first_switch(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["beam_type"] = "Continuous Beam"
    session_state[workspace_page.CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY] = False
    for prefix in ("nb_tens", "nb_comp"):
        session_state[f"{prefix}_layer_1_group_a_diameter_option"] = "-"
        session_state[f"{prefix}_layer_1_group_a_diameter"] = 0
        session_state[f"{prefix}_layer_1_group_a_count"] = 0
        session_state[f"{prefix}_layer_1_group_b_diameter_option"] = "-"
        session_state[f"{prefix}_layer_1_group_b_diameter"] = 0
        session_state[f"{prefix}_layer_1_group_b_count"] = 0

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._handle_beam_type_change()

    assert session_state["nb_tens_layer_1_group_a_diameter_option"] == 12
    assert session_state["nb_tens_layer_1_group_a_diameter"] == 12
    assert session_state["nb_tens_layer_1_group_a_count"] == 2
    assert session_state["nb_comp_layer_1_group_a_diameter_option"] == 12
    assert session_state["nb_comp_layer_1_group_a_diameter"] == 12
    assert session_state["nb_comp_layer_1_group_a_count"] == 2
    assert session_state[workspace_page.CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY] is True


def test_handle_beam_type_change_restores_user_negative_rebar_after_simple_switch(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["beam_type"] = "Simple Beam"
    session_state[workspace_page.CONTINUOUS_NEGATIVE_DEFAULTS_APPLIED_KEY] = True
    session_state[workspace_page.NEGATIVE_REBAR_INPUT_BACKUP_KEY] = {
        "nb_tens_layer_1_group_a_diameter_option": 20,
        "nb_tens_layer_1_group_a_diameter": 20,
        "nb_tens_layer_1_group_a_count": 4,
        "nb_comp_layer_1_group_a_diameter_option": 16,
        "nb_comp_layer_1_group_a_diameter": 16,
        "nb_comp_layer_1_group_a_count": 3,
        "negative_mu_kgm": 1250.0,
    }

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    session_state["beam_type"] = "Continuous Beam"
    workspace_page._handle_beam_type_change()

    assert session_state["nb_tens_layer_1_group_a_diameter_option"] == 20
    assert session_state["nb_tens_layer_1_group_a_diameter"] == 20
    assert session_state["nb_tens_layer_1_group_a_count"] == 4
    assert session_state["nb_comp_layer_1_group_a_diameter_option"] == 16
    assert session_state["nb_comp_layer_1_group_a_diameter"] == 16
    assert session_state["nb_comp_layer_1_group_a_count"] == 3
    assert session_state["negative_mu_kgm"] == 1250.0


def test_handle_beam_type_change_restores_last_continuous_deflection_ie_method(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["beam_type"] = "Continuous Beam"
    session_state["deflection_ie_method"] = "Averaged Ie (midspan + support)"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._handle_beam_type_change()
    assert session_state["deflection_ie_method"] == "Averaged Ie (midspan + support)"

    session_state["beam_type"] = "Simple Beam"
    workspace_page._handle_beam_type_change()
    assert session_state[workspace_page.DEFLECTION_IE_METHOD_BACKUP_KEY] == "Averaged Ie (midspan + support)"

    session_state["deflection_ie_method"] = "Midspan Ie only"
    session_state["beam_type"] = "Continuous Beam"
    workspace_page._handle_beam_type_change()

    assert session_state["deflection_ie_method"] == "Averaged Ie (midspan + support)"


def test_handle_beam_type_change_restores_worst_case_method_after_simple_switch(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["beam_type"] = "Continuous Beam"
    session_state["deflection_ie_method"] = "Conservative / Worst Case"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._handle_beam_type_change()
    session_state["beam_type"] = "Simple Beam"
    workspace_page._handle_beam_type_change()
    session_state["deflection_ie_method"] = "Midspan Ie only"
    session_state["beam_type"] = "Continuous Beam"
    workspace_page._handle_beam_type_change()

    assert session_state["deflection_ie_method"] == "Conservative / Worst Case"


def test_persist_session_state_snapshots_current_workspace_values(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = {
        "beam_type": "Continuous Beam",
        "width_cm": 42.0,
        "project_date_auto_value": "2026-03-29 11:00",
    }

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page.persist_session_state(default_inputs)

    persisted_state = session_state[workspace_page.PERSISTED_WORKSPACE_STATE_KEY]
    assert persisted_state["beam_type"] == "Continuous Beam"
    assert persisted_state["width_cm"] == 42.0
    assert persisted_state["project_date_auto_value"] == "2026-03-29 11:00"


def test_build_inputs_from_state_uses_main_design_code_for_torsion(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["include_torsion_design"] = True
    session_state["design_code"] = "ACI318-14"
    session_state["torsion_tu_kgfm"] = 500.0
    session_state["project_date_auto_value"] = "2026-03-29 12:00"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    inputs = workspace_page.build_inputs_from_state()

    assert inputs.torsion.design_code == TorsionDesignCode.ACI318_14
    assert inputs.torsion.provided_longitudinal_bar_fy_ksc == 4000.0


def test_build_inputs_from_state_preserves_consider_deflection_checkbox(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["consider_deflection"] = True
    session_state["project_date_auto_value"] = "2026-03-29 12:10"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    inputs = workspace_page.build_inputs_from_state()

    assert inputs.consider_deflection is True


def test_build_inputs_from_state_clamps_beam_behavior_threshold(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["beam_behavior_mode"] = BeamBehaviorMode.AUTO.value
    session_state["auto_beam_behavior_threshold_percent"] = 150.0
    session_state["project_date_auto_value"] = "2026-03-29 12:11"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    inputs = workspace_page.build_inputs_from_state()

    assert inputs.beam_behavior_mode == BeamBehaviorMode.AUTO
    assert inputs.auto_beam_behavior_threshold_ratio == 1.0

    session_state["auto_beam_behavior_threshold_percent"] = -20.0
    inputs = workspace_page.build_inputs_from_state()

    assert inputs.auto_beam_behavior_threshold_ratio == 0.0


def test_build_default_state_uses_requested_deflection_defaults() -> None:
    default_inputs = workspace_page.load_default_inputs()

    state = workspace_page.build_default_state(default_inputs)

    assert state["deflection_allowable_limit_preset"] == "L/240"
    assert state["deflection_long_term_factor_x"] == 2.0
    assert state["span_length_m"] == 1.0
    assert state["deflection_sustained_live_load_ratio"] == 0.3
    assert state["deflection_support_moment_mode"] == "Auto"


def test_handle_consider_deflection_change_applies_defaults_on_first_enable(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["consider_deflection"] = True
    session_state["deflection_sustained_live_load_ratio"] = 0.9
    session_state["span_length_m"] = 8.0
    session_state["deflection_long_term_factor_x"] = 0.1
    session_state["deflection_allowable_limit_preset"] = "L/360"
    session_state["deflection_ie_method"] = "Midspan Ie only"
    session_state[workspace_page.DEFLECTION_FIRST_ENABLE_KEY] = False

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._handle_consider_deflection_change()

    assert session_state["deflection_sustained_live_load_ratio"] == 0.3
    assert session_state["span_length_m"] == 1.0
    assert session_state["deflection_long_term_factor_x"] == 2.0
    assert session_state["deflection_allowable_limit_preset"] == "L/240"
    assert session_state["deflection_ie_method"] == "Conservative / Worst Case"
    assert session_state[workspace_page.DEFLECTION_FIRST_ENABLE_KEY] is True


def test_handle_consider_deflection_change_sets_worst_case_for_continuous_beam_on_first_enable(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["beam_type"] = "Continuous Beam"
    session_state["consider_deflection"] = True
    session_state["deflection_support_condition"] = "Simple"
    session_state["deflection_ie_method"] = "Midspan Ie only"
    session_state[workspace_page.DEFLECTION_FIRST_ENABLE_KEY] = False

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._handle_consider_deflection_change()

    assert session_state["deflection_support_condition"] == "Continuous, 2 spans"
    assert session_state["deflection_ie_method"] == "Conservative / Worst Case"


def test_handle_consider_deflection_change_preserves_user_values_after_first_enable(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["consider_deflection"] = True
    session_state["deflection_sustained_live_load_ratio"] = 0.45
    session_state["span_length_m"] = 6.5
    session_state["deflection_long_term_factor_x"] = 1.7
    session_state["deflection_allowable_limit_preset"] = "L/480"
    session_state[workspace_page.DEFLECTION_FIRST_ENABLE_KEY] = True

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._handle_consider_deflection_change()

    assert session_state["deflection_sustained_live_load_ratio"] == 0.45
    assert session_state["span_length_m"] == 6.5
    assert session_state["deflection_long_term_factor_x"] == 1.7
    assert session_state["deflection_allowable_limit_preset"] == "L/480"


def test_build_inputs_from_state_maps_new_deflection_controls(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["consider_deflection"] = True
    session_state["design_code"] = "ACI318-14"
    session_state["width_cm"] = 25.0
    session_state["depth_cm"] = 50.0
    session_state["deflection_member_type"] = "Continuous beam"
    session_state["deflection_support_condition"] = "Continuous, 2 spans"
    session_state["deflection_ie_method"] = "Averaged Ie (midspan + support)"
    session_state["deflection_allowable_limit_preset"] = "Custom"
    session_state["deflection_allowable_limit_custom_denominator"] = 500
    session_state["deflection_long_term_factor_x"] = 1.4
    session_state["deflection_service_dead_load_kgf_per_m"] = 350.0
    session_state["deflection_service_live_load_kgf_per_m"] = 180.0
    session_state["deflection_additional_sustained_load_kgf_per_m"] = 40.0
    session_state["deflection_sustained_live_load_ratio"] = 0.25
    session_state["deflection_support_moment_mode"] = "Manual"
    session_state["deflection_support_dead_load_service_moment_kgm"] = -1200.0
    session_state["deflection_support_live_load_service_moment_kgm"] = -600.0
    session_state["project_date_auto_value"] = "2026-03-29 12:15"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    inputs = workspace_page.build_inputs_from_state()

    assert inputs.deflection.design_code == DeflectionCodeVersion.ACI318_14
    assert inputs.deflection.member_type == DeflectionMemberType.CONTINUOUS_BEAM
    assert inputs.deflection.support_condition == DeflectionSupportCondition.CONTINUOUS_2_SPANS
    assert inputs.deflection.ie_method == DeflectionIeMethod.AVERAGED
    assert inputs.deflection.allowable_limit_preset == AllowableDeflectionPreset.CUSTOM
    assert inputs.deflection.allowable_limit_custom_denominator == 500
    assert inputs.deflection.long_term_factor_x == 1.4
    assert inputs.deflection.service_dead_load_kgf_per_m == 300.0
    assert inputs.deflection.service_live_load_kgf_per_m == 180.0
    assert inputs.deflection.support_dead_load_service_moment_kgm == -1200.0
    assert inputs.deflection.support_live_load_service_moment_kgm == -600.0


def test_resolved_deflection_ie_method_preserves_continuous_selection_but_uses_midspan_for_simple(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["deflection_ie_method"] = "Conservative / Worst Case"
    session_state["deflection_support_condition"] = "Simple"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    assert workspace_page._resolved_deflection_ie_method_from_state() == DeflectionIeMethod.MIDSPAN_ONLY
    assert session_state["deflection_ie_method"] == "Conservative / Worst Case"


def test_deflection_support_moment_mode_is_preserved_when_ie_method_changes() -> None:
    default_inputs = workspace_page.load_default_inputs()
    state = workspace_page.build_default_state(default_inputs)

    assert state["deflection_support_moment_mode"] == "Auto"
    state["deflection_support_moment_mode"] = "Manual"
    state["deflection_ie_method"] = "Midspan Ie only"
    state["deflection_ie_method"] = "Conservative / Worst Case"

    assert state["deflection_support_moment_mode"] == "Manual"


def test_deflection_support_input_visibility_restores_latest_support_input_state(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["deflection_support_moment_mode"] = "Manual"
    session_state["deflection_support_dead_load_service_moment_kgm"] = -1200.0
    session_state["deflection_support_live_load_service_moment_kgm"] = -600.0
    session_state[workspace_page.DEFLECTION_SUPPORT_INPUT_VISIBLE_KEY] = True

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._leave_deflection_support_input_visibility()
    session_state["deflection_support_moment_mode"] = "Auto"
    session_state["deflection_support_dead_load_service_moment_kgm"] = 0.0
    session_state["deflection_support_live_load_service_moment_kgm"] = 0.0

    workspace_page._enter_deflection_support_input_visibility()

    assert session_state["deflection_support_moment_mode"] == "Manual"
    assert session_state["deflection_support_dead_load_service_moment_kgm"] == -1200.0
    assert session_state["deflection_support_live_load_service_moment_kgm"] == -600.0


def test_build_inputs_from_state_auto_estimates_deflection_support_moments(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["consider_deflection"] = True
    session_state["beam_type"] = "Continuous Beam"
    session_state["design_code"] = "ACI318-19"
    session_state["width_cm"] = 25.0
    session_state["depth_cm"] = 50.0
    session_state["deflection_member_type"] = "Continuous beam"
    session_state["deflection_support_condition"] = "Continuous, 2 spans"
    session_state["span_length_m"] = 10.0
    session_state["deflection_additional_sustained_load_kgf_per_m"] = 40.0
    session_state["deflection_service_live_load_kgf_per_m"] = 180.0
    session_state["deflection_support_moment_mode"] = "Auto"
    session_state["deflection_support_dead_load_service_moment_kgm"] = -1.0
    session_state["deflection_support_live_load_service_moment_kgm"] = -1.0
    session_state["project_date_auto_value"] = "2026-03-29 12:15"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    inputs = workspace_page.build_inputs_from_state()

    assert inputs.deflection.support_dead_load_service_moment_kgm == -4250.0
    assert inputs.deflection.support_live_load_service_moment_kgm == -2250.0


def test_deflection_info_texts_follow_selected_project_code(monkeypatch) -> None:
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update({"design_code": "ACI318-19"})

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    long_term_text = workspace_page._deflection_long_term_x_info_text()
    limit_text = workspace_page._deflection_limit_info_text()
    service_text = workspace_page._deflection_service_load_info_text()

    assert "ACI318-19 - Clause 24.2.4" in long_term_text
    assert "L/240 (default)" in limit_text
    assert "ACI318-19 - Chapter 24 gives the serviceability framework for deflection checks in the selected code version." in limit_text
    assert "L/240: common general building limit where moderate deflection control is needed." in limit_text
    assert "L/480: tighter architectural/serviceability control for more sensitive finishes." in limit_text
    assert "are engineering guidance in this app and are not directly assigned to these exact ratios by the selected ACI code text." in limit_text
    assert "Simple beam: L = serviceability span length of the simple span being checked." in limit_text
    assert "w_sustained = DL_auto + SDL + (Sustained LL ratio x Service LL)" in service_text
    assert "Sustained LL ratio is the portion of service live load treated as sustained" in service_text
    assert "Strength design for Mu and Vu remains based on the user-entered factored actions." in service_text
    assert "Startup default in this app = 0.30." in service_text
    assert "This is not the same as SDL." in service_text


def test_warning_reference_helpers_use_verified_torsion_clauses() -> None:
    assert workspace_page._torsion_spacing_clause_reference_for_ui("ACI 318-14") == "ACI 318-14 9.7.6.3.3"
    assert workspace_page._torsion_spacing_clause_reference_for_ui("ACI 318-19") == "ACI 318-19 9.7.6.3.3"
    assert workspace_page._torsion_cross_section_clause_reference_for_ui("ACI 318-14") == "ACI 318-14 22.7.7.1"
    assert workspace_page._torsion_cross_section_clause_reference_for_ui("ACI 318-19") == "ACI 318-19 22.7.7.1"
    assert (
        workspace_page._shear_spacing_clause_reference_for_ui(workspace_page.DesignCode.ACI318_19, True)
        == "ACI 318-19 9.7.6.2 together with 9.7.6.3.3"
    )


def test_simple_beam_deflection_support_options_remain_single_value() -> None:
    options = workspace_page._deflection_support_options_for_member_type("Simple beam")

    assert options == ["Simple"]


def test_deflection_reference_diagram_marks_simple_midspan(monkeypatch) -> None:
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update({"deflection_support_condition": "Simple"})

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    html = workspace_page._deflection_reference_diagram_html()

    assert "Simple beam: maximum deflection is checked at midspan." in html
    assert "Max deflection check point" in html
    assert "deflection-support-triangle" in html
    assert "max-width:520px" in html
    assert "fill:#111111" in html
    assert "\n        <polygon" not in html


def test_deflection_reference_diagram_marks_continuous_representative_span(monkeypatch) -> None:
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update({"deflection_support_condition": "Continuous, 3 or more spans"})

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    html = workspace_page._deflection_reference_diagram_html()

    assert (
        "Continuous 3 or more spans: the module checks both Ie at the interior representative span midspan and "
        "representative Ie,avg, then uses the larger deflection."
    ) in html
    assert "Span 2" in html


def test_deflection_reference_diagram_keeps_triangle_supports_for_continuous_case(monkeypatch) -> None:
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(
        {
            "deflection_support_condition": "Continuous, 2 spans",
            "deflection_support_dead_load_service_moment_kgm": 50.0,
            "deflection_support_live_load_service_moment_kgm": 25.0,
        }
    )

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    html = workspace_page._deflection_reference_diagram_html()

    assert "deflection-support-fixed-wall" not in html
    assert html.count("<polygon class='deflection-support-triangle'") == 3


def test_deflection_reference_diagram_uses_preview_results_in_note(monkeypatch) -> None:
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update({"deflection_support_condition": "Simple"})
    preview_results = type(
        "PreviewResults",
        (),
        {
            "deflection": type(
                "DeflectionResult",
                (),
                {"total_service_deflection_cm": 1.25, "allowable_deflection_cm": 2.5},
            )()
        },
    )()

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    html = workspace_page._deflection_reference_diagram_html(preview_results)

    assert "Total service deflection = 1.25 cm, allowable = 2.50 cm." in html
    assert "&#916;max = 1.25 cm" in html


def test_deflection_reference_diagram_summary_mode_shows_legend_without_delta_marker(monkeypatch) -> None:
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update({"deflection_support_condition": "Simple"})
    preview_results = type(
        "PreviewResults",
        (),
        {
            "deflection": type(
                "DeflectionResult",
                (),
                {"total_service_deflection_cm": 1.25, "allowable_deflection_cm": 2.5},
            )()
        },
    )()

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    html = workspace_page._deflection_reference_diagram_html(preview_results, summary_mode=True, palette=LIGHT_THEME)

    assert "Calculated deflection shape" in html
    assert "Allowable limit shape" in html
    assert "&#916;max" not in html


def test_sync_layer_group_counts_resets_middle_bar_count_when_diameter_is_empty(monkeypatch) -> None:
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(
        {
            "pb_tens_layer_1_group_a_diameter_option": 12,
            "pb_tens_layer_1_group_a_count": 0,
            "pb_tens_layer_1_group_b_diameter_option": "-",
            "pb_tens_layer_1_group_b_count": 3,
        }
    )

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._sync_layer_group_counts_from_selected_diameters("pb_tens", 1)

    assert session_state["pb_tens_layer_1_group_a_count"] == 2
    assert session_state["pb_tens_layer_1_group_b_count"] == 0


def test_build_inputs_from_state_uses_selected_fyl_for_torsion_longitudinal_steel(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["include_torsion_design"] = True
    session_state["fy_grade_option"] = 5000
    session_state["fy_ksc"] = 5000.0
    session_state["torsion_longitudinal_fy_grade_option"] = 3000
    session_state["torsion_longitudinal_fy_ksc"] = 3000.0
    session_state["project_date_auto_value"] = "2026-03-29 12:30"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    inputs = workspace_page.build_inputs_from_state()

    assert inputs.materials.main_steel_yield_ksc == 5000.0
    assert inputs.torsion.provided_longitudinal_bar_fy_ksc == 3000.0


def test_build_inputs_for_torsion_capacity_preview_allows_selected_diameter_with_zero_count(monkeypatch) -> None:
    default_inputs = workspace_page.load_default_inputs()
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(workspace_page.build_default_state(default_inputs))
    session_state["include_torsion_design"] = True
    session_state["torsion_longitudinal_diameter_option"] = 16
    session_state["torsion_longitudinal_diameter_mm"] = 16
    session_state["torsion_longitudinal_count"] = 0
    session_state["project_date_auto_value"] = "2026-03-29 13:00"

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    inputs = workspace_page._build_inputs_for_torsion_capacity_preview()

    assert inputs.torsion.provided_longitudinal_bar_diameter_mm == 16
    assert inputs.torsion.provided_longitudinal_bar_count == 1
    assert session_state["torsion_longitudinal_count"] == 0


def test_include_torsion_toggle_restores_previous_torsion_inputs(monkeypatch) -> None:
    session_state = type("SessionState", (dict,), {"__getattr__": dict.__getitem__, "__setattr__": dict.__setitem__})()
    session_state.update(
        {
            "include_torsion_design": False,
            "torsion_tu_kgfm": 1250.0,
            "torsion_demand_type": "equilibrium torsion",
            "torsion_longitudinal_diameter_option": 16,
            "torsion_longitudinal_diameter_mm": 16,
            "torsion_longitudinal_fy_grade_option": 4000,
            "torsion_longitudinal_fy_ksc": 4000.0,
            "torsion_longitudinal_count": 6,
        }
    )

    monkeypatch.setattr(workspace_page.st, "session_state", session_state)

    workspace_page._handle_include_torsion_design_change()

    session_state.update(
        {
            "torsion_tu_kgfm": 0.0,
            "torsion_demand_type": "compatibility torsion",
            "torsion_longitudinal_diameter_option": "-",
            "torsion_longitudinal_diameter_mm": 0,
            "torsion_longitudinal_fy_grade_option": 2400,
            "torsion_longitudinal_fy_ksc": 2400.0,
            "torsion_longitudinal_count": 0,
        }
    )

    session_state["include_torsion_design"] = True
    workspace_page._handle_include_torsion_design_change()

    assert session_state["torsion_tu_kgfm"] == 1250.0
    assert session_state["torsion_demand_type"] == "equilibrium torsion"
    assert session_state["torsion_longitudinal_diameter_option"] == 16
    assert session_state["torsion_longitudinal_diameter_mm"] == 16
    assert session_state["torsion_longitudinal_fy_grade_option"] == 4000
    assert session_state["torsion_longitudinal_fy_ksc"] == 4000.0
    assert session_state["torsion_longitudinal_count"] == 6


def test_review_flags_tab_is_omitted_when_no_review_flags_exist(monkeypatch) -> None:
    recorded_labels: list[list[str]] = []

    class DummyContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_tabs(labels):
        recorded_labels.append(list(labels))
        return [DummyContext() for _ in labels]

    monkeypatch.setattr(workspace_page.st, "tabs", fake_tabs)
    monkeypatch.setattr(workspace_page.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(workspace_page.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(workspace_page.st, "json", lambda *args, **kwargs: None)
    monkeypatch.setattr(workspace_page.st, "markdown", lambda *args, **kwargs: None)

    workspace_page.render_warnings_and_flags(type("Results", (), {"warnings": [], "review_flags": []})())

    assert recorded_labels == [["Warnings", "Raw Results"]]


def test_shear_torsion_interaction_diagram_html_shows_shared_stirrup_rule() -> None:
    html = workspace_page._build_shear_torsion_interaction_diagram_html(
        CombinedShearTorsionResults(
            active=True,
            torsion_ignored=False,
            ignore_message="",
            vu_kg=5000.0,
            tu_kgfm=1200.0,
            shear_required_transverse_mm2_per_mm=0.020,
            torsion_required_transverse_mm2_per_mm=0.030,
            combined_required_transverse_mm2_per_mm=0.050,
            provided_transverse_mm2_per_mm=0.080,
            governing_case="Shear + Torsion",
            capacity_ratio=0.625,
            design_status="PASS",
            stirrup_diameter_mm=9,
            stirrup_legs=2,
            stirrup_spacing_cm=15.0,
            summary_note="",
        ),
        LIGHT_THEME,
        TorsionDesignResults(
            enabled=True,
            code_version="ACI 318-19",
            demand_type=TorsionDemandType.EQUILIBRIUM,
            design_method="Standard thin-walled tube / space-truss method",
            status="PASS",
            pass_fail_summary="Provided torsion reinforcement satisfies the implemented standard torsion checks.",
            tu_kgfm=1200.0,
            threshold_torsion_kgfm=100.0,
            cracking_torsion_kgfm=None,
            acp_mm2=0.0,
            pcp_mm=0.0,
            aoh_mm2=0.0,
            ao_mm2=0.0,
            ph_mm=0.0,
            wall_thickness_mm=0.0,
            aspect_ratio_h_over_bt=0.0,
            transverse_reinf_required_mm2_per_mm=0.0,
            transverse_reinf_required_governing="",
            longitudinal_reinf_required_mm2=0.0,
            longitudinal_reinf_required_governing="",
            transverse_reinf_provided_mm2_per_mm=0.0,
            longitudinal_reinf_provided_mm2=0.0,
            max_spacing_mm=0.0,
            can_neglect_torsion=False,
            cross_section_ok=True,
            alternative_procedure_allowed=False,
        ),
    )

    assert "Shear&ndash;Torsion Interaction Diagram" in html
    assert "x + y &le; 1.00" in html
    assert "Demand point" in html


def test_shear_torsion_interaction_diagram_html_appends_solid_section_limit_graph_when_available() -> None:
    html = workspace_page._build_shear_torsion_interaction_diagram_html(
        CombinedShearTorsionResults(
            active=True,
            torsion_ignored=False,
            ignore_message="",
            vu_kg=12000.0,
            tu_kgfm=2000.0,
            shear_required_transverse_mm2_per_mm=0.020,
            torsion_required_transverse_mm2_per_mm=0.030,
            combined_required_transverse_mm2_per_mm=0.050,
            provided_transverse_mm2_per_mm=0.080,
            governing_case="Combined section limit",
            capacity_ratio=0.625,
            design_status="FAIL",
            stirrup_diameter_mm=16,
            stirrup_legs=4,
            stirrup_spacing_cm=5.0,
            summary_note="",
            cross_section_limit_check_applied=True,
            cross_section_limit_lhs_mpa=3.187,
            cross_section_limit_rhs_mpa=1.000,
            cross_section_limit_ratio=3.187,
            cross_section_limit_clause="ACI 318-19 22.7.7.1",
            shear_section_stress_mpa=0.900,
            torsion_section_stress_mpa=3.057,
            design_status_note="Combined shear and torsion exceed the implemented solid-section stress limit.",
        ),
        LIGHT_THEME,
    )

    assert "Solid Section Combined Section-Limit Diagram" in html
    assert "(x<sup>2</sup> + y<sup>2</sup>)<sup>1/2</sup> &le; 1.00" in html
    assert "Shear stress / limit stress" in html
    assert "Torsion stress / limit stress" in html


def test_torsion_warning_summary_prefers_specific_warning_text() -> None:
    torsion_results = TorsionDesignResults(
        enabled=True,
        code_version="ACI 318-19",
        demand_type=TorsionDemandType.EQUILIBRIUM,
        design_method="Standard thin-walled tube / space-truss method",
        status="DOES NOT MEET REQUIREMENTS",
        pass_fail_summary="Provided torsion reinforcement does not meet one or more torsion reinforcement requirements.",
        tu_kgfm=1200.0,
        threshold_torsion_kgfm=100.0,
        cracking_torsion_kgfm=None,
        acp_mm2=0.0,
        pcp_mm=0.0,
        aoh_mm2=0.0,
        ao_mm2=0.0,
        ph_mm=0.0,
        wall_thickness_mm=0.0,
        aspect_ratio_h_over_bt=0.0,
        transverse_reinf_required_mm2_per_mm=0.0,
        transverse_reinf_required_governing="",
        longitudinal_reinf_required_mm2=0.0,
        longitudinal_reinf_required_governing="",
        transverse_reinf_provided_mm2_per_mm=0.0,
        longitudinal_reinf_provided_mm2=0.0,
        max_spacing_mm=0.0,
        can_neglect_torsion=False,
        cross_section_ok=True,
        alternative_procedure_allowed=False,
        warnings=("Provided longitudinal torsion reinforcement does not meet the required Al.",),
    )

    assert workspace_page._torsion_warning_summary(torsion_results) == (
        "Provided longitudinal torsion reinforcement does not meet the required Al."
    )


def test_torsion_demand_type_info_text_keeps_conservative_guidance() -> None:
    info_text = workspace_page.TORSION_DEMAND_TYPE_INFO_TEXT

    assert "Use 'equilibrium torsion'" in info_text
    assert "Use 'compatibility torsion'" in info_text
    assert "safer and more conservative design assumption" in info_text


def test_shear_design_section_label_switches_to_combined_mode_when_torsion_is_enabled() -> None:
    assert workspace_page._shear_design_section_label(False, BeamType.SIMPLE) == "7. Shear Design"
    assert workspace_page._shear_design_section_label(True, BeamType.SIMPLE) == "7. Shear & Torsion Design"
    assert workspace_page._shear_design_section_label(True, BeamType.CONTINUOUS) == "7. Shear & Torsion Design"


def test_active_flexural_section_specs_support_cantilever_mappings() -> None:
    assert workspace_page._active_flexural_section_specs(BeamType.STANDALONE_CANTILEVER, False) == [
        ("Cantilever Negative Section", "cantilever_negative")
    ]
    assert workspace_page._active_flexural_section_specs(BeamType.SIMPLE, False) == [
        ("Middle Section", "middle"),
        ("Support Section", "support"),
    ]
    assert workspace_page._active_flexural_section_specs(BeamType.SIMPLE, True) == [
        ("Middle Section", "middle"),
        ("Support Section", "support"),
        ("Cantilever Negative Section", "cantilever_negative"),
    ]
    assert workspace_page._active_flexural_section_specs(BeamType.CONTINUOUS, False) == [
        ("Positive Section", "positive"),
        ("Negative Section", "negative"),
    ]
    assert workspace_page._active_flexural_section_specs(BeamType.CONTINUOUS, True) == [
        ("Positive Section", "positive"),
        ("Negative Section", "negative"),
        ("Cantilever Negative Section", "cantilever_negative"),
    ]


def test_active_vu_region_specs_show_support_before_middle_for_simple_beam() -> None:
    assert workspace_page._active_vu_region_specs(BeamType.SIMPLE, False) == [
        ("support", "Support Vu", "Support Section"),
        ("middle", "Middle-region Vu", "Middle Section"),
    ]
    assert workspace_page._active_vu_region_specs(BeamType.SIMPLE, True) == [
        ("support", "Support Vu", "Support Section"),
        ("middle", "Middle-region Vu", "Middle Section"),
        ("cantilever", "Cantilever Vu", "Cantilever Negative Section"),
    ]


def test_torsion_detail_inputs_are_hidden_when_torsion_can_be_ignored() -> None:
    preview_results = type(
        "PreviewResults",
        (),
        {
            "combined_shear_torsion": CombinedShearTorsionResults(
                active=False,
                torsion_ignored=True,
                ignore_message="Tu < Tth, ignore torsion",
                vu_kg=0.0,
                tu_kgfm=0.0,
                shear_required_transverse_mm2_per_mm=0.0,
                torsion_required_transverse_mm2_per_mm=0.0,
                combined_required_transverse_mm2_per_mm=0.0,
                provided_transverse_mm2_per_mm=0.0,
                governing_case="Torsion ignored",
                capacity_ratio=0.0,
                design_status="PASS",
                stirrup_diameter_mm=9,
                stirrup_legs=2,
                stirrup_spacing_cm=15.0,
                summary_note="",
            )
        },
    )()

    assert workspace_page._torsion_detail_inputs_required(None) is True
    assert workspace_page._torsion_detail_inputs_required(preview_results) is False
