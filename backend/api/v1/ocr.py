# backend/api/v1/ocr.py
import asyncio
import os
from fastapi import APIRouter
from pydantic import BaseModel
from pathlib import Path
from core.task_manager import task_manager, TaskStatus
from services.ocr_service import run_ocr_pipeline

router = APIRouter()


class OcrRequest(BaseModel):
    video_path: str
    crop_region: list[int]   # [X, Y, W, H]
    fps: float = 4.0         # Tăng lên 4 FPS để bắt phụ đề ngắn < 0.5s
    output_dir: str = ""     # Nếu rỗng → lưu cạnh video


@router.post("/ocr")
async def start_ocr(req: OcrRequest):
    # Tạo task
    task = task_manager.create_task("ocr")
    task.status = TaskStatus.RUNNING

    # Xác định output path
    if req.output_dir:
        output_srt = os.path.join(req.output_dir, "ocr.srt")
    else:
        video_dir = Path(req.video_path).parent
        output_srt = str(video_dir / "ocr.srt")

    # Chạy pipeline trong background
    asyncio.create_task(
        run_ocr_pipeline(
            video_path=req.video_path,
            crop_region=req.crop_region,
            fps=req.fps,
            output_srt=output_srt,
            task=task
        )
    )

    return {
        "task_id": task.task_id,
        "message": "OCR đã bắt đầu. Subscribe SSE để nhận progress.",
        "stream_url": f"/api/v1/tasks/{task.task_id}/stream"
    }
