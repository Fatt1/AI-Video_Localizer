# ui_pyside6/widgets/subtitle_editor.py
"""
Right panel — Subtitle Editor + Tools.

Sections (shown via stacked pages + tab buttons):
  1. SRT Edit     — inline editor after double-clicking a timeline block
  2. OCR          — region selection + lang + run OCR
  3. STT          — Speech-to-Text settings + run
  4. Dubbing      — Voice clone + CapCut project + run
  5. SRT Tools    — Normalize before/after translate, Filter duplicates

Signals bubble up to MainWindow for actual processing.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from models.subtitle_model import SubtitleEntry


class SubtitleEditorPanel(QWidget):
    """Right panel: tab-based sections for editing and running tools."""

    # ── Signals ──────────────────────────────────────────────────────────────
    # SRT Edit
    subtitle_applied  = Signal(int, int, int, str)  # (index, start_ms, end_ms, text)
    subtitle_canceled = Signal()

    # OCR
    ocr_region_requested = Signal()          # open rubber-band selection
    run_ocr_requested    = Signal(str, float, str)  # (lang_code, fps, out_srt_path)

    # STT
    run_stt_requested = Signal(str, str, float, bool)  # (model_key, language, silence_gap_s, use_diarization)

    # Dubbing
    run_dubbing_requested = Signal(str, str, float)  # (voice_id, capcut_project, rate)
    voices_refresh        = Signal()

    # SRT Tools
    normalize_before_requested = Signal()
    normalize_after_requested  = Signal()
    filter_dup_requested       = Signal()

    # Single TTS
    single_tts_requested = Signal(str, str, float, str)  # (text, voice_id, rate, output_path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_entry: SubtitleEntry | None = None
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Tab buttons row ──
        tab_bar = QWidget()
        tab_bar.setStyleSheet("background: #0e0e1a; border-bottom: 1px solid #2a2a3d;")
        tab_lay = QHBoxLayout(tab_bar)
        tab_lay.setContentsMargins(4, 0, 4, 0)
        tab_lay.setSpacing(0)

        self._tab_btns: list[QPushButton] = []
        tabs = ["✏ Edit", "🔍 OCR", "🎙 STT", "🎵 Dub", "🔊 TTS", "🛠 Tools"]
        for i, name in enumerate(tabs):
            btn = QPushButton(name)
            btn.setObjectName("tab_btn")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            tab_lay.addWidget(btn)
            self._tab_btns.append(btn)

        root.addWidget(tab_bar)

        # ── Stacked pages ──
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_edit_page())      # 0
        self._stack.addWidget(self._build_ocr_page())       # 1
        self._stack.addWidget(self._build_stt_page())       # 2
        self._stack.addWidget(self._build_dubbing_page())   # 3
        self._stack.addWidget(self._build_single_tts_page()) # 4
        self._stack.addWidget(self._build_tools_page())     # 5
        root.addWidget(self._stack, stretch=1)

    def _switch_tab(self, idx: int):
        for i, btn in enumerate(self._tab_btns):
            btn.setChecked(i == idx)
        self._stack.setCurrentIndex(idx)

    def switch_to_edit_tab(self):
        self._switch_tab(0)

    # ── Page builders ─────────────────────────────────────────────────────────

    def _scrollable(self, widget: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidget(widget)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        return sa

    # ── Page 0: Edit ──────────────────────────────────────────────────────────
    def _build_edit_page(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        placeholder = QLabel("← Nhấp đúp vào một khối SRT trên timeline để chỉnh sửa.")
        placeholder.setObjectName("warning_label")
        placeholder.setWordWrap(True)
        placeholder.setStyleSheet("color: #555568; font-size: 12px; padding: 20px 10px;")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit_placeholder = placeholder
        lay.addWidget(placeholder)

        # Edit form (hidden until a block is selected)
        self._edit_form_widget = QWidget()
        form_lay = QVBoxLayout(self._edit_form_widget)
        form_lay.setContentsMargins(0, 0, 0, 0)
        form_lay.setSpacing(8)

        grp = QGroupBox("Chỉnh sửa subtitle")
        grp_lay = QFormLayout(grp)
        grp_lay.setSpacing(8)

        # Index label
        self._edit_idx_label = QLabel("—")
        self._edit_idx_label.setStyleSheet("color: #8080c0; font-weight: 700;")
        grp_lay.addRow("Số thứ tự:", self._edit_idx_label)

        # Start time (ms)
        self._edit_start = QSpinBox()
        self._edit_start.setRange(0, 99_999_999)
        self._edit_start.setSuffix(" ms")
        grp_lay.addRow("Bắt đầu:", self._edit_start)

        # End time (ms)
        self._edit_end = QSpinBox()
        self._edit_end.setRange(0, 99_999_999)
        self._edit_end.setSuffix(" ms")
        grp_lay.addRow("Kết thúc:", self._edit_end)

        # Text
        self._edit_text = QTextEdit()
        self._edit_text.setMinimumHeight(80)
        self._edit_text.setMaximumHeight(160)
        self._edit_text.setPlaceholderText("Nội dung subtitle...")
        grp_lay.addRow("Nội dung:", self._edit_text)

        form_lay.addWidget(grp)

        # Apply / Cancel buttons
        btn_row = QHBoxLayout()
        self._btn_apply = QPushButton("✔  Áp dụng")
        self._btn_apply.clicked.connect(self._on_apply)
        self._btn_apply.setStyleSheet(
            "QPushButton { background:#c07800; border:none; color:#000; font-weight:700; "
            "border-radius:6px; padding:7px 18px; }"
            "QPushButton:hover { background:#f5a623; }"
        )
        self._btn_cancel_edit = QPushButton("✕  Hủy")
        self._btn_cancel_edit.clicked.connect(self._on_cancel_edit)
        btn_row.addWidget(self._btn_apply)
        btn_row.addWidget(self._btn_cancel_edit)
        form_lay.addLayout(btn_row)
        form_lay.addStretch()

        self._edit_form_widget.hide()
        lay.addWidget(self._edit_form_widget)
        lay.addStretch()
        return page

    # ── Page 1: OCR ───────────────────────────────────────────────────────────
    def _build_ocr_page(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Region selection
        grp_region = QGroupBox("Vùng OCR")
        r_lay = QVBoxLayout(grp_region)

        self._btn_ocr_region = QPushButton("🖱  Chọn vùng subtitle trên video")
        self._btn_ocr_region.setObjectName("btn_select_ocr_region")
        self._btn_ocr_region.setCheckable(True)
        self._btn_ocr_region.clicked.connect(lambda: self.ocr_region_requested.emit())
        r_lay.addWidget(self._btn_ocr_region)

        self._ocr_region_label = QLabel("Chưa chọn vùng (mặc định: toàn khung)")
        self._ocr_region_label.setStyleSheet("color: #606080; font-size: 11px;")
        r_lay.addWidget(self._ocr_region_label)

        lay.addWidget(grp_region)

        # Settings
        grp_set = QGroupBox("Cài đặt OCR")
        s_lay = QFormLayout(grp_set)
        s_lay.setSpacing(8)

        self._ocr_lang = QComboBox()
        self._ocr_lang.addItems([
            "ch — Tiếng Trung",
            "en — Tiếng Anh",
            "japan — Tiếng Nhật",
            "korean — Tiếng Hàn",
            "vi — Tiếng Việt",
        ])
        self._ocr_lang.setCurrentIndex(0)
        s_lay.addRow("Ngôn ngữ:", self._ocr_lang)

        self._ocr_fps = QDoubleSpinBox()
        self._ocr_fps.setRange(0.5, 60.0)
        self._ocr_fps.setValue(4.0)
        self._ocr_fps.setSingleStep(0.5)
        self._ocr_fps.setDecimals(1)
        s_lay.addRow("FPS:", self._ocr_fps)

        lay.addWidget(grp_set)

        # Output SRT path
        grp_out = QGroupBox("File output")
        out_lay = QFormLayout(grp_out)
        self._ocr_out_path = QLineEdit()
        self._ocr_out_path.setPlaceholderText("Để trống → lưu cạnh video (ocr.srt)")
        out_lay.addRow("SRT:", self._ocr_out_path)
        lay.addWidget(grp_out)

        # Run button
        self._btn_run_ocr = QPushButton("▶  Chạy OCR Hardsub")
        self._btn_run_ocr.setObjectName("btn_run_ocr")
        self._btn_run_ocr.clicked.connect(self._on_run_ocr)
        lay.addWidget(self._btn_run_ocr)
        lay.addStretch()

        return self._scrollable(content)

    # ── Page 2: STT ───────────────────────────────────────────────────────────
    def _build_stt_page(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        grp = QGroupBox("Speech-to-Text")
        g_lay = QFormLayout(grp)
        g_lay.setSpacing(8)

        # Model
        self._stt_model = QComboBox()
        self._stt_model.setObjectName("stt_model_combo")
        from services.stt_service import AVAILABLE_MODELS
        for key, label in AVAILABLE_MODELS.items():
            self._stt_model.addItem(label, userData=key)
        self._stt_model.setCurrentIndex(0)
        g_lay.addRow("ð¤ Model:", self._stt_model)

        # Language
        self._stt_lang = QComboBox()
        self._stt_lang.setObjectName("stt_lang_combo")
        self._stt_lang.addItems([
            "zh — Tiếng Trung",
            "en — Tiếng Anh",
            "ja — Tiếng Nhật",
            "ko — Tiếng Hàn",
            "vi — Tiếng Việt",
            "auto — Tự động",
        ])
        self._stt_lang.setCurrentIndex(0)
        g_lay.addRow("🌐 Ngôn ngữ:", self._stt_lang)

        # Diarization
        self._stt_diarization = QCheckBox("Bật — nhận biết nhiều người nói")
        self._stt_diarization.setChecked(False)
        g_lay.addRow("👥 Người nói:", self._stt_diarization)

        hint_diar = QLabel("⚠ Bật sẽ load thêm model cam++ (tốn VRAM hơn)")
        hint_diar.setStyleSheet("color:#f5a623; font-size:10px;")
        hint_diar.setWordWrap(True)
        g_lay.addRow("", hint_diar)

        self._stt_silence_gap = QDoubleSpinBox()
        self._stt_silence_gap.setRange(0.5, 5.0)
        self._stt_silence_gap.setValue(1.5)
        self._stt_silence_gap.setSingleStep(0.1)
        self._stt_silence_gap.setDecimals(1)
        self._stt_silence_gap.setSuffix(" s")
        g_lay.addRow("⏸ Khoảng lặng:", self._stt_silence_gap)

        hint_gap = QLabel("FunASR Nano: ngắt dòng khi ngừng nói ≥ Xs. Không ảnh hưởng Qwen3 / Paraformer.")
        hint_gap.setStyleSheet("color:#555568; font-size:10px;")
        hint_gap.setWordWrap(True)
        g_lay.addRow("", hint_gap)

        lay.addWidget(grp)

        self._btn_run_stt = QPushButton("🎤  Nhận dạng giọng nói → SRT")
        self._btn_run_stt.setObjectName("btn_run_stt")
        self._btn_run_stt.clicked.connect(self._on_run_stt)
        lay.addWidget(self._btn_run_stt)

        hint_model = QLabel("⚠ Lần đầu chạy sẽ tải model về (~vài phút), cần CUDA")
        hint_model.setStyleSheet("color:#f5a623; font-size:10px; padding:4px;")
        hint_model.setWordWrap(True)
        lay.addWidget(hint_model)
        lay.addStretch()

        return self._scrollable(content)

    # ── Page 3: Dubbing ───────────────────────────────────────────────────────
    def _build_dubbing_page(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        grp = QGroupBox("Dubbing (OmniVoice → CapCut)")
        g_lay = QFormLayout(grp)
        g_lay.setSpacing(8)

        # Voice selector
        voice_row = QWidget()
        vr_lay = QHBoxLayout(voice_row)
        vr_lay.setContentsMargins(0, 0, 0, 0)
        self._voice_combo = QComboBox()
        self._voice_combo.setPlaceholderText("Chọn voice clone...")
        vr_lay.addWidget(self._voice_combo, stretch=1)

        btn_refresh = QPushButton("↻")
        btn_refresh.setFixedSize(30, 28)
        btn_refresh.setToolTip("Reload danh sách voice clones")
        btn_refresh.clicked.connect(self.voices_refresh.emit)
        vr_lay.addWidget(btn_refresh)
        g_lay.addRow("Voice:", voice_row)

        # CapCut project name
        self._capcut_project = QLineEdit()
        self._capcut_project.setPlaceholderText("Tên project CapCut...")
        g_lay.addRow("CapCut:", self._capcut_project)

        # Speech rate
        rate_row = QWidget()
        rt_lay = QHBoxLayout(rate_row)
        rt_lay.setContentsMargins(0, 0, 0, 0)
        self._speech_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self._speech_rate_slider.setRange(50, 200)
        self._speech_rate_slider.setValue(100)
        self._rate_label = QLabel("1.00×")
        self._rate_label.setMinimumWidth(46)
        self._speech_rate_slider.valueChanged.connect(
            lambda v: self._rate_label.setText(f"{v/100:.2f}×")
        )
        rt_lay.addWidget(self._speech_rate_slider, stretch=1)
        rt_lay.addWidget(self._rate_label)
        g_lay.addRow("Tốc độ:", rate_row)

        lay.addWidget(grp)

        self._btn_run_dubbing = QPushButton("🎵  Tạo Audio → CapCut")
        self._btn_run_dubbing.setObjectName("btn_run_dubbing")
        self._btn_run_dubbing.clicked.connect(self._on_run_dubbing)
        lay.addWidget(self._btn_run_dubbing)
        lay.addStretch()

        return self._scrollable(content)

    # ── Page 4: Single TTS ────────────────────────────────────────────────────
    def _build_single_tts_page(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # ── Text input ──
        grp_text = QGroupBox("Van ban can doc")
        t_lay = QVBoxLayout(grp_text)
        self._tts_text_input = QTextEdit()
        self._tts_text_input.setPlaceholderText("Nhap noi dung can doc vao day...")
        self._tts_text_input.setMinimumHeight(100)
        self._tts_text_input.setMaximumHeight(200)
        t_lay.addWidget(self._tts_text_input)
        lay.addWidget(grp_text)

        # ── Voice & Speed ──
        grp_settings = QGroupBox("Cai dat giong noi")
        s_lay = QFormLayout(grp_settings)
        s_lay.setSpacing(8)

        # Voice selector (shares data from set_voices)
        tts_voice_row = QWidget()
        tvr_lay = QHBoxLayout(tts_voice_row)
        tvr_lay.setContentsMargins(0, 0, 0, 0)
        self._tts_voice_combo = QComboBox()
        self._tts_voice_combo.setPlaceholderText("Chon giong noi...")
        tvr_lay.addWidget(self._tts_voice_combo, stretch=1)
        btn_tts_refresh = QPushButton("↻")
        btn_tts_refresh.setFixedSize(30, 28)
        btn_tts_refresh.setToolTip("Reload danh sach voice clones")
        btn_tts_refresh.clicked.connect(self.voices_refresh.emit)
        tvr_lay.addWidget(btn_tts_refresh)
        s_lay.addRow("Giong:", tts_voice_row)

        # Speed slider
        tts_rate_row = QWidget()
        trr_lay = QHBoxLayout(tts_rate_row)
        trr_lay.setContentsMargins(0, 0, 0, 0)
        self._tts_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self._tts_rate_slider.setRange(50, 200)
        self._tts_rate_slider.setValue(100)
        self._tts_rate_label = QLabel("1.00x")
        self._tts_rate_label.setMinimumWidth(46)
        self._tts_rate_slider.valueChanged.connect(
            lambda v: self._tts_rate_label.setText(f"{v/100:.2f}x")
        )
        trr_lay.addWidget(self._tts_rate_slider, stretch=1)
        trr_lay.addWidget(self._tts_rate_label)
        s_lay.addRow("Toc do:", tts_rate_row)

        lay.addWidget(grp_settings)

        # ── Buttons ──
        self._btn_run_tts = QPushButton("🎙  Tao giong noi")
        self._btn_run_tts.setObjectName("btn_run_single_tts")
        self._btn_run_tts.setStyleSheet(
            "QPushButton { background:#1a3a5c; border:1px solid #2a6ca8; color:#7ec8e3;"
            " font-weight:700; border-radius:6px; padding:8px; }"
            "QPushButton:hover { background:#2a5c8a; color:#ffffff; }"
            "QPushButton:disabled { background:#1a1a2e; color:#444460; border-color:#2a2a3d; }"
        )
        self._btn_run_tts.clicked.connect(self._on_run_single_tts)
        lay.addWidget(self._btn_run_tts)

        # Play button (hidden until audio is ready)
        self._btn_play_tts = QPushButton("▶  Nghe thu")
        self._btn_play_tts.setObjectName("btn_play_tts")
        self._btn_play_tts.setStyleSheet(
            "QPushButton { background:#1a4a2a; border:1px solid #2a8a4a; color:#7ee3a0;"
            " font-weight:700; border-radius:6px; padding:8px; }"
            "QPushButton:hover { background:#2a7a3a; color:#ffffff; }"
            "QPushButton:disabled { background:#1a1a2e; color:#444460; border-color:#2a2a3d; }"
        )
        self._btn_play_tts.setEnabled(False)
        self._btn_play_tts.clicked.connect(self._on_play_tts_audio)
        lay.addWidget(self._btn_play_tts)

        # Status label
        self._tts_status_label = QLabel("")
        self._tts_status_label.setStyleSheet("color:#606080; font-size:11px; padding:4px;")
        self._tts_status_label.setWordWrap(True)
        lay.addWidget(self._tts_status_label)

        self._tts_output_path: str = ""

        lay.addStretch()
        return self._scrollable(content)

    # ── Page 5: SRT Tools ─────────────────────────────────────────────────────
    def _build_tools_page(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        def _tool_btn(label: str, tooltip: str, signal) -> QPushButton:
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.clicked.connect(signal.emit)
            return btn

        grp_norm = QGroupBox("Chuẩn hóa SRT")
        n_lay = QVBoxLayout(grp_norm)
        n_lay.addWidget(_tool_btn(
            "📄  Chuẩn hóa trước khi dịch (Export Plain)",
            "Xuất plain subtitle (index + text, không timestamp) để đưa vào AI dịch",
            self.normalize_before_requested
        ))
        n_lay.addWidget(_tool_btn(
            "🔀  Chuẩn hóa sau khi dịch (Merge SRT)",
            "Ghép timestamp từ ocr.srt vào file plain đã dịch → tạo vietsub",
            self.normalize_after_requested
        ))
        lay.addWidget(grp_norm)

        grp_filter = QGroupBox("Lọc & Làm sạch")
        f_lay = QVBoxLayout(grp_filter)
        f_lay.addWidget(_tool_btn(
            "🔃  Lọc lặp SRT",
            "Gộp các dòng lặp liên tiếp: giữ Start dòng đầu và End dòng cuối",
            self.filter_dup_requested
        ))
        lay.addWidget(grp_filter)

        grp_tts = QGroupBox("Long tieng")
        t_lay = QVBoxLayout(grp_tts)
        btn_single = QPushButton("🔊  Long tieng single -> Dung tab TTS")
        btn_single.setEnabled(True)
        btn_single.clicked.connect(lambda: self._switch_tab(4))
        t_lay.addWidget(btn_single)
        lay.addWidget(grp_tts)

        lay.addStretch()
        return self._scrollable(content)

    # ── Public API ────────────────────────────────────────────────────────────
    def load_entry_for_edit(self, entry: SubtitleEntry):
        """Fill edit form with selected subtitle data and switch to Edit tab."""
        self._current_entry = entry
        self._edit_idx_label.setText(str(entry.index))
        self._edit_start.setValue(entry.start_ms)
        self._edit_end.setValue(entry.end_ms)
        self._edit_text.setPlainText(entry.text)
        self._edit_placeholder.hide()
        self._edit_form_widget.show()
        self.switch_to_edit_tab()

    def clear_edit_form(self):
        self._current_entry = None
        self._edit_form_widget.hide()
        self._edit_placeholder.show()

    def set_ocr_region_label(self, text: str):
        self._ocr_region_label.setText(text)

    def set_voices(self, voices: list[dict]):
        """Populate voice combo boxes (Dubbing tab + TTS tab)."""
        self._voice_combo.clear()
        self._tts_voice_combo.clear()
        for v in voices:
            label = v.get("name", v["id"])
            uid   = v["id"]
            self._voice_combo.addItem(label, userData=uid)
            self._tts_voice_combo.addItem(label, userData=uid)

    def set_busy(self, busy: bool):
        """Disable run buttons when a task is running."""
        self._btn_run_ocr.setEnabled(not busy)
        self._btn_run_stt.setEnabled(not busy)
        self._btn_run_dubbing.setEnabled(not busy)
        self._btn_run_tts.setEnabled(not busy)

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_apply(self):
        if self._current_entry is None:
            return
        start_ms = self._edit_start.value()
        end_ms   = self._edit_end.value()
        text     = self._edit_text.toPlainText()
        self.subtitle_applied.emit(self._current_entry.index, start_ms, end_ms, text)

    def _on_cancel_edit(self):
        self.clear_edit_form()
        self.subtitle_canceled.emit()

    def _on_run_ocr(self):
        lang_text = self._ocr_lang.currentText()
        lang_code = lang_text.split(" — ")[0].strip()
        fps       = self._ocr_fps.value()
        out_path  = self._ocr_out_path.text().strip()
        self.run_ocr_requested.emit(lang_code, fps, out_path)

    def _on_run_stt(self):
        model_key       = self._stt_model.currentData()
        lang_text       = self._stt_lang.currentText()
        lang_code       = lang_text.split(" — ")[0].strip()
        silence_gap     = self._stt_silence_gap.value()
        use_diarization = self._stt_diarization.isChecked()
        self.run_stt_requested.emit(model_key, lang_code, silence_gap, use_diarization)

    def _on_run_dubbing(self):
        voice_id = self._voice_combo.currentData()
        if not voice_id:
            voice_id = self._voice_combo.currentText()
        project  = self._capcut_project.text().strip()
        rate     = self._speech_rate_slider.value() / 100.0
        self.run_dubbing_requested.emit(voice_id or "", project, rate)

    def _on_run_single_tts(self):
        text     = self._tts_text_input.toPlainText().strip()
        voice_id = self._tts_voice_combo.currentData()
        if not voice_id:
            voice_id = self._tts_voice_combo.currentText()
        rate = self._tts_rate_slider.value() / 100.0

        if not text:
            self._tts_status_label.setText("⚠ Hay nhap van ban truoc.")
            return
        if not voice_id:
            self._tts_status_label.setText("⚠ Hay chon giong noi.")
            return

        # Build a stable output path in temp dir
        import hashlib, time
        from pathlib import Path
        slug = hashlib.md5(f"{voice_id}{text[:30]}{time.time()}".encode()).hexdigest()[:8]
        out_dir = Path(__file__).parent.parent.parent / "temp" / "standalone_tts"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"tts_{slug}.wav")

        self._tts_output_path = ""
        self._btn_play_tts.setEnabled(False)
        self._tts_status_label.setText("Dang tao giong noi...")
        self.single_tts_requested.emit(text, voice_id, rate, output_path)

    def on_single_tts_finished(self, success: bool, result: str):
        """Called by MainWindow when TTS job completes."""
        if success:
            self._tts_output_path = result
            self._btn_play_tts.setEnabled(True)
            self._tts_status_label.setText(f"Da tao xong: {result}")
        else:
            self._tts_status_label.setText(f"Loi: {result[:120]}")

    def _on_play_tts_audio(self):
        if not self._tts_output_path:
            return
        from pathlib import Path
        if not Path(self._tts_output_path).exists():
            self._tts_status_label.setText("File audio khong ton tai.")
            return
        import os
        os.startfile(self._tts_output_path)
