# ui_pyside6/workers/single_tts_worker.py
"""
Single TTS Worker — tạo giọng nói từ văn bản thuần (không cần SRT).
Dùng trực tiếp synthesize_line từ tts_service.
"""
from __future__ import annotations

from .base_worker import BaseWorker


class SingleTtsWorker(BaseWorker):
    """
    Run standalone TTS synthesis for a single piece of text.

    Args:
        text        : text to synthesize
        voice_id    : voice clone ID
        output_path : destination WAV file path
        speech_rate : speech rate 0.5–2.0
    """

    def __init__(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        speech_rate: float = 1.0,
        parent=None,
    ):
        super().__init__(parent)
        self.text        = text
        self.voice_id    = voice_id
        self.output_path = output_path
        self.speech_rate = speech_rate

    async def run_async(self):
        self.emit_log(
            f"[TTS] Bat dau | voice={self.voice_id} | rate={self.speech_rate:.2f}x | "
            f"chars={len(self.text)}"
        )
        self.emit_progress(0, "Dang khoi tao TTS...")

        try:
            from services.tts_service import get_tts_model, unload_tts_model
            from services.dubbing_service import _normalize_tts_text

            text = _normalize_tts_text(self.text)
            if not text:
                self.emit_finished(False, "Text rong sau khi chuan hoa")
                return

            self.emit_progress(10, "Dang tai model OmniVoice (lan dau co the mat vai phut)...")
            self.emit_log("[TTS] Tai model OmniVoice...")
            get_tts_model()
            self.emit_log("[TTS] Model san sang")

            self.emit_progress(30, "Dang tong hop giong noi...")
            self.emit_log(f"[TTS] Tong hop: {text[:60]}...")

            from services.tts_service import synthesize_line
            result_path = await synthesize_line(
                text=text,
                voice_id=self.voice_id,
                output_path=self.output_path,
                speech_rate=self.speech_rate,
            )

            self.emit_progress(100, "Tong hop giong noi hoan thanh!")
            self.emit_log(f"[TTS] Da luu: {result_path}")
            self.emit_finished(True, result_path)

        except Exception as exc:
            self.emit_log(f"[TTS] Loi: {exc}")
            self.emit_finished(False, str(exc))
        finally:
            try:
                from services.tts_service import unload_tts_model
                unload_tts_model()
            except Exception:
                pass
