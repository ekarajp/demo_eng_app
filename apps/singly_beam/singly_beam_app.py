from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import streamlit as st
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

from core.navigation import go_home

from .calculation_report_full_page import main as render_calculation_report_full_page
from .calculation_report_page import main as render_calculation_report_page
from .settings_page import main as render_settings_page
from .workspace_page import (
    build_inputs_from_state,
    initialize_session_state,
    load_default_inputs,
    main as render_workspace_page,
)


def run_app_entrypoint() -> None:
    if get_script_run_ctx() is None:
        app_path = str(Path(__file__).resolve())
        print("Launching Streamlit app...", flush=True)
        print("If the browser does not open, use: http://localhost:8501", flush=True)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                app_path,
                "--server.showEmailPrompt=false",
                "--browser.gatherUsageStats=false",
                *sys.argv[1:],
            ],
            check=False,
        )
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
        return
    main()


def main(*, show_home_button: bool = True) -> None:
    if show_home_button and st.sidebar.button("Home", use_container_width=True):
        go_home()
        st.rerun()
    navigation = st.navigation(
        [
            st.Page(
                render_workspace_page,
                title="Input data",
                icon=":material/edit_note:",
                url_path="input-data",
                default=True,
            ),
            st.Page(
                render_calculation_report_page,
                title="Calculation Report (Summery)",
                icon=":material/description:",
                url_path="calculation-report",
            ),
            st.Page(
                render_calculation_report_full_page,
                title="Calculation Report (Full)",
                icon=":material/article:",
                url_path="calculation-report-full",
            ),
            st.Page(
                render_settings_page,
                title="Settings",
                icon=":material/tune:",
                url_path="settings",
            ),
        ],
        position="sidebar",
    )
    navigation.run()


__all__ = [
    "build_inputs_from_state",
    "initialize_session_state",
    "load_default_inputs",
    "main",
    "run_app_entrypoint",
]


if __name__ == "__main__":
    run_app_entrypoint()
