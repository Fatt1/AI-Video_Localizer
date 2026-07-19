# backend/services/stt_service.py
"""
Speech-to-Text service — hỗ trợ nhiều model:

  1. funasr-nano  : FunAudioLLM/Fun-ASR-Nano-2512 — 31 ngôn ngữ, token timestamps
  2. qwen3-asr   : Qwen/Qwen3-ASR-1.7B — 52 ngôn ngữ, LLM-based, sentence_info
  3. paraformer  : paraformer-zh + fsmn-vad + ct-punc — Tiếng Trung chuyên biệt,
                    trả về character timestamps dạng [[start_ms, end_ms], ...]

Mỗi model có cache riêng và hỗ trợ diarization (cam++) tuỳ chọn.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from core.config import FFMPEG_PATH, TEMP_DIR

logger = logging.getLogger(__name__)

# ─── Hằng số model key ────────────────────────────────────────────────────────
MODEL_FUNASR_NANO = "funasr-nano"
MODEL_QWEN3_ASR   = "qwen3-asr"
MODEL_PARAFORMER  = "paraformer"

# Danh sách model hiển thị cho UI
AVAILABLE_MODELS: dict[str, str] = {
    MODEL_FUNASR_NANO : "FunASR Nano 2512 (31 ngôn ngữ)",
    MODEL_QWEN3_ASR   : "Qwen3 ASR 1.7B (52 ngôn ngữ)",
    MODEL_PARAFORMER  : "Paraformer-ZH (Tiếng Trung)",
}

# ─── Model caches (mỗi model 1 slot) ─────────────────────────────────────────
_models: dict[str, object]     = {}   # model_key → AutoModel instance
_model_diar: dict[str, bool]   = {}   # model_key → has_diarization


def _set_hf_env():
    """Tắt symlink HuggingFace trên Windows để tránh WinError 1314."""
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"


def _free_vram():
    try:
        import gc, torch  # type: ignore
        gc.collect()
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
    except Exception as e:
        logger.warning("Lỗi giải phóng VRAM: %s", e)


# ─── Loader cho từng model ────────────────────────────────────────────────────

def _load_funasr_nano(use_diarization: bool):
    from funasr import AutoModel  # type: ignore
    logger.info("Loading FunASR Nano 2512 (diarization=%s)...", use_diarization)
    kwargs: dict = {
        "model"            : "FunAudioLLM/Fun-ASR-Nano-2512",
        "trust_remote_code": True,
        "remote_code"      : "./model.py",
        "vad_model"        : "fsmn-vad",
        "vad_kwargs"       : {"max_single_segment_time": 30000},
        "device"           : "cuda:0",
        "hub"              : "hf",
        "disable_update"   : True,
        "disable_pbar"     : True,
        "log_level"        : "ERROR",
    }
    if use_diarization:
        kwargs["spk_model"]   = "cam++"
        kwargs["spk_kwargs"]  = {"trust_remote_code": True}
        kwargs["punc_model"]  = "ct-punc"   # bắt buộc khi dùng cam++ để phân đoạn câu chính xác
    return AutoModel(**kwargs)


def _load_qwen3_asr(use_diarization: bool):
    from funasr import AutoModel  # type: ignore
    logger.info("Loading Qwen3 ASR 1.7B (diarization=%s)...", use_diarization)
    kwargs: dict = {
        "model"       : "Qwen/Qwen3-ASR-1.7B",
        "hub"         : "hf",
        "device"      : "cuda:0",
        "dtype"       : "bf16",
        "vad_model"   : "fsmn-vad",
        "vad_kwargs"  : {"max_single_segment_time": 30000},
        "disable_update": True,
        "disable_pbar": True,
        "log_level"   : "ERROR",
    }
    if use_diarization:
        kwargs["spk_model"]  = "cam++"
        kwargs["spk_kwargs"] = {"trust_remote_code": True}
        kwargs["punc_model"] = "ct-punc"   # bắt buộc khi dùng cam++ để phân đoạn câu chính xác
    return AutoModel(**kwargs)


def _load_paraformer(use_diarization: bool):
    from funasr import AutoModel  # type: ignore
    logger.info("Loading Paraformer-ZH (diarization=%s)...", use_diarization)
    # "paraformer-zh" là shorthand chỉ hoạt động với ModelScope (hub="ms")
    # Không dùng hub="hf" ở đây — để mặc định "ms"
    kwargs: dict = {
        "model"      : "paraformer-zh",
        "vad_model"  : "fsmn-vad",
        "vad_kwargs" : {"max_single_segment_time": 60000},
        "punc_model" : "ct-punc",
        "disable_update": True,
        "disable_pbar"  : True,
        "log_level"     : "ERROR",
    }
    if use_diarization:
        kwargs["spk_model"]  = "cam++"
        kwargs["spk_kwargs"] = {"trust_remote_code": True}
    return AutoModel(**kwargs)


_LOADERS = {
    MODEL_FUNASR_NANO: _load_funasr_nano,
    MODEL_QWEN3_ASR  : _load_qwen3_asr,
    MODEL_PARAFORMER : _load_paraformer,
}


def get_stt_model(model_key: str = MODEL_FUNASR_NANO, use_diarization: bool = False):
    """Lazy-load model theo key. Reload nếu thay đổi diarization."""
    global _models, _model_diar
    if model_key not in AVAILABLE_MODELS:
        raise ValueError(f"Model không hợp lệ: '{model_key}'. Chọn: {list(AVAILABLE_MODELS)}")

    if model_key in _models and _model_diar.get(model_key) != use_diarization:
        logger.info("Diarization state changed for %s. Reloading...", model_key)
        unload_stt_model(model_key)

    if model_key not in _models:
        _set_hf_env()
        _models[model_key]   = _LOADERS[model_key](use_diarization)
        _model_diar[model_key] = use_diarization
        logger.info("%s loaded OK.", model_key)

    return _models[model_key]


def unload_stt_model(model_key: str | None = None):
    """
    Giải phóng VRAM.
    - model_key=None → unload tất cả models đang loaded.
    - model_key=str  → chỉ unload model đó.
    """
    global _models, _model_diar
    keys = list(_models.keys()) if model_key is None else [model_key]
    for k in keys:
        if k in _models:
            del _models[k]
            _model_diar.pop(k, None)
            logger.info("Unloaded %s.", k)
    if keys:
        _free_vram()
    else:
        logger.debug("Không có model nào cần unload.")


# ─── Audio extraction ─────────────────────────────────────────────────────────

def extract_audio(video_path: str, output_wav: str) -> str:
    """FFmpeg: video → WAV mono 16kHz."""
    cmd = [
        FFMPEG_PATH, "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_wav,
    ]
    logger.info("Extracting audio: %s → %s", video_path, output_wav)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg trích xuất audio thất bại:\n{result.stderr[-500:]}")
    return output_wav


# ─── Timestamp → SRT helpers ─────────────────────────────────────────────────

def _ms_to_srt(ms: float) -> str:
    total = int(ms)
    h = total // 3_600_000
    m = (total % 3_600_000) // 60_000
    s = (total % 60_000) // 1000
    ms_ = total % 1000
    return f"{h:02}:{m:02}:{s:02},{ms_:03}"


def _sec_to_srt(sec: float) -> str:
    return _ms_to_srt(sec * 1000)


def _build_srt_from_tokens(
    timestamps: list[dict],
    silence_gap_s: float = 1.5,
) -> list[dict]:
    """
    FunASR Nano token timestamps → SRT entries.
    Ngắt entry khi khoảng nghỉ >= silence_gap_s giây (điều kiện chính).
    Đơn vị time: giây (float).
    """
    if not timestamps:
        return []

    entries, srt_idx = [], 1
    n, idx = len(timestamps), 0

    while idx < n:
        group: list[dict] = []
        group_start = timestamps[idx]["start_time"]

        while idx < n:
            tok = timestamps[idx]
            if group:
                gap = tok["start_time"] - group[-1]["end_time"]
                if gap >= silence_gap_s:
                    break
            group.append(tok)
            idx += 1

        if not group:
            idx += 1
            continue

        text = "".join(t.get("token", "") for t in group).strip()
        if text:
            entries.append({
                "index": srt_idx,
                "start": group_start,
                "end"  : group[-1]["end_time"],
                "text" : text,
            })
            srt_idx += 1

    return entries


def _build_srt_from_sentence_info(sentence_info: list[dict]) -> list[dict]:
    """
    sentence_info → SRT entries.
    Dùng cho FunASR Nano (diarization), Qwen3, Paraformer.
    Mỗi phần tử: {"text": ..., "start": ms, "end": ms, "spk": int (tuỳ chọn)}
    Đơn vị time: milliseconds (int).
    """
    entries, srt_idx = [], 1
    for sent in sentence_info:
        text = (sent.get("text") or sent.get("sentence") or "").strip()
        if not text:
            continue
        entries.append({
            "index"   : srt_idx,
            "start_ms": sent.get("start", 0),
            "end_ms"  : sent.get("end", 0),
            "text"    : text,
            "use_ms"  : True,
        })
        srt_idx += 1
    return entries


def _build_srt_from_paraformer_timestamps(
    text: str,
    timestamps: list[list[int]],
) -> list[dict]:
    """
    Paraformer trả về timestamps dạng [[start_ms, end_ms], ...] per character.
    Gom lại theo câu (dựa vào dấu câu cuối đoạn).
    """
    if not timestamps or not text:
        return []

    chars = list(text)
    ts    = timestamps
    # Đảm bảo đồng độ dài
    n = min(len(chars), len(ts))
    if n == 0:
        return []

    PUNCTS = set("。！？.!?\n")
    entries, srt_idx = [], 1
    buf_chars, buf_ts = [], []

    for i in range(n):
        buf_chars.append(chars[i])
        buf_ts.append(ts[i])
        is_end = chars[i] in PUNCTS or i == n - 1
        if is_end and buf_chars:
            seg_text = "".join(buf_chars).strip()
            if seg_text:
                entries.append({
                    "index"   : srt_idx,
                    "start_ms": buf_ts[0][0],
                    "end_ms"  : buf_ts[-1][1],
                    "text"    : seg_text,
                    "use_ms"  : True,
                })
                srt_idx += 1
            buf_chars, buf_ts = [], []

    return entries


def build_srt_content(entries: list[dict]) -> str:
    """List SRT entry dicts → chuỗi SRT hoàn chỉnh."""
    lines = []
    for e in entries:
        start_srt = _ms_to_srt(e["start_ms"]) if e.get("use_ms") else _sec_to_srt(e["start"])
        end_srt   = _ms_to_srt(e["end_ms"])   if e.get("use_ms") else _sec_to_srt(e["end"])
        lines.append(f"{e['index']}\n{start_srt} --> {end_srt}\n{e['text']}\n")
    return "\n".join(lines)


# ─── Main transcription ───────────────────────────────────────────────────────

def transcribe_audio(
    audio_path: str,
    model_key: str = MODEL_FUNASR_NANO,
    language: str = "zh",
    silence_gap_s: float = 1.5,
    hotwords: list[str] | None = None,
    use_diarization: bool = False,
) -> list[dict]:
    """
    Chạy STT model trên file WAV, trả về list SRT entry dicts.

    Args:
        audio_path      : Đường dẫn WAV (16kHz mono)
        model_key       : "funasr-nano" | "qwen3-asr" | "paraformer"
        language        : Mã ngôn ngữ (model-specific, ví dụ "zh", "Chinese", "auto")
        silence_gap_s   : (FunASR Nano) khoảng lặng giữa token → ngắt dòng
        hotwords        : (Paraformer) danh sách từ ưu tiên
        use_diarization : Bật nhận diện nhiều người nói (cam++)

    Returns:
        List of SRT entry dicts
    """
    model = get_stt_model(model_key=model_key, use_diarization=use_diarization)

    # ── Build generate kwargs theo từng model ─────────────────────────────────
    if model_key == MODEL_PARAFORMER:
        gen_kwargs: dict = {
            "input"       : audio_path,
            "batch_size_s": 300,
        }
        if hotwords:
            gen_kwargs["hotword"] = " ".join(hotwords)
    elif model_key == MODEL_QWEN3_ASR:
        gen_kwargs = {
            "input"     : audio_path,
            "cache"     : {},
            "batch_size": 1,
        }
        if language and language.lower() not in ("auto", ""):
            gen_kwargs["language"] = language
    else:  # funasr-nano
        gen_kwargs = {
            "input"     : [audio_path],
            "cache"     : {},
            "batch_size": 1,
            "language"  : language,
        }
        if hotwords:
            gen_kwargs["hotwords"] = hotwords

    logger.info(
        "STT | model=%s lang=%s diarization=%s audio=%s",
        model_key, language, use_diarization, audio_path,
    )

    res = model.generate(**gen_kwargs)

    if not res or not res[0]:
        raise RuntimeError(f"Model {model_key} không trả về kết quả.")

    result        = res[0]
    text: str     = result.get("text", "")
    timestamps    = result.get("timestamps", []) or result.get("timestamp", [])
    sentence_info = result.get("sentence_info", [])

    logger.info("STT done. text_len=%d, timestamps=%d, sentences=%d",
                len(text), len(timestamps), len(sentence_info))

    # ── Gắn nhãn người nói nếu diarization ───────────────────────────────────
    if use_diarization and sentence_info:
        for sent in sentence_info:
            spk = sent.get("spk", "?")
            raw = sent.get("text") or sent.get("sentence") or ""
            sent["text"] = f"[Người nói {spk}]: {raw}"

    # ── Chọn builder phù hợp ─────────────────────────────────────────────────
    if use_diarization and sentence_info:
        return _build_srt_from_sentence_info(sentence_info)

    if model_key == MODEL_PARAFORMER:
        # Paraformer + punc_model + vad_model → luôn có sentence_info
        # Ref: for sent in res[0]["sentence_info"]: sent['spk'], sent['start'], sent['end'], sent['text']
        if sentence_info:
            return _build_srt_from_sentence_info(sentence_info)
        # Fallback hiếm gặp: chỉ có character timestamps (khi không dùng punc+vad)
        if timestamps and isinstance(timestamps[0], (list, tuple)):
            return _build_srt_from_paraformer_timestamps(text, timestamps)
        return [{"index": 1, "start_ms": 0, "end_ms": 30000, "text": text, "use_ms": True}]

    if model_key == MODEL_QWEN3_ASR:
        # Qwen3: sentence_info có start/end ms sau khi dùng vad_model
        if sentence_info:
            return _build_srt_from_sentence_info(sentence_info)
        # Fallback nếu không có VAD segment
        return [{"index": 1, "start_ms": 0, "end_ms": 30000, "text": text, "use_ms": True}]

    # FunASR Nano (default)
    if timestamps and isinstance(timestamps[0], dict):
        return _build_srt_from_tokens(timestamps, silence_gap_s=silence_gap_s)
    elif sentence_info:
        return _build_srt_from_sentence_info(sentence_info)
    else:
        logger.warning("Không có timestamp, tạo 1 SRT entry duy nhất.")
        return [{"index": 1, "start": 0.0, "end": 30.0, "text": text}]


def run_stt_and_save_srt(
    video_path: str,
    output_srt_path: str = "",
    model_key: str = MODEL_FUNASR_NANO,
    language: str = "zh",
    silence_gap_s: float = 1.5,
    hotwords: list[str] | None = None,
    use_diarization: bool = False,
) -> str:
    """
    Pipeline hoàn chỉnh: video → extract audio → STT → save SRT.

    Returns:
        str: Đường dẫn file SRT đã lưu
    """
    video_path_obj = Path(video_path)

    if not output_srt_path:
        output_srt_path = str(video_path_obj.with_suffix("")) + "_stt.srt"

    wav_path = str(TEMP_DIR / f"stt_{video_path_obj.stem}.wav")

    extract_audio(video_path, wav_path)

    entries = transcribe_audio(
        audio_path=wav_path,
        model_key=model_key,
        language=language,
        silence_gap_s=silence_gap_s,
        hotwords=hotwords,
        use_diarization=use_diarization,
    )

    srt_content = build_srt_content(entries)
    Path(output_srt_path).write_text(srt_content, encoding="utf-8")
    logger.info("SRT saved → %s (%d entries)", output_srt_path, len(entries))

    return output_srt_path
