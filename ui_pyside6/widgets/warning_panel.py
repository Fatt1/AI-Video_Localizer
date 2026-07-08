# ui_pyside6/widgets/warning_panel.py
"""
Left panel:
  TOP   — QTableWidget listing SRT entries with duration < 1 second (likely errors)
  BOTTOM — QPlainTextEdit console log with timestamps
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.subtitle_model import SubtitleEntry


class WarningPanel(QWidget):
    """Left panel: SRT warning table + console log."""

    # Emitted when user clicks a warning row → seek to that subtitle
    seek_to_subtitle = Signal(int)   # start_ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setHandleWidth(4)

        # ── Warning table ────────────────────────────────────────────────────
        top = QWidget()
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(6, 6, 6, 4)
        top_lay.setSpacing(4)

        self._warning_label = QLabel("⚠ Đoạn SRT nghi lỗi (< 1 giây)")
        self._warning_label.setObjectName("warning_label")
        top_lay.addWidget(self._warning_label)

        self._warning_table = QTableWidget(0, 4)
        self._warning_table.setHorizontalHeaderLabels(["#", "Bắt đầu", "Kết thúc", "Nội dung"])
        self._warning_table.horizontalHeader().setStretchLastSection(True)
        self._warning_table.setColumnWidth(0, 36)
        self._warning_table.setColumnWidth(1, 80)
        self._warning_table.setColumnWidth(2, 80)
        self._warning_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._warning_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._warning_table.setAlternatingRowColors(True)
        self._warning_table.verticalHeader().setVisible(False)
        self._warning_table.cellClicked.connect(self._on_warning_clicked)
        top_lay.addWidget(self._warning_table)
        splitter.addWidget(top)

        # ── Console log ──────────────────────────────────────────────────────
        bottom = QWidget()
        bot_lay = QVBoxLayout(bottom)
        bot_lay.setContentsMargins(6, 4, 6, 6)
        bot_lay.setSpacing(4)

        log_header = QLabel("🖥  Console Log")
        log_header.setObjectName("warning_label")
        bot_lay.addWidget(log_header)

        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setMaximumBlockCount(2000)
        mono = QFont("Consolas", 10)
        self._console.setFont(mono)
        self._console.setPlaceholderText("Logs sẽ hiện ở đây...")
        bot_lay.addWidget(self._console)
        splitter.addWidget(bottom)

        splitter.setSizes([220, 300])
        root.addWidget(splitter)

    # ── Public API ────────────────────────────────────────────────────────────
    def update_warnings(self, short_entries: list[SubtitleEntry]):
        """Populate warning table with short-duration entries."""
        self._warning_table.setRowCount(0)
        for entry in short_entries:
            row = self._warning_table.rowCount()
            self._warning_table.insertRow(row)

            idx_item = QTableWidgetItem(str(entry.index))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            start_item = QTableWidgetItem(entry.start_str)
            end_item   = QTableWidgetItem(entry.end_str)
            text_item  = QTableWidgetItem(entry.text.replace("\n", " "))

            # Store start_ms for seeking
            idx_item.setData(Qt.ItemDataRole.UserRole, entry.start_ms)

            # Color orange for warnings
            warn_color = QColor("#f5a623")
            for item in (idx_item, start_item, end_item, text_item):
                item.setForeground(warn_color)

            self._warning_table.setItem(row, 0, idx_item)
            self._warning_table.setItem(row, 1, start_item)
            self._warning_table.setItem(row, 2, end_item)
            self._warning_table.setItem(row, 3, text_item)

        count = len(short_entries)
        self._warning_label.setText(
            f"⚠ Đoạn SRT nghi lỗi (< 1 giây) — {count} dòng"
            if count else "✅ Không có đoạn SRT nghi lỗi"
        )
        self._warning_label.setObjectName("warning_label")

    def append_log(self, message: str):
        """Append timestamped line to console log."""
        ts  = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        self._console.appendPlainText(line)
        # Auto-scroll to bottom
        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._console.setTextCursor(cursor)

    def clear_log(self):
        self._console.clear()

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_warning_clicked(self, row: int, _col: int):
        item = self._warning_table.item(row, 0)
        if item:
            start_ms = item.data(Qt.ItemDataRole.UserRole)
            if start_ms is not None:
                self.seek_to_subtitle.emit(int(start_ms))
