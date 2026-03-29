from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import streamlit as st
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

from apps.beam_fiber_model.placeholder import main as render_beam_fiber_model
from apps.doubly_beam.placeholder import main as render_doubly_beam
from apps.landing.landing_page import main as render_landing_page
from apps.singly_beam.singly_beam_app import main as render_singly_beam
from core.navigation import HOME_VIEW, current_view


def run_app_entrypoint() -> None:
    if get_script_run_ctx() is None:
        app_path = str(Path(__file__).resolve())
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


def main() -> None:
    st.set_page_config(page_title="Engineering App Suite", page_icon=":material/engineering:", layout="wide")

    active_view = current_view()
    if active_view == HOME_VIEW:
        render_landing_page()
        return
    if active_view == "singly_beam":
        render_singly_beam(show_home_button=True)
        return
    if active_view == "doubly_beam":
        render_doubly_beam()
        return
    if active_view == "beam_fiber_model":
        render_beam_fiber_model()
        return

    render_landing_page()


if __name__ == "__main__":
    run_app_entrypoint()

