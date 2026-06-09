# backend/services/srt_merge_service.py
"""
Các service xử lý file SRT:

1. srt_to_plain_subtitle  — Chuẩn hóa trước khi dịch:
       Nhận file .srt bất kỳ → xuất plain txt (chỉ index + text, không timestamp)
       Đưa vào AI dịch an toàn (AI không thể làm loạn thứ tự timestamp).

2. merge_plain_to_srt  — Chuẩn hóa sau khi dịch:
       Nhận file plain đã dịch + đọc ocr.srt cùng folder lấy timestamp
       → ghép thành file SRT vietsub hoàn chỉnh.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────

@dataclass
class SrtEntry:
    index: int
    start: str   # "HH:MM:SS,mmm"
    end: str     # "HH:MM:SS,mmm"
    text: str


@dataclass
class PlainEntry:
    index: int
    text: str


@dataclass
class MergeResult:
    output_path: str
    merged_count: int
    skipped_count: int
    skipped_indices: list[int]


@dataclass
class PlainExportResult:
    output_path: str
    entry_count: int


# ─────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────

_TIMESTAMP_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})"
)


def parse_srt(srt_path: str) -> dict[int, SrtEntry]:
    """
    Đọc file SRT → dict {index: SrtEntry}.
    Hỗ trợ cả dấu phẩy (,) và dấu chấm (.) trong timestamp.
    """
    # utf-8-sig tự động strip BOM (\ufeff) nếu file được lưu bằng UTF-8 BOM
    # (phổ biến trên Windows / Notepad) để tránh int('\ufeff1') fail.
    content = Path(srt_path).read_text(encoding="utf-8-sig")
    blocks = re.split(r"\r?\n\r?\n", content.strip())
    entries: dict[int, SrtEntry] = {}

    for block in blocks:
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if len(lines) < 3:
            continue

        # Dòng 1: chỉ số
        try:
            idx = int(lines[0])
        except ValueError:
            continue

        # Dòng 2: timestamp
        m = _TIMESTAMP_RE.match(lines[1])
        if not m:
            continue

        start = m.group(1).replace(".", ",")
        end = m.group(2).replace(".", ",")

        # Dòng 3+: text (nhiều dòng)
        text = "\n".join(lines[2:])
        entries[idx] = SrtEntry(index=idx, start=start, end=end, text=text)

    return entries


def parse_plain_subtitle(plain_path: str) -> list[PlainEntry]:
    """
    Đọc file plain subtitle (chỉ số + text, không có timestamp).

    Format chấp nhận:
        1
        Nội dung câu 1

        2
        Nội dung câu 2

    Trả về list PlainEntry theo thứ tự trong file.
    """
    # utf-8-sig tự động strip BOM (\ufeff) nếu file được lưu bằng UTF-8 BOM
    content = Path(plain_path).read_text(encoding="utf-8-sig")
    blocks = re.split(r"\r?\n\r?\n", content.strip())
    entries: list[PlainEntry] = []

    for block in blocks:
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue

        # Dòng đầu phải là chỉ số nguyên
        try:
            idx = int(lines[0])
        except ValueError:
            continue

        text = "\n".join(lines[1:])
        entries.append(PlainEntry(index=idx, text=text))

    return entries


# ─────────────────────────────────────────────────────────────
# Merge logic
# ─────────────────────────────────────────────────────────────

def _find_ocr_srt(plain_path: str) -> str:
    """
    Tìm ocr.srt cùng folder với file plain.
    Ném FileNotFoundError nếu không tìm thấy.
    """
    folder = Path(plain_path).parent
    candidate = folder / "ocr.srt"
    if not candidate.exists():
        raise FileNotFoundError(
            f"Không tìm thấy ocr.srt trong thư mục '{folder}'. "
            "Hãy đảm bảo file plain dịch nằm cùng folder với ocr.srt."
        )
    return str(candidate)


def _default_output_path(plain_path: str) -> str:
    """Tạo tên file output mặc định cạnh file plain."""
    p = Path(plain_path)
    return str(p.parent / (p.stem + "_vietsub.srt"))


def _format_srt_block(index: int, start: str, end: str, text: str) -> str:
    return f"{index}\n{start} --> {end}\n{text}\n\n"


def merge_plain_to_srt(
    translated_plain_path: str,
    ocr_srt_path: str | None = None,
    output_srt_path: str | None = None,
) -> MergeResult:
    """
    Ghép timestamp từ ocr.srt vào file plain đã dịch.

    Args:
        translated_plain_path: Đường dẫn file plain đã dịch.
        ocr_srt_path: Đường dẫn ocr.srt. Nếu None, tự tìm cùng folder.
        output_srt_path: Đường dẫn output. Nếu None, đặt tên tự động.

    Returns:
        MergeResult với thống kê số dòng ghép/bỏ qua.
    """
    # Xác định đường dẫn
    if ocr_srt_path is None:
        ocr_srt_path = _find_ocr_srt(translated_plain_path)
    if output_srt_path is None:
        output_srt_path = _default_output_path(translated_plain_path)

    # Parse
    srt_dict = parse_srt(ocr_srt_path)           # {index: SrtEntry}
    plain_entries = parse_plain_subtitle(translated_plain_path)  # list[PlainEntry]

    if not plain_entries:
        raise ValueError("File plain đã dịch trống hoặc không đúng định dạng.")

    # Ghép
    output_blocks: list[str] = []
    merged_count = 0
    skipped_count = 0
    skipped_indices: list[int] = []

    for i, plain in enumerate(plain_entries, 1):
        srt_entry = srt_dict.get(plain.index)

        if srt_entry is None:
            # Index trong plain không có trong OCR SRT → bỏ qua
            skipped_count += 1
            skipped_indices.append(plain.index)
            continue

        # Dùng text đã dịch, lấy timestamp từ OCR SRT
        block = _format_srt_block(
            index=merged_count + 1,   # đánh lại số thứ tự liên tiếp
            start=srt_entry.start,
            end=srt_entry.end,
            text=plain.text,
        )
        output_blocks.append(block)
        merged_count += 1

    if merged_count == 0:
        raise ValueError(
            "Không ghép được dòng nào. "
            "Hãy kiểm tra chỉ số trong file plain và ocr.srt có khớp nhau không."
        )

    # Ghi file
    Path(output_srt_path).write_text(
        "".join(output_blocks), encoding="utf-8"
    )

    return MergeResult(
        output_path=output_srt_path,
        merged_count=merged_count,
        skipped_count=skipped_count,
        skipped_indices=skipped_indices,
    )


# ─────────────────────────────────────────────────────────────
# Chuẩn hóa SRT trước khi dịch
# ─────────────────────────────────────────────────────────────

def _default_plain_path(srt_path: str) -> str:
    """Tạo tên file plain mặc định cạnh file SRT."""
    p = Path(srt_path)
    return str(p.parent / (p.stem + "_plain.txt"))


def srt_to_plain_subtitle(
    srt_path: str,
    output_path: str | None = None,
) -> PlainExportResult:
    """
    Chuẩn hóa SRT trước khi dịch:
    Đọc file .srt → xuất plain txt (chỉ index + text, không timestamp).

    Ví dụ output:
        1
        邦哥喝饮料

        2
        摔了个狗吃屎

    Mục đích: đưa file này vào AI dịch an toàn — AI không thể làm lộn
    thứ tự timestamp vì không có timestamp trong đầu vào.

    Args:
        srt_path: Đường dẫn file SRT gốc (thường là ocr.srt).
        output_path: Đường dẫn file plain output.
                     Nếu None, đặt tên tự động: <stem>_plain.txt cạnh file SRT.

    Returns:
        PlainExportResult với đường dẫn output và số entry đã xuất.
    """
    if output_path is None:
        output_path = _default_plain_path(srt_path)

    srt_dict = parse_srt(srt_path)  # {index: SrtEntry}

    if not srt_dict:
        raise ValueError("File SRT trống hoặc không đúng định dạng.")

    # Sắp xếp theo index để đảm bảo thứ tự đúng
    entries = sorted(srt_dict.values(), key=lambda e: e.index)

    with Path(output_path).open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(f"{entry.index}\n")
            f.write(f"{entry.text}\n\n")

    return PlainExportResult(
        output_path=output_path,
        entry_count=len(entries),
    )
