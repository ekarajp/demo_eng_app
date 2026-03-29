from __future__ import annotations

from .deflection_base import DeflectionClauseMap, DeflectionWorkflowOptions, calculate_deflection_design
from .deflection_inputs import DeflectionDesignInput


def calculate_aci_11_deflection(design_input: DeflectionDesignInput):
    return calculate_deflection_design(
        design_input,
        DeflectionClauseMap(
            immediate_deflection="ACI318-11 - Clause 9.5.2",
            effective_inertia="ACI318-11 - Clause 9.5.2.3",
            long_term="ACI318-11 - Clause 9.5.2.5",
            allowable_limit="User-selected allowable deflection limit",
        ),
        DeflectionWorkflowOptions(immediate_method="branson"),
    )
