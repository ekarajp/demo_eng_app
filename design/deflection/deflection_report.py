from __future__ import annotations

from .deflection_inputs import DeflectionDesignResults


def deflection_workspace_summary_lines(results: DeflectionDesignResults) -> tuple[str, ...]:
    if results.mockup_only:
        return (results.note,)
    lines = [
        f"Code = {results.code_version} | Member = {results.member_type} | Support = {results.support_condition}",
        f"Ie method = {results.ie_method_selected}",
        f"Allowable deflection = {results.allowable_limit_label} = {results.allowable_deflection_cm:.4f} cm",
    ]
    if results.method_2_total_service_deflection_cm is not None:
        lines.append(
            f"Method 1 = {results.method_1_total_service_deflection_cm:.4f} cm | "
            f"Method 2 = {results.method_2_total_service_deflection_cm:.4f} cm | "
            f"Governing = {results.ie_method_governing}"
        )
    lines.extend(
        [
            f"Immediate total deflection = {results.immediate_total_deflection_cm:.4f} cm",
            f"Additional long-term deflection = {results.additional_long_term_deflection_cm:.4f} cm",
            f"Total service deflection = {results.total_service_deflection_cm:.4f} cm | Capacity Ratio (Deflection) = {results.capacity_ratio:.4f}",
        ]
    )
    return tuple(lines)
