"""Main application window."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

from .gauge import GaugeWidget, MiniBarChart
from .collector import collect_window_stats, get_hourly_buckets, WINDOW_HOURS


REFRESH_INTERVAL_MS = 10_000
DEFAULT_LIMIT = 200_000

CSS = """
.pct-label {
    font-size: 46px;
    font-weight: bold;
    font-family: monospace;
}
.pct-green  { color: #34C77A; }
.pct-yellow { color: #F4C20D; }
.pct-orange { color: #FF7300; }
.pct-red    { color: #E62E2E; }

.countdown {
    font-size: 36px;
    font-weight: bold;
    font-family: monospace;
    color: #f0f0f4;
}
.countdown-label {
    font-size: 10px;
    color: #666;
    letter-spacing: 1px;
}
.section-title {
    font-size: 10px;
    font-weight: bold;
    color: #666;
    letter-spacing: 1px;
}
.stat-value {
    font-size: 20px;
    font-weight: bold;
    color: #f0f0f4;
}
.stat-label {
    font-size: 10px;
    color: #888;
}
.meta-value {
    font-size: 14px;
    font-weight: bold;
    color: #d0d0d8;
}
.meta-label {
    font-size: 10px;
    color: #666;
}
.warning-banner {
    background-color: rgba(230, 46, 46, 0.15);
    border-radius: 8px;
    padding: 6px 12px;
}
"""


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, token_limit: int = DEFAULT_LIMIT):
        super().__init__(application=app)
        self._limit = token_limit
        self._timer_id = None

        self.set_title("Claude Token Monitor")
        self.set_default_size(400, 680)
        self.set_resizable(True)
        self.set_size_request(300, 480)

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
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        self.set_content(scroll)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_margin_top(12)
        root.set_margin_bottom(24)
        root.set_margin_start(14)
        root.set_margin_end(14)
        root.set_hexpand(True)
        scroll.set_child(root)

        # ── Header ───────────────────────────────────────────────
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_bottom(12)
        icon = Gtk.Label(label="⬡")
        icon.add_css_class("title-2")
        header.append(icon)
        title = Gtk.Label(label="Claude Token Monitor")
        title.add_css_class("title-3")
        title.set_hexpand(True)
        title.set_halign(Gtk.Align.START)
        header.append(title)
        self._status_dot = Gtk.Label()
        self._status_dot.set_markup('<span color="#34C77A">●</span>')
        header.append(self._status_dot)
        root.append(header)

        # ── Warning banner (hidden by default) ───────────────────
        self._warning_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._warning_box.add_css_class("warning-banner")
        self._warning_box.set_margin_bottom(10)
        self._warning_icon = Gtk.Label(label="⚠")
        self._warning_box.append(self._warning_icon)
        self._warning_label = Gtk.Label()
        self._warning_label.set_hexpand(True)
        self._warning_label.set_halign(Gtk.Align.START)
        self._warning_box.append(self._warning_label)
        self._warning_box.set_visible(False)
        root.append(self._warning_box)

        # ── Main card: gauge + big pct + meta info ────────────────
        main_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_card.add_css_class("card")
        main_card.set_margin_bottom(10)

        # Gauge + percentage side by side
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        top_row.set_margin_top(16)
        top_row.set_margin_start(16)
        top_row.set_margin_end(16)
        top_row.set_margin_bottom(12)
        top_row.set_hexpand(True)

        self._gauge = GaugeWidget()
        self._gauge.set_valign(Gtk.Align.CENTER)
        self._gauge.set_halign(Gtk.Align.FILL)
        top_row.append(self._gauge)

        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_col.set_hexpand(True)
        right_col.set_valign(Gtk.Align.CENTER)

        self._pct_label = Gtk.Label(label="0%")
        self._pct_label.add_css_class("pct-label")
        self._pct_label.add_css_class("pct-green")
        self._pct_label.set_halign(Gtk.Align.START)
        right_col.append(self._pct_label)

        self._tokens_used_lbl = Gtk.Label(label="0 tokens usados")
        self._tokens_used_lbl.add_css_class("dim-label")
        self._tokens_used_lbl.set_halign(Gtk.Align.START)
        right_col.append(self._tokens_used_lbl)

        self._limit_lbl = Gtk.Label()
        self._limit_lbl.add_css_class("dim-label")
        self._limit_lbl.set_halign(Gtk.Align.START)
        right_col.append(self._limit_lbl)

        # Progress bar
        self._progress = Gtk.LevelBar()
        self._progress.set_min_value(0)
        self._progress.set_max_value(1)
        self._progress.set_value(0)
        self._progress.set_margin_top(6)
        right_col.append(self._progress)

        top_row.append(right_col)
        main_card.append(top_row)

        # Separator
        sep = Gtk.Separator()
        sep.set_margin_start(16)
        sep.set_margin_end(16)
        main_card.append(sep)

        # Meta info grid: sessions, messages, avg, velocity
        meta_grid = Gtk.Grid()
        meta_grid.set_column_spacing(0)
        meta_grid.set_row_spacing(0)
        meta_grid.set_column_homogeneous(True)
        meta_grid.set_margin_top(12)
        meta_grid.set_margin_bottom(14)
        meta_grid.set_margin_start(16)
        meta_grid.set_margin_end(16)

        self._meta = {}
        meta_items = [
            ("sessions",  "Sessões",         "0", 0, 0),
            ("messages",  "Mensagens",        "0", 0, 1),
            ("avg",       "Média/msg",        "0", 0, 2),
            ("velocity",  "Tokens/hora",      "0", 0, 3),
        ]
        for key, label, default, row, col in meta_items:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_halign(Gtk.Align.CENTER)

            val = Gtk.Label(label=default)
            val.add_css_class("meta-value")
            box.append(val)

            lbl = Gtk.Label(label=label)
            lbl.add_css_class("meta-label")
            box.append(lbl)

            meta_grid.attach(box, col, row, 1, 1)
            self._meta[key] = val

        main_card.append(meta_grid)
        root.append(main_card)

        # ── Countdown card ────────────────────────────────────────
        cd_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cd_card.add_css_class("card")
        cd_card.set_margin_bottom(10)

        cd_top = Gtk.Label(label="PRÓXIMA EXPIRAÇÃO")
        cd_top.add_css_class("countdown-label")
        cd_top.set_margin_top(10)
        cd_card.append(cd_top)

        self._countdown = Gtk.Label(label="--:--:--")
        self._countdown.add_css_class("countdown")
        self._countdown.set_margin_top(2)
        cd_card.append(self._countdown)

        self._expiry_label = Gtk.Label(label="")
        self._expiry_label.add_css_class("dim-label")
        self._expiry_label.set_margin_bottom(10)
        cd_card.append(self._expiry_label)

        root.append(cd_card)

        # ── Stats grid ────────────────────────────────────────────
        stats_title = Gtk.Label(label="TOKENS NAS ÚLTIMAS 4 HORAS")
        stats_title.add_css_class("section-title")
        stats_title.set_halign(Gtk.Align.START)
        stats_title.set_margin_bottom(6)
        root.append(stats_title)

        grid = Gtk.Grid()
        grid.set_column_spacing(8)
        grid.set_row_spacing(8)
        grid.set_margin_bottom(10)
        grid.set_column_homogeneous(True)

        self._stat_widgets = {}
        for (key, label, icon, row, col) in [
            ("output",   "Output",       "🟢", 0, 0),
            ("input",    "Input",        "🔵", 0, 1),
            ("cache_cr", "Cache Criado", "🟡", 1, 0),
            ("cache_rd", "Cache Lido",   "⚪", 1, 1),
        ]:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.add_css_class("card")

            val_lbl = Gtk.Label(label="0")
            val_lbl.add_css_class("stat-value")
            val_lbl.set_halign(Gtk.Align.CENTER)
            box.append(val_lbl)

            lbl = Gtk.Label(label=f"{icon} {label}")
            lbl.add_css_class("stat-label")
            lbl.set_halign(Gtk.Align.CENTER)
            lbl.set_margin_bottom(4)
            box.append(lbl)

            grid.attach(box, col, row, 1, 1)
            self._stat_widgets[key] = val_lbl

        root.append(grid)

        # ── Cost + model row ──────────────────────────────────────
        cost_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        cost_box.add_css_class("card")
        cost_box.set_margin_bottom(10)

        cost_left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        cost_left.set_hexpand(True)
        cost_icon_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        cost_icon_row.append(Gtk.Label(label="💰"))
        cost_title_lbl = Gtk.Label(label="Custo estimado (4h)")
        cost_title_lbl.add_css_class("dim-label")
        cost_icon_row.append(cost_title_lbl)
        cost_left.append(cost_icon_row)
        self._cost_label = Gtk.Label(label="$0.0000")
        self._cost_label.add_css_class("stat-value")
        self._cost_label.set_halign(Gtk.Align.START)
        cost_left.append(self._cost_label)
        cost_box.append(cost_left)

        limit_btn = Gtk.Button(label="⚙ Limite")
        limit_btn.add_css_class("flat")
        limit_btn.set_valign(Gtk.Align.CENTER)
        limit_btn.connect("clicked", self._show_limit_dialog)
        cost_box.append(limit_btn)
        root.append(cost_box)

        # ── Chart ─────────────────────────────────────────────────
        chart_title = Gtk.Label(label="ATIVIDADE — ÚLTIMAS 4H (15 MIN/BARRA)")
        chart_title.add_css_class("section-title")
        chart_title.set_halign(Gtk.Align.START)
        chart_title.set_margin_bottom(6)
        root.append(chart_title)

        chart_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        chart_card.add_css_class("card")
        chart_card.set_margin_bottom(10)

        self._chart = MiniBarChart()
        self._chart.set_hexpand(True)
        self._chart.set_margin_top(10)
        self._chart.set_margin_bottom(4)
        self._chart.set_margin_start(8)
        self._chart.set_margin_end(8)
        chart_card.append(self._chart)

        axis = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        axis.set_margin_start(8)
        axis.set_margin_end(8)
        axis.set_margin_bottom(8)
        for lbl_text, align in [("4h atrás", Gtk.Align.START), ("2h atrás", Gtk.Align.CENTER), ("agora", Gtk.Align.END)]:
            lbl = Gtk.Label(label=lbl_text)
            lbl.add_css_class("dim-label")
            lbl.set_hexpand(True)
            lbl.set_halign(align)
            axis.append(lbl)
        chart_card.append(axis)
        root.append(chart_card)

        # ── Footer ────────────────────────────────────────────────
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._last_update = Gtk.Label(label="")
        self._last_update.add_css_class("dim-label")
        self._last_update.set_hexpand(True)
        self._last_update.set_halign(Gtk.Align.START)
        footer.append(self._last_update)
        refresh_btn = Gtk.Button(label="↻")
        refresh_btn.add_css_class("flat")
        refresh_btn.connect("clicked", lambda _: self._refresh())
        footer.append(refresh_btn)
        root.append(footer)

    def _refresh(self):
        from datetime import datetime, timezone
        stats = collect_window_stats(self._limit)

        effective = stats.effective_tokens
        pct = effective / self._limit if self._limit > 0 else 0.0
        pct_str = f"{pct * 100:.1f}%"

        # Gauge
        self._gauge.set_value(pct, pct_str)
        self._progress.set_value(min(pct, 1.0))

        # Big percentage
        for cls in ["pct-green", "pct-yellow", "pct-orange", "pct-red"]:
            self._pct_label.remove_css_class(cls)
        if pct < 0.6:
            self._pct_label.add_css_class("pct-green")
            self._status_dot.set_markup('<span color="#34C77A">●</span>')
        elif pct < 0.8:
            self._pct_label.add_css_class("pct-yellow")
            self._status_dot.set_markup('<span color="#F4C20D">●</span>')
        elif pct < 0.92:
            self._pct_label.add_css_class("pct-orange")
            self._status_dot.set_markup('<span color="#FF7300">●</span>')
        else:
            self._pct_label.add_css_class("pct-red")
            self._status_dot.set_markup('<span color="#E62E2E">●</span>')

        self._pct_label.set_label(pct_str)
        self._tokens_used_lbl.set_label(f"{effective:,} tokens usados")
        self._limit_lbl.set_label(f"Limite: {self._limit:,}")

        # Warning banner
        if pct >= 0.90:
            self._warning_box.set_visible(True)
            self._warning_label.set_label(f"Limite crítico! {(1-pct)*100:.1f}% restante.")
        elif pct >= 0.75:
            self._warning_box.set_visible(True)
            self._warning_label.set_label(f"Atenção: {(1-pct)*100:.1f}% do limite restante.")
        else:
            self._warning_box.set_visible(False)

        # Meta info
        sessions = len(set(e.session_id for e in stats.entries))
        messages = len(stats.entries)
        avg = effective // messages if messages > 0 else 0
        # velocity: tokens in last 60 min
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        last_hour = [e for e in stats.entries if e.timestamp > now - timedelta(hours=1)]
        velocity = sum(e.effective_tokens for e in last_hour)

        self._meta["sessions"].set_label(str(sessions))
        self._meta["messages"].set_label(str(messages))
        self._meta["avg"].set_label(_fmt(avg))
        self._meta["velocity"].set_label(_fmt(velocity))

        # Countdown
        remaining = stats.time_until_next_expiry
        if remaining is not None:
            total_sec = int(remaining.total_seconds())
            h = total_sec // 3600
            m = (total_sec % 3600) // 60
            s = total_sec % 60
            self._countdown.set_label(f"{h:02d}:{m:02d}:{s:02d}")
            if stats.oldest_entry_time and stats.window_reset_time:
                self._expiry_label.set_label(
                    f"Tokens de {stats.oldest_entry_time.astimezone().strftime('%H:%M')} "
                    f"expiram às {stats.window_reset_time.astimezone().strftime('%H:%M')}"
                )
        else:
            self._countdown.set_label("--:--:--")
            self._expiry_label.set_label("Sem uso nas últimas 4 horas")

        # Stat grid
        self._stat_widgets["output"].set_label(_fmt(stats.total_output))
        self._stat_widgets["input"].set_label(_fmt(stats.total_input))
        self._stat_widgets["cache_cr"].set_label(_fmt(stats.total_cache_creation))
        self._stat_widgets["cache_rd"].set_label(_fmt(stats.total_cache_read))
        self._cost_label.set_label(f"${stats.total_cost:.4f}")

        # Chart
        buckets = get_hourly_buckets(stats.entries, hours=WINDOW_HOURS)
        self._chart.set_data([v for _, v in buckets])

        # Footer
        self._last_update.set_label(f"Atualizado: {datetime.now().strftime('%H:%M:%S')}")
        return True

    def _start_timer(self):
        self._timer_id = GLib.timeout_add(REFRESH_INTERVAL_MS, self._refresh)

    def _show_limit_dialog(self, _):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Limite de tokens",
            body="Tokens máximos na janela de 4 horas:",
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
