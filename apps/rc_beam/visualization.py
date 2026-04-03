from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from core.theme import ThemePalette
from core.utils import format_ratio, longitudinal_bar_mark, stirrup_bar_mark

from .formulas import flexural_phi_chart_points, flexural_phi_chart_supported
from .models import BeamDesignInputSet, DesignCode, ReinforcementArrangementInput

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover
    go = None


DRAWING_VIEWPORT_WIDTH = 240.0
DRAWING_VIEWPORT_HEIGHT = 240.0
DRAWING_TARGET_SPAN = 170.0
DRAWING_PADDING = 18.0
MIN_DRAWN_BAR_RADIUS = 2.2
STIRRUP_DRAWING_COLOR = "#2f80ed"


@dataclass(frozen=True, slots=True)
class BarPoint:
    x_cm: float
    y_cm: float
    diameter_mm: int
    layer_index: int
    group_name: str


@dataclass(frozen=True, slots=True)
class SectionRebarDetails:
    top_lines: list[str]
    bottom_lines: list[str]
    stirrup_line: str
    torsion_side_lines: list[str]
    torsion_warning: str = ""


@dataclass(frozen=True, slots=True)
class PhiFlexureChartState:
    title: str
    design_code: DesignCode
    et: float
    ety: float
    phi: float


@dataclass(frozen=True, slots=True)
class TorsionBarLayout:
    points: list[BarPoint]
    detail_lines: list[str]
    warning: str = ""


@dataclass(frozen=True, slots=True)
class _TorsionPerimeterGeometry:
    x_left_cm: float
    x_right_cm: float
    y_top_cm: float
    y_bottom_cm: float


def build_beam_section_visual(
    inputs: BeamDesignInputSet,
    theme: ThemePalette,
    moment_case: str = "positive",
    transform: "DrawingTransform | None" = None,
) -> Any:
    normalized_case = normalize_moment_case(inputs, moment_case)
    if go is None:
        return build_beam_section_svg(inputs, theme, normalized_case, transform=transform)
    return build_beam_section_figure(inputs, theme, normalized_case, transform=transform)


def build_beam_section_figure(
    inputs: BeamDesignInputSet,
    theme: ThemePalette,
    moment_case: str = "positive",
    transform: "DrawingTransform | None" = None,
):
    transform = transform or _drawing_transform(inputs.geometry.width_cm, inputs.geometry.depth_cm)
    top_arrangement, bottom_arrangement = _select_arrangements(inputs, moment_case)
    top_bars = compute_bar_points(inputs, top_arrangement, face="top")
    bottom_bars = compute_bar_points(inputs, bottom_arrangement, face="bottom")
    torsion_layout = compute_torsion_bar_layout(inputs, moment_case)
    figure = go.Figure()
    figure.add_shape(
        type="rect",
        x0=transform.x_offset,
        x1=transform.x_offset + transform.section_width,
        y0=transform.y_offset,
        y1=transform.y_offset + transform.section_depth,
        line=dict(color=theme.text, width=2),
        fillcolor=theme.surface_alt,
    )
    stirrup_offset = (inputs.geometry.cover_cm + (inputs.shear.stirrup_diameter_mm / 10)) * transform.scale
    figure.add_shape(
        type="rect",
        x0=transform.x_offset + stirrup_offset,
        x1=transform.x_offset + transform.section_width - stirrup_offset,
        y0=transform.y_offset + stirrup_offset,
        y1=transform.y_offset + transform.section_depth - stirrup_offset,
        line=dict(color=STIRRUP_DRAWING_COLOR, width=2),
        fillcolor="rgba(0,0,0,0)",
    )
    _add_bar_shapes(figure, top_bars, theme.ok, transform)
    _add_bar_shapes(figure, bottom_bars, theme.fail, transform)
    _add_bar_shapes(figure, torsion_layout.points, theme.warning, transform)

    figure.update_xaxes(range=[0, DRAWING_VIEWPORT_WIDTH], visible=False)
    figure.update_yaxes(range=[DRAWING_VIEWPORT_HEIGHT, 0], visible=False, scaleanchor="x", scaleratio=1)
    figure.update_layout(
        height=280,
        width=280,
        margin=dict(l=4, r=4, t=4, b=4),
        paper_bgcolor=theme.plot_background,
        plot_bgcolor=theme.plot_background,
        showlegend=False,
    )
    return figure


def build_beam_section_svg(
    inputs: BeamDesignInputSet,
    theme: ThemePalette,
    moment_case: str = "positive",
    transform: "DrawingTransform | None" = None,
) -> str:
    transform = transform or _drawing_transform(inputs.geometry.width_cm, inputs.geometry.depth_cm)
    top_arrangement, bottom_arrangement = _select_arrangements(inputs, moment_case)
    top_bars = compute_bar_points(inputs, top_arrangement, face="top")
    bottom_bars = compute_bar_points(inputs, bottom_arrangement, face="bottom")
    torsion_layout = compute_torsion_bar_layout(inputs, moment_case)
    stirrup_offset = (inputs.geometry.cover_cm + inputs.shear.stirrup_diameter_mm / 10) * transform.scale
    svg_width = int(DRAWING_VIEWPORT_WIDTH)
    svg_height = int(DRAWING_VIEWPORT_HEIGHT)

    def tx(x_cm: float) -> float:
        return transform.x_offset + x_cm * transform.scale

    def ty(y_cm: float) -> float:
        return transform.y_offset + y_cm * transform.scale

    bar_elements = []
    for bar in top_bars:
        radius = max((bar.diameter_mm / 10) * transform.scale / 2, MIN_DRAWN_BAR_RADIUS)
        bar_elements.append(f"<circle cx='{tx(bar.x_cm):.2f}' cy='{ty(bar.y_cm):.2f}' r='{radius:.2f}' fill='{theme.ok}' opacity='0.92' />")
    for bar in bottom_bars:
        radius = max((bar.diameter_mm / 10) * transform.scale / 2, MIN_DRAWN_BAR_RADIUS)
        bar_elements.append(f"<circle cx='{tx(bar.x_cm):.2f}' cy='{ty(bar.y_cm):.2f}' r='{radius:.2f}' fill='{theme.fail}' opacity='0.92' />")
    for bar in torsion_layout.points:
        radius = max((bar.diameter_mm / 10) * transform.scale / 2, MIN_DRAWN_BAR_RADIUS)
        bar_elements.append(f"<circle cx='{tx(bar.x_cm):.2f}' cy='{ty(bar.y_cm):.2f}' r='{radius:.2f}' fill='{theme.warning}' opacity='0.92' />")

    return f"""
    <svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">
      <rect x="{transform.x_offset:.2f}" y="{transform.y_offset:.2f}" width="{transform.section_width:.2f}" height="{transform.section_depth:.2f}" rx="10" fill="{theme.surface_alt}" stroke="{theme.text}" stroke-width="2"/>
      <rect x="{transform.x_offset + stirrup_offset:.2f}" y="{transform.y_offset + stirrup_offset:.2f}" width="{transform.section_width - 2 * stirrup_offset:.2f}" height="{transform.section_depth - 2 * stirrup_offset:.2f}" rx="8" fill="none" stroke="{STIRRUP_DRAWING_COLOR}" stroke-width="2"/>
      {''.join(bar_elements)}
    </svg>
    """


def compute_bar_points(
    inputs: BeamDesignInputSet,
    arrangement: ReinforcementArrangementInput,
    *,
    face: str,
) -> list[BarPoint]:
    points: list[BarPoint] = []
    cover = inputs.geometry.cover_cm
    stirrup_diameter_cm = inputs.shear.stirrup_diameter_mm / 10
    clear_face = cover + stirrup_diameter_cm

    for layer_index, layer in enumerate(arrangement.layers(), start=1):
        ordered_bars = ordered_layer_bars(layer)
        if not ordered_bars:
            continue
        diameters = [diameter_mm for diameter_mm, _ in ordered_bars]
        y_local = _layer_centerline_from_face(inputs, arrangement, layer_index - 1, face)
        x_positions = _layer_bar_centers(inputs.geometry.width_cm, clear_face, diameters)
        for (diameter_mm, group_name), x_position in zip(ordered_bars, x_positions):
            points.append(
                BarPoint(
                    x_cm=x_position,
                    y_cm=y_local,
                    diameter_mm=diameter_mm,
                    layer_index=layer_index,
                    group_name=group_name,
                )
            )
    return points


def compute_torsion_side_bar_points(inputs: BeamDesignInputSet, moment_case: str = "positive") -> list[BarPoint]:
    return compute_torsion_bar_layout(inputs, moment_case).points


def compute_torsion_bar_layout(inputs: BeamDesignInputSet, moment_case: str = "positive") -> TorsionBarLayout:
    return _compute_torsion_bar_layout_for_count(
        inputs,
        moment_case,
        inputs.torsion.provided_longitudinal_bar_count,
    )


def torsion_bar_drawable_capacity(inputs: BeamDesignInputSet, moment_case: str = "positive") -> int:
    return len(_compute_torsion_bar_layout_for_count(inputs, moment_case, 999).points)


def _compute_torsion_bar_layout_for_count(
    inputs: BeamDesignInputSet,
    moment_case: str,
    requested_count: int,
) -> TorsionBarLayout:
    torsion = inputs.torsion
    if (
        not torsion.enabled
        or torsion.provided_longitudinal_bar_diameter_mm is None
        or requested_count <= 0
    ):
        return TorsionBarLayout(points=[], detail_lines=["-"])

    top_arrangement, bottom_arrangement = _select_arrangements(inputs, moment_case)
    occupied_points = [
        *compute_bar_points(inputs, top_arrangement, face="top"),
        *compute_bar_points(inputs, bottom_arrangement, face="bottom"),
    ]
    minimum_clear_cm = inputs.geometry.minimum_clear_spacing_cm
    bar_diameter_mm = torsion.provided_longitudinal_bar_diameter_mm
    perimeter = _torsion_perimeter_geometry(inputs, bar_diameter_mm)
    surface_counts = {"left": 0, "right": 0, "top": 0, "bottom": 0}

    while sum(surface_counts.values()) < requested_count:
        remaining = requested_count - sum(surface_counts.values())
        if remaining >= 2:
            paired_counts = dict(surface_counts)
            paired_counts["left"] += 1
            paired_counts["right"] += 1
            paired_layout = _compose_torsion_surface_layout(
                paired_counts,
                perimeter,
                bar_diameter_mm,
                occupied_points,
                minimum_clear_cm,
            )
            if paired_layout is not None:
                surface_counts = paired_counts
                continue

        surface_priority = _torsion_surface_priority(surface_counts)
        placed_in_cycle = False
        for surface_name in surface_priority:
            trial_counts = dict(surface_counts)
            trial_counts[surface_name] += 1
            candidate_layout = _compose_torsion_surface_layout(
                trial_counts,
                perimeter,
                bar_diameter_mm,
                occupied_points,
                minimum_clear_cm,
            )
            if candidate_layout is not None:
                surface_counts = trial_counts
                placed_in_cycle = True
                break
        if not placed_in_cycle:
            break

    placed_points = _compose_torsion_surface_layout(
        surface_counts,
        perimeter,
        bar_diameter_mm,
        occupied_points,
        minimum_clear_cm,
    ) or []

    detail_lines = _format_torsion_surface_distribution(
        placed_points,
        longitudinal_bar_mark(torsion.provided_longitudinal_bar_fy_ksc),
    )
    warning_messages: list[str] = []
    if len(placed_points) < requested_count:
        warning_messages.append(
            "Reached maximum Al bar count for the current section perimeter layout. "
            f"Requested = {requested_count}, drawable = {len(placed_points)}. "
            "Additional Al bars would violate the minimum clear spacing requirement."
        )
    all_section_points = [*occupied_points, *placed_points]
    minimum_clear_found_cm = _minimum_clear_spacing_cm(all_section_points)
    if minimum_clear_found_cm is not None and minimum_clear_found_cm + 1e-9 < minimum_clear_cm:
        warning_messages.append(
            "Some section bars are closer than the minimum clear spacing requirement "
            f"({minimum_clear_found_cm:.2f} cm < {minimum_clear_cm:.2f} cm)."
        )
    return TorsionBarLayout(
        points=placed_points,
        detail_lines=detail_lines or ["-"],
        warning=" ".join(warning_messages),
    )


def _torsion_surface_priority(surface_counts: dict[str, int]) -> tuple[str, ...]:
    total_count = sum(surface_counts.values())
    if total_count == 0:
        return ("left", "right", "top", "bottom")
    if surface_counts["left"] == surface_counts["right"]:
        return ("top", "bottom", "left", "right")
    if surface_counts["left"] < surface_counts["right"]:
        return ("left", "top", "bottom", "right")
    return ("right", "top", "bottom", "left")


def normalize_moment_case(inputs: BeamDesignInputSet, moment_case: str) -> str:
    active_cases = [key for key, _ in inputs.active_flexural_sections]
    if moment_case in active_cases:
        return moment_case
    if "middle" in active_cases:
        return "middle"
    if "support" in active_cases:
        return "support"
    if "positive" in active_cases:
        return "positive"
    if "negative" in active_cases:
        return "negative"
    return "cantilever_negative"


def available_moment_cases(inputs: BeamDesignInputSet) -> list[str]:
    return [key for key, _ in inputs.active_flexural_sections]


def beam_section_specs(inputs: BeamDesignInputSet) -> list[tuple[str, str]]:
    return [(label, key) for key, label in inputs.active_flexural_sections]


def shared_drawing_transform(inputs: BeamDesignInputSet) -> "DrawingTransform":
    return _drawing_transform(inputs.geometry.width_cm, inputs.geometry.depth_cm)


def build_section_rebar_details(
    inputs: BeamDesignInputSet,
    moment_case: str,
    stirrup_spacing_cm: float | None = None,
) -> SectionRebarDetails:
    top_arrangement, bottom_arrangement = _select_arrangements(inputs, moment_case)
    longitudinal_mark = longitudinal_bar_mark(inputs.materials.main_steel_yield_ksc)
    torsion_layout = compute_torsion_bar_layout(inputs, moment_case)
    return SectionRebarDetails(
        top_lines=_format_arrangement_layers(top_arrangement, longitudinal_mark),
        bottom_lines=_format_arrangement_layers(bottom_arrangement, longitudinal_mark),
        stirrup_line=_format_stirrup_detail(inputs, stirrup_spacing_cm),
        torsion_side_lines=torsion_layout.detail_lines,
        torsion_warning=torsion_layout.warning,
    )


def build_flexural_phi_chart_svg(theme: ThemePalette, state: PhiFlexureChartState) -> str:
    if not flexural_phi_chart_supported(state.design_code):
        return ""

    curve_points = flexural_phi_chart_points(state.design_code, state.ety)
    max_curve_x = max(point[0] for point in curve_points)
    x_min = min(0.0, state.et, state.ety) - 0.0002
    x_max = max(max_curve_x, state.et, state.ety) + 0.0004
    x_span = max(x_max - x_min, 0.001)
    curve_phi_values = [point[1] for point in curve_points]
    y_min = min(curve_phi_values + [state.phi]) - 0.02
    y_max = max(curve_phi_values + [state.phi]) + 0.02
    y_min = max(0.0, min(y_min, 0.65))
    y_max = min(1.0, max(y_max, 0.90))
    y_span = y_max - y_min

    width = 300.0
    height = 180.0
    padding_left = 44.0
    padding_right = 14.0
    padding_top = 14.0
    padding_bottom = 34.0
    plot_width = width - padding_left - padding_right
    plot_height = height - padding_top - padding_bottom

    def sx(x_value: float) -> float:
        return padding_left + ((x_value - x_min) / x_span) * plot_width

    def sy(y_value: float) -> float:
        return padding_top + ((y_max - y_value) / y_span) * plot_height

    transition_start = curve_points[1][0]
    transition_end = curve_points[2][0]
    compression_x0 = sx(x_min)
    compression_x1 = sx(transition_start)
    transition_x1 = sx(transition_end)
    tension_x1 = sx(x_max)

    plot_curve_points = list(curve_points)
    if x_max > plot_curve_points[-1][0]:
        plot_curve_points.append((x_max, plot_curve_points[-1][1]))
    polyline_points = " ".join(f"{sx(x_value):.2f},{sy(y_value):.2f}" for x_value, y_value in plot_curve_points)
    marker_x = sx(state.et)
    marker_y = sy(max(min(state.phi, y_max), y_min))

    tick_values = sorted({0.0, transition_start, transition_end, max_curve_x, max(state.et, 0.0)})
    filtered_tick_values: list[float] = []
    min_tick_spacing_px = 34.0
    for tick_value in tick_values:
        tick_x = sx(tick_value)
        if filtered_tick_values and abs(tick_x - sx(filtered_tick_values[-1])) < min_tick_spacing_px:
            if abs(tick_value - state.et) < abs(filtered_tick_values[-1] - state.et):
                filtered_tick_values[-1] = tick_value
            continue
        filtered_tick_values.append(tick_value)
    if filtered_tick_values[-1] != tick_values[-1]:
        filtered_tick_values[-1] = tick_values[-1]

    tick_markup = []
    x_grid_markup = []
    for tick_value in filtered_tick_values:
        tick_x = sx(tick_value)
        tick_label = f"{tick_value:.4f}"
        if abs(tick_x - padding_left) >= 1 and abs(tick_x - (padding_left + plot_width)) >= 1:
            x_grid_markup.append(
                f"<line x1='{tick_x:.2f}' y1='{padding_top:.2f}' x2='{tick_x:.2f}' y2='{padding_top + plot_height:.2f}' "
                f"stroke='{theme.border}' stroke-width='1' stroke-opacity='0.7' stroke-dasharray='3 5' />"
            )
        tick_markup.append(
            f"<line x1='{tick_x:.2f}' y1='{padding_top + plot_height:.2f}' x2='{tick_x:.2f}' y2='{padding_top + plot_height + 5:.2f}' "
            f"stroke='{theme.muted_text}' stroke-width='1' />"
            f"<text x='{tick_x:.2f}' y='{height - 12:.2f}' text-anchor='middle' font-size='9.5' fill='{theme.muted_text}'>{tick_label}</text>"
        )

    y_tick_markup = []
    y_grid_markup = []
    for y_tick in (0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        if y_tick < y_min - 1e-9 or y_tick > y_max + 1e-9:
            continue
        tick_y = sy(y_tick)
        y_grid_markup.append(
            f"<line x1='{padding_left:.2f}' y1='{tick_y:.2f}' x2='{padding_left + plot_width:.2f}' y2='{tick_y:.2f}' "
            f"stroke='{theme.border}' stroke-width='1' stroke-opacity='0.75' />"
        )
        y_tick_markup.append(
            f"<line x1='{padding_left - 5:.2f}' y1='{tick_y:.2f}' x2='{padding_left:.2f}' y2='{tick_y:.2f}' stroke='{theme.muted_text}' stroke-width='1' />"
            f"<text x='{padding_left - 8:.2f}' y='{tick_y + 3:.2f}' text-anchor='end' font-size='9.5' fill='{theme.muted_text}'>{y_tick:.2f}</text>"
        )

    curve_color = "#1f4fff"
    curve_halo = "#f8fbff"
    guide_color = "#7ea1ff"

    return f"""
    <div class="metric-card">
      <div class="section-label">{state.title}</div>
      <svg width="100%" style="display:block;max-width:{width:.0f}px;margin:0 auto;" viewBox="0 0 {width:.0f} {height:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{state.title} flexural phi strain chart">
        <rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" rx="14" fill="{theme.surface_alt}" />
        <rect x="{padding_left:.2f}" y="{padding_top:.2f}" width="{plot_width:.2f}" height="{plot_height:.2f}" rx="12" fill="{theme.surface}" stroke="{theme.border}" stroke-width="1.3" />
        <rect x="{compression_x0:.2f}" y="{padding_top:.2f}" width="{max(compression_x1 - compression_x0, 0):.2f}" height="{plot_height:.2f}" fill="{theme.fail}" fill-opacity="0.12" />
        <rect x="{compression_x1:.2f}" y="{padding_top:.2f}" width="{max(transition_x1 - compression_x1, 0):.2f}" height="{plot_height:.2f}" fill="{theme.warning}" fill-opacity="0.15" />
        <rect x="{transition_x1:.2f}" y="{padding_top:.2f}" width="{max(tension_x1 - transition_x1, 0):.2f}" height="{plot_height:.2f}" fill="{theme.ok}" fill-opacity="0.12" />
        {''.join(y_grid_markup)}
        {''.join(x_grid_markup)}
        <line x1="{padding_left:.2f}" y1="{padding_top:.2f}" x2="{padding_left:.2f}" y2="{padding_top + plot_height:.2f}" stroke="{theme.text}" stroke-width="1.9" />
        <line x1="{padding_left:.2f}" y1="{padding_top + plot_height:.2f}" x2="{padding_left + plot_width:.2f}" y2="{padding_top + plot_height:.2f}" stroke="{theme.text}" stroke-width="1.9" />
        {''.join(y_tick_markup)}
        {''.join(tick_markup)}
        <polyline points="{polyline_points}" fill="none" stroke="{curve_halo}" stroke-width="5.2" stroke-linejoin="round" stroke-linecap="round" stroke-opacity="0.96" />
        <polyline points="{polyline_points}" fill="none" stroke="{curve_color}" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round" />
        <line x1="{marker_x:.2f}" y1="{padding_top:.2f}" x2="{marker_x:.2f}" y2="{padding_top + plot_height:.2f}" stroke="{guide_color}" stroke-width="1.5" stroke-opacity="0.95" stroke-dasharray="4 4" />
        <circle cx="{marker_x:.2f}" cy="{marker_y:.2f}" r="6.5" fill="{theme.surface}" fill-opacity="0.96" />
        <circle cx="{marker_x:.2f}" cy="{marker_y:.2f}" r="5.0" fill="{theme.fail}" stroke="{theme.surface}" stroke-width="2.1" />
        <circle cx="{marker_x:.2f}" cy="{marker_y:.2f}" r="1.8" fill="{theme.surface}" />
        <text x="{padding_left + plot_width / 2:.2f}" y="{height - 1:.2f}" text-anchor="middle" font-size="10.5" font-weight="600" fill="{theme.text}">Tensile strain, &#949;<tspan baseline-shift="sub">t</tspan></text>
        <text x="14" y="{padding_top + plot_height / 2:.2f}" text-anchor="middle" font-size="10.5" font-weight="600" fill="{theme.text}" transform="rotate(-90 14 {padding_top + plot_height / 2:.2f})">Flexural &#966;</text>
      </svg>
      <div class="metric-note">Current point: &#949;<sub>t</sub> = {format_ratio(state.et, 5)}, &#949;<sub>y</sub> = {format_ratio(state.ety, 5)}, &#966; = {format_ratio(state.phi, 3)}</div>
    </div>
    """


def _select_arrangements(inputs: BeamDesignInputSet, moment_case: str) -> tuple[ReinforcementArrangementInput, ReinforcementArrangementInput]:
    normalized_case = normalize_moment_case(inputs, moment_case)
    if normalized_case == "support":
        return (
            inputs.simple_support_bending.compression_reinforcement,
            inputs.simple_support_bending.tension_reinforcement,
        )
    if normalized_case == "middle":
        return (
            inputs.positive_bending.compression_reinforcement,
            inputs.positive_bending.tension_reinforcement,
        )
    if normalized_case == "negative":
        return (inputs.negative_bending.tension_reinforcement, inputs.negative_bending.compression_reinforcement)
    if normalized_case == "cantilever_negative":
        return (
            inputs.cantilever_negative_bending.tension_reinforcement,
            inputs.cantilever_negative_bending.compression_reinforcement,
        )
    return (inputs.positive_bending.compression_reinforcement, inputs.positive_bending.tension_reinforcement)


def _format_arrangement_layers(arrangement: ReinforcementArrangementInput, bar_mark: str) -> list[str]:
    layers: list[str] = []
    populated_layers: list[str] = []
    for layer_index, layer in enumerate(arrangement.layers(), start=1):
        group_parts: list[str] = []
        for group in layer.groups():
            if group.diameter_mm is None or group.count == 0:
                continue
            group_parts.append(f"{group.count}{bar_mark}{group.diameter_mm}")
        if group_parts:
            populated_layers.append(f"Layer {layer_index}: {' + '.join(group_parts)}")
    if not populated_layers:
        return ["-"]
    if len(populated_layers) == 1:
        return [populated_layers[0].replace("Layer 1: ", "", 1)]
    layers.extend(populated_layers)
    return layers


def _format_stirrup_detail(inputs: BeamDesignInputSet, stirrup_spacing_cm: float | None) -> str:
    spacing_text = ""
    if stirrup_spacing_cm is not None:
        spacing_mm = int(round(stirrup_spacing_cm * 10))
        spacing_text = f" @ {spacing_mm} mm"
    return f"{stirrup_bar_mark(inputs.materials.shear_steel_yield_ksc)}{inputs.shear.stirrup_diameter_mm}, {inputs.shear.legs_per_plane} legs{spacing_text}"


def _format_torsion_side_lines(inputs: BeamDesignInputSet) -> list[str]:
    return compute_torsion_bar_layout(inputs, "positive").detail_lines


def _evenly_distribute_side_bar_positions(y_min_cm: float, y_max_cm: float, count: int) -> list[float]:
    if count <= 1:
        return [(y_min_cm + y_max_cm) / 2.0]
    spacing_cm = (y_max_cm - y_min_cm) / (count + 1)
    return [y_min_cm + (spacing_cm * (index + 1)) for index in range(count)]


def torsion_bar_spacing_warning(inputs: BeamDesignInputSet, moment_case: str = "positive") -> str:
    return compute_torsion_bar_layout(inputs, moment_case).warning


def _torsion_perimeter_geometry(inputs: BeamDesignInputSet, bar_diameter_mm: int) -> _TorsionPerimeterGeometry:
    cover = inputs.geometry.cover_cm
    stirrup_diameter_cm = inputs.shear.stirrup_diameter_mm / 10.0
    bar_radius_cm = bar_diameter_mm / 20.0
    x_left_cm = cover + stirrup_diameter_cm + bar_radius_cm
    x_right_cm = inputs.geometry.width_cm - x_left_cm
    y_top_cm = cover + stirrup_diameter_cm + bar_radius_cm
    y_bottom_cm = inputs.geometry.depth_cm - y_top_cm
    return _TorsionPerimeterGeometry(
        x_left_cm=x_left_cm,
        x_right_cm=x_right_cm,
        y_top_cm=y_top_cm,
        y_bottom_cm=y_bottom_cm,
    )


def _compose_torsion_surface_layout(
    surface_counts: dict[str, int],
    perimeter: _TorsionPerimeterGeometry,
    bar_diameter_mm: int,
    occupied_points: list[BarPoint],
    minimum_clear_cm: float,
) -> list[BarPoint] | None:
    points: list[BarPoint] = []
    for surface_name in ("left", "right"):
        side_points = _build_side_surface_points(
            surface_name,
            surface_counts[surface_name],
            perimeter,
            bar_diameter_mm,
            occupied_points,
            minimum_clear_cm,
        )
        if side_points is None:
            return None
        points.extend(side_points)

    for surface_name in ("top", "bottom"):
        surface_points = _build_top_bottom_surface_points(
            surface_name,
            surface_counts[surface_name],
            perimeter,
            bar_diameter_mm,
            minimum_clear_cm,
        )
        if surface_points is None:
            return None
        points.extend(surface_points)

    if not _layout_points_are_clear(points, occupied_points, minimum_clear_cm):
        return None
    return points


def _build_side_surface_points(
    surface_name: str,
    count: int,
    perimeter: _TorsionPerimeterGeometry,
    bar_diameter_mm: int,
    occupied_points: list[BarPoint],
    minimum_clear_cm: float,
) -> list[BarPoint] | None:
    if count <= 0:
        return []
    x_cm = perimeter.x_left_cm if surface_name == "left" else perimeter.x_right_cm
    y_top_anchor_cm, y_bottom_anchor_cm = _side_surface_anchor_positions(
        surface_name,
        x_cm,
        perimeter,
        occupied_points,
    )
    if y_top_anchor_cm is None or y_bottom_anchor_cm is None:
        return None
    y_positions = _evenly_distribute_side_bar_positions(y_top_anchor_cm, y_bottom_anchor_cm, count)
    points = [
        BarPoint(
            x_cm=x_cm,
            y_cm=y_cm,
            diameter_mm=bar_diameter_mm,
            layer_index=index,
            group_name=surface_name,
        )
        for index, y_cm in enumerate(y_positions, start=1)
    ]
    if not _layout_points_are_clear(points, occupied_points, minimum_clear_cm):
        return None
    return points


def _side_surface_anchor_positions(
    surface_name: str,
    x_cm: float,
    perimeter: _TorsionPerimeterGeometry,
    occupied_points: list[BarPoint],
) -> tuple[float | None, float | None]:
    top_anchor = min(occupied_points, key=lambda point: point.y_cm, default=None)
    bottom_anchor = max(occupied_points, key=lambda point: point.y_cm, default=None)
    if top_anchor is None or bottom_anchor is None:
        return (None, None)
    return (top_anchor.y_cm, bottom_anchor.y_cm)


def _build_top_bottom_surface_points(
    surface_name: str,
    count: int,
    perimeter: _TorsionPerimeterGeometry,
    bar_diameter_mm: int,
    minimum_clear_cm: float,
) -> list[BarPoint] | None:
    if count <= 0:
        return []
    center_spacing_cm = minimum_clear_cm + (bar_diameter_mm / 10.0)
    span_cm = max(perimeter.x_right_cm - perimeter.x_left_cm, 0.0)
    if span_cm <= 0:
        return None
    if count > max(int(math.floor(span_cm / center_spacing_cm)) - 1, 1):
        return None
    axis_positions = _interior_surface_positions(perimeter.x_left_cm, perimeter.x_right_cm, count)
    y_cm = perimeter.y_top_cm if surface_name == "top" else perimeter.y_bottom_cm
    return [
        BarPoint(x_cm=x_cm, y_cm=y_cm, diameter_mm=bar_diameter_mm, layer_index=index, group_name=surface_name)
        for index, x_cm in enumerate(axis_positions, start=1)
    ]


def _max_surface_points(
    surface_name: str,
    axis_start_cm: float,
    axis_end_cm: float,
    fixed_axis_cm: float,
    bar_diameter_mm: int,
    minimum_clear_cm: float,
) -> list[BarPoint]:
    center_spacing_cm = minimum_clear_cm + (bar_diameter_mm / 10.0)
    span_cm = max(axis_end_cm - axis_start_cm, 0.0)
    max_count = max(int(math.floor(span_cm / center_spacing_cm)) - 1, 1)
    points: list[BarPoint] = []
    for count in range(1, max_count + 1):
        axis_positions = _interior_surface_positions(axis_start_cm, axis_end_cm, count)
        points = [
            (
                BarPoint(x_cm=fixed_axis_cm, y_cm=axis_value, diameter_mm=bar_diameter_mm, layer_index=index, group_name=surface_name)
                if surface_name in {"left", "right"}
                else BarPoint(x_cm=axis_value, y_cm=fixed_axis_cm, diameter_mm=bar_diameter_mm, layer_index=index, group_name=surface_name)
            )
            for index, axis_value in enumerate(axis_positions, start=1)
        ]
    return points


def _interior_surface_positions(start_cm: float, end_cm: float, count: int) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [(start_cm + end_cm) / 2.0]
    spacing_cm = (end_cm - start_cm) / (count + 1)
    return [start_cm + (spacing_cm * (index + 1)) for index in range(count)]


def _torsion_surface_slots(inputs: BeamDesignInputSet, bar_diameter_mm: int) -> dict[str, list[BarPoint]]:
    cover = inputs.geometry.cover_cm
    stirrup_diameter_cm = inputs.shear.stirrup_diameter_mm / 10.0
    bar_radius_cm = bar_diameter_mm / 20.0
    min_clear_cm = inputs.geometry.minimum_clear_spacing_cm
    center_spacing_cm = min_clear_cm + (bar_diameter_mm / 10.0)

    x_left_cm = cover + stirrup_diameter_cm + bar_radius_cm
    x_right_cm = inputs.geometry.width_cm - x_left_cm
    y_top_cm = cover + stirrup_diameter_cm + bar_radius_cm
    y_bottom_cm = inputs.geometry.depth_cm - y_top_cm

    left_y_positions = _surface_axis_positions(y_top_cm, y_bottom_cm, center_spacing_cm)
    top_x_positions = _surface_axis_positions(x_left_cm, x_right_cm, center_spacing_cm)

    return {
        "left": [BarPoint(x_cm=x_left_cm, y_cm=y_cm, diameter_mm=bar_diameter_mm, layer_index=index, group_name="left") for index, y_cm in enumerate(left_y_positions, start=1)],
        "right": [BarPoint(x_cm=x_right_cm, y_cm=y_cm, diameter_mm=bar_diameter_mm, layer_index=index, group_name="right") for index, y_cm in enumerate(left_y_positions, start=1)],
        "top": [BarPoint(x_cm=x_cm, y_cm=y_top_cm, diameter_mm=bar_diameter_mm, layer_index=index, group_name="top") for index, x_cm in enumerate(top_x_positions, start=1)],
        "bottom": [BarPoint(x_cm=x_cm, y_cm=y_bottom_cm, diameter_mm=bar_diameter_mm, layer_index=index, group_name="bottom") for index, x_cm in enumerate(top_x_positions, start=1)],
    }


def _surface_axis_positions(start_cm: float, end_cm: float, center_spacing_cm: float) -> list[float]:
    span_cm = max(end_cm - start_cm, 0.0)
    if span_cm <= 0:
        return [(start_cm + end_cm) / 2.0]
    slot_count = max(int(math.floor(span_cm / center_spacing_cm)) + 1, 1)
    actual_spacing_cm = 0.0 if slot_count == 1 else span_cm / (slot_count - 1)
    raw_positions = [start_cm + (actual_spacing_cm * index) for index in range(slot_count)]
    center_cm = (start_cm + end_cm) / 2.0
    return sorted(raw_positions, key=lambda value: (abs(value - center_cm), value))


def _bar_candidate_is_clear(candidate: BarPoint, occupied_points: list[BarPoint], minimum_clear_cm: float) -> bool:
    for occupied in occupied_points:
        required_center_distance_cm = _required_center_distance_cm(candidate, occupied, minimum_clear_cm)
        if math.dist((candidate.x_cm, candidate.y_cm), (occupied.x_cm, occupied.y_cm)) < required_center_distance_cm - 1e-9:
            return False
    return True


def _layout_points_are_clear(
    candidate_points: list[BarPoint],
    occupied_points: list[BarPoint],
    minimum_clear_cm: float,
) -> bool:
    for index, point in enumerate(candidate_points):
        if not _bar_candidate_is_clear(point, [*occupied_points, *candidate_points[:index]], minimum_clear_cm):
            return False
    return True


def _minimum_clear_spacing_cm(points: list[BarPoint]) -> float | None:
    if len(points) < 2:
        return None
    minimum_clear_cm: float | None = None
    for index, point in enumerate(points[:-1]):
        for other_point in points[index + 1 :]:
            center_distance_cm = math.dist((point.x_cm, point.y_cm), (other_point.x_cm, other_point.y_cm))
            clear_spacing_cm = center_distance_cm - (point.diameter_mm / 20.0) - (other_point.diameter_mm / 20.0)
            if minimum_clear_cm is None or clear_spacing_cm < minimum_clear_cm:
                minimum_clear_cm = clear_spacing_cm
    return minimum_clear_cm


def _required_center_distance_cm(first: BarPoint, second: BarPoint, minimum_clear_cm: float) -> float:
    return (
        (first.diameter_mm / 20.0)
        + (second.diameter_mm / 20.0)
        + minimum_clear_cm
    )


def _format_torsion_surface_distribution(points: list[BarPoint], bar_mark: str) -> list[str]:
    if not points:
        return []
    counts: dict[str, tuple[int, int]] = {}
    for point in points:
        count, diameter_mm = counts.get(point.group_name, (0, point.diameter_mm))
        counts[point.group_name] = (count + 1, diameter_mm)
    face_order = ["left", "right", "top", "bottom"]
    lines: list[str] = []
    for face_name in face_order:
        if face_name not in counts:
            continue
        count, diameter_mm = counts[face_name]
        label = face_name.capitalize()
        lines.append(f"{label} face: {count}{bar_mark}{diameter_mm}")
    return lines


def ordered_layer_bars(layer) -> list[tuple[int, str]]:
    """Expand a layer into a symmetric left-to-right drawing order.

    Group A represents the two corner bars and is always placed at the outside
    edges of the layer. Group B represents the middle bars placed between the
    corner bars. The resulting order is symmetric about the section centerline.
    """
    ordered: list[tuple[int, str]] = []
    if layer.group_a.diameter_mm is not None and layer.group_a.count == 2:
        ordered.append((layer.group_a.diameter_mm, "Corner"))
    if layer.group_b.diameter_mm is not None:
        ordered.extend([(layer.group_b.diameter_mm, "Middle")] * layer.group_b.count)
    if layer.group_a.diameter_mm is not None and layer.group_a.count == 2:
        ordered.append((layer.group_a.diameter_mm, "Corner"))
    return ordered


def _layer_centerline_from_face(
    inputs: BeamDesignInputSet,
    arrangement: ReinforcementArrangementInput,
    layer_index: int,
    face: str,
) -> float:
    cover = inputs.geometry.cover_cm
    stirrup_diameter_cm = inputs.shear.stirrup_diameter_mm / 10
    distance_from_face = cover + stirrup_diameter_cm
    layers = arrangement.layers()
    for previous_index in range(layer_index):
        previous_layer = layers[previous_index]
        previous_max_diameter_cm = max(previous_layer.group_a.diameter_cm, previous_layer.group_b.diameter_cm)
        distance_from_face += previous_max_diameter_cm + max(
            inputs.geometry.minimum_clear_spacing_cm,
            previous_layer.group_a.diameter_cm,
            previous_layer.group_b.diameter_cm,
        )
    current_layer = layers[layer_index]
    centerline = distance_from_face + max(current_layer.group_a.diameter_cm, current_layer.group_b.diameter_cm) / 2
    if face == "top":
        return centerline
    return inputs.geometry.depth_cm - centerline


def _layer_bar_centers(width_cm: float, clear_face_cm: float, diameters_mm: list[int]) -> list[float]:
    if len(diameters_mm) == 1:
        return [width_cm / 2]
    diameters_cm = [diameter / 10 for diameter in diameters_mm]
    clear_width_cm = width_cm - clear_face_cm * 2
    occupied_width_cm = sum(diameters_cm)
    clear_spacing_cm = (clear_width_cm - occupied_width_cm) / (len(diameters_mm) - 1)
    centers: list[float] = []
    current_x = clear_face_cm + diameters_cm[0] / 2
    centers.append(current_x)
    for previous_diameter, next_diameter in zip(diameters_cm, diameters_cm[1:]):
        current_x += previous_diameter / 2 + clear_spacing_cm + next_diameter / 2
        centers.append(current_x)
    return centers


@dataclass(frozen=True, slots=True)
class DrawingTransform:
    scale: float
    x_offset: float
    y_offset: float
    section_width: float
    section_depth: float


def _drawing_transform(width_cm: float, depth_cm: float) -> DrawingTransform:
    max_dimension_cm = max(width_cm, depth_cm, 1.0)
    scale = min(DRAWING_TARGET_SPAN / max_dimension_cm, DRAWING_TARGET_SPAN / 20.0)
    section_width = width_cm * scale
    section_depth = depth_cm * scale
    x_offset = max((DRAWING_VIEWPORT_WIDTH - section_width) / 2, DRAWING_PADDING)
    y_offset = max((DRAWING_VIEWPORT_HEIGHT - section_depth) / 2, DRAWING_PADDING)
    return DrawingTransform(
        scale=scale,
        x_offset=x_offset,
        y_offset=y_offset,
        section_width=section_width,
        section_depth=section_depth,
    )


def _add_bar_shapes(figure, bars: list[BarPoint], color: str, transform: DrawingTransform) -> None:
    for bar in bars:
        radius = max((bar.diameter_mm / 10) * transform.scale / 2, MIN_DRAWN_BAR_RADIUS)
        center_x = transform.x_offset + (bar.x_cm * transform.scale)
        center_y = transform.y_offset + (bar.y_cm * transform.scale)
        figure.add_shape(
            type="circle",
            x0=center_x - radius,
            x1=center_x + radius,
            y0=center_y - radius,
            y1=center_y + radius,
            line=dict(color=color, width=2),
            fillcolor=color,
            opacity=0.9,
        )
