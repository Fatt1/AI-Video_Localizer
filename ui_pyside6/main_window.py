# ui_pyside6/main_window.py
"""
MainWindow — CapCut-style layout:
  Left   (25%) : WarningPanel (short-duration SRT list + console log)
  Center (50%) : VideoPlayerWidget (video + transport bar)
  Right  (25%) : SubtitleEditorPanel (tools + inline edit)
  Bottom       : TimelineWidget (zoomable, draggable)
  Top          : Menu bar (File | Tools | Settings)
  Bottom bar   : Status bar (LED + message + progress bar)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from dialogs.add_subtitle_dialog import AddSubtitleDialog
from dialogs.find_replace_dialog import FindReplaceDialog
from models.subtitle_model import (
    SubtitleEntry,
    filter_duplicate_subtitles,
    get_short_duration_warnings,
    parse_srt,
    reindex,
    save_srt,
)
from widgets.subtitle_editor import SubtitleEditorPanel
from widgets.timeline import TimelineWidget
from widgets.video_player import VideoPlayerWidget
from widgets.warning_panel import WarningPanel


class SubtitleTimeEditCommand(QUndoCommand):
    """Command pattern for undoing/redoing subtitle timeline drags."""
    def __init__(self, main_window: "MainWindow", entry_index: int, old_s: int, old_e: int, new_s: int, new_e: int):
        super().__init__()
        self.main_window = main_window
        self.entry_index = entry_index
        self.old_s = old_s
        self.old_e = old_e
        self.new_s = new_s
        self.new_e = new_e
        self.setText(f"Sửa thời gian dòng #{entry_index}")

    def undo(self):
        entry = self.main_window._find_entry(self.entry_index)
        if entry:
            entry.start_ms = self.old_s
            entry.end_ms   = self.old_e
            self.main_window._refresh_timeline()
            self.main_window._refresh_warnings()
            self.main_window._set_status(f"Undo: Phục hồi thời gian dòng #{self.entry_index}")

    def redo(self):
        entry = self.main_window._find_entry(self.entry_index)
        if entry:
            entry.start_ms = self.new_s
            entry.end_ms   = self.new_e
            self.main_window._refresh_timeline()
            self.main_window._refresh_warnings()
            self.main_window._set_status(f"Redo: Sửa thời gian dòng #{self.entry_index}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Video Localizer")
        self.resize(1400, 860)
        self.setMinimumSize(1100, 700)

        # ── State ────────────────────────────────────────────────────────────
        self._entries:       list[SubtitleEntry] = []
        self._video_path:    str = ""
        self._srt_path:      str = ""
        self._ocr_region:    list[int] = [0, 0, 0, 0]
        self._selected_idx:  int | None = None
        self._active_worker  = None
        self._find_replace_dialog: FindReplaceDialog | None = None
        
        self._undo_stack = QUndoStack(self)

        self._build_ui()
        self._build_menu()
        self._build_statusbar()
        self._connect_signals()

        QTimer.singleShot(200, self._refresh_voices)

    def _init_splitter_sizes(self):
        """Set timeline to ~40% of window height after window is shown."""
        total_h = self._v_splitter.height()
        if total_h > 200:
            top_h      = int(total_h * 0.60)
            timeline_h = total_h - top_h
            self._v_splitter.setSizes([top_h, timeline_h])

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Vertical splitter: top (video+panels) | bottom (timeline) ──
        self._v_splitter = QSplitter(Qt.Orientation.Vertical)
        self._v_splitter.setHandleWidth(4)

        # TOP: Horizontal splitter Left | Center | Right
        self._top_widget = QWidget()
        top_layout = QVBoxLayout(self._top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setHandleWidth(3)

        # LEFT — Warning panel
        self._warning_panel = WarningPanel()
        self._warning_panel.setMinimumWidth(200)
        self._main_splitter.addWidget(self._warning_panel)

        # CENTER — Video player
        self._video_player = VideoPlayerWidget()
        self._video_player.setMinimumWidth(400)
        self._main_splitter.addWidget(self._video_player)

        # RIGHT — Subtitle editor panel
        self._editor_panel = SubtitleEditorPanel()
        self._editor_panel.setMinimumWidth(220)
        self._main_splitter.addWidget(self._editor_panel)

        # Set initial proportions: 22% | 53% | 25%
        self._main_splitter.setSizes([240, 680, 300])
        top_layout.addWidget(self._main_splitter)
        self._v_splitter.addWidget(self._top_widget)

        # BOTTOM: Timeline (~40% height)
        self._timeline = TimelineWidget()
        self._timeline.setMinimumHeight(100)
        self._v_splitter.addWidget(self._timeline)

        root_layout.addWidget(self._v_splitter)

        # Set vertical split: 60% top / 40% timeline
        # Will be adjusted once window is shown
        QTimer.singleShot(0, self._init_splitter_sizes)

    # ── Build menu ────────────────────────────────────────────────────────────
    def _build_menu(self):
        mb = self.menuBar()

        # ── File ──
        file_menu = mb.addMenu("&File")

        act_open = QAction("Mở Video...", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self._open_video)
        file_menu.addAction(act_open)

        act_load_srt = QAction("Load SRT...", self)
        act_load_srt.triggered.connect(self._load_srt)
        file_menu.addAction(act_load_srt)

        act_save_srt = QAction("Lưu SRT", self)
        act_save_srt.setShortcut(QKeySequence("Ctrl+S"))
        act_save_srt.triggered.connect(self._save_srt)
        file_menu.addAction(act_save_srt)

        act_save_as = QAction("Lưu SRT Thành...", self)
        act_save_as.triggered.connect(self._save_srt_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_exit = QAction("Thoát", self)
        act_exit.setShortcut(QKeySequence("Alt+F4"))
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ── Edit ──
        edit_menu = mb.addMenu("&Edit")
        
        act_undo = edit_menu.addAction("Undo")
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        act_undo.triggered.connect(self._undo_stack.undo)
        
        act_redo = edit_menu.addAction("Redo")
        act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        act_redo.triggered.connect(self._undo_stack.redo)

        # ── Tools ──
        tools_menu = mb.addMenu("&Tools")

        act_ocr_region = QAction("Chọn vùng OCR...", self)
        act_ocr_region.setCheckable(True)
        act_ocr_region.triggered.connect(self._toggle_ocr_region)
        self._act_ocr_region = act_ocr_region
        tools_menu.addAction(act_ocr_region)

        act_run_ocr = QAction("Chạy OCR Hardsub...", self)
        act_run_ocr.triggered.connect(lambda: self._editor_panel._on_run_ocr())
        tools_menu.addAction(act_run_ocr)

        tools_menu.addSeparator()

        act_find = QAction("Tìm & Thay thế SRT...", self)
        act_find.setShortcut(QKeySequence("Ctrl+H"))
        act_find.triggered.connect(self._open_find_replace)
        tools_menu.addAction(act_find)

        act_filter = QAction("Lọc lặp SRT", self)
        act_filter.triggered.connect(self._filter_duplicates)
        tools_menu.addAction(act_filter)

        tools_menu.addSeparator()

        act_norm_before = QAction("Chuẩn hóa trước dịch (Export Plain)...", self)
        act_norm_before.triggered.connect(self._normalize_before)
        tools_menu.addAction(act_norm_before)

        act_norm_after = QAction("Chuẩn hóa sau dịch (Merge SRT)...", self)
        act_norm_after.triggered.connect(self._normalize_after)
        tools_menu.addAction(act_norm_after)

    # ── Build status bar ──────────────────────────────────────────────────────
    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.setStyleSheet("QStatusBar { background:#0e0e1a; border-top:1px solid #2a2a3d; "
                         "color:#8080a0; font-size:11px; padding:0 8px; }")

        # LED indicator
        self._led = QLabel()
        self._led.setObjectName("status_led")
        self._led.setFixedSize(10, 10)
        self._led.setStyleSheet("border-radius:5px; background:#44ff88;")
        sb.addWidget(self._led)

        # Status message
        self._status_msg = QLabel("Ready")
        sb.addWidget(self._status_msg, stretch=1)

        # Progress bar (hidden when idle)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setFixedWidth(180)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.hide()
        sb.addPermanentWidget(self._progress_bar)

        # Cancel button
        self._btn_cancel_task = QPushButton("✕ Hủy")
        self._btn_cancel_task.setFixedHeight(22)
        self._btn_cancel_task.setStyleSheet(
            "QPushButton { background:#3d1a22; color:#ff6680; border:1px solid #6a2535;"
            " border-radius:4px; font-size:11px; padding:0 10px; }"
            "QPushButton:hover { background:#e94560; color:white; }"
        )
        self._btn_cancel_task.hide()
        self._btn_cancel_task.clicked.connect(self._cancel_task)
        sb.addPermanentWidget(self._btn_cancel_task)

    # ── Connect all signals ───────────────────────────────────────────────────
    def _connect_signals(self):
        # Video player
        self._video_player.time_changed_ms.connect(self._on_video_time_changed)
        self._video_player.duration_changed.connect(self._timeline.set_duration_ms)
        self._video_player.ocr_region_selected.connect(self._on_ocr_region_selected)

        # Timeline
        self._timeline.subtitle_selected.connect(self._on_timeline_subtitle_selected)
        self._timeline.subtitle_double_clicked.connect(self._on_timeline_double_click)
        self._timeline.seek_requested.connect(self._on_timeline_seek)
        self._timeline.subtitle_time_changed.connect(self._on_subtitle_time_changed)
        self._timeline.context_add_before.connect(self._on_add_before)
        self._timeline.context_add_after.connect(self._on_add_after)
        self._timeline.context_delete.connect(self._on_delete)

        # Warning panel
        self._warning_panel.seek_to_subtitle.connect(self._video_player.seek_to_ms)

        # Editor panel signals
        self._editor_panel.subtitle_applied.connect(self._on_subtitle_applied)
        self._editor_panel.subtitle_canceled.connect(self._on_subtitle_edit_canceled)
        self._editor_panel.ocr_region_requested.connect(self._toggle_ocr_region)
        self._editor_panel.run_ocr_requested.connect(self._run_ocr)
        self._editor_panel.run_stt_requested.connect(self._run_stt)
        self._editor_panel.run_dubbing_requested.connect(self._run_dubbing)
        self._editor_panel.voices_refresh.connect(self._refresh_voices)
        self._editor_panel.normalize_before_requested.connect(self._normalize_before)
        self._editor_panel.normalize_after_requested.connect(self._normalize_after)
        self._editor_panel.filter_dup_requested.connect(self._filter_duplicates)

    # ══════════════════════════════════════════════════════════════════════════
    # FILE OPERATIONS
    # ══════════════════════════════════════════════════════════════════════════

    def _open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn Video",
            str(Path.home()),
            "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm);;All Files (*)"
        )
        if not path:
            return
        self._video_path = path
        ok = self._video_player.load_video(path)
        if ok:
            self._set_status(f"Đã mở: {Path(path).name}")
            # Auto-suggest SRT path
            srt_candidate = str(Path(path).with_suffix(".srt"))
            if Path(srt_candidate).exists():
                reply = QMessageBox.question(
                    self, "Load SRT?",
                    f"Tìm thấy file SRT:\n{srt_candidate}\n\nLoad vào timeline?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._load_srt_from(srt_candidate)

            # Set duration after a small delay (VLC needs time to parse)
            QTimer.singleShot(800, self._sync_video_duration)
        else:
            self._set_status("Lỗi: Không thể load video (kiểm tra VLC đã cài chưa)")

    def _sync_video_duration(self):
        dur = self._video_player.get_duration_ms()
        if dur > 0:
            self._timeline.set_duration_ms(dur)
        else:
            # retry
            QTimer.singleShot(800, self._sync_video_duration)

    def _load_srt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load SRT",
            str(Path(self._video_path).parent) if self._video_path else str(Path.home()),
            "SRT Files (*.srt);;All Files (*)"
        )
        if path:
            self._load_srt_from(path)

    def _load_srt_from(self, path: str):
        try:
            self._entries  = parse_srt(path)
            self._srt_path = path
            self._refresh_timeline()
            self._refresh_warnings()
            count = len(self._entries)
            self._set_status(f"Đã load SRT: {Path(path).name} ({count} dòng)")
            self._warning_panel.append_log(f"[File] Load SRT: {path} — {count} dòng")

            # If no video loaded yet, estimate duration from SRT end times
            if not self._video_path and self._entries:
                max_end = max(e.end_ms for e in self._entries)
                self._timeline.set_duration_ms(max_end + 2000)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi Load SRT", str(e))

    def _save_srt(self):
        if not self._srt_path:
            self._save_srt_as()
            return
        self._do_save_srt(self._srt_path)

    def _save_srt_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu SRT thành",
            self._srt_path or str(Path.home()),
            "SRT Files (*.srt)"
        )
        if path:
            self._srt_path = path
            self._do_save_srt(path)

    def _do_save_srt(self, path: str):
        try:
            save_srt(self._entries, path)
            self._set_status(f"Đã lưu SRT: {Path(path).name}")
            self._warning_panel.append_log(f"[File] Lưu SRT: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi Lưu SRT", str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # VIDEO / TIMELINE SYNC
    # ══════════════════════════════════════════════════════════════════════════

    def _on_video_time_changed(self, ms: int):
        self._timeline.set_current_ms(ms)
        # Auto-highlight subtitle at current position
        for i, e in enumerate(self._entries):
            if e.start_ms <= ms <= e.end_ms:
                if self._selected_idx != e.index:
                    self._selected_idx = e.index
                    self._timeline.set_selected(e.index)
                break

    def _on_timeline_seek(self, ms: int):
        self._video_player.seek_to_ms(ms)

    def _on_timeline_subtitle_selected(self, entry_index: int):
        self._selected_idx = entry_index
        entry = self._find_entry(entry_index)
        if entry:
            self._video_player.seek_to_ms(entry.start_ms)

    def _on_timeline_double_click(self, entry_index: int):
        self._video_player.pause()
        entry = self._find_entry(entry_index)
        if entry:
            self._editor_panel.load_entry_for_edit(entry)
            self._set_status(f"Đang chỉnh sửa subtitle #{entry.index}")

    def _on_subtitle_time_changed(self, entry_index: int, old_start: int, old_end: int, new_start: int, new_end: int):
        cmd = SubtitleTimeEditCommand(self, entry_index, old_start, old_end, new_start, new_end)
        self._undo_stack.push(cmd)

    # ══════════════════════════════════════════════════════════════════════════
    # SUBTITLE EDIT (from right panel)
    # ══════════════════════════════════════════════════════════════════════════

    def _on_subtitle_applied(self, index: int, start_ms: int, end_ms: int, text: str):
        entry = self._find_entry(index)
        if entry:
            entry.start_ms = start_ms
            entry.end_ms   = end_ms
            entry.text     = text
            self._refresh_timeline()
            self._refresh_warnings()
            self._editor_panel.clear_edit_form()
            self._set_status(f"Đã lưu subtitle #{index}")
            self._warning_panel.append_log(f"[Edit] Cập nhật subtitle #{index}")

    def _on_subtitle_edit_canceled(self):
        self._editor_panel.clear_edit_form()

    # ══════════════════════════════════════════════════════════════════════════
    # SUBTITLE ADD / DELETE (from timeline context menu)
    # ══════════════════════════════════════════════════════════════════════════

    def _on_add_before(self, entry_index: int):
        entry = self._find_entry(entry_index)
        dialog = AddSubtitleDialog(
            default_start_ms=self._video_player.get_current_ms(),
            parent=self
        )
        if dialog.exec() and dialog.result_entry:
            new_entry = dialog.result_entry
            if entry:
                pos = self._entries.index(entry)
                self._entries.insert(pos, new_entry)
            else:
                self._entries.insert(0, new_entry)
            reindex(self._entries)
            self._refresh_timeline()
            self._refresh_warnings()

    def _on_add_after(self, entry_index: int):
        entry = self._find_entry(entry_index)
        dialog = AddSubtitleDialog(
            default_start_ms=self._video_player.get_current_ms(),
            parent=self
        )
        if dialog.exec() and dialog.result_entry:
            new_entry = dialog.result_entry
            if entry:
                pos = self._entries.index(entry)
                self._entries.insert(pos + 1, new_entry)
            else:
                self._entries.append(new_entry)
            reindex(self._entries)
            self._refresh_timeline()
            self._refresh_warnings()

    def _on_delete(self, entry_index: int):
        entry = self._find_entry(entry_index)
        if not entry:
            return
        reply = QMessageBox.question(
            self, "Xóa Subtitle",
            f"Xóa subtitle #{entry.index}?\n\"{entry.text[:60]}\"",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._entries.remove(entry)
            reindex(self._entries)
            self._refresh_timeline()
            self._refresh_warnings()

    # ══════════════════════════════════════════════════════════════════════════
    # OCR REGION SELECTION
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_ocr_region(self):
        if not self._video_path:
            QMessageBox.information(self, "OCR", "Hãy mở video trước.")
            return
        self._video_player.pause()
        self._video_player.enter_ocr_mode()
        self._set_status("🖱 Kéo chuột trên video để chọn vùng subtitle — Nhấn Esc để hủy")

    def _on_ocr_region_selected(self, region: list):
        self._ocr_region = region
        label = f"Vùng OCR: [{region[0]}, {region[1]}, {region[2]}, {region[3]}]"
        self._editor_panel.set_ocr_region_label(label)
        self._set_status(label)
        self._warning_panel.append_log(f"[OCR] Vùng chọn: {region}")
        if hasattr(self, "_act_ocr_region"):
            self._act_ocr_region.setChecked(False)

    # ══════════════════════════════════════════════════════════════════════════
    # WORKER TASKS: OCR / STT / Dubbing / SRT Tools
    # ══════════════════════════════════════════════════════════════════════════

    def _run_ocr(self, lang_code: str, fps: float, out_srt_path: str):
        if not self._video_path:
            QMessageBox.warning(self, "OCR", "Chưa mở video.")
            return

        if not out_srt_path:
            out_srt_path = str(Path(self._video_path).with_suffix("")) + "_ocr.srt"

        from workers.ocr_worker import OcrWorker
        worker = OcrWorker(
            video_path=self._video_path,
            crop_region=self._ocr_region if any(self._ocr_region) else [0, 0, 0, 0],
            fps=fps,
            output_srt=out_srt_path,
            lang=lang_code,
        )
        self._start_worker(worker, "OCR")

        def on_finished(success: bool, result: str):
            if success and "|" in result:
                srt_path, count = result.split("|", 1)
                QTimer.singleShot(0, lambda: self._load_srt_from(srt_path))
                self._set_status(f"✅ OCR xong: {count} dòng → {Path(srt_path).name}")

        worker.task_finished.connect(on_finished)

    def _run_stt(self, model_key: str, language: str, silence_gap: float, use_diarization: bool):
        if not self._video_path:
            QMessageBox.warning(self, "STT", "Chưa mở video.")
            return

        out_srt = str(Path(self._video_path).with_suffix("")) + "_stt.srt"

        from workers.stt_worker import SttWorker
        worker = SttWorker(
            video_path=self._video_path,
            output_srt=out_srt,
            model_key=model_key,
            language=language,
            silence_gap_s=silence_gap,
            use_diarization=use_diarization,
        )
        self._start_worker(worker, "STT")

        def on_finished(success: bool, result: str):
            if success:
                QTimer.singleShot(0, lambda: self._load_srt_from(result))

        worker.task_finished.connect(on_finished)

    def _run_dubbing(self, voice_id: str, capcut_project: str, rate: float):
        if not self._srt_path or not self._entries:
            QMessageBox.warning(self, "Dubbing", "Chưa có SRT. Hãy load hoặc tạo SRT trước.")
            return
        if not voice_id:
            QMessageBox.warning(self, "Dubbing", "Chưa chọn voice clone.")
            return
        if not capcut_project:
            QMessageBox.warning(self, "Dubbing", "Chưa nhập tên project CapCut.")
            return

        # Save latest SRT to disk before dubbing
        self._do_save_srt(self._srt_path)

        from workers.dubbing_worker import DubbingWorker
        worker = DubbingWorker(
            srt_path=self._srt_path,
            voice_id=voice_id,
            capcut_project_name=capcut_project,
            speech_rate=rate,
        )
        self._start_worker(worker, "Dubbing")

    def _normalize_before(self):
        """Chuẩn hóa trước khi dịch: export plain subtitle."""
        if not self._srt_path and not self._entries:
            QMessageBox.warning(self, "Chuẩn hóa", "Chưa có SRT.")
            return

        srt_path = self._srt_path
        if not srt_path:
            srt_path, _ = QFileDialog.getOpenFileName(
                self, "Chọn SRT nguồn", str(Path.home()), "SRT Files (*.srt)"
            )
        if not srt_path:
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Lưu plain subtitle thành",
            str(Path(srt_path).with_suffix("")) + "_plain.txt",
            "Text Files (*.txt)"
        )
        if not out_path:
            return

        from workers.dubbing_worker import SrtToolWorker
        from services.srt_merge_service import srt_to_plain_subtitle

        worker = SrtToolWorker(
            func=srt_to_plain_subtitle,
            kwargs={"srt_path": srt_path, "output_path": out_path},
            task_name="Chuẩn hóa trước dịch",
        )
        self._start_worker(worker, "Chuẩn hóa trước dịch")

    def _normalize_after(self):
        """Chuẩn hóa sau khi dịch: merge plain + ocr.srt → vietsub."""
        plain_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file plain đã dịch",
            str(Path(self._srt_path).parent) if self._srt_path else str(Path.home()),
            "Text Files (*.txt);;All Files (*)"
        )
        if not plain_path:
            return

        ocr_srt, _ = QFileDialog.getOpenFileName(
            self, "Chọn ocr.srt (nguồn timestamp)",
            str(Path(plain_path).parent),
            "SRT Files (*.srt)"
        )
        if not ocr_srt:
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Lưu vietsub thành",
            str(Path(plain_path).with_suffix("")) + "_vietsub.srt",
            "SRT Files (*.srt)"
        )
        if not out_path:
            return

        from workers.dubbing_worker import SrtToolWorker
        from services.srt_merge_service import merge_plain_to_srt

        worker = SrtToolWorker(
            func=merge_plain_to_srt,
            kwargs={
                "translated_plain_path": plain_path,
                "ocr_srt_path": ocr_srt,
                "output_srt_path": out_path,
            },
            task_name="Chuẩn hóa sau dịch",
        )
        self._start_worker(worker, "Chuẩn hóa sau dịch")

        def on_finished(success: bool, result: str):
            if success:
                reply = QMessageBox.question(
                    self, "Merge xong",
                    f"Đã tạo vietsub:\n{result}\n\nLoad vào timeline?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    QTimer.singleShot(0, lambda: self._load_srt_from(result))

        worker.task_finished.connect(on_finished)

    def _filter_duplicates(self):
        if not self._entries:
            QMessageBox.information(self, "Lọc lặp", "Danh sách SRT đang trống.")
            return
        original_count = len(self._entries)
        self._entries  = filter_duplicate_subtitles(self._entries)
        removed = original_count - len(self._entries)
        self._refresh_timeline()
        self._refresh_warnings()
        self._set_status(f"Lọc lặp: đã xóa {removed} dòng, còn lại {len(self._entries)} dòng")
        self._warning_panel.append_log(f"[Filter] Lọc lặp SRT: -{removed} dòng")

    # ── Find & Replace ────────────────────────────────────────────────────────
    def _open_find_replace(self):
        if not self._entries:
            QMessageBox.information(self, "Tìm & Thay thế", "SRT đang trống.")
            return
        if self._find_replace_dialog is None or not self._find_replace_dialog.isVisible():
            self._find_replace_dialog = FindReplaceDialog(self._entries, parent=self)
            self._find_replace_dialog.entries_changed.connect(self._on_find_replace_changed)
        self._find_replace_dialog.show()
        self._find_replace_dialog.raise_()

    def _on_find_replace_changed(self):
        self._refresh_timeline()
        self._refresh_warnings()

    # ── Voice refresh ─────────────────────────────────────────────────────────
    def _refresh_voices(self):
        try:
            from services.tts_service import list_voice_clones
            voices = list_voice_clones()
            self._editor_panel.set_voices(voices)
            if voices:
                self._warning_panel.append_log(f"[Voices] {len(voices)} voice clone(s) tìm thấy")
        except Exception as e:
            self._warning_panel.append_log(f"[Voices] Không load được: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # WORKER MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _start_worker(self, worker, task_name: str):
        if self._active_worker and self._active_worker.isRunning():
            QMessageBox.warning(self, "Bận", "Đang có task chạy. Hủy trước khi bắt đầu.")
            return

        self._active_worker = worker
        self._set_busy(True)
        self._set_status(f"⏳ Đang chạy: {task_name}...")

        worker.log_emitted.connect(self._warning_panel.append_log)
        worker.progress_updated.connect(self._on_worker_progress)
        worker.task_finished.connect(lambda ok, msg: self._on_worker_finished(ok, msg, task_name))
        worker.error_occurred.connect(lambda msg: self._on_worker_error(msg, task_name))

        worker.start()

    def _cancel_task(self):
        if self._active_worker:
            self._active_worker.cancel()
            self._warning_panel.append_log("[Task] Yêu cầu hủy task...")
            self._set_status("Đang hủy...")

    def _on_worker_progress(self, percent: int, message: str):
        self._progress_bar.setValue(percent)
        self._set_status(message)

    def _on_worker_finished(self, success: bool, message: str, task_name: str):
        self._set_busy(False)
        if success:
            self._set_status(f"✅ {task_name} hoàn thành")
        else:
            self._set_status(f"❌ {task_name} thất bại: {message[:80]}")
            QMessageBox.warning(self, f"{task_name} Lỗi", message)
        self._active_worker = None

    def _on_worker_error(self, message: str, task_name: str):
        self._set_busy(False)
        self._warning_panel.append_log(f"[Error] {task_name}: {message[:200]}")
        self._active_worker = None

    # ══════════════════════════════════════════════════════════════════════════
    # REFRESH HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_timeline(self):
        self._timeline.set_entries(self._entries)
        if self._selected_idx is not None:
            self._timeline.set_selected(self._selected_idx)

    def _refresh_warnings(self):
        short_entries = get_short_duration_warnings(self._entries, threshold_ms=1000)
        self._warning_panel.update_warnings(short_entries)

    def _find_entry(self, index: int) -> SubtitleEntry | None:
        return next((e for e in self._entries if e.index == index), None)

    # ══════════════════════════════════════════════════════════════════════════
    # STATUS / BUSY HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _set_status(self, msg: str):
        self._status_msg.setText(msg)

    def _set_busy(self, busy: bool):
        self._progress_bar.setVisible(busy)
        self._btn_cancel_task.setVisible(busy)
        self._editor_panel.set_busy(busy)
        if not busy:
            self._progress_bar.setValue(0)

    # ══════════════════════════════════════════════════════════════════════════
    # CLOSE
    # ══════════════════════════════════════════════════════════════════════════

    def closeEvent(self, event: QCloseEvent):
        if self._active_worker and self._active_worker.isRunning():
            reply = QMessageBox.question(
                self, "Thoát",
                "Đang có task đang chạy. Bạn có chắc muốn thoát?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._active_worker.cancel()
            self._active_worker.wait(2000)
        super().closeEvent(event)
