from __future__ import annotations

from dataclasses import dataclass

from design.torsion.torsion_report import build_torsion_report_rows
from design.torsion.torsion_units import mm2_to_cm2, mm_to_cm
from core.theme import ThemePalette
from core.utils import format_number, format_ratio, longitudinal_bar_mark, stirrup_bar_mark

from .formulas import calculate_beam_geometry
from .models import BeamBehaviorMode, BeamDesignInputSet, BeamDesignResults, BeamType, ReinforcementArrangementInput, VerificationStatus


@dataclass(frozen=True, slots=True)
class ReportRow:
    variable: str
    equation: str
    substitution: str
    result: str
    units: str
    status: str = ""
    note: str = ""


@dataclass(frozen=True, slots=True)
class ReportSection:
    title: str
    rows: list[ReportRow]


@dataclass(frozen=True, slots=True)
class NarrativeSection:
    title: str
    body: str
    bullets: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SummaryReportData:
    member_summary: str
    member_facts: tuple[str, ...]
    design_actions: str
    check_sections: tuple[NarrativeSection, ...]
    reinforcement_lines: tuple[str, ...]
    governing_notes: tuple[str, ...]
    conclusion: str


def _active_section_names(inputs: BeamDesignInputSet) -> str:
    return ", ".join(label for _, label in inputs.active_flexural_sections)


def _cantilever_span_summary(inputs: BeamDesignInputSet) -> str | None:
    if inputs.beam_type.value == "Standalone Cantilever Beam":
        return None
    return "Yes" if inputs.include_cantilever_span else "No"


def _mu_mapping_text(inputs: BeamDesignInputSet) -> str:
    return "; ".join(f"{label} -> {section_label}" for label, _, section_label in inputs.active_mu_region_mappings)


def _vu_mapping_text(inputs: BeamDesignInputSet) -> str:
    return "; ".join(
        f"{region_label} -> {section_label}" for _, region_label, _, section_label in inputs.active_vu_region_mappings
    )


def _primary_section_label(inputs: BeamDesignInputSet) -> str:
    if not inputs.has_positive_design and inputs.has_cantilever_negative_design:
        return "Cantilever Negative"
    if inputs.beam_type == BeamType.SIMPLE:
        return "Middle"
    return "Positive"


def _shear_basis_text(results: BeamDesignResults) -> str:
    return f"{results.shear.design_section_label} section"


def _shear_effective_depth_text(results: BeamDesignResults) -> str:
    return format_number(results.shear.effective_depth_cm)


def _negative_section_effective_depth_text(inputs: BeamDesignInputSet, bending_input) -> str:
    geometry_results = calculate_beam_geometry(
        inputs.geometry,
        inputs.positive_bending,
        bending_input,
        inputs.shear,
        include_negative=True,
    )
    return format_number(geometry_results.d_minus_cm) if geometry_results.d_minus_cm is not None else "N/A"


def _moment_capacity_row_content(
    flexural_result,
    *,
    default_equation: str,
    default_substitution: str,
) -> tuple[str, str]:
    if getattr(flexural_result, "effective_beam_behavior", "") == BeamBehaviorMode.DOUBLY.value:
        return (
            "Full-section strain compatibility result",
            "Compatibility-based full-section flexural strength using bar depths measured from the compression face",
        )
    return default_equation, default_substitution


def _moment_capacity_summary_equation(flexural_result, default_equation: str) -> str:
    if getattr(flexural_result, "effective_beam_behavior", "") == BeamBehaviorMode.DOUBLY.value:
        return "Full-section compatibility Mn, phiMn"
    return default_equation


def _with_updated_moment_summary_row(section: ReportSection, flexural_result) -> ReportSection:
    rows = list(section.rows)
    if not rows:
        return section
    last_row = rows[-1]
    rows[-1] = ReportRow(
        variable=last_row.variable,
        equation=_moment_capacity_summary_equation(flexural_result, last_row.equation),
        substitution=last_row.substitution,
        result=last_row.result,
        units=last_row.units,
        status=last_row.status,
        note=last_row.note,
    )
    return ReportSection(title=section.title, rows=rows)


def build_summary_report_data(inputs: BeamDesignInputSet, results: BeamDesignResults) -> SummaryReportData:
    check_sections = [
        _build_flexure_summary_section(inputs, results),
        _build_shear_summary_section(inputs, results),
    ]
    torsion_section = _build_torsion_summary_section(inputs, results)
    if torsion_section is not None:
        check_sections.append(torsion_section)
    deflection_section = _build_deflection_summary_narrative(results)
    if deflection_section is not None:
        check_sections.append(deflection_section)

    return SummaryReportData(
        member_summary=_member_summary_text(inputs, results),
        member_facts=tuple(_member_fact_lines(inputs)),
        design_actions=_design_actions_text(inputs, results),
        check_sections=tuple(check_sections),
        reinforcement_lines=tuple(_reinforcement_summary_lines(inputs, results)),
        governing_notes=tuple(_governing_note_lines(results)),
        conclusion=_summary_conclusion_text(inputs, results),
    )


def build_full_report_overview_data(inputs: BeamDesignInputSet, results: BeamDesignResults) -> SummaryReportData:
    return build_summary_report_data(inputs, results)


def _build_summary_table_shear_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    combined = results.combined_shear_torsion
    if combined.active:
        rows = [
            ReportRow(
                "Shear + Torsion",
                "-",
                f"ratio {format_ratio(combined.capacity_ratio)} | s {format_number(combined.stirrup_spacing_cm)} cm",
                format_ratio(combined.capacity_ratio),
                "-",
                combined.design_status,
                _summary_label(combined.design_status_note or combined.summary_note),
            ),
            ReportRow(
                "Stirrups",
                "-",
                f"{stirrup_bar_mark(inputs.materials.shear_steel_yield_ksc)}{combined.stirrup_diameter_mm}, {combined.stirrup_legs}-leg @ {format_number(combined.stirrup_spacing_cm)} cm",
                format_number(combined.stirrup_spacing_cm),
                "cm",
            ),
            ReportRow("Basis", "-", f"{_shear_basis_text(results)}, d = {_shear_effective_depth_text(results)} cm", results.shear.design_section_label, "-", combined.design_status),
        ]
        if combined.cross_section_limit_check_applied:
            rows.append(
                ReportRow(
                    "Section Limit",
                    "-",
                    f"{format_number(combined.cross_section_limit_lhs_mpa)} / {format_number(combined.cross_section_limit_rhs_mpa)} MPa",
                    format_ratio(combined.cross_section_limit_ratio),
                    "-",
                    "PASS" if combined.cross_section_limit_ratio <= 1.0 else "FAIL",
                    _summary_label(combined.cross_section_limit_clause),
                )
            )
        return ReportSection(title="Shear", rows=rows)
    return ReportSection(
        title="Shear",
        rows=[
            ReportRow(
                "Shear Strength",
                "-",
                f"V<sub>u</sub> {format_number(inputs.shear.factored_shear_kg)} | &phi;V<sub>n</sub> {format_number(results.shear.phi_vn_kg)}",
                format_ratio(results.shear.capacity_ratio),
                "-",
                results.shear.design_status,
                _summary_label(results.shear.review_note or results.shear.section_change_note),
            ),
            ReportRow("Basis", "-", f"{_shear_basis_text(results)}, d = {_shear_effective_depth_text(results)} cm", results.shear.design_section_label, "-", results.shear.design_status),
            ReportRow(
                "Stirrups",
                "-",
                f"{stirrup_bar_mark(inputs.materials.shear_steel_yield_ksc)}{inputs.shear.stirrup_diameter_mm}, {inputs.shear.legs_per_plane}-leg @ {format_number(results.shear.provided_spacing_cm)} cm",
                format_number(results.shear.provided_spacing_cm),
                "cm",
            ),
        ],
    )


def _build_summary_table_torsion_section(results: BeamDesignResults) -> ReportSection:
    torsion = results.torsion
    combined = results.combined_shear_torsion
    if combined.torsion_ignored:
        return ReportSection(
            title="Torsion",
            rows=[
                ReportRow("Threshold", "-", "Tu below threshold", "Ignore Tu", "-", "PASS"),
                ReportRow("Threshold", "-", format_number(torsion.threshold_torsion_kgfm), format_number(torsion.threshold_torsion_kgfm), "kgf-m"),
            ],
        )
    return ReportSection(
        title="Torsion",
        rows=[
            ReportRow("Tu", "-", format_number(torsion.tu_kgfm), format_number(torsion.tu_kgfm), "kgf-m"),
            ReportRow(
                "Interaction",
                "-",
                _summary_label(combined.summary_note or torsion.pass_fail_summary),
                format_ratio(combined.capacity_ratio if combined.active else 0.0),
                "-",
                combined.design_status if combined.active else torsion.status,
            ),
            ReportRow(
                "Al req.",
                "-",
                "-",
                format_number(mm2_to_cm2(torsion.longitudinal_reinf_required_mm2)),
                "cm2",
            ),
        ],
    )


def _build_summary_table_deflection_section(results: BeamDesignResults) -> ReportSection:
    deflection = results.deflection
    return ReportSection(
        title="Deflection",
        rows=[
            ReportRow("Allowable", "-", _summary_label(deflection.allowable_limit_label), format_number(deflection.allowable_deflection_cm), "cm"),
            ReportRow("Service", "-", _summary_label(deflection.ie_method_governing), format_number(deflection.total_service_deflection_cm), "cm"),
            ReportRow("Ratio", "-", "-", format_ratio(deflection.capacity_ratio), "-", deflection.status),
        ],
    )


def build_report_print_css(palette: ThemePalette) -> str:
    text = "#101418"
    muted = "#475467"
    border = "#cfd7e3"
    surface = "#ffffff"
    surface_alt = "#f5f7fb"
    accent = palette.accent
    return f"""
    <style>
    .screen-only {{
        display: block;
    }}
    .report-toolbar {{
        margin-bottom: 0.85rem;
    }}
    .print-sheet {{
        max-width: 210mm;
        margin: 0 auto 1rem auto;
        padding: 6mm;
        border-radius: 16px;
        border: 1px solid {palette.border};
        background: {palette.surface};
        box-shadow: {palette.shadow};
        color: {palette.text};
    }}
    .summary-sheet {{
        width: 198mm;
        min-height: 284mm;
        max-height: 284mm;
        overflow: hidden;
        margin: 0 auto 1rem auto;
        padding: 6mm;
        border-radius: 16px;
        border: 1px solid {palette.border};
        background: {palette.surface};
        box-shadow: {palette.shadow};
        color: {palette.text};
        box-sizing: border-box;
    }}
    .summary-header {{
        display: grid;
        grid-template-columns: 1.2fr 0.8fr;
        gap: 3mm;
        align-items: start;
        margin-bottom: 2.2mm;
    }}
    .summary-title {{
        margin: 0;
        font-size: 14px;
        line-height: 1.08;
    }}
    .summary-subtitle {{
        margin: 0.8mm 0 0 0;
        font-size: 8px;
        color: {palette.muted_text};
    }}
    .summary-lead {{
        margin: 1.3mm 0 0 0;
        font-size: 7.5px;
        line-height: 1.42;
        color: {palette.text};
    }}
    .summary-fact-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1mm;
        margin-top: 1.5mm;
    }}
    .summary-fact {{
        border: 1px solid {palette.border};
        border-radius: 8px;
        padding: 1mm 1.2mm;
        background: {palette.surface_alt};
        font-size: 6.8px;
        line-height: 1.28;
    }}
    .summary-content {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 1.8mm;
    }}
    .summary-block {{
        border: 1px solid {palette.border};
        border-radius: 10px;
        padding: 1.8mm 2mm;
        background: {palette.surface};
        break-inside: avoid;
    }}
    .summary-block-title {{
        margin: 0 0 1mm 0;
        font-size: 8px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: {palette.text};
    }}
    .summary-block p {{
        margin: 0;
        font-size: 7.2px;
        line-height: 1.42;
        color: {palette.text};
    }}
    .summary-check-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1.4mm;
    }}
    .summary-check-item {{
        border: 1px solid {palette.border};
        border-radius: 8px;
        padding: 1.2mm 1.4mm;
        background: {palette.surface_alt};
    }}
    .summary-check-item h3 {{
        margin: 0 0 0.7mm 0;
        font-size: 7px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    .summary-check-item p {{
        margin: 0;
        font-size: 7px;
        line-height: 1.35;
    }}
    .summary-check-item ul,
    .summary-list {{
        margin: 1mm 0 0 2.7mm;
        padding: 0;
    }}
    .summary-check-item li,
    .summary-list li {{
        font-size: 6.8px;
        line-height: 1.32;
        margin: 0 0 0.5mm 0;
    }}
    .print-header {{
        display: grid;
        grid-template-columns: 1.35fr 0.65fr;
        gap: 2.2mm;
        align-items: start;
        margin-bottom: 2.2mm;
    }}
    .print-header.dual-layout {{
        grid-template-columns: 1fr;
    }}
    .print-header.single-layout {{
        grid-template-columns: 1.5fr 0.5fr;
    }}
    .print-header h1 {{
        margin: 0;
        font-size: 14px;
        line-height: 1.1;
    }}
    .print-header p {{
        margin: 0.9mm 0 0 0;
        font-size: 8px;
        color: {palette.muted_text};
    }}
    .print-chip-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 1.2mm;
        margin-top: 1.4mm;
    }}
    .print-chip {{
        border: 1px solid {palette.border};
        border-radius: 999px;
        padding: 0.7mm 1.9mm;
        font-size: 7.4px;
        background: {palette.surface_alt};
    }}
    .print-figure {{
        min-height: 13mm;
        display: flex;
        justify-content: center;
        align-items: center;
        border: 1px solid {palette.border};
        border-radius: 10px;
        background: {palette.surface_alt};
        padding: 0.35mm;
    }}
    .print-figure svg {{
        width: 100%;
        height: auto;
        max-width: 40mm;
    }}
    .print-drawing-stack {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 1.5mm;
    }}
    .print-drawing-stack.single .print-figure svg {{
        max-width: 24mm;
    }}
    .print-drawing-stack.single .print-figure {{
        min-height: 11mm;
    }}
    .print-drawing-stack.dual {{
        grid-template-columns: 1fr 1fr;
        gap: 1mm;
    }}
    .print-drawing-stack.dual .print-figure svg {{
        max-width: 26mm;
    }}
    .print-rebar-box {{
        margin-top: 0.6mm;
        border: 1px solid {palette.border};
        border-radius: 8px;
        background: {palette.surface};
        padding: 0.65mm 0.8mm;
        font-size: 6.4px;
        line-height: 1.1;
    }}
    .print-rebar-row {{
        display: grid;
        grid-template-columns: 10mm 1fr;
        gap: 0.8mm;
        align-items: start;
        padding: 0.25mm 0;
    }}
    .print-rebar-row + .print-rebar-row {{
        border-top: 1px solid {palette.border};
        margin-top: 0.25mm;
        padding-top: 0.4mm;
    }}
    .print-rebar-row > span {{
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    .print-rebar-line {{
        word-break: break-word;
    }}
    .print-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 2.2mm;
    }}
    .print-block {{
        break-inside: avoid;
        border: 1px solid {palette.border};
        border-radius: 10px;
        padding: 1.8mm;
        background: {palette.surface};
    }}
    .print-compact-block {{
        background: linear-gradient(180deg, {palette.surface_alt} 0%, {palette.surface} 100%);
    }}
    .print-compact-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1.4mm;
    }}
    .print-compact-item {{
        border: 1px solid {palette.border};
        border-radius: 8px;
        background: {palette.surface};
        padding: 1.2mm 1.4mm;
    }}
    .print-compact-label {{
        font-size: 6.8px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: {palette.muted_text};
        margin-bottom: 0.45mm;
    }}
    .print-compact-value {{
        font-size: 8.2px;
        font-weight: 700;
        line-height: 1.3;
        color: {palette.text};
    }}
    .print-compact-unit {{
        font-size: 6.8px;
        font-weight: 600;
        color: {palette.muted_text};
    }}
    .print-compact-detail {{
        margin-top: 0.55mm;
        font-size: 6.5px;
        line-height: 1.25;
        color: {palette.muted_text};
    }}
    .print-compact-meta {{
        margin-top: 0.55mm;
        font-size: 6.5px;
        line-height: 1.25;
        color: {palette.muted_text};
    }}
    .print-summary-block {{
        border-color: {palette.accent};
    }}
    .print-section-title {{
        margin: 0 0 1.1mm 0;
        font-size: 8px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: {palette.text};
    }}
    .print-table {{
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        font-size: 7.2px;
        line-height: 1.1;
        color: {palette.text};
    }}
    .print-table col:nth-child(1) {{ width: 16%; }}
    .print-table col:nth-child(2) {{ width: 38%; }}
    .print-table col:nth-child(3) {{ width: 17%; }}
    .print-table col:nth-child(4) {{ width: 29%; }}
    .print-table th,
    .print-table td {{
        border: 1px solid {palette.border};
        padding: 0.75mm 0.95mm;
        vertical-align: top;
        text-align: left;
        word-break: break-word;
    }}
    .print-table th {{
        background: {palette.surface_alt};
        font-weight: 700;
    }}
    .print-result {{
        font-weight: 700;
        color: {accent};
    }}
    .print-footer {{
        margin-top: 2.2mm;
        font-size: 6.8px;
        color: {palette.muted_text};
    }}
    @page {{
        size: A4 portrait;
        margin: 6mm;
    }}
    @media print {{
        :root {{
            color-scheme: light;
        }}
        .stApp,
        .stApp p,
        .stApp label,
        .stApp span,
        .stApp h1,
        .stApp h2,
        .stApp h3,
        .stApp h4,
        .stApp h5,
        .stApp h6,
        div[data-testid="stMarkdownContainer"] {{
            color: {text} !important;
        }}
        .stApp {{
            background: #ffffff !important;
        }}
        .screen-only,
        header[data-testid="stHeader"],
        div[data-testid="stToolbar"],
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"],
        div[data-testid="stSidebar"],
        div[data-testid="collapsedControl"] {{
            display: none !important;
        }}
        .block-container {{
            padding: 0 !important;
            max-width: none !important;
        }}
        .print-sheet {{
            width: 198mm;
            max-width: 198mm;
            min-height: 284mm;
            margin: 0 auto !important;
            padding: 0 !important;
            border: none !important;
            box-shadow: none !important;
            background: {surface} !important;
            color: {text} !important;
        }}
        .summary-sheet {{
            width: 198mm;
            max-width: 198mm;
            min-height: 284mm;
            max-height: 284mm;
            margin: 0 auto !important;
            border: none !important;
            box-shadow: none !important;
            background: {surface} !important;
            color: {text} !important;
        }}
        .print-header p,
        .print-chip,
        .print-footer {{
            color: {muted} !important;
        }}
        .print-block,
        .print-figure,
        .print-rebar-box,
        .print-compact-item,
        .print-table th,
        .print-table td {{
            border-color: {border} !important;
        }}
        .print-block {{
            background: {surface} !important;
        }}
        .print-compact-block,
        .print-figure,
        .print-table th {{
            background: {surface_alt} !important;
        }}
        .print-compact-item,
        .print-rebar-box {{
            background: {surface} !important;
        }}
        .print-table td,
        .print-sheet,
        .print-section-title,
        .print-compact-value,
        .print-header h1,
        .print-result,
        .print-rebar-row,
        .print-rebar-line {{
            color: {text} !important;
        }}
        .print-compact-label,
        .print-compact-unit,
        .print-compact-detail,
        .print-compact-meta {{
            color: {muted} !important;
        }}
    }}
    </style>
    """


def build_full_report_print_css(palette: ThemePalette) -> str:
    return f"""
    <style>
    .stApp,
    .stAppViewContainer,
    .main,
    div[data-testid="stAppViewContainer"] {{
        background: #ffffff !important;
        color: #101418 !important;
    }}
    .block-container {{
        background: #ffffff !important;
    }}
    .hero-title,
    .hero-subtitle,
    .stApp p,
    .stApp span,
    .stApp div,
    .stApp label,
    .stApp h1,
    .stApp h2,
    .stApp h3,
    .stApp h4,
    .stApp h5,
    .stApp h6,
    div[data-testid="stMarkdownContainer"] {{
        color: #101418 !important;
    }}
    .screen-only {{
        display: block;
    }}
    .report-toolbar {{
        margin-bottom: 0.85rem;
    }}
    .full-report-root {{
        color: #101418;
        background: #ffffff;
        padding-bottom: 8mm;
    }}
    .full-report-page {{
        width: 210mm;
        min-height: 297mm;
        margin: 0 auto 10mm auto;
        padding: 10mm;
        border: 1px solid #cfd7e3;
        border-radius: 18px;
        background: #ffffff;
        box-shadow: 0 14px 32px rgba(16, 20, 24, 0.08);
        break-after: page;
        page-break-after: always;
        box-sizing: border-box;
    }}
    .full-report-page:last-child {{
        break-after: auto;
        page-break-after: auto;
    }}
    .full-report-hero {{
        display: grid;
        grid-template-columns: 1.2fr 0.8fr;
        gap: 6mm;
        align-items: start;
        margin-bottom: 5mm;
    }}
    .full-report-title {{
        margin: 0;
        font-size: 20px;
        line-height: 1.05;
        color: #101418;
    }}
    .full-report-subtitle {{
        margin-top: 1.5mm;
        font-size: 10px;
        color: #475467;
    }}
    .full-report-lead {{
        margin-top: 2.5mm;
        font-size: 8.6px;
        line-height: 1.5;
        color: #101418;
    }}
    .full-report-meta {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1.4mm;
        margin-top: 3mm;
    }}
    .full-report-meta-item {{
        border: 1px solid #cfd7e3;
        border-radius: 10px;
        padding: 1.4mm 2mm;
        background: #f5f7fb;
        font-size: 8.4px;
    }}
    .full-report-meta-label {{
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #475467;
        margin-bottom: 0.4mm;
    }}
    .full-report-figures {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 2mm;
    }}
    .full-report-figures.dual {{
        grid-template-columns: 1fr 1fr;
    }}
    .full-report-figure-block {{
        border: 1px solid #cfd7e3;
        border-radius: 14px;
        padding: 2mm;
        background: #f5f7fb;
    }}
    .full-report-figure-title {{
        margin: 0 0 1mm 0;
        font-size: 8px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    .full-report-figure {{
        min-height: 40mm;
        display: flex;
        align-items: center;
        justify-content: center;
    }}
    .full-report-figure svg {{
        width: 100%;
        height: auto;
        max-width: 60mm;
    }}
    .full-report-figure-block.dual .full-report-figure svg {{
        max-width: 44mm;
    }}
    .full-report-rebar {{
        margin-top: 1.3mm;
        font-size: 7px;
        line-height: 1.2;
        color: #101418;
    }}
    .full-report-rebar strong {{
        display: inline-block;
        min-width: 12mm;
    }}
    .full-report-summary {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 2mm;
        margin: 0 0 4mm 0;
    }}
    .full-report-summary-card {{
        border: 1px solid #cfd7e3;
        border-radius: 12px;
        padding: 2mm;
        background: linear-gradient(160deg, #ffffff, #f5f7fb);
    }}
    .full-report-summary-card .label {{
        font-size: 7px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #475467;
    }}
    .full-report-summary-card .value {{
        margin-top: 0.8mm;
        font-size: 12px;
        font-weight: 800;
        color: #101418;
    }}
    .full-report-bullets {{
        margin: 0.5mm 0 0 3.2mm;
        padding: 0;
    }}
    .full-report-bullets li {{
        margin: 0 0 0.9mm 0;
        font-size: 7.8px;
        line-height: 1.4;
        color: #101418;
    }}
    .full-report-section {{
        border: 1px solid #cfd7e3;
        border-radius: 14px;
        padding: 3.6mm;
        background: #ffffff;
        break-inside: avoid;
        page-break-inside: avoid;
    }}
    .full-report-section + .full-report-section {{
        margin-top: 3mm;
    }}
    .full-report-section-title {{
        margin: 0 0 2mm 0;
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #101418;
    }}
    .full-report-section-intro {{
        margin: 0 0 2.2mm 0;
        font-size: 8.2px;
        line-height: 1.45;
        color: #475467;
    }}
    .full-report-visuals {{
        margin: 0 0 2.2mm 0;
    }}
    .full-report-visuals .metric-card {{
        margin-top: 0 !important;
        padding: 0.55rem 0.7rem !important;
        min-height: auto !important;
    }}
    .full-report-visuals .metric-note {{
        font-size: 0.72rem !important;
        min-height: auto !important;
    }}
    .full-report-visuals .section-label {{
        font-size: 0.86rem !important;
        margin-bottom: 0.4rem !important;
    }}
    .full-report-visuals svg[aria-label*="flexural phi strain chart"] {{
        max-width: 230px !important;
    }}
    .full-report-visuals svg[aria-label="Shear-Torsion interaction diagram"],
    .full-report-visuals svg[aria-label="Solid-section combined section-limit diagram"] {{
        max-width: 280px !important;
    }}
    .full-report-visuals svg[aria-label="Deflection reference diagram"] {{
        max-width: 340px !important;
    }}
    .full-report-steps {{
        display: grid;
        gap: 2.1mm;
    }}
    .full-report-steps.two-column {{
        grid-template-columns: 1fr 1fr;
        column-gap: 2.2mm;
        align-items: start;
    }}
    .full-report-steps.single-column {{
        grid-template-columns: 1fr;
    }}
    .full-report-step {{
        border: 1px solid #d8e0ea;
        border-radius: 12px;
        padding: 2.2mm 2.5mm;
        background: #fbfcfe;
    }}
    .full-report-step-header {{
        display: flex;
        align-items: baseline;
        gap: 1.5mm;
        margin-bottom: 0.9mm;
    }}
    .full-report-step-number {{
        min-width: 7mm;
        font-size: 7.2px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #1f6fb2;
    }}
    .full-report-step-title {{
        font-size: 9px;
        font-weight: 800;
        color: #101418;
    }}
    .full-report-step-text {{
        font-size: 8.3px;
        line-height: 1.55;
        color: #101418;
    }}
    .full-report-step.compact {{
        padding: 1.8mm 2.2mm;
    }}
    .full-report-step.compact .full-report-step-header {{
        margin-bottom: 0.5mm;
    }}
    .full-report-inline-value {{
        margin-top: 0.8mm;
        font-size: 8.3px;
        line-height: 1.5;
        color: #1f6fb2;
        font-weight: 700;
    }}
    .full-report-notation {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1.8mm 2.4mm;
    }}
    .full-report-notation-item {{
        border: 1px solid #d8e0ea;
        border-radius: 12px;
        padding: 2mm 2.3mm;
        background: #fbfcfe;
    }}
    .full-report-notation-term {{
        font-size: 8.6px;
        font-weight: 800;
        color: #101418;
    }}
    .full-report-notation-definition {{
        margin-top: 0.6mm;
        font-size: 8px;
        line-height: 1.45;
        color: #101418;
    }}
    .full-report-notation-unit {{
        margin-top: 0.6mm;
        font-size: 7.2px;
        color: #475467;
    }}
    .full-report-equation-block,
    .full-report-substitution-block,
    .full-report-result-block,
    .full-report-note-block {{
        margin-top: 1mm;
        padding: 1.2mm 1.5mm;
        border-radius: 10px;
        border: 1px solid #d8e0ea;
        background: #ffffff;
    }}
    .full-report-block-label {{
        font-size: 6.8px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 700;
        color: #475467;
    }}
    .full-report-block-value {{
        margin-top: 0.7mm;
        font-size: 8.2px;
        line-height: 1.45;
        color: #101418;
    }}
    .full-report-result-block .full-report-block-value {{
        font-weight: 800;
        color: #1f6fb2;
    }}
    .full-report-page-number {{
        margin-top: 3mm;
        font-size: 7px;
        color: #475467;
        text-align: right;
    }}
    @page {{
        size: A4 portrait;
        margin: 8mm;
    }}
    @media print {{
        :root {{
            color-scheme: light;
        }}
        .screen-only,
        header[data-testid="stHeader"],
        div[data-testid="stToolbar"],
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"],
        div[data-testid="stSidebar"],
        div[data-testid="collapsedControl"] {{
            display: none !important;
        }}
        .block-container {{
            padding: 0 !important;
            max-width: none !important;
        }}
        .full-report-page {{
            width: 194mm;
            min-height: 281mm;
            margin: 0 auto !important;
            padding: 0 !important;
            border: none !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            background: #ffffff !important;
            color: #101418 !important;
        }}
        .full-report-section,
        .full-report-meta-item,
        .full-report-summary-card,
        .full-report-figure-block,
        .full-report-step,
        .full-report-equation-block,
        .full-report-substitution-block,
        .full-report-result-block,
        .full-report-note-block {{
            border-color: #cfd7e3 !important;
        }}
        .full-report-section,
        .full-report-summary-card,
        .full-report-meta-item {{
            background: #ffffff !important;
        }}
        .full-report-figure-block,
        .full-report-step {{
            background: #f5f7fb !important;
        }}
        .full-report-root,
        .full-report-root * {{
            color: #101418 !important;
        }}
        .full-report-result {{
            color: {palette.accent} !important;
        }}
    }}
    </style>
    """


def _build_material_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    return ReportSection(
        title="Material Properties",
        rows=[
            ReportRow(
                "Ec",
                results.materials.ec_default_logic,
                _material_substitution(results.materials.ec_mode.value, results.materials.ec_default_ksc, inputs.material_settings.ec.manual_value),
                format_number(results.materials.ec_ksc),
                "ksc",
                status=results.materials.ec_mode.value,
                note=_material_note(results.materials.ec_mode.value, results.materials.ec_default_logic),
            ),
            ReportRow(
                "Es",
                results.materials.es_default_logic,
                _material_substitution(results.materials.es_mode.value, results.materials.es_default_ksc, inputs.material_settings.es.manual_value),
                format_number(results.materials.es_ksc),
                "ksc",
                status=results.materials.es_mode.value,
            ),
            ReportRow(
                "fr",
                results.materials.fr_default_logic,
                _material_substitution(results.materials.fr_mode.value, results.materials.fr_default_ksc, inputs.material_settings.fr.manual_value),
                format_number(results.materials.modulus_of_rupture_fr_ksc),
                "ksc",
                status=results.materials.fr_mode.value,
            ),
            ReportRow(
                "n",
                "Es / Ec",
                f"{format_number(results.materials.es_ksc)} / {format_number(results.materials.ec_ksc)}",
                format_ratio(results.materials.modular_ratio_n),
                "-",
                status=VerificationStatus.VERIFIED_CODE.value,
            ),
            ReportRow(
                "beta1",
                "Current beta1 logic",
                f"fc' = {inputs.materials.concrete_strength_ksc:.2f}",
                format_ratio(results.materials.beta_1),
                "-",
                status=VerificationStatus.VERIFIED_CODE.value,
                note="ACI 318-99/08/11 10.2.7.3; ACI 318-14/19/25 22.2.2.4.3",
            ),
        ],
    )


def _build_geometry_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    primary_section_label = _primary_section_label(inputs)
    rows = [
        ReportRow("Section area", "b * h", f"{inputs.geometry.width_cm:.2f} * {inputs.geometry.depth_cm:.2f}", format_number(results.beam_geometry.section_area_cm2), "cm2"),
        ReportRow("Ig", "b * h^3 / 12", f"{inputs.geometry.width_cm:.2f} * {inputs.geometry.depth_cm:.2f}^3 / 12", format_number(results.beam_geometry.gross_moment_of_inertia_cm4), "cm4"),
        ReportRow("d'", "Top compression steel centroid", "Layer centroid calculation", format_number(results.beam_geometry.positive_compression_centroid_d_prime_cm), "cm", note="Compression reinforcement"),
        ReportRow("d", "Bottom tension steel centroid", "Layer centroid calculation", format_number(results.beam_geometry.positive_tension_centroid_from_bottom_d_cm), "cm", note=f"{primary_section_label} tension reinforcement"),
        ReportRow("d+", "h - d", f"{inputs.geometry.depth_cm:.2f} - {results.beam_geometry.positive_tension_centroid_from_bottom_d_cm:.2f}", format_number(results.beam_geometry.d_plus_cm), "cm", note=f"{primary_section_label} effective depth"),
    ]
    if inputs.has_negative_design and results.beam_geometry.d_minus_cm is not None:
        rows.append(
            ReportRow(
                "d-",
                "h - d(top tension centroid)",
                f"{inputs.geometry.depth_cm:.2f} - {results.beam_geometry.negative_tension_centroid_from_top_cm:.2f}",
                format_number(results.beam_geometry.d_minus_cm),
                "cm",
                note="Negative effective depth",
            )
        )
    return ReportSection(title="Section Geometry", rows=rows)


def _build_positive_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    positive = results.positive_bending
    mn_equation, mn_substitution = _moment_capacity_row_content(
        positive,
        default_equation="As * fy * (d - a/2) / 100",
        default_substitution=(
            f"{format_number(positive.as_provided_cm2)} * {format_number(inputs.materials.main_steel_yield_ksc)} "
            f"* ({format_number(results.beam_geometry.d_plus_cm)} - {format_number(positive.a_cm)}/2) / 100"
        ),
    )
    return ReportSection(
        title="Middle Moment Design" if inputs.beam_type == BeamType.SIMPLE else "Positive Moment Design",
        rows=[
            ReportRow("Tension Reinforcement", "Bottom bars", _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Bottom bars"),
            ReportRow("Compression Reinforcement", "Top bars", _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Top bars"),
            ReportRow("phi", "Current / ACI-style phi logic", f"et = {positive.et:.6f}", format_ratio(positive.phi), "-", positive.ratio_status),
            ReportRow("Ru", "Mu * 100 / (phi * b * d^2)", f"{format_number(inputs.positive_bending.factored_moment_kgm)} * 100 / ({format_ratio(positive.phi, 3)} * {format_number(inputs.geometry.width_cm)} * {format_number(results.beam_geometry.d_plus_cm)}^2)", format_number(positive.ru_kg_per_cm2), "kg/cm2"),
            ReportRow("rho required", "0.85(fc'/fy)(1-sqrt(1-2Ru/(0.85fc')))", f"Ru = {format_number(positive.ru_kg_per_cm2)}", format_ratio(positive.rho_required, 6), "-", positive.as_status),
            ReportRow("rho provided", "As / (b*d)", f"{format_number(positive.as_provided_cm2)} / ({format_number(inputs.geometry.width_cm)} * {format_number(results.beam_geometry.d_plus_cm)})", format_ratio(positive.rho_provided, 6), "-", positive.as_status),
            ReportRow("rho min", "Current code-style minimum", f"fy = {format_number(inputs.materials.main_steel_yield_ksc)}", format_ratio(positive.rho_min, 6), "-"),
            ReportRow("rho max", "Current code-style maximum", f"beta1 = {format_ratio(results.materials.beta_1, 4)}", format_ratio(positive.rho_max, 6), "-"),
            ReportRow("As required", "rho_req * b * d", f"{positive.rho_required:.6f} * {inputs.geometry.width_cm:.2f} * {results.beam_geometry.d_plus_cm:.2f}", format_number(positive.as_required_cm2), "cm2"),
            ReportRow("As provided", "sum(bar areas)", _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), format_number(positive.as_provided_cm2), "cm2", positive.as_status),
            ReportRow("As min", "rho_min * b * d", f"{positive.rho_min:.6f} * {inputs.geometry.width_cm:.2f} * {results.beam_geometry.d_plus_cm:.2f}", format_number(positive.as_min_cm2), "cm2"),
            ReportRow("As max", "rho_max * b * d", f"{positive.rho_max:.6f} * {inputs.geometry.width_cm:.2f} * {results.beam_geometry.d_plus_cm:.2f}", format_number(positive.as_max_cm2), "cm2"),
            ReportRow("a", "As * fy / (0.85 * fc' * b)", f"{format_number(positive.as_provided_cm2)} * {format_number(inputs.materials.main_steel_yield_ksc)} / (0.85 * {format_number(inputs.materials.concrete_strength_ksc)} * {format_number(inputs.geometry.width_cm)})", format_number(positive.a_cm), "cm"),
            ReportRow("c", "a / beta1", f"{format_number(positive.a_cm)} / {format_ratio(results.materials.beta_1, 4)}", format_number(positive.c_cm), "cm"),
            ReportRow("dt", "h - cover - stirrup - db/2", f"{format_number(inputs.geometry.depth_cm)} - {format_number(inputs.geometry.cover_cm)} - {format_number(inputs.shear.stirrup_diameter_mm / 10)} - db/2", format_number(positive.dt_cm), "cm"),
            ReportRow("ety", "fy / Es", f"{format_number(inputs.materials.main_steel_yield_ksc)} / {format_number(results.materials.es_ksc)}", format_ratio(positive.ety, 6), "-"),
            ReportRow("et", "ecu * (dt - c) / c", f"0.003 * ({format_number(positive.dt_cm)} - {format_number(positive.c_cm)}) / {format_number(positive.c_cm)}", format_ratio(positive.et, 6), "-"),
            ReportRow("Mn", mn_equation, mn_substitution, format_number(positive.mn_kgm), "kg-m"),
            ReportRow("phiMn", "phi * Mn", f"{positive.phi:.3f} * {positive.mn_kgm:.2f}", format_number(positive.phi_mn_kgm), "kg-m", positive.ratio_status),
            ReportRow("Moment capacity ratio", "Mu / PhiMn", f"{format_number(inputs.positive_bending.factored_moment_kgm)} / {format_number(positive.phi_mn_kgm)}", format_ratio(positive.ratio), "-", positive.design_status),
        ],
    )


def _build_support_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    support = results.support_bending
    if support is None:
        raise ValueError("Support moment report section requested without support results.")
    mn_equation, mn_substitution = _moment_capacity_row_content(
        support,
        default_equation="As * fy * (d - a/2) / 100",
        default_substitution=(
            f"{format_number(support.as_provided_cm2)} * {format_number(inputs.materials.main_steel_yield_ksc)} "
            f"* ({format_number(results.beam_geometry.d_plus_cm)} - {format_number(support.a_cm)}/2) / 100"
        ),
    )
    support_note = "Auto Mu at support - L/4 from simple beam moment diagram." if inputs.simple_support_bending.moment_mode.value == "Auto" else "Manual Mu at support - L/4."
    return ReportSection(
        title="Support Moment Design",
        rows=[
            ReportRow("Tension Reinforcement", "Bottom bars", _format_arrangement(inputs.simple_support_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.simple_support_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Bottom bars"),
            ReportRow("Compression Reinforcement", "Top bars", _format_arrangement(inputs.simple_support_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.simple_support_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Top bars"),
            ReportRow("Mu", "Support - L/4", support_note, format_number(inputs.resolved_simple_support_moment_kgm), "kg-m"),
            ReportRow("Mn", mn_equation, mn_substitution, format_number(support.mn_kgm), "kg-m"),
            ReportRow("phiMn", "phi * Mn", f"{support.phi:.3f} * {support.mn_kgm:.2f}", format_number(support.phi_mn_kgm), "kg-m", support.ratio_status),
            ReportRow("Moment capacity ratio", "Mu / PhiMn", f"{format_number(inputs.resolved_simple_support_moment_kgm)} / {format_number(support.phi_mn_kgm)}", format_ratio(support.ratio), "-", support.design_status),
        ],
    )


def _build_shear_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    shear = results.shear
    return ReportSection(
        title="Shear Design",
        rows=[
            ReportRow("phi", "Shear phi by selected code", inputs.metadata.design_code.value, format_ratio(shear.phi), "-", shear.design_status),
            ReportRow("Shear basis", "Active flexural section controlling shear depth", _shear_basis_text(results), shear.design_section_label, "-", shear.design_status, shear.section_change_note),
            ReportRow("d used for shear", "Effective depth used in Vc, Vs, and Vn", _shear_basis_text(results), _shear_effective_depth_text(results), "cm"),
            ReportRow("Vc", "0.53 * sqrt(fc') * b * d", f"Current nominal concrete shear with d = {_shear_effective_depth_text(results)} cm", format_number(shear.vc_kg), "kg"),
            ReportRow("phiVc", "phi * Vc", f"{shear.phi:.3f} * {shear.vc_kg:.2f}", format_number(shear.phi_vc_kg), "kg"),
            ReportRow("Vs,max", "2.1 * sqrt(fc') * b * d", f"Current nominal steel shear limit with d = {_shear_effective_depth_text(results)} cm", format_number(shear.vs_max_kg), "kg"),
            ReportRow("phiVs,max", "phi * Vs,max", f"{format_ratio(shear.phi, 3)} * {format_number(shear.vs_max_kg)}", format_number(shear.phi_vs_max_kg), "kg"),
            ReportRow("phiVs required", "Vu - phiVc", f"{format_number(shear.input_factored_shear_kg)} - {format_number(shear.phi_vc_kg)}", format_number(shear.phi_vs_required_kg), "kg"),
            ReportRow("Vs required", "phiVs required / phi", f"{format_number(shear.phi_vs_required_kg)} / {format_ratio(shear.phi, 3)}", format_number(shear.nominal_vs_required_kg), "kg"),
            ReportRow("Av", "pi * db^2 / 4 * legs", f"db={inputs.shear.stirrup_diameter_mm}, legs={inputs.shear.legs_per_plane}", format_number(shear.av_cm2), "cm2"),
            ReportRow("Av,min", "Minimum stirrup area at provided spacing", f"s = {format_number(shear.provided_spacing_cm)}", format_number(shear.av_min_cm2), "cm2", shear.design_status if shear.minimum_reinforcement_required and shear.av_cm2 < shear.av_min_cm2 else None),
            ReportRow("Size effect", "ACI 318-19/25 lambda_s", "Applied to Vc when Av < Av,min" if shear.size_effect_applied else "Not applied", format_ratio(shear.size_effect_factor, 3), "-", shear.design_status if shear.minimum_reinforcement_required and shear.size_effect_applied else None),
            ReportRow("s max from Av", "min(Av*fvy/(0.2*sqrt(fc')*b), Av*fvy/(3.5*b))", "Current spacing limit", format_number(shear.s_max_from_av_cm), "cm"),
            ReportRow("s max from Vs", "Code-style spacing limit", "Current branch logic", format_number(shear.s_max_from_vs_cm), "cm"),
            ReportRow("Required spacing", "min(s strength, s max from Av, s max from Vs)", "Governing required spacing", format_number(shear.required_spacing_cm), "cm"),
            ReportRow("Provided spacing", f"{shear.spacing_mode.value} selection", "Spacing used for PhiVs and PhiVn", format_number(shear.provided_spacing_cm), "cm", shear.design_status),
            ReportRow("Vs", "Av * fvy * d / s", f"Use d = {_shear_effective_depth_text(results)} cm and s = {format_number(shear.provided_spacing_cm)} cm", format_number(shear.vs_provided_kg), "kg"),
            ReportRow("PhiVs", "phi * Vs", f"{shear.phi:.3f} * {format_number(shear.vs_provided_kg)}", format_number(shear.phi_vs_provided_kg), "kg"),
            ReportRow("Vn", "Vc + min(Vs, Vs,max)", f"{format_number(shear.vc_kg)} + min({format_number(shear.vs_provided_kg)}, {format_number(shear.vs_max_kg)})", format_number(shear.vn_kg), "kg"),
            ReportRow("PhiVn", "phi * Vn", f"{shear.phi:.3f} * {format_number(shear.vn_kg)}", format_number(shear.phi_vn_kg), "kg"),
            ReportRow("Stirrup spacing", "Provided spacing", f"{shear.spacing_mode.value} mode", format_number(shear.provided_spacing_cm), "cm", shear.design_status, shear.review_note),
            ReportRow("Shear capacity ratio", "Vu / PhiVn", f"{format_number(shear.input_factored_shear_kg)} / {format_number(shear.phi_vn_kg)}", format_ratio(shear.capacity_ratio), "-", shear.design_status),
        ],
    )


def _build_torsion_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    torsion = results.torsion
    combined = results.combined_shear_torsion
    if combined.torsion_ignored:
        return ReportSection(
            title="Torsion Design",
            rows=[
                ReportRow("Tu", "-", format_number(torsion.tu_kgfm), format_number(torsion.tu_kgfm), "kgf-m"),
                ReportRow("Threshold torsion", "Neglect check", "-", format_number(torsion.threshold_torsion_kgfm), "kgf-m"),
                ReportRow("Summary", "-", combined.ignore_message, "Ignore Tu", "-", "PASS"),
            ],
        )
    rows = [
        ReportRow("Code", "-", torsion.code_version, torsion.code_version, "-"),
        ReportRow("Tu", "-", format_number(torsion.tu_kgfm), format_number(torsion.tu_kgfm), "kgf-m", torsion.status),
        ReportRow("Threshold torsion", "Neglect check", "-", format_number(torsion.threshold_torsion_kgfm), "kgf-m", torsion.status),
        ReportRow("Shear & Torsion", "-", f"Vu = {format_number(combined.vu_kg)} | Tu = {format_number(combined.tu_kgfm)}", combined.design_status if combined.active else torsion.status, "-", combined.design_status if combined.active else torsion.status),
        ReportRow("Shear-only req.", "-", "-", f"{combined.shear_required_transverse_mm2_per_mm:.6f}", "mm2/mm", combined.design_status if combined.active else torsion.status),
        ReportRow("Torsion-only req.", "-", "-", f"{combined.torsion_required_transverse_mm2_per_mm:.6f}", "mm2/mm", combined.design_status if combined.active else torsion.status),
        ReportRow("Combined req.", "-", "-", f"{combined.combined_required_transverse_mm2_per_mm:.6f}", "mm2/mm", combined.design_status if combined.active else torsion.status),
        ReportRow("Provided transverse", "-", "-", f"{combined.provided_transverse_mm2_per_mm:.6f}", "mm2/mm", combined.design_status if combined.active else torsion.status),
        ReportRow("Capacity Ratio (Shear + Torsion)", "-", combined.summary_note, format_ratio(combined.capacity_ratio), "-", combined.design_status if combined.active else torsion.status),
        ReportRow("At/s req.", torsion.transverse_reinf_required_governing, "-", f"{torsion.transverse_reinf_required_mm2_per_mm:.6f}", "mm2/mm", torsion.status),
        ReportRow("Al req.", torsion.longitudinal_reinf_required_governing, "-", format_number(mm2_to_cm2(torsion.longitudinal_reinf_required_mm2)), "cm2", torsion.status),
        ReportRow("Al prov.", "User input", "-", format_number(mm2_to_cm2(torsion.longitudinal_reinf_provided_mm2)), "cm2", torsion.status),
        ReportRow("Summary", torsion.governing_equation or "-", torsion.pass_fail_summary, torsion.status, "-", torsion.status),
    ]
    if combined.cross_section_limit_check_applied:
        rows.insert(
            9,
            ReportRow(
                "Combined section limit",
                combined.cross_section_limit_clause,
                f"{combined.cross_section_limit_lhs_mpa:.3f} <= {combined.cross_section_limit_rhs_mpa:.3f}",
                format_ratio(combined.cross_section_limit_ratio),
                "-",
                combined.design_status,
                combined.design_status_note,
            ),
        )
    return ReportSection(title="Torsion Design", rows=rows)


def _build_negative_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    negative = results.negative_bending
    if negative is None:
        raise ValueError("Negative moment report section requested for a simple beam result.")
    d_minus_cm = results.beam_geometry.d_minus_cm
    d_minus_text = format_number(d_minus_cm) if d_minus_cm is not None else "N/A"
    mn_equation, mn_substitution = _moment_capacity_row_content(
        negative,
        default_equation="As * fy * (d- - a/2) / 100",
        default_substitution=(
            f"{format_number(negative.as_provided_cm2)} * {format_number(inputs.materials.main_steel_yield_ksc)} "
            f"* ({d_minus_text} - {format_number(negative.a_cm)}/2) / 100"
        ),
    )
    return ReportSection(
        title="Negative Moment Design",
        rows=[
            ReportRow("Tension Reinforcement", "Top bars", _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Top bars"),
            ReportRow("Compression Reinforcement", "Bottom bars", _format_arrangement(inputs.negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Bottom bars"),
            ReportRow("phi", "Current / ACI-style phi logic", f"et = {negative.et:.6f}", format_ratio(negative.phi), "-", negative.ratio_status),
            ReportRow("Ru", "Mu * 100 / (phi * b * d^2)", f"{format_number(inputs.negative_bending.factored_moment_kgm)} * 100 / ({format_ratio(negative.phi, 3)} * {format_number(inputs.geometry.width_cm)} * {d_minus_text}^2)", format_number(negative.ru_kg_per_cm2), "kg/cm2"),
            ReportRow("rho required", "Current flexural demand equation", f"Ru = {format_number(negative.ru_kg_per_cm2)}", format_ratio(negative.rho_required, 6), "-"),
            ReportRow("rho provided", "As / (b*d-)", f"{format_number(negative.as_provided_cm2)} / ({format_number(inputs.geometry.width_cm)} * {d_minus_text})", format_ratio(negative.rho_provided, 6), "-", negative.as_status),
            ReportRow("As required", "rho_req * b * d-", f"{negative.rho_required:.6f} * {inputs.geometry.width_cm:.2f} * {d_minus_text}", format_number(negative.as_required_cm2), "cm2"),
            ReportRow("As provided", "sum(bar areas)", _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), format_number(negative.as_provided_cm2), "cm2", negative.as_status),
            ReportRow("As min", "rho_min * b * d-", f"{negative.rho_min:.6f} * {inputs.geometry.width_cm:.2f} * {d_minus_text}", format_number(negative.as_min_cm2), "cm2"),
            ReportRow("As max", "rho_max * b * d-", f"{negative.rho_max:.6f} * {inputs.geometry.width_cm:.2f} * {d_minus_text}", format_number(negative.as_max_cm2), "cm2"),
            ReportRow("a", "As * fy / (0.85 * fc' * b)", "Negative bending", format_number(negative.a_cm), "cm"),
            ReportRow("c", "a / beta1", "Negative bending", format_number(negative.c_cm), "cm"),
            ReportRow("et", "ecu * (dt - c) / c", f"0.003 * ({format_number(negative.dt_cm)} - {format_number(negative.c_cm)}) / {format_number(negative.c_cm)}", format_ratio(negative.et, 6), "-"),
            ReportRow("Mn", mn_equation, mn_substitution, format_number(negative.mn_kgm), "kg-m"),
            ReportRow("phiMn", "phi * Mn", f"{negative.phi:.3f} * {negative.mn_kgm:.2f}", format_number(negative.phi_mn_kgm), "kg-m", negative.ratio_status),
        ],
    )


def _build_spacing_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    rows: list[ReportRow] = []
    spacing_groups = [
        ("Positive compression", results.beam_geometry.positive_compression_spacing),
        ("Positive tension", results.beam_geometry.positive_tension_spacing),
    ]
    if inputs.has_negative_design and results.beam_geometry.negative_compression_spacing and results.beam_geometry.negative_tension_spacing:
        spacing_groups.extend(
            [
                ("Negative compression", results.beam_geometry.negative_compression_spacing),
                ("Negative tension", results.beam_geometry.negative_tension_spacing),
            ]
        )
    for label, spacing in spacing_groups:
        for layer in spacing.layers():
            if not _spacing_layer_has_reinforcement(layer):
                continue
            rows.append(
                ReportRow(
                    f"{label} L{layer.layer_index}",
                    "Provided clear spacing",
                    f"Provided = {format_number(layer.spacing_cm)} | Required = {format_number(layer.required_spacing_cm)}",
                    layer.status,
                    "-",
                    layer.status,
                    layer.message,
                )
            )
    return ReportSection(title="Reinforcement Spacing Checks", rows=rows)


def _build_warning_section(results: BeamDesignResults) -> ReportSection:
    rows = [
        ReportRow(
            f"Warning {index}",
            "-",
            message,
            message,
            "-",
            "Warning",
        )
        for index, message in enumerate(results.warnings, start=1)
    ]
    if not rows:
        rows = [ReportRow("Warnings", "-", "No immediate warnings.", "No immediate warnings.", "-", "OK")]
    return ReportSection(title="Warnings", rows=rows)


def _build_review_flag_section(results: BeamDesignResults) -> ReportSection:
    rows = [
        ReportRow(
            flag.title,
            flag.verification_status.value,
            flag.message,
            flag.severity.title(),
            "-",
            flag.severity.title(),
        )
        for flag in results.review_flags
    ]
    return ReportSection(title="Review Flags", rows=rows)


def _build_full_material_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    ec_substitution = (
        f"E_c = 15100 x sqrt({format_number(inputs.materials.concrete_strength_ksc)})"
        if results.materials.ec_mode.value == "Default"
        else f"User-defined value = {format_number(results.materials.ec_ksc)}"
    )
    es_substitution = (
        f"E_s = {format_number(results.materials.es_default_ksc)}"
        if results.materials.es_mode.value == "Default"
        else f"User-defined value = {format_number(results.materials.es_ksc)}"
    )
    fr_substitution = (
        f"f_r = 2 x sqrt({format_number(inputs.materials.concrete_strength_ksc)})"
        if results.materials.fr_mode.value == "Default"
        else f"User-defined value = {format_number(results.materials.modulus_of_rupture_fr_ksc)}"
    )
    return ReportSection(
        title="Material Properties",
        rows=[
            ReportRow(_sym_ec(), _format_default_ec_logic(), ec_substitution.replace("E_c", _sym_ec()).replace("f'c", _sym_fc()), format_number(results.materials.ec_ksc), "ksc", results.materials.ec_mode.value),
            ReportRow(_sym_es(), "-", es_substitution.replace("E_s", _sym_es()), format_number(results.materials.es_ksc), "ksc", results.materials.es_mode.value),
            ReportRow(_sym_fr(), _format_default_fr_logic(), fr_substitution.replace("f_r", _sym_fr()).replace("f'c", _sym_fc()), format_number(results.materials.modulus_of_rupture_fr_ksc), "ksc", results.materials.fr_mode.value),
            ReportRow("n", f"n = {_sym_es()} / {_sym_ec()}", f"n = {format_number(results.materials.es_ksc)} / {format_number(results.materials.ec_ksc)}", format_ratio(results.materials.modular_ratio_n), "-", results.materials.ec_mode.value),
            ReportRow(_sym_beta1(), "-", f"{_sym_beta1()} from {_sym_fc()} = {format_number(inputs.materials.concrete_strength_ksc)} ksc", format_ratio(results.materials.beta_1), "-", VerificationStatus.VERIFIED_CODE.value),
        ],
    )


def _build_full_geometry_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    primary_section_label = _primary_section_label(inputs)
    rows = [
        ReportRow("A<sub>g</sub>", "A<sub>g</sub> = b x h", f"A<sub>g</sub> = {format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)}", format_number(results.beam_geometry.section_area_cm2), _unit_cm2()),
        ReportRow("I<sub>g</sub>", "I<sub>g</sub> = bh<sup>3</sup> / 12", f"I<sub>g</sub> = {format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)}<sup>3</sup> / 12", format_number(results.beam_geometry.gross_moment_of_inertia_cm4), "cm<sup>4</sup>"),
        ReportRow("d′", "-", "Centroid of top reinforcement from compression face", format_number(results.beam_geometry.positive_compression_centroid_d_prime_cm), "cm"),
        ReportRow("d", "-", f"Effective depth to the {primary_section_label.lower()} tension reinforcement", format_number(results.beam_geometry.d_plus_cm), "cm"),
    ]
    if inputs.has_negative_design and results.beam_geometry.d_minus_cm is not None:
        rows.append(
            ReportRow("d-", "-", "Effective depth for negative moment reinforcement", format_number(results.beam_geometry.d_minus_cm), "cm")
        )
    return ReportSection(title="Section Geometry", rows=rows)


def _build_full_positive_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    positive = results.positive_bending
    mn_equation, mn_substitution = _moment_capacity_row_content(
        positive,
        default_equation=f"{_sym_mn()} = A<sub>s</sub>{_sym_fy()}(d - a/2) / 100",
        default_substitution=(
            f"{_sym_mn()} = {format_number(positive.as_provided_cm2)} &times; {format_number(inputs.materials.main_steel_yield_ksc)} "
            f"&times; ({format_number(results.beam_geometry.d_plus_cm)} - {format_number(positive.a_cm)}/2) / 100"
        ),
    )
    return ReportSection(
        title="Middle Moment Design" if inputs.beam_type == BeamType.SIMPLE else "Positive Moment Design",
        rows=[
            ReportRow("Tension reinforcement", "-", _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
            ReportRow("Compression reinforcement", "-", _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
            ReportRow("M<sub>u</sub>", "-", "M<sub>u</sub> = " + f"{format_number(inputs.positive_bending.factored_moment_kgm)} kg-m", format_number(inputs.positive_bending.factored_moment_kgm), "kg-m"),
            ReportRow("&phi;", "-", f"From tensile strain, &epsilon;<sub>t</sub> = {format_ratio(positive.et, 6)}", format_ratio(positive.phi), "-", positive.ratio_status),
            ReportRow("R<sub>u</sub>", "R<sub>u</sub> = M<sub>u</sub> &times; 100 / (&phi;bd<sup>2</sup>)", f"R<sub>u</sub> = {format_number(inputs.positive_bending.factored_moment_kgm)} &times; 100 / ({format_ratio(positive.phi, 3)} &times; {format_number(inputs.geometry.width_cm)} &times; {format_number(results.beam_geometry.d_plus_cm)}<sup>2</sup>)", format_number(positive.ru_kg_per_cm2), "kg/cm<sup>2</sup>"),
            ReportRow(_sym_rho_req(), f"{_sym_rho_req()} = 0.85({_sym_fc()}/{_sym_fy()})[1 - &radic;(1 - 2R<sub>u</sub>/(0.85{_sym_fc()}))]", f"Use R<sub>u</sub> = {format_number(positive.ru_kg_per_cm2)}", format_ratio(positive.rho_required, 6), "-", positive.as_status),
            ReportRow("&rho;<sub>prov</sub>", "&rho;<sub>prov</sub> = A<sub>s</sub> / (bd)", f"&rho;<sub>prov</sub> = {format_number(positive.as_provided_cm2)} / ({format_number(inputs.geometry.width_cm)} &times; {format_number(results.beam_geometry.d_plus_cm)})", format_ratio(positive.rho_provided, 6), "-", positive.as_status),
            ReportRow("&rho;<sub>min</sub>", "-", f"From {_sym_fc()} = {format_number(inputs.materials.concrete_strength_ksc)} and {_sym_fy()} = {format_number(inputs.materials.main_steel_yield_ksc)}", format_ratio(positive.rho_min, 6), "-", positive.as_status),
            ReportRow("&rho;<sub>max</sub>", "-", f"From {_sym_beta1()} = {format_ratio(results.materials.beta_1, 4)}", format_ratio(positive.rho_max, 6), "-", positive.as_status),
            ReportRow(_sym_as_req(), f"{_sym_as_req()} = {_sym_rho_req()}bd", f"{_sym_as_req()} = {format_ratio(positive.rho_required, 6)} &times; {format_number(inputs.geometry.width_cm)} &times; {format_number(results.beam_geometry.d_plus_cm)}", format_number(positive.as_required_cm2), _unit_cm2()),
            ReportRow(_sym_as_prov(), "-", _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), format_number(positive.as_provided_cm2), _unit_cm2(), positive.as_status),
            ReportRow("A<sub>s,min</sub>", "A<sub>s,min</sub> = &rho;<sub>min</sub>bd", f"A<sub>s,min</sub> = {format_ratio(positive.rho_min, 6)} &times; {format_number(inputs.geometry.width_cm)} &times; {format_number(results.beam_geometry.d_plus_cm)}", format_number(positive.as_min_cm2), _unit_cm2()),
            ReportRow("A<sub>s,max</sub>", "A<sub>s,max</sub> = &rho;<sub>max</sub>bd", f"A<sub>s,max</sub> = {format_ratio(positive.rho_max, 6)} &times; {format_number(inputs.geometry.width_cm)} &times; {format_number(results.beam_geometry.d_plus_cm)}", format_number(positive.as_max_cm2), _unit_cm2()),
            ReportRow("a", "a = A<sub>s</sub>f<sub>y</sub> / (0.85f&#8242;<sub>c</sub>b)", f"a = {format_number(positive.as_provided_cm2)} &times; {format_number(inputs.materials.main_steel_yield_ksc)} / (0.85 &times; {format_number(inputs.materials.concrete_strength_ksc)} &times; {format_number(inputs.geometry.width_cm)})", format_number(positive.a_cm), "cm"),
            ReportRow("c", f"c = a / {_sym_beta1()}", f"c = {format_number(positive.a_cm)} / {format_ratio(results.materials.beta_1, 4)}", format_number(positive.c_cm), "cm"),
            ReportRow("d<sub>t</sub>", "-", f"d<sub>t</sub> = {format_number(positive.dt_cm)} cm", format_number(positive.dt_cm), "cm"),
            ReportRow("&epsilon;<sub>y</sub>", f"&epsilon;<sub>y</sub> = {_sym_fy()} / {_sym_es()}", f"&epsilon;<sub>y</sub> = {format_number(inputs.materials.main_steel_yield_ksc)} / {format_number(results.materials.es_ksc)}", format_ratio(positive.ety, 6), "-"),
            ReportRow("&epsilon;<sub>t</sub>", "&epsilon;<sub>t</sub> = 0.003(d<sub>t</sub> - c) / c", f"&epsilon;<sub>t</sub> = 0.003({format_number(positive.dt_cm)} - {format_number(positive.c_cm)}) / {format_number(positive.c_cm)}", format_ratio(positive.et, 6), "-"),
            ReportRow(_sym_mn(), mn_equation, mn_substitution, format_number(positive.mn_kgm), "kg-m"),
            ReportRow(_sym_phi_mn(), f"{_sym_phi_mn()} = &phi;{_sym_mn()}", f"{_sym_phi_mn()} = {format_ratio(positive.phi, 3)} &times; {format_number(positive.mn_kgm)}", format_number(positive.phi_mn_kgm), "kg-m", positive.ratio_status),
            ReportRow(f"M<sub>u</sub> / {_sym_phi_mn()}", "-", f"{format_number(inputs.positive_bending.factored_moment_kgm)} / {format_number(positive.phi_mn_kgm)}", format_ratio(positive.ratio), "-", positive.design_status),
        ],
    )


def _build_full_support_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    return _build_support_section(inputs, results)


def _build_full_shear_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    shear = results.shear
    return ReportSection(
        title="Shear Design",
        rows=[
            ReportRow(_sym_vu(), "-", f"{_sym_vu()} = {format_number(shear.input_factored_shear_kg)} kg", format_number(shear.input_factored_shear_kg), "kg"),
            ReportRow("&phi;", "-", f"Selected from {inputs.metadata.design_code.value}", format_ratio(shear.phi), "-", shear.design_status),
            ReportRow("Section basis", "-", _shear_basis_text(results), shear.design_section_label, "-", shear.design_status, shear.section_change_note),
            ReportRow("d<sub>shear</sub>", "-", f"d from {_shear_basis_text(results)} = {_shear_effective_depth_text(results)} cm", _shear_effective_depth_text(results), "cm"),
            ReportRow(_sym_vc(), f"{_sym_vc()} = 0.53&radic;{_sym_fc()}bd", f"{_sym_vc()} = 0.53 &times; &radic;{format_number(inputs.materials.concrete_strength_ksc)} &times; {format_number(inputs.geometry.width_cm)} &times; {_shear_effective_depth_text(results)}", format_number(shear.vc_kg), "kg"),
            ReportRow(_sym_phi_vc(), f"{_sym_phi_vc()} = &phi;{_sym_vc()}", f"{_sym_phi_vc()} = {format_ratio(shear.phi, 3)} &times; {format_number(shear.vc_kg)}", format_number(shear.phi_vc_kg), "kg"),
            ReportRow("V<sub>s,max</sub>", f"V<sub>s,max</sub> = 2.1&radic;{_sym_fc()}bd", f"V<sub>s,max</sub> = 2.1 &times; &radic;{format_number(inputs.materials.concrete_strength_ksc)} &times; {format_number(inputs.geometry.width_cm)} &times; {_shear_effective_depth_text(results)}", format_number(shear.vs_max_kg), "kg"),
            ReportRow("&phi;V<sub>s,max</sub>", "&phi;V<sub>s,max</sub> = &phi; &times; V<sub>s,max</sub>", f"&phi;V<sub>s,max</sub> = {format_ratio(shear.phi, 3)} &times; {format_number(shear.vs_max_kg)}", format_number(shear.phi_vs_max_kg), "kg"),
            ReportRow("&phi;V<sub>s,req</sub>", f"&phi;V<sub>s,req</sub> = {_sym_vu()} - {_sym_phi_vc()}", f"&phi;V<sub>s,req</sub> = {format_number(shear.input_factored_shear_kg)} - {format_number(shear.phi_vc_kg)}", format_number(shear.phi_vs_required_kg), "kg"),
            ReportRow("V<sub>s,req</sub>", "V<sub>s,req</sub> = &phi;V<sub>s,req</sub> / &phi;", f"V<sub>s,req</sub> = {format_number(shear.phi_vs_required_kg)} / {format_ratio(shear.phi, 3)}", format_number(shear.nominal_vs_required_kg), "kg"),
            ReportRow(_sym_av(), f"{_sym_av()} = &pi;d<sub>b</sub><sup>2</sup> / 4 &times; number of legs", f"{_sym_av()} = &pi; &times; {format_number(inputs.shear.stirrup_diameter_mm / 10)}<sup>2</sup> / 4 &times; {inputs.shear.legs_per_plane}", format_number(shear.av_cm2), _unit_cm2()),
            ReportRow("s_max,1", "-", "Limit from transverse reinforcement proportioning", format_number(shear.s_max_from_av_cm), "cm"),
            ReportRow("s_max,2", "-", "Limit from shear demand branch", format_number(shear.s_max_from_vs_cm), "cm"),
            ReportRow("s<sub>req</sub>", "s<sub>req</sub> = min(strength limit, spacing limits)", "Use the smallest permitted spacing", format_number(shear.required_spacing_cm), "cm"),
            ReportRow("s<sub>prov</sub>", "-", f"{shear.spacing_mode.value} spacing used in design", format_number(shear.provided_spacing_cm), "cm", shear.design_status),
            ReportRow(_sym_vs(), f"{_sym_vs()} = {_sym_av()}{_sym_fvy()}d / s<sub>prov</sub>", f"{_sym_vs()} = {format_number(shear.av_cm2)} &times; {format_number(inputs.materials.shear_steel_yield_ksc)} &times; {_shear_effective_depth_text(results)} / {format_number(shear.provided_spacing_cm)}", format_number(shear.vs_provided_kg), "kg"),
            ReportRow(_sym_phi_vs(), f"{_sym_phi_vs()} = &phi;{_sym_vs()}", f"{_sym_phi_vs()} = {format_ratio(shear.phi, 3)} &times; {format_number(shear.vs_provided_kg)}", format_number(shear.phi_vs_provided_kg), "kg"),
            ReportRow(_sym_vn(), f"{_sym_vn()} = {_sym_vc()} + min({_sym_vs()}, V<sub>s,max</sub>)", f"{_sym_vn()} = {format_number(shear.vc_kg)} + min({format_number(shear.vs_provided_kg)}, {format_number(shear.vs_max_kg)})", format_number(shear.vn_kg), "kg"),
            ReportRow(_sym_phi_vn(), f"{_sym_phi_vn()} = &phi;{_sym_vn()}", f"{_sym_phi_vn()} = {format_ratio(shear.phi, 3)} &times; {format_number(shear.vn_kg)}", format_number(shear.phi_vn_kg), "kg"),
            ReportRow(f"{_sym_vu()} / {_sym_phi_vn()}", "-", f"{format_number(shear.input_factored_shear_kg)} / {format_number(shear.phi_vn_kg)}", format_ratio(shear.capacity_ratio), "-", shear.design_status, shear.review_note),
        ],
    )


def _build_full_torsion_section(results: BeamDesignResults) -> ReportSection:
    torsion = results.torsion
    combined = results.combined_shear_torsion
    if combined.torsion_ignored:
        return ReportSection(
            title="Torsion Design",
            rows=[
                ReportRow("Tu", "-", format_number(torsion.tu_kgfm), format_number(torsion.tu_kgfm), "kgf-m"),
                ReportRow("Threshold torsion", "Neglect check", "-", format_number(torsion.threshold_torsion_kgfm), "kgf-m"),
                ReportRow("Summary", "-", combined.ignore_message, "Ignore Tu", "-", "PASS"),
            ],
        )
    rows = [
        ReportRow("Torsion code", "-", torsion.code_version, torsion.code_version, "-"),
        ReportRow("Demand type", "-", torsion.demand_type.value, torsion.demand_type.value, "-"),
        ReportRow("Tu", "-", format_number(torsion.tu_kgfm), format_number(torsion.tu_kgfm), "kgf-m", torsion.status),
        ReportRow("Threshold torsion", "Neglect check", "-", format_number(torsion.threshold_torsion_kgfm), "kgf-m", torsion.status),
        ReportRow("Shear & Torsion", "-", f"Vu = {format_number(combined.vu_kg)} | Tu = {format_number(combined.tu_kgfm)}", combined.design_status if combined.active else torsion.status, "-", combined.design_status if combined.active else torsion.status),
        ReportRow("Shear-only required transverse reinforcement", "-", "-", f"{combined.shear_required_transverse_mm2_per_mm:.6f}", "mm2/mm"),
        ReportRow("Torsion-only required transverse reinforcement", "-", "-", f"{combined.torsion_required_transverse_mm2_per_mm:.6f}", "mm2/mm"),
        ReportRow("Combined required transverse reinforcement", "-", "-", f"{combined.combined_required_transverse_mm2_per_mm:.6f}", "mm2/mm", combined.design_status if combined.active else torsion.status),
        ReportRow("Provided transverse reinforcement", "-", "-", f"{combined.provided_transverse_mm2_per_mm:.6f}", "mm2/mm", combined.design_status if combined.active else torsion.status),
        ReportRow("Capacity Ratio (Shear + Torsion)", "-", combined.summary_note, format_ratio(combined.capacity_ratio), "-", combined.design_status if combined.active else torsion.status),
        ReportRow("Acp / pcp", "Outside perimeter geometry", "-", f"{format_number(torsion.acp_mm2)} / {format_number(torsion.pcp_mm)}", "mm2 / mm"),
        ReportRow("Aoh / Ao / ph", "Thin-walled tube geometry", "-", f"{format_number(torsion.aoh_mm2)} / {format_number(torsion.ao_mm2)} / {format_number(torsion.ph_mm)}", "mm2 / mm2 / mm"),
        ReportRow("At/s req.", torsion.transverse_reinf_required_governing, "-", f"{torsion.transverse_reinf_required_mm2_per_mm:.6f}", "mm2/mm", torsion.status),
        ReportRow("At/s prov.", "One stirrup leg area / s", "-", f"{torsion.transverse_reinf_provided_mm2_per_mm:.6f}", "mm2/mm", torsion.status),
        ReportRow("Al req.", torsion.longitudinal_reinf_required_governing, "-", format_number(mm2_to_cm2(torsion.longitudinal_reinf_required_mm2)), "cm2", torsion.status),
        ReportRow("Al prov.", "User input", "-", format_number(mm2_to_cm2(torsion.longitudinal_reinf_provided_mm2)), "cm2", torsion.status),
        ReportRow("s max", "min(ph/8, 300 mm)", "-", format_number(mm_to_cm(torsion.max_spacing_mm)), "cm", torsion.status),
    ]
    if combined.cross_section_limit_check_applied:
        rows.insert(
            10,
            ReportRow(
                "Combined section limit",
                combined.cross_section_limit_clause,
                f"{combined.cross_section_limit_lhs_mpa:.3f} <= {combined.cross_section_limit_rhs_mpa:.3f}",
                format_ratio(combined.cross_section_limit_ratio),
                "-",
                combined.design_status,
                combined.design_status_note,
            ),
        )
    for row in build_torsion_report_rows(torsion):
        rows.append(
            ReportRow(
                row["variable"],
                row["equation"],
                row["substitution"],
                row["result"],
                row["units"],
                row["status"],
                f"{row['clause']} {row['note']}".strip(),
            )
        )
    warning_note = " | ".join(torsion.warnings)
    rows.append(ReportRow("Summary", torsion.governing_equation or "-", torsion.pass_fail_summary, torsion.status, "-", torsion.status, warning_note))
    return ReportSection(title="Torsion Design", rows=rows)


def _build_full_negative_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    negative = results.negative_bending
    if negative is None:
        raise ValueError("Negative moment report section requested for a simple beam result.")
    d_minus_cm = results.beam_geometry.d_minus_cm
    d_minus_text = format_number(d_minus_cm) if d_minus_cm is not None else "N/A"
    mn_equation, mn_substitution = _moment_capacity_row_content(
        negative,
        default_equation="M<sub>n,neg</sub> = A<sub>s</sub>f<sub>y</sub>(d<sub>neg</sub> - a/2) / 100",
        default_substitution=(
            f"M<sub>n,neg</sub> = {format_number(negative.as_provided_cm2)} &times; {format_number(inputs.materials.main_steel_yield_ksc)} "
            f"&times; ({d_minus_text} - {format_number(negative.a_cm)}/2) / 100"
        ),
    )
    return ReportSection(
        title="Negative Moment Design",
        rows=[
            ReportRow("Tension reinforcement", "-", _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
            ReportRow("Compression reinforcement", "-", _format_arrangement(inputs.negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
            ReportRow("M<sub>u,neg</sub>", "-", f"M<sub>u,neg</sub> = {format_number(inputs.negative_bending.factored_moment_kgm)} kg-m", format_number(inputs.negative_bending.factored_moment_kgm), "kg-m"),
            ReportRow("&phi;", "-", f"From tensile strain, &epsilon;<sub>t</sub> = {format_ratio(negative.et, 6)}", format_ratio(negative.phi), "-", negative.ratio_status),
            ReportRow("R<sub>u,neg</sub>", "R<sub>u,neg</sub> = M<sub>u,neg</sub> &times; 100 / (&phi;bd<sub>neg</sub><sup>2</sup>)", f"R<sub>u,neg</sub> = {format_number(inputs.negative_bending.factored_moment_kgm)} &times; 100 / ({format_ratio(negative.phi, 3)} &times; {format_number(inputs.geometry.width_cm)} &times; {d_minus_text}<sup>2</sup>)", format_number(negative.ru_kg_per_cm2), "kg/cm<sup>2</sup>"),
            ReportRow(_sym_rho_req(), "-", f"Use R<sub>u,neg</sub> = {format_number(negative.ru_kg_per_cm2)}", format_ratio(negative.rho_required, 6), "-", negative.as_status),
            ReportRow("&rho;<sub>prov,neg</sub>", "&rho;<sub>prov,neg</sub> = A<sub>s</sub> / (bd<sub>neg</sub>)", f"&rho;<sub>prov,neg</sub> = {format_number(negative.as_provided_cm2)} / ({format_number(inputs.geometry.width_cm)} &times; {d_minus_text})", format_ratio(negative.rho_provided, 6), "-", negative.as_status),
            ReportRow(_sym_as_req(), f"{_sym_as_req()} = {_sym_rho_req()}bd<sub>neg</sub>", f"{_sym_as_req()} = {format_ratio(negative.rho_required, 6)} &times; {format_number(inputs.geometry.width_cm)} &times; {d_minus_text}", format_number(negative.as_required_cm2), _unit_cm2()),
            ReportRow(_sym_as_prov(), "-", _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), format_number(negative.as_provided_cm2), _unit_cm2(), negative.as_status),
            ReportRow("A<sub>s,min,neg</sub>", "A<sub>s,min,neg</sub> = &rho;<sub>min</sub>bd<sub>neg</sub>", f"A<sub>s,min,neg</sub> = {format_ratio(negative.rho_min, 6)} &times; {format_number(inputs.geometry.width_cm)} &times; {d_minus_text}", format_number(negative.as_min_cm2), _unit_cm2()),
            ReportRow("A<sub>s,max,neg</sub>", "A<sub>s,max,neg</sub> = &rho;<sub>max</sub>bd<sub>neg</sub>", f"A<sub>s,max,neg</sub> = {format_ratio(negative.rho_max, 6)} &times; {format_number(inputs.geometry.width_cm)} &times; {d_minus_text}", format_number(negative.as_max_cm2), _unit_cm2()),
            ReportRow("a", "-", f"a = {format_number(negative.a_cm)} cm", format_number(negative.a_cm), "cm"),
            ReportRow("c", f"c = a / {_sym_beta1()}", f"c = {format_number(negative.a_cm)} / {format_ratio(results.materials.beta_1, 4)}", format_number(negative.c_cm), "cm"),
            ReportRow("&epsilon;<sub>t,neg</sub>", "&epsilon;<sub>t,neg</sub> = 0.003(d<sub>t</sub> - c) / c", f"&epsilon;<sub>t,neg</sub> = 0.003({format_number(negative.dt_cm)} - {format_number(negative.c_cm)}) / {format_number(negative.c_cm)}", format_ratio(negative.et, 6), "-"),
            ReportRow("M<sub>n,neg</sub>", mn_equation, mn_substitution, format_number(negative.mn_kgm), "kg-m"),
            ReportRow("&phi;M<sub>n,neg</sub>", "&phi;M<sub>n,neg</sub> = &phi; &times; M<sub>n,neg</sub>", f"&phi;M<sub>n,neg</sub> = {format_ratio(negative.phi, 3)} &times; {format_number(negative.mn_kgm)}", format_number(negative.phi_mn_kgm), "kg-m", negative.ratio_status),
            ReportRow("M<sub>u,neg</sub> / &phi;M<sub>n,neg</sub>", "-", f"{format_number(inputs.negative_bending.factored_moment_kgm)} / {format_number(negative.phi_mn_kgm)}", format_ratio(negative.ratio), "-", negative.design_status),
        ],
    )


def _build_full_spacing_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    rows: list[ReportRow] = []
    spacing_groups = [
        ("Positive Compression Reinforcement", results.beam_geometry.positive_compression_spacing),
        ("Positive Tension Reinforcement", results.beam_geometry.positive_tension_spacing),
    ]
    if inputs.has_negative_design and results.beam_geometry.negative_compression_spacing and results.beam_geometry.negative_tension_spacing:
        spacing_groups.extend(
            [
                ("Negative Compression Reinforcement", results.beam_geometry.negative_compression_spacing),
                ("Negative Tension Reinforcement", results.beam_geometry.negative_tension_spacing),
            ]
        )
    for label, spacing in spacing_groups:
        for layer in spacing.layers():
            if not _spacing_layer_has_reinforcement(layer):
                continue
            rows.append(
                ReportRow(
                    f"{label} L{layer.layer_index}",
                    "-",
                    f"Provided clear spacing = {format_number(layer.spacing_cm)}; required clear spacing = {format_number(layer.required_spacing_cm)}",
                    layer.status,
                    "-",
                    layer.status,
                    layer.message,
                )
            )
    return ReportSection(title="Reinforcement Spacing Checks", rows=rows)


def _build_full_deflection_section(results: BeamDesignResults) -> ReportSection:
    deflection = results.deflection
    rows = [
        ReportRow("Selected code", "-", deflection.code_version, deflection.code_version, "-"),
        ReportRow("Member / Support", "-", f"{deflection.member_type} / {deflection.support_condition}", f"{deflection.member_type} / {deflection.support_condition}", "-"),
        ReportRow("Ie method", "-", deflection.ie_method_selected, deflection.ie_method_governing, "-", note=deflection.governing_result),
        ReportRow(
            "Service loads",
            "-",
            f"DL (auto beam self-weight) = {format_number(deflection.service_dead_load_kgf_per_m)}, "
            f"LL = {format_number(deflection.service_live_load_kgf_per_m)}, "
            f"SDL = {format_number(deflection.additional_sustained_load_kgf_per_m)}",
            f"{format_number(deflection.service_sustained_load_kgf_per_m)}",
            "kgf/m",
        ),
        ReportRow("Allowable limit", "Delta_allow = L / limit", deflection.allowable_limit_label, format_number(deflection.allowable_deflection_cm), "cm", note=deflection.limit_clause),
        ReportRow("Ie at midspan", "-", "-", format_number(deflection.ie_midspan_total_cm4), "cm^4", note=deflection.immediate_clause),
        ReportRow("Ie at support", "-", "-", format_number(deflection.ie_support_total_cm4 or 0.0), "cm^4", note=deflection.immediate_clause),
        ReportRow("Averaged Ie", "-", "-", format_number(deflection.ie_average_total_cm4 or 0.0), "cm^4", note=deflection.immediate_clause),
        ReportRow("Deflection Method 1", "Midspan Ie only", "-", format_number(deflection.method_1_total_service_deflection_cm), "cm", note=deflection.immediate_clause),
        ReportRow(
            "Deflection Method 2",
            "Averaged Ie (midspan + support)",
            "-",
            format_number(deflection.method_2_total_service_deflection_cm or 0.0),
            "cm",
            note=deflection.immediate_clause,
        ),
        ReportRow("Immediate total deflection", "-", format_number(deflection.immediate_total_deflection_cm), format_number(deflection.immediate_total_deflection_cm), "cm", note=deflection.immediate_clause),
        ReportRow("Additional long-term deflection", "-", format_number(deflection.additional_long_term_deflection_cm), format_number(deflection.additional_long_term_deflection_cm), "cm", note=deflection.long_term_clause),
        ReportRow("Total service deflection", "-", format_number(deflection.total_service_deflection_cm), format_number(deflection.total_service_deflection_cm), "cm", deflection.status),
        ReportRow("Capacity Ratio (Deflection)", "Delta_calc / Delta_allow", f"{format_number(deflection.total_service_deflection_cm)} / {format_number(deflection.allowable_deflection_cm)}", format_ratio(deflection.capacity_ratio), "-", deflection.status),
    ]
    for index, step in enumerate(deflection.steps, start=1):
        rows.append(
            ReportRow(
                f"Step {index}: {step.variable}",
                step.equation,
                step.substitution,
                step.result,
                step.units,
                step.status,
                step.clause,
            )
        )
    return ReportSection(title="Deflection Check", rows=rows)


def _build_full_warning_section(results: BeamDesignResults) -> ReportSection:
    rows = [
        ReportRow(f"Warning {index}", "-", message, message, "-", "Warning")
        for index, message in enumerate(results.warnings, start=1)
    ]
    if not rows:
        rows = [ReportRow("Warnings", "-", "No direct warnings were triggered in this calculation run.", "No direct warnings were triggered.", "-", "OK")]
    return ReportSection(title="Warnings", rows=rows)


def _build_full_review_flag_section(results: BeamDesignResults) -> ReportSection:
    rows = [
        ReportRow(
            flag.title,
            "-",
            flag.message,
            flag.verification_status.value,
            "-",
            flag.severity.title(),
        )
        for flag in results.review_flags
    ]
    if not rows:
        rows = [ReportRow("Review notes", "-", "No review notes were generated in this calculation run.", "No review notes were generated.", "-", "OK")]
    return ReportSection(title="Review Notes", rows=rows)


def _build_full_summary_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    combined = results.combined_shear_torsion
    warning_summary = "; ".join(results.warnings) if results.warnings else "No direct warnings."
    review_summary = "; ".join(flag.message for flag in results.review_flags) if results.review_flags else "No review notes."
    rows = [
        ReportRow("Overall design status", "-", results.overall_note, results.overall_status, "-", results.overall_note),
        ReportRow(f"Positive flexure, M<sub>u</sub> / {_sym_phi_mn()}", "-", f"M<sub>u</sub> / {_sym_phi_mn()} = {format_ratio(results.positive_bending.ratio)}", results.positive_bending.design_status, "-", results.positive_bending.as_status),
    ]
    if combined.active:
        rows.append(
            ReportRow(
                "Shear & Torsion",
                "-",
                f"Capacity Ratio (Shear + Torsion) = {format_ratio(combined.capacity_ratio)}",
                combined.design_status,
                "-",
                combined.design_status_note or f"\u03d5{combined.stirrup_diameter_mm} mm / {combined.stirrup_legs} legs @ {format_number(combined.stirrup_spacing_cm)} cm",
            )
        )
    else:
        rows.append(
            ReportRow(f"Shear, {_sym_vu()} / {_sym_phi_vn()}", "-", f"{_sym_vu()} / {_sym_phi_vn()} = {format_ratio(results.shear.capacity_ratio)}; s<sub>prov</sub> = {format_number(results.shear.provided_spacing_cm)} cm", results.shear.design_status, "-", f"s<sub>prov</sub> = {format_number(results.shear.provided_spacing_cm)} cm")
        )
    if inputs.torsion.enabled:
        torsion_note = combined.ignore_message if combined.torsion_ignored else results.torsion.pass_fail_summary
        rows.append(ReportRow("Torsion", "-", torsion_note, results.torsion.status, "-", results.torsion.status))
    if inputs.has_negative_design and results.negative_bending is not None:
        rows.append(
            ReportRow("Negative flexure, M<sub>u,neg</sub> / &phi;M<sub>n,neg</sub>", "-", f"M<sub>u,neg</sub> / &phi;M<sub>n,neg</sub> = {format_ratio(results.negative_bending.ratio)}", results.negative_bending.design_status, "-", results.negative_bending.as_status)
        )
    if inputs.consider_deflection:
        rows.append(
            ReportRow(
                "Deflection",
                "-",
                f"Capacity Ratio (Deflection) = {format_ratio(results.deflection.capacity_ratio)} | Delta_allow = {format_number(results.deflection.allowable_deflection_cm)} cm",
                results.deflection.status,
                "-",
                results.deflection.pass_fail_summary,
            )
        )
    rows.extend(
        [
            ReportRow("Warnings", "-", warning_summary, warning_summary, "-", f"{len(results.warnings)} item(s)" if results.warnings else "None"),
            ReportRow("Review notes", "-", review_summary, review_summary, "-", f"{len(results.review_flags)} item(s)" if results.review_flags else "None"),
        ]
    )
    return ReportSection(title="Final Design Summary", rows=rows)


def _build_full_notation_section(inputs: BeamDesignInputSet) -> ReportSection:
    return ReportSection(
        title="Notation",
        rows=[
            ReportRow(_sym_b(), "-", "beam width", "beam width", "cm"),
            ReportRow(_sym_h(), "-", "overall beam depth", "overall beam depth", "cm"),
            ReportRow(_sym_d(), "-", "effective depth to the tension reinforcement", "effective depth to the tension reinforcement", "cm"),
            ReportRow(_sym_d_prime(), "-", "depth to the compression reinforcement centroid", "depth to the compression reinforcement centroid", "cm"),
            ReportRow(_sym_fc(), "-", "specified concrete compressive strength", "specified concrete compressive strength", "ksc"),
            ReportRow(_sym_fy(), "-", "yield strength of longitudinal reinforcement", "yield strength of longitudinal reinforcement", "ksc"),
            ReportRow(_sym_fvy(), "-", "yield strength of stirrup reinforcement", "yield strength of stirrup reinforcement", "ksc"),
            ReportRow(_sym_as_req(), "-", "required area of tension reinforcement", "required area of tension reinforcement", _unit_cm2()),
            ReportRow(_sym_as_prov(), "-", "provided area of tension reinforcement", "provided area of tension reinforcement", _unit_cm2()),
            ReportRow(_sym_mn(), "-", "nominal flexural strength", "nominal flexural strength", "kg-m"),
            ReportRow(_sym_phi_mn(), "-", "design flexural strength", "design flexural strength", "kg-m"),
            ReportRow(_sym_vn(), "-", "nominal shear strength", "nominal shear strength", "kg"),
            ReportRow(_sym_phi_vn(), "-", "design shear strength", "design shear strength", "kg"),
        ],
    )


def _member_summary_text(inputs: BeamDesignInputSet, results: BeamDesignResults) -> str:
    active_options = []
    if inputs.torsion.enabled:
        active_options.append("torsion")
    if inputs.consider_deflection:
        active_options.append("deflection")
    options_text = ", ".join(active_options) if active_options else "strength checks only"
    return (
        f"This note summarizes the design review of a {inputs.beam_type.value.lower()} designed to "
        f"{inputs.metadata.design_code.value}. The member has a section {format_number(inputs.geometry.width_cm)} x "
        f"{format_number(inputs.geometry.depth_cm)} cm with {format_number(inputs.geometry.cover_cm)} cm cover and "
        f"uses f'c = {format_number(inputs.materials.concrete_strength_ksc)} ksc, fy = "
        f"{format_number(inputs.materials.main_steel_yield_ksc)} ksc, and fvy = "
        f"{format_number(inputs.materials.shear_steel_yield_ksc)} ksc. Active report scope: {options_text}."
    )


def _build_torsion_summary_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> NarrativeSection | None:
    if not inputs.torsion.enabled:
        return None
    if results.combined_shear_torsion.torsion_ignored:
        return NarrativeSection(
            title="Torsion",
            body=(
                f"The entered torsion, {format_number(inputs.torsion.factored_torsion_kgfm)} kgf-m, is below the threshold value "
                f"of {format_number(results.torsion.threshold_torsion_kgfm)} kgf-m, so separate torsion reinforcement does not govern this case."
            ),
        )
    body = (
        f"Torsion design is {_acceptability_phrase(results.combined_shear_torsion.design_status)}. "
        f"The design uses Tu = {format_number(inputs.torsion.factored_torsion_kgfm)} kgf-m together with the shared stirrup check, "
        f"for which the governing interaction ratio is {format_ratio(results.combined_shear_torsion.capacity_ratio)}."
    )
    bullets: list[str] = []
    if results.combined_shear_torsion.cross_section_limit_check_applied:
        bullets.append(
            f"Solid-section combined section-limit ratio = {format_ratio(results.combined_shear_torsion.cross_section_limit_ratio)}."
        )
    if results.combined_shear_torsion.design_status_note:
        bullets.append(results.combined_shear_torsion.design_status_note)
    return NarrativeSection(title="Torsion", body=body, bullets=tuple(bullets))


def _build_deflection_summary_narrative(results: BeamDesignResults) -> NarrativeSection | None:
    if results.deflection.status == "Not considered":
        return None
    body = (
        f"Deflection is {_acceptability_phrase(results.deflection.status)}. The calculated service deflection is "
        f"{format_number(results.deflection.total_service_deflection_cm)} cm against an allowable limit of "
        f"{format_number(results.deflection.allowable_deflection_cm)} cm, giving a utilization ratio of "
        f"{format_ratio(results.deflection.capacity_ratio)}."
    )
    bullets: list[str] = []
    if results.deflection.pass_fail_summary:
        bullets.append(results.deflection.pass_fail_summary)
    return NarrativeSection(title="Deflection", body=body, bullets=tuple(bullets))


def _governing_note_lines(results: BeamDesignResults) -> list[str]:
    notes: list[str] = []
    seen: set[str] = set()
    for message in [*results.warnings, *(flag.message for flag in results.review_flags)]:
        cleaned = message.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        notes.append(cleaned)
        if len(notes) == 4:
            break
    return notes


def _summary_conclusion_text(inputs: BeamDesignInputSet, results: BeamDesignResults) -> str:
    if results.overall_status == "PASS":
        return (
            f"On the basis of the active checks summarized above, the member is adequate under {inputs.metadata.design_code.value} "
            "for the stated geometry, materials, and design actions."
        )
    if results.overall_status == "PASS WITH REVIEW":
        return (
            f"The member satisfies the current strength checks under {inputs.metadata.design_code.value}, "
            "but the noted review items should be resolved before issue."
        )
    if results.overall_status == "DOES NOT MEET REQUIREMENTS":
        return (
            f"The reported strength results may be acceptable, but detailing, serviceability, or review items remain unresolved under "
            f"{inputs.metadata.design_code.value}."
        )
    return (
        f"The member does not satisfy the active design requirements under {inputs.metadata.design_code.value} "
        "for the current inputs and assumptions."
    )


def _acceptability_phrase(status: str) -> str:
    if status == "PASS":
        return "satisfactory"
    if status == "PASS WITH REVIEW":
        return "acceptable subject to review"
    if status == "DOES NOT MEET REQUIREMENTS":
        return "not yet acceptable"
    return "not satisfactory"


def _format_arrangement_for_note(arrangement: ReinforcementArrangementInput, fy_ksc: float) -> str:
    return _format_arrangement(arrangement, fy_ksc).replace(" | ", "; ").replace("L", "Layer ")


def _format_arrangement(arrangement: ReinforcementArrangementInput, fy_ksc: float) -> str:
    layer_parts: list[str] = []
    bar_mark = longitudinal_bar_mark(fy_ksc)
    for layer_index, layer in enumerate(arrangement.layers(), start=1):
        group_parts: list[str] = []
        for group in layer.groups():
            if group.diameter_mm is None or group.count == 0:
                continue
            group_parts.append(f"{group.count}{bar_mark}{group.diameter_mm}")
        if group_parts:
            layer_parts.append(f"L{layer_index}: {' + '.join(group_parts)}")
    return " | ".join(layer_parts) if layer_parts else "-"


def _material_substitution(mode: str, default_value: float, manual_value: float | None) -> str:
    if mode == "Manual" and manual_value is not None:
        return f"Manual override = {format_number(manual_value)}"
    return f"Default = {format_number(default_value)}"


def _material_note(mode: str, default_logic: str) -> str:
    if mode == "Manual":
        return "User override"
    return f"Original app logic: {default_logic}"


def _beam_behavior_mode_summary(inputs: BeamDesignInputSet) -> str:
    return (
        f"{inputs.beam_behavior_mode.value} | "
        f"R threshold {format_number(inputs.auto_beam_behavior_threshold_ratio * 100.0)}%"
    )


def _beam_behavior_report_text(results) -> str:
    mode_text = f"Mode {results.beam_behavior_mode}"
    if results.beam_behavior_mode == "Auto":
        classification_text = f"Auto heuristic result {results.auto_result or results.effective_beam_behavior}"
    else:
        classification_text = f"Effective {results.effective_beam_behavior}"
    ratio_text = f"R {format_number(results.behavior_contribution_ratio_r * 100.0)}%"
    threshold_text = f"Threshold {format_number(results.behavior_threshold_r * 100.0)}%"
    method_text = (
        "Method full-section compatibility by bar depth"
        if results.effective_beam_behavior == BeamBehaviorMode.DOUBLY.value
        else "Method singly reinforced block"
    )
    return " | ".join((mode_text, classification_text, method_text, ratio_text, threshold_text))


def _beam_behavior_sentence(results, *, prefix: str = "Beam behavior") -> str:
    method_text = (
        "The reported strength uses the full-section strain-compatibility branch with bar depths measured from the compression face."
        if results.effective_beam_behavior == BeamBehaviorMode.DOUBLY.value
        else "The reported strength uses the singly reinforced rectangular stress-block branch."
    )
    if results.beam_behavior_mode == "Auto":
        return (
            f"{prefix} is set to Auto and the app heuristic classifies this section as "
            f"{results.auto_result or results.effective_beam_behavior}, based on "
            f"R = {format_number(results.behavior_contribution_ratio_r * 100.0)}% "
            f"against a threshold of {format_number(results.behavior_threshold_r * 100.0)}%. "
            f"{method_text}"
        )
    return (
        f"{prefix} is set to {results.beam_behavior_mode}, so the flexural check uses "
        f"{results.effective_beam_behavior} behavior with "
        f"R = {format_number(results.behavior_contribution_ratio_r * 100.0)}%. "
        f"{method_text}"
    )


def _summary_label(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned or cleaned == "-":
        return ""
    replacements = {
        "Capacity ratio <= 1.00 is acceptable in this summary view.": "",
        "Check stirrup spacing, Av, and section size against the required shear branch.": "Review spacing/section",
        "Provided torsion reinforcement does not meet one or more torsion reinforcement requirements.": "Torsion steel NG",
        "Needs manual engineering review": "Review",
        "Verified against code": "Code ok",
        "DOES NOT MEET REQUIREMENTS": "FAIL",
        "DOES NOT MEET DESIGN REQUIREMENTS": "FAIL",
        "PASS WITH REVIEW": "PASS W/ REVIEW",
    }
    shortened = replacements.get(cleaned, cleaned)
    first_sentence = shortened.split(". ")[0].strip()
    if len(first_sentence) <= 28:
        return first_sentence
    return first_sentence[:25].rstrip() + "..."


def _spacing_layer_has_reinforcement(layer) -> bool:
    return (
        (layer.group_a_diameter_mm is not None and layer.group_a_count > 0)
        or (layer.group_b_diameter_mm is not None and layer.group_b_count > 0)
    )


def _build_print_torsion_section(results: BeamDesignResults) -> ReportSection:
    torsion = results.torsion
    combined = results.combined_shear_torsion
    if combined.torsion_ignored:
        return ReportSection(
            title="Torsion Design",
            rows=[
                ReportRow("Tu", "-", format_number(torsion.tu_kgfm), format_number(torsion.tu_kgfm), "kgf-m"),
                ReportRow("Threshold", "-", format_number(torsion.threshold_torsion_kgfm), format_number(torsion.threshold_torsion_kgfm), "kgf-m"),
                ReportRow("Summary", "-", combined.ignore_message, "Ignore Tu", "-", "PASS"),
            ],
        )
    return ReportSection(
        title="Torsion Design",
        rows=[
            ReportRow("Code", "-", torsion.code_version, torsion.code_version, "-"),
            ReportRow("Tu", "-", format_number(torsion.tu_kgfm), format_number(torsion.tu_kgfm), "kgf-m"),
            ReportRow("Threshold", "-", format_number(torsion.threshold_torsion_kgfm), format_number(torsion.threshold_torsion_kgfm), "kgf-m"),
            ReportRow("Capacity Ratio (Shear + Torsion)", "-", combined.summary_note, format_ratio(combined.capacity_ratio), "-", combined.design_status if combined.active else torsion.status),
            ReportRow("At/s req.", "-", f"{torsion.transverse_reinf_required_mm2_per_mm:.6f}", f"{torsion.transverse_reinf_required_mm2_per_mm:.6f}", "mm2/mm"),
            ReportRow("Al req.", "-", format_number(mm2_to_cm2(torsion.longitudinal_reinf_required_mm2)), format_number(mm2_to_cm2(torsion.longitudinal_reinf_required_mm2)), "cm2"),
            ReportRow("Status", "-", torsion.pass_fail_summary, torsion.status, "-", torsion.status),
        ],
    )


def _build_deflection_section(results: BeamDesignResults) -> ReportSection:
    deflection = results.deflection
    return ReportSection(
        title="Deflection Check",
        rows=[
            ReportRow("Code", "-", deflection.code_version, deflection.code_version, "-"),
            ReportRow("Member / Support", "-", f"{deflection.member_type} / {deflection.support_condition}", f"{deflection.member_type} / {deflection.support_condition}", "-"),
            ReportRow("Ie method", "-", deflection.ie_method_selected, deflection.ie_method_governing, "-"),
            ReportRow("Allowable", "-", deflection.allowable_limit_label, format_number(deflection.allowable_deflection_cm), "cm"),
            ReportRow("Method 1", "Midspan Ie only", "-", format_number(deflection.method_1_total_service_deflection_cm), "cm"),
            ReportRow("Method 2", "Averaged Ie", "-", format_number(deflection.method_2_total_service_deflection_cm or 0.0), "cm"),
            ReportRow("Immediate total", "-", format_number(deflection.immediate_total_deflection_cm), format_number(deflection.immediate_total_deflection_cm), "cm"),
            ReportRow("Long-term additional", "-", format_number(deflection.additional_long_term_deflection_cm), format_number(deflection.additional_long_term_deflection_cm), "cm"),
            ReportRow("Total service", "-", format_number(deflection.total_service_deflection_cm), format_number(deflection.total_service_deflection_cm), "cm"),
            ReportRow("Capacity Ratio (Deflection)", "-", format_ratio(deflection.capacity_ratio), format_ratio(deflection.capacity_ratio), "-", deflection.status),
        ],
    )


def _build_print_deflection_section(results: BeamDesignResults) -> ReportSection:
    deflection = results.deflection
    return ReportSection(
        title="Deflection Check",
        rows=[
            ReportRow("Code", "-", deflection.code_version, deflection.code_version, "-"),
            ReportRow("Ie method", "-", deflection.ie_method_selected, deflection.ie_method_governing, "-"),
            ReportRow("Allowable limit", "-", f"{deflection.allowable_limit_label} = {format_number(deflection.allowable_deflection_cm)} cm", format_number(deflection.allowable_deflection_cm), "cm"),
            ReportRow("Method 1", "Midspan Ie only", "-", format_number(deflection.method_1_total_service_deflection_cm), "cm"),
            ReportRow("Method 2", "Averaged Ie", "-", format_number(deflection.method_2_total_service_deflection_cm or 0.0), "cm"),
            ReportRow("Immediate total", "-", format_number(deflection.immediate_total_deflection_cm), format_number(deflection.immediate_total_deflection_cm), "cm"),
            ReportRow("Long-term additional", "-", format_number(deflection.additional_long_term_deflection_cm), format_number(deflection.additional_long_term_deflection_cm), "cm"),
            ReportRow("Total service deflection", "-", format_number(deflection.total_service_deflection_cm), format_number(deflection.total_service_deflection_cm), "cm"),
            ReportRow("Capacity Ratio (Deflection)", "-", format_ratio(deflection.capacity_ratio), format_ratio(deflection.capacity_ratio), "-", deflection.status, deflection.pass_fail_summary),
        ],
    )


def _print_flexural_summary_note(review_note: str) -> str:
    if review_note:
        return review_note
    return "Capacity ratio <= 1.00 is acceptable in this summary view."


def _print_shear_summary_note(results: BeamDesignResults) -> str:
    shear = results.shear
    if shear.section_change_note:
        return shear.section_change_note
    if shear.review_note:
        return shear.review_note
    if shear.design_status != "PASS":
        return "Check stirrup spacing, Av, and section size against the required shear branch."
    return f"Based on {_shear_basis_text(results)} with d = {_shear_effective_depth_text(results)} cm."


def _sym_b() -> str:
    return "b"


def _sym_h() -> str:
    return "h"


def _sym_d() -> str:
    return "d"


def _sym_d_prime() -> str:
    return "d&#8242;"


def _sym_d_neg() -> str:
    return "d<sub>neg</sub>"


def _sym_fc() -> str:
    return "f&#8242;<sub>c</sub>"


def _sym_fy() -> str:
    return "f<sub>y</sub>"


def _sym_fvy() -> str:
    return "f<sub>vy</sub>"


def _sym_ec() -> str:
    return "E<sub>c</sub>"


def _sym_es() -> str:
    return "E<sub>s</sub>"


def _sym_fr() -> str:
    return "f<sub>r</sub>"


def _sym_beta1() -> str:
    return "&beta;<sub>1</sub>"


def _sym_rho_req() -> str:
    return "&rho;<sub>req</sub>"


def _sym_as() -> str:
    return "A<sub>s</sub>"


def _sym_as_req() -> str:
    return "A<sub>s,req</sub>"


def _sym_as_prov() -> str:
    return "A<sub>s,prov</sub>"


def _sym_mn() -> str:
    return "M<sub>n</sub>"


def _sym_phi_mn() -> str:
    return "&phi;M<sub>n</sub>"


def _sym_vu() -> str:
    return "V<sub>u</sub>"


def _sym_vc() -> str:
    return "V<sub>c</sub>"


def _sym_phi_vc() -> str:
    return "&phi;V<sub>c</sub>"


def _sym_av() -> str:
    return "A<sub>v</sub>"


def _sym_vs() -> str:
    return "V<sub>s</sub>"


def _sym_phi_vs() -> str:
    return "&phi;V<sub>s</sub>"


def _sym_vn() -> str:
    return "V<sub>n</sub>"


def _sym_phi_vn() -> str:
    return "&phi;V<sub>n</sub>"


def _unit_cm2() -> str:
    return "cm<sup>2</sup>"


def _format_default_ec_logic() -> str:
    return f"{_sym_ec()} = 15100&radic;{_sym_fc()}"


def _format_default_fr_logic() -> str:
    return f"{_sym_fr()} = 2&radic;{_sym_fc()}"


def _format_default_es_logic() -> str:
    return f"{_sym_es()} = 2.04 &times; 10<sup>6</sup>"


def _active_flexural_report_specs(inputs: BeamDesignInputSet, results: BeamDesignResults) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    if inputs.has_positive_design:
        specs.append(
            {
                "key": "middle" if inputs.beam_type == BeamType.SIMPLE else "positive",
                "label": "Middle" if inputs.beam_type == BeamType.SIMPLE else "Positive",
                "title": "Middle Moment Design" if inputs.beam_type == BeamType.SIMPLE else "Positive Moment Design",
                "moment": inputs.positive_bending.factored_moment_kgm,
                "input": inputs.positive_bending,
                "result": results.positive_bending,
            }
        )
    if inputs.has_simple_support_design and results.support_bending is not None:
        specs.append(
            {
                "key": "support",
                "label": "Support",
                "title": "Support Moment Design",
                "moment": inputs.resolved_simple_support_moment_kgm,
                "input": inputs.simple_support_bending,
                "result": results.support_bending,
            }
        )
    if inputs.has_support_negative_design and results.negative_bending is not None:
        specs.append(
            {
                "key": "negative",
                "label": "Negative",
                "title": "Negative Moment Design",
                "moment": inputs.negative_bending.factored_moment_kgm,
                "input": inputs.negative_bending,
                "result": results.negative_bending,
            }
        )
    if inputs.has_cantilever_negative_design and results.cantilever_negative_bending is not None:
        specs.append(
            {
                "key": "cantilever_negative",
                "label": "Cantilever Negative",
                "title": "Cantilever Negative Moment Design",
                "moment": inputs.cantilever_negative_bending.factored_moment_kgm,
                "input": inputs.cantilever_negative_bending,
                "result": results.cantilever_negative_bending,
            }
        )
    return specs


def _build_cantilever_negative_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    cantilever = results.cantilever_negative_bending
    if cantilever is None:
        raise ValueError("Cantilever negative report section requested without cantilever results.")
    d_minus_text = _negative_section_effective_depth_text(inputs, inputs.cantilever_negative_bending)
    mn_equation, mn_substitution = _moment_capacity_row_content(
        cantilever,
        default_equation="As * fy * (d- - a/2) / 100",
        default_substitution=(
            f"{format_number(cantilever.as_provided_cm2)} * {format_number(inputs.materials.main_steel_yield_ksc)} "
            f"* ({d_minus_text} - {format_number(cantilever.a_cm)}/2) / 100"
        ),
    )
    return ReportSection(
        title="Cantilever Negative Moment Design",
        rows=[
            ReportRow("Tension Reinforcement", "Top bars", _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Top bars"),
            ReportRow("Compression Reinforcement", "Bottom bars", _format_arrangement(inputs.cantilever_negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.cantilever_negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Bottom bars"),
            ReportRow("phi", "Current / ACI-style phi logic", f"et = {cantilever.et:.6f}", format_ratio(cantilever.phi), "-", cantilever.ratio_status),
            ReportRow("Ru", "Mu * 100 / (phi * b * d^2)", f"{format_number(inputs.cantilever_negative_bending.factored_moment_kgm)} * 100 / ({format_ratio(cantilever.phi, 3)} * {format_number(inputs.geometry.width_cm)} * {d_minus_text}^2)", format_number(cantilever.ru_kg_per_cm2), "kg/cm2"),
            ReportRow("rho required", "Current flexural demand equation", f"Ru = {format_number(cantilever.ru_kg_per_cm2)}", format_ratio(cantilever.rho_required, 6), "-"),
            ReportRow("rho provided", "As / (b*d-)", f"{format_number(cantilever.as_provided_cm2)} / ({format_number(inputs.geometry.width_cm)} * {d_minus_text})", format_ratio(cantilever.rho_provided, 6), "-", cantilever.as_status),
            ReportRow("As required", "rho_req * b * d-", f"{cantilever.rho_required:.6f} * {inputs.geometry.width_cm:.2f} * {d_minus_text}", format_number(cantilever.as_required_cm2), "cm2"),
            ReportRow("As provided", "sum(bar areas)", _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), format_number(cantilever.as_provided_cm2), "cm2", cantilever.as_status),
            ReportRow("As min", "rho_min * b * d-", f"{cantilever.rho_min:.6f} * {inputs.geometry.width_cm:.2f} * {d_minus_text}", format_number(cantilever.as_min_cm2), "cm2"),
            ReportRow("As max", "rho_max * b * d-", f"{cantilever.rho_max:.6f} * {inputs.geometry.width_cm:.2f} * {d_minus_text}", format_number(cantilever.as_max_cm2), "cm2"),
            ReportRow("a", "As * fy / (0.85 * fc' * b)", "Cantilever negative bending", format_number(cantilever.a_cm), "cm"),
            ReportRow("c", "a / beta1", "Cantilever negative bending", format_number(cantilever.c_cm), "cm"),
            ReportRow("et", "ecu * (dt - c) / c", f"0.003 * ({format_number(cantilever.dt_cm)} - {format_number(cantilever.c_cm)}) / {format_number(cantilever.c_cm)}", format_ratio(cantilever.et, 6), "-"),
            ReportRow("Mn", mn_equation, mn_substitution, format_number(cantilever.mn_kgm), "kg-m"),
            ReportRow("phiMn", "phi * Mn", f"{cantilever.phi:.3f} * {cantilever.mn_kgm:.2f}", format_number(cantilever.phi_mn_kgm), "kg-m", cantilever.ratio_status),
        ],
    )


def _build_full_cantilever_negative_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    cantilever = results.cantilever_negative_bending
    if cantilever is None:
        raise ValueError("Cantilever negative full report section requested without cantilever results.")
    d_minus_text = _negative_section_effective_depth_text(inputs, inputs.cantilever_negative_bending)
    mn_equation, mn_substitution = _moment_capacity_row_content(
        cantilever,
        default_equation="M<sub>n,cant</sub> = A<sub>s</sub>f<sub>y</sub>(d<sub>cant</sub> - a/2) / 100",
        default_substitution=(
            f"M<sub>n,cant</sub> = {format_number(cantilever.as_provided_cm2)} &times; {format_number(inputs.materials.main_steel_yield_ksc)} "
            f"&times; ({d_minus_text} - {format_number(cantilever.a_cm)}/2) / 100"
        ),
    )
    return ReportSection(
        title="Cantilever Negative Moment Design",
        rows=[
            ReportRow("Tension reinforcement", "-", _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
            ReportRow("Compression reinforcement", "-", _format_arrangement(inputs.cantilever_negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.cantilever_negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
            ReportRow("M<sub>u,cant</sub>", "-", f"M<sub>u,cant</sub> = {format_number(inputs.cantilever_negative_bending.factored_moment_kgm)} kg-m", format_number(inputs.cantilever_negative_bending.factored_moment_kgm), "kg-m"),
            ReportRow("&phi;", "-", f"From tensile strain, &epsilon;<sub>t</sub> = {format_ratio(cantilever.et, 6)}", format_ratio(cantilever.phi), "-", cantilever.ratio_status),
            ReportRow("R<sub>u,cant</sub>", "R<sub>u,cant</sub> = M<sub>u,cant</sub> &times; 100 / (&phi;bd<sub>cant</sub><sup>2</sup>)", f"R<sub>u,cant</sub> = {format_number(inputs.cantilever_negative_bending.factored_moment_kgm)} &times; 100 / ({format_ratio(cantilever.phi, 3)} &times; {format_number(inputs.geometry.width_cm)} &times; {d_minus_text}<sup>2</sup>)", format_number(cantilever.ru_kg_per_cm2), "kg/cm<sup>2</sup>"),
            ReportRow(_sym_as_req(), f"{_sym_as_req()} = {_sym_rho_req()}bd<sub>cant</sub>", f"{_sym_as_req()} = {format_ratio(cantilever.rho_required, 6)} &times; {format_number(inputs.geometry.width_cm)} &times; {d_minus_text}", format_number(cantilever.as_required_cm2), _unit_cm2()),
            ReportRow(_sym_as_prov(), "-", _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), format_number(cantilever.as_provided_cm2), _unit_cm2(), cantilever.as_status),
            ReportRow("&epsilon;<sub>t,cant</sub>", "&epsilon;<sub>t,cant</sub> = 0.003(d<sub>t</sub> - c) / c", f"&epsilon;<sub>t,cant</sub> = 0.003({format_number(cantilever.dt_cm)} - {format_number(cantilever.c_cm)}) / {format_number(cantilever.c_cm)}", format_ratio(cantilever.et, 6), "-"),
            ReportRow("M<sub>n,cant</sub>", mn_equation, mn_substitution, format_number(cantilever.mn_kgm), "kg-m"),
            ReportRow("&phi;M<sub>n,cant</sub>", "&phi;M<sub>n,cant</sub> = &phi; &times; M<sub>n,cant</sub>", f"&phi;M<sub>n,cant</sub> = {format_ratio(cantilever.phi, 3)} &times; {format_number(cantilever.mn_kgm)}", format_number(cantilever.phi_mn_kgm), "kg-m", cantilever.ratio_status),
            ReportRow("M<sub>u,cant</sub> / &phi;M<sub>n,cant</sub>", "-", f"{format_number(inputs.cantilever_negative_bending.factored_moment_kgm)} / {format_number(cantilever.phi_mn_kgm)}", format_ratio(cantilever.ratio), "-", cantilever.design_status),
        ],
    )


def build_report_sections(inputs: BeamDesignInputSet, results: BeamDesignResults) -> list[ReportSection]:
    sections = [_build_input_summary(inputs), _build_material_section(inputs, results), _build_geometry_section(inputs, results)]
    if inputs.has_positive_design:
        sections.append(_with_updated_moment_summary_row(_build_positive_section(inputs, results), results.positive_bending))
    if inputs.has_support_negative_design and results.negative_bending is not None:
        sections.append(_with_updated_moment_summary_row(_build_negative_section(inputs, results), results.negative_bending))
    if inputs.has_cantilever_negative_design and results.cantilever_negative_bending is not None:
        sections.append(_with_updated_moment_summary_row(_build_cantilever_negative_section(inputs, results), results.cantilever_negative_bending))
    sections.append(_build_shear_section(inputs, results))
    if inputs.torsion.enabled:
        sections.append(_build_torsion_section(inputs, results))
    if inputs.consider_deflection:
        sections.append(_build_deflection_section(results))
    sections.append(_build_summary_section(inputs, results))
    return sections


def build_summary_table_sections(inputs: BeamDesignInputSet, results: BeamDesignResults) -> list[ReportSection]:
    rows = [
        ReportRow("Beam Type", "-", inputs.beam_type.value, inputs.beam_type.value, "-"),
        ReportRow("Beam Behavior", "-", inputs.beam_behavior_mode.value, inputs.beam_behavior_mode.value, "-"),
    ]
    cantilever_value = _cantilever_span_summary(inputs)
    if cantilever_value is not None:
        rows.append(ReportRow("Include Cantilever Span", "-", cantilever_value, cantilever_value, "-"))
    rows.extend(
        [
            ReportRow("Sections", "-", _active_section_names(inputs), _active_section_names(inputs), "-"),
            ReportRow("Code", "-", inputs.metadata.design_code.value, inputs.metadata.design_code.value, "-"),
            ReportRow("Section", "-", f"{format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)} cm, c={format_number(inputs.geometry.cover_cm)} cm", f"{format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)}", "cm"),
            ReportRow("Vu", "-", format_number(inputs.shear.factored_shear_kg), format_number(inputs.shear.factored_shear_kg), "kgf"),
        ]
    )
    for spec in _active_flexural_report_specs(inputs, results):
        moment_label = "Mu(+)" if spec["key"] == "positive" else ("Mu(-)" if spec["key"] == "negative" else "Mu(cant-)")
        rows.append(ReportRow(moment_label, "-", format_number(spec["moment"]), format_number(spec["moment"]), "kgf-m"))
    sections = [
        ReportSection(title="Member Summary", rows=rows),
        _build_summary_table_flexure_section(inputs, results),
        _build_summary_table_shear_section(inputs, results),
        _build_summary_reinforcement_section(inputs, results),
        _build_print_design_summary(inputs, results),
    ]
    if inputs.torsion.enabled:
        sections[0].rows.append(ReportRow("Tu", "-", format_number(inputs.torsion.factored_torsion_kgfm), format_number(inputs.torsion.factored_torsion_kgfm), "kgf-m"))
        sections.insert(3, _build_summary_table_torsion_section(results))
    if inputs.consider_deflection and results.deflection.status != "Not considered":
        sections.insert(-2, _build_summary_table_deflection_section(results))
    return sections


def build_full_report_sections(inputs: BeamDesignInputSet, results: BeamDesignResults) -> list[ReportSection]:
    sections = [_build_full_input_summary(inputs), _build_full_material_section(inputs, results), _build_full_geometry_section(inputs, results)]
    if inputs.has_simple_support_design and results.support_bending is not None:
        sections.append(_build_full_support_section(inputs, results))
    if inputs.has_positive_design:
        sections.append(_build_full_positive_section(inputs, results))
    sections.extend([_build_full_spacing_section(inputs, results), _build_full_shear_section(inputs, results)])
    if inputs.torsion.enabled:
        sections.append(_build_full_torsion_section(results))
    if inputs.consider_deflection:
        sections.append(_build_full_deflection_section(results))
    if inputs.has_support_negative_design and results.negative_bending is not None:
        sections.append(_build_full_negative_section(inputs, results))
    if inputs.has_cantilever_negative_design and results.cantilever_negative_bending is not None:
        sections.append(_build_full_cantilever_negative_section(inputs, results))
    if results.warnings:
        sections.append(_build_full_warning_section(results))
    if results.review_flags:
        sections.append(_build_full_review_flag_section(results))
    return sections


def _build_summary_table_flexure_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    rows: list[ReportRow] = []
    for spec in _active_flexural_report_specs(inputs, results):
        result = spec["result"]
        label = spec["label"]
        rows.append(
            ReportRow(
                f"{label} Flexure",
                "-",
                f"M<sub>u</sub> {format_number(spec['moment'])} | &phi;M<sub>n</sub> {format_number(result.phi_mn_kgm)} | {_beam_behavior_report_text(result)}",
                format_ratio(result.ratio),
                "-",
                result.design_status,
                _summary_label(result.as_status),
            )
        )
        rows.append(
            ReportRow(
                f"{label} Behavior",
                "-",
                _beam_behavior_report_text(result),
                result.effective_beam_behavior,
                "-",
                result.design_status,
            )
        )
    rows.append(
        ReportRow(
            "Primary d",
            "-",
            f"{_primary_section_label(inputs)} section effective depth",
            format_number(results.beam_geometry.d_plus_cm),
            "cm",
        )
    )
    if inputs.has_support_negative_design and results.beam_geometry.d_minus_cm is not None:
        rows.append(ReportRow("d-", "-", "Support negative section effective depth", format_number(results.beam_geometry.d_minus_cm), "cm"))
    return ReportSection(title="Flexure", rows=rows)


def _build_summary_reinforcement_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    rows: list[ReportRow] = []
    if inputs.has_positive_design:
        rows.extend(
            [
                ReportRow("Positive Bottom Steel", "-", _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
                ReportRow("Positive Top Steel", "-", _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
            ]
        )
    if inputs.has_support_negative_design and results.negative_bending is not None:
        rows.append(ReportRow("Negative Top Steel", "-", _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"))
    if inputs.has_cantilever_negative_design and results.cantilever_negative_bending is not None:
        rows.append(ReportRow("Cantilever Top Steel", "-", _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"))
    rows.append(
        ReportRow(
            "Stirrups",
            "-",
            f"{stirrup_bar_mark(inputs.materials.shear_steel_yield_ksc)}{inputs.shear.stirrup_diameter_mm}, {inputs.shear.legs_per_plane}-leg @ {format_number(results.combined_shear_torsion.stirrup_spacing_cm if results.combined_shear_torsion.active else results.shear.provided_spacing_cm)} cm",
            f"{format_number(results.combined_shear_torsion.stirrup_spacing_cm if results.combined_shear_torsion.active else results.shear.provided_spacing_cm)}",
            "cm",
        )
    )
    if inputs.torsion.enabled and not results.combined_shear_torsion.torsion_ignored and inputs.torsion.provided_longitudinal_bar_diameter_mm is not None:
        rows.append(ReportRow("Torsion Long. Steel", "-", f"{inputs.torsion.provided_longitudinal_bar_count}-{longitudinal_bar_mark(inputs.torsion.provided_longitudinal_bar_fy_ksc)}{inputs.torsion.provided_longitudinal_bar_diameter_mm}", f"{inputs.torsion.provided_longitudinal_bar_count}-{longitudinal_bar_mark(inputs.torsion.provided_longitudinal_bar_fy_ksc)}{inputs.torsion.provided_longitudinal_bar_diameter_mm}", "-"))
    return ReportSection(title="Reinforcement Summary", rows=rows)


def _member_fact_lines(inputs: BeamDesignInputSet) -> list[str]:
    facts = [
        f"Beam type: {inputs.beam_type.value}",
        f"Code: {inputs.metadata.design_code.value}",
        f"Section: {format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)} cm, cover {format_number(inputs.geometry.cover_cm)} cm",
        f"Materials: f'c {format_number(inputs.materials.concrete_strength_ksc)} ksc, fy {format_number(inputs.materials.main_steel_yield_ksc)} ksc, fvy {format_number(inputs.materials.shear_steel_yield_ksc)} ksc",
        f"Active sections: {_active_section_names(inputs)}",
    ]
    cantilever_value = _cantilever_span_summary(inputs)
    if cantilever_value is not None:
        facts.append(f"Include cantilever span: {cantilever_value}")
    if inputs.torsion.enabled:
        facts.append(f"Torsion demand type: {inputs.torsion.demand_type.value}")
    if inputs.consider_deflection:
        facts.append(f"Deflection check: {inputs.deflection.member_type.value}, {inputs.deflection.support_condition.value}")
    return facts


def _design_actions_text(inputs: BeamDesignInputSet, results: BeamDesignResults) -> str:
    action_parts = [f"The governing factored shear is {format_number(inputs.shear.factored_shear_kg)} kgf."]
    for spec in _active_flexural_report_specs(inputs, results):
        action_parts.insert(
            len(action_parts) - 0,
            f"The {str(spec['label']).lower()} section is checked for Mu = {format_number(spec['moment'])} kgf-m."
        )
    action_parts.append(
        f"Shear strength is based on the {_shear_basis_text(results)} with d = {_shear_effective_depth_text(results)} cm."
    )
    if inputs.torsion.enabled:
        if results.combined_shear_torsion.torsion_ignored:
            action_parts.append(f"The entered torsion, {format_number(inputs.torsion.factored_torsion_kgfm)} kgf-m, falls below the code threshold and is not required to govern reinforcement design.")
        else:
            action_parts.append(f"Torsion has been considered using Tu = {format_number(inputs.torsion.factored_torsion_kgfm)} kgf-m.")
    if inputs.consider_deflection:
        action_parts.append(f"Serviceability is checked against an allowable deflection of {format_number(results.deflection.allowable_deflection_cm)} cm.")
    return " ".join(action_parts)


def _build_flexure_summary_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> NarrativeSection:
    specs = _active_flexural_report_specs(inputs, results)
    first = specs[0]
    first_result = first["result"]
    first_label = "support" if first["key"] == "negative" else str(first["label"]).lower()
    body = (
        f"At the {first_label} section, the factored moment is {format_number(first['moment'])} kgf-m "
        f"and the available design flexural strength is {format_number(first_result.phi_mn_kgm)} kgf-m, "
        f"giving a utilization ratio of {format_ratio(first_result.ratio)}. "
        f"{str(first['label'])} flexural design is {_acceptability_phrase(first_result.design_status)}. "
        f"{_beam_behavior_sentence(first_result)}"
    )
    bullets: list[str] = []
    for spec in specs[1:]:
        result = spec["result"]
        section_prefix = "Support section" if spec["key"] == "negative" else f"{spec['label']} section"
        bullets.append(
            f"{section_prefix}: Mu = {format_number(spec['moment'])} kgf-m, phiMn = {format_number(result.phi_mn_kgm)} kgf-m, ratio = {format_ratio(result.ratio)}."
        )
        bullets.append(_beam_behavior_sentence(result, prefix=section_prefix))
    return NarrativeSection(title="Flexure", body=body, bullets=tuple(bullets))


def _build_shear_summary_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> NarrativeSection:
    stirrup_spacing_cm = (
        results.combined_shear_torsion.stirrup_spacing_cm
        if results.combined_shear_torsion.active
        else results.shear.provided_spacing_cm
    )
    body = (
        f"Shear design is {_acceptability_phrase(results.shear.design_status)}. The factored shear is "
        f"{format_number(inputs.shear.factored_shear_kg)} kgf, compared with a design shear strength of "
        f"{format_number(results.shear.phi_vn_kg)} kgf, giving a utilization ratio of {format_ratio(results.shear.capacity_ratio)}. "
        f"The shear check uses the {_shear_basis_text(results)} with d = {_shear_effective_depth_text(results)} cm. "
        f"The provided closed stirrups are {stirrup_bar_mark(inputs.materials.shear_steel_yield_ksc)}{inputs.shear.stirrup_diameter_mm} "
        f"with {inputs.shear.legs_per_plane} legs at {format_number(stirrup_spacing_cm)} cm."
    )
    bullets: list[str] = []
    if results.shear.section_change_note:
        bullets.append(results.shear.section_change_note)
    if results.shear.review_note:
        bullets.append(results.shear.review_note)
    return NarrativeSection(title="Shear", body=body, bullets=tuple(bullets))


def _reinforcement_summary_lines(inputs: BeamDesignInputSet, results: BeamDesignResults) -> list[str]:
    lines: list[str] = []
    if inputs.has_positive_design:
        lines.append(f"Provide bottom flexural reinforcement at the positive section as {_format_arrangement_for_note(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc)}.")
    if inputs.has_support_negative_design and results.negative_bending is not None:
        lines.append(f"Provide top flexural reinforcement at the negative section as {_format_arrangement_for_note(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc)}.")
    if inputs.has_cantilever_negative_design and results.cantilever_negative_bending is not None:
        lines.append(f"Provide top flexural reinforcement at the cantilever negative section as {_format_arrangement_for_note(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc)}.")
    stirrup_spacing_cm = results.combined_shear_torsion.stirrup_spacing_cm if results.combined_shear_torsion.active else results.shear.provided_spacing_cm
    lines.append(f"Provide closed {stirrup_bar_mark(inputs.materials.shear_steel_yield_ksc)}{inputs.shear.stirrup_diameter_mm} stirrups with {inputs.shear.legs_per_plane} legs at {format_number(stirrup_spacing_cm)} cm.")
    if inputs.torsion.enabled and not results.combined_shear_torsion.torsion_ignored and inputs.torsion.provided_longitudinal_bar_diameter_mm is not None:
        lines.append(f"Provide torsion longitudinal steel as {inputs.torsion.provided_longitudinal_bar_count}-{longitudinal_bar_mark(inputs.torsion.provided_longitudinal_bar_fy_ksc)}{inputs.torsion.provided_longitudinal_bar_diameter_mm}.")
    return lines


def _print_input_mu_value(inputs: BeamDesignInputSet) -> str:
    parts: list[str] = []
    if inputs.has_simple_support_design:
        support_prefix = "(support auto)" if inputs.simple_support_bending.moment_mode.value == "Auto" else "(support)"
        parts.append(f"{support_prefix} {format_number(inputs.resolved_simple_support_moment_kgm)}")
    if inputs.has_positive_design:
        positive_prefix = "(middle)" if inputs.beam_type == BeamType.SIMPLE else "(+)"
        parts.append(f"{positive_prefix} {format_number(inputs.positive_bending.factored_moment_kgm)}")
    if inputs.has_support_negative_design:
        parts.append(f"(-) {format_number(inputs.negative_bending.factored_moment_kgm)}")
    if inputs.has_cantilever_negative_design:
        parts.append(f"(cant-) {format_number(inputs.cantilever_negative_bending.factored_moment_kgm)}")
    return " | ".join(parts)


def _build_print_design_summary(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    combined = results.combined_shear_torsion
    rows = [ReportRow("Overall Status", "-", f"W {len(results.warnings)} | R {len(results.review_flags)}", results.overall_status, "-", note=_summary_label(results.overall_note))]
    for spec in _active_flexural_report_specs(inputs, results):
        result = spec["result"]
        rows.append(
            ReportRow(
                f"{spec['label']} Flexure",
                "-",
                f"ratio {format_ratio(result.ratio)}",
                result.design_status,
                "-",
                status=_summary_label(result.as_status),
                note=_summary_label(_beam_behavior_report_text(result)),
            )
        )
    if combined.active:
        rows.append(ReportRow("Shear & Torsion", "-", f"ratio {format_ratio(combined.capacity_ratio)}", combined.design_status, "-", status=f"{stirrup_bar_mark(inputs.materials.shear_steel_yield_ksc)}{combined.stirrup_diameter_mm} @ {format_number(combined.stirrup_spacing_cm)} cm", note=_summary_label(combined.design_status_note or combined.summary_note)))
    else:
        rows.append(ReportRow("Shear", "-", f"ratio {format_ratio(results.shear.capacity_ratio)}", results.shear.design_status, "-", status=f"{stirrup_bar_mark(inputs.materials.shear_steel_yield_ksc)}{inputs.shear.stirrup_diameter_mm} @ {format_number(results.shear.provided_spacing_cm)} cm", note=_summary_label(_print_shear_summary_note(results))))
    rows.append(ReportRow("Shear Basis", "-", _shear_basis_text(results), _shear_effective_depth_text(results), "cm"))
    if inputs.consider_deflection:
        rows.append(ReportRow("Deflection", "-", f"ratio {format_ratio(results.deflection.capacity_ratio)}", results.deflection.status, "-", status=f"allow {format_number(results.deflection.allowable_deflection_cm)} cm", note=_summary_label(results.deflection.pass_fail_summary or results.deflection.note)))
    return ReportSection(title="Design Summary", rows=rows)


def _build_input_summary(inputs: BeamDesignInputSet) -> ReportSection:
    rows = [
        ReportRow("Design code", "-", inputs.metadata.design_code.value, inputs.metadata.design_code.value, "-"),
        ReportRow("Beam Type", "-", inputs.beam_type.value, inputs.beam_type.value, "-"),
        ReportRow("Sections", "-", _active_section_names(inputs), _active_section_names(inputs), "-"),
        ReportRow("Mu Mapping", "-", _mu_mapping_text(inputs), _mu_mapping_text(inputs), "-"),
        ReportRow("Vu Mapping", "-", _vu_mapping_text(inputs), _vu_mapping_text(inputs), "-"),
        ReportRow("fc'", "-", format_number(inputs.materials.concrete_strength_ksc), format_number(inputs.materials.concrete_strength_ksc), "ksc"),
        ReportRow("fy", "-", format_number(inputs.materials.main_steel_yield_ksc), format_number(inputs.materials.main_steel_yield_ksc), "ksc"),
        ReportRow("b", "-", format_number(inputs.geometry.width_cm), format_number(inputs.geometry.width_cm), "cm"),
        ReportRow("h", "-", format_number(inputs.geometry.depth_cm), format_number(inputs.geometry.depth_cm), "cm"),
    ]
    cantilever_value = _cantilever_span_summary(inputs)
    if cantilever_value is not None:
        rows.insert(2, ReportRow("Include Cantilever Span", "-", cantilever_value, cantilever_value, "-"))
    return ReportSection(title="Input Summary", rows=rows)


def _build_full_input_summary(inputs: BeamDesignInputSet) -> ReportSection:
    rows = [
        ReportRow("Design code", "-", inputs.metadata.design_code.value, inputs.metadata.design_code.value, "-"),
        ReportRow("Beam type", "-", inputs.beam_type.value, inputs.beam_type.value, "-"),
        ReportRow("Active sections", "-", _active_section_names(inputs), _active_section_names(inputs), "-"),
        ReportRow("Mu mapping", "-", _mu_mapping_text(inputs), _mu_mapping_text(inputs), "-"),
        ReportRow("Vu mapping", "-", _vu_mapping_text(inputs), _vu_mapping_text(inputs), "-"),
        ReportRow(_sym_fc(), "-", f"{_sym_fc()} = {format_number(inputs.materials.concrete_strength_ksc)} ksc", format_number(inputs.materials.concrete_strength_ksc), "ksc"),
        ReportRow(_sym_fy(), "-", f"{_sym_fy()} = {format_number(inputs.materials.main_steel_yield_ksc)} ksc", format_number(inputs.materials.main_steel_yield_ksc), "ksc"),
        ReportRow(_sym_fvy(), "-", f"{_sym_fvy()} = {format_number(inputs.materials.shear_steel_yield_ksc)} ksc", format_number(inputs.materials.shear_steel_yield_ksc), "ksc"),
        ReportRow("b", "-", f"b = {format_number(inputs.geometry.width_cm)} cm", format_number(inputs.geometry.width_cm), "cm"),
        ReportRow("h", "-", f"h = {format_number(inputs.geometry.depth_cm)} cm", format_number(inputs.geometry.depth_cm), "cm"),
        ReportRow("cover", "-", f"cover = {format_number(inputs.geometry.cover_cm)} cm", format_number(inputs.geometry.cover_cm), "cm"),
    ]
    cantilever_value = _cantilever_span_summary(inputs)
    if cantilever_value is not None:
        rows.insert(2, ReportRow("Include Cantilever Span", "-", cantilever_value, cantilever_value, "-"))
    return ReportSection(title="Input Summary", rows=rows)


def _build_summary_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    combined = results.combined_shear_torsion
    rows = [ReportRow("Overall status", "-", results.overall_note, results.overall_status, "-", results.overall_note)]
    for spec in _active_flexural_report_specs(inputs, results):
        result = spec["result"]
        rows.append(ReportRow(f"{spec['label']} flexure", "-", result.design_status, result.design_status, "-", result.as_status))
    if combined.active:
        rows.append(ReportRow("Shear & Torsion", "-", f"Capacity Ratio (Shear + Torsion) = {format_ratio(combined.capacity_ratio)}", combined.design_status, "-", combined.design_status_note or f"\u03d5{combined.stirrup_diameter_mm} mm / {combined.stirrup_legs} legs @ {format_number(combined.stirrup_spacing_cm)} cm"))
    else:
        rows.append(ReportRow("Shear", "-", results.shear.design_status, results.shear.design_status, "-", f"{format_number(results.shear.provided_spacing_cm)} cm"))
    rows.append(ReportRow("Shear basis", "-", _shear_basis_text(results), f"{_shear_effective_depth_text(results)} cm", "-", results.shear.design_status))
    if inputs.torsion.enabled:
        torsion_note = combined.ignore_message if combined.torsion_ignored else results.torsion.pass_fail_summary
        rows.append(ReportRow("Torsion", "-", torsion_note, results.torsion.status, "-", results.torsion.status))
    rows.extend(
        [
            ReportRow("Warnings", "-", f"{len(results.warnings)} warnings", f"{len(results.warnings)} warnings", "-", note="See workspace summary for details"),
            ReportRow("Review flags", "-", f"{len(results.review_flags)} review flags", f"{len(results.review_flags)} review flags", "-", VerificationStatus.NEEDS_REVIEW.value if results.review_flags else "None"),
        ]
    )
    return ReportSection(title="Final Design Summary", rows=rows)


def build_print_report_sections(inputs: BeamDesignInputSet, results: BeamDesignResults) -> list[ReportSection]:
    input_summary_rows = [
        ReportRow("Design Code", "-", inputs.metadata.design_code.value, inputs.metadata.design_code.value, "-"),
        ReportRow("Beam Type", "-", inputs.beam_type.value, inputs.beam_type.value, "-"),
        ReportRow("Beam Behavior", "-", _beam_behavior_mode_summary(inputs), _beam_behavior_mode_summary(inputs), "-"),
        ReportRow("Sections", "-", _active_section_names(inputs), _active_section_names(inputs), "-"),
        ReportRow("Mu Mapping", "-", _mu_mapping_text(inputs), _mu_mapping_text(inputs), "-"),
        ReportRow("Vu Mapping", "-", _vu_mapping_text(inputs), _vu_mapping_text(inputs), "-"),
        ReportRow("Geometry", f"{_sym_b()} x {_sym_h()}, cover", f"{format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)}, c={format_number(inputs.geometry.cover_cm)}", f"{format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)} / {format_number(inputs.geometry.cover_cm)}", "cm"),
        ReportRow("Mu", "-", _print_input_mu_value(inputs), _print_input_mu_value(inputs), "kg-m"),
        ReportRow("Vu", "-", format_number(results.shear.input_factored_shear_kg), format_number(results.shear.input_factored_shear_kg), "kg"),
    ]
    cantilever_value = _cantilever_span_summary(inputs)
    if cantilever_value is not None:
        input_summary_rows.insert(3, ReportRow("Include Cantilever Span", "-", cantilever_value, cantilever_value, "-"))
    sections = [
        ReportSection(title="Input Summary", rows=input_summary_rows),
        ReportSection(
            title="Material Properties",
            rows=[
                ReportRow(f"{_sym_fc()}, {_sym_fy()}, {_sym_fvy()}", "-", f"{format_number(inputs.materials.concrete_strength_ksc)} / {format_number(inputs.materials.main_steel_yield_ksc)} / {format_number(inputs.materials.shear_steel_yield_ksc)}", f"{format_number(inputs.materials.concrete_strength_ksc)} / {format_number(inputs.materials.main_steel_yield_ksc)} / {format_number(inputs.materials.shear_steel_yield_ksc)}", "ksc"),
                ReportRow(_sym_ec(), _format_default_ec_logic(), _material_substitution(results.materials.ec_mode.value, results.materials.ec_default_ksc, inputs.material_settings.ec.manual_value), format_number(results.materials.ec_ksc), "ksc", results.materials.ec_mode.value, _material_note(results.materials.ec_mode.value, results.materials.ec_default_logic)),
                ReportRow(_sym_es(), _format_default_es_logic(), _material_substitution(results.materials.es_mode.value, results.materials.es_default_ksc, inputs.material_settings.es.manual_value), format_number(results.materials.es_ksc), "ksc", results.materials.es_mode.value, _material_note(results.materials.es_mode.value, results.materials.es_default_logic)),
                ReportRow(_sym_fr(), _format_default_fr_logic(), _material_substitution(results.materials.fr_mode.value, results.materials.fr_default_ksc, inputs.material_settings.fr.manual_value), format_number(results.materials.modulus_of_rupture_fr_ksc), "ksc", results.materials.fr_mode.value, _material_note(results.materials.fr_mode.value, results.materials.fr_default_logic)),
                ReportRow(_sym_beta1(), "-", f"{_sym_fc()} = {format_number(inputs.materials.concrete_strength_ksc)}", format_ratio(results.materials.beta_1), "-", note=VerificationStatus.VERIFIED_CODE.value),
            ],
        ),
        ReportSection(title="Section Geometry", rows=[ReportRow("Spacing", f"{_primary_section_label(inputs)} tension spacing", results.beam_geometry.positive_tension_spacing.overall_status, results.beam_geometry.positive_tension_spacing.overall_status, "-")]),
    ]
    if inputs.has_simple_support_design and results.support_bending is not None:
        sections.append(_build_support_section(inputs, results))
    if inputs.has_positive_design:
        positive_title = "Middle Moment Design" if inputs.beam_type == BeamType.SIMPLE else "Positive Moment Design"
        sections.append(ReportSection(title=positive_title, rows=[ReportRow("Tension Reinforcement", "Bottom bars", _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"), ReportRow("Compression Reinforcement", "Top bars", _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Top bars"), ReportRow(f"{_sym_as_req()} / {_sym_as_prov()}", f"{_sym_rho_req()} {_sym_b()} d, sum(bar areas)", "Positive bending", f"{format_number(results.positive_bending.as_required_cm2)} / {format_number(results.positive_bending.as_provided_cm2)}", _unit_cm2(), results.positive_bending.as_status), ReportRow(f"{_sym_mn()} / {_sym_phi_mn()}", f"{_sym_as()} {_sym_fy()} (d - a/2), Ï†{_sym_mn()}", "Positive bending", f"{format_number(results.positive_bending.mn_kgm)} / {format_number(results.positive_bending.phi_mn_kgm)}", "kg-m", results.positive_bending.design_status)]))
    if inputs.has_support_negative_design and results.negative_bending is not None:
        sections.append(ReportSection(title="Negative Moment Design", rows=[ReportRow("Tension Reinforcement", "Top bars", _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"), ReportRow("Compression Reinforcement", "Bottom bars", _format_arrangement(inputs.negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Bottom bars"), ReportRow("As req. / prov.", "rho_req * b * d-, sum(bar areas)", "Negative bending", f"{format_number(results.negative_bending.as_required_cm2)} / {format_number(results.negative_bending.as_provided_cm2)}", "cm2", results.negative_bending.as_status), ReportRow("Mn / phiMn", _moment_capacity_summary_equation(results.negative_bending, "As * fy * (d- - a/2), phi*Mn"), "Negative bending", f"{format_number(results.negative_bending.mn_kgm)} / {format_number(results.negative_bending.phi_mn_kgm)}", "kg-m", results.negative_bending.design_status)]))
    if inputs.has_cantilever_negative_design and results.cantilever_negative_bending is not None:
        sections.append(ReportSection(title="Cantilever Negative Moment Design", rows=[ReportRow("Tension Reinforcement", "Top bars", _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.cantilever_negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"), ReportRow("Compression Reinforcement", "Bottom bars", _format_arrangement(inputs.cantilever_negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.cantilever_negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Bottom bars"), ReportRow("As req. / prov.", "rho_req * b * d-, sum(bar areas)", "Cantilever negative bending", f"{format_number(results.cantilever_negative_bending.as_required_cm2)} / {format_number(results.cantilever_negative_bending.as_provided_cm2)}", "cm2", results.cantilever_negative_bending.as_status), ReportRow("Mn / phiMn", _moment_capacity_summary_equation(results.cantilever_negative_bending, "As * fy * (d- - a/2), phi*Mn"), "Cantilever negative bending", f"{format_number(results.cantilever_negative_bending.mn_kgm)} / {format_number(results.cantilever_negative_bending.phi_mn_kgm)}", "kg-m", results.cantilever_negative_bending.design_status)]))
    sections.append(ReportSection(title="Shear Design", rows=[ReportRow(f"{_sym_vu()} / {_sym_phi_vc()}", "Demand / concrete capacity", format_number(results.shear.input_factored_shear_kg), format_number(results.shear.phi_vc_kg), "kg", results.shear.design_status), ReportRow("Basis", "-", f"{results.shear.region_label} -> {results.shear.design_section_label}", results.shear.design_section_label, "-", results.shear.design_status), ReportRow("Req. spacing", "governing spacing s", "Strength and code spacing limits", format_number(results.shear.required_spacing_cm), "cm", results.shear.design_status), ReportRow("Prov. spacing", f"{results.shear.spacing_mode.value} spacing", f"db={inputs.shear.stirrup_diameter_mm} mm, legs={inputs.shear.legs_per_plane}", format_number(results.shear.provided_spacing_cm), "cm", results.shear.design_status), ReportRow(_sym_phi_vs(), f"Ï† {_sym_av()} {_sym_fvy()} d / s", f"{results.shear.phi:.3f} x {_sym_av()} x {format_number(inputs.materials.shear_steel_yield_ksc)} x d / {format_number(results.shear.provided_spacing_cm)}", format_number(results.shear.phi_vs_provided_kg), "kg"), ReportRow(f"{_sym_vn()} / {_sym_phi_vn()}", f"{_sym_vc()} + {_sym_vs()}(provided), Ï†{_sym_vn()}", f"{format_number(results.shear.vn_kg)} / {format_number(results.shear.phi_vn_kg)}", f"{format_number(results.shear.vn_kg)} / {format_number(results.shear.phi_vn_kg)}", "kg", results.shear.design_status), ReportRow("Shear capacity ratio", f"{_sym_vu()} / {_sym_phi_vn()}", f"{format_number(results.shear.input_factored_shear_kg)} / {format_number(results.shear.phi_vn_kg)}", format_ratio(results.shear.capacity_ratio), "-", results.shear.design_status)]))
    if inputs.torsion.enabled:
        sections.append(_build_print_torsion_section(results))
    if inputs.consider_deflection:
        sections.append(_build_print_deflection_section(results))
    for index, section in enumerate(sections):
        if section.title in {"Positive Moment Design", "Middle Moment Design"}:
            sections[index] = _with_updated_moment_summary_row(section, results.positive_bending)
        elif section.title == "Support Moment Design" and results.support_bending is not None:
            sections[index] = _with_updated_moment_summary_row(section, results.support_bending)
        elif section.title == "Negative Moment Design" and results.negative_bending is not None:
            sections[index] = _with_updated_moment_summary_row(section, results.negative_bending)
        elif section.title == "Cantilever Negative Moment Design" and results.cantilever_negative_bending is not None:
            sections[index] = _with_updated_moment_summary_row(section, results.cantilever_negative_bending)
    sections.append(_build_print_design_summary(inputs, results))
    return sections
