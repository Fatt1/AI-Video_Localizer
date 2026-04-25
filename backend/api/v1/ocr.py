# backend/api/v1/ocr.py
import asyncio
import os
import traceback
from fastapi import APIRouter
from pydantic import BaseModel
from pathlib import Path
from core.task_manager import task_manager, TaskStatus, Task
from services.ocr_service import run_ocr_pipeline

router = APIRouter()


class OcrRequest(BaseModel):
    video_path: str
    crop_region: list[int]   # [X, Y, W, H]
    fps: float = 4.0         # Tăng lên 4 FPS để bắt phụ đề ngắn < 0.5s
    output_dir: str = ""     # Nếu rỗng → lưu cạnh video


def _to_user_error_message(exc: Exception) -> str:
    msg = str(exc)
    lowered = msg.lower()
    if (
        "cudnn64_8.dll" in lowered
        or ("dynamic library" in lowered and "error code is 126" in lowered)
    ):
        return (
            "OCR GPU thất bại vì không nạp được CUDA/cuDNN DLL (cudnn64_8.dll). "
            "Cấu hình hiện tại là GPU-only nên task sẽ fail ngay. Hãy kiểm tra PATH và package nvidia trong .venv."
        )
    return f"OCR thất bại: {msg}"


async def _run_ocr_pipeline_safe(
    video_path: str,
    crop_region: list[int],
    fps: float,
    output_srt: str,
    task: Task,
):
    try:
        await run_ocr_pipeline(
            video_path=video_path,
            crop_region=crop_region,
            fps=fps,
            output_srt=output_srt,
            task=task,
        )
    except Exception as exc:
        traceback.print_exc()
        await task.fail(_to_user_error_message(exc))


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
        _run_ocr_pipeline_safe(
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
