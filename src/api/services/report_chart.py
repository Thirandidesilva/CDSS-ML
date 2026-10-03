"""Pure function: builds the inline-SVG severity-over-time chart for the vet-report PDF.
No I/O, no Jinja2 — just geometry. Kept separate from report_pdf_data.py so the chart
math is unit-testable without a database or a template engine.
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

_LOW_FILL, _MOD_FILL, _HIGH_FILL = "#dcfce7", "#fef3c7", "#fee2e2"
_LOW_TEXT, _MOD_TEXT, _HIGH_TEXT = "#16a34a", "#d97706", "#dc2626"
_BLUE = "#2563eb"


def render_severity_chart_svg(
    points: list[tuple[str, float]],
    cut_75: float,
    cut_90: float,
    *,
    width: int = 640,
    height: int = 220,
) -> str:
    """points: chronological (date_display, theta) pairs, at least one. Returns a bare
    <svg>...</svg> string — the caller wraps it with a caption/legend in HTML."""
    if not points:
        raise ValueError("render_severity_chart_svg requires at least one point")

    thetas = [theta for _, theta in points]
    # right_margin is wide enough to hold the band-name labels OUTSIDE the plotted data
    # area (x > plot_x1) so they never collide with the line/markers/value labels, and
    # wide enough that the last (text-anchor=middle) x-axis date label doesn't clip.
    left_margin, right_margin, top_margin, bottom_margin = 48, 60, 24, 32
    plot_x0, plot_x1 = left_margin, width - right_margin
    plot_y0, plot_y1 = top_margin, height - bottom_margin

    # Clean 0.5 gridlines; y_min is NOT hardcoded to 0 since theta_calibrated can be
    # negative (e.g. -0.376 is a real observed value in this project's data).
    y_max = math.ceil((max(cut_90, max(thetas)) + 0.15) * 2) / 2
    y_min = min(0.0, math.floor(min(thetas) * 2) / 2)

    def y_to_svg(theta: float) -> float:
        return plot_y1 - (theta - y_min) / (y_max - y_min) * (plot_y1 - plot_y0)

    n = len(points)

    def x_to_svg(i: int) -> float:
        if n == 1:
            return (plot_x0 + plot_x1) / 2
        return plot_x0 + i * (plot_x1 - plot_x0) / (n - 1)

    parts: list[str] = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']

    # Three threshold bands, clamped into [y_min, y_max] — cut_75/cut_90 come from the
    # real population norms, not from this chart's own data, so a defensive clamp
    # guards against a band boundary falling outside this particular chart's range.
    bands = [
        (max(y_min, y_min), min(y_max, cut_75), _LOW_FILL, _LOW_TEXT, "Low"),
        (max(y_min, cut_75), min(y_max, cut_90), _MOD_FILL, _MOD_TEXT, "Moderate"),
        (max(y_min, cut_90), y_max, _HIGH_FILL, _HIGH_TEXT, "High"),
    ]
    for lo, hi, fill, text_color, label in bands:
        if hi <= lo:
            continue
        y_top, y_bottom = y_to_svg(hi), y_to_svg(lo)
        parts.append(
            f'<rect x="{plot_x0}" y="{y_top:.1f}" width="{plot_x1 - plot_x0}" '
            f'height="{y_bottom - y_top:.1f}" fill="{fill}" />'
        )
        # Placed just OUTSIDE the plotted data area (x > plot_x1), never inside it, so a
        # band label can never sit under a data point's marker or value label.
        parts.append(
            f'<text x="{plot_x1 + 8}" y="{(y_top + y_bottom) / 2:.1f}" text-anchor="start" '
            f'dominant-baseline="middle" font-size="9" fill="{text_color}">{label}</text>'
        )

    # Gridlines + y-axis labels at every 0.5 step.
    steps = round((y_max - y_min) / 0.5)
    for i in range(steps + 1):
        val = y_min + i * 0.5
        y = y_to_svg(val)
        parts.append(
            f'<line x1="{plot_x0}" y1="{y:.1f}" x2="{plot_x1}" y2="{y:.1f}" '
            f'stroke="#e5e7eb" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{plot_x0 - 8}" y="{y:.1f}" text-anchor="end" dominant-baseline="middle" '
            f'font-size="9" fill="#6b7280">{val:g}</text>'
        )

    coords = [(x_to_svg(i), y_to_svg(theta)) for i, (_, theta) in enumerate(points)]

    if n >= 2:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{_BLUE}" stroke-width="2" />')

    for (date_display, theta), (x, y) in zip(points, coords):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="white" stroke="{_BLUE}" stroke-width="2" />')

        # Flip the value label below the marker instead of above when it's close to the
        # chart's top edge, so it doesn't get clipped off the SVG canvas.
        near_top = (y - plot_y0) < 14
        label_y = y + 16 if near_top else y - 10
        parts.append(
            f'<text x="{x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="10" '
            f'font-weight="600" fill="#111827">{theta:.2f}</text>'
        )

        parts.append(
            f'<text x="{x:.1f}" y="{plot_y1 + 20}" text-anchor="middle" font-size="9" '
            f'fill="#6b7280">{escape(date_display)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)
