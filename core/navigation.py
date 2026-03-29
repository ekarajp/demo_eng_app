from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


HOME_VIEW = "landing"
ACTIVE_VIEW_KEY = "_engineering_suite_active_view"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    key: str
    title: str
    description: str
    status: str
    available: bool


TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        key="singly_beam",
        title="Singly Beam Analysis",
        description="Reinforced concrete singly reinforced beam analysis and design.",
        status="Available",
        available=True,
    ),
    ToolDefinition(
        key="doubly_beam",
        title="Doubly Beam Analysis",
        description="Reinforced concrete doubly reinforced beam analysis and design.",
        status="Coming Soon",
        available=False,
    ),
    ToolDefinition(
        key="beam_fiber_model",
        title="Beam Fiber Model",
        description="Section fiber analysis and nonlinear response modeling.",
        status="Coming Soon",
        available=False,
    ),
)


def get_tools() -> tuple[ToolDefinition, ...]:
    return TOOLS


def current_view() -> str:
    return str(st.session_state.get(ACTIVE_VIEW_KEY, HOME_VIEW))


def open_tool(tool_key: str) -> None:
    st.session_state[ACTIVE_VIEW_KEY] = tool_key


def go_home() -> None:
    st.session_state[ACTIVE_VIEW_KEY] = HOME_VIEW

