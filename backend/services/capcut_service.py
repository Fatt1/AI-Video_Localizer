from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
import wave
from datetime import datetime
from pathlib import Path

from core.config import FFMPEG_PATH

DEFAULT_CAPCUT_DRAFTS_DIR = Path(
    os.environ.get(
        "CAPCUT_DRAFTS_DIR",
        Path.home()
        / "AppData"
        / "Local"
        / "CapCut"
        / "User Data"
        / "Projects"
        / "com.lveditor.draft",
    )
)

DRAFT_PATH_PLACEHOLDER = "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"


def _norm_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def find_draft_folder(project_name: str) -> Path | None:
    """
    Find a CapCut draft folder with conservative matching.

    Priority:
    1) exact draft_name in draft_meta_info.json
    2) exact folder name
    3) unique partial draft_name match
    4) unique partial folder name match

    Returns None when ambiguous, to avoid injecting into a wrong project.
    """
    drafts_dir = DEFAULT_CAPCUT_DRAFTS_DIR
    if not drafts_dir.exists():
        return None

    target = _norm_name(project_name)
    if not target:
        return None

    exact_meta_matches: list[Path] = []
    exact_folder_matches: list[Path] = []
    partial_meta_matches: list[Path] = []
    partial_folder_matches: list[Path] = []

    for folder in drafts_dir.iterdir():
        if not folder.is_dir():
            continue

        meta_file = folder / "draft_meta_info.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                draft_name = _norm_name(str(meta.get("draft_name", "")))
                if draft_name == target:
                    exact_meta_matches.append(folder)
                elif target in draft_name:
                    partial_meta_matches.append(folder)
            except json.JSONDecodeError:
                pass

        folder_name = _norm_name(folder.name)
        if folder_name == target:
            exact_folder_matches.append(folder)
        elif target in folder_name:
            partial_folder_matches.append(folder)

    # Prefer exact matches from CapCut metadata.
    if len(exact_meta_matches) == 1:
        return exact_meta_matches[0]
    if len(exact_meta_matches) > 1:
        return max(exact_meta_matches, key=lambda p: p.stat().st_mtime)

    if len(exact_folder_matches) == 1:
        return exact_folder_matches[0]
    if len(exact_folder_matches) > 1:
        return max(exact_folder_matches, key=lambda p: p.stat().st_mtime)

    # Partial match is risky; only allow it when unique.
    if len(partial_meta_matches) == 1:
        return partial_meta_matches[0]
    if len(partial_folder_matches) == 1:
        return partial_folder_matches[0]

    return None


def backup_draft(draft_folder: Path) -> Path:
    """Create timestamped backup for draft_content.json before modifications."""
    draft_json = draft_folder / "draft_content.json"
    if not draft_json.exists():
        raise FileNotFoundError(f"Không tìm thấy draft_content.json trong {draft_folder}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = draft_folder / f"draft_content.json.backup_{ts}"
    shutil.copy2(draft_json, backup)
    return backup


def _get_duration_us_via_ffmpeg(path: Path) -> int:
    """Fallback duration reader via ffprobe/ffmpeg for non-PCM audio (e.g. MP3 saved as .wav by CapCut)."""
    ffprobe_exe = str(Path(FFMPEG_PATH).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe"))
    if not Path(ffprobe_exe).exists():
        ffprobe_exe = shutil.which("ffprobe") or ""

    if ffprobe_exe:
        proc = subprocess.run(
            [
                ffprobe_exe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                return int(float(proc.stdout.strip()) * 1_000_000)
            except ValueError:
                pass

    proc = subprocess.run([FFMPEG_PATH, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
    if m:
        hours, mins, secs = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return int((hours * 3600 + mins * 60 + secs) * 1_000_000)

    raise ValueError(f"Không đọc được thời lượng audio: {path}")


def get_audio_duration_us(audio_path: str | Path) -> int:
    """Read audio duration in microseconds (fast wave path + ffprobe/ffmpeg fallback for CapCut MP3-in-WAV)."""
    path = Path(audio_path)
    try:
        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            num_frames = wav_file.getnframes()
        if sample_rate > 0:
            return int((num_frames / sample_rate) * 1_000_000)
    except (wave.Error, EOFError):
        pass

    return _get_duration_us_via_ffmpeg(path)


def _generate_uuid() -> str:
    return str(uuid.uuid4()).upper()


def _build_material_entry(
    material_id: str,
    text_id: str,
    text: str,
    audio_filename: str,
    duration_us: int,
) -> dict:
    return {
        "ai_music_enter_from": "",
        "ai_music_generate_scene": 0,
        "ai_music_type": 0,
        "aigc_history_id": "",
        "aigc_item_id": "",
        "app_id": 0,
        "category_id": "",
        "category_name": "",
        "check_flag": 1,
        "cloned_model_type": "",
        "copyright_limit_type": "none",
        "duration": duration_us,
        "effect_id": "",
        "formula_id": "",
        "id": material_id,
        "intensifies_path": "",
        "is_ai_clone_tone": False,
        "is_ai_clone_tone_post": False,
        "is_text_edit_overdub": False,
        "is_ugc": False,
        "local_material_id": "",
        "lyric_type": 0,
        "mock_tone_speaker": "",
        "moyin_emotion": "",
        "music_id": "",
        "music_source": "",
        "name": text[:80],
        "path": f"{DRAFT_PATH_PLACEHOLDER}/textReading/{audio_filename}",
        "pgc_id": "",
        "pgc_name": "",
        "query": "",
        "request_id": "",
        "resource_id": "",
        "search_id": "",
        "similiar_music_info": {
            "original_song_id": "",
            "original_song_name": "",
        },
        "sound_separate_type": "",
        "source_from": "",
        "source_platform": 0,
        "team_id": "",
        "text_id": text_id,
        "third_resource_id": "",
        "tone_category_id": "",
        "tone_category_name": "",
        "tone_effect_id": "",
        "tone_effect_name": "OmniVoice Clone",
        "tone_emotion_name_key": "",
        "tone_emotion_role": "",
        "tone_emotion_scale": 0.0,
        "tone_emotion_selection": "",
        "tone_emotion_style": "",
        "tone_platform": "custom",
        "tone_second_category_id": "",
        "tone_second_category_name": "",
        "tone_speaker": "omnivoice_clone",
        "tone_type": "OmniVoice Clone",
        "tts_benefit_info": {
            "benefit_amount": -1,
            "benefit_log_extra": "",
            "benefit_log_id": "",
            "benefit_type": "none",
        },
        "tts_generate_scene": "audio_panel",
        "tts_task_id": "",
        "type": "text_to_audio",
        "unique_id": "",
        "video_id": "",
        "wave_points": [],
    }


def _build_track_segment(
    segment_id: str,
    material_id: str,
    duration_us: int,
    start_time_us: int,
) -> dict:
    # Keep a richer schema that matches CapCut 8.4 audio segments.
    return {
        "id": segment_id,
        "material_id": material_id,
        "raw_segment_id": segment_id,
        "render_index": 0,
        "track_render_index": 0,
        "track_attribute": 0,
        "group_id": "",
        "template_id": "",
        "template_scene": "",
        "desc": "",
        "clip": None,
        "speed": 1.0,
        "volume": 1.0,
        "last_nonzero_volume": 1.0,
        "is_loop": False,
        "reverse": False,
        "visible": True,
        "state": {},
        "source": "",
        "source_timerange": {
            "start": 0,
            "duration": duration_us,
        },
        "target_timerange": {
            "start": start_time_us,
            "duration": duration_us,
        },
        "render_timerange": {
            "start": start_time_us,
            "duration": duration_us,
        },
        "extra_material_refs": [],
        "common_keyframes": [],
        "keyframe_refs": [],
        "lyric_keyframes": [],
        "caption_info": None,
        "responsive_layout": None,
        "uniform_scale": None,
        "hdr_settings": None,
        "cartoon": False,
        "intensifies_audio": False,
        "is_tone_modify": False,
        "is_placeholder": False,
        "enable_adjust": False,
        "enable_adjust_mask": False,
        "enable_hsl": False,
        "enable_hsl_curves": False,
        "enable_lut": False,
        "enable_color_wheels": False,
        "enable_color_curves": False,
        "enable_color_adjust_pro": False,
        "enable_color_correct_adjust": False,
        "enable_color_match_adjust": False,
        "enable_smart_color_adjust": False,
        "enable_video_mask": False,
        "enable_mask_shadow": False,
        "enable_mask_stroke": False,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": None,
    }


def _remove_overlapping_segments(
    existing_segments: list[dict],
    new_segments: list[dict],
) -> tuple[list[dict], set[str]]:
    """Return cleaned existing segments and material_ids removed by overlap."""
    new_ranges: list[tuple[int, int]] = []
    for seg in new_segments:
        tr = seg["target_timerange"]
        start = int(tr.get("start", 0))
        end = start + int(tr.get("duration", 0))
        new_ranges.append((start, end))

    cleaned: list[dict] = []
    removed_material_ids: set[str] = set()

    for seg in existing_segments:
        tr = seg.get("target_timerange", {})
        seg_start = int(tr.get("start", 0))
        seg_end = seg_start + int(tr.get("duration", 0))

        overlap = False
        for new_start, new_end in new_ranges:
            if seg_start < new_end and seg_end > new_start:
                overlap = True
                break

        if overlap:
            mat_id = seg.get("material_id")
            if isinstance(mat_id, str) and mat_id:
                removed_material_ids.add(mat_id)
        else:
            cleaned.append(seg)

    return cleaned, removed_material_ids


def _find_or_create_tts_track(draft: dict) -> dict:
    tracks = draft.setdefault("tracks", [])
    for track in tracks:
        if track.get("type") == "audio" and isinstance(track.get("segments"), list):
            return track

    track = {
        "attribute": 0,
        "flag": 0,
        "id": _generate_uuid(),
        "is_default_name": True,
        "name": "",
        "segments": [],
        "type": "audio",
    }
    tracks.append(track)
    return track


def inject_audio_to_capcut(draft_folder: Path, audio_entries: list[dict]) -> str:
    """Inject generated TTS audio clips into draft_content.json and return backup path."""
    if not audio_entries:
        raise ValueError("Không có audio entries để inject vào CapCut")

    draft_json_path = draft_folder / "draft_content.json"
    if not draft_json_path.exists():
        raise FileNotFoundError(f"Không tìm thấy draft_content.json trong {draft_folder}")

    backup_path = backup_draft(draft_folder)
    draft = json.loads(draft_json_path.read_text(encoding="utf-8"))

    text_reading_dir = draft_folder / "textReading"
    text_reading_dir.mkdir(exist_ok=True)

    for entry in audio_entries:
        src = Path(entry["audio_path"])
        dst = text_reading_dir / entry["audio_filename"]
        if not src.exists() or src.stat().st_size <= 44:
            raise FileNotFoundError(f"Audio nguồn không tồn tại hoặc rỗng: {src}")
        shutil.copy2(src, dst)
        if not dst.exists() or dst.stat().st_size <= 44:
            raise RuntimeError(f"Copy audio vào textReading thất bại: {dst}")

    materials = draft.setdefault("materials", {})
    # CapCut 8.x uses materials.audios for timeline audio materials.
    tts_materials = materials.setdefault("audios", [])
    if not isinstance(tts_materials, list):
        raise ValueError("materials.audios không đúng định dạng list")

    # Backward compatibility: keep the legacy bucket in sync when it exists.
    legacy_tts_materials = materials.get("text_to_audio_materials")
    if legacy_tts_materials is not None and not isinstance(legacy_tts_materials, list):
        legacy_tts_materials = None

    new_materials: list[dict] = []
    new_segments: list[dict] = []

    for entry in audio_entries:
        material_id = _generate_uuid()
        text_id = _generate_uuid()
        segment_id = _generate_uuid()

        new_materials.append(
            _build_material_entry(
                material_id=material_id,
                text_id=text_id,
                text=entry["text"],
                audio_filename=entry["audio_filename"],
                duration_us=int(entry["duration_us"]),
            )
        )

        new_segments.append(
            _build_track_segment(
                segment_id=segment_id,
                material_id=material_id,
                duration_us=int(entry["duration_us"]),
                start_time_us=int(entry["start_time_us"]),
            )
        )

    tts_track = _find_or_create_tts_track(draft)
    existing_segments = tts_track.get("segments", [])
    if not isinstance(existing_segments, list):
        existing_segments = []

    cleaned_segments, removed_material_ids = _remove_overlapping_segments(
        existing_segments, new_segments
    )

    if removed_material_ids:
        tts_materials[:] = [
            m for m in tts_materials if m.get("id") not in removed_material_ids
        ]
        if legacy_tts_materials is not None:
            legacy_tts_materials[:] = [
                m for m in legacy_tts_materials if m.get("id") not in removed_material_ids
            ]

    tts_materials.extend(new_materials)
    if legacy_tts_materials is not None:
        legacy_tts_materials.extend(new_materials)
    cleaned_segments.extend(new_segments)
    cleaned_segments.sort(key=lambda s: int(s.get("target_timerange", {}).get("start", 0)))
    tts_track["segments"] = cleaned_segments

    draft_json_path.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return str(backup_path)


def resolve_capcut_media_path(draft_folder: Path, raw_path: str) -> Path:
    """Resolve CapCut ##_draftpath_placeholder_..._## path to an actual Path."""
    normalized = str(raw_path or "").replace(DRAFT_PATH_PLACEHOLDER, str(draft_folder))
    return Path(normalized)


def _apply_omnivoice_clean_to_material(mat: dict) -> None:
    """Reset Pro TTS metadata on a CapCut audio material to free OmniVoice Clone schema."""
    mat["type"] = "text_to_audio"
    mat["resource_id"] = ""
    mat["tone_speaker"] = "omnivoice_clone"
    mat["mock_tone_speaker"] = ""
    mat["tone_effect_name"] = "OmniVoice Clone"
    mat["tone_type"] = "OmniVoice Clone"
    mat["tone_platform"] = "custom"
    mat["check_flag"] = 1
    benefit = mat.get("tts_benefit_info")
    benefit_type = 0 if isinstance(benefit, dict) and isinstance(benefit.get("benefit_type"), int) else "none"
    mat["tts_benefit_info"] = {
        "benefit_amount": -1,
        "benefit_log_extra": "",
        "benefit_log_id": "",
        "benefit_type": benefit_type,
    }


def extract_capcut_tts_items(draft_folder: Path) -> list[dict]:
    """
    Read existing TTS audio materials and their matching subtitle slot durations
    from a CapCut draft folder.
    """
    draft_json_path = draft_folder / "draft_content.json"
    if not draft_json_path.exists():
        raise FileNotFoundError(f"Không tìm thấy draft_content.json trong {draft_folder}")

    draft = json.loads(draft_json_path.read_text(encoding="utf-8"))
    materials = draft.get("materials", {})
    audios = materials.get("audios", [])
    tracks = draft.get("tracks", [])

    # Map text material_id -> slot duration from text tracks
    text_slot_by_mat_id: dict[str, int] = {}
    text_segments_ranges: list[tuple[int, int, int]] = []
    audio_seg_by_mat_id: dict[str, dict] = {}

    for track in tracks:
        t_type = track.get("type")
        for seg in track.get("segments", []):
            mat_id = seg.get("material_id")
            tr = seg.get("target_timerange", {})
            start_us = int(tr.get("start", 0))
            dur_us = int(tr.get("duration", 0))
            if t_type == "text" and dur_us > 0:
                if mat_id:
                    text_slot_by_mat_id[mat_id] = dur_us
                text_segments_ranges.append((start_us, start_us + dur_us, dur_us))
            elif t_type == "audio" and mat_id:
                audio_seg_by_mat_id[mat_id] = seg

    items: list[dict] = []
    for mat in audios:
        mat_id = mat.get("id", "")
        raw_path = mat.get("path", "")
        if not raw_path:
            continue

        is_tts = (
            mat.get("type") == "text_to_audio"
            or "textReading" in raw_path
            or mat_id in audio_seg_by_mat_id
        )
        if not is_tts:
            continue

        audio_path = resolve_capcut_media_path(draft_folder, raw_path)
        seg = audio_seg_by_mat_id.get(mat_id, {})
        tr = seg.get("target_timerange", {})
        start_time_us = int(tr.get("start", 0))
        seg_dur_us = int(tr.get("duration", mat.get("duration", 0)))

        # Resolve subtitle slot duration: exact text_id match first, then overlap fallback
        text_id = mat.get("text_id", "")
        slot_duration_us = text_slot_by_mat_id.get(text_id)
        if slot_duration_us is None and text_segments_ranges and seg_dur_us > 0:
            seg_end = start_time_us + seg_dur_us
            best_overlap = 0
            best_dur = None
            for t_start, t_end, t_dur in text_segments_ranges:
                overlap = min(seg_end, t_end) - max(start_time_us, t_start)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_dur = t_dur
            slot_duration_us = best_dur

        items.append(
            {
                "material_id": mat_id,
                "segment_id": seg.get("id", ""),
                "text_id": text_id,
                "name": mat.get("name", audio_path.name),
                "raw_path": raw_path,
                "audio_path": audio_path,
                "start_time_us": start_time_us,
                "material_duration_us": int(mat.get("duration", 0)),
                "slot_duration_us": slot_duration_us,
            }
        )

    items.sort(key=lambda x: x["start_time_us"])
    return items


def _update_draft_json_durations(
    draft_path: Path,
    duration_updates: dict[str, int],
    clean_pro: bool,
) -> None:
    if not draft_path.exists():
        return

    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    materials = draft.get("materials", {})

    for mat in materials.get("audios", []):
        mat_id = mat.get("id")
        if mat_id in duration_updates:
            mat["duration"] = duration_updates[mat_id]
        if clean_pro and (mat.get("type") == "text_to_audio" or mat.get("tone_speaker") or mat_id in duration_updates):
            _apply_omnivoice_clean_to_material(mat)

    for track in draft.get("tracks", []):
        if track.get("type") != "audio":
            continue
        for seg in track.get("segments", []):
            mat_id = seg.get("material_id")
            if mat_id in duration_updates:
                new_dur = duration_updates[mat_id]
                seg["speed"] = 1.0
                if isinstance(seg.get("source_timerange"), dict):
                    seg["source_timerange"]["start"] = 0
                    seg["source_timerange"]["duration"] = new_dur
                if isinstance(seg.get("target_timerange"), dict):
                    seg["target_timerange"]["duration"] = new_dur
                if isinstance(seg.get("render_timerange"), dict):
                    seg["render_timerange"]["duration"] = new_dur

    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_mini_draft_durations(
    mini_draft_path: Path,
    duration_updates: dict[str, int],
    clean_pro: bool,
) -> None:
    if not mini_draft_path.exists():
        return

    try:
        data = json.loads(mini_draft_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    segments = data.get("mini_draft_data", {}).get("segments", [])
    if not isinstance(segments, list):
        return

    for seg in segments:
        mat = seg.get("material")
        if not isinstance(mat, dict):
            continue
        mat_id = mat.get("id")
        if mat_id in duration_updates:
            new_dur = duration_updates[mat_id]
            mat["duration"] = new_dur
            if isinstance(seg.get("source_time_range"), dict):
                seg["source_time_range"]["start"] = 0
                seg["source_time_range"]["duration"] = new_dur
            if isinstance(seg.get("target_time_range"), dict):
                seg["target_time_range"]["duration"] = new_dur
            if isinstance(seg.get("render_timerange"), dict):
                seg["render_timerange"]["duration"] = new_dur
            if isinstance(seg.get("speed"), dict):
                seg["speed"]["speed"] = 1.0
        if clean_pro and (mat.get("type") in ("text_to_audio", "extract_music") or mat.get("tone_speaker")):
            _apply_omnivoice_clean_to_material(mat)

    mini_draft_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _clean_key_value_and_temp_files(draft_folder: Path) -> None:
    kv_path = draft_folder / "key_value.json"
    if kv_path.exists():
        try:
            kv = json.loads(kv_path.read_text(encoding="utf-8"))
            keys_to_delete = [
                k for k, v in kv.items()
                if isinstance(v, dict)
                and v.get("materialCategory") == "tone"
                and (v.get("is_vip") in ("1", 1) or v.get("template_need_purcahse") is True)
            ]
            for k in keys_to_delete:
                del kv[k]
            for v in kv.values():
                if isinstance(v, dict):
                    if v.get("template_need_purcahse") is True:
                        v["template_need_purcahse"] = False
                    if v.get("is_vip") in ("1", 1):
                        v["is_vip"] = "0"
            kv_path.write_text(json.dumps(kv, ensure_ascii=False, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass

    for pattern in ("*.tmp", "*.bak"):
        for tmp_file in draft_folder.rglob(pattern):
            try:
                tmp_file.unlink()
            except OSError:
                pass


def update_capcut_audio_durations(
    draft_folder: Path,
    duration_updates: dict[str, int],
    clean_pro: bool = True,
) -> str:
    """
    Update audio durations (and optionally clean Pro flags) across root draft_content.json,
    Timelines/*/draft_content.json, and mini_draft.json. Returns backup path.
    """
    if not duration_updates:
        raise ValueError("Không có audio nào được cập nhật thời lượng")

    backup_path = backup_draft(draft_folder)

    _update_draft_json_durations(draft_folder / "draft_content.json", duration_updates, clean_pro)

    timelines_dir = draft_folder / "Timelines"
    if timelines_dir.exists():
        for tl_draft in timelines_dir.rglob("draft_content.json"):
            _update_draft_json_durations(tl_draft, duration_updates, clean_pro)
        for mini_draft in timelines_dir.rglob("mini_draft.json"):
            _update_mini_draft_durations(mini_draft, duration_updates, clean_pro)

    if clean_pro:
        _clean_key_value_and_temp_files(draft_folder)

    return str(backup_path)
