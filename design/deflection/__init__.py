from .deflection_base import calculate_deflection_design
from .deflection_inputs import (
    AllowableDeflectionLimitInput,
    AllowableDeflectionPreset,
    DeflectionCalculationStep,
    DeflectionCodeVersion,
    DeflectionDesignInput,
    DeflectionDesignResults,
    DeflectionIeMethod,
    DeflectionMemberType,
    DeflectionSectionReinforcementInput,
    DeflectionServiceLoadInput,
    DeflectionSupportCondition,
    DeflectionVerificationStatus,
)
from .deflection_limits import allowable_deflection_cm, allowable_limit_denominator, allowable_limit_label

__all__ = [
    "AllowableDeflectionLimitInput",
    "AllowableDeflectionPreset",
    "DeflectionCalculationStep",
    "DeflectionCodeVersion",
    "DeflectionDesignInput",
    "DeflectionDesignResults",
    "DeflectionIeMethod",
    "DeflectionMemberType",
    "DeflectionSectionReinforcementInput",
    "DeflectionServiceLoadInput",
    "DeflectionSupportCondition",
    "DeflectionVerificationStatus",
    "allowable_deflection_cm",
    "allowable_limit_denominator",
    "allowable_limit_label",
    "calculate_deflection_design",
    "design_deflection_check",
]


def design_deflection_check(design_input: DeflectionDesignInput) -> DeflectionDesignResults:
    if design_input.code_version == DeflectionCodeVersion.ACI318_99:
        from .deflection_aci_99 import calculate_aci_99_deflection

        return calculate_aci_99_deflection(design_input)
    if design_input.code_version == DeflectionCodeVersion.ACI318_11:
        from .deflection_aci_11 import calculate_aci_11_deflection

        return calculate_aci_11_deflection(design_input)
    if design_input.code_version == DeflectionCodeVersion.ACI318_14:
        from .deflection_aci_14 import calculate_aci_14_deflection

        return calculate_aci_14_deflection(design_input)
    from .deflection_aci_19 import calculate_aci_19_deflection

    return calculate_aci_19_deflection(design_input)
