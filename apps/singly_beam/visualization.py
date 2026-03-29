from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class PhiFlexureChartState:
    title: str
    design_code: DesignCode
    et: float
    ety: float
    phi: float


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


def normalize_moment_case(inputs: BeamDesignInputSet, moment_case: str) -> str:
    if not inputs.has_negative_design:
        return "positive"
    return "negative" if moment_case == "negative" else "positive"


def available_moment_cases(inputs: BeamDesignInputSet) -> list[str]:
    if inputs.has_negative_design:
        return ["positive", "negative"]
    return ["positive"]


def beam_section_specs(inputs: BeamDesignInputSet) -> list[tuple[str, str]]:
    if inputs.has_negative_design:
        return [("Positive", "positive"), ("Negative", "negative")]
    return [("Beam Section", "positive")]


def shared_drawing_transform(inputs: BeamDesignInputSet) -> "DrawingTransform":
    return _drawing_transform(inputs.geometry.width_cm, inputs.geometry.depth_cm)


def build_section_rebar_details(
    inputs: BeamDesignInputSet,
    moment_case: str,
    stirrup_spacing_cm: float | None = None,
) -> SectionRebarDetails:
    top_arrangement, bottom_arrangement = _select_arrangements(inputs, moment_case)
    longitudinal_mark = longitudinal_bar_mark(inputs.materials.main_steel_yield_ksc)
    return SectionRebarDetails(
        top_lines=_format_arrangement_layers(top_arrangement, longitudinal_mark),
        bottom_lines=_format_arrangement_layers(bottom_arrangement, longitudinal_mark),
        stirrup_line=_format_stirrup_detail(inputs, stirrup_spacing_cm),
    )


def build_flexural_phi_chart_svg(theme: ThemePalette, state: PhiFlexureChartState) -> str:
    if not flexural_phi_chart_supported(state.design_code):
        return ""

    curve_points = flexural_phi_chart_points(state.design_code, state.ety)
    max_curve_x = max(point[0] for point in curve_points)
    x_min = min(0.0, state.et, state.ety) - 0.0002
    x_max = max(max_curve_x, state.et, state.ety) + 0.0004
    x_span = max(x_max - x_min, 0.001)
    y_min = 0.73
    y_max = 0.92
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
    for y_tick in (0.75, 0.80, 0.85, 0.90):
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
    if normalized_case == "negative":
        return (inputs.negative_bending.tension_reinforcement, inputs.negative_bending.compression_reinforcement)
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
