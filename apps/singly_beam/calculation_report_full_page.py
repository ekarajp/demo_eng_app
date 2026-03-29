from __future__ import annotations

from textwrap import dedent

import streamlit as st
import streamlit.components.v1 as components

from core.theme import apply_theme
from core.utils import format_number, format_ratio

from .formulas import calculate_full_design_results
from .report_builder import build_full_report_print_css, build_full_report_sections
from .visualization import beam_section_specs, build_beam_section_svg, build_section_rebar_details, shared_drawing_transform
from .workspace_page import LAST_RENDERED_PAGE_KEY, build_inputs_from_state, initialize_session_state, load_default_inputs


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
    report_html = render_full_report_layout(inputs, results, sections, palette)

    st.markdown("<div class='screen-only report-toolbar'>", unsafe_allow_html=True)
    toolbar_left, toolbar_right = st.columns([0.9, 2.1], gap="medium")
    with toolbar_left:
        render_print_button("full-report-root", "Singly Reinforced Beam Analysis - Full Report", palette)
    with toolbar_right:
        st.markdown("<div class='hero-title'>Singly Reinforced Beam Analysis</div>", unsafe_allow_html=True)
        st.markdown("<div class='hero-subtitle'>Calculation Report (Full)</div>", unsafe_allow_html=True)
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


def render_full_report_layout(inputs, results, sections, palette) -> str:
    page_html_parts: list[str] = []
    grouped_sections = _group_sections_for_pages(sections)
    total_pages = len(grouped_sections)

    for page_number, page_sections in enumerate(grouped_sections, start=1):
        if page_number == 1:
            content = _render_cover_page(inputs, results, palette, page_sections, page_number, total_pages)
        else:
            content = _render_detail_page(page_sections, page_number, total_pages)
        page_html_parts.append(content)

    return _normalize_html(
        dedent(
        f"""
        <div id='full-report-root' class='full-report-root'>{''.join(page_html_parts)}</div>
        """
        )
    )


def _group_sections_for_pages(sections) -> list[list]:
    if not sections:
        return [[]]
    groups: list[list] = [sections[:3]]
    remaining = sections[3:]
    while remaining:
        groups.append(remaining[:4])
        remaining = remaining[4:]
    return groups


def _render_cover_page(inputs, results, palette, sections, page_number: int, total_pages: int) -> str:
    figure_specs = beam_section_specs(inputs)
    drawing_transform = shared_drawing_transform(inputs)
    figure_class = "full-report-figures dual" if len(figure_specs) > 1 else "full-report-figures"
    figures_html = "".join(
        _render_figure_block(inputs, results, palette, title, moment_case, drawing_transform, dual=len(figure_specs) > 1)
        for title, moment_case in figure_specs
    )
    section_html = "".join(_render_full_section(section) for section in sections)
    return _normalize_html(
        dedent(
        f"""
        <div class="full-report-page">
          <div class="full-report-hero">
            <div>
              <h1 class="full-report-title">Singly Reinforced Beam Analysis</h1>
              <div class="full-report-subtitle">Calculation Report (Full)</div>
              <div class="full-report-lead">
                This report presents the reinforced concrete beam design check for the selected member using the
                current application inputs. The calculations are arranged in the conventional order used in
                engineering submissions: input definition, material properties, section geometry, flexural design,
                shear design, and final review remarks. Values shown below are the governing numerical substitutions
                used by the program for this design run.
              </div>
              <div class="full-report-meta">
                {_meta_item("Project Name", inputs.metadata.project_name or "-")}
                {_meta_item("Project Number", inputs.metadata.project_number or "-")}
                {_meta_item("Tag", inputs.metadata.tag or "-")}
                {_meta_item("Engineer", inputs.metadata.engineer or "-")}
                {_meta_item("Date", inputs.metadata.design_date or "-")}
                {_meta_item("Code", inputs.metadata.design_code.value)}
                {_meta_item("Beam Type", inputs.beam_type.value)}
                {_meta_item("Overall Status", results.overall_status)}
              </div>
            </div>
            <div class="{figure_class}">
              {figures_html}
            </div>
          </div>
          <div class="full-report-summary">
            {_summary_card("As req.", format_number(results.positive_bending.as_required_cm2), "cm2")}
            {_summary_card("phiMn", format_number(results.positive_bending.phi_mn_kgm), "kg-m")}
            {_summary_card("PhiVn", format_number(results.shear.phi_vn_kg), "kg")}
            {_summary_card("Ratios", f"M {format_ratio(results.positive_bending.ratio)} / V {format_ratio(results.shear.capacity_ratio)}", "-")}
          </div>
          {section_html}
        </div>
        """
        )
    )


def _render_detail_page(sections, page_number: int, total_pages: int) -> str:
    section_html = "".join(_render_full_section(section) for section in sections)
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
    details = build_section_rebar_details(inputs, moment_case, results.shear.provided_spacing_cm)
    top_lines = "<br>".join(details.top_lines)
    bottom_lines = "<br>".join(details.bottom_lines)
    dual_class = " dual" if dual else ""
    return _normalize_html(
        dedent(
        f"""
        <div class='full-report-figure-block{dual_class}'>
          <div class='full-report-figure-title'>{title} Section</div>
          <div class='full-report-figure'>{build_beam_section_svg(inputs, palette, moment_case, transform=drawing_transform)}</div>
          <div class='full-report-rebar'><strong>Top:</strong> {top_lines}<br>
          <strong>Bottom:</strong> {bottom_lines}<br>
          <strong>Stirrup:</strong> {details.stirrup_line}</div>
        </div>
        """
        )
    )


def _render_full_section(section) -> str:
    intro_text = _section_intro_text(section.title)
    if section.title == "Notation":
        return _render_notation_section(section, intro_text)
    rows_html = "".join(
        _render_calculation_step(section.title, row, index)
        for index, row in enumerate(section.rows, start=1)
    )
    layout_class = _section_layout_class(section.title)
    return _normalize_html(
        dedent(
        f"""
        <div class="full-report-section">
          <div class="full-report-section-title">{section.title}</div>
          <div class="full-report-section-intro">{intro_text}</div>
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
        .replace(" x ", " &times; ")
    )


def _normalize_html(value: str) -> str:
    return "\n".join(line.lstrip() for line in value.strip().splitlines())
