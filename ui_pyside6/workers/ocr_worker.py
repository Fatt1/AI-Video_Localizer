# ui_pyside6/workers/ocr_worker.py
"""
OCR Worker — wraps backend run_ocr_pipeline in a QThread.
Supports OCR language selection by resetting the engine singleton when lang changes.
"""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from .base_worker import BaseWorker


class _ProgressTask:
    """
    Minimal Task-like object that satisfies backend's Task interface.
    Bridges backend progress/status updates → Qt signals.
    """
    def __init__(self, worker: "OcrWorker"):
        self._worker = worker
        self.task_id = "ocr_ui"
        self._cancelled = False

    def is_cancelled(self) -> bool:
        return self._worker.is_cancelled or self._cancelled

    async def update(self, progress: int, message: str, status=None):
        self._worker.emit_progress(progress, message)
        self._worker.emit_log(f"[OCR] {message}")

    async def complete(self, result: dict | None = None):
        self._worker.emit_progress(100, "Hoàn thành OCR!")
        self._worker.emit_log("[OCR] ✅ Hoàn thành!")
        if result:
            srt_path = result.get("srt_path", "")
            count    = result.get("subtitle_count", 0)
            self._worker.emit_finished(True, f"{srt_path}|{count}")

    async def fail(self, message: str):
        self._worker.emit_log(f"[OCR] ❌ {message}")
        self._worker.emit_finished(False, message)


class OcrWorker(BaseWorker):
    """
    Runs OCR pipeline in background.

    Args:
        video_path  : path to video file
        crop_region : [x, y, w, h] in pixels
        fps         : frames per second to sample
        output_srt  : output .srt file path
        lang        : PaddleOCR language code (ch, en, japan, korean, vi)
    """

    def __init__(
        self,
        video_path: str,
        crop_region: list[int],
        fps: float,
        output_srt: str,
        lang: str = "ch",
        parent=None,
    ):
        super().__init__(parent)
        self.video_path  = video_path
        self.crop_region = crop_region
        self.fps         = fps
        self.output_srt  = output_srt
        self.lang        = lang

    async def run_async(self):
        self.emit_log(f"[OCR] Bắt đầu | video={self.video_path} lang={self.lang}")
        self.emit_progress(0, "Đang khởi tạo OCR engine...")

        # Import backend (sys.path adjusted in main.py)
        import services.ocr_service as ocr_svc

        # Reset engine if language changed
        current_lang = getattr(ocr_svc._ocr_engine, "_lang", None) if ocr_svc._ocr_engine else None
        if self.lang != "ch" or (ocr_svc._ocr_engine is not None and current_lang != self.lang):
            # Force reload engine with new lang
            ocr_svc._ocr_engine = None

        # Patch PaddleOCR init to use selected lang
        _orig_init = None
        if self.lang != "ch":
            from paddleocr import PaddleOCR as _POCR
            _orig_get = ocr_svc.get_ocr_engine

            def _patched_get():
                if ocr_svc._ocr_engine is None:
                    ocr_svc._ocr_engine = _POCR(
                        use_angle_cls=True,
                        use_gpu=True,
                        lang=self.lang,
                        show_log=False,
                    )
                return ocr_svc._ocr_engine

            ocr_svc.get_ocr_engine = _patched_get

        # Capture stdout/stderr from backend prints
        log_buf = io.StringIO()
        try:
            with redirect_stdout(log_buf), redirect_stderr(log_buf):
                task = _ProgressTask(self)
                await ocr_svc.run_ocr_pipeline(
                    video_path=self.video_path,
                    crop_region=self.crop_region,
                    fps=self.fps,
                    output_srt=self.output_srt,
                    task=task,
                )
        finally:
            # Restore original if patched
            if self.lang != "ch" and _orig_get is not None:
                ocr_svc.get_ocr_engine = _orig_get

            captured = log_buf.getvalue()
            if captured.strip():
                for line in captured.strip().splitlines():
                    if line.strip():
                        self.emit_log(line)
