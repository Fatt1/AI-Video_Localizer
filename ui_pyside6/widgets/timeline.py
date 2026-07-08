# ui_pyside6/widgets/timeline.py
"""
TimelineWidget — CapCut-style custom QPainter timeline.

Tracks:
  Row 0: Video track (solid bar for total duration)
  Row 1: SRT track   (draggable/resizable colored blocks)

Features:
  - Zoom: Ctrl+Scroll or +/- buttons
  - Playhead: red vertical line, draggable
  - Click block → select + seek
  - Double-click block → request inline edit + pause
  - Drag block body → shift start/end times
  - Drag block left/right edge → resize start or end
  - Right-click block → context menu (Add before, Add after, Delete)
  - Time ruler with tick marks and labels
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import (
    QPoint, QRect, QRectF, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QLinearGradient,
    QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea, QHBoxLayout, QLabel, QMenu, QPushButton,
    QScrollBar, QSizePolicy, QVBoxLayout, QWidget,
)

from models.subtitle_model import SubtitleEntry

# ─── Layout constants ──────────────────────────────────────────────────────────
RULER_H     = 28   # px, time ruler height
TRACK_H     = 36   # px, each track row height
TRACK_GAP   = 4    # px, gap between tracks
HEADER_W    = 72   # px, left column for track labels
EDGE_GRAB   = 8    # px, edge grab zone for resizing

_COLORS = {
    "bg":              QColor("#12121e"),
    "ruler_bg":        QColor("#1a1a2e"),
    "ruler_tick_maj":  QColor("#404060"),
    "ruler_tick_min":  QColor("#282838"),
    "ruler_text":      QColor("#606080"),
    "header_bg":       QColor("#0e0e1a"),
    "header_text":     QColor("#6060a0"),
    "video_fill":      QColor("#1e3258"),
    "video_stroke":    QColor("#2a4a80"),
    "srt_fill":        QColor("#8a5600"),
    "srt_fill_active": QColor("#c07800"),
    "srt_fill_hover":  QColor("#a06400"),
    "srt_stroke":      QColor("#f5a623"),
    "srt_stroke_act":  QColor("#ffc040"),
    "srt_text":        QColor("#ffe0a0"),
    "playhead":        QColor("#e94560"),
    "playhead_head":   QColor("#ff5575"),
}

class _Block:
    """Internal representation of an SRT block on the timeline."""
    __slots__ = ("entry", "x", "w", "row", "hovered", "selected")

    def __init__(self, entry: SubtitleEntry, x: float, w: float, row: int = 0):
        self.entry    = entry
        self.x        = x      # float px
        self.w        = w      # float px
        self.row      = row
        self.hovered  = False
        self.selected = False


class TimelineCanvas(QWidget):
    """
    The actual drawable area (inside a scroll view).
    Width = duration_ms / 1000 * pixels_per_second + HEADER_W
    """

    # Signals → MainWindow handles
    subtitle_selected       = Signal(int)   # entry.index
    subtitle_double_clicked = Signal(int)   # entry.index
    seek_requested          = Signal(int)   # ms
    subtitle_time_changed   = Signal(int, int, int, int, int)  # (index, old_start, old_end, new_start, new_end)
    context_add_before      = Signal(int)   # entry.index
    context_add_after       = Signal(int)   # entry.index
    context_delete          = Signal(int)   # entry.index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries:          list[SubtitleEntry] = []
        self._blocks:           list[_Block]        = []
        self._duration_ms:      int   = 0
        self._current_ms:       int   = 0
        self._pixels_per_sec:   float = 100.0   # default zoom
        self._selected_idx:     Optional[int]   = None  # entry index

        # Interaction state
        self._drag_block:       Optional[_Block] = None
        self._drag_mode:        str = ""   # "move" | "left" | "right"
        self._drag_start_x:     int = 0
        self._drag_block_orig_start: int = 0
        self._drag_block_orig_end:   int = 0

        self._playhead_dragging: bool = False
        self._hover_block:      Optional[_Block] = None
        self._scroll_offset:    int = 0   # horizontal scroll offset in pixels
        self._srt_lanes:        int = 1

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        # Fonts
        self._font_ruler = QFont("Segoe UI", 9)
        self._font_block = QFont("Segoe UI", 9)
        self._font_track = QFont("Segoe UI", 9, QFont.Weight.Bold)

    def set_scroll_offset(self, offset: int):
        self._scroll_offset = offset
        self.update()

    # ── Public API ────────────────────────────────────────────────────────────
    def set_entries(self, entries: list[SubtitleEntry]):
        self._entries = entries
        self._rebuild_blocks()
        self.update()

    def set_duration_ms(self, ms: int):
        self._duration_ms = max(0, ms)
        self._update_size()
        self.update()

    def set_current_ms(self, ms: int):
        self._current_ms = max(0, ms)
        self.update()

    def set_pixels_per_sec(self, pps: float):
        self._pixels_per_sec = max(10.0, min(2000.0, pps))
        self._rebuild_blocks()
        self._update_size()
        self.update()

    def set_selected(self, entry_index: Optional[int]):
        self._selected_idx = entry_index
        for b in self._blocks:
            b.selected = (b.entry.index == entry_index)
        self.update()

    @property
    def pixels_per_sec(self) -> float:
        return self._pixels_per_sec

    # ── Layout helpers ────────────────────────────────────────────────────────
    def _ms_to_x(self, ms: int) -> float:
        return HEADER_W + (ms / 1000.0) * self._pixels_per_sec

    def _x_to_ms(self, x: float) -> int:
        return int((x - HEADER_W) / self._pixels_per_sec * 1000)

    def _total_width(self) -> int:
        dur_px = int((self._duration_ms / 1000.0) * self._pixels_per_sec)
        return HEADER_W + dur_px + 200  # padding right

    def _srt_track_y(self) -> int:
        return RULER_H + TRACK_H + TRACK_GAP

    def _video_track_y(self) -> int:
        return RULER_H

    def _update_size(self):
        total_h = RULER_H + TRACK_H + TRACK_GAP + (self._srt_lanes * TRACK_H) + 20
        self.setMinimumSize(self._total_width(), total_h)

    def _rebuild_blocks(self):
        self._blocks = []
        rows_end_time = []

        # Sort entries by start_ms to compute overlapping lanes correctly
        sorted_entries = sorted(self._entries, key=lambda e: e.start_ms)

        for e in sorted_entries:
            x = self._ms_to_x(e.start_ms)
            w = max(4.0, (e.end_ms - e.start_ms) / 1000.0 * self._pixels_per_sec)

            row = 0
            placed = False
            for i, end_time in enumerate(rows_end_time):
                if e.start_ms >= end_time:
                    rows_end_time[i] = e.end_ms
                    row = i
                    placed = True
                    break

            if not placed:
                row = len(rows_end_time)
                rows_end_time.append(e.end_ms)

            b = _Block(e, x, w, row=row)
            b.selected = (e.index == self._selected_idx)
            self._blocks.append(b)

        self._srt_lanes = max(1, len(rows_end_time))

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Only repaint the exposed region
        clip = event.rect()
        p.fillRect(clip, _COLORS["bg"])

        self._draw_ruler(p, clip)
        self._draw_video_track(p, clip)
        self._draw_srt_track(p, clip)
        self._draw_playhead(p, clip)
        
        # Finally, draw fixed headers (sticky on the left)
        self._draw_headers(p)

    def _draw_ruler(self, p: QPainter, rect: QRect):
        p.fillRect(0, 0, rect.width(), RULER_H, _COLORS["ruler_bg"])
        p.setPen(QPen(QColor("#2a2a40"), 1))
        p.drawLine(0, RULER_H - 1, rect.width(), RULER_H - 1)

        if self._duration_ms <= 0:
            return

        p.setFont(self._font_ruler)

        # Choose tick interval based on zoom
        pps = self._pixels_per_sec
        # Major ticks: prefer intervals of 1s, 5s, 10s, 30s, 60s, etc.
        candidates = [0.1, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
        major_interval_s = 1.0
        for c in candidates:
            if pps * c >= 60:
                major_interval_s = c
                break
        minor_interval_s = major_interval_s / 5.0

        total_s = self._duration_ms / 1000.0

        # Draw minor ticks
        p.setPen(QPen(_COLORS["ruler_tick_min"], 1))
        t = 0.0
        while t <= total_s + minor_interval_s:
            x = int(self._ms_to_x(int(t * 1000)))
            if x > HEADER_W and x < rect.width():
                p.drawLine(x, RULER_H - 6, x, RULER_H - 1)
            t += minor_interval_s

        # Draw major ticks + labels
        p.setPen(QPen(_COLORS["ruler_tick_maj"], 1))
        p.setFont(self._font_ruler)
        t = 0.0
        while t <= total_s + major_interval_s:
            x = int(self._ms_to_x(int(t * 1000)))
            if x > HEADER_W - 10 and x < rect.width():
                p.setPen(QPen(_COLORS["ruler_tick_maj"], 1))
                p.drawLine(x, RULER_H - 12, x, RULER_H - 1)
                # Label
                label = self._format_ruler_time(t)
                p.setPen(QPen(_COLORS["ruler_text"]))
                p.drawText(x + 3, RULER_H - 12, label)
            t += major_interval_s

    def _format_ruler_time(self, seconds: float) -> str:
        total_s = int(seconds)
        h, rem  = divmod(total_s, 3600)
        m, s    = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _draw_video_track(self, p: QPainter, rect: QRect):
        y = self._video_track_y()

        if self._duration_ms <= 0:
            return

        # Video bar
        x_start = self._ms_to_x(0)
        x_end   = self._ms_to_x(self._duration_ms)
        bar_rect = QRectF(x_start, y + 4, x_end - x_start, TRACK_H - 8)

        grad = QLinearGradient(bar_rect.topLeft(), bar_rect.bottomLeft())
        grad.setColorAt(0, QColor("#2a4878"))
        grad.setColorAt(1, QColor("#1a3058"))
        p.setBrush(grad)
        p.setPen(QPen(_COLORS["video_stroke"], 1))
        p.drawRoundedRect(bar_rect, 3, 3)

        # Label
        p.setPen(QPen(QColor("#8090c0")))
        p.setFont(self._font_block)
        p.drawText(int(bar_rect.x()) + 6, int(bar_rect.y()),
                   int(bar_rect.width()) - 12, int(bar_rect.height()),
                   Qt.AlignmentFlag.AlignVCenter, "Video")

    def _draw_srt_track(self, p: QPainter, rect: QRect):
        y = self._srt_track_y()

        # Track background
        p.fillRect(QRectF(HEADER_W, y, rect.width(), TRACK_H * self._srt_lanes), QColor("#0f0f1c"))

        for block in self._blocks:
            self._draw_block(p, block, y)

    def _draw_block(self, p: QPainter, block: _Block, track_y: int):
        x = block.x
        w = block.w
        bh = TRACK_H - 6
        by = track_y + (block.row * TRACK_H) + 3

        if x + w < self._scroll_offset + HEADER_W or x > self._scroll_offset + self.width():
            return  # off-screen, skip

        br = QRectF(x, by, max(2, w), bh)

        # Choose colors
        if block.selected:
            fill   = _COLORS["srt_fill_active"]
            stroke = _COLORS["srt_stroke_act"]
        elif block.hovered:
            fill   = _COLORS["srt_fill_hover"]
            stroke = _COLORS["srt_stroke"]
        else:
            fill   = _COLORS["srt_fill"]
            stroke = _COLORS["srt_stroke"]

        # Gradient fill
        grad = QLinearGradient(br.topLeft(), br.bottomLeft())
        grad.setColorAt(0, fill.lighter(130))
        grad.setColorAt(1, fill)
        p.setBrush(grad)
        p.setPen(QPen(stroke, 1.5))
        p.drawRoundedRect(br, 3, 3)

        # Text
        if br.width() > 20:
            p.setPen(QPen(_COLORS["srt_text"]))
            p.setFont(self._font_block)
            text = block.entry.text.replace("\n", " ")
            p.drawText(
                int(br.x()) + 5, int(br.y()),
                int(br.width()) - 10, int(br.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text
            )

        # Edge grab indicators when hovered
        if block.hovered or block.selected:
            edge_color = QColor("#ffffff60")
            p.fillRect(QRectF(br.x(), by, EDGE_GRAB, bh), edge_color)
            p.fillRect(QRectF(br.right() - EDGE_GRAB, by, EDGE_GRAB, bh), edge_color)

    def _draw_playhead(self, p: QPainter, rect: QRect):
        x = int(self._ms_to_x(self._current_ms))
        if x < HEADER_W:
            return

        # Triangle head
        head_size = 8
        path = QPainterPath()
        path.moveTo(x, RULER_H)
        path.lineTo(x - head_size, 0)
        path.lineTo(x + head_size, 0)
        path.closeSubpath()
        p.fillPath(path, _COLORS["playhead_head"])

        # Vertical line
        p.setPen(QPen(_COLORS["playhead"], 1.5))
        p.drawLine(x, RULER_H, x, rect.height())

    def _draw_headers(self, p: QPainter):
        sx = self._scroll_offset
        
        # Background for header column
        header_rect = QRectF(sx, 0, HEADER_W, self.height())
        p.fillRect(header_rect, _COLORS["header_bg"])
        p.setPen(QPen(QColor("#2a2a40"), 1))
        p.drawLine(int(sx + HEADER_W), 0, int(sx + HEADER_W), self.height())
        
        # Track labels
        p.setFont(self._font_track)
        p.setPen(QPen(_COLORS["header_text"]))
        p.drawText(int(sx) + 4, self._video_track_y() + 4, HEADER_W - 8, TRACK_H - 8, Qt.AlignmentFlag.AlignVCenter, "VIDEO")
        p.drawText(int(sx) + 4, self._srt_track_y() + 4, HEADER_W - 8, TRACK_H - 8, Qt.AlignmentFlag.AlignTop, "SRT")

    # ── Hit testing ───────────────────────────────────────────────────────────
    def _hit_test_block(self, pos: QPoint) -> tuple[Optional[_Block], str]:
        """Returns (block, mode) where mode is 'left'|'right'|'body'|''."""
        y = self._srt_track_y()
        if not (y <= pos.y() <= y + self._srt_lanes * TRACK_H):
            return None, ""
            
        row = int((pos.y() - y) // TRACK_H)
        
        for block in reversed(self._blocks):  # reverse so front-most drawn on top
            if block.row != row:
                continue
            bx = block.x
            bw = block.w
            if bx <= pos.x() <= bx + bw:
                # Determine zone
                if pos.x() - bx <= EDGE_GRAB:
                    return block, "left"
                if bx + bw - pos.x() <= EDGE_GRAB:
                    return block, "right"
                return block, "body"
        return None, ""

    def _hit_playhead(self, pos: QPoint) -> bool:
        ph_x = int(self._ms_to_x(self._current_ms))
        return abs(pos.x() - ph_x) <= 8 and pos.y() <= RULER_H + TRACK_H

    # ── Mouse events ──────────────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent):
        pos = event.pos()

        if event.button() == Qt.MouseButton.LeftButton:
            # Playhead drag
            if self._hit_playhead(pos) or pos.y() <= RULER_H:
                self._playhead_dragging = True
                self._seek_to_x(pos.x())
                return

            # Block drag
            # Ignore clicks in the sticky header area
            if pos.x() > self._scroll_offset + HEADER_W:
                block, mode = self._hit_test_block(pos)
                if block:
                    self._drag_block           = block
                    self._drag_mode            = mode
                    self._drag_start_x         = pos.x()
                    self._drag_block_orig_start = block.entry.start_ms
                    self._drag_block_orig_end   = block.entry.end_ms
                    # Select block
                    self._select_block(block)
                    return

            # Click on empty area → seek
            if pos.x() > self._scroll_offset + HEADER_W:
                self._seek_to_x(pos.x())

        elif event.button() == Qt.MouseButton.RightButton:
            block, _ = self._hit_test_block(pos)
            if block:
                self._show_context_menu(block, event.globalPos())

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            block, _ = self._hit_test_block(event.pos())
            if block:
                self._select_block(block)
                self.subtitle_double_clicked.emit(block.entry.index)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.pos()

        # Update cursor
        if self._playhead_dragging:
            self._seek_to_x(pos.x())
            return

        if self._drag_block:
            dx = pos.x() - self._drag_start_x
            delta_ms = int(dx / self._pixels_per_sec * 1000)

            entry = self._drag_block.entry
            if self._drag_mode == "body":
                new_start = max(0, self._drag_block_orig_start + delta_ms)
                dur = self._drag_block_orig_end - self._drag_block_orig_start
                new_end = new_start + dur
            elif self._drag_mode == "left":
                new_start = max(0, min(
                    self._drag_block_orig_start + delta_ms,
                    self._drag_block_orig_end - 100  # min 100ms
                ))
                new_end = self._drag_block_orig_end
            elif self._drag_mode == "right":
                new_end = max(
                    self._drag_block_orig_start + 100,
                    self._drag_block_orig_end + delta_ms
                )
                new_start = self._drag_block_orig_start
            else:
                return

            # Update block visually (don't emit yet)
            entry.start_ms = new_start
            entry.end_ms   = new_end
            self._drag_block.x = self._ms_to_x(new_start)
            self._drag_block.w = max(4.0, (new_end - new_start) / 1000.0 * self._pixels_per_sec)
            self.update()
            return

        # Hover detection
        block, mode = self._hit_test_block(pos)
        for b in self._blocks:
            b.hovered = (b is block)

        # Cursor shape
        if block:
            if mode in ("left", "right"):
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        elif self._hit_playhead(pos):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._playhead_dragging:
                self._playhead_dragging = False
                return

            if self._drag_block:
                entry = self._drag_block.entry
                
                # Emit change if times actually changed
                if (entry.start_ms != self._drag_block_orig_start or
                        entry.end_ms != self._drag_block_orig_end):
                    
                    new_s = entry.start_ms
                    new_e = entry.end_ms
                    
                    # Revert locally so QUndoCommand can apply it cleanly
                    entry.start_ms = self._drag_block_orig_start
                    entry.end_ms   = self._drag_block_orig_end
                    
                    self.subtitle_time_changed.emit(
                        entry.index, 
                        self._drag_block_orig_start, self._drag_block_orig_end,
                        new_s, new_e
                    )
                    
                self._drag_block = None
                self._drag_mode  = ""
                self._rebuild_blocks()  # redraw lanes in case overlap changed
                self.update()
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1.0 / 1.15
            self.set_pixels_per_sec(self._pixels_per_sec * factor)
            event.accept()
        else:
            super().wheelEvent(event)

    # ── Internal ──────────────────────────────────────────────────────────────
    def _seek_to_x(self, x: int):
        ms = max(0, self._x_to_ms(x))
        self.seek_requested.emit(ms)

    def _select_block(self, block: _Block):
        for b in self._blocks:
            b.selected = (b is block)
        self._selected_idx = block.entry.index
        self.subtitle_selected.emit(block.entry.index)
        self.update()

    def _show_context_menu(self, block: _Block, global_pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e30; border: 1px solid #3a3a55; border-radius: 6px; }"
            "QMenu::item { padding: 7px 20px; color: #d0d0e0; }"
            "QMenu::item:selected { background: #2d2d4a; }"
        )
        act_before = menu.addAction("➕  Thêm trước")
        act_after  = menu.addAction("➕  Thêm sau")
        menu.addSeparator()
        act_delete = menu.addAction("🗑  Xóa")
        chosen = menu.exec(global_pos)
        if chosen == act_before:
            self.context_add_before.emit(block.entry.index)
        elif chosen == act_after:
            self.context_add_after.emit(block.entry.index)
        elif chosen == act_delete:
            self.context_delete.emit(block.entry.index)


# ─── Scroll wrapper ───────────────────────────────────────────────────────────

class TimelineWidget(QWidget):
    """
    Full timeline panel: zoom controls + scrollable TimelineCanvas.
    Uses QScrollArea (not QAbstractScrollArea.setViewport) to avoid
    circular size issues.
    """

    subtitle_selected       = Signal(int)
    subtitle_double_clicked = Signal(int)
    seek_requested          = Signal(int)
    subtitle_time_changed   = Signal(int, int, int, int, int)
    context_add_before      = Signal(int)
    context_add_after       = Signal(int)
    context_delete          = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top toolbar ──
        toolbar = QWidget()
        toolbar.setFixedHeight(30)
        toolbar.setStyleSheet("background: #0e0e1a; border-bottom: 1px solid #2a2a3d;")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(8, 2, 8, 2)
        tb_lay.setSpacing(6)

        lbl = QLabel("Timeline")
        lbl.setStyleSheet("color: #6060a0; font-size: 11px; font-weight: 700;")
        tb_lay.addWidget(lbl)
        tb_lay.addStretch()

        for text, slot in [("−", self._zoom_out), ("+", self._zoom_in)]:
            btn = QPushButton(text)
            btn.setFixedSize(26, 22)
            btn.setStyleSheet(
                "QPushButton { background:#2a2a42; color:#d0d0e8; border:1px solid #3a3a56;"
                " border-radius:4px; font-size:14px; font-weight:700; }"
                "QPushButton:hover { background:#353555; }"
            )
            btn.clicked.connect(slot)
            tb_lay.addWidget(btn)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setStyleSheet("color:#5555a0; font-size:11px; min-width:42px;")
        tb_lay.addWidget(self._zoom_label)

        root.addWidget(toolbar)

        # ── Canvas inside a proper QScrollArea ──
        self._canvas = TimelineCanvas()
        min_h = RULER_H + TRACK_H + TRACK_GAP + TRACK_H + 10
        self._canvas.setMinimumHeight(min_h)
        # Give canvas enough initial width to trigger scrollbar
        self._canvas.setMinimumWidth(HEADER_W + 200)

        from PySide6.QtWidgets import QScrollArea
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._canvas)
        self._scroll.setWidgetResizable(False)   # Canvas controls its own size
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: #12121e; }"
            "QScrollArea > QWidget > QWidget { background: #12121e; }"
        )
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # Forward scrollbar → canvas offset
        self._scroll.horizontalScrollBar().valueChanged.connect(
            self._canvas.set_scroll_offset
        )

        # Connect canvas signals → self signals (pass-through)
        self._canvas.subtitle_selected.connect(self.subtitle_selected)
        self._canvas.subtitle_double_clicked.connect(self.subtitle_double_clicked)
        self._canvas.seek_requested.connect(self.seek_requested)
        self._canvas.subtitle_time_changed.connect(self.subtitle_time_changed)
        self._canvas.context_add_before.connect(self.context_add_before)
        self._canvas.context_add_after.connect(self.context_add_after)
        self._canvas.context_delete.connect(self.context_delete)

        root.addWidget(self._scroll, stretch=1)

    # ── Forwarded API ─────────────────────────────────────────────────────────
    def set_entries(self, entries):
        self._canvas.set_entries(entries)
        self._sync_canvas_size()

    def set_duration_ms(self, ms: int):
        self._canvas.set_duration_ms(ms)
        self._sync_canvas_size()

    def set_current_ms(self, ms: int):
        self._canvas.set_current_ms(ms)
        # Auto-scroll to keep playhead visible
        ph_x   = int(self._canvas._ms_to_x(ms))
        offset = self._scroll.horizontalScrollBar().value()
        vw     = self._scroll.viewport().width()
        if ph_x < HEADER_W + 20:
            pass  # at start
        elif ph_x - offset > vw - 40:
            self._scroll.horizontalScrollBar().setValue(ph_x - vw + 60)
        elif ph_x - offset < 40:
            self._scroll.horizontalScrollBar().setValue(max(0, ph_x - HEADER_W - 20))

    def set_selected(self, entry_index):
        self._canvas.set_selected(entry_index)

    # ── Zoom ──────────────────────────────────────────────────────────────────
    def _zoom_in(self):
        self._canvas.set_pixels_per_sec(self._canvas.pixels_per_sec * 1.3)
        self._sync_canvas_size()
        self._update_zoom_label()

    def _zoom_out(self):
        self._canvas.set_pixels_per_sec(self._canvas.pixels_per_sec / 1.3)
        self._sync_canvas_size()
        self._update_zoom_label()

    def _update_zoom_label(self):
        pct = int(self._canvas.pixels_per_sec)
        self._zoom_label.setText(f"{pct}px/s")

    def _sync_canvas_size(self):
        """Resize canvas to its content width; height fills the scroll area."""
        vw = self._scroll.viewport().width()
        vh = self._scroll.viewport().height()
        target_w = max(self._canvas._total_width(), vw)
        target_h = max(self._canvas.minimumHeight(), vh)
        self._canvas.resize(target_w, target_h)
