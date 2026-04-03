from __future__ import annotations

from apps.rc_beam.calculation_report_full_page import render_full_report_layout
from apps.rc_beam.calculation_report_page import _render_print_section, render_print_layout
from apps.rc_beam.formulas import calculate_full_design_results
from apps.rc_beam.models import BeamDesignInputSet, BeamType
from apps.rc_beam.models import ProjectMetadata
from apps.rc_beam.models import NegativeBendingInput, PositiveBendingInput, RebarGroupInput, RebarLayerInput, ReinforcementArrangementInput
from apps.rc_beam.report_builder import (
    ReportRow,
    build_full_report_overview_data,
    build_full_report_sections,
    build_report_print_css,
    build_summary_table_sections,
)
from core.theme import LIGHT_THEME
from design.torsion import TorsionDemandType, TorsionDesignCode, TorsionDesignInput


def test_input_summary_renders_compact_block_without_table() -> None:
    html = _render_print_section(
        "Input Summary",
        [
            ReportRow("Design Code", "-", "ACI318-19", "ACI318-19", "-"),
            ReportRow("Geometry", "b x h, cover", "20.00 x 40.00, c=4.00", "20.00 x 40.00 / 4.00", "cm"),
        ],
    )

    assert "print-input-summary-block" in html
    assert "print-compact-grid" in html
    assert "<table class=\"print-table\">" not in html
    assert ">-<" not in html
    assert "print-compact-item" in html


def test_material_properties_render_compact_block_without_table() -> None:
    html = _render_print_section(
        "Material Properties",
        [
            ReportRow("f'c", "-", "240.00", "240.00", "ksc"),
            ReportRow("Ec", "-", "Default", "233,928.19", "ksc", "Default"),
        ],
    )

    assert "print-material-block" in html
    assert "print-compact-grid" in html
    assert "<table class=\"print-table\">" not in html


def test_summary_report_is_fixed_to_one_a4_page_and_includes_section_figure() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_full_design_results(inputs)
    sections = build_summary_table_sections(inputs, results)

    css = build_report_print_css(LIGHT_THEME)
    html = render_print_layout(inputs, results, sections, LIGHT_THEME)

    assert 'class="summary-sheet"' in html
    assert "<svg" in html
    assert "<table class='print-table'>" in html
    assert "width: 198mm;" in css
    assert "min-height: 284mm;" in css
    assert "max-height: 284mm;" in css
    assert "overflow: hidden;" in css


def test_summary_report_header_includes_project_metadata() -> None:
    inputs = BeamDesignInputSet(
        metadata=ProjectMetadata(
            project_name="Warehouse Beam Check",
            project_number="WB-24-017",
            engineer="A. Engineer",
            design_date="2026-03-30",
            tag="B-12",
        )
    )
    results = calculate_full_design_results(inputs)
    sections = build_summary_table_sections(inputs, results)
    html = render_print_layout(inputs, results, sections, LIGHT_THEME)

    assert "Project Name:</strong> Warehouse Beam Check" in html
    assert "Project Number:</strong> WB-24-017" in html
    assert "Engineer:</strong> A. Engineer" in html
    assert "Date:</strong> 2026-03-30" in html
    assert "Tag:</strong> B-12" in html


def test_summary_report_omits_inactive_modules_and_uses_table_sections() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_full_design_results(inputs)
    sections = build_summary_table_sections(inputs, results)
    html = render_print_layout(inputs, results, sections, LIGHT_THEME)
    titles = [section.title for section in sections]

    assert titles == ["Member Summary", "Flexure", "Shear", "Reinforcement Summary", "Design Summary"]
    assert "Torsion" not in html
    assert "Deflection" not in html
    assert "Negative Flexure" not in html
    assert "PASS" in html


def test_summary_report_includes_only_active_torsion_and_deflection_checks() -> None:
    inputs = BeamDesignInputSet(
        consider_deflection=True,
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=1200.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=8.0,
        ),
    )
    results = calculate_full_design_results(inputs)
    sections = build_summary_table_sections(inputs, results)
    html = render_print_layout(inputs, results, sections, LIGHT_THEME)
    titles = [section.title for section in sections]

    assert titles == ["Member Summary", "Flexure", "Shear", "Torsion", "Deflection", "Reinforcement Summary", "Design Summary"]
    assert "Torsion" in html
    assert "Deflection" in html
    assert "Negative Flexure" not in html
    assert "DB9" in html or "RB9" in html


def test_full_report_includes_cover_figure_and_only_active_sections_for_simple_beam() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_full_design_results(inputs)
    sections = build_full_report_sections(inputs, results)
    overview = build_full_report_overview_data(inputs, results)
    html = render_full_report_layout(inputs, results, overview, sections, LIGHT_THEME)
    titles = [section.title for section in sections]

    assert "<svg" in html
    assert "Full Report" in html
    assert "Design Actions" in html
    assert "Reinforcement Summary" in html
    assert "Torsion Design" not in html
    assert "Deflection Check" not in html
    assert "Negative Moment Design" not in html
    assert "Final Design Summary" not in titles


def test_full_report_adds_torsion_and_deflection_sections_only_when_enabled() -> None:
    inputs = BeamDesignInputSet(
        consider_deflection=True,
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=1200.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=8.0,
        ),
    )
    results = calculate_full_design_results(inputs)
    sections = build_full_report_sections(inputs, results)
    overview = build_full_report_overview_data(inputs, results)
    html = render_full_report_layout(inputs, results, overview, sections, LIGHT_THEME)
    titles = [section.title for section in sections]

    assert "Torsion Design" in titles
    assert "Deflection Check" in titles
    assert "Negative Moment Design" not in titles
    assert "Torsion Design" in html
    assert "Deflection Check" in html
    assert "Middle Moment Design" in html
    assert "Support Moment Design" in html
    assert "Shear-Torsion interaction diagram" in html
    assert "Deflection reference diagram" in html


def test_full_report_includes_negative_section_only_for_continuous_beam() -> None:
    inputs = BeamDesignInputSet(beam_type=BeamType.CONTINUOUS)
    results = calculate_full_design_results(inputs)
    sections = build_full_report_sections(inputs, results)
    overview = build_full_report_overview_data(inputs, results)
    html = render_full_report_layout(inputs, results, overview, sections, LIGHT_THEME)
    titles = [section.title for section in sections]

    assert "Negative Moment Design" in titles
    assert "Support section" in html
    assert "aria-label=\"Negative Moment Flexural" in html


def test_summary_report_header_includes_cantilever_metadata_for_simple_beam_option() -> None:
    inputs = BeamDesignInputSet(beam_type=BeamType.SIMPLE, include_cantilever_span=True)
    results = calculate_full_design_results(inputs)
    sections = build_summary_table_sections(inputs, results)
    html = render_print_layout(inputs, results, sections, LIGHT_THEME)

    assert "Include Cantilever Span: Yes" in html
    assert "Sections: Middle Section, Support Section, Cantilever Negative Section" in html


def test_full_report_includes_cantilever_section_when_enabled() -> None:
    inputs = BeamDesignInputSet(beam_type=BeamType.CONTINUOUS, include_cantilever_span=True)
    results = calculate_full_design_results(inputs)
    sections = build_full_report_sections(inputs, results)
    overview = build_full_report_overview_data(inputs, results)
    html = render_full_report_layout(inputs, results, overview, sections, LIGHT_THEME)
    titles = [section.title for section in sections]

    assert "Cantilever Negative Moment Design" in titles
    assert "Include Cantilever Span" in html
    assert "Sections" in html
    assert "Cantilever Negative Section" in html


def test_full_report_uses_cantilever_negative_labels_for_standalone_cantilever() -> None:
    inputs = BeamDesignInputSet(beam_type=BeamType.STANDALONE_CANTILEVER)
    results = calculate_full_design_results(inputs)
    sections = build_full_report_sections(inputs, results)
    overview = build_full_report_overview_data(inputs, results)
    html = render_full_report_layout(inputs, results, overview, sections, LIGHT_THEME)
    titles = [section.title for section in sections]
    shear_section = next(section for section in sections if section.title == "Shear Design")

    assert "Positive Moment Design" not in titles
    assert "Cantilever Negative Moment Design" in titles
    assert "Cantilever Negative Section" in html
    assert any(row.variable == "Section basis" and row.result == "Cantilever Negative Section" for row in shear_section.rows)


def test_summary_report_exposes_shear_basis_for_negative_governed_case() -> None:
    inputs = BeamDesignInputSet(
        beam_type=BeamType.CONTINUOUS,
        negative_bending=NegativeBendingInput(
            tension_reinforcement=ReinforcementArrangementInput(
                layer_1=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=25, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=3),
                ),
                layer_2=RebarLayerInput(
                    group_a=RebarGroupInput(diameter_mm=25, count=2),
                    group_b=RebarGroupInput(diameter_mm=25, count=2),
                ),
            ),
        ),
    )
    results = calculate_full_design_results(inputs)
    sections = build_summary_table_sections(inputs, results)
    shear_section = next(section for section in sections if section.title == "Shear")

    assert any(row.variable == "Basis" and row.result == "Negative Section" for row in shear_section.rows)


def test_full_report_hides_empty_reinforcement_faces_in_section_detail() -> None:
    inputs = BeamDesignInputSet(
        positive_bending=PositiveBendingInput(
            compression_reinforcement=ReinforcementArrangementInput(),
            tension_reinforcement=BeamDesignInputSet().positive_bending.tension_reinforcement,
        )
    )
    results = calculate_full_design_results(inputs)
    sections = build_full_report_sections(inputs, results)
    overview = build_full_report_overview_data(inputs, results)
    html = render_full_report_layout(inputs, results, overview, sections, LIGHT_THEME)

    assert "<strong>Top:</strong> -" not in html


def test_full_report_spacing_section_skips_empty_layers() -> None:
    inputs = BeamDesignInputSet(
        positive_bending=PositiveBendingInput(
            compression_reinforcement=ReinforcementArrangementInput(),
            tension_reinforcement=BeamDesignInputSet().positive_bending.tension_reinforcement,
        )
    )
    results = calculate_full_design_results(inputs)
    spacing_section = next(section for section in build_full_report_sections(inputs, results) if section.title == "Reinforcement Spacing Checks")
    variables = [row.variable for row in spacing_section.rows]

    assert "Positive Compression Reinforcement L1" not in variables
    assert "Positive Compression Reinforcement L2" not in variables
    assert "Positive Compression Reinforcement L3" not in variables
