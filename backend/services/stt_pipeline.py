# backend/services/stt_pipeline.py
"""
Pipeline STT hoàn chỉnh với progress reporting cho Task system.

Flow:
1. Validate input video
2. Extract audio → WAV 16kHz mono
3. Load model + run STT (Fun-ASR-Nano)
4. Build SRT từ token timestamps
5. Save SRT + load vào result
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.config import TEMP_DIR
from core.task_manager import Task
from services.stt_service import (
    extract_audio,
    transcribe_audio,
    build_srt_content,
    unload_stt_model,
)

logger = logging.getLogger(__name__)


async def run_stt_pipeline(
    video_path: str,
    output_srt_path: str = "",
    language: str = "中文",
    max_chars_per_line: int = 42,
    silence_gap_s: float = 1.5,
    hotwords: list[str] | None = None,
    task: Task = None,
) -> None:
    """
    Pipeline STT đầy đủ, chạy trong background task với SSE progress.

    Args:
        video_path: Đường dẫn video đầu vào
        output_srt_path: Đường dẫn SRT output (tự tạo nếu trống)
        language: Ngôn ngữ nhận dạng ("中文", "auto", ...)
        max_chars_per_line: Giới hạn ký tự mỗi dòng SRT
        hotwords: Từ khóa ưu tiên nhận dạng
        task: Task object để report progress
    """
    video_path_obj = Path(video_path)

    # ── Bước 1: Validate input ────────────────────────────────────────────
    await task.update(5, "Kiểm tra file video...")
    if not video_path_obj.exists():
        await task.fail(f"File video không tồn tại: {video_path}")
        return

    if task.is_cancelled():
        return

    # ── Bước 2: Tạo đường dẫn output ─────────────────────────────────────
    if not output_srt_path:
        output_srt_path = str(video_path_obj.with_suffix(".srt"))

    # File WAV tạm
    wav_path = str(TEMP_DIR / f"stt_{video_path_obj.stem}.wav")

    # ── Bước 3: Trích xuất audio ──────────────────────────────────────────
    await task.update(10, "Đang trích xuất audio từ video (FFmpeg)...")
    try:
        extract_audio(video_path, wav_path)
    except Exception as e:
        await task.fail(f"Lỗi trích xuất audio: {e}")
        return

    if task.is_cancelled():
        return

    # ── Bước 4 + 5: STT + Save SRT — wrap trong try/finally để luôn giải phóng VRAM ──
    entries = []
    try:
        # Load model + nhận dạng
        await task.update(20, "Đang tải model Fun-ASR-Nano (lần đầu có thể mất vài phút)...")
        import asyncio
        loop = asyncio.get_event_loop()

        await task.update(30, "Model đã sẵn sàng. Đang nhận dạng giọng nói...")

        entries = await loop.run_in_executor(
            None,
            lambda: transcribe_audio(
                audio_path=wav_path,
                language=language,
                max_chars_per_line=max_chars_per_line,
                silence_gap_s=silence_gap_s,
                hotwords=hotwords or [],
            )
        )

        if task.is_cancelled():
            return

        # Build và lưu SRT
        await task.update(88, f"Đang xuất {len(entries)} dòng SRT...")
        srt_content = build_srt_content(entries)
        Path(output_srt_path).write_text(srt_content, encoding="utf-8")
        logger.info("SRT saved: %s (%d entries)", output_srt_path, len(entries))

    except Exception as e:
        await task.fail(f"Lỗi STT pipeline: {e}")
        return

    finally:
        # ── Luôn giải phóng VRAM dù thành công hay thất bại ──────────────
        await task.update(95, "Đang giải phóng VRAM...")
        unload_stt_model()  # gc.collect() + torch.cuda.empty_cache() bên trong

    # ── Hoàn tất ──────────────────────────────────────────────────────────
    await task.complete(result={
        "srt_path": output_srt_path,
        "subtitle_count": len(entries),
        "message": f"STT hoàn tất: {len(entries)} dòng subtitle → {Path(output_srt_path).name}",
    })
