# ui_pyside6/widgets/video_player.py
"""
VideoPlayerWidget — embeds python-vlc into a QFrame.
Includes:
  - Play/Pause, Seek slider, Volume, Time label
  - OCR region selection via TRULY transparent overlay (no dark background)
  - VLC hardware decode disabled to fix D3D11VA errors

Fix history:
  v2: transparent overlay widget instead of event filter on VLC HWND
  v3: overlay fully transparent — no dark fill blocking video view
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QRubberBand, QSizePolicy,
    QSlider, QVBoxLayout, QWidget,
)

try:
    import vlc
    VLC_AVAILABLE = True
except (ImportError, OSError, FileNotFoundError):
    vlc = None          # type: ignore
    VLC_AVAILABLE = False


# ─── Transparent OCR overlay ─────────────────────────────────────────────────

class _OcrOverlay(QWidget):
    """
    Fully transparent overlay for rubber-band OCR region selection.
    Sits on top of the VLC video_frame without covering/darkening the video.
    """
    region_selected = Signal(QRect)

    def __init__(self, parent: QWidget):
        # Must be a top-level tool window to overlay correctly over native VLC child on Windows
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        # CRITICAL: allow painting without Qt blocking transparency
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self._origin: QPoint | None = None
        self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        # Style the rubber band to be very visible
        self._rubber_band.setStyleSheet(
            "QRubberBand { border: 2px solid #f5a623; background: rgba(245,166,35,30); }"
        )
        self.hide()

    def show_hint(self):
        self._origin = None
        self._rubber_band.hide()
        self.show()
        self.raise_()
        self.setFocus()
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.update()

    def hide_overlay(self):
        self._origin = None
        self._rubber_band.hide()
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.hide()

    def paintEvent(self, event):
        """Draw only a thin border + instruction label — NO dark fill."""
        p = QPainter(self)
        
        # CRITICAL WINDOWS FIX: 
        # If alpha is exactly 0, Windows DWM treats the window as click-through (HTTRANSPARENT).
        # We must draw a 1/255 alpha background so it captures mouse events!
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        
        # Just a visible border so user knows overlay is active
        p.setPen(QPen(QColor("#f5a623"), 2))
        p.drawRect(self.rect().adjusted(1, 1, -1, -1))

        # Instruction at top
        hint = "🖱  Kéo chuột để chọn vùng subtitle — Nhấn Esc để hủy"
        p.setPen(QColor("#FFD700"))
        f = self.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        fm   = p.fontMetrics()
        tw   = fm.horizontalAdvance(hint)
        th   = fm.height()
        pad  = 8
        bx   = (self.width() - tw) // 2 - pad
        by   = 10
        # Small translucent background for readability only
        p.fillRect(bx, by, tw + pad * 2, th + pad, QColor(0, 0, 0, 160))
        p.drawText(bx + pad, by + th, hint)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            self._rubber_band.setGeometry(QRect(self._origin, QSize()))
            self._rubber_band.show()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._rubber_band.setGeometry(
                QRect(self._origin, event.pos()).normalized()
            )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._origin is not None:
            rect = QRect(self._origin, event.pos()).normalized()
            self._origin = None
            self.region_selected.emit(rect)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide_overlay()
        else:
            super().keyPressEvent(event)


# ─── Main VideoPlayerWidget ───────────────────────────────────────────────────

class VideoPlayerWidget(QWidget):
    """
    Embeds VLC video player with transport controls.

    Signals:
        position_changed(float)         — playback position 0.0–1.0
        duration_changed(int)           — total duration in ms
        playing_state_changed(bool)     — True=playing
        ocr_region_selected(list)       — [x, y, w, h] in source-video pixels
        time_changed_ms(int)            — current time in ms (every 100ms)
    """

    position_changed      = Signal(float)
    duration_changed      = Signal(int)
    playing_state_changed = Signal(bool)
    ocr_region_selected   = Signal(list)
    time_changed_ms       = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vlc_instance  = None
        self._media_player  = None
        self._duration_ms:  int  = 0
        self._is_seeking:   bool = False
        self._ocr_mode:     bool = False

        self._build_ui()

        if VLC_AVAILABLE:
            self._init_vlc()

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(100)
        self._sync_timer.timeout.connect(self._on_sync_tick)
        self._sync_timer.start()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Container holds both video_frame and overlay
        self._video_container = QWidget(self)
        self._video_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._video_container.setMinimumHeight(200)
        root.addWidget(self._video_container, stretch=1)

        # VLC renders into this black frame
        self._video_frame = QFrame(self._video_container)
        self._video_frame.setObjectName("video_frame")
        self._video_frame.setStyleSheet("background-color: #000000;")

        # Transparent overlay for OCR selection (on top, no dark fill)
        self._ocr_overlay = _OcrOverlay(self._video_container)
        self._ocr_overlay.region_selected.connect(self._on_overlay_region)

        # Transport controls
        ctrl_bar = QWidget()
        ctrl_bar.setStyleSheet("background-color: #111120; border-top: 1px solid #2a2a3d;")
        ctrl_lay = QHBoxLayout(ctrl_bar)
        ctrl_lay.setContentsMargins(10, 6, 10, 6)
        ctrl_lay.setSpacing(8)

        self._btn_play = QPushButton("▶")
        self._btn_play.setObjectName("btn_play_pause")
        self._btn_play.setFixedSize(40, 40)
        self._btn_play.clicked.connect(self.toggle_play_pause)
        ctrl_lay.addWidget(self._btn_play)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setObjectName("seek_slider")
        self._seek_slider.setRange(0, 10000)
        self._seek_slider.setValue(0)
        self._seek_slider.sliderPressed.connect(lambda: setattr(self, "_is_seeking", True))
        self._seek_slider.sliderReleased.connect(self._on_seek_released)
        ctrl_lay.addWidget(self._seek_slider, stretch=1)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("time_label")
        self._time_label.setMinimumWidth(110)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ctrl_lay.addWidget(self._time_label)

        vol_lbl = QLabel("🔊")
        vol_lbl.setStyleSheet("color: #8080a0; font-size: 14px;")
        ctrl_lay.addWidget(vol_lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setObjectName("vol_slider")
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(80)
        self._vol_slider.setFixedWidth(80)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        ctrl_lay.addWidget(self._vol_slider)

        root.addWidget(ctrl_bar)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self._video_container.width()
        ch = self._video_container.height()
        self._video_frame.setGeometry(0, 0, cw, ch)
        
        # Sync top-level overlay geometry if active
        if self._ocr_mode:
            self._sync_overlay_geometry()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._ocr_mode:
            self.exit_ocr_mode()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._ocr_mode:
            self._sync_overlay_geometry()

    # ── VLC init ──────────────────────────────────────────────────────────────
    def _init_vlc(self):
        try:
            self._vlc_instance = vlc.Instance(
                "--no-xlib",
                "--avcodec-hw=none",          # disable D3D11VA HW errors
                "--no-sub-autodetect-file",   # don't auto-load external subtitle files
                "--sub-track=-1",             # no subtitle track by default
                "--quiet",
            )
        except Exception:
            self._vlc_instance = vlc.Instance("--no-xlib", "--avcodec-hw=none")

        self._media_player = self._vlc_instance.media_player_new()
        if sys.platform == "win32":
            self._media_player.set_hwnd(int(self._video_frame.winId()))
        elif sys.platform == "linux":
            self._media_player.set_xwindow(int(self._video_frame.winId()))
        elif sys.platform == "darwin":
            self._media_player.set_nsobject(int(self._video_frame.winId()))
        self._media_player.audio_set_volume(80)

    # ── Public API ────────────────────────────────────────────────────────────
    def load_video(self, path: str) -> bool:
        if not VLC_AVAILABLE or self._media_player is None:
            return False
        media = self._vlc_instance.media_new(path)
        self._media_player.set_media(media)
        media.release()
        self._media_player.play()
        self._duration_ms = 0
        self._btn_play.setText("⏸")
        # Disable built-in subtitle rendering (SPU track = -1 means no subtitles)
        # Use a short delay to let VLC parse the media before setting SPU
        QTimer.singleShot(500, self._disable_subtitles)

        return True

    def _disable_subtitles(self):
        """Turn off VLC's built-in subtitle track (SPU -1 = disabled)."""
        if self._media_player:
            try:
                self._media_player.video_set_spu(-1)
            except Exception:
                pass

    def toggle_play_pause(self):
        if not self._media_player:
            return
        if self._media_player.is_playing():
            self._media_player.pause()
            self._btn_play.setText("▶")
            self.playing_state_changed.emit(False)
        else:
            self._media_player.play()
            self._btn_play.setText("⏸")
            self.playing_state_changed.emit(True)

    def pause(self):
        if self._media_player and self._media_player.is_playing():
            self._media_player.pause()
            self._btn_play.setText("▶")
            self.playing_state_changed.emit(False)

    def play(self):
        if self._media_player and not self._media_player.is_playing():
            self._media_player.play()
            self._btn_play.setText("⏸")
            self.playing_state_changed.emit(True)

    def seek_to_ms(self, ms: int):
        if not self._media_player:
            return
        dur = self._get_duration_ms()
        if dur > 0:
            self._media_player.set_time(max(0, min(ms, dur)))

    def get_current_ms(self) -> int:
        if self._media_player:
            t = self._media_player.get_time()
            return max(0, t)
        return 0

    def get_duration_ms(self) -> int:
        return self._get_duration_ms()

    def is_playing(self) -> bool:
        return bool(self._media_player and self._media_player.is_playing())

    def set_volume(self, vol: int):
        if self._media_player:
            self._media_player.audio_set_volume(max(0, min(100, vol)))

    def enter_ocr_mode(self):
        self._ocr_mode = True
        self._sync_overlay_geometry()
        self._ocr_overlay.show_hint()

    def exit_ocr_mode(self):
        self._ocr_mode = False
        self._ocr_overlay.hide_overlay()

    def _sync_overlay_geometry(self):
        """Map overlay to exact global screen position of the video frame."""
        if self._video_frame and self._video_frame.isVisible():
            global_pt = self._video_frame.mapToGlobal(QPoint(0, 0))
            self._ocr_overlay.setGeometry(QRect(global_pt, self._video_frame.size()))

    def take_snapshot(self, out_path: str) -> bool:
        if not self._media_player:
            return False
        return self._media_player.video_take_snapshot(0, out_path, 0, 0) == 0

    # ── Overlay → source pixels ───────────────────────────────────────────────
    def _on_overlay_region(self, rect: QRect):
        self.exit_ocr_mode()
        if rect.width() < 5 or rect.height() < 5:
            return
        ow, oh = self._ocr_overlay.width(), self._ocr_overlay.height()
        if ow <= 0 or oh <= 0:
            return
        vid_rect = self._get_rendered_video_rect(ow, oh)
        clipped  = rect.intersected(vid_rect)
        if clipped.width() < 5 or clipped.height() < 5:
            return
        rel_x = clipped.x() - vid_rect.x()
        rel_y = clipped.y() - vid_rect.y()
        sw, sh = self._get_video_source_size()
        if sw > 0 and sh > 0:
            sx = sw / vid_rect.width();  sy = sh / vid_rect.height()
            px_x, px_y = int(rel_x * sx), int(rel_y * sy)
            px_w, px_h = int(clipped.width() * sx), int(clipped.height() * sy)
        else:
            px_x = int(rel_x / vid_rect.width()  * 1920)
            px_y = int(rel_y / vid_rect.height() * 1080)
            px_w = int(clipped.width() / vid_rect.width()  * 1920)
            px_h = int(clipped.height() / vid_rect.height() * 1080)
        self.ocr_region_selected.emit([px_x, px_y, px_w, px_h])

    def _get_rendered_video_rect(self, fw: int, fh: int) -> QRect:
        sw, sh = self._get_video_source_size()
        if sw <= 0 or sh <= 0:
            return QRect(0, 0, fw, fh)
        if fw / fh > sw / sh:
            rh = fh; rw = int(rh * sw / sh)
            return QRect((fw - rw) // 2, 0, rw, rh)
        else:
            rw = fw; rh = int(rw * sh / sw)
            return QRect(0, (fh - rh) // 2, rw, rh)

    def _get_video_source_size(self) -> tuple[int, int]:
        if not self._media_player:
            return 0, 0
        try:
            w, h = self._media_player.video_get_size(0)
            return int(w), int(h)
        except Exception:
            return 0, 0

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _get_duration_ms(self) -> int:
        if self._media_player:
            d = self._media_player.get_length()
            if d > 0:
                self._duration_ms = d
        return self._duration_ms

    def _fmt_time(self, ms: int) -> str:
        s = ms // 1000; m, s = divmod(s, 60); h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def _on_sync_tick(self):
        if not self._media_player or self._is_seeking:
            return
        cur_ms = max(0, self._media_player.get_time())
        dur_ms = self._get_duration_ms()
        if dur_ms > 0:
            self._seek_slider.blockSignals(True)
            self._seek_slider.setValue(int(cur_ms / dur_ms * 10000))
            self._seek_slider.blockSignals(False)
        self._time_label.setText(
            f"{self._fmt_time(cur_ms)} / {self._fmt_time(max(0, dur_ms))}"
        )
        if dur_ms > 0:
            self.position_changed.emit(cur_ms / dur_ms)
        self.time_changed_ms.emit(cur_ms)
        playing = self._media_player.is_playing()
        icon = "⏸" if playing else "▶"
        if self._btn_play.text() != icon:
            self._btn_play.setText(icon)
            self.playing_state_changed.emit(playing)

    def _on_seek_released(self):
        if self._media_player:
            dur = self._get_duration_ms()
            if dur > 0:
                self._media_player.set_time(int(self._seek_slider.value() / 10000 * dur))
                if not self._media_player.is_playing():
                    self._media_player.play()
        self._is_seeking = False

    def _on_volume_changed(self, v: int):
        if self._media_player:
            self._media_player.audio_set_volume(v)

    def closeEvent(self, event):
        self._sync_timer.stop()
        if self._media_player:
            self._media_player.stop()
        super().closeEvent(event)
