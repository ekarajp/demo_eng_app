from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from core.theme import apply_theme

from .formulas import calculate_full_design_results
from .report_builder import build_report_print_css, build_summary_table_sections
from .visualization import beam_section_specs, build_beam_section_svg, build_section_rebar_details, shared_drawing_transform
from .workspace_page import LAST_RENDERED_PAGE_KEY, build_inputs_from_state, initialize_session_state, load_default_inputs


def main() -> None:
    initialize_session_state(load_default_inputs())
    st.session_state[LAST_RENDERED_PAGE_KEY] = "report_summary"
    palette = apply_theme()
    st.markdown(build_report_print_css(palette), unsafe_allow_html=True)

    inputs = st.session_state.get("current_design_inputs")
    results = st.session_state.get("current_design_results")
    if inputs is None or results is None:
        try:
            inputs = build_inputs_from_state()
            results = calculate_full_design_results(inputs)
        except ValueError as error:
            st.error(str(error))
            st.info("Return to the workspace page and correct the invalid input combination before opening the report.")
            return

    sections = build_summary_table_sections(inputs, results)
    report_html = render_print_layout(inputs, results, sections, palette)

    st.markdown("<div class='screen-only report-toolbar'>", unsafe_allow_html=True)
    toolbar_left, toolbar_right = st.columns([0.9, 2.1], gap="medium")
    with toolbar_left:
        render_print_button(palette)
    with toolbar_right:
        st.markdown("<div class='hero-title'>Reinforced Concrete Beam Analysis</div>", unsafe_allow_html=True)
        st.markdown("<div class='hero-subtitle'>Summary Report</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(report_html, unsafe_allow_html=True)


def render_print_button(palette) -> None:
    components.html(
        f"""
        <div style="padding:0;margin:0;">
          <button
            id="print-report-button"
            type="button"
            onclick="
              const parentDoc = window.parent.document;
              const reportRoot = parentDoc.getElementById('print-report-root');
              if (!reportRoot) {{
                alert('Report sheet not found.');
                return;
              }}
              const styleTags = Array.from(parentDoc.querySelectorAll('style'))
                .map((tag) => tag.outerHTML)
                .join('');
              const printWindow = window.open('', '_blank', 'width=980,height=1280');
              if (!printWindow) {{
                alert('Please allow popups for printing.');
                return;
              }}
              printWindow.document.open();
              printWindow.document.write(`
                <html>
                  <head>
                    <title>Reinforced Concrete Beam Analysis</title>
                    ${{styleTags}}
                    <style>
                      html, body {{
                        margin: 0;
                        padding: 0;
                        background: #ffffff;
                      }}
                      body {{
                        display: flex;
                        justify-content: center;
                        align-items: flex-start;
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
            Print Report
          </button>
          <script>
            const rootStyles = window.parent.getComputedStyle(window.parent.document.documentElement);
            const button = document.getElementById('print-report-button');
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


def render_print_layout(inputs, results, sections, palette) -> str:
    drawing_specs = beam_section_specs(inputs)
    drawing_transform = shared_drawing_transform(inputs)
    drawings_html = "".join(
        _render_print_drawing_block(inputs, results, palette, title, moment_case, drawing_transform)
        for title, moment_case in drawing_specs
    )
    drawing_stack_class = "print-drawing-stack dual" if len(drawing_specs) > 1 else "print-drawing-stack single"
    section_html = "".join(_render_print_table_section(section) for section in sections)
    header_meta_html = "".join(
        f"<div class='summary-fact'><strong>{label}:</strong> {value}</div>"
        for label, value in [
            ("Project Name", inputs.metadata.project_name or "-"),
            ("Project Number", inputs.metadata.project_number or "-"),
            ("Engineer", inputs.metadata.engineer or "-"),
            ("Date", inputs.metadata.design_date or "-"),
            ("Tag", inputs.metadata.tag or "-"),
        ]
    )
    project_line = inputs.metadata.project_name or inputs.metadata.tag or "Reinforced Concrete Beam"
    meta_html = "".join(
        f"<span>{item}</span>"
        for item in [
            f"Beam Type: {inputs.beam_type.value}",
            *(
                [f"Include Cantilever Span: {'Yes' if inputs.include_cantilever_span else 'No'}"]
                if inputs.beam_type.value in {"Simple Beam", "Continuous Beam"}
                else []
            ),
            f"Sections: {', '.join(label for _, label in inputs.active_flexural_sections)}",
            f"Code: {inputs.metadata.design_code.value}",
            f"Overall Status: {results.overall_status}",
        ]
    )
    return f"""
    <div id="print-report-root">
      <div class="summary-sheet">
      <div class="print-header {'dual-layout' if len(drawing_specs) > 1 else 'single-layout'}">
        <div>
          <h1 class="summary-title">Beam Design Summary</h1>
          <div class="summary-subtitle">{project_line}</div>
          <p class="summary-lead">One-page summary of the governing beam design results, key provided reinforcement, and current design status.</p>
          <div class="summary-fact-grid">{header_meta_html}</div>
          <div class="print-meta">{meta_html}</div>
        </div>
        <div class="{drawing_stack_class}">{drawings_html}</div>
      </div>
      <div class="print-grid">
        {section_html}
      </div>
      </div>
    </div>
    """


def _render_print_table_section(section) -> str:
    table_rows = "".join(_render_print_table_row(row) for row in section.rows)
    return (
        "<div class='print-block'>"
        f"<div class='print-section-title'>{section.title}</div>"
        "<table class='print-table'>"
        "<thead><tr><th>Item</th><th>Key Value</th><th>Result</th><th>Status</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
        "</div>"
    )


def _render_print_table_row(row) -> str:
    detail = row.substitution if row.substitution and row.substitution != "-" else (row.equation if row.equation != "-" else "")
    result = _compact_primary_value(row)
    status_parts = [part for part in [row.status, row.note] if part and part != "-"]
    status_text = " | ".join(status_parts) if status_parts else "-"
    if len(detail) > 42:
        detail = detail[:39].rstrip() + "..."
    if len(status_text) > 32:
        status_text = status_text[:29].rstrip() + "..."
    return (
        "<tr>"
        f"<td>{row.variable}</td>"
        f"<td>{detail or '-'}</td>"
        f"<td>{result}</td>"
        f"<td>{status_text}</td>"
        "</tr>"
    )


def _render_print_drawing_block(inputs, results, palette, title: str, moment_case: str, drawing_transform) -> str:
    details = build_section_rebar_details(inputs, moment_case, results.shear.provided_spacing_cm)
    top_lines = "".join(f"<div class='print-rebar-line'>{line}</div>" for line in details.top_lines)
    bottom_lines = "".join(f"<div class='print-rebar-line'>{line}</div>" for line in details.bottom_lines)
    return (
        "<div>"
        f"<div class='print-section-title'>{title} Section</div>"
        f"<div class='print-figure'>{build_beam_section_svg(inputs, palette, moment_case, transform=drawing_transform)}</div>"
        "<div class='print-rebar-box'>"
        "<div class='print-rebar-row'><span>Top Rebar</span>"
        f"<div>{top_lines}</div></div>"
        "<div class='print-rebar-row'><span>Bottom Rebar</span>"
        f"<div>{bottom_lines}</div></div>"
        "<div class='print-rebar-row'><span>Stirrup</span>"
        f"<div><div class='print-rebar-line'>{details.stirrup_line}</div></div></div>"
        "</div>"
        "</div>"
    )


def _render_print_section(title: str, rows) -> str:
    block_class = _section_block_class(title)
    items_html = "".join(_render_compact_item(row) for row in rows)
    return (
        f"<div class=\"print-block {block_class}\">"
        f"<div class=\"print-section-title\">{title}</div>"
        f"<div class=\"print-compact-grid\">{items_html}</div>"
        "</div>"
    )


def _section_block_class(title: str) -> str:
    mapping = {
        "Input Summary": "print-input-summary-block print-compact-block",
        "Material Properties": "print-material-block print-compact-block",
        "Design Summary": "print-summary-block print-compact-block",
    }
    return mapping.get(title, "print-compact-block")


def _render_compact_item(row) -> str:
    detail_html = _compact_detail_html(row)
    meta_html = _compact_meta_html(row)
    return (
        "<div class=\"print-compact-item\">"
        f"<div class=\"print-compact-label\">{row.variable}</div>"
        f"<div class=\"print-compact-value\">{_compact_primary_value(row)}</div>"
        f"{detail_html}"
        f"{meta_html}"
        "</div>"
    )


def _compact_primary_value(row) -> str:
    unit_text = f" <span class=\"print-compact-unit\">{row.units}</span>" if row.units != "-" else ""
    if row.substitution and row.substitution != "-" and row.substitution != row.result and row.result in {"PASS", "FAIL", "PASS WITH REVIEW", "DOES NOT MEET REQUIREMENTS", "DOES NOT MEET DESIGN REQUIREMENTS"}:
        return row.result
    return f"{row.result}{unit_text}"


def _compact_detail_html(row) -> str:
    detail_text = _compact_detail_text(row)
    if not detail_text:
        return ""
    return f"<div class=\"print-compact-detail\">{detail_text}</div>"


def _compact_detail_text(row) -> str:
    if row.substitution and row.substitution != "-" and row.substitution != row.result:
        return row.substitution
    if row.equation and row.equation != "-":
        return row.equation
    return ""


def _compact_meta_html(row) -> str:
    meta_parts = [part for part in [row.status, row.note] if part and part != "-"]
    if not meta_parts:
        return ""
    return f"<div class=\"print-compact-meta\">{' | '.join(meta_parts)}</div>"
