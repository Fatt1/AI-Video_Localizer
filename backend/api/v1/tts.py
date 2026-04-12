import asyncio
import logging

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from core.task_manager import TaskStatus, task_manager
from services.dubbing_service import run_dubbing_pipeline
from services.tts_service import list_voice_clones

router = APIRouter(tags=["TTS"])
logger = logging.getLogger(__name__)


@router.get("/tts/voices")
async def get_voices():
    """List available OmniVoice clone profiles from voice_clones directory."""
    return {"voices": list_voice_clones()}


class DubbingRequest(BaseModel):
    srt_path: str
    voice_id: str
    capcut_project_name: str
    speech_rate: float = Field(default=1.0, ge=0.5, le=2.0)


@router.post("/dubbing", status_code=status.HTTP_202_ACCEPTED)
async def start_dubbing(req: DubbingRequest):
    """Start dubbing pipeline: OmniVoice TTS generation and CapCut injection."""
    task = task_manager.create_task("dubbing")
    task.status = TaskStatus.RUNNING

    async def _run() -> None:
        try:
            await run_dubbing_pipeline(
                srt_path=req.srt_path,
                voice_id=req.voice_id,
                capcut_project_name=req.capcut_project_name,
                speech_rate=req.speech_rate,
                task=task,
            )
        except Exception as exc:
            logger.exception("Dubbing task %s failed unexpectedly", task.task_id)
            if task.status != TaskStatus.FAILED:
                await task.fail(f"{type(exc).__name__}: {exc}")

    asyncio.create_task(_run())

    return {
        "task_id": task.task_id,
        "message": "Dubbing đã bắt đầu. Subscribe SSE để nhận progress.",
        "stream_url": f"/api/v1/tasks/{task.task_id}/stream",
    }
