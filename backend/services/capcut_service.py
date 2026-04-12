from __future__ import annotations

import json
import os
import shutil
import uuid
import wave
from datetime import datetime
from pathlib import Path

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


def get_audio_duration_us(audio_path: str | Path) -> int:
    """Read WAV duration in microseconds without loading torch/torchaudio."""
    path = Path(audio_path)
    try:
        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            num_frames = wav_file.getnframes()
    except wave.Error as exc:
        raise ValueError(f"File WAV không hợp lệ: {audio_path}") from exc

    if sample_rate <= 0:
        raise ValueError(f"File audio không hợp lệ: {audio_path}")

    duration_s = num_frames / sample_rate
    return int(duration_s * 1_000_000)


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
