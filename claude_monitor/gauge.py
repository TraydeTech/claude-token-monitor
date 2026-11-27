"""Gauge and chart widgets."""

import math
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib
import cairo


class GaugeWidget(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self._percent = 0.0
        self._label = "0%"
        self._sublabel = ""
        self.set_draw_func(self._draw)
        self.set_size_request(120, 120)
        self.set_hexpand(True)
        self.set_vexpand(True)

    def set_value(self, percent: float, label: str = "", sublabel: str = ""):
        self._percent = max(0.0, min(1.0, percent))
        self._label = label or f"{percent * 100:.1f}%"
        self._sublabel = sublabel
        self.queue_draw()

    def _draw(self, widget, cr: cairo.Context, width: int, height: int):
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 12

        p = self._percent
        if p < 0.6:
            r, g, b = 0.20, 0.78, 0.47
        elif p < 0.80:
            r, g, b = 1.0, 0.76, 0.03
        elif p < 0.92:
            r, g, b = 1.0, 0.45, 0.0
        else:
            r, g, b = 0.90, 0.17, 0.17

        start_angle = math.pi * 0.75
        end_angle = math.pi * 2.25

        # Track
        cr.set_line_width(12)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(1, 1, 1, 0.1)
        cr.arc(cx, cy, radius, start_angle, end_angle)
        cr.stroke()

        # Progress
        if p > 0.005:
            cr.set_line_width(12)
            cr.set_source_rgb(r, g, b)
            fill_angle = start_angle + (end_angle - start_angle) * p
            cr.arc(cx, cy, radius, start_angle, fill_angle)
            cr.stroke()

        # Percentage text
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(30)
        cr.set_source_rgba(0.95, 0.95, 0.97, 1.0)
        extents = cr.text_extents(self._label)
        cr.move_to(cx - extents.width / 2, cy + extents.height / 2 - 8)
        cr.show_text(self._label)

        # Sublabel
        if self._sublabel:
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(10)
            cr.set_source_rgba(0.55, 0.55, 0.60, 1.0)
            extents = cr.text_extents(self._sublabel)
            cr.move_to(cx - extents.width / 2, cy + 20)
            cr.show_text(self._sublabel)


class MiniBarChart(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self._buckets: list[int] = [0] * 16
        self._max_val = 1
        self.set_draw_func(self._draw)
        self.set_size_request(0, 56)
        self.set_hexpand(True)

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

        for i, val in enumerate(self._buckets):
            ratio = val / self._max_val
            bar_h = max(ratio * (height - 4), 2 if val > 0 else 0)
            x = i * bar_w + gap / 2
            y = height - bar_h
            age_ratio = i / max(n - 1, 1)
            alpha = 0.35 + age_ratio * 0.65
            cr.set_source_rgba(0.20, 0.78, 0.47, alpha)
            cr.rectangle(x, y, bar_w - gap, bar_h)
            cr.fill()
