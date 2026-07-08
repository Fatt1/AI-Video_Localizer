# ui_pyside6/workers/stt_worker.py
"""
STT Worker — wraps backend stt_service in a QThread.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout, redirect_stderr

from .base_worker import BaseWorker


class SttWorker(BaseWorker):
    """
    Run Speech-to-Text (FunASR) on a video file.

    Args:
        video_path        : path to video file
        output_srt        : destination .srt path
        language          : FunASR language string (default '中文')
        max_chars_per_line: max chars per SRT line
        silence_gap_s     : silence gap in seconds to split lines
    """

    def __init__(
        self,
        video_path: str,
        output_srt: str,
        language: str = "中文",
        max_chars_per_line: int = 42,
        silence_gap_s: float = 1.5,
        parent=None,
    ):
        super().__init__(parent)
        self.video_path         = video_path
        self.output_srt         = output_srt
        self.language           = language
        self.max_chars_per_line = max_chars_per_line
        self.silence_gap_s      = silence_gap_s

    async def run_async(self):
        self.emit_log(f"[STT] Bắt đầu | video={self.video_path} lang={self.language}")
        self.emit_progress(0, "Đang tải STT model (Fun-ASR-Nano)...")

        from services.stt_service import run_stt_and_save_srt

        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                self.emit_progress(5, "Đang trích xuất audio từ video...")
                srt_path = run_stt_and_save_srt(
                    video_path=self.video_path,
                    output_srt_path=self.output_srt,
                    language=self.language,
                    max_chars_per_line=self.max_chars_per_line,
                )
            self.emit_progress(100, "Nhận dạng giọng nói hoàn thành!")
            self.emit_log(f"[STT] ✅ SRT lưu tại: {srt_path}")
            self.emit_finished(True, srt_path)
        except Exception as exc:
            self.emit_log(f"[STT] ❌ Lỗi: {exc}")
            self.emit_finished(False, str(exc))
        finally:
            captured = buf.getvalue()
            for line in captured.strip().splitlines():
                if line.strip():
                    self.emit_log(line)
