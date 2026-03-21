# backend/api/v1/translate.py
import asyncio
import os
from fastapi import APIRouter
from pydantic import BaseModel
from pathlib import Path
from core.task_manager import task_manager, TaskStatus
from services.translate_service import run_translate_pipeline

router = APIRouter()

class TranslateRequest(BaseModel):
    srt_path: str
    target_language: str = "vi"
    style: str = "lifestyle"          # "review" | "ancient_drama" | "lifestyle"
    glossary: dict[str, str] = {}
    output_dir: str = ""

@router.post("/translate")
async def start_translate(req: TranslateRequest):
    task = task_manager.create_task("translate")
    task.status = TaskStatus.RUNNING

    if req.output_dir:
        output_srt = os.path.join(req.output_dir, "translated.srt")
    else:
        srt_dir = Path(req.srt_path).parent
        output_srt = str(srt_dir / "translated.srt")

    asyncio.create_task(
        run_translate_pipeline(
            srt_path=req.srt_path,
            target_language=req.target_language,
            style=req.style,
            glossary=req.glossary,
            output_srt=output_srt,
            task=task
        )
    )

    return {
        "task_id": task.task_id,
        "message": "Dịch đã bắt đầu",
        "stream_url": f"/api/v1/tasks/{task.task_id}/stream"
    }
