# backend/services/stt_service.py
"""
Speech-to-Text service sử dụng FunASR Fun-ASR-Nano-2512.

- Model hỗ trợ 31 ngôn ngữ, tích hợp dấu câu natively (không cần punc_model)
- Output: res[0]["text"] và res[0]["timestamps"] (token-level)
- timestamps format: [{"token": "开", "start_time": 0.42, "end_time": 0.48}, ...]
- Từ token-level timestamps → gom thành sentences → xuất SRT
"""
from __future__ import annotations

import logging
import os
import subprocess
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from core.config import FFMPEG_PATH, TEMP_DIR

logger = logging.getLogger(__name__)

# ─── Lazy-load model (tốn VRAM, chỉ khởi tạo 1 lần) ───────────────────────
_model = None

def get_stt_model():
    """Lazy-load Fun-ASR-Nano. Gọi lần đầu sẽ tải model (~HuggingFace)."""
    global _model
    if _model is None:
        from funasr import AutoModel  # type: ignore
        logger.info("Loading Fun-ASR-Nano-2512 model (lần đầu có thể mất vài phút)...")
        _model = AutoModel(
            model="FunAudioLLM/Fun-ASR-Nano-2512",
            trust_remote_code=True,
            remote_code="./model.py",
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device="cuda:0",
            hub="hf",
            disable_update=True,
            disable_pbar=True,
            log_level="ERROR",
        )
        logger.info("Fun-ASR-Nano-2512 model loaded OK.")
    return _model


def unload_stt_model():
    """Giải phóng VRAM khi không dùng nữa."""
    global _model
    if _model is not None:
        del _model
        _model = None
        try:
            import torch  # type: ignore
            torch.cuda.empty_cache()
        except Exception:
            pass
        logger.info("STT model unloaded.")


# ─── Audio extraction ────────────────────────────────────────────────────────

def extract_audio(video_path: str, output_wav: str) -> str:
    """
    Dùng FFmpeg để trích xuất audio từ video → WAV mono 16kHz.
    Fun-ASR-Nano yêu cầu 16kHz mono WAV để nhận dạng chính xác nhất.
    """
    cmd = [
        FFMPEG_PATH,
        "-y",                  # Overwrite output
        "-i", video_path,
        "-vn",                 # Bỏ video track
        "-acodec", "pcm_s16le",  # PCM 16-bit
        "-ar", "16000",        # 16kHz sample rate
        "-ac", "1",            # Mono
        output_wav,
    ]
    logger.info("Extracting audio: %s → %s", video_path, output_wav)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg trích xuất audio thất bại:\n{result.stderr[-500:]}"
        )
    return output_wav


# ─── Timestamp → SRT logic ────────────────────────────────────────────────────

def _ms_to_srt_time(ms: float) -> str:
    """Chuyển milliseconds → SRT timestamp (HH:MM:SS,mmm)."""
    total_ms = int(ms * 1000) if ms < 1000 else int(ms)  # handle both s and ms
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    seconds = (total_ms % 60_000) // 1000
    millis  = total_ms % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def _seconds_to_srt_time(seconds: float) -> str:
    """Chuyển seconds (float) → SRT timestamp."""
    total_ms = int(seconds * 1000)
    hours  = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    secs   = (total_ms % 60_000) // 1000
    millis = total_ms % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _build_srt_from_tokens(
    timestamps: list[dict],
    text: str,
    max_chars_per_line: int = 42,
) -> list[dict]:
    """
    Gom token-level timestamps → SRT entries.

    Fun-ASR-Nano trả về timestamps dạng token (ký tự/từ):
      [{"token": "开", "start_time": 0.42, "end_time": 0.48}, ...]
    Thời gian đơn vị là giây (seconds).

    Chiến lược gom tokens:
    1. Mỗi SRT entry không vượt quá max_chars_per_line ký tự
    2. Ưu tiên cắt tại dấu câu (。！？，、) nếu có trong khoảng ký tự cho phép
    3. Mỗi entry có start_time = token đầu, end_time = token cuối của nhóm
    """
    if not timestamps:
        return []

    entries = []
    idx = 0
    srt_idx = 1

    while idx < len(timestamps):
        group_tokens = []
        group_text = ""
        group_start = timestamps[idx]["start_time"]
        last_punct_pos = -1  # vị trí dấu câu gần nhất trong group

        while idx < len(timestamps):
            tok = timestamps[idx]
            token_str = tok.get("token", "")

            # Kiểm tra vượt quá giới hạn ký tự (không tính dấu câu đặc biệt)
            if group_text and len(group_text) + len(token_str) > max_chars_per_line:
                # Nếu có dấu câu trước đó → cắt tại đó
                if last_punct_pos >= 0:
                    # Giữ lại tokens từ last_punct_pos+1 trở đi
                    cut_at = last_punct_pos + 1
                    final_tokens = group_tokens[:cut_at]
                    # Trả lại tokens từ cut_at về idx để xử lý lần sau
                    idx -= len(group_tokens) - cut_at
                    group_tokens = final_tokens
                    group_text = "".join(t.get("token", "") for t in final_tokens)
                break

            group_tokens.append(tok)
            group_text += token_str

            # Ghi nhận vị trí dấu câu
            if token_str in "。！？，、.!?,;；":
                last_punct_pos = len(group_tokens) - 1

            idx += 1

        if not group_tokens:
            idx += 1
            continue

        group_end = group_tokens[-1]["end_time"]
        text_line = group_text.strip()
        if text_line:
            entries.append({
                "index": srt_idx,
                "start": group_start,
                "end": group_end,
                "text": text_line,
            })
            srt_idx += 1

    return entries


def _build_srt_from_sentence_info(
    sentence_info: list[dict],
    max_chars_per_line: int = 42,
) -> list[dict]:
    """
    Fallback: dùng sentence_info nếu timestamps không có.
    sentence_info: [{"text": "...", "start": 610, "end": 5530, "spk": 0}, ...]
    Thời gian đơn vị là milliseconds.
    """
    entries = []
    srt_idx = 1

    for sent in sentence_info:
        raw_text = sent.get("text") or sent.get("sentence") or ""
        raw_text = raw_text.strip()
        if not raw_text:
            continue

        start_ms = sent.get("start", 0)
        end_ms   = sent.get("end", 0)

        # Chia dòng dài thành nhiều dòng SRT
        if len(raw_text) <= max_chars_per_line:
            entries.append({
                "index": srt_idx,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": raw_text,
                "use_ms": True,
            })
            srt_idx += 1
        else:
            # Wrap dài → nhiều dòng con, chia đều timestamp
            chunks = _wrap_text(raw_text, max_chars_per_line)
            total_chars = len(raw_text)
            char_duration = (end_ms - start_ms) / max(total_chars, 1)
            current_start = start_ms
            char_pos = 0
            for chunk in chunks:
                chunk_end = current_start + int(len(chunk) * char_duration)
                entries.append({
                    "index": srt_idx,
                    "start_ms": current_start,
                    "end_ms": chunk_end,
                    "text": chunk,
                    "use_ms": True,
                })
                srt_idx += 1
                current_start = chunk_end
                char_pos += len(chunk)

    return entries


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """Cắt text theo max_chars, ưu tiên cắt tại dấu câu."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        # Tìm dấu câu trong khoảng max_chars
        cut = max_chars
        for punct in "。！？，、.!?,;；":
            pos = text.rfind(punct, 0, max_chars + 1)
            if pos > 0:
                cut = pos + 1
                break
        chunks.append(text[:cut])
        text = text[cut:].strip()
    return chunks


def build_srt_content(entries: list[dict]) -> str:
    """
    Từ list entries → chuỗi SRT hoàn chỉnh.
    Entry có thể dùng "start"/"end" (seconds) hoặc "start_ms"/"end_ms" (ms).
    """
    lines = []
    for entry in entries:
        idx = entry["index"]
        text = entry["text"]

        if entry.get("use_ms"):
            start_srt = _ms_to_srt_time(entry["start_ms"])
            end_srt   = _ms_to_srt_time(entry["end_ms"])
        else:
            start_srt = _seconds_to_srt_time(entry["start"])
            end_srt   = _seconds_to_srt_time(entry["end"])

        lines.append(f"{idx}\n{start_srt} --> {end_srt}\n{text}\n")

    return "\n".join(lines)


# ─── Main transcription function ─────────────────────────────────────────────

def transcribe_audio(
    audio_path: str,
    language: str = "中文",
    max_chars_per_line: int = 42,
    hotwords: list[str] | None = None,
) -> list[dict]:
    """
    Chạy Fun-ASR-Nano trên file WAV, trả về list SRT entries.

    Args:
        audio_path: Đường dẫn file WAV (16kHz mono)
        language: Ngôn ngữ nhận dạng, mặc định "中文"
        max_chars_per_line: Giới hạn ký tự mỗi dòng SRT (35–42 thông dụng)
        hotwords: Danh sách từ khóa ưu tiên nhận dạng

    Returns:
        List of SRT entry dicts với keys: index, start, end, text
    """
    model = get_stt_model()

    generate_kwargs = dict(
        input=[audio_path],
        cache={},
        batch_size=1,
        language=language,
    )
    if hotwords:
        generate_kwargs["hotwords"] = hotwords

    logger.info("Running STT on: %s (lang=%s, max_chars=%d)", audio_path, language, max_chars_per_line)
    res = model.generate(**generate_kwargs)

    if not res or not res[0]:
        raise RuntimeError("Fun-ASR-Nano không trả về kết quả nào.")

    result = res[0]
    text = result.get("text", "")
    timestamps: list[dict] = result.get("timestamps", [])
    sentence_info: list[dict] = result.get("sentence_info", [])

    logger.info("STT completed. Text length=%d, tokens=%d, sentences=%d",
                len(text), len(timestamps), len(sentence_info))

    # Ưu tiên dùng token timestamps → SRT entries chi tiết hơn
    if timestamps:
        entries = _build_srt_from_tokens(timestamps, text, max_chars_per_line)
    elif sentence_info:
        entries = _build_srt_from_sentence_info(sentence_info, max_chars_per_line)
    else:
        # Fallback: không có timestamp → 1 entry duy nhất
        logger.warning("Không có timestamp, tạo 1 SRT entry duy nhất.")
        entries = [{"index": 1, "start": 0.0, "end": 30.0, "text": text}]

    return entries


def run_stt_and_save_srt(
    video_path: str,
    output_srt_path: str = "",
    language: str = "中文",
    max_chars_per_line: int = 42,
    hotwords: list[str] | None = None,
) -> str:
    """
    Pipeline hoàn chỉnh: video → extract audio → STT → save SRT.

    Returns:
        str: Đường dẫn file SRT đã lưu
    """
    video_path_obj = Path(video_path)

    # Tạo đường dẫn output SRT nếu không chỉ định
    if not output_srt_path:
        output_srt_path = str(video_path_obj.with_suffix(".srt"))

    # Tạo file WAV tạm trong TEMP_DIR
    wav_path = str(TEMP_DIR / f"stt_{video_path_obj.stem}.wav")

    # Bước 1: Trích xuất audio
    extract_audio(video_path, wav_path)

    # Bước 2: Nhận dạng
    entries = transcribe_audio(
        audio_path=wav_path,
        language=language,
        max_chars_per_line=max_chars_per_line,
        hotwords=hotwords,
    )

    # Bước 3: Build và lưu SRT
    srt_content = build_srt_content(entries)
    Path(output_srt_path).write_text(srt_content, encoding="utf-8")
    logger.info("SRT saved → %s (%d entries)", output_srt_path, len(entries))

    return output_srt_path
