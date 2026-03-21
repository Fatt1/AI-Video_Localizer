# backend/services/translate_service.py
import pysrt
import httpx
from core.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from core.task_manager import Task

STYLE_PROMPTS = {
    "review": "Dịch theo phong cách bình luận phim tự nhiên, sinh động. Giữ nguyên các từ chuyên ngành điện ảnh.",
    "ancient_drama": "Dịch theo phong cách phim cổ trang, dùng ngôn từ trang trọng, cổ điển. Các chức danh và tên gọi phải được dịch theo đúng văn phong cổ trang Việt Nam.",
    "lifestyle": "Dịch tự nhiên, gần gũi như đời sống hàng ngày. Có thể dùng tiếng lóng phổ biến nếu phù hợp."
}


CONTEXT_WINDOW = 3  # Số câu cuối batch trước đưa vào làm ngữ cảnh


def build_prompt(
    texts: list[str],
    style: str,
    glossary: dict,
    prev_src: list[str] | None = None,
    prev_tgt: list[str] | None = None,
) -> str:
    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["lifestyle"])

    glossary_text = ""
    if glossary:
        glossary_lines = "\n".join([f"  {k} = {v}" for k, v in glossary.items()])
        glossary_text = f"""
TỪ ĐIỂN BẮT BUỘC (PHẢI dùng đúng các từ này, không được thay thế):
{glossary_lines}
"""

    # --- Sliding Window: đưa vài câu cuối batch trước làm ngữ cảnh ---
    context_block = ""
    if prev_src and prev_tgt:
        pairs = "\n".join(
            [f"  [{s}] → [{t}]" for s, t in zip(prev_src, prev_tgt)]
        )
        context_block = f"""
NGỮ CẢNH TRƯỚC ĐÓ (chỉ tham khảo, KHÔNG dịch lại):
{pairs}
"""

    numbered_texts = "\n".join([f"{i+1}. {t}" for i, t in enumerate(texts)])

    return f"""Bạn là dịch thuật chuyên nghiệp Trung-Việt.
{style_instruction}
{glossary_text}{context_block}
QUY TẮC BẮT BUỘC:
- Cấm dịch word-by-word thô cứng.
- Dịch 100% sang Tiếng Việt. TUYỆT ĐỐI KHÔNG để sót bất kỳ chữ Hán nào. Nếu gặp thành ngữ hoặc từ lóng khó, bắt buộc phải DỊCH THOÁT NGHĨA cho thuần Việt.
- Chỉ trả về các dòng đã dịch, KHÔNG thêm giải thích.
- Giữ đúng số thứ tự (1., 2., 3., ...)
- Số lượng dòng đầu ra PHẢI BẰNG đầu vào.
- Nếu dòng rỗng, trả về dòng rỗng.

INPUT:
{numbered_texts}

OUTPUT (chỉ các dòng đã dịch):"""


async def translate_batch(
    texts: list[str],
    style: str,
    glossary: dict,
    prev_src: list[str] | None = None,
    prev_tgt: list[str] | None = None,
    ollama_context: list[int] | None = None,
) -> tuple[list[str], list[int] | None]:
    """
    Dịch một batch, trả về (bản_dịch, ollama_context).
    - prev_src / prev_tgt : CONTEXT_WINDOW câu cuối batch trước (sliding window).
    - ollama_context      : context token Ollama trả về từ batch trước (KV-cache).
    """
    prompt = build_prompt(texts, style, glossary, prev_src, prev_tgt)

    body: dict = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if ollama_context:
        body["context"] = ollama_context  # giữ KV-cache từ batch trước

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=body,
        )
        response.raise_for_status()
        result = response.json()
        output = result.get("response", "").strip()
        new_context: list[int] | None = result.get("context")  # lưu lại KV-cache

    # Parse output — loại bỏ số thứ tự nếu có
    lines = output.split("\n")
    translated = []
    for line in lines:
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            line = line.split(". ", 1)[1]
        translated.append(line)

    # Đảm bảo số dòng khớp với đầu vào
    while len(translated) < len(texts):
        translated.append("")

    return translated[:len(texts)], new_context


async def run_translate_pipeline(
    srt_path: str,
    target_language: str,
    style: str,
    glossary: dict,
    output_srt: str,
    task: Task,
    batch_size: int = 15
):
    """Pipeline dịch: SRT gốc → batch dịch Ollama → SRT dịch mới"""
    # Đọc SRT gốc
    await task.update(5, "Đang đọc file SRT...")
    subs = pysrt.open(srt_path, encoding="utf-8")
    total = len(subs)
    await task.update(10, f"Đã đọc {total} subtitle entries")

    if task.is_cancelled():
        return

    # Dịch theo batch (giữ ngữ cảnh liên tục giữa các batch)
    translated_texts: list[str] = []
    all_source_texts: list[str] = [subs[i].text for i in range(total)]
    num_batches = (total + batch_size - 1) // batch_size

    ollama_context: list[int] | None = None  # KV-cache Ollama
    prev_src: list[str] | None = None        # sliding window — câu gốc
    prev_tgt: list[str] | None = None        # sliding window — bản dịch

    for batch_idx in range(num_batches):
        if task.is_cancelled():
            return

        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch_texts = all_source_texts[start:end]

        progress = 10 + int((batch_idx / num_batches) * 80)
        await task.update(progress, f"Đang dịch batch {batch_idx+1}/{num_batches}...")

        batch_translated, ollama_context = await translate_batch(
            batch_texts,
            style,
            glossary,
            prev_src=prev_src,
            prev_tgt=prev_tgt,
            ollama_context=ollama_context,
        )
        translated_texts.extend(batch_translated)

        # Cập nhật sliding window: lấy CONTEXT_WINDOW câu cuối batch này
        prev_src = batch_texts[-CONTEXT_WINDOW:]
        prev_tgt = batch_translated[-CONTEXT_WINDOW:]

    # Gán text đã dịch vào pysrt object (giữ nguyên timestamp)
    await task.update(90, "Đang tạo file SRT đã dịch...")
    for i, sub in enumerate(subs):
        if i < len(translated_texts):
            sub.text = translated_texts[i]

    # Lưu bản dịch (file gốc srt_path KHÔNG bị chỉnh sửa)
    subs.save(output_srt, encoding="utf-8")
    await task.complete(result={"srt_path": output_srt, "total_lines": total})
