from __future__ import annotations

import apps.singly_beam.workspace_page as workspace_page


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
