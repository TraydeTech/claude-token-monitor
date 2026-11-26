"""Cairo-based circular gauge widget for GTK4."""

import math
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk
import cairo


class GaugeWidget(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self._percent = 0.0
        self._label = "0%"
        self._sublabel = ""
        self.set_draw_func(self._draw)
        self.set_size_request(220, 220)

    def set_value(self, percent: float, label: str = "", sublabel: str = ""):
        self._percent = max(0.0, min(1.0, percent))
        self._label = label or f"{percent * 100:.1f}%"
        self._sublabel = sublabel
        self.queue_draw()

    def _draw(self, widget, cr: cairo.Context, width: int, height: int):
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 16

        # Background
        cr.set_source_rgb(0.13, 0.13, 0.15)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Track arc
        cr.set_line_width(14)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(1, 1, 1, 0.08)
        start_angle = math.pi * 0.75
        end_angle = math.pi * 2.25
        cr.arc(cx, cy, radius, start_angle, end_angle)
        cr.stroke()

        # Determine color based on percent
        p = self._percent
        if p < 0.6:
            r, g, b = 0.20, 0.78, 0.47   # green
        elif p < 0.80:
            r, g, b = 1.0, 0.76, 0.03    # yellow
        elif p < 0.92:
            r, g, b = 1.0, 0.45, 0.0     # orange
        else:
            r, g, b = 0.90, 0.17, 0.17   # red

        # Glow effect
        if p > 0.01:
            glow_radius = radius + 2
            cr.set_line_width(20)
            cr.set_source_rgba(r, g, b, 0.12)
            fill_angle = start_angle + (end_angle - start_angle) * p
            cr.arc(cx, cy, glow_radius, start_angle, fill_angle)
            cr.stroke()

        # Progress arc
        if p > 0.005:
            cr.set_line_width(14)
            cr.set_source_rgb(r, g, b)
            fill_angle = start_angle + (end_angle - start_angle) * p
            cr.arc(cx, cy, radius, start_angle, fill_angle)
            cr.stroke()

        # Center dot
        cr.set_source_rgba(r, g, b, 0.25)
        cr.arc(cx, cy, 6, 0, 2 * math.pi)
        cr.fill()

        # Main percentage label
        cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        font_size = 36 if len(self._label) <= 4 else 30
        cr.set_font_size(font_size)
        cr.set_source_rgb(0.95, 0.95, 0.97)
        extents = cr.text_extents(self._label)
        cr.move_to(cx - extents.width / 2, cy + extents.height / 2 - 10)
        cr.show_text(self._label)

        # Sublabel
        if self._sublabel:
            cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(12)
            cr.set_source_rgba(0.6, 0.6, 0.65, 1.0)
            extents = cr.text_extents(self._sublabel)
            cr.move_to(cx - extents.width / 2, cy + 22)
            cr.show_text(self._sublabel)


class MiniBarChart(Gtk.DrawingArea):
    """Mini bar chart showing token usage over 4h window (16 buckets of 15min)."""

    def __init__(self):
        super().__init__()
        self._buckets: list[int] = [0] * 16
        self._max_val = 1
        self.set_draw_func(self._draw)
        self.set_size_request(0, 60)

    def set_data(self, buckets: list[int]):
        self._buckets = buckets if buckets else [0] * 16
        self._max_val = max(max(self._buckets), 1)
        self.queue_draw()

    def _draw(self, widget, cr: cairo.Context, width: int, height: int):
        n = len(self._buckets)
        if n == 0:
            return

        bar_w = width / n
        gap = 2
        cr.set_source_rgb(0.13, 0.13, 0.15)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        for i, val in enumerate(self._buckets):
            ratio = val / self._max_val
            bar_h = max(ratio * (height - 4), 2 if val > 0 else 0)
            x = i * bar_w + gap / 2
            y = height - bar_h

            # Color: recent bars brighter
            age_ratio = i / max(n - 1, 1)
            alpha = 0.4 + age_ratio * 0.6
            cr.set_source_rgba(0.20, 0.78, 0.47, alpha)
            cr.rectangle(x, y, bar_w - gap, bar_h)
            cr.fill()
