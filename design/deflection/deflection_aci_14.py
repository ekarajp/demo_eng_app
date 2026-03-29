from __future__ import annotations

from .deflection_base import DeflectionClauseMap, DeflectionWorkflowOptions, calculate_deflection_design
from .deflection_inputs import DeflectionDesignInput


def calculate_aci_14_deflection(design_input: DeflectionDesignInput):
    return calculate_deflection_design(
        design_input,
        DeflectionClauseMap(
            immediate_deflection="ACI318-14 - Chapter 24.2.3",
            effective_inertia="ACI318-14 - Chapter 24.2.3",
            long_term="ACI318-14 - Chapter 24.2.4",
            allowable_limit="User-selected allowable deflection limit",
        ),
        DeflectionWorkflowOptions(immediate_method="branson"),
    )
