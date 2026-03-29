from __future__ import annotations

import streamlit as st

from core.navigation import go_home
from core.theme import apply_theme


def main() -> None:
    apply_theme()
    if st.button("Back to Home", use_container_width=False):
        go_home()
        st.rerun()
    st.markdown("## Beam Fiber Model")
    st.info("Coming Soon")
    st.caption("This tool is reserved for future fiber-section analysis and nonlinear response modeling workflows.")

