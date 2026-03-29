from __future__ import annotations

import streamlit as st

from core.navigation import get_tools, open_tool
from core.theme import apply_theme


def main() -> None:
    apply_theme()
    _inject_landing_css()

    st.markdown(
        """
        <div class="suite-hero">
          <div class="suite-eyebrow">Engineering Software Platform</div>
          <h1>Engineering App Suite</h1>
          <p>
            Central workspace for beam design, section analysis, and future structural engineering tools.
            Choose a program below to open its dedicated workflow.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    columns = st.columns(3, gap="large")
    for column, tool in zip(columns, get_tools()):
        with column:
            st.markdown(
                f"""
                <div class="suite-card {'available' if tool.available else 'coming-soon'}">
                  <div class="suite-card-header">
                    <div class="suite-card-title">{tool.title}</div>
                    <div class="suite-status {'available' if tool.available else 'soon'}">{tool.status}</div>
                  </div>
                  <div class="suite-card-body">{tool.description}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if tool.available:
                if st.button("Open Tool", key=f"open_tool_{tool.key}", use_container_width=True):
                    open_tool(tool.key)
                    st.rerun()
            else:
                st.button("Coming Soon", key=f"coming_soon_{tool.key}", disabled=True, use_container_width=True)

    st.markdown(
        """
        <div class="suite-footer-note">
          The suite is structured for future expansion. Additional engineering tools can be added without changing the main entry workflow.
        </div>
        """,
        unsafe_allow_html=True,
    )


def _inject_landing_css() -> None:
    st.markdown(
        """
        <style>
        .suite-hero {
            padding: 0.5rem 0 1.35rem 0;
            max-width: 920px;
        }
        .suite-eyebrow {
            display: inline-block;
            margin-bottom: 0.85rem;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            border: 1px solid rgba(31, 111, 178, 0.18);
            background: linear-gradient(135deg, rgba(31, 111, 178, 0.1), rgba(220, 236, 248, 0.8));
            color: #1f3552;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }
        .suite-hero h1 {
            margin: 0;
            font-size: clamp(2rem, 4vw, 3.2rem);
            line-height: 0.98;
            letter-spacing: -0.03em;
        }
        .suite-hero p {
            margin: 0.95rem 0 0 0;
            max-width: 760px;
            font-size: 1rem;
            line-height: 1.65;
            color: #526172;
        }
        .suite-card {
            min-height: 228px;
            padding: 1.15rem 1.15rem 1rem 1.15rem;
            border-radius: 20px;
            border: 1px solid rgba(141, 154, 171, 0.28);
            background:
                radial-gradient(circle at top right, rgba(31, 111, 178, 0.08), transparent 34%),
                linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(246, 249, 252, 0.95));
            box-shadow: 0 14px 34px rgba(16, 20, 24, 0.06);
            margin-bottom: 0.85rem;
        }
        .suite-card.coming-soon {
            opacity: 0.88;
        }
        .suite-card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }
        .suite-card-title {
            font-size: 1.18rem;
            font-weight: 800;
            line-height: 1.2;
            color: #101418;
        }
        .suite-status {
            flex: 0 0 auto;
            padding: 0.35rem 0.65rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }
        .suite-status.available {
            background: rgba(20, 122, 72, 0.12);
            color: #147a48;
        }
        .suite-status.soon {
            background: rgba(182, 124, 0, 0.12);
            color: #915c00;
        }
        .suite-card-body {
            color: #526172;
            line-height: 1.65;
            font-size: 0.97rem;
        }
        .suite-footer-note {
            margin-top: 1.5rem;
            color: #6a7887;
            font-size: 0.92rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

