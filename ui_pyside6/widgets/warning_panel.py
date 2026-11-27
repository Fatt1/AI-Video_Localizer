# ui_pyside6/widgets/warning_panel.py
"""
Left panel:
  Tab 1 (Subtitles) — Full SRT table with search, <1s warning filter,
                      multi-select (Ctrl/Shift), inline editing, and batch actions
                      (Add, Delete, Merge, Shift Time, Move Up/Down).
  Tab 2 (Console)   — QPlainTextEdit console log with timestamps.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.subtitle_model import SubtitleEntry, _time_str_to_ms


class WarningPanel(QWidget):
    """Left panel: full subtitle table + batch editor + console log."""

    # Navigation / sync
    seek_to_subtitle = Signal(int)                # start_ms
    subtitle_selected = Signal(int)               # entry_index

    # Editing & batch operations
    subtitle_inline_edited = Signal(int, int, int, str)  # index, start_ms, end_ms, text
    add_subtitle_requested = Signal()
    delete_selected_requested = Signal(list)      # list[int] entry indices
    merge_selected_requested = Signal(list)       # list[int] entry indices
    shift_selected_requested = Signal(list, int)  # list[int] entry indices, delta_ms
    move_entry_requested = Signal(int, int)       # entry_index, direction (-1 or +1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_entries: list[SubtitleEntry] = []
        self._only_warnings: bool = False
        self._search_text: str = ""
        self._populating: bool = False
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top mode switch: Subtitles | Console Log ─────────────────────────
        tab_bar = QWidget()
        tab_lay = QHBoxLayout(tab_bar)
        tab_lay.setContentsMargins(6, 6, 6, 4)
        tab_lay.setSpacing(4)

        self._btn_tab_subs = QPushButton("📋 Subtitles (0)")
        self._btn_tab_subs.setObjectName("tab_btn")
        self._btn_tab_subs.setCheckable(True)
        self._btn_tab_subs.setChecked(True)
        self._btn_tab_subs.clicked.connect(lambda: self._switch_tab(0))

        self._btn_tab_log = QPushButton("🖥 Console Log")
        self._btn_tab_log.setObjectName("tab_btn")
        self._btn_tab_log.setCheckable(True)
        self._btn_tab_log.clicked.connect(lambda: self._switch_tab(1))

        tab_lay.addWidget(self._btn_tab_subs, 1)
        tab_lay.addWidget(self._btn_tab_log, 1)
        root.addWidget(tab_bar)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # ══════════════════════════════════════════════════════════════════════
        # PAGE 0: FULL SUBTITLE LIST
        # ══════════════════════════════════════════════════════════════════════
        sub_page = QWidget()
        sub_lay = QVBoxLayout(sub_page)
        sub_lay.setContentsMargins(6, 2, 6, 6)
        sub_lay.setSpacing(5)

        # Search + Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 Tìm nội dung hoặc #...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search_changed)
        filter_row.addWidget(self._search_input, 1)

        self._btn_filter_warn = QPushButton("⚠ <1s (0)")
        self._btn_filter_warn.setCheckable(True)
        self._btn_filter_warn.setToolTip("Chỉ hiện các dòng nghi lỗi (< 1 giây)")
        self._btn_filter_warn.clicked.connect(self._on_filter_warn_toggled)
        filter_row.addWidget(self._btn_filter_warn)

        sub_lay.addLayout(filter_row)

        # Batch action toolbar
        action_row = QHBoxLayout()
        action_row.setSpacing(4)

        self._btn_add = QPushButton("+ Thêm")
        self._btn_add.setToolTip("Thêm subtitle mới tại vị trí video hiện tại")
        self._btn_add.clicked.connect(self.add_subtitle_requested.emit)

        self._btn_delete = QPushButton("🗑 Xóa")
        self._btn_delete.setToolTip("Xóa các dòng đã chọn (phím Delete)")
        self._btn_delete.clicked.connect(self._on_delete_clicked)

        self._btn_merge = QPushButton("🔗 Gộp")
        self._btn_merge.setToolTip("Gộp 2+ dòng đang chọn thành 1 dòng")
        self._btn_merge.clicked.connect(self._on_merge_clicked)

        self._btn_shift = QPushButton("⏱ ±ms")
        self._btn_shift.setToolTip("Dịch thời gian hàng loạt cho các dòng đã chọn")
        self._btn_shift.clicked.connect(self._on_shift_clicked)

        self._btn_move_up = QPushButton("▲")
        self._btn_move_up.setFixedWidth(28)
        self._btn_move_up.setToolTip("Đưa dòng đang chọn lên trên")
        self._btn_move_up.clicked.connect(lambda: self._on_move_clicked(-1))

        self._btn_move_down = QPushButton("▼")
        self._btn_move_down.setFixedWidth(28)
        self._btn_move_down.setToolTip("Đưa dòng đang chọn xuống dưới")
        self._btn_move_down.clicked.connect(lambda: self._on_move_clicked(1))

        for btn in (
            self._btn_add,
            self._btn_delete,
            self._btn_merge,
            self._btn_shift,
            self._btn_move_up,
            self._btn_move_down,
        ):
            action_row.addWidget(btn)
        action_row.addStretch()
        sub_lay.addLayout(action_row)

        # Subtitle table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["#", "Bắt đầu", "Kết thúc", "Giây", "Nội dung"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 38)
        self._table.setColumnWidth(1, 86)
        self._table.setColumnWidth(2, 86)
        self._table.setColumnWidth(3, 46)

        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self._table.setWordWrap(True)
        self._table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)

        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemChanged.connect(self._on_item_changed)

        # Delete shortcut inside table
        del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._table)
        del_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        del_shortcut.activated.connect(self._on_delete_clicked)

        sub_lay.addWidget(self._table, 1)

        self._selection_hint = QLabel("Click: nhảy video • Double-click: sửa trực tiếp • Ctrl/Shift: chọn nhiều")
        self._selection_hint.setStyleSheet("color: #8888a0; font-size: 11px;")
        sub_lay.addWidget(self._selection_hint)

        self._stack.addWidget(sub_page)

        # ══════════════════════════════════════════════════════════════════════
        # PAGE 1: CONSOLE LOG
        # ══════════════════════════════════════════════════════════════════════
        log_page = QWidget()
        log_lay = QVBoxLayout(log_page)
        log_lay.setContentsMargins(6, 2, 6, 6)
        log_lay.setSpacing(4)

        log_top = QHBoxLayout()
        log_header = QLabel("🖥  Console Log")
        log_header.setObjectName("warning_label")
        btn_clear_log = QPushButton("Xóa log")
        btn_clear_log.clicked.connect(self.clear_log)
        log_top.addWidget(log_header)
        log_top.addStretch()
        log_top.addWidget(btn_clear_log)
        log_lay.addLayout(log_top)

        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setMaximumBlockCount(2000)
        self._console.setFont(QFont("Consolas", 10))
        self._console.setPlaceholderText("Logs sẽ hiện ở đây...")
        log_lay.addWidget(self._console, 1)

        self._stack.addWidget(log_page)
        self._update_action_buttons()

    # ── Public API ────────────────────────────────────────────────────────────
    def set_entries(self, entries: list[SubtitleEntry]):
        """Set full subtitle list and refresh table."""
        self._all_entries = list(entries)
        self._rebuild_table()

    def update_warnings(self, short_entries: list[SubtitleEntry]):
        """Update <1s warning badge count (kept for compatibility)."""
        count = len(short_entries)
        self._btn_filter_warn.setText(f"⚠ <1s ({count})")

    def highlight_entry(self, entry_index: int):
        """Highlight active subtitle during playback without breaking multi-select."""
        if len(self._selected_entry_indices()) > 1:
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == entry_index:
                self._table.blockSignals(True)
                self._table.selectRow(row)
                self._table.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
                self._table.blockSignals(False)
                self._update_action_buttons()
                break

    def append_log(self, message: str):
        """Append timestamped line to console log."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        self._console.appendPlainText(line)
        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._console.setTextCursor(cursor)

    def clear_log(self):
        self._console.clear()

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _switch_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._btn_tab_subs.setChecked(idx == 0)
        self._btn_tab_log.setChecked(idx == 1)

    def _filtered_entries(self) -> list[SubtitleEntry]:
        q = self._search_text.strip().lower()
        out: list[SubtitleEntry] = []
        for e in self._all_entries:
            if self._only_warnings and not e.is_short_duration(1000):
                continue
            if q:
                if q not in e.text.lower() and q not in str(e.index):
                    continue
            out.append(e)
        return out

    def _rebuild_table(self):
        selected_before = set(self._selected_entry_indices())
        entries = self._filtered_entries()

        self._populating = True
        self._table.blockSignals(True)
        self._table.setRowCount(0)

        warn_color = QColor("#f5a623")
        normal_color = QColor("#e4e4ef")
        dim_color = QColor("#9898b0")

        for entry in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)

            idx_item = QTableWidgetItem(str(entry.index))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            idx_item.setFlags(idx_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            idx_item.setData(Qt.ItemDataRole.UserRole, entry.index)
            idx_item.setData(Qt.ItemDataRole.UserRole + 1, entry.start_ms)

            start_item = QTableWidgetItem(entry.start_str)
            end_item = QTableWidgetItem(entry.end_str)

            dur_sec = entry.duration_ms / 1000.0
            dur_item = QTableWidgetItem(f"{dur_sec:.1f}s")
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            text_item = QTableWidgetItem(entry.text)

            is_warn = entry.is_short_duration(1000)
            if is_warn:
                for it in (idx_item, start_item, end_item, dur_item, text_item):
                    it.setForeground(warn_color)
            else:
                idx_item.setForeground(dim_color)
                start_item.setForeground(dim_color)
                end_item.setForeground(dim_color)
                dur_item.setForeground(dim_color)
                text_item.setForeground(normal_color)

            self._table.setItem(row, 0, idx_item)
            self._table.setItem(row, 1, start_item)
            self._table.setItem(row, 2, end_item)
            self._table.setItem(row, 3, dur_item)
            self._table.setItem(row, 4, text_item)

            if entry.index in selected_before:
                self._table.selectRow(row)

        self._table.resizeRowsToContents()
        self._table.blockSignals(False)
        self._populating = False

        total = len(self._all_entries)
        warn_count = sum(1 for e in self._all_entries if e.is_short_duration(1000))
        self._btn_tab_subs.setText(f"📋 Subtitles ({total})")
        self._btn_filter_warn.setText(f"⚠ <1s ({warn_count})")
        self._update_action_buttons()

    def _selected_entry_indices(self) -> list[int]:
        indices: list[int] = []
        seen: set[int] = set()
        for model_idx in self._table.selectionModel().selectedRows():
            item = self._table.item(model_idx.row(), 0)
            if item:
                idx_val = item.data(Qt.ItemDataRole.UserRole)
                if idx_val is not None and int(idx_val) not in seen:
                    seen.add(int(idx_val))
                    indices.append(int(idx_val))
        return indices

    def _update_action_buttons(self):
        n = len(self._selected_entry_indices())
        self._btn_delete.setEnabled(n >= 1)
        self._btn_shift.setEnabled(n >= 1)
        self._btn_merge.setEnabled(n >= 2)
        self._btn_move_up.setEnabled(n == 1)
        self._btn_move_down.setEnabled(n == 1)

        if n > 1:
            self._selection_hint.setText(f"Đang chọn {n} dòng — bấm Xóa, Gộp hoặc ±ms để sửa hàng loạt")
        else:
            self._selection_hint.setText("Click: nhảy video • Double-click: sửa trực tiếp • Ctrl/Shift: chọn nhiều")

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_search_changed(self, text: str):
        self._search_text = text
        self._rebuild_table()

    def _on_filter_warn_toggled(self, checked: bool):
        self._only_warnings = checked
        self._rebuild_table()

    def _on_selection_changed(self):
        self._update_action_buttons()

    def _on_cell_clicked(self, row: int, _col: int):
        item = self._table.item(row, 0)
        if not item:
            return
        entry_idx = item.data(Qt.ItemDataRole.UserRole)
        start_ms = item.data(Qt.ItemDataRole.UserRole + 1)
        if entry_idx is not None:
            self.subtitle_selected.emit(int(entry_idx))
        if start_ms is not None:
            self.seek_to_subtitle.emit(int(start_ms))

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._populating:
            return
        row = item.row()
        idx_item = self._table.item(row, 0)
        start_item = self._table.item(row, 1)
        end_item = self._table.item(row, 2)
        text_item = self._table.item(row, 4)
        if not (idx_item and start_item and end_item and text_item):
            return

        entry_idx = int(idx_item.data(Qt.ItemDataRole.UserRole))
        try:
            start_ms = _time_str_to_ms(start_item.text().strip())
            end_ms = _time_str_to_ms(end_item.text().strip())
        except Exception:
            self._rebuild_table()
            return

        if end_ms < start_ms:
            end_ms = start_ms

        self.subtitle_inline_edited.emit(entry_idx, start_ms, end_ms, text_item.text().strip())

    def _on_delete_clicked(self):
        indices = self._selected_entry_indices()
        if indices:
            self.delete_selected_requested.emit(indices)

    def _on_merge_clicked(self):
        indices = self._selected_entry_indices()
        if len(indices) >= 2:
            self.merge_selected_requested.emit(indices)

    def _on_shift_clicked(self):
        indices = self._selected_entry_indices()
        if not indices:
            return
        delta_ms, ok = QInputDialog.getInt(
            self,
            "Dịch thời gian hàng loạt",
            f"Dịch {len(indices)} dòng đã chọn (ms, âm = sớm hơn, dương = trễ hơn):",
            0,
            -600_000,
            600_000,
            100,
        )
        if ok and delta_ms != 0:
            self.shift_selected_requested.emit(indices, delta_ms)

    def _on_move_clicked(self, direction: int):
        indices = self._selected_entry_indices()
        if len(indices) == 1:
            self.move_entry_requested.emit(indices[0], direction)
