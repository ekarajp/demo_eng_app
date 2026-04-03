import pytest

from apps.rc_beam.formulas import calculate_full_design_results
from apps.rc_beam.models import BeamDesignInputSet
from apps.rc_beam.report_builder import build_report_sections
from design.torsion import (
    TorsionDemandType,
    TorsionDesignCode,
    TorsionDesignInput,
    TorsionDesignMaterialInput,
    TorsionSectionGeometryInput,
    calculate_torsion_design,
)
from design.torsion.torsion_base import ACI_318_19_ALT_PROCEDURE_MESSAGE
from design.torsion.torsion_units import kgf_m_to_n_mm, ksc_to_mpa, n_mm_to_kgf_m


def test_torsion_checkbox_off_keeps_old_sections_unchanged() -> None:
    inputs = BeamDesignInputSet()

    results = calculate_full_design_results(inputs)
    sections = build_report_sections(inputs, results)

    assert results.torsion.status == "DISABLED"
    assert [section.title for section in sections] == [
        "Input Summary",
        "Material Properties",
        "Section Geometry",
        "Middle Moment Design",
        "Shear Design",
        "Final Design Summary",
    ]


def test_torsion_checkbox_on_adds_torsion_section_after_shear() -> None:
    inputs = BeamDesignInputSet(
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=1200.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=8.0,
        )
    )

    results = calculate_full_design_results(inputs)
    sections = build_report_sections(inputs, results)
    titles = [section.title for section in sections]

    assert "Torsion Design" in titles
    assert titles[titles.index("Shear Design") + 1] == "Torsion Design"


def test_torsion_below_threshold_reverts_to_shear_only_summary_behavior() -> None:
    inputs = BeamDesignInputSet(
        torsion=TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=1.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=0.0,
        )
    )

    results = calculate_full_design_results(inputs)

    assert results.combined_shear_torsion.active is False
    assert results.combined_shear_torsion.torsion_ignored is True
    assert "torsion may be ignored" in results.combined_shear_torsion.ignore_message


@pytest.mark.parametrize(
    "design_code",
    [
        TorsionDesignCode.ACI318_99,
        TorsionDesignCode.ACI318_08,
        TorsionDesignCode.ACI318_11,
        TorsionDesignCode.ACI318_14,
        TorsionDesignCode.ACI318_19,
        TorsionDesignCode.ACI318_25,
    ],
)
def test_each_aci_torsion_version_runs_independently(design_code: TorsionDesignCode) -> None:
    results = calculate_torsion_design(
        TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=1200.0,
            design_code=design_code,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=8.0,
        ),
        TorsionSectionGeometryInput(
            width_cm=30.0,
            depth_cm=50.0,
            cover_cm=4.0,
            stirrup_diameter_mm=9,
            stirrup_spacing_cm=15.0,
            stirrup_legs=2,
        ),
        TorsionDesignMaterialInput(
            concrete_strength_ksc=240.0,
            transverse_steel_yield_ksc=2400.0,
            longitudinal_steel_yield_ksc=4000.0,
        ),
    )

    assert results.code_version == design_code.value
    assert results.enabled is True
    assert results.steps


def test_torsion_unit_conversion_round_trips_kgf_m() -> None:
    moment_kgfm = 12.5
    moment_nmm = kgf_m_to_n_mm(moment_kgfm)

    assert moment_nmm == pytest.approx(12.5 * 9.80665 * 1000.0)
    assert n_mm_to_kgf_m(moment_nmm) == pytest.approx(moment_kgfm)
    assert ksc_to_mpa(240.0) == pytest.approx(23.53596)


def test_torsion_bar_input_resolves_provided_al_area() -> None:
    design_input = TorsionDesignInput(
        enabled=True,
        factored_torsion_kgfm=1200.0,
        design_code=TorsionDesignCode.ACI318_19,
        demand_type=TorsionDemandType.EQUILIBRIUM,
        provided_longitudinal_bar_diameter_mm=16,
        provided_longitudinal_bar_count=4,
        provided_longitudinal_bar_fy_ksc=4000.0,
    )

    assert design_input.resolved_provided_longitudinal_steel_cm2 == pytest.approx(8.042477193189871)


def test_aci318_19_alt_procedure_warning_triggers_for_h_over_bt_ge_3() -> None:
    results = calculate_torsion_design(
        TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=1200.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=8.0,
        ),
        TorsionSectionGeometryInput(
            width_cm=20.0,
            depth_cm=70.0,
            cover_cm=4.0,
            stirrup_diameter_mm=9,
            stirrup_spacing_cm=15.0,
            stirrup_legs=2,
        ),
        TorsionDesignMaterialInput(
            concrete_strength_ksc=240.0,
            transverse_steel_yield_ksc=2400.0,
            longitudinal_steel_yield_ksc=4000.0,
        ),
    )

    assert results.alternative_procedure_allowed is True
    assert ACI_318_19_ALT_PROCEDURE_MESSAGE in results.warnings


def test_aci318_25_alt_procedure_warning_triggers_for_h_over_bt_ge_3() -> None:
    results = calculate_torsion_design(
        TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=1200.0,
            design_code=TorsionDesignCode.ACI318_25,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=8.0,
        ),
        TorsionSectionGeometryInput(
            width_cm=20.0,
            depth_cm=70.0,
            cover_cm=4.0,
            stirrup_diameter_mm=9,
            stirrup_spacing_cm=15.0,
            stirrup_legs=2,
        ),
        TorsionDesignMaterialInput(
            concrete_strength_ksc=240.0,
            transverse_steel_yield_ksc=2400.0,
            longitudinal_steel_yield_ksc=4000.0,
        ),
    )

    assert results.alternative_procedure_allowed is True
    assert "ACI 318-25 allows an alternative torsion design procedure" in results.warnings[0]


def test_impossible_geometry_or_negative_inputs_raise_validation_errors() -> None:
    with pytest.raises(ValueError):
        TorsionDesignInput(enabled=True, factored_torsion_kgfm=-1.0)

    with pytest.raises(ValueError):
        calculate_torsion_design(
            TorsionDesignInput(
                enabled=True,
                factored_torsion_kgfm=1000.0,
                provided_longitudinal_steel_cm2=5.0,
            ),
            TorsionSectionGeometryInput(
                width_cm=20.0,
                depth_cm=40.0,
                cover_cm=18.0,
                stirrup_diameter_mm=12,
                stirrup_spacing_cm=15.0,
                stirrup_legs=2,
            ),
            TorsionDesignMaterialInput(
                concrete_strength_ksc=240.0,
                transverse_steel_yield_ksc=2400.0,
                longitudinal_steel_yield_ksc=4000.0,
            ),
        )


def test_insufficient_longitudinal_torsion_steel_is_requirement_issue_not_fail() -> None:
    results = calculate_torsion_design(
        TorsionDesignInput(
            enabled=True,
            factored_torsion_kgfm=1200.0,
            design_code=TorsionDesignCode.ACI318_19,
            demand_type=TorsionDemandType.EQUILIBRIUM,
            provided_longitudinal_steel_cm2=0.5,
        ),
        TorsionSectionGeometryInput(
            width_cm=30.0,
            depth_cm=50.0,
            cover_cm=4.0,
            stirrup_diameter_mm=9,
            stirrup_spacing_cm=15.0,
            stirrup_legs=2,
        ),
        TorsionDesignMaterialInput(
            concrete_strength_ksc=240.0,
            transverse_steel_yield_ksc=2400.0,
            longitudinal_steel_yield_ksc=4000.0,
        ),
    )

    assert results.cross_section_ok is True
    assert results.status == "DOES NOT MEET REQUIREMENTS"
    assert results.pass_fail_summary == (
        "Provided torsion reinforcement does not meet one or more torsion reinforcement requirements."
    )
    assert "Provided longitudinal torsion reinforcement does not meet the required Al." in results.warnings
