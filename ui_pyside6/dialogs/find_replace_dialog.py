# ui_pyside6/dialogs/find_replace_dialog.py
"""
Find & Replace dialog — similar to C# FindReplaceSubtitleDialog.
Supports:
  - Exact text search
  - Case-insensitive option
  - Replace one / Replace all
  - Navigate through results
"""
from __future__ import annotations

from difflib import SequenceMatcher

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.subtitle_model import SubtitleEntry


class FindReplaceDialog(QDialog):
    """
    Non-modal Find & Replace dialog for SRT entries list.

    Signals:
        entries_changed() — emitted after Replace All so MainWindow can refresh.
    """

    entries_changed = Signal()

    def __init__(self, entries: list[SubtitleEntry], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tìm & Thay thế SRT")
        self.setMinimumWidth(500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self._entries = entries
        self._results: list[int] = []   # indices into _entries
        self._result_pos: int = -1
        self.replaced_count = 0
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # Find field
        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("Tìm:"))
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("Nhập văn bản cần tìm...")
        self._find_edit.textChanged.connect(self._on_find_changed)
        find_row.addWidget(self._find_edit, stretch=1)
        lay.addLayout(find_row)

        # Replace field
        rep_row = QHBoxLayout()
        rep_row.addWidget(QLabel("Thay bằng:"))
        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("Văn bản thay thế...")
        rep_row.addWidget(self._replace_edit, stretch=1)
        lay.addLayout(rep_row)

        # Options
        opts = QHBoxLayout()
        self._case_cb  = QCheckBox("Phân biệt hoa/thường")
        self._fuzzy_cb = QCheckBox("Tìm gần đúng (fuzzy ≥ 70%)")
        self._fuzzy_cb.setChecked(True)
        opts.addWidget(self._case_cb)
        opts.addWidget(self._fuzzy_cb)
        opts.addStretch()
        lay.addLayout(opts)

        # Status
        self._status_label = QLabel("Nhập từ cần tìm để bắt đầu")
        self._status_label.setStyleSheet("color:#7070a0; font-size:11px;")
        lay.addWidget(self._status_label)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_prev    = QPushButton("◀ Trước")
        self._btn_next    = QPushButton("Tiếp ▶")
        self._btn_replace = QPushButton("Thay 1")
        self._btn_all     = QPushButton("Thay tất cả")
        self._btn_close   = QPushButton("Đóng")

        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_next.clicked.connect(self._go_next)
        self._btn_replace.clicked.connect(self._replace_one)
        self._btn_all.clicked.connect(self._replace_all)
        self._btn_close.clicked.connect(self.close)

        for btn in (self._btn_prev, self._btn_next, self._btn_replace, self._btn_all):
            btn.setEnabled(False)

        btn_row.addWidget(self._btn_prev)
        btn_row.addWidget(self._btn_next)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_replace)
        btn_row.addWidget(self._btn_all)
        btn_row.addWidget(self._btn_close)
        lay.addLayout(btn_row)

    # ── Search logic ──────────────────────────────────────────────────────────
    def _on_find_changed(self, text: str):
        self._search(text)

    def _search(self, query: str = ""):
        if not query:
            query = self._find_edit.text()
        self._results.clear()
        self._result_pos = -1

        if not query:
            self._status_label.setText("Nhập từ cần tìm để bắt đầu")
            self._set_btns_enabled(False)
            return

        case_sens = self._case_cb.isChecked()
        fuzzy     = self._fuzzy_cb.isChecked()

        for i, entry in enumerate(self._entries):
            if self._match(query, entry.text, case_sens, fuzzy):
                self._results.append(i)

        count = len(self._results)
        if count == 0:
            self._status_label.setText(f"Không tìm thấy '{query}'")
            self._set_btns_enabled(False)
        else:
            self._result_pos = 0
            self._status_label.setText(f"Tìm thấy {count} kết quả")
            self._set_btns_enabled(True)

    def _match(self, query: str, text: str, case_sens: bool, fuzzy: bool) -> bool:
        if not case_sens:
            q, t = query.lower(), text.lower()
        else:
            q, t = query, text

        if q in t:
            return True

        if fuzzy:
            ratio = SequenceMatcher(None, q, t).ratio()
            return ratio >= 0.70

        return False

    def _set_btns_enabled(self, enabled: bool):
        for btn in (self._btn_prev, self._btn_next, self._btn_replace, self._btn_all):
            btn.setEnabled(enabled)

    def _go_next(self):
        if not self._results:
            return
        self._result_pos = (self._result_pos + 1) % len(self._results)
        self._update_pos_label()

    def _go_prev(self):
        if not self._results:
            return
        self._result_pos = (self._result_pos - 1) % len(self._results)
        self._update_pos_label()

    def _update_pos_label(self):
        total = len(self._results)
        pos   = self._result_pos + 1
        self._status_label.setText(f"Kết quả {pos}/{total}")

    def _replace_one(self):
        if not self._results or self._result_pos < 0:
            return
        entry_idx = self._results[self._result_pos]
        query   = self._find_edit.text()
        replace = self._replace_edit.text()
        entry   = self._entries[entry_idx]
        entry.text = entry.text.replace(query, replace)
        self.replaced_count += 1
        self.entries_changed.emit()
        # Re-search to refresh results
        self._search()

    def _replace_all(self):
        if not self._results:
            return
        query   = self._find_edit.text()
        replace = self._replace_edit.text()
        replaced = 0
        for idx in self._results:
            entry = self._entries[idx]
            old   = entry.text
            entry.text = entry.text.replace(query, replace)
            if entry.text != old:
                replaced += 1

        self.replaced_count += replaced
        self.entries_changed.emit()
        self._status_label.setText(f"Đã thay thế {replaced} dòng")
        self._search()
