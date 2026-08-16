from __future__ import annotations

from pathlib import Path

import pysrt

from core.config import TEMP_DIR
from core.task_manager import Task
from services.capcut_service import (
    find_draft_folder,
    get_audio_duration_us,
    inject_audio_to_capcut,
)
from services.tts_service import (
    apply_speed_to_existing_audio,
    get_clone_by_id,
    get_vieneu_clone_by_id,
    list_voice_clones,
    list_vieneu_voice_clones,
    synthesize_line,
    synthesize_line_vieneu,
    unload_tts_model,
    unload_vieneu_model,
)


_ERROR_SAMPLE_LIMIT = 3
_FIT_HEADROOM_RATIO = 1.005
_MAX_ATEMPO_FACTOR_PER_LINE = 1.18


def _normalize_tts_text(text: str) -> str:
    """
    Normalize subtitle text before sending it to TTS.

    OmniVoice may behave poorly with embedded line breaks or irregular spacing,
    so we collapse all whitespace into single spaces.
    """
    return " ".join((text or "").split()).strip()


def _normalize_error_message(error: Exception | str) -> str:
    """Compact exception text so task status is readable in UI poll/SSE."""
    if isinstance(error, Exception):
        error_name = type(error).__name__
        error_text = str(error).strip()
        message = f"{error_name}: {error_text}" if error_text else error_name
    else:
        message = str(error).strip()

    compact = " ".join(message.split())
    if len(compact) > 240:
        return f"{compact[:237]}..."
    return compact or "Lỗi không xác định"


def _build_no_audio_failure_message(
    line_errors: list[tuple[int, str]],
    total_text_lines: int,
) -> str:
    if not line_errors:
        return "Không tạo được file audio nào từ SRT"

    sample_errors = "; ".join(
        f"dòng {line_no}: {reason}"
        for line_no, reason in line_errors[:_ERROR_SAMPLE_LIMIT]
    )
    hidden_count = max(0, len(line_errors) - _ERROR_SAMPLE_LIMIT)
    hidden_suffix = f" (+{hidden_count} lỗi khác)" if hidden_count else ""

    total = max(1, total_text_lines)
    return (
        f"Không tạo được file audio nào từ SRT ({len(line_errors)}/{total} dòng lỗi). "
        f"Lỗi mẫu: {sample_errors}{hidden_suffix}"
    )


def _srt_time_to_us(subrip_time) -> int:
    """Convert pysrt SubRipTime to microseconds used by CapCut."""
    return int(subrip_time.ordinal) * 1000


def _slot_duration_us(sub) -> int:
    start_us = _srt_time_to_us(sub.start)
    end_us = _srt_time_to_us(sub.end)
    return max(1, end_us - start_us)


def _compute_adaptive_speedup_factor(duration_us: int, slot_us: int) -> float:
    """Return speedup factor needed to fit duration inside subtitle slot."""
    if duration_us <= slot_us:
        return 1.0
    # Add tiny headroom to avoid edge cases caused by rounding.
    return (duration_us / slot_us) * _FIT_HEADROOM_RATIO


def _fit_audio_to_slot(audio_path: Path, slot_us: int, base_speech_rate: float) -> tuple[int, float, bool]:
    """
    Fit one generated line into subtitle slot by increasing speed only when needed.

    Returns:
        duration_us: final audio duration after fitting
        effective_rate: resulting absolute speech rate
        adjusted: True if an extra speedup was applied
    """
    duration_us = get_audio_duration_us(audio_path)
    if duration_us <= slot_us:
        return duration_us, base_speech_rate, False

    remaining_factor_budget = _MAX_ATEMPO_FACTOR_PER_LINE
    total_factor = 1.0
    adjusted = False
    duration_after = duration_us

    for _ in range(2):
        if duration_after <= slot_us or remaining_factor_budget <= 1.0 + 1e-6:
            break

        required_factor = _compute_adaptive_speedup_factor(duration_after, slot_us)
        step_factor = min(required_factor, remaining_factor_budget)
        if step_factor <= 1.0 + 1e-6:
            break

        apply_speed_to_existing_audio(audio_path, step_factor)
        adjusted = True
        total_factor *= step_factor
        remaining_factor_budget /= step_factor
        duration_after = get_audio_duration_us(audio_path)

    return duration_after, base_speech_rate * total_factor, adjusted


async def run_dubbing_pipeline(
    srt_path: str,
    voice_id: str,
    capcut_project_name: str,
    task: Task,
    speech_rate: float = 1.0,
    tts_engine: str = "omnivoice",
) -> None:
    """Pipeline: SRT -> TTS WAV clips -> CapCut draft injection.

    Args:
        tts_engine: 'omnivoice' (default) or 'vieneu' to select TTS engine.
    """
    srt_file = Path(srt_path)
    if not srt_file.exists():
        await task.fail(f"Không tìm thấy file SRT: {srt_path}")
        return

    await task.update(5, "Đang đọc file SRT...")
    subs = pysrt.open(str(srt_file), encoding="utf-8")
    total = len(subs)
    await task.update(10, f"Đọc được {total} dòng subtitle")

    if total == 0:
        await task.fail("File SRT không có dòng subtitle nào")
        return

    total_text_lines = sum(1 for sub in subs if sub.text and sub.text.strip())
    if total_text_lines == 0:
        await task.fail("File SRT không có nội dung text hợp lệ để tạo audio")
        return

    # Resolve voice clone based on engine
    if tts_engine == "vieneu":
        clone = get_vieneu_clone_by_id(voice_id)
        voices_fn = list_vieneu_voice_clones
        voice_dir_name = "voice_clones_vieneu"
    else:
        clone = get_clone_by_id(voice_id)
        voices_fn = list_voice_clones
        voice_dir_name = "voice_clones"

    if clone is None:
        voices = voices_fn()
        available_ids = ", ".join(v["id"] for v in voices[:5])
        voice_hint = available_ids if available_ids else f"không có voice clone nào trong thư mục {voice_dir_name}"
        await task.fail(
            f"Voice clone '{voice_id}' không tồn tại. Voice hiện có: {voice_hint}"
        )
        return

    if not str(clone.get("ref_text", "")).strip():
        await task.fail(
            (
                f"Voice clone '{voice_id}' chưa có transcript .txt hoặc nội dung transcript đang rỗng. "
                f"Hãy thêm file .txt cùng tên với file .wav trong thư mục {voice_dir_name}"
            )
        )
        return

    engine_label = "VieNeu-TTS v2" if tts_engine == "vieneu" else "OmniVoice"
    await task.update(11, f"Đang dùng voice clone: {clone['id']} (engine: {engine_label})")

    if task.is_cancelled():
        return

    await task.update(12, f"Đang tìm project CapCut: {capcut_project_name}...")
    draft_folder = find_draft_folder(capcut_project_name)
    if draft_folder is None:
        await task.fail(
            f"Không tìm thấy project CapCut '{capcut_project_name}' (hoặc tên bị mơ hồ). "
            "Hãy nhập đúng tên project trong CapCut và đảm bảo CapCut đã đóng project đó."
        )
        return

    await task.update(15, f"Tìm thấy draft: {draft_folder.name}")

    audio_entries: list[dict] = []
    tts_output_dir = TEMP_DIR / "tts_output" / task.task_id
    tts_output_dir.mkdir(parents=True, exist_ok=True)
    adjusted_lines = 0
    line_errors: list[tuple[int, str]] = []

    try:
        for i, sub in enumerate(subs, start=1):
            if task.is_cancelled():
                return

            original_text = sub.text.strip()
            text = _normalize_tts_text(original_text)
            if not text:
                continue

            progress = 15 + int((i / total) * 70)
            await task.update(progress, f"Đang tạo audio {i}/{total}: {text[:30]}...")
            print(
                f"[Dubbing] line={i} slot_us={_slot_duration_us(sub)} "
                f"text_len={len(text)} original_len={len(original_text)} "
                f"text={text!r}"
            )

            audio_filename = f"line_{i:03d}.wav"
            audio_path = tts_output_dir / audio_filename

            try:
                if tts_engine == "vieneu":
                    await synthesize_line_vieneu(
                        text=text,
                        voice_id=voice_id,
                        output_path=str(audio_path),
                        speech_rate=speech_rate,
                    )
                else:
                    await synthesize_line(
                        text=text,
                        voice_id=voice_id,
                        output_path=str(audio_path),
                        speech_rate=speech_rate,
                    )
            except Exception as exc:
                reason = _normalize_error_message(exc)
                line_errors.append((i, reason))
                await task.update(progress, f"Lỗi TTS dòng {i}: {reason}")
                continue

            if not audio_path.exists() or audio_path.stat().st_size <= 44:
                reason = "file audio không được tạo hoặc bị rỗng"
                line_errors.append((i, reason))
                await task.update(
                    progress,
                    f"Lỗi TTS dòng {i}: {reason}",
                )
                continue

            slot_us = _slot_duration_us(sub)
            generated_duration_us = get_audio_duration_us(audio_path)
            duration_us, effective_rate, adjusted = _fit_audio_to_slot(
                audio_path=audio_path,
                slot_us=slot_us,
                base_speech_rate=speech_rate,
            )
            print(
                f"[Dubbing] line={i} generated_us={generated_duration_us} "
                f"slot_us={slot_us} final_us={duration_us} "
                f"base_rate={speech_rate:.2f} effective_rate={effective_rate:.2f} "
                f"adjusted={adjusted}"
            )

            if adjusted:
                adjusted_lines += 1
                await task.update(
                    progress,
                    (
                        f"Dòng {i}: audio dài hơn SRT, auto tăng tốc "
                        f"{speech_rate:0.2f}x -> {effective_rate:0.2f}x"
                    ),
                )

            if duration_us > slot_us:
                over_ms = (duration_us - slot_us) / 1000.0
                warn_message = (
                    f"Dòng {i}: audio vẫn dài hơn slot {over_ms:.0f}ms "
                    f"sau khi fit ở {effective_rate:0.2f}x"
                )
                print(f"[Dubbing][Warn] {warn_message}")
                await task.update(progress, warn_message)

            start_us = _srt_time_to_us(sub.start)

            audio_entries.append(
                {
                    "audio_path": str(audio_path),
                    "audio_filename": audio_filename,
                    "text": text,
                    "start_time_us": start_us,
                    "duration_us": duration_us,
                    "slot_duration_us": slot_us,
                    "effective_speech_rate": effective_rate,
                }
            )

        if task.is_cancelled():
            return

        if not audio_entries:
            await task.fail(
                _build_no_audio_failure_message(
                    line_errors=line_errors,
                    total_text_lines=total_text_lines,
                )
            )
            return

        await task.update(
            88,
            f"Đang chèn {len(audio_entries)} audio vào CapCut project...",
        )

        backup_path = inject_audio_to_capcut(draft_folder, audio_entries)
        text_reading_dir = draft_folder / "textReading"
        copied_files = [
            text_reading_dir / entry["audio_filename"] for entry in audio_entries
        ]
        copied_ok = sum(
            1
            for p in copied_files
            if p.exists() and p.stat().st_size > 44
        )
        if copied_ok <= 0:
            await task.fail("Inject CapCut thất bại: không có file audio nào được copy vào textReading")
            return

        await task.update(95, f"Backup đã tạo: {backup_path}")

        await task.complete(
            result={
                "total_lines": len(audio_entries),
                "failed_lines": len(line_errors),
                "failed_samples": [
                    f"dòng {line_no}: {reason}"
                    for line_no, reason in line_errors[:_ERROR_SAMPLE_LIMIT]
                ],
                "auto_speedup_lines": adjusted_lines,
                "draft_folder": str(draft_folder),
                "backup_path": backup_path,
                "speech_rate": speech_rate,
                "message": (
                    f"Đã chèn {len(audio_entries)} audio vào CapCut project "
                    f"'{capcut_project_name}'"
                    f" ({len(line_errors)} dòng lỗi đã bỏ qua)"
                    if line_errors
                    else f"Đã chèn {len(audio_entries)} audio vào CapCut project '{capcut_project_name}'"
                ),
            }
        )
    finally:
        if tts_engine == "vieneu":
            unload_vieneu_model()
        else:
            unload_tts_model()
