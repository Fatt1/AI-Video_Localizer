# backend/api/v1/stt.py
"""
API endpoint cho Speech-to-Text (STT) sử dụng Fun-ASR-Nano.

Tách biệt hoàn toàn khỏi TTS (tts.py).

Endpoints:
    POST /api/v1/stt  — Bắt đầu STT pipeline, trả về task_id ngay
                        Client dùng SSE /api/v1/tasks/{id}/stream để nhận progress
"""
import asyncio
import logging

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from core.task_manager import TaskStatus, task_manager
from services.stt_pipeline import run_stt_pipeline

router = APIRouter(tags=["STT"])
logger = logging.getLogger(__name__)


class SttRequest(BaseModel):
    video_path: str = Field(..., description="Đường dẫn tới file video cần nhận dạng")
    output_srt_path: str = Field(
        default="",
        description="Đường dẫn output SRT (để trống = tự tạo cạnh file video)"
    )
    language: str = Field(
        default="中文",
        description="Ngôn ngữ nhận dạng: '中文' | 'auto' | 'en' | 'ja' | ..."
    )
    max_chars_per_line: int = Field(
        default=42,
        ge=10,
        le=120,
        description="Số ký tự tối đa trên 1 dòng SRT (thường 35–42) — chỉ là trần, không phải mục tiêu"
    )
    silence_gap_s: float = Field(
        default=1.5,
        ge=0.3,
        le=10.0,
        description="Khoảng lặng tối thiểu (giây) giữa 2 token để ngắt dòng SRT mới (mặc định 1.5s)"
    )
    hotwords: list[str] = Field(
        default_factory=list,
        description="Danh sách từ khóa ưu tiên nhận dạng"
    )


@router.post("/stt", status_code=status.HTTP_202_ACCEPTED)
async def start_stt(req: SttRequest):
    """
    Bắt đầu Speech-to-Text pipeline dùng Fun-ASR-Nano.

    Trả về task_id ngay lập tức (HTTP 202).
    Client subscribe SSE /api/v1/tasks/{task_id}/stream để nhận progress realtime.
    Khi hoàn tất, result chứa: { srt_path, subtitle_count }.
    """
    task = task_manager.create_task("stt")
    task.status = TaskStatus.RUNNING

    async def _run() -> None:
        try:
            await run_stt_pipeline(
                video_path=req.video_path,
                output_srt_path=req.output_srt_path,
                language=req.language,
                max_chars_per_line=req.max_chars_per_line,
                silence_gap_s=req.silence_gap_s,
                hotwords=req.hotwords if req.hotwords else None,
                task=task,
            )
        except Exception as exc:
            logger.exception("STT task %s failed unexpectedly", task.task_id)
            if task.status != TaskStatus.FAILED:
                await task.fail(f"{type(exc).__name__}: {exc}")

    asyncio.create_task(_run())

    return {
        "task_id": task.task_id,
        "message": "STT đã bắt đầu. Subscribe SSE để nhận progress.",
        "stream_url": f"/api/v1/tasks/{task.task_id}/stream",
    }
