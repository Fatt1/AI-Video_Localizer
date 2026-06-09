# backend/api/v1/srt_merge.py
"""
Các endpoint xử lý file SRT (đồng bộ, không cần task_manager):

  POST /api/v1/srt/to-plain  — Chuẩn hóa trước khi dịch:
      Nhận file .srt → xuất plain txt (index + text, không timestamp).

  POST /api/v1/srt/merge     — Chuẩn hóa sau khi dịch:
      Nhận file plain đã dịch + ocr.srt → ghép thành SRT vietsub hoàn chỉnh.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.srt_merge_service import merge_plain_to_srt, srt_to_plain_subtitle

router = APIRouter()


# ─────────────────────────────────────────────────────────────
# POST /api/v1/srt/to-plain — Chuẩn hóa trước khi dịch
# ─────────────────────────────────────────────────────────────

class SrtToPlainRequest(BaseModel):
    srt_path: str
    """Đường dẫn file SRT nguồn (thường là ocr.srt)."""

    output_path: str = ""
    """
    Đường dẫn file plain output.
    Nếu để trống, đặt tên tự động: <stem>_plain.txt cạnh file SRT.
    """


class SrtToPlainResponse(BaseModel):
    output_path: str
    entry_count: int
    message: str


@router.post("/srt/to-plain", response_model=SrtToPlainResponse)
async def export_plain_subtitle(req: SrtToPlainRequest):
    """
    Chuẩn hóa SRT trước khi dịch:
    Đọc file .srt → xuất plain txt (chỉ index + text, không timestamp).

    Dùng file plain này để đưa vào AI dịch — AI không thể làm loạn timestamp.

    - **srt_path**: file SRT nguồn
    - **output_path**: đường dẫn output (để trống = tên tự động cạnh SRT)
    """
    try:
        result = srt_to_plain_subtitle(
            srt_path=req.srt_path,
            output_path=req.output_path or None,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xuất plain subtitle: {exc}")

    return SrtToPlainResponse(
        output_path=result.output_path,
        entry_count=result.entry_count,
        message=f"Đã xuất {result.entry_count} dòng → {result.output_path}",
    )


# ─────────────────────────────────────────────────────────────
# POST /api/v1/srt/merge — Chuẩn hóa sau khi dịch
# ─────────────────────────────────────────────────────────────

class SrtMergeRequest(BaseModel):
    translated_plain_path: str
    """Đường dẫn file plain đã dịch (index + text, không timestamp)."""

    ocr_srt_path: str = ""
    """
    Đường dẫn file ocr.srt có timestamp gốc.
    Nếu để trống, tự tìm ocr.srt cùng folder với translated_plain_path.
    """

    output_srt_path: str = ""
    """
    Đường dẫn file SRT output.
    Nếu để trống, đặt tên tự động: <tên_plain>_vietsub.srt cạnh file plain.
    """


class SrtMergeResponse(BaseModel):
    output_path: str
    merged_count: int
    skipped_count: int
    skipped_indices: list[int]
    message: str


@router.post("/srt/merge", response_model=SrtMergeResponse)
async def merge_srt(req: SrtMergeRequest):
    """
    Ghép timestamp từ ocr.srt vào file plain đã dịch để tạo SRT vietsub.

    - **translated_plain_path**: file plain tiếng Việt (format: index + text)
    - **ocr_srt_path**: file ocr.srt có timestamp (để trống = tự tìm cùng folder)
    - **output_srt_path**: output path (để trống = tên tự động)
    """
    try:
        result = merge_plain_to_srt(
            translated_plain_path=req.translated_plain_path,
            ocr_srt_path=req.ocr_srt_path or None,
            output_srt_path=req.output_srt_path or None,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi khi ghép SRT: {exc}")

    skipped_msg = ""
    if result.skipped_count > 0:
        skipped_msg = (
            f" (bỏ qua {result.skipped_count} dòng không tìm thấy index: "
            f"{result.skipped_indices[:10]}{'...' if len(result.skipped_indices) > 10 else ''})"
        )

    return SrtMergeResponse(
        output_path=result.output_path,
        merged_count=result.merged_count,
        skipped_count=result.skipped_count,
        skipped_indices=result.skipped_indices,
        message=f"Đã ghép {result.merged_count} dòng → {result.output_path}{skipped_msg}",
    )
