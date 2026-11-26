"""GTK4/Adwaita application entry point."""

import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from .window import MainWindow


class TokenMonitorApp(Adw.Application):
    def __init__(self, token_limit: int = 200_000):
        super().__init__(
            application_id="io.github.traydetech.claude-token-monitor",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._token_limit = token_limit
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        win = MainWindow(app=app, token_limit=self._token_limit)
        win.present()


def main(token_limit: int = 200_000):
    app = TokenMonitorApp(token_limit=token_limit)
    return app.run(sys.argv)
