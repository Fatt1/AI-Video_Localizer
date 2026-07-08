# ui_pyside6/workers/dubbing_worker.py
"""
Dubbing Worker — wraps backend run_dubbing_pipeline in a QThread.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout, redirect_stderr

from .base_worker import BaseWorker


class _ProgressTask:
    """Bridges backend Task interface → Qt signals."""

    def __init__(self, worker: "DubbingWorker"):
        self._worker = worker
        self.task_id = "dubbing_ui"

    def is_cancelled(self) -> bool:
        return self._worker.is_cancelled

    async def update(self, progress: int, message: str, status=None):
        self._worker.emit_progress(progress, message)
        self._worker.emit_log(f"[Dubbing] {message}")

    async def complete(self, result: dict | None = None):
        self._worker.emit_progress(100, "Dubbing hoàn thành!")
        self._worker.emit_log("[Dubbing] ✅ Hoàn thành!")
        msg = ""
        if result:
            msg = result.get("message", "")
        self._worker.emit_finished(True, msg)

    async def fail(self, message: str):
        self._worker.emit_log(f"[Dubbing] ❌ {message}")
        self._worker.emit_finished(False, message)


class DubbingWorker(BaseWorker):
    """
    Run OmniVoice TTS + inject into CapCut project.

    Args:
        srt_path            : SRT file to read
        voice_id            : voice clone ID (stem of .wav file)
        capcut_project_name : CapCut project name
        speech_rate         : TTS speed (0.5–2.0)
    """

    def __init__(
        self,
        srt_path: str,
        voice_id: str,
        capcut_project_name: str,
        speech_rate: float = 1.0,
        parent=None,
    ):
        super().__init__(parent)
        self.srt_path            = srt_path
        self.voice_id            = voice_id
        self.capcut_project_name = capcut_project_name
        self.speech_rate         = speech_rate

    async def run_async(self):
        self.emit_log(
            f"[Dubbing] Bắt đầu | srt={self.srt_path} voice={self.voice_id} "
            f"project={self.capcut_project_name} rate={self.speech_rate}"
        )
        self.emit_progress(0, "Khởi tạo dubbing pipeline...")

        from services.dubbing_service import run_dubbing_pipeline

        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                task = _ProgressTask(self)
                await run_dubbing_pipeline(
                    srt_path=self.srt_path,
                    voice_id=self.voice_id,
                    capcut_project_name=self.capcut_project_name,
                    task=task,
                    speech_rate=self.speech_rate,
                )
        finally:
            captured = buf.getvalue()
            for line in captured.strip().splitlines():
                if line.strip():
                    self.emit_log(line)


class SrtToolWorker(BaseWorker):
    """
    Generic synchronous SRT tool worker (normalize, merge, filter).

    Args:
        func      : callable that does the work, receives **kwargs
        kwargs    : keyword arguments for func
        task_name : display name for logs
    """

    def __init__(self, func, kwargs: dict, task_name: str = "SRT Tool", parent=None):
        super().__init__(parent)
        self._func      = func
        self._kwargs    = kwargs
        self._task_name = task_name

    async def run_async(self):
        self.emit_log(f"[{self._task_name}] Bắt đầu...")
        self.emit_progress(0, f"Đang chạy {self._task_name}...")
        try:
            result = self._func(**self._kwargs)
            self.emit_progress(100, f"{self._task_name} hoàn thành!")
            # result might be a dataclass with output_path
            out_path = getattr(result, "output_path", str(result))
            self.emit_log(f"[{self._task_name}] ✅ {out_path}")
            self.emit_finished(True, out_path)
        except Exception as exc:
            self.emit_log(f"[{self._task_name}] ❌ {exc}")
            self.emit_finished(False, str(exc))
