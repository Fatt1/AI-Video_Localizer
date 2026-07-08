# ui_pyside6/dialogs/add_subtitle_dialog.py
"""
Dialog to add a new subtitle entry.
Pre-fills start time with current video position.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from models.subtitle_model import SubtitleEntry


class AddSubtitleDialog(QDialog):
    """Modal dialog for adding a new subtitle entry."""

    def __init__(self, default_start_ms: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thêm Subtitle")
        self.setMinimumWidth(380)
        self.result_entry: SubtitleEntry | None = None
        self._build_ui(default_start_ms)

    def _build_ui(self, default_start_ms: int):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # Start time
        self._start = QSpinBox()
        self._start.setRange(0, 99_999_999)
        self._start.setValue(default_start_ms)
        self._start.setSuffix(" ms")
        form.addRow("Bắt đầu:", self._start)

        # End time (default = start + 2000ms)
        self._end = QSpinBox()
        self._end.setRange(0, 99_999_999)
        self._end.setValue(default_start_ms + 2000)
        self._end.setSuffix(" ms")
        form.addRow("Kết thúc:", self._end)

        # Text
        self._text = QTextEdit()
        self._text.setMinimumHeight(70)
        self._text.setPlaceholderText("Nội dung subtitle...")
        form.addRow("Nội dung:", self._text)

        lay.addLayout(form)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_accept(self):
        start_ms = self._start.value()
        end_ms   = self._end.value()
        text     = self._text.toPlainText().strip()

        if end_ms <= start_ms:
            end_ms = start_ms + 500  # enforce minimum

        self.result_entry = SubtitleEntry(
            index=0,  # MainWindow assigns real index
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
        )
        self.accept()
