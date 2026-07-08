# ui_pyside6/styles/theme.py
"""Dark CapCut-inspired stylesheet for PySide6."""

DARK_THEME = """
/* ═══════════════════════════════════════════════
   BASE
═══════════════════════════════════════════════ */
QMainWindow, QDialog {
    background-color: #141420;
    color: #e8e8f0;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}

QWidget {
    background-color: transparent;
    color: #e8e8f0;
    font-family: "Segoe UI", "Inter", sans-serif;
}

/* ═══════════════════════════════════════════════
   MENU BAR
═══════════════════════════════════════════════ */
QMenuBar {
    background-color: #0e0e1a;
    color: #c8c8d8;
    border-bottom: 1px solid #2a2a40;
    padding: 2px 4px;
    font-size: 13px;
}
QMenuBar::item {
    padding: 5px 12px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #2a2a45;
    color: #ffffff;
}
QMenuBar::item:pressed {
    background-color: #e94560;
    color: #ffffff;
}

QMenu {
    background-color: #1e1e30;
    border: 1px solid #3a3a55;
    border-radius: 8px;
    padding: 4px 0;
}
QMenu::item {
    padding: 7px 20px 7px 12px;
    color: #d0d0e0;
}
QMenu::item:selected {
    background-color: #2d2d4a;
    color: #ffffff;
}
QMenu::item:disabled {
    color: #555568;
}
QMenu::separator {
    height: 1px;
    background-color: #2a2a3d;
    margin: 4px 8px;
}

/* ═══════════════════════════════════════════════
   TOOLBAR
═══════════════════════════════════════════════ */
QToolBar {
    background-color: #1a1a28;
    border: none;
    border-bottom: 1px solid #2a2a3d;
    padding: 4px 8px;
    spacing: 4px;
}
QToolBar::separator {
    width: 1px;
    background-color: #2a2a3d;
    margin: 4px 6px;
}

/* ═══════════════════════════════════════════════
   PANELS / FRAMES
═══════════════════════════════════════════════ */
#left_panel, #right_panel {
    background-color: #16162a;
    border: none;
}
#center_panel {
    background-color: #0c0c14;
}
#video_frame {
    background-color: #000000;
    border: none;
}
#timeline_panel {
    background-color: #12121e;
    border-top: 2px solid #2a2a40;
}

/* Group boxes */
QGroupBox {
    background-color: #1c1c2e;
    border: 1px solid #2e2e45;
    border-radius: 8px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
    font-size: 12px;
    font-weight: 600;
    color: #9090b0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: -1px;
    padding: 0 6px;
    color: #7878a8;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ═══════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════ */
QPushButton {
    background-color: #2a2a42;
    color: #d0d0e8;
    border: 1px solid #3a3a56;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #353555;
    border-color: #5555aa;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #252540;
    border-color: #e94560;
}
QPushButton:disabled {
    background-color: #1e1e30;
    color: #444460;
    border-color: #2a2a3d;
}

/* Primary / accent buttons */
QPushButton#btn_run_ocr,
QPushButton#btn_run_stt,
QPushButton#btn_run_dubbing {
    background-color: #e94560;
    border: none;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#btn_run_ocr:hover,
QPushButton#btn_run_stt:hover,
QPushButton#btn_run_dubbing:hover {
    background-color: #ff5575;
}
QPushButton#btn_run_ocr:disabled,
QPushButton#btn_run_stt:disabled,
QPushButton#btn_run_dubbing:disabled {
    background-color: #5a1a28;
    color: #884455;
}

/* Play button */
QPushButton#btn_play_pause {
    background-color: #2a2a45;
    border: 2px solid #4a4a6a;
    border-radius: 20px;
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
    font-size: 16px;
    padding: 0;
}
QPushButton#btn_play_pause:hover {
    background-color: #e94560;
    border-color: #e94560;
    color: white;
}

/* Danger button */
QPushButton#btn_cancel {
    background-color: #3d1a22;
    border-color: #6a2535;
    color: #ff6680;
}
QPushButton#btn_cancel:hover {
    background-color: #e94560;
    color: white;
    border-color: #e94560;
}

/* OCR Toggle button */
QPushButton#btn_select_ocr_region {
    background-color: #1e3a5f;
    border-color: #2a5080;
    color: #60a0e0;
}
QPushButton#btn_select_ocr_region:checked {
    background-color: #f5a623;
    border-color: #f5a623;
    color: #000000;
    font-weight: 700;
}

/* ═══════════════════════════════════════════════
   SLIDERS
═══════════════════════════════════════════════ */
QSlider::groove:horizontal {
    height: 4px;
    background-color: #2a2a42;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background-color: #e94560;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background-color: #ff5575;
    width: 16px;
    height: 16px;
    margin: -6px 0;
}
QSlider::sub-page:horizontal {
    background-color: #e94560;
    border-radius: 2px;
}

/* Seek slider */
QSlider#seek_slider::groove:horizontal {
    height: 5px;
    background-color: #252538;
}
QSlider#seek_slider::sub-page:horizontal {
    background-color: #e94560;
}

/* Volume slider */
QSlider#vol_slider::groove:horizontal {
    height: 3px;
    background-color: #252538;
}
QSlider#vol_slider::sub-page:horizontal {
    background-color: #7878c8;
}
QSlider#vol_slider::handle:horizontal {
    background-color: #9090d0;
    width: 12px;
    height: 12px;
    margin: -4.5px 0;
}

/* ═══════════════════════════════════════════════
   COMBO BOX
═══════════════════════════════════════════════ */
QComboBox {
    background-color: #22223a;
    border: 1px solid #3a3a55;
    border-radius: 6px;
    padding: 5px 10px;
    color: #d0d0e8;
    font-size: 12px;
    min-height: 26px;
}
QComboBox:hover {
    border-color: #5555aa;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #7070a0;
    width: 0;
    height: 0;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #1e1e35;
    border: 1px solid #3a3a55;
    selection-background-color: #2d2d4a;
    color: #d0d0e8;
    padding: 4px;
}

/* ═══════════════════════════════════════════════
   TEXT FIELDS
═══════════════════════════════════════════════ */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #1e1e32;
    border: 1px solid #2e2e48;
    border-radius: 6px;
    padding: 5px 9px;
    color: #d8d8f0;
    font-size: 12px;
    min-height: 26px;
    selection-background-color: #e94560;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #e94560;
    background-color: #222238;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #2a2a42;
    border: none;
    width: 18px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: #3a3a58;
}

QTextEdit, QPlainTextEdit {
    background-color: #181828;
    border: 1px solid #2a2a40;
    border-radius: 6px;
    color: #c8c8e0;
    font-size: 12px;
    padding: 6px;
    selection-background-color: #e94560;
    selection-color: #ffffff;
}
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #e94560;
}

/* ═══════════════════════════════════════════════
   TABLES & LISTS
═══════════════════════════════════════════════ */
QTableWidget, QTableView {
    background-color: #16162a;
    alternate-background-color: #1c1c30;
    color: #c8c8e0;
    gridline-color: #252538;
    border: 1px solid #252538;
    border-radius: 6px;
    selection-background-color: #2d2d50;
    font-size: 12px;
}
QTableWidget::item, QTableView::item {
    padding: 4px 6px;
    border: none;
}
QTableWidget::item:selected, QTableView::item:selected {
    background-color: #3d3d6a;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #1a1a2e;
    color: #7878a8;
    border: none;
    border-bottom: 1px solid #2a2a40;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

QListWidget {
    background-color: #16162a;
    border: 1px solid #252538;
    border-radius: 6px;
    color: #c0c0d8;
}
QListWidget::item {
    padding: 5px 8px;
}
QListWidget::item:selected {
    background-color: #2d2d50;
    color: #ffffff;
}
QListWidget::item:hover {
    background-color: #222240;
}

/* ═══════════════════════════════════════════════
   SCROLL BARS
═══════════════════════════════════════════════ */
QScrollBar:vertical {
    background-color: #141420;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #333355;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #4a4a7a;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background-color: #141420;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #333355;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #4a4a7a;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ═══════════════════════════════════════════════
   STATUS BAR
═══════════════════════════════════════════════ */
QStatusBar {
    background-color: #0e0e1a;
    border-top: 1px solid #2a2a3d;
    color: #8080a0;
    font-size: 11px;
    padding: 2px 8px;
}

/* ═══════════════════════════════════════════════
   PROGRESS BAR
═══════════════════════════════════════════════ */
QProgressBar {
    background-color: #1e1e30;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #e94560,
        stop:1 #f5a623
    );
    border-radius: 4px;
}

/* ═══════════════════════════════════════════════
   SPLITTER
═══════════════════════════════════════════════ */
QSplitter::handle {
    background-color: #2a2a3d;
}
QSplitter::handle:hover {
    background-color: #e94560;
}
QSplitter::handle:horizontal {
    width: 3px;
}
QSplitter::handle:vertical {
    height: 3px;
}

/* ═══════════════════════════════════════════════
   CHECKBOXES & RADIO BUTTONS
═══════════════════════════════════════════════ */
QCheckBox {
    color: #c0c0d8;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #3a3a58;
    border-radius: 4px;
    background-color: #1a1a2e;
}
QCheckBox::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}
QCheckBox::indicator:hover {
    border-color: #5555aa;
}

/* ═══════════════════════════════════════════════
   LABELS
═══════════════════════════════════════════════ */
QLabel#time_label {
    color: #a0a0c0;
    font-family: "Consolas", monospace;
    font-size: 12px;
}
QLabel#status_led {
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
    border-radius: 5px;
}

/* ═══════════════════════════════════════════════
   TOOLTIPS
═══════════════════════════════════════════════ */
QToolTip {
    background-color: #1e1e35;
    color: #d0d0e8;
    border: 1px solid #3a3a55;
    border-radius: 5px;
    padding: 5px 9px;
    font-size: 12px;
}

/* ═══════════════════════════════════════════════
   STACKED WIDGET TABS (custom toolbar buttons)
═══════════════════════════════════════════════ */
QPushButton#tab_btn {
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    color: #7070a0;
    padding: 6px 14px;
    font-size: 12px;
}
QPushButton#tab_btn:hover {
    color: #c0c0e8;
    background-color: #1e1e30;
}
QPushButton#tab_btn:checked {
    color: #e94560;
    border-bottom: 2px solid #e94560;
}

/* Warning label */
QLabel#warning_label {
    color: #f5a623;
    font-size: 11px;
    font-weight: 600;
}
"""

# Color constants for use in QPainter (timeline, etc.)
COLORS = {
    "bg_main":          "#141420",
    "bg_panel":         "#16162a",
    "bg_dark":          "#0e0e1a",
    "bg_surface":       "#1c1c2e",
    "accent":           "#e94560",
    "accent_hover":     "#ff5575",
    "accent_secondary": "#f5a623",
    "text_primary":     "#e8e8f0",
    "text_secondary":   "#9090b0",
    "text_muted":       "#555568",
    "border":           "#2a2a3d",
    "border_hover":     "#5555aa",
    "timeline_bg":      "#12121e",
    "timeline_ruler":   "#1a1a2e",
    "video_track":      "#1a2540",
    "video_track_fill": "#2a4070",
    "srt_block":        "#b87000",
    "srt_block_active": "#f5a623",
    "srt_block_hover":  "#d09030",
    "srt_block_border": "#f5c060",
    "playhead":         "#e94560",
    "playhead_bg":      "#ff5575",
    "tick_major":       "#404060",
    "tick_minor":       "#282838",
    "tick_label":       "#606080",
}
