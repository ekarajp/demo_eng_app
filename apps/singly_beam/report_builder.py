from __future__ import annotations

from dataclasses import dataclass

from core.theme import ThemePalette
from core.utils import format_number, format_ratio, longitudinal_bar_mark

from .models import BeamDesignInputSet, BeamDesignResults, ReinforcementArrangementInput, VerificationStatus


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


def build_report_sections(inputs: BeamDesignInputSet, results: BeamDesignResults) -> list[ReportSection]:
    sections = [
        _build_input_summary(inputs),
        _build_material_section(inputs, results),
        _build_geometry_section(inputs, results),
        _build_positive_section(inputs, results),
    ]
    if inputs.has_negative_design and results.negative_bending is not None:
        sections.append(_build_negative_section(inputs, results))
    sections.append(_build_shear_section(inputs, results))
    sections.append(_build_summary_section(inputs, results))
    return sections


def build_print_report_sections(inputs: BeamDesignInputSet, results: BeamDesignResults) -> list[ReportSection]:
    input_summary_rows = [
        ReportRow("Design Code", "-", inputs.metadata.design_code.value, inputs.metadata.design_code.value, "-"),
        ReportRow(
            "Geometry",
            f"{_sym_b()} x {_sym_h()}, cover",
            f"{format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)}, c={format_number(inputs.geometry.cover_cm)}",
            f"{format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)} / {format_number(inputs.geometry.cover_cm)}",
            "cm",
        ),
        ReportRow(
            "Mu",
            "-",
            _print_input_mu_value(inputs),
            _print_input_mu_value(inputs),
            "kg-m",
        ),
        ReportRow("Vu", "-", format_number(inputs.shear.factored_shear_kg), format_number(inputs.shear.factored_shear_kg), "kg"),
    ]
    sections = [
        ReportSection(
            title="Input Summary",
            rows=input_summary_rows,
        ),
        ReportSection(
            title="Material Properties",
            rows=[
                ReportRow(
                    f"{_sym_fc()}, {_sym_fy()}, {_sym_fvy()}",
                    "-",
                    f"{format_number(inputs.materials.concrete_strength_ksc)} / {format_number(inputs.materials.main_steel_yield_ksc)} / {format_number(inputs.materials.shear_steel_yield_ksc)}",
                    f"{format_number(inputs.materials.concrete_strength_ksc)} / {format_number(inputs.materials.main_steel_yield_ksc)} / {format_number(inputs.materials.shear_steel_yield_ksc)}",
                    "ksc",
                ),
                ReportRow(_sym_ec(), _format_default_ec_logic(), _material_substitution(results.materials.ec_mode.value, results.materials.ec_default_ksc, inputs.material_settings.ec.manual_value), format_number(results.materials.ec_ksc), "ksc", results.materials.ec_mode.value, _material_note(results.materials.ec_mode.value, results.materials.ec_default_logic)),
                ReportRow(_sym_es(), _format_default_es_logic(), _material_substitution(results.materials.es_mode.value, results.materials.es_default_ksc, inputs.material_settings.es.manual_value), format_number(results.materials.es_ksc), "ksc", results.materials.es_mode.value, _material_note(results.materials.es_mode.value, results.materials.es_default_logic)),
                ReportRow(_sym_fr(), _format_default_fr_logic(), _material_substitution(results.materials.fr_mode.value, results.materials.fr_default_ksc, inputs.material_settings.fr.manual_value), format_number(results.materials.modulus_of_rupture_fr_ksc), "ksc", results.materials.fr_mode.value, _material_note(results.materials.fr_mode.value, results.materials.fr_default_logic)),
                ReportRow(_sym_beta1(), "-", f"{_sym_fc()} = {format_number(inputs.materials.concrete_strength_ksc)}", format_ratio(results.materials.beta_1), "-", note=VerificationStatus.NEEDS_REVIEW.value),
            ],
        ),
        ReportSection(
            title="Section Geometry",
            rows=[
                ReportRow("d′", "Compression steel centroid", "Layer centroid", format_number(results.beam_geometry.positive_compression_centroid_d_prime_cm), "cm"),
                ReportRow("d", "Tension steel centroid", "Layer centroid", format_number(results.beam_geometry.d_plus_cm), "cm", note="Positive effective depth"),
                ReportRow("Spacing", "Positive tension spacing", results.beam_geometry.positive_tension_spacing.overall_status, results.beam_geometry.positive_tension_spacing.overall_status, "-"),
            ],
        ),
        ReportSection(
            title="Positive Moment Design",
            rows=[
                ReportRow("Tension Reinforcement", "Bottom bars", _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
                ReportRow("Compression Reinforcement", "Top bars", _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.positive_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Top bars"),
                ReportRow(f"{_sym_as_req()} / {_sym_as_prov()}", f"{_sym_rho_req()} {_sym_b()} d, sum(bar areas)", "Positive bending", f"{format_number(results.positive_bending.as_required_cm2)} / {format_number(results.positive_bending.as_provided_cm2)}", _unit_cm2(), results.positive_bending.as_status),
                ReportRow(f"{_sym_mn()} / {_sym_phi_mn()}", f"{_sym_as()} {_sym_fy()} (d - a/2), φ{_sym_mn()}", "Positive bending", f"{format_number(results.positive_bending.mn_kgm)} / {format_number(results.positive_bending.phi_mn_kgm)}", "kg-m", results.positive_bending.design_status),
            ],
        ),
    ]
    if inputs.has_negative_design and results.negative_bending is not None:
        sections.append(
            ReportSection(
                title="Negative Moment Design",
                rows=[
                    ReportRow("Tension Reinforcement", "Top bars", _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.negative_bending.tension_reinforcement, inputs.materials.main_steel_yield_ksc), "-"),
                    ReportRow("Compression Reinforcement", "Bottom bars", _format_arrangement(inputs.negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), _format_arrangement(inputs.negative_bending.compression_reinforcement, inputs.materials.main_steel_yield_ksc), "-", note="Bottom bars"),
                    ReportRow("As req. / prov.", "rho_req * b * d, sum(bar areas)", "Negative bending", f"{format_number(results.negative_bending.as_required_cm2)} / {format_number(results.negative_bending.as_provided_cm2)}", "cm2", results.negative_bending.as_status),
                    ReportRow("Mn / phiMn", "As * fy * (d+ - a/2), phi*Mn", "Current negative block", f"{format_number(results.negative_bending.mn_kgm)} / {format_number(results.negative_bending.phi_mn_kgm)}", "kg-m", results.negative_bending.design_status, results.negative_bending.review_note),
                ],
            )
        )
    sections.append(
        ReportSection(
            title="Shear Design",
            rows=[
                ReportRow(f"{_sym_vu()} / {_sym_phi_vc()}", "Demand / concrete capacity", format_number(inputs.shear.factored_shear_kg), format_number(results.shear.phi_vc_kg), "kg", results.shear.design_status),
                ReportRow("Req. spacing", "governing spacing s", "Strength and code spacing limits", format_number(results.shear.required_spacing_cm), "cm", results.shear.design_status),
                ReportRow("Prov. spacing", f"{results.shear.spacing_mode.value} spacing", f"db={inputs.shear.stirrup_diameter_mm} mm, legs={inputs.shear.legs_per_plane}", format_number(results.shear.provided_spacing_cm), "cm", results.shear.design_status),
                ReportRow(_sym_phi_vs(), f"φ {_sym_av()} {_sym_fvy()} d / s", f"{results.shear.phi:.3f} x {_sym_av()} x {format_number(inputs.materials.shear_steel_yield_ksc)} x d / {format_number(results.shear.provided_spacing_cm)}", format_number(results.shear.phi_vs_provided_kg), "kg"),
                ReportRow(f"{_sym_vn()} / {_sym_phi_vn()}", f"{_sym_vc()} + {_sym_vs()}(provided), φ{_sym_vn()}", f"{format_number(results.shear.vn_kg)} / {format_number(results.shear.phi_vn_kg)}", f"{format_number(results.shear.vn_kg)} / {format_number(results.shear.phi_vn_kg)}", "kg", results.shear.design_status),
                ReportRow("Shear capacity ratio", f"{_sym_vu()} / {_sym_phi_vn()}", f"{format_number(inputs.shear.factored_shear_kg)} / {format_number(results.shear.phi_vn_kg)}", format_ratio(results.shear.capacity_ratio), "-", results.shear.design_status),
            ],
        )
    )
    sections.append(_build_print_design_summary(inputs, results))
    return sections


def build_full_report_sections(inputs: BeamDesignInputSet, results: BeamDesignResults) -> list[ReportSection]:
    sections = [
        _build_full_input_summary(inputs),
        _build_full_material_section(inputs, results),
        _build_full_geometry_section(inputs, results),
        _build_full_positive_section(inputs, results),
        _build_full_spacing_section(inputs, results),
        _build_full_shear_section(inputs, results),
    ]
    if inputs.has_negative_design and results.negative_bending is not None:
        sections.append(_build_full_negative_section(inputs, results))
    sections.extend(
        [
            _build_full_warning_section(results),
            _build_full_review_flag_section(results),
            _build_full_summary_section(inputs, results),
            _build_full_notation_section(inputs),
        ]
    )
    return sections


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
        grid-template-columns: repeat(4, minmax(0, 1fr));
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


def _build_input_summary(inputs: BeamDesignInputSet) -> ReportSection:
    return ReportSection(
        title="Input Summary",
        rows=[
            ReportRow("Design code", "-", inputs.metadata.design_code.value, inputs.metadata.design_code.value, "-"),
            ReportRow("fc'", "-", format_number(inputs.materials.concrete_strength_ksc), format_number(inputs.materials.concrete_strength_ksc), "ksc"),
            ReportRow("fy", "-", format_number(inputs.materials.main_steel_yield_ksc), format_number(inputs.materials.main_steel_yield_ksc), "ksc"),
            ReportRow("b", "-", format_number(inputs.geometry.width_cm), format_number(inputs.geometry.width_cm), "cm"),
            ReportRow("h", "-", format_number(inputs.geometry.depth_cm), format_number(inputs.geometry.depth_cm), "cm"),
        ],
    )


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
                status=VerificationStatus.NEEDS_REVIEW.value,
                note="Current ACI-style transition logic implemented. Manual clause check still recommended.",
            ),
        ],
    )


def _build_geometry_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    rows = [
        ReportRow("Section area", "b * h", f"{inputs.geometry.width_cm:.2f} * {inputs.geometry.depth_cm:.2f}", format_number(results.beam_geometry.section_area_cm2), "cm2"),
        ReportRow("Ig", "b * h^3 / 12", f"{inputs.geometry.width_cm:.2f} * {inputs.geometry.depth_cm:.2f}^3 / 12", format_number(results.beam_geometry.gross_moment_of_inertia_cm4), "cm4"),
        ReportRow("d'", "Top compression steel centroid", "Layer centroid calculation", format_number(results.beam_geometry.positive_compression_centroid_d_prime_cm), "cm", note="Compression reinforcement"),
        ReportRow("d", "Bottom tension steel centroid", "Layer centroid calculation", format_number(results.beam_geometry.positive_tension_centroid_from_bottom_d_cm), "cm", note="Tension reinforcement"),
        ReportRow("d+", "h - d", f"{inputs.geometry.depth_cm:.2f} - {results.beam_geometry.positive_tension_centroid_from_bottom_d_cm:.2f}", format_number(results.beam_geometry.d_plus_cm), "cm", note="Positive effective depth"),
    ]
    if inputs.has_negative_design and results.beam_geometry.d_minus_cm is not None:
        rows.append(
            ReportRow("d-", "h - d'", f"{inputs.geometry.depth_cm:.2f} - {results.beam_geometry.positive_compression_centroid_d_prime_cm:.2f}", format_number(results.beam_geometry.d_minus_cm), "cm", note="Negative effective depth")
        )
    return ReportSection(title="Section Geometry", rows=rows)


def _build_positive_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    positive = results.positive_bending
    return ReportSection(
        title="Positive Moment Design",
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
            ReportRow("et", "ecu * dt / c", f"0.003 * {format_number(positive.dt_cm)} / {format_number(positive.c_cm)}", format_ratio(positive.et, 6), "-"),
            ReportRow("Mn", "As * fy * (d - a/2) / 100", f"{format_number(positive.as_provided_cm2)} * {format_number(inputs.materials.main_steel_yield_ksc)} * ({format_number(results.beam_geometry.d_plus_cm)} - {format_number(positive.a_cm)}/2) / 100", format_number(positive.mn_kgm), "kg-m"),
            ReportRow("phiMn", "phi * Mn", f"{positive.phi:.3f} * {positive.mn_kgm:.2f}", format_number(positive.phi_mn_kgm), "kg-m", positive.ratio_status),
            ReportRow("Moment capacity ratio", "Mu / PhiMn", f"{format_number(inputs.positive_bending.factored_moment_kgm)} / {format_number(positive.phi_mn_kgm)}", format_ratio(positive.ratio), "-", positive.design_status),
        ],
    )


def _build_shear_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    shear = results.shear
    return ReportSection(
        title="Shear Design",
        rows=[
            ReportRow("phi", "Shear phi by selected code", inputs.metadata.design_code.value, format_ratio(shear.phi), "-", shear.design_status),
            ReportRow("Vc", "0.53 * sqrt(fc') * b * d", "Current nominal concrete shear", format_number(shear.vc_kg), "kg"),
            ReportRow("phiVc", "phi * Vc", f"{shear.phi:.3f} * {shear.vc_kg:.2f}", format_number(shear.phi_vc_kg), "kg"),
            ReportRow("Vs,max", "2.1 * sqrt(fc') * b * d", "Current nominal steel shear limit", format_number(shear.vs_max_kg), "kg"),
            ReportRow("phiVs,max", "phi * Vs,max", f"{format_ratio(shear.phi, 3)} * {format_number(shear.vs_max_kg)}", format_number(shear.phi_vs_max_kg), "kg"),
            ReportRow("phiVs required", "Vu - phiVc", f"{format_number(inputs.shear.factored_shear_kg)} - {format_number(shear.phi_vc_kg)}", format_number(shear.phi_vs_required_kg), "kg"),
            ReportRow("Vs required", "phiVs required / phi", f"{format_number(shear.phi_vs_required_kg)} / {format_ratio(shear.phi, 3)}", format_number(shear.nominal_vs_required_kg), "kg"),
            ReportRow("Av", "pi * db^2 / 4 * legs", f"db={inputs.shear.stirrup_diameter_mm}, legs={inputs.shear.legs_per_plane}", format_number(shear.av_cm2), "cm2"),
            ReportRow("Av,min", "Minimum stirrup area at provided spacing", f"s = {format_number(shear.provided_spacing_cm)}", format_number(shear.av_min_cm2), "cm2", shear.design_status if shear.av_cm2 < shear.av_min_cm2 else None),
            ReportRow("Size effect", "ACI 318-19 lambda_s", "Applied to Vc when Av < Av,min" if shear.size_effect_applied else "Not applied", format_ratio(shear.size_effect_factor, 3), "-", shear.design_status if shear.size_effect_applied else None),
            ReportRow("s max from Av", "min(Av*fvy/(0.2*sqrt(fc')*b), Av*fvy/(3.5*b))", "Current spacing limit", format_number(shear.s_max_from_av_cm), "cm"),
            ReportRow("s max from Vs", "Code-style spacing limit", "Current branch logic", format_number(shear.s_max_from_vs_cm), "cm"),
            ReportRow("Required spacing", "min(s strength, s max from Av, s max from Vs)", "Governing required spacing", format_number(shear.required_spacing_cm), "cm"),
            ReportRow("Provided spacing", f"{shear.spacing_mode.value} selection", "Spacing used for PhiVs and PhiVn", format_number(shear.provided_spacing_cm), "cm", shear.design_status),
            ReportRow("Vs", "Av * fvy * d / s", f"Use s = {format_number(shear.provided_spacing_cm)}", format_number(shear.vs_provided_kg), "kg"),
            ReportRow("PhiVs", "phi * Vs", f"{shear.phi:.3f} * {format_number(shear.vs_provided_kg)}", format_number(shear.phi_vs_provided_kg), "kg"),
            ReportRow("Vn", "Vc + min(Vs, Vs,max)", f"{format_number(shear.vc_kg)} + min({format_number(shear.vs_provided_kg)}, {format_number(shear.vs_max_kg)})", format_number(shear.vn_kg), "kg"),
            ReportRow("PhiVn", "phi * Vn", f"{shear.phi:.3f} * {format_number(shear.vn_kg)}", format_number(shear.phi_vn_kg), "kg"),
            ReportRow("Stirrup spacing", "Provided spacing", f"{shear.spacing_mode.value} mode", format_number(shear.provided_spacing_cm), "cm", shear.design_status, shear.review_note),
            ReportRow("Shear capacity ratio", "Vu / PhiVn", f"{format_number(inputs.shear.factored_shear_kg)} / {format_number(shear.phi_vn_kg)}", format_ratio(shear.capacity_ratio), "-", shear.design_status),
        ],
    )


def _build_negative_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    negative = results.negative_bending
    if negative is None:
        raise ValueError("Negative moment report section requested for a simple beam result.")
    d_minus_cm = results.beam_geometry.d_minus_cm
    d_minus_text = format_number(d_minus_cm) if d_minus_cm is not None else "N/A"
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
            ReportRow("As min", "rho_min * b * d+", "Current negative block uses d+ here", format_number(negative.as_min_cm2), "cm2", VerificationStatus.NEEDS_REVIEW.value, negative.review_note),
            ReportRow("As max", "rho_max * b * d-", f"{negative.rho_max:.6f} * {inputs.geometry.width_cm:.2f} * {d_minus_text}", format_number(negative.as_max_cm2), "cm2"),
            ReportRow("a", "As * fy / (0.85 * fc' * b)", "Current negative block", format_number(negative.a_cm), "cm"),
            ReportRow("c", "a / beta1", "Current negative block", format_number(negative.c_cm), "cm"),
            ReportRow("et", "ecu * dt / c", "Current negative block", format_ratio(negative.et, 6), "-"),
            ReportRow("Mn", "As * fy * (d+ - a/2) / 100", "Current negative block uses d+ here", format_number(negative.mn_kgm), "kg-m", VerificationStatus.NEEDS_REVIEW.value, negative.review_note),
            ReportRow("phiMn", "phi * Mn", f"{negative.phi:.3f} * {negative.mn_kgm:.2f}", format_number(negative.phi_mn_kgm), "kg-m", negative.ratio_status),
        ],
    )


def _build_summary_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    rows = [
        ReportRow("Overall status", "-", results.overall_note, results.overall_status, "-", results.overall_note),
        ReportRow("Positive flexure", "-", results.positive_bending.design_status, results.positive_bending.design_status, "-", results.positive_bending.as_status),
        ReportRow("Shear", "-", results.shear.design_status, results.shear.design_status, "-", f"{format_number(results.shear.provided_spacing_cm)} cm"),
    ]
    if inputs.has_negative_design and results.negative_bending is not None:
        rows.append(
            ReportRow("Negative flexure", "-", results.negative_bending.design_status, results.negative_bending.design_status, "-", results.negative_bending.as_status)
        )
    rows.extend(
        [
            ReportRow("Warnings", "-", f"{len(results.warnings)} warnings", f"{len(results.warnings)} warnings", "-", note="See workspace summary for details"),
            ReportRow("Review flags", "-", f"{len(results.review_flags)} review flags", f"{len(results.review_flags)} review flags", "-", VerificationStatus.NEEDS_REVIEW.value),
        ]
    )
    return ReportSection(title="Final Design Summary", rows=rows)


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


def _build_full_input_summary(inputs: BeamDesignInputSet) -> ReportSection:
    return ReportSection(
        title="Input Summary",
        rows=[
            ReportRow("Design code", "-", inputs.metadata.design_code.value, inputs.metadata.design_code.value, "-"),
            ReportRow(_sym_fc(), "-", f"{_sym_fc()} = {format_number(inputs.materials.concrete_strength_ksc)} ksc", format_number(inputs.materials.concrete_strength_ksc), "ksc"),
            ReportRow(_sym_fy(), "-", f"{_sym_fy()} = {format_number(inputs.materials.main_steel_yield_ksc)} ksc", format_number(inputs.materials.main_steel_yield_ksc), "ksc"),
            ReportRow(_sym_fvy(), "-", f"{_sym_fvy()} = {format_number(inputs.materials.shear_steel_yield_ksc)} ksc", format_number(inputs.materials.shear_steel_yield_ksc), "ksc"),
            ReportRow("b", "-", f"b = {format_number(inputs.geometry.width_cm)} cm", format_number(inputs.geometry.width_cm), "cm"),
            ReportRow("h", "-", f"h = {format_number(inputs.geometry.depth_cm)} cm", format_number(inputs.geometry.depth_cm), "cm"),
            ReportRow("cover", "-", f"cover = {format_number(inputs.geometry.cover_cm)} cm", format_number(inputs.geometry.cover_cm), "cm"),
        ],
    )


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
            ReportRow(_sym_beta1(), "-", f"{_sym_beta1()} from {_sym_fc()} = {format_number(inputs.materials.concrete_strength_ksc)} ksc", format_ratio(results.materials.beta_1), "-", VerificationStatus.NEEDS_REVIEW.value),
        ],
    )


def _build_full_geometry_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    rows = [
        ReportRow("A<sub>g</sub>", "A<sub>g</sub> = b x h", f"A<sub>g</sub> = {format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)}", format_number(results.beam_geometry.section_area_cm2), _unit_cm2()),
        ReportRow("I<sub>g</sub>", "I<sub>g</sub> = bh<sup>3</sup> / 12", f"I<sub>g</sub> = {format_number(inputs.geometry.width_cm)} x {format_number(inputs.geometry.depth_cm)}<sup>3</sup> / 12", format_number(results.beam_geometry.gross_moment_of_inertia_cm4), "cm<sup>4</sup>"),
        ReportRow("d′", "-", "Centroid of top reinforcement from compression face", format_number(results.beam_geometry.positive_compression_centroid_d_prime_cm), "cm"),
        ReportRow("d", "-", "Effective depth to bottom tension reinforcement", format_number(results.beam_geometry.d_plus_cm), "cm"),
    ]
    if inputs.has_negative_design and results.beam_geometry.d_minus_cm is not None:
        rows.append(
            ReportRow("d-", "-", "Effective depth for negative moment reinforcement", format_number(results.beam_geometry.d_minus_cm), "cm")
        )
    return ReportSection(title="Section Geometry", rows=rows)


def _build_full_positive_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    positive = results.positive_bending
    return ReportSection(
        title="Positive Moment Design",
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
            ReportRow("&epsilon;<sub>t</sub>", "&epsilon;<sub>t</sub> = 0.003d<sub>t</sub> / c", f"&epsilon;<sub>t</sub> = 0.003 &times; {format_number(positive.dt_cm)} / {format_number(positive.c_cm)}", format_ratio(positive.et, 6), "-"),
            ReportRow(_sym_mn(), f"{_sym_mn()} = A<sub>s</sub>{_sym_fy()}(d - a/2) / 100", f"{_sym_mn()} = {format_number(positive.as_provided_cm2)} &times; {format_number(inputs.materials.main_steel_yield_ksc)} &times; ({format_number(results.beam_geometry.d_plus_cm)} - {format_number(positive.a_cm)}/2) / 100", format_number(positive.mn_kgm), "kg-m"),
            ReportRow(_sym_phi_mn(), f"{_sym_phi_mn()} = &phi;{_sym_mn()}", f"{_sym_phi_mn()} = {format_ratio(positive.phi, 3)} &times; {format_number(positive.mn_kgm)}", format_number(positive.phi_mn_kgm), "kg-m", positive.ratio_status),
            ReportRow(f"M<sub>u</sub> / {_sym_phi_mn()}", "-", f"{format_number(inputs.positive_bending.factored_moment_kgm)} / {format_number(positive.phi_mn_kgm)}", format_ratio(positive.ratio), "-", positive.design_status),
        ],
    )


def _build_full_shear_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    shear = results.shear
    return ReportSection(
        title="Shear Design",
        rows=[
            ReportRow(_sym_vu(), "-", f"{_sym_vu()} = {format_number(inputs.shear.factored_shear_kg)} kg", format_number(inputs.shear.factored_shear_kg), "kg"),
            ReportRow("&phi;", "-", f"Selected from {inputs.metadata.design_code.value}", format_ratio(shear.phi), "-", shear.design_status),
            ReportRow(_sym_vc(), f"{_sym_vc()} = 0.53&radic;{_sym_fc()}bd", f"{_sym_vc()} = 0.53 &times; &radic;{format_number(inputs.materials.concrete_strength_ksc)} &times; {format_number(inputs.geometry.width_cm)} &times; {format_number(results.beam_geometry.d_plus_cm)}", format_number(shear.vc_kg), "kg"),
            ReportRow(_sym_phi_vc(), f"{_sym_phi_vc()} = &phi;{_sym_vc()}", f"{_sym_phi_vc()} = {format_ratio(shear.phi, 3)} &times; {format_number(shear.vc_kg)}", format_number(shear.phi_vc_kg), "kg"),
            ReportRow("V<sub>s,max</sub>", f"V<sub>s,max</sub> = 2.1&radic;{_sym_fc()}bd", f"V<sub>s,max</sub> = 2.1 &times; &radic;{format_number(inputs.materials.concrete_strength_ksc)} &times; {format_number(inputs.geometry.width_cm)} &times; {format_number(results.beam_geometry.d_plus_cm)}", format_number(shear.vs_max_kg), "kg"),
            ReportRow("&phi;V<sub>s,max</sub>", "&phi;V<sub>s,max</sub> = &phi; &times; V<sub>s,max</sub>", f"&phi;V<sub>s,max</sub> = {format_ratio(shear.phi, 3)} &times; {format_number(shear.vs_max_kg)}", format_number(shear.phi_vs_max_kg), "kg"),
            ReportRow("&phi;V<sub>s,req</sub>", f"&phi;V<sub>s,req</sub> = {_sym_vu()} - {_sym_phi_vc()}", f"&phi;V<sub>s,req</sub> = {format_number(inputs.shear.factored_shear_kg)} - {format_number(shear.phi_vc_kg)}", format_number(shear.phi_vs_required_kg), "kg"),
            ReportRow("V<sub>s,req</sub>", "V<sub>s,req</sub> = &phi;V<sub>s,req</sub> / &phi;", f"V<sub>s,req</sub> = {format_number(shear.phi_vs_required_kg)} / {format_ratio(shear.phi, 3)}", format_number(shear.nominal_vs_required_kg), "kg"),
            ReportRow(_sym_av(), f"{_sym_av()} = &pi;d<sub>b</sub><sup>2</sup> / 4 &times; number of legs", f"{_sym_av()} = &pi; &times; {format_number(inputs.shear.stirrup_diameter_mm / 10)}<sup>2</sup> / 4 &times; {inputs.shear.legs_per_plane}", format_number(shear.av_cm2), _unit_cm2()),
            ReportRow("s_max,1", "-", "Limit from transverse reinforcement proportioning", format_number(shear.s_max_from_av_cm), "cm"),
            ReportRow("s_max,2", "-", "Limit from shear demand branch", format_number(shear.s_max_from_vs_cm), "cm"),
            ReportRow("s<sub>req</sub>", "s<sub>req</sub> = min(strength limit, spacing limits)", "Use the smallest permitted spacing", format_number(shear.required_spacing_cm), "cm"),
            ReportRow("s<sub>prov</sub>", "-", f"{shear.spacing_mode.value} spacing used in design", format_number(shear.provided_spacing_cm), "cm", shear.design_status),
            ReportRow(_sym_vs(), f"{_sym_vs()} = {_sym_av()}{_sym_fvy()}d / s<sub>prov</sub>", f"{_sym_vs()} = {format_number(shear.av_cm2)} &times; {format_number(inputs.materials.shear_steel_yield_ksc)} &times; {format_number(results.beam_geometry.d_plus_cm)} / {format_number(shear.provided_spacing_cm)}", format_number(shear.vs_provided_kg), "kg"),
            ReportRow(_sym_phi_vs(), f"{_sym_phi_vs()} = &phi;{_sym_vs()}", f"{_sym_phi_vs()} = {format_ratio(shear.phi, 3)} &times; {format_number(shear.vs_provided_kg)}", format_number(shear.phi_vs_provided_kg), "kg"),
            ReportRow(_sym_vn(), f"{_sym_vn()} = {_sym_vc()} + min({_sym_vs()}, V<sub>s,max</sub>)", f"{_sym_vn()} = {format_number(shear.vc_kg)} + min({format_number(shear.vs_provided_kg)}, {format_number(shear.vs_max_kg)})", format_number(shear.vn_kg), "kg"),
            ReportRow(_sym_phi_vn(), f"{_sym_phi_vn()} = &phi;{_sym_vn()}", f"{_sym_phi_vn()} = {format_ratio(shear.phi, 3)} &times; {format_number(shear.vn_kg)}", format_number(shear.phi_vn_kg), "kg"),
            ReportRow(f"{_sym_vu()} / {_sym_phi_vn()}", "-", f"{format_number(inputs.shear.factored_shear_kg)} / {format_number(shear.phi_vn_kg)}", format_ratio(shear.capacity_ratio), "-", shear.design_status, shear.review_note),
        ],
    )


def _build_full_negative_section(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    negative = results.negative_bending
    if negative is None:
        raise ValueError("Negative moment report section requested for a simple beam result.")
    d_minus_cm = results.beam_geometry.d_minus_cm
    d_minus_text = format_number(d_minus_cm) if d_minus_cm is not None else "N/A"
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
            ReportRow("A<sub>s,min,neg</sub>", "-", "The current negative-moment branch follows the implemented application logic.", format_number(negative.as_min_cm2), _unit_cm2(), VerificationStatus.NEEDS_REVIEW.value, negative.review_note),
            ReportRow("A<sub>s,max,neg</sub>", "A<sub>s,max,neg</sub> = &rho;<sub>max</sub>bd<sub>neg</sub>", f"A<sub>s,max,neg</sub> = {format_ratio(negative.rho_max, 6)} &times; {format_number(inputs.geometry.width_cm)} &times; {d_minus_text}", format_number(negative.as_max_cm2), _unit_cm2()),
            ReportRow("a", "-", f"a = {format_number(negative.a_cm)} cm", format_number(negative.a_cm), "cm"),
            ReportRow("c", f"c = a / {_sym_beta1()}", f"c = {format_number(negative.a_cm)} / {format_ratio(results.materials.beta_1, 4)}", format_number(negative.c_cm), "cm"),
            ReportRow("&epsilon;<sub>t,neg</sub>", "&epsilon;<sub>t,neg</sub> = 0.003d<sub>t</sub> / c", "The tensile strain is taken from the implemented strain-compatibility check.", format_ratio(negative.et, 6), "-"),
            ReportRow("M<sub>n,neg</sub>", "-", "The current negative-moment branch follows the implemented application logic.", format_number(negative.mn_kgm), "kg-m", VerificationStatus.NEEDS_REVIEW.value, negative.review_note),
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
    warning_summary = "; ".join(results.warnings) if results.warnings else "No direct warnings."
    review_summary = "; ".join(flag.message for flag in results.review_flags) if results.review_flags else "No review notes."
    rows = [
        ReportRow("Overall design status", "-", results.overall_note, results.overall_status, "-", results.overall_note),
        ReportRow(f"Positive flexure, M<sub>u</sub> / {_sym_phi_mn()}", "-", f"M<sub>u</sub> / {_sym_phi_mn()} = {format_ratio(results.positive_bending.ratio)}", results.positive_bending.design_status, "-", results.positive_bending.as_status),
        ReportRow(f"Shear, {_sym_vu()} / {_sym_phi_vn()}", "-", f"{_sym_vu()} / {_sym_phi_vn()} = {format_ratio(results.shear.capacity_ratio)}; s<sub>prov</sub> = {format_number(results.shear.provided_spacing_cm)} cm", results.shear.design_status, "-", f"s<sub>prov</sub> = {format_number(results.shear.provided_spacing_cm)} cm"),
    ]
    if inputs.has_negative_design and results.negative_bending is not None:
        rows.append(
            ReportRow("Negative flexure, M<sub>u,neg</sub> / &phi;M<sub>n,neg</sub>", "-", f"M<sub>u,neg</sub> / &phi;M<sub>n,neg</sub> = {format_ratio(results.negative_bending.ratio)}", results.negative_bending.design_status, "-", results.negative_bending.as_status)
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


def _print_input_mu_value(inputs: BeamDesignInputSet) -> str:
    positive_text = format_number(inputs.positive_bending.factored_moment_kgm)
    if not inputs.has_negative_design:
        return positive_text
    return f"(+) {positive_text} | (-) {format_number(inputs.negative_bending.factored_moment_kgm)}"


def _build_print_design_summary(inputs: BeamDesignInputSet, results: BeamDesignResults) -> ReportSection:
    rows = [
        ReportRow(
            "Overall Status",
            "-",
            f"Warnings = {len(results.warnings)} | Review flags = {len(results.review_flags)}",
            results.overall_status,
            "-",
            note=results.overall_note,
        ),
        ReportRow(
            "Positive Flexure",
            "-",
            f"Mu / phiMn = {format_ratio(results.positive_bending.ratio)} | phiMn = {format_number(results.positive_bending.phi_mn_kgm)} kg-m",
            results.positive_bending.design_status,
            "-",
            status=results.positive_bending.as_status,
            note=_print_flexural_summary_note(results.positive_bending.review_note),
        ),
        ReportRow(
            "Shear",
            "-",
            f"Vu / phiVn = {format_ratio(results.shear.capacity_ratio)} | phiVn = {format_number(results.shear.phi_vn_kg)} kg",
            results.shear.design_status,
            "-",
            status=f"s prov = {format_number(results.shear.provided_spacing_cm)} cm",
            note=_print_shear_summary_note(results),
        ),
    ]
    if inputs.has_negative_design and results.negative_bending is not None:
        rows.insert(
            2,
            ReportRow(
                "Negative Flexure",
                "-",
                f"Mu / phiMn = {format_ratio(results.negative_bending.ratio)} | phiMn = {format_number(results.negative_bending.phi_mn_kgm)} kg-m",
                results.negative_bending.design_status,
                "-",
                status=results.negative_bending.as_status,
                note=_print_flexural_summary_note(results.negative_bending.review_note),
            ),
        )
    return ReportSection(title="Design Summary", rows=rows)


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
    return "Capacity ratio <= 1.00 is acceptable in this summary view."


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


def _format_default_es_logic() -> str:
    return f"{_sym_es()} = 2.04 × 10<sup>6</sup>"


def _format_default_fr_logic() -> str:
    return f"{_sym_fr()} = 2&radic;{_sym_fc()}"


def _format_default_es_logic() -> str:
    return f"{_sym_es()} = 2.04 &times; 10<sup>6</sup>"
