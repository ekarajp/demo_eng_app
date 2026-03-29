from __future__ import annotations

import core.theme as theme


def test_resolve_palette_is_locked_to_light_theme():
    palette = theme.resolve_palette("light")

    assert palette == theme.LIGHT_THEME


def test_resolve_palette_ignores_dark_theme_requests():
    palette = theme.resolve_palette("dark")

    assert palette == theme.LIGHT_THEME


def test_resolve_streamlit_theme_type_is_locked_to_light():
    assert theme.resolve_streamlit_theme_type() == "light"
