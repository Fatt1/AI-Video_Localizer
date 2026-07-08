# ui_pyside6/main.py
"""
Entry point for AI Video Localizer PySide6 UI.

Usage:
    python ui_pyside6/main.py

Requirements:
    pip install PySide6 python-vlc
    (backend deps: paddleocr, funasr, cv2, pysrt, etc. already installed)
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# ── Add backend to sys.path so we can import services/* directly ──────────────
_UI_DIR      = Path(__file__).parent.resolve()          # …/ui_pyside6
_PROJECT_DIR = _UI_DIR.parent.resolve()                 # …/AI-Video_Localizer
_BACKEND_DIR = _PROJECT_DIR / "backend"

for _p in (_UI_DIR, _BACKEND_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ── PySide6 ───────────────────────────────────────────────────────────────────
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from styles.theme import DARK_THEME
from main_window import MainWindow


def main() -> int:
    # PySide6 6.x handles high-DPI automatically — no attribute needed

    app = QApplication(sys.argv)
    app.setApplicationName("AI Video Localizer")
    app.setOrganizationName("VideoLocalizer")
    app.setStyle("Fusion")  # base style — overridden by QSS

    # Apply dark theme stylesheet
    app.setStyleSheet(DARK_THEME)

    # Prefer system Segoe UI, fallback to Inter / sans-serif
    for family in ("Segoe UI", "Inter", "Noto Sans", "Arial"):
        if family in QFontDatabase.families():
            app.setFont(QFont(family, 10))
            break

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
