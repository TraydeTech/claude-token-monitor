"""System tray icon using pystray + PIL."""

import threading
from gi.repository import GLib

try:
    import pystray
    from PIL import Image, ImageDraw
    _TRAY_AVAILABLE = True
except (ImportError, ValueError, Exception):
    _TRAY_AVAILABLE = False


def _make_icon(color: str) -> "Image.Image":
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color)
    return img


def _color_for_pct(pct: float) -> str:
    if pct >= 90:
        return "#E62E2E"
    elif pct >= 80:
        return "#F4C20D"
    return "#34C77A"


class TrayIcon:
    def __init__(self):
        self._icon = None
        self._thread = None
        self._window = None
        self._app = None
        self._pct = 0.0

    def start(self, window, app):
        if not _TRAY_AVAILABLE:
            return
        self._window = window
        self._app = app

        def toggle_visibility(icon, item):
            def _do():
                if self._window.is_visible():
                    self._window.hide()
                else:
                    self._window.present()
                return False
            GLib.idle_add(_do)

        def toggle_top(icon, item):
            def _do():
                self._window._toggle_always_on_top()
                return False
            GLib.idle_add(_do)

        def quit_app(icon, item):
            def _do():
                icon.stop()
                self._app.quit()
                return False
            GLib.idle_add(_do)

        menu = pystray.Menu(
            pystray.MenuItem("Mostrar/Ocultar", toggle_visibility),
            pystray.MenuItem("Sempre no Topo", toggle_top),
            pystray.MenuItem("Sair", quit_app),
        )

        img = _make_icon(_color_for_pct(self._pct))
        self._icon = pystray.Icon(
            "claude-token-monitor",
            img,
            "Claude Token Monitor",
            menu,
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def update_pct(self, pct: float):
        self._pct = pct
        if self._icon:
            try:
                self._icon.icon = _make_icon(_color_for_pct(pct))
            except Exception:
                pass
