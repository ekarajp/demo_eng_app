from __future__ import annotations

from textwrap import dedent

import streamlit as st
import streamlit.components.v1 as components

from core.theme import apply_theme
from core.utils import format_number, format_ratio

from .formulas import calculate_full_design_results
from .report_builder import build_full_report_overview_data, build_full_report_print_css, build_full_report_sections
from .visualization import (
    PhiFlexureChartState,
    beam_section_specs,
    build_beam_section_svg,
    build_flexural_phi_chart_svg,
    build_section_rebar_details,
    shared_drawing_transform,
)
from .workspace_page import (
    LAST_RENDERED_PAGE_KEY,
    _build_shear_torsion_interaction_diagram_html,
    build_inputs_from_state,
    initialize_session_state,
    load_default_inputs,
)


def main() -> None:
    initialize_session_state(load_default_inputs())
    st.session_state[LAST_RENDERED_PAGE_KEY] = "report_full"
    palette = apply_theme()
    st.markdown(build_full_report_print_css(palette), unsafe_allow_html=True)

    inputs = st.session_state.get("current_design_inputs")
    results = st.session_state.get("current_design_results")
    if inputs is None or results is None:
        try:
            inputs = build_inputs_from_state()
            results = calculate_full_design_results(inputs)
        except ValueError as error:
            st.error(str(error))
            st.info("Return to the workspace page and correct the invalid input combination before opening the full report.")
            return

    sections = build_full_report_sections(inputs, results)
    overview = build_full_report_overview_data(inputs, results)
    report_html = render_full_report_layout(inputs, results, overview, sections, palette)

    st.markdown("<div class='screen-only report-toolbar'>", unsafe_allow_html=True)
    toolbar_left, toolbar_right = st.columns([0.9, 2.1], gap="medium")
    with toolbar_left:
        render_print_button("full-report-root", "Reinforced Concrete Beam Analysis - Full Report", palette)
    with toolbar_right:
        st.markdown("<div class='hero-title'>Reinforced Concrete Beam Analysis</div>", unsafe_allow_html=True)
        st.markdown("<div class='hero-subtitle'>Full Report</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(report_html, unsafe_allow_html=True)


def render_print_button(root_id: str, window_title: str, palette) -> None:
    components.html(
        f"""
        <div style="padding:0;margin:0;">
          <button
            id="{root_id}-print-button"
            type="button"
            onclick="
              const parentDoc = window.parent.document;
              const reportRoot = parentDoc.getElementById('{root_id}');
              if (!reportRoot) {{
                alert('Report sheet not found.');
                return;
              }}
              const styleTags = Array.from(parentDoc.querySelectorAll('style'))
                .map((tag) => tag.outerHTML)
                .join('');
              const printWindow = window.open('', '_blank', 'width=1080,height=1400');
              if (!printWindow) {{
                alert('Please allow popups for printing.');
                return;
              }}
              printWindow.document.open();
              printWindow.document.write(`
                <html>
                  <head>
                    <title>{window_title}</title>
                    ${{styleTags}}
                    <style>
                      html, body {{
                        margin: 0;
                        padding: 0;
                        background: #ffffff;
                      }}
                      body {{
                        display: block;
                      }}
                      .screen-only {{
                        display: none !important;
                      }}
                    </style>
                  </head>
                  <body>${{reportRoot.outerHTML}}</body>
                </html>
              `);
              printWindow.document.close();
              printWindow.focus();
              setTimeout(() => {{
                printWindow.print();
              }}, 250);
            "
            style="
              width:100%;
              min-height:42px;
              border:none;
              border-radius:14px;
              background:linear-gradient(135deg,#1f6fb2,#dcecf8);
              color:#111111;
              font-weight:700;
              cursor:pointer;
              font-family:inherit;
            "
          >
            Print Full Report
          </button>
          <script>
            const rootStyles = window.parent.getComputedStyle(window.parent.document.documentElement);
            const button = document.getElementById('{root_id}-print-button');
            if (button) {{
              const accent = rootStyles.getPropertyValue('--beam-accent').trim() || '#1f6fb2';
              const accentSoft = rootStyles.getPropertyValue('--beam-accent-soft').trim() || '#dcecf8';
              const onAccent = rootStyles.getPropertyValue('--beam-on-accent').trim() || '#111111';
              button.style.background = 'linear-gradient(135deg, ' + accent + ', ' + accentSoft + ')';
              button.style.color = onAccent;
            }}
          </script>
        </div>
        """,
        height=52,
    )


def render_full_report_layout(inputs, results, overview, sections, palette) -> str:
    page_html_parts: list[str] = []
    grouped_sections = _group_sections_for_pages(sections)
    total_pages = len(grouped_sections)

    for page_number, page_sections in enumerate(grouped_sections, start=1):
        if page_number == 1:
            content = _render_cover_page(inputs, results, overview, palette, page_number, total_pages)
        else:
            content = _render_detail_page(inputs, results, page_sections, palette, page_number, total_pages)
        page_html_parts.append(content)

    return _normalize_html(
        dedent(
        f"""
        <div id='full-report-root' class='full-report-root'>{''.join(page_html_parts)}</div>
        """
        )
    )


def _group_sections_for_pages(sections) -> list[list]:
    groups: list[list] = [[]]
    remaining = sections[3:]
    if sections:
        remaining = sections
    while remaining:
        groups.append(remaining[:4])
        remaining = remaining[4:]
    return groups


def _render_cover_page(inputs, results, overview, palette, page_number: int, total_pages: int) -> str:
    figure_specs = beam_section_specs(inputs)
    drawing_transform = shared_drawing_transform(inputs)
    figure_class = "full-report-figures dual" if len(figure_specs) > 1 else "full-report-figures"
    figures_html = "".join(
        _render_figure_block(inputs, results, palette, title, moment_case, drawing_transform, dual=len(figure_specs) > 1)
        for title, moment_case in figure_specs
    )
    check_html = "".join(
        _normalize_html(
            dedent(
            f"""
            <div class="full-report-summary-card">
              <div class="label">{section.title}</div>
              <div class="value" style="font-size:8.4px;line-height:1.45;font-weight:600;">{section.body}</div>
              {f"<ul class='full-report-bullets'>{''.join(f'<li>{item}</li>' for item in section.bullets)}</ul>" if section.bullets else ""}
            </div>
            """
            )
        )
        for section in overview.check_sections
    )
    reinforcement_html = "".join(f"<li>{item}</li>" for item in overview.reinforcement_lines)
    note_html = "".join(f"<li>{item}</li>" for item in overview.governing_notes)
    return _normalize_html(
        dedent(
        f"""
        <div class="full-report-page">
          <div class="full-report-hero">
            <div>
              <h1 class="full-report-title">Reinforced Concrete Beam Analysis</h1>
              <div class="full-report-subtitle">Full Report</div>
              <div class="full-report-lead">
                {overview.member_summary}
              </div>
              <div class="full-report-meta">
                {_meta_item("Project Name", inputs.metadata.project_name or "-")}
                {_meta_item("Project Number", inputs.metadata.project_number or "-")}
                {_meta_item("Tag", inputs.metadata.tag or "-")}
                {_meta_item("Engineer", inputs.metadata.engineer or "-")}
                {_meta_item("Date", inputs.metadata.design_date or "-")}
                {_meta_item("Code", inputs.metadata.design_code.value)}
                {_meta_item("Beam Type", inputs.beam_type.value)}
                {
                    _meta_item("Include Cantilever Span", "Yes" if inputs.include_cantilever_span else "No")
                    if inputs.beam_type.value in {"Simple Beam", "Continuous Beam"}
                    else ""
                }
                {_meta_item("Sections", ", ".join(label for _, label in inputs.active_flexural_sections))}
                {_meta_item("Overall Status", results.overall_status)}
              </div>
            </div>
            <div class="{figure_class}">
              {figures_html}
            </div>
          </div>
          <div class="full-report-section">
            <div class="full-report-section-title">Design Actions</div>
            <div class="full-report-section-intro">{overview.design_actions}</div>
          </div>
          <div class="full-report-summary">
            {check_html}
          </div>
          <div class="full-report-section">
            <div class="full-report-section-title">Reinforcement Summary</div>
            <ul class="full-report-bullets">{reinforcement_html}</ul>
          </div>
          {f"<div class='full-report-section'><div class='full-report-section-title'>Governing Notes</div><ul class='full-report-bullets'>{note_html}</ul></div>" if overview.governing_notes else ""}
          <div class="full-report-section">
            <div class="full-report-section-title">Conclusion</div>
            <div class="full-report-section-intro">{overview.conclusion}</div>
          </div>
        </div>
        """
        )
    )


def _render_detail_page(inputs, results, sections, palette, page_number: int, total_pages: int) -> str:
    section_html = "".join(_render_full_section(section, inputs, results, palette) for section in sections)
    return _normalize_html(
        dedent(
        f"""
        <div class="full-report-page">
          {section_html}
        </div>
        """
        )
    )


def _render_figure_block(inputs, results, palette, title: str, moment_case: str, drawing_transform, *, dual: bool) -> str:
    stirrup_spacing_cm = results.combined_shear_torsion.stirrup_spacing_cm if results.combined_shear_torsion.active else results.shear.provided_spacing_cm
    details = build_section_rebar_details(inputs, moment_case, stirrup_spacing_cm)
    rebar_parts: list[str] = []
    if _has_rebar_lines(details.top_lines):
        rebar_parts.append(f"<strong>Top:</strong> {'<br>'.join(details.top_lines)}")
    if _has_rebar_lines(details.bottom_lines):
        rebar_parts.append(f"<strong>Bottom:</strong> {'<br>'.join(details.bottom_lines)}")
    rebar_parts.append(f"<strong>Stirrup:</strong> {details.stirrup_line}")
    if details.torsion_side_lines:
        rebar_parts.append(f"<strong>Torsion Side:</strong> {'<br>'.join(details.torsion_side_lines)}")
    dual_class = " dual" if dual else ""
    return _normalize_html(
        dedent(
        f"""
        <div class='full-report-figure-block{dual_class}'>
          <div class='full-report-figure-title'>{title} Section</div>
          <div class='full-report-figure'>{build_beam_section_svg(inputs, palette, moment_case, transform=drawing_transform)}</div>
          <div class='full-report-rebar'>{"<br>".join(rebar_parts)}</div>
        </div>
        """
        )
    )


def _render_full_section(section, inputs, results, palette) -> str:
    intro_text = _section_intro_text(section.title)
    if section.title == "Notation":
        return _render_notation_section(section, intro_text)
    rows_html = "".join(
        _render_calculation_step(section.title, row, index)
        for index, row in enumerate(section.rows, start=1)
    )
    layout_class = _section_layout_class(section.title)
    visuals_html = _render_section_visuals(section.title, inputs, results, palette)
    return _normalize_html(
        dedent(
        f"""
        <div class="full-report-section">
          <div class="full-report-section-title">{section.title}</div>
          <div class="full-report-section-intro">{intro_text}</div>
          {f"<div class='full-report-visuals'>{visuals_html}</div>" if visuals_html else ""}
          <div class="full-report-steps {layout_class}">
            {rows_html}
          </div>
        </div>
        """
        )
    )


def _render_notation_section(section, intro_text: str) -> str:
    items_html = "".join(
        _normalize_html(
            dedent(
            f"""
            <div class="full-report-notation-item">
              <div class="full-report-notation-term">{_clean_report_html(row.variable)}</div>
              <div class="full-report-notation-definition">{_clean_report_html(row.substitution).capitalize()}.</div>
              <div class="full-report-notation-unit">Unit: {row.units if row.units != "-" else "Not applicable"}</div>
            </div>
            """
            )
        )
        for row in section.rows
    )
    return _normalize_html(
        dedent(
        f"""
        <div class="full-report-section">
          <div class="full-report-section-title">{section.title}</div>
          <div class="full-report-section-intro">{intro_text}</div>
          <div class="full-report-notation">
            {items_html}
          </div>
        </div>
        """
        )
    )


def _render_section_visuals(section_title: str, inputs, results, palette) -> str:
    if section_title == "Positive Moment Design":
        return build_flexural_phi_chart_svg(
            palette,
            PhiFlexureChartState(
                title="Positive Moment Flexural φ",
                design_code=inputs.metadata.design_code,
                et=results.positive_bending.et,
                ety=results.positive_bending.ety,
                phi=results.positive_bending.phi,
            ),
        )
    if section_title == "Negative Moment Design" and results.negative_bending is not None:
        return build_flexural_phi_chart_svg(
            palette,
            PhiFlexureChartState(
                title="Negative Moment Flexural φ",
                design_code=inputs.metadata.design_code,
                et=results.negative_bending.et,
                ety=results.negative_bending.ety,
                phi=results.negative_bending.phi,
            ),
        )
    if section_title == "Torsion Design" and results.combined_shear_torsion.active:
        return _build_shear_torsion_interaction_diagram_html(results.combined_shear_torsion, palette, results.torsion)
    if section_title == "Deflection Check" and results.deflection.status != "Not considered":
        return _build_report_deflection_diagram_html(results, palette)
    return ""


def _has_rebar_lines(lines: list[str]) -> bool:
    return any(line.strip() and line.strip() != "-" for line in lines)


def _build_report_deflection_diagram_html(results, palette) -> str:
    support_condition = results.deflection.support_condition
    width = 360.0
    height = 148.0
    beam_y = 58.0
    left_x = 34.0
    right_x = 326.0
    span_width = right_x - left_x
    calculated_deflection_cm = float(results.deflection.total_service_deflection_cm)
    allowable_deflection_cm = float(results.deflection.allowable_deflection_cm)
    base_amplitude = 16.0
    if allowable_deflection_cm > 0:
        governing = max(calculated_deflection_cm, allowable_deflection_cm, 1e-9)
        base_amplitude = 10.0 + (22.0 * (calculated_deflection_cm / governing))

    if support_condition == "Continuous 2 spans":
        support_positions = [left_x, left_x + (span_width / 2.0), right_x]
        highlight_positions = [left_x + (span_width * 0.25), left_x + (span_width * 0.75)]
        span_amplitudes = [base_amplitude * 0.88, base_amplitude * 0.88]
        note = "Continuous 2 spans: representative span locations govern the displayed check."
    elif support_condition == "Continuous 3 or more spans":
        support_positions = [left_x, left_x + (span_width / 3.0), left_x + (2.0 * span_width / 3.0), right_x]
        highlight_positions = [left_x + (span_width / 2.0)]
        span_amplitudes = [base_amplitude * 0.72, base_amplitude, base_amplitude * 0.72]
        note = "Continuous multi-span case: the interior representative span governs the displayed check."
    else:
        support_positions = [left_x, right_x]
        highlight_positions = [left_x + (span_width / 2.0)]
        span_amplitudes = [base_amplitude]
        note = "Simple beam: maximum deflection is checked at midspan."

    support_markup = "".join(
        f"<polygon points='{support_x - 9:.2f},{beam_y + 21:.2f} {support_x + 9:.2f},{beam_y + 21:.2f} {support_x:.2f},{beam_y + 0.5:.2f}' fill='{palette.text}' stroke='{palette.text}' stroke-width='1.6' />"
        for support_x in support_positions
    )
    span_labels = "".join(
        f"<text x='{(support_positions[index] + support_positions[index + 1]) / 2.0:.2f}' y='{beam_y - 14:.2f}' text-anchor='middle' font-size='9.5' fill='{palette.muted_text}'>Span {index + 1}</text>"
        for index in range(len(support_positions) - 1)
    )
    deflected_shape_segments = [f"M {support_positions[0]:.2f} {beam_y:.2f}"]
    for index, amplitude in enumerate(span_amplitudes):
        start_x = support_positions[index]
        end_x = support_positions[index + 1]
        mid_x = (start_x + end_x) / 2.0
        deflected_shape_segments.append(f"Q {mid_x:.2f} {beam_y + amplitude:.2f}, {end_x:.2f} {beam_y:.2f}")
    deflected_shape_path = " ".join(deflected_shape_segments)
    highlight_markup: list[str] = []
    for index, highlight_x in enumerate(highlight_positions):
        amplitude = span_amplitudes[min(index, len(span_amplitudes) - 1)]
        highlight_y = beam_y + (amplitude / 2.0)
        highlight_markup.append(
            f"<line x1='{highlight_x:.2f}' y1='{beam_y - 18:.2f}' x2='{highlight_x:.2f}' y2='{highlight_y - 7:.2f}' stroke='{palette.fail}' stroke-width='1.2' stroke-dasharray='4 3' />"
            f"<circle cx='{highlight_x:.2f}' cy='{highlight_y:.2f}' r='6.2' fill='none' stroke='{palette.fail}' stroke-width='2' />"
            f"<circle cx='{highlight_x:.2f}' cy='{highlight_y:.2f}' r='2.8' fill='{palette.fail}' />"
            f"<text x='{highlight_x + 8:.2f}' y='{highlight_y - 7:.2f}' font-size='9.2' font-weight='700' fill='{palette.fail}'>&#916;max = {format_number(calculated_deflection_cm)} cm</text>"
        )
    return dedent(
        f"""
        <div class="metric-card" style="margin-top:0.2rem">
          <div class="section-label">Deflection Reference Diagram</div>
          <svg width="100%" viewBox="0 0 {width:.0f} {height:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Deflection reference diagram" style="display:block;max-width:{width:.0f}px;margin:0 auto;height:auto;">
            <rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" rx="14" fill="{palette.surface_alt}" />
            <line x1="{left_x:.2f}" y1="{beam_y:.2f}" x2="{right_x:.2f}" y2="{beam_y:.2f}" stroke="{palette.text}" stroke-width="3.4" stroke-linecap="round" />
            <path d="{deflected_shape_path}" fill="none" stroke="#0b5cab" stroke-width="2.4" stroke-dasharray="6 4" />
            {support_markup}
            {span_labels}
            {''.join(highlight_markup)}
          </svg>
          <div class="metric-note">{note} Total service deflection = {format_number(calculated_deflection_cm)} cm; allowable = {format_number(allowable_deflection_cm)} cm.</div>
        </div>
        """
    ).strip()


def _summary_card(label: str, value: str, unit: str) -> str:
    unit_text = f" {unit}" if unit != "-" else ""
    return _normalize_html(
        dedent(
        f"""
        <div class='full-report-summary-card'>
          <div class='label'>{label}</div>
          <div class='value'>{value}{unit_text}</div>
        </div>
        """
        )
    )


def _meta_item(label: str, value: str) -> str:
    return _normalize_html(
        dedent(
        f"""
        <div class='full-report-meta-item'>
          <div class='full-report-meta-label'>{label}</div>
          <div>{value}</div>
        </div>
        """
        )
    )


def _section_intro_text(title: str) -> str:
    descriptions = {
        "Input Summary": (
            "The following values define the design case and are adopted directly in the calculations."
        ),
        "Notation": (
            "The principal symbols used in this report are summarized below for ease of review."
        ),
        "Material Properties": (
            "Material properties are established before the strength checks are performed."
        ),
        "Section Geometry": (
            "Section properties and effective depths are obtained from the beam dimensions and reinforcement layout."
        ),
        "Positive Moment Design": (
            "Positive flexural strength is evaluated with the bottom bars acting as the tension reinforcement."
        ),
        "Negative Moment Design": (
            "Negative flexural strength is evaluated with the top bars acting as the tension reinforcement."
        ),
        "Reinforcement Spacing Checks": (
            "Clear spacing is reviewed layer by layer to confirm constructability and minimum spacing requirements."
        ),
        "Shear Design": (
            "Shear capacity is obtained from the concrete contribution together with the provided stirrup reinforcement."
        ),
        "Torsion Design": (
            "Torsion is evaluated with the standard thin-walled tube / space-truss method for a rectangular nonprestressed beam."
        ),
        "Warnings": (
            "The following warnings were generated by the design routine and should be reviewed before the result is issued."
        ),
        "Review Notes": (
            "The following notes identify items that still require engineering judgement or manual verification."
        ),
        "Final Design Summary": (
            "The governing design conclusions are summarized below in compact form."
        ),
    }
    return descriptions.get(
        title,
        "This section records the governing calculations and the substituted values used by the program for the current design case.",
    )


def _section_layout_class(title: str) -> str:
    single_column_sections = {"Warnings", "Review Notes", "Notation"}
    return "single-column" if title in single_column_sections else "two-column"


def _render_calculation_step(section_title: str, row, index: int) -> str:
    variable = _clean_report_html(row.variable)
    equation = _clean_report_html(row.equation)
    substitution = _clean_report_html(row.substitution)
    result = _clean_report_html(row.result)
    narrative = _step_narrative(section_title, variable, substitution, result, row.units)
    units_text = f" {row.units}" if row.units != "-" else ""
    note_text = _clean_report_html(" | ".join(part for part in [row.status, row.note] if part))
    show_equation = _has_meaningful_equation(equation)
    show_substitution = _has_meaningful_equation(substitution)
    compact = _should_render_compact_step(section_title, show_equation, show_substitution)
    note_block = (
        _normalize_html(
            dedent(
            f"""
            <div class='full-report-note-block'>
              <div class='full-report-block-label'>Status / Note</div>
              <div class='full-report-block-value'>{note_text}</div>
            </div>
            """
            )
        )
        if note_text
        else ""
    )
    equation_block = (
        _normalize_html(
            dedent(
            f"""
            <div class="full-report-equation-block">
              <div class="full-report-block-label">Equation</div>
              <div class="full-report-block-value">{equation}</div>
            </div>
            """
            )
        )
        if show_equation
        else ""
    )
    substitution_block = (
        _normalize_html(
            dedent(
            f"""
            <div class="full-report-substitution-block">
              <div class="full-report-block-label">Substitution</div>
              <div class="full-report-block-value">{substitution}</div>
            </div>
            """
            )
        )
        if show_substitution
        else ""
    )
    if compact:
        return _normalize_html(
            dedent(
            f"""
            <div class="full-report-step compact">
              <div class="full-report-step-header">
                <div class="full-report-step-number">Step {index:02d}</div>
                <div class="full-report-step-title">{variable}</div>
              </div>
              <div class="full-report-step-text">{narrative}</div>
              {note_block}
            </div>
            """
            )
        )
    return _normalize_html(
        dedent(
        f"""
        <div class="full-report-step">
          <div class="full-report-step-header">
            <div class="full-report-step-number">Step {index:02d}</div>
            <div class="full-report-step-title">{variable}</div>
          </div>
          <div class="full-report-step-text">{narrative}</div>
          {equation_block}
          {substitution_block}
          <div class="full-report-result-block">
            <div class="full-report-block-label">Result</div>
            <div class="full-report-block-value">{result}{units_text}</div>
          </div>
          {note_block}
        </div>
        """
        )
    )


def _step_narrative(section_title: str, variable: str, substitution: str, result: str, units: str) -> str:
    units_text = _unit_suffix(units)
    if section_title == "Input Summary":
        if variable == "Design code":
            return f"The design check is carried out in accordance with {substitution}."
        return f"{substitution}."
    if section_title == "Notation":
        unit_note = f" The unit used in this report is {units}." if units != "-" else ""
        return f"In this report, {variable} denotes {substitution}.{unit_note}"
    if section_title == "Material Properties":
        if _has_meaningful_equation(substitution):
            return f"The value of {variable} is established from the governing material relationship."
        return f"The value adopted for {variable} is {result}{units_text}."
    if section_title == "Section Geometry":
        if _has_meaningful_equation(substitution):
            return f"The section property {variable} is obtained from the section dimensions as shown below."
        return f"The geometric quantity adopted for {variable} is {substitution}."
    if section_title == "Positive Moment Design":
        if not _has_meaningful_equation(substitution):
            return f"For the positive-moment check, {variable.lower()} is taken as {substitution}."
        return f"The positive-moment check is carried out for {variable} as shown below."
    if section_title == "Negative Moment Design":
        if not _has_meaningful_equation(substitution):
            return f"For the negative-moment check, {variable.lower()} is taken as {substitution}."
        return f"The negative-moment check is carried out for {variable} as shown below."
    if section_title == "Reinforcement Spacing Checks":
        return f"For {variable.lower()}, {substitution}. The check result is {result}."
    if section_title == "Shear Design":
        if not _has_meaningful_equation(substitution):
            return f"In the shear design, {variable.lower()} is taken as {substitution}."
        return f"The shear-design quantity {variable} is evaluated as shown below."
    if section_title == "Torsion Design":
        if not _has_meaningful_equation(substitution):
            return f"In the torsion design, {variable.lower()} is taken as {substitution}."
        return f"The torsion-design quantity {variable} is evaluated as shown below."
    if section_title == "Warnings":
        return result if result.endswith(".") else f"{result}."
    if section_title == "Review Notes":
        return substitution if substitution.endswith(".") else f"{substitution}."
    if section_title == "Final Design Summary":
        if variable == "Overall design status":
            return f"The governing outcome of the present design check is {result}."
        if variable.startswith("Positive flexure"):
            return f"The positive-flexure demand ratio is {substitution}, which leads to a design status of {result}."
        if variable.startswith("Negative flexure"):
            return f"The negative-flexure demand ratio is {substitution}, which leads to a design status of {result}."
        if variable.startswith("Shear"):
            return f"The shear-demand ratio is {substitution}, which leads to a design status of {result}."
        if variable in {"Warnings", "Review notes"}:
            return result if result.endswith(".") else f"{result}."
        return f"{substitution}."
    return f"The reported value for {variable} is {result}{units_text}."


def _unit_suffix(units: str) -> str:
    return "" if units == "-" else f" {units}"


def _has_meaningful_equation(value: str) -> bool:
    normalized = value.strip()
    if not normalized or normalized == "-":
        return False
    if len(normalized) < 3:
        return False
    markers = ("=", "&radic;", "sqrt", "/", "*", "+", "&times;", "min", "max", "&phi;", "&rho;", "&epsilon;", "&beta;")
    return any(marker in normalized for marker in markers)


def _should_render_compact_step(section_title: str, show_equation: bool, show_substitution: bool) -> bool:
    compact_sections = {"Input Summary", "Notation", "Warnings", "Review Notes", "Final Design Summary", "Reinforcement Spacing Checks"}
    if section_title in compact_sections:
        return True
    return not show_equation and not show_substitution


def _clean_report_html(value: str) -> str:
    return (
        value.replace("dâ€²", "d&#8242;")
        .replace("Ã—", "&times;")
        .replace("Ï†", "&phi;")
        .replace("Φ", "&phi;")
        .replace("phiMn", "&phi;M<sub>n</sub>")
        .replace("phiVn", "&phi;V<sub>n</sub>")
        .replace("phiVc", "&phi;V<sub>c</sub>")
        .replace("phiVs", "&phi;V<sub>s</sub>")
        .replace("PhiMn", "&phi;M<sub>n</sub>")
        .replace("PhiVn", "&phi;V<sub>n</sub>")
        .replace(" x ", " &times; ")
    )


def _normalize_html(value: str) -> str:
    return "\n".join(line.lstrip() for line in value.strip().splitlines())
