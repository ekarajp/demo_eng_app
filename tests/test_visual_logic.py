from apps.singly_beam.models import BeamDesignInputSet, RebarGroupInput, RebarLayerInput
from apps.singly_beam.visualization import STIRRUP_DRAWING_COLOR, build_beam_section_svg, build_section_rebar_details, compute_bar_points, ordered_layer_bars
from core.theme import LIGHT_THEME


def test_positive_bottom_bars_stay_inside_cover_zone() -> None:
    inputs = BeamDesignInputSet()
    bars = compute_bar_points(inputs, inputs.positive_bending.tension_reinforcement, face="bottom")

    assert bars
    clear_face = inputs.geometry.cover_cm + inputs.shear.stirrup_diameter_mm / 10
    assert all(bar.x_cm >= clear_face for bar in bars)
    assert all(bar.x_cm <= inputs.geometry.width_cm - clear_face for bar in bars)
    assert all(bar.y_cm <= inputs.geometry.depth_cm - clear_face for bar in bars)


def test_negative_top_bars_are_ordered_left_to_right() -> None:
    inputs = BeamDesignInputSet()
    bars = compute_bar_points(inputs, inputs.negative_bending.tension_reinforcement, face="top")

    assert bars == sorted(bars, key=lambda bar: bar.x_cm)


def test_three_layer_capacity_is_supported() -> None:
    inputs = BeamDesignInputSet()
    inputs.positive_bending.tension_reinforcement.layer_2.group_a.diameter_mm = 16
    inputs.positive_bending.tension_reinforcement.layer_2.group_a.count = 2
    inputs.positive_bending.tension_reinforcement.layer_3.group_a.diameter_mm = 12
    inputs.positive_bending.tension_reinforcement.layer_3.group_a.count = 2

    bars = compute_bar_points(inputs, inputs.positive_bending.tension_reinforcement, face="bottom")

    assert max(bar.layer_index for bar in bars) == 3


def test_layer_bar_order_places_corner_bars_outside_and_middle_bar_at_center() -> None:
    layer = RebarLayerInput(
        group_a=RebarGroupInput(diameter_mm=20, count=2),
        group_b=RebarGroupInput(diameter_mm=16, count=1),
    )

    ordered = ordered_layer_bars(layer)

    assert [diameter for diameter, _ in ordered] == [20, 16, 20]
    assert [group for _, group in ordered] == ["Corner", "Middle", "Corner"]


def test_layer_bar_order_places_middle_bars_between_corners() -> None:
    layer = RebarLayerInput(
        group_a=RebarGroupInput(diameter_mm=20, count=2),
        group_b=RebarGroupInput(diameter_mm=16, count=2),
    )

    ordered = ordered_layer_bars(layer)

    assert [diameter for diameter, _ in ordered] == [20, 16, 16, 20]
    assert [group for _, group in ordered] == ["Corner", "Middle", "Middle", "Corner"]


def test_section_rebar_details_show_multiple_layers() -> None:
    inputs = BeamDesignInputSet()
    inputs.positive_bending.tension_reinforcement.layer_2.group_a = RebarGroupInput(diameter_mm=16, count=2)
    inputs.positive_bending.tension_reinforcement.layer_3.group_a = RebarGroupInput(diameter_mm=12, count=2)

    details = build_section_rebar_details(inputs, "positive", stirrup_spacing_cm=16.7)

    assert details.top_lines == ["2DB12"]
    assert details.bottom_lines == ["Layer 1: 2DB12 + 1DB12", "Layer 2: 2DB16", "Layer 3: 2DB12"]
    assert details.stirrup_line == "RB9, 2 legs @ 167 mm"


def test_section_rebar_details_switch_to_rb_for_2400_grade() -> None:
    inputs = BeamDesignInputSet()
    inputs.materials.main_steel_yield_ksc = 2400.0
    inputs.materials.shear_steel_yield_ksc = 2400.0

    details = build_section_rebar_details(inputs, "positive", stirrup_spacing_cm=16.7)

    assert details.top_lines == ["2RB12"]
    assert details.bottom_lines == ["2RB12 + 1RB12"]
    assert details.stirrup_line.startswith("RB9")


def test_section_svg_uses_blue_stirrup_line() -> None:
    inputs = BeamDesignInputSet()

    svg = build_beam_section_svg(inputs, LIGHT_THEME, "positive")

    assert f'stroke="{STIRRUP_DRAWING_COLOR}"' in svg
