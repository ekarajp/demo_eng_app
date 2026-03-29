from __future__ import annotations

from apps.singly_beam.calculation_report_page import _render_print_section
from apps.singly_beam.formulas import calculate_full_design_results
from apps.singly_beam.models import BeamDesignInputSet
from apps.singly_beam.report_builder import build_print_report_sections
from apps.singly_beam.report_builder import ReportRow


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


def test_print_report_input_summary_includes_mu_and_vu() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_full_design_results(inputs)

    sections = build_print_report_sections(inputs, results)
    input_summary = next(section for section in sections if section.title == "Input Summary")

    variables = [row.variable for row in input_summary.rows]
    assert "Mu" in variables
    assert "Vu" in variables


def test_print_report_includes_design_summary_section() -> None:
    inputs = BeamDesignInputSet()
    results = calculate_full_design_results(inputs)

    sections = build_print_report_sections(inputs, results)
    design_summary = next(section for section in sections if section.title == "Design Summary")

    variables = [row.variable for row in design_summary.rows]
    assert "Overall Status" in variables
    assert "Positive Flexure" in variables
    assert "Shear" in variables
