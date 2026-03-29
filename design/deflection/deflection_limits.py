from __future__ import annotations

from .deflection_inputs import AllowableDeflectionLimitInput, AllowableDeflectionPreset


_LIMIT_MAP = {
    AllowableDeflectionPreset.L_120: 120,
    AllowableDeflectionPreset.L_180: 180,
    AllowableDeflectionPreset.L_240: 240,
    AllowableDeflectionPreset.L_360: 360,
    AllowableDeflectionPreset.L_480: 480,
    AllowableDeflectionPreset.L_600: 600,
}


def allowable_limit_denominator(limit_input: AllowableDeflectionLimitInput) -> int:
    if limit_input.preset == AllowableDeflectionPreset.CUSTOM:
        if limit_input.custom_denominator is None:
            raise ValueError("custom_denominator is required when the allowable limit preset is Custom.")
        return limit_input.custom_denominator
    return _LIMIT_MAP[limit_input.preset]


def allowable_limit_label(limit_input: AllowableDeflectionLimitInput) -> str:
    denominator = allowable_limit_denominator(limit_input)
    return f"L/{denominator}"


def allowable_deflection_cm(span_length_m: float, limit_input: AllowableDeflectionLimitInput) -> float:
    return (span_length_m * 100.0) / allowable_limit_denominator(limit_input)
