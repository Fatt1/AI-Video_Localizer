# ui_pyside6/workers/stt_worker.py
"""
STT Worker — wraps backend stt_service in a QThread.
Emit log/progress tại từng giai đoạn thay vì chặn stdout.
"""
from __future__ import annotations

import logging

from .base_worker import BaseWorker


class SttWorker(BaseWorker):
    """
    Run Speech-to-Text (FunASR) on a video file.

    Args:
        video_path      : path to video file
        output_srt      : destination .srt path
        model_key       : "funasr-nano" | "qwen3-asr" | "paraformer"
        language        : language code (model-specific)
        silence_gap_s   : silence gap in seconds (FunASR Nano only)
        use_diarization : detect multiple speakers via cam++ spk_model
    """

    def __init__(
        self,
        video_path: str,
        output_srt: str,
        model_key: str = "funasr-nano",
        language: str = "zh",
        silence_gap_s: float = 1.5,
        use_diarization: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.video_path      = video_path
        self.output_srt      = output_srt
        self.model_key       = model_key
        self.language        = language
        self.silence_gap_s   = silence_gap_s
        self.use_diarization = use_diarization

    async def run_async(self):
        # Tắt bớt log ồn từ funasr/transformers ra stderr
        for noisy in ("funasr", "transformers", "modelscope", "torch"):
            logging.getLogger(noisy).setLevel(logging.ERROR)

        self.emit_log(
            f"[STT] ▶ Bắt đầu | model={self.model_key} | lang={self.language} | "
            f"diarization={self.use_diarization}"
        )

        try:
            # ── Bước 1: Import services ───────────────────────────────────────
            from pathlib import Path
            from services.stt_service import (
                get_stt_model,
                extract_audio,
                transcribe_audio,
                build_srt_content,
            )
            from core.config import TEMP_DIR

            # ── Bước 2: Load model ────────────────────────────────────────────
            self.emit_progress(5, f"⏳ Đang tải model {self.model_key}...")
            self.emit_log(f"[STT] Tải model {self.model_key} (lần đầu có thể mất vài phút)...")
            get_stt_model(model_key=self.model_key, use_diarization=self.use_diarization)
            self.emit_log(f"[STT] ✅ Model {self.model_key} sẵn sàng")

            # ── Bước 3: Trích xuất audio ──────────────────────────────────────
            self.emit_progress(20, "🔊 Đang trích xuất audio từ video...")
            self.emit_log(f"[STT] Trích xuất audio: {self.video_path}")
            video_stem = Path(self.video_path).stem
            wav_path   = str(TEMP_DIR / f"stt_{video_stem}.wav")
            extract_audio(self.video_path, wav_path)
            self.emit_log(f"[STT] ✅ Audio sẵn sàng: {wav_path}")

            # ── Bước 4: Nhận dạng giọng nói ──────────────────────────────────
            self.emit_progress(40, f"🎙 Đang nhận dạng giọng nói ({self.model_key})...")
            self.emit_log(f"[STT] Chạy nhận dạng (lang={self.language}, diarization={self.use_diarization})...")
            entries = transcribe_audio(
                audio_path=wav_path,
                model_key=self.model_key,
                language=self.language,
                silence_gap_s=self.silence_gap_s,
                use_diarization=self.use_diarization,
            )
            self.emit_log(f"[STT] ✅ Nhận dạng xong: {len(entries)} đoạn subtitle")

            # ── Bước 5: Build & lưu SRT ──────────────────────────────────────
            self.emit_progress(90, "💾 Đang lưu file SRT...")
            srt_content = build_srt_content(entries)
            Path(self.output_srt).write_text(srt_content, encoding="utf-8")
            self.emit_log(f"[STT] ✅ SRT đã lưu: {self.output_srt} ({len(entries)} dòng)")

            self.emit_progress(100, "✅ Nhận dạng giọng nói hoàn thành!")
            self.emit_finished(True, self.output_srt)

        except Exception as exc:
            self.emit_log(f"[STT] ❌ Lỗi: {exc}")
            self.emit_finished(False, str(exc))
