"""Main application window."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from .gauge import GaugeWidget, MiniBarChart
from .collector import collect_window_stats, get_hourly_buckets, WINDOW_HOURS


REFRESH_INTERVAL_MS = 10_000  # 10 seconds
DEFAULT_LIMIT = 200_000


CSS = """
.card-dark {
    background-color: rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 12px;
}
.stat-value {
    font-size: 22px;
    font-weight: bold;
    color: #f0f0f4;
}
.stat-label {
    font-size: 11px;
    color: #888;
}
.countdown {
    font-size: 32px;
    font-weight: bold;
    font-family: monospace;
    color: #f0f0f4;
}
.countdown-label {
    font-size: 11px;
    color: #666;
    letter-spacing: 1px;
}
.section-title {
    font-size: 11px;
    font-weight: bold;
    color: #666;
    letter-spacing: 1px;
}
.limit-row {
    color: #aaa;
    font-size: 12px;
}
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, token_limit: int = DEFAULT_LIMIT):
        super().__init__(application=app)
        self._limit = token_limit
        self._timer_id = None

        self.set_title("Claude Token Monitor")
        self.set_default_size(400, 640)
        self.set_resizable(False)

        self._apply_css()
        self._build_ui()
        self._refresh()
        self._start_timer()

    def _apply_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_ui(self):
        # Root scroll
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_content(scroll)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_margin_top(16)
        root.set_margin_bottom(24)
        root.set_margin_start(16)
        root.set_margin_end(16)
        scroll.set_child(root)

        # ── Header ────────────────────────────────────────────────
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_bottom(16)

        icon_label = Gtk.Label(label="⬡")
        icon_label.add_css_class("title-1")
        header.append(icon_label)

        title = Gtk.Label(label="Claude Token Monitor")
        title.add_css_class("title-3")
        title.set_hexpand(True)
        title.set_halign(Gtk.Align.START)
        header.append(title)

        self._status_dot = Gtk.Label(label="●")
        self._status_dot.add_css_class("dim-label")
        header.append(self._status_dot)

        root.append(header)

        # ── Gauge card ────────────────────────────────────────────
        gauge_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        gauge_card.add_css_class("card")
        gauge_card.set_margin_bottom(12)

        self._gauge = GaugeWidget()
        self._gauge.set_halign(Gtk.Align.CENTER)
        gauge_card.append(self._gauge)

        # Limit row under gauge
        self._limit_row = Gtk.Label()
        self._limit_row.add_css_class("limit-row")
        self._limit_row.set_margin_bottom(8)
        gauge_card.append(self._limit_row)

        root.append(gauge_card)

        # ── Countdown card ────────────────────────────────────────
        countdown_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        countdown_card.add_css_class("card")
        countdown_card.set_margin_bottom(12)

        section_lbl = Gtk.Label(label="PRÓXIMA EXPIRAÇÃO DE TOKENS")
        section_lbl.add_css_class("countdown-label")
        section_lbl.set_margin_top(8)
        countdown_card.append(section_lbl)

        self._countdown = Gtk.Label(label="--:--:--")
        self._countdown.add_css_class("countdown")
        self._countdown.set_margin_top(4)
        self._countdown.set_margin_bottom(4)
        countdown_card.append(self._countdown)

        self._expiry_label = Gtk.Label(label="")
        self._expiry_label.add_css_class("dim-label")
        self._expiry_label.set_margin_bottom(8)
        countdown_card.append(self._expiry_label)

        root.append(countdown_card)

        # ── Stats grid ────────────────────────────────────────────
        stats_title = Gtk.Label(label="TOKENS NAS ÚLTIMAS 4 HORAS")
        stats_title.add_css_class("section-title")
        stats_title.set_halign(Gtk.Align.START)
        stats_title.set_margin_bottom(6)
        root.append(stats_title)

        grid = Gtk.Grid()
        grid.set_column_spacing(8)
        grid.set_row_spacing(8)
        grid.set_margin_bottom(12)

        self._stat_widgets = {}
        stats = [
            ("output",    "Output",         "🟢", 0, 0),
            ("input",     "Input",          "🔵", 0, 1),
            ("cache_cr",  "Cache Criado",   "🟡", 1, 0),
            ("cache_rd",  "Cache Lido",     "⚪", 1, 1),
        ]

        for key, label, icon, row, col in stats:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.add_css_class("card-dark")

            val_lbl = Gtk.Label(label="0")
            val_lbl.add_css_class("stat-value")
            val_lbl.set_halign(Gtk.Align.CENTER)
            box.append(val_lbl)

            lbl = Gtk.Label(label=f"{icon} {label}")
            lbl.add_css_class("stat-label")
            lbl.set_halign(Gtk.Align.CENTER)
            box.append(lbl)

            grid.attach(box, col, row, 1, 1)
            grid.set_column_homogeneous(True)
            self._stat_widgets[key] = val_lbl

        root.append(grid)

        # ── Cost row ──────────────────────────────────────────────
        cost_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cost_box.add_css_class("card")
        cost_box.set_margin_bottom(12)

        cost_icon = Gtk.Label(label="💰")
        cost_box.append(cost_icon)

        cost_title = Gtk.Label(label="Custo estimado (4h)")
        cost_title.set_hexpand(True)
        cost_title.set_halign(Gtk.Align.START)
        cost_box.append(cost_title)

        self._cost_label = Gtk.Label(label="$0.0000")
        self._cost_label.add_css_class("stat-value")
        cost_box.append(self._cost_label)

        root.append(cost_box)

        # ── Chart ─────────────────────────────────────────────────
        chart_title = Gtk.Label(label="ATIVIDADE (15 MIN/BARRA)")
        chart_title.add_css_class("section-title")
        chart_title.set_halign(Gtk.Align.START)
        chart_title.set_margin_bottom(6)
        root.append(chart_title)

        chart_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        chart_card.add_css_class("card")
        chart_card.set_margin_bottom(12)

        self._chart = MiniBarChart()
        self._chart.set_hexpand(True)
        self._chart.set_margin_top(8)
        self._chart.set_margin_bottom(8)
        self._chart.set_margin_start(8)
        self._chart.set_margin_end(8)
        chart_card.append(self._chart)

        chart_x = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        chart_x.set_margin_start(8)
        chart_x.set_margin_end(8)
        chart_x.set_margin_bottom(6)
        lbl_left = Gtk.Label(label="4h atrás")
        lbl_left.add_css_class("dim-label")
        lbl_right = Gtk.Label(label="agora")
        lbl_right.add_css_class("dim-label")
        lbl_left.set_halign(Gtk.Align.START)
        lbl_right.set_halign(Gtk.Align.END)
        lbl_left.set_hexpand(True)
        lbl_right.set_hexpand(True)
        chart_x.append(lbl_left)
        chart_x.append(lbl_right)
        chart_card.append(chart_x)

        root.append(chart_card)

        # ── Footer ────────────────────────────────────────────────
        footer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self._last_update = Gtk.Label(label="Atualizado: --")
        self._last_update.add_css_class("dim-label")
        self._last_update.set_hexpand(True)
        self._last_update.set_halign(Gtk.Align.START)
        footer_box.append(self._last_update)

        refresh_btn = Gtk.Button(label="↻ Atualizar")
        refresh_btn.add_css_class("flat")
        refresh_btn.connect("clicked", lambda _: self._refresh())
        footer_box.append(refresh_btn)

        limit_btn = Gtk.Button(label="⚙ Limite")
        limit_btn.add_css_class("flat")
        limit_btn.connect("clicked", self._show_limit_dialog)
        footer_box.append(limit_btn)

        root.append(footer_box)

    def _refresh(self):
        from datetime import datetime, timezone
        stats = collect_window_stats(self._limit)

        # Gauge
        effective = stats.effective_tokens
        pct = effective / self._limit if self._limit > 0 else 0.0
        pct_str = f"{pct * 100:.1f}%"
        self._gauge.set_value(pct, pct_str, f"{effective:,} / {self._limit:,}")
        self._limit_row.set_label(f"{effective:,} tokens usados de {self._limit:,}")

        # Status dot color
        if pct < 0.6:
            self._status_dot.set_markup('<span color="#34C77A">●</span>')
        elif pct < 0.8:
            self._status_dot.set_markup('<span color="#F4C20D">●</span>')
        else:
            self._status_dot.set_markup('<span color="#E62E2E">●</span>')

        # Countdown
        remaining = stats.time_until_next_expiry
        if remaining is not None:
            total_sec = int(remaining.total_seconds())
            h = total_sec // 3600
            m = (total_sec % 3600) // 60
            s = total_sec % 60
            self._countdown.set_label(f"{h:02d}:{m:02d}:{s:02d}")
            if stats.oldest_entry_time:
                reset_at = stats.window_reset_time
                self._expiry_label.set_label(
                    f"Tokens de {stats.oldest_entry_time.astimezone().strftime('%H:%M')} expiram às {reset_at.astimezone().strftime('%H:%M')}"
                )
        else:
            self._countdown.set_label("--:--:--")
            self._expiry_label.set_label("Nenhum uso nas últimas 4 horas")

        # Stats grid
        self._stat_widgets["output"].set_label(f"{stats.total_output:,}")
        self._stat_widgets["input"].set_label(f"{stats.total_input:,}")
        self._stat_widgets["cache_cr"].set_label(f"{stats.total_cache_creation:,}")
        self._stat_widgets["cache_rd"].set_label(f"{stats.total_cache_read:,}")

        # Cost
        self._cost_label.set_label(f"${stats.total_cost:.4f}")

        # Chart
        buckets = get_hourly_buckets(stats.entries, hours=WINDOW_HOURS)
        self._chart.set_data([v for _, v in buckets])

        # Footer
        now_str = datetime.now().strftime("%H:%M:%S")
        self._last_update.set_label(f"Atualizado: {now_str}")

        return True  # keep timer alive

    def _start_timer(self):
        self._timer_id = GLib.timeout_add(REFRESH_INTERVAL_MS, self._refresh)

    def _show_limit_dialog(self, _):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Configurar limite de tokens",
            body="Defina o limite máximo de tokens para a janela de 4 horas:",
        )

        entry = Gtk.Entry()
        entry.set_text(str(self._limit))
        entry.set_input_purpose(Gtk.InputPurpose.NUMBER)
        entry.set_halign(Gtk.Align.CENTER)
        entry.set_width_chars(12)
        dialog.set_extra_child(entry)

        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("ok", "Salvar")
        dialog.set_default_response("ok")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "ok":
                try:
                    val = int(entry.get_text().replace(",", "").replace(".", ""))
                    if val > 0:
                        self._limit = val
                        self._refresh()
                except ValueError:
                    pass
            d.destroy()

        dialog.connect("response", on_response)
        dialog.present()
