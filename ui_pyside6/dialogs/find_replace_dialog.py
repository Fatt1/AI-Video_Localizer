# ui_pyside6/dialogs/find_replace_dialog.py
"""
Find & Replace dialog — similar to C# FindReplaceSubtitleDialog.
Supports:
  - Exact text search
  - Case-insensitive option
  - Fuzzy match option
  - Live results list showing all matching lines
  - Replace one / Replace all
  - Navigate through results
"""
from __future__ import annotations

from difflib import SequenceMatcher

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
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
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self._entries = entries
        self._results: list[int] = []   # indices into _entries
        self._result_pos: int = -1
        self.replaced_count = 0
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # ── Find field ─────────────────────────────────────────────────────────
        find_row = QHBoxLayout()
        lbl_find = QLabel("Tìm:")
        lbl_find.setFixedWidth(70)
        find_row.addWidget(lbl_find)
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("Nhập văn bản cần tìm...")
        self._find_edit.textChanged.connect(self._on_find_changed)
        find_row.addWidget(self._find_edit, stretch=1)
        lay.addLayout(find_row)

        # ── Replace field ──────────────────────────────────────────────────────
        rep_row = QHBoxLayout()
        lbl_rep = QLabel("Thay bằng:")
        lbl_rep.setFixedWidth(70)
        rep_row.addWidget(lbl_rep)
        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("Văn bản thay thế...")
        rep_row.addWidget(self._replace_edit, stretch=1)
        lay.addLayout(rep_row)

        # ── Options ────────────────────────────────────────────────────────────
        opts = QHBoxLayout()
        self._case_cb  = QCheckBox("Phân biệt hoa/thường")
        self._fuzzy_cb = QCheckBox("Tìm gần đúng (fuzzy ≥ 70%)")
        self._fuzzy_cb.setChecked(True)
        self._case_cb.stateChanged.connect(lambda _: self._search())
        self._fuzzy_cb.stateChanged.connect(lambda _: self._search())
        opts.addWidget(self._case_cb)
        opts.addWidget(self._fuzzy_cb)
        opts.addStretch()
        lay.addLayout(opts)

        # ── Status label ───────────────────────────────────────────────────────
        self._status_label = QLabel("Nhập từ cần tìm để bắt đầu")
        self._status_label.setStyleSheet("color:#7070a0; font-size:11px;")
        lay.addWidget(self._status_label)

        # ── Results list ───────────────────────────────────────────────────────
        results_label = QLabel("Kết quả trùng khớp:")
        results_label.setStyleSheet("color:#9090b0; font-size:11px; font-weight:600;")
        lay.addWidget(results_label)

        self._results_list = QListWidget()
        self._results_list.setStyleSheet(
            "QListWidget {"
            "  background:#0e0e1a;"
            "  border:1px solid #2a2a3d;"
            "  border-radius:4px;"
            "  font-size:12px;"
            "  color:#c0c0d8;"
            "}"
            "QListWidget::item {"
            "  padding:5px 8px;"
            "  border-bottom:1px solid #1a1a2e;"
            "}"
            "QListWidget::item:selected {"
            "  background:#2a2a5a;"
            "  color:#ffffff;"
            "}"
            "QListWidget::item:hover {"
            "  background:#1a1a3a;"
            "}"
        )
        self._results_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._results_list.currentRowChanged.connect(self._on_result_selected)
        lay.addWidget(self._results_list, stretch=1)

        # ── Nav + action buttons ───────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_prev    = QPushButton("◀ Trước")
        self._btn_next    = QPushButton("Tiếp ▶")
        self._btn_replace = QPushButton("Thay 1")
        self._btn_all     = QPushButton("Thay tất cả")
        self._btn_close   = QPushButton("Đóng")

        self._btn_prev.setToolTip("Đến kết quả trước")
        self._btn_next.setToolTip("Đến kết quả tiếp theo")
        self._btn_replace.setToolTip("Thay thế kết quả đang chọn")
        self._btn_all.setToolTip("Thay thế tất cả kết quả")

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
        self._results_list.clear()

        if not query:
            self._status_label.setText("Nhập từ cần tìm để bắt đầu")
            self._set_btns_enabled(False)
            return

        case_sens = self._case_cb.isChecked()
        fuzzy     = self._fuzzy_cb.isChecked()

        for i, entry in enumerate(self._entries):
            if self._match(query, entry.text, case_sens, fuzzy):
                self._results.append(i)
                # Build display text: "#index  hh:mm:ss  text preview"
                start_s = entry.start_ms // 1000
                h, m, s = start_s // 3600, (start_s % 3600) // 60, start_s % 60
                time_str = f"{h:02d}:{m:02d}:{s:02d}"
                preview = entry.text.replace("\n", " ").strip()
                if len(preview) > 60:
                    preview = preview[:57] + "..."
                item = QListWidgetItem(f"#{entry.index:>3}  [{time_str}]  {preview}")
                item.setData(Qt.ItemDataRole.UserRole, i)  # store index into _entries
                # Highlight matched items with a subtle tint
                item.setForeground(QBrush(QColor("#e0e0ff")))
                self._results_list.addItem(item)

        count = len(self._results)
        if count == 0:
            self._status_label.setText(f"Không tìm thấy '{query}'")
            self._set_btns_enabled(False)
            no_result_item = QListWidgetItem("(Không có kết quả nào)")
            no_result_item.setFlags(Qt.ItemFlag.NoItemFlags)
            no_result_item.setForeground(QBrush(QColor("#505070")))
            self._results_list.addItem(no_result_item)
        else:
            self._result_pos = 0
            self._status_label.setText(f"Tìm thấy {count} kết quả — chọn 1 dòng để thay thế")
            self._set_btns_enabled(True)
            # Auto-select first result in list
            self._results_list.setCurrentRow(0)

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

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_result_selected(self, row: int):
        """Sync _result_pos when user clicks a row in the list."""
        if row < 0 or row >= len(self._results):
            return
        self._result_pos = row
        self._update_pos_label()

    def _go_next(self):
        if not self._results:
            return
        self._result_pos = (self._result_pos + 1) % len(self._results)
        self._results_list.setCurrentRow(self._result_pos)
        self._update_pos_label()

    def _go_prev(self):
        if not self._results:
            return
        self._result_pos = (self._result_pos - 1) % len(self._results)
        self._results_list.setCurrentRow(self._result_pos)
        self._update_pos_label()

    def _update_pos_label(self):
        total = len(self._results)
        pos   = self._result_pos + 1
        self._status_label.setText(f"Kết quả {pos}/{total} — chọn 1 dòng để thay thế")

    # ── Replace ───────────────────────────────────────────────────────────────

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
        # Re-search to refresh results list
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
