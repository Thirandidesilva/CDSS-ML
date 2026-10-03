"""Pure geometry for the severity-over-time chart in the vet-report PDF. No I/O and no
drawing library — just where things go. Kept separate from report_pdf.py so the chart
math is unit-testable without ReportLab, a database or a template engine.

Coordinates are in the chart's own box, origin top-left, y growing downwards (the
drawing code flips y). Band colours are exported because the PDF legend reuses them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

LOW_FILL, MOD_FILL, HIGH_FILL = "#dcfce7", "#fef3c7", "#fee2e2"
LOW_TEXT, MOD_TEXT, HIGH_TEXT = "#16a34a", "#d97706", "#dc2626"
BLUE = "#2563eb"


@dataclass(frozen=True)
class Band:
    y_top: float
    y_bottom: float
    fill: str
    text_color: str
    label: str


@dataclass(frozen=True)
class Marker:
    x: float
    y: float
    theta: float
    date_display: str
    label_y: float  # baseline of the theta value label (above the marker, or below near the top edge)


@dataclass(frozen=True)
class ChartLayout:
    width: int
    height: int
    plot_x0: float
    plot_x1: float
    plot_y0: float
    plot_y1: float
    bands: list[Band]
    gridlines: list[tuple[float, float]]  # (y, theta value) every 0.5
    markers: list[Marker]

    @property
    def connected(self) -> bool:
        return len(self.markers) >= 2


def layout_severity_chart(
    points: list[tuple[str, float]],
    cut_75: float,
    cut_90: float,
    *,
    width: int = 640,
    height: int = 220,
) -> ChartLayout:
    """points: chronological (date_display, theta) pairs, at least one."""
    if not points:
        raise ValueError("layout_severity_chart requires at least one point")

    thetas = [theta for _, theta in points]
    # right_margin is wide enough to hold the band-name labels OUTSIDE the plotted data
    # area (x > plot_x1) so they never collide with the line/markers/value labels, and
    # wide enough that the last (centred) x-axis date label doesn't clip.
    left_margin, right_margin, top_margin, bottom_margin = 48, 60, 24, 32
    plot_x0, plot_x1 = left_margin, width - right_margin
    plot_y0, plot_y1 = top_margin, height - bottom_margin

    # Clean 0.5 gridlines; y_min is NOT hardcoded to 0 since theta_calibrated can be
    # negative (e.g. -0.376 is a real observed value in this project's data).
    y_max = math.ceil((max(cut_90, max(thetas)) + 0.15) * 2) / 2
    y_min = min(0.0, math.floor(min(thetas) * 2) / 2)

    def y_of(theta: float) -> float:
        return plot_y1 - (theta - y_min) / (y_max - y_min) * (plot_y1 - plot_y0)

    n = len(points)
    inset = 24

    def x_of(i: int) -> float:
        if n == 1:
            return (plot_x0 + plot_x1) / 2
        # Inset so the first/last marker and its value label stay clear of the band names.
        return plot_x0 + inset + i * (plot_x1 - plot_x0 - 2 * inset) / (n - 1)

    # Three threshold bands, clamped into [y_min, y_max] — cut_75/cut_90 come from the
    # real population norms, not from this chart's own data, so a defensive clamp
    # guards against a band boundary falling outside this particular chart's range.
    spans = [
        (y_min, min(y_max, cut_75), LOW_FILL, LOW_TEXT, "Low"),
        (max(y_min, cut_75), min(y_max, cut_90), MOD_FILL, MOD_TEXT, "Moderate"),
        (max(y_min, cut_90), y_max, HIGH_FILL, HIGH_TEXT, "High"),
    ]
    bands = [
        Band(y_of(hi), y_of(lo), fill, text_color, label)
        for lo, hi, fill, text_color, label in spans
        if hi > lo
    ]

    steps = round((y_max - y_min) / 0.5)
    gridlines = [(y_of(y_min + i * 0.5), y_min + i * 0.5) for i in range(steps + 1)]

    markers = []
    for i, (date_display, theta) in enumerate(points):
        y = y_of(theta)
        # Flip the value label below the marker when it's close to the chart's top edge,
        # so it doesn't get clipped off the canvas.
        near_top = (y - plot_y0) < 14
        markers.append(Marker(x_of(i), y, theta, date_display, y + 16 if near_top else y - 10))

    return ChartLayout(width, height, plot_x0, plot_x1, plot_y0, plot_y1, bands, gridlines, markers)
