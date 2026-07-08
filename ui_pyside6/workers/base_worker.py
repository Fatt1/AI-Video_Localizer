# ui_pyside6/workers/base_worker.py
"""
Base QThread worker with asyncio support for async backend functions.
"""
from __future__ import annotations

import asyncio
import traceback
from typing import Any, Callable, Coroutine

from PySide6.QtCore import QThread, Signal


class BaseWorker(QThread):
    """
    Run an async coroutine in a background QThread.

    Signals:
        log_emitted(str)         — Log message for console panel
        progress_updated(int, str) — (percent 0–100, message)
        task_finished(bool, str) — (success, message_or_result)
        error_occurred(str)      — Critical error message
    """

    log_emitted      = Signal(str)
    progress_updated = Signal(int, str)
    task_finished    = Signal(bool, str)
    error_occurred   = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        """Request cancellation. Backend must check task.is_cancelled()."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    # ── Subclasses must implement this ──────────────────────────────────────
    async def run_async(self) -> None:
        """Override in subclass: put your async logic here."""
        raise NotImplementedError

    # ── QThread entry point ─────────────────────────────────────────────────
    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_async())
        except Exception as exc:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"{type(exc).__name__}: {exc}\n{tb}")
            self.task_finished.emit(False, str(exc))
        finally:
            loop.close()

    # ── Convenience emit helpers (can be called from async context) ─────────
    def emit_log(self, message: str):
        self.log_emitted.emit(message)

    def emit_progress(self, percent: int, message: str):
        self.progress_updated.emit(percent, message)

    def emit_finished(self, success: bool, message: str):
        self.task_finished.emit(success, message)
