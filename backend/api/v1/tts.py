import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.config import TEMP_DIR
from core.task_manager import TaskStatus, task_manager
from services.dubbing_service import _normalize_tts_text
from services.tts_service import (
    list_voice_clones,
    list_vieneu_voice_clones,
    synthesize_line,
    synthesize_line_vieneu,
    get_active_engine,
    get_vieneu_backend_mode,
)

router = APIRouter(tags=["TTS"])
logger = logging.getLogger(__name__)


@router.get("/tts/voices")
async def get_voices():
    """List available OmniVoice clone profiles from voice_clones directory."""
    return {"voices": list_voice_clones()}


@router.get("/tts/vieneu/voices")
async def get_vieneu_voices():
    """List available VieNeu-TTS v2 clone profiles from voice_clones_vieneu directory."""
    return {"voices": list_vieneu_voice_clones()}


@router.get("/tts/engines")
async def get_engines():
    """List available TTS engines and which one is currently loaded."""
    return {
        "engines": [
            {
                "id": "omnivoice",
                "name": "OmniVoice",
                "description": "k2-fsa/OmniVoice — Vietnamese TTS",
                "voice_dir": "voice_clones",
            },
            {
                "id": "vieneu",
                "name": "VieNeu-TTS v2",
                "description": "VieNeu-TTS v2 — GPU CUDA, NeuCodec Distill",
                "voice_dir": "voice_clones_vieneu",
            },
        ],
        "active_engine": get_active_engine(),
        "vieneu_backend": get_vieneu_backend_mode(),
    }


class DubbingRequest(BaseModel):
    srt_path: str
    voice_id: str
    capcut_project_name: str
    speech_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    tts_engine: str = Field(
        default="omnivoice",
        description="TTS engine: 'omnivoice' hoặc 'vieneu'",
    )


@router.post("/dubbing", status_code=status.HTTP_202_ACCEPTED)
async def start_dubbing(req: DubbingRequest):
    """Start dubbing pipeline: TTS generation and CapCut injection.

    Use tts_engine='omnivoice' (default) or tts_engine='vieneu' to choose engine.
    """
    from services.dubbing_service import run_dubbing_pipeline

    task = task_manager.create_task("dubbing")
    task.status = TaskStatus.RUNNING

    async def _run() -> None:
        try:
            await run_dubbing_pipeline(
                srt_path=req.srt_path,
                voice_id=req.voice_id,
                capcut_project_name=req.capcut_project_name,
                speech_rate=req.speech_rate,
                tts_engine=req.tts_engine,
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


# ─────────────────────────────────────────────────────────────
# Standalone TTS: tạo giọng nói từ text thuần (không cần SRT)
# ─────────────────────────────────────────────────────────────

_STANDALONE_TTS_DIR = TEMP_DIR / "standalone_tts"
_STANDALONE_TTS_DIR.mkdir(parents=True, exist_ok=True)


class TtsSynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Văn bản cần tổng hợp giọng nói")
    voice_id: str = Field(..., description="ID voice clone")
    speech_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    output_filename: str = Field(default="", description="Tên file output (để trống = tự tạo)")


class TtsSynthesizeResponse(BaseModel):
    audio_path: str
    audio_filename: str
    text: str
    voice_id: str
    speech_rate: float


class VieneuSynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Văn bản cần tổng hợp giọng nói")
    voice_id: str = Field(..., description="ID voice clone VieNeu")
    speech_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    temperature: float = Field(default=1.0, ge=0.1, le=2.0, description="Sampling temperature")
    max_chars: int = Field(default=256, ge=50, le=1000, description="Max chars per chunk")
    output_filename: str = Field(default="", description="Tên file output (để trống = tự tạo)")


class VieneuSynthesizeResponse(BaseModel):
    audio_path: str
    audio_filename: str
    text: str
    voice_id: str
    speech_rate: float
    temperature: float
    engine: str = "vieneu"


@router.post("/tts/synthesize", response_model=TtsSynthesizeResponse)
async def synthesize_text(req: TtsSynthesizeRequest):
    """
    Tạo giọng nói từ văn bản thuần bằng OmniVoice (không cần SRT).
    - **text**: văn bản cần đọc
    - **voice_id**: ID voice clone (từ voice_clones/)
    - **speech_rate**: tốc độ đọc (0.5–2.0, mặc định 1.0)
    - **output_filename**: tên file output tùy chỉnh (để trống = tên tự động)
    """
    text = _normalize_tts_text(req.text)
    if not text:
        raise HTTPException(status_code=422, detail="text không được rỗng sau khi chuẩn hóa")

    if req.output_filename.strip():
        filename = req.output_filename.strip()
        if not filename.endswith(".wav"):
            filename += ".wav"
    else:
        filename = f"tts_{uuid.uuid4().hex[:8]}.wav"

    output_path = _STANDALONE_TTS_DIR / filename

    try:
        await synthesize_line(
            text=text,
            voice_id=req.voice_id,
            output_path=str(output_path),
            speech_rate=req.speech_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Standalone TTS synthesis failed")
        raise HTTPException(status_code=500, detail=f"Lỗi tổng hợp giọng nói: {exc}")

    if not output_path.exists() or output_path.stat().st_size <= 44:
        raise HTTPException(status_code=500, detail="File audio không được tạo hoặc bị rỗng")

    return TtsSynthesizeResponse(
        audio_path=str(output_path),
        audio_filename=filename,
        text=text,
        voice_id=req.voice_id,
        speech_rate=req.speech_rate,
    )


@router.post("/tts/vieneu/synthesize", response_model=VieneuSynthesizeResponse)
async def synthesize_text_vieneu(req: VieneuSynthesizeRequest):
    """
    Tạo giọng nói từ văn bản thuần bằng VieNeu-TTS v2 (GPU).
    - **text**: văn bản cần đọc
    - **voice_id**: ID voice clone (từ voice_clones_vieneu/)
    - **speech_rate**: tốc độ đọc (0.5–2.0, mặc định 1.0)
    - **temperature**: sampling temperature (0.1–2.0, mặc định 1.0)
    - **max_chars**: max chars per chunk (50–1000, mặc định 256)
    - **output_filename**: tên file output tùy chỉnh (để trống = tên tự động)
    """
    text = _normalize_tts_text(req.text)
    if not text:
        raise HTTPException(status_code=422, detail="text không được rỗng sau khi chuẩn hóa")

    if req.output_filename.strip():
        filename = req.output_filename.strip()
        if not filename.endswith(".wav"):
            filename += ".wav"
    else:
        filename = f"vieneu_{uuid.uuid4().hex[:8]}.wav"

    output_path = _STANDALONE_TTS_DIR / filename

    try:
        await synthesize_line_vieneu(
            text=text,
            voice_id=req.voice_id,
            output_path=str(output_path),
            speech_rate=req.speech_rate,
            temperature=req.temperature,
            max_chars=req.max_chars,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("VieNeu TTS synthesis failed")
        raise HTTPException(status_code=500, detail=f"Lỗi tổng hợp VieNeu: {exc}")

    if not output_path.exists() or output_path.stat().st_size <= 44:
        raise HTTPException(status_code=500, detail="File audio không được tạo hoặc bị rỗng")

    return VieneuSynthesizeResponse(
        audio_path=str(output_path),
        audio_filename=filename,
        text=text,
        voice_id=req.voice_id,
        speech_rate=req.speech_rate,
        temperature=req.temperature,
    )


@router.get("/tts/audio/{filename}")
async def get_audio_file(filename: str):
    """
    Trả về file audio WAV để FE phát trực tiếp.
    GET /api/v1/tts/audio/<filename>
    """
    safe_name = Path(filename).name
    audio_path = _STANDALONE_TTS_DIR / safe_name

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"File audio '{safe_name}' không tồn tại")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/wav",
        filename=safe_name,
    )
