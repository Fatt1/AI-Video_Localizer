# Task 3: OmniVoice TTS + CapCut Integration

## Tổng quan

Thay **edge-tts** bằng **OmniVoice** (zero-shot voice cloning, 600+ ngôn ngữ). Thay vì mix audio trực tiếp vào video, **inject audio vào CapCut project** để user có thể chỉnh sửa audio bằng CapCut trước khi xuất video.

### Workflow

```
SRT (đã dịch) + Voice Clone
     ↓
OmniVoice: sinh audio cho từng dòng subtitle
     ↓
Lưu file .wav vào thư mục textReading/ trong CapCut draft
     ↓
Inject entries vào draft_content.json (backup trước)
     ↓
User mở CapCut → thấy audio đã nằm trên timeline → chỉnh sửa
```

---

## Architecture

### Thư mục Voice Clones

```
voice_clones/
  ├── narrator.wav          (file âm thanh mẫu 3-10 giây)
  ├── narrator.txt          (transcript chính xác)
  ├── female_host.wav
  ├── female_host.txt
  └── deep_male.wav
      deep_male.txt
```

### CapCut Draft Structure

```
C:\Users\{username}\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\
  └── {project_folder_name}/
      ├── draft_content.json            ← file chính, chứa timeline
      ├── draft_content.json.backup     ← backup tự động tạo trước khi modify
      └── textReading/                  ← thư mục chứa audio TTS
          ├── line_001.wav
          ├── line_002.wav
          └── ...
```

---

## CapCut JSON Format — Audio Entry

Mỗi audio TTS được thêm vào 2 nơi trong `draft_content.json`:

### 1. `materials.text_to_audio_materials[]` — Metadata audio

```json
{
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
    "duration": 3333333,
    "effect_id": "",
    "formula_id": "",
    "id": "{GENERATED_UUID}",
    "intensifies_path": "",
    "is_ai_clone_tone": false,
    "is_ai_clone_tone_post": false,
    "is_text_edit_overdub": false,
    "is_ugc": false,
    "local_material_id": "",
    "lyric_type": 0,
    "mock_tone_speaker": "",
    "moyin_emotion": "",
    "music_id": "",
    "music_source": "",
    "name": "{SRT_TEXT}",
    "path": "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##/textReading/{filename}.wav",
    "pgc_id": "",
    "pgc_name": "",
    "query": "",
    "request_id": "",
    "resource_id": "",
    "search_id": "",
    "similiar_music_info": {
        "original_song_id": "",
        "original_song_name": ""
    },
    "sound_separate_type": "",
    "source_from": "",
    "source_platform": 0,
    "team_id": "",
    "text_id": "{TEXT_UUID}",
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
        "benefit_type": "none"
    },
    "tts_generate_scene": "audio_panel",
    "tts_task_id": "",
    "type": "text_to_audio",
    "unique_id": "",
    "video_id": "",
    "wave_points": []
}
```

### 2. `tracks[]` — Timeline placement (audio track)

Mỗi audio entry cần 1 segment trong audio track:

```json
{
    "attribute": 0,
    "id": "{SEGMENT_UUID}",
    "material_id": "{MATERIAL_UUID}",
    "render_index": 0,
    "source_timerange": {
        "duration": 3333333,
        "start": 0
    },
    "target_timerange": {
        "duration": 3333333,
        "start": 5000000
    },
    "type": "audio",
    "visible": true,
    "volume": 1.0
}
```

> [!IMPORTANT]
> **Đơn vị thời gian CapCut**: microseconds (μs) — **KHÔNG** phải milliseconds.
> - 1 giây = 1,000,000 μs
> - SRT dùng ms → nhân ×1000 để chuyển sang CapCut μs
> - `duration` trong material = duration thực tế của file audio (μs)
> - `target_timerange.start` = vị trí trên timeline (SRT start_time × 1000)
> - `target_timerange.duration` = duration audio

---

## Proposed Changes

### Backend

---

#### [NEW] `backend/services/tts_service.py`

Service TTS bằng OmniVoice:

```python
# backend/services/tts_service.py
from omnivoice import OmniVoice
import torchaudio
from pathlib import Path
from core.config import VOICE_CLONES_DIR

_model = None

def get_tts_model():
    """Lazy-load OmniVoice (tốn VRAM, load 1 lần)"""
    global _model
    if _model is None:
        _model = OmniVoice()
    return _model

def unload_tts_model():
    """Giải phóng VRAM khi không dùng"""
    global _model
    if _model is not None:
        del _model
        _model = None
        import torch
        torch.cuda.empty_cache()

def list_voice_clones() -> list[dict]:
    """Liệt kê voice clones từ thư mục voice_clones/"""
    clones = []
    for wav_file in sorted(VOICE_CLONES_DIR.glob("*.wav")):
        txt_file = wav_file.with_suffix(".txt")
        ref_text = ""
        if txt_file.exists():
            ref_text = txt_file.read_text(encoding="utf-8").strip()
        clones.append({
            "id": wav_file.stem,
            "name": wav_file.stem.replace("_", " ").title(),
            "ref_audio": str(wav_file),
            "ref_text": ref_text,
            "has_transcript": txt_file.exists(),
        })
    return clones

def get_clone_by_id(voice_id: str) -> dict | None:
    """Tìm voice clone theo ID"""
    for clone in list_voice_clones():
        if clone["id"] == voice_id:
            return clone
    return None

async def synthesize_line(
    text: str,
    voice_id: str,
    output_path: str,
) -> str:
    """Sinh audio cho 1 dòng subtitle bằng OmniVoice"""
    model = get_tts_model()
    clone = get_clone_by_id(voice_id)
    if clone is None:
        raise ValueError(f"Voice clone '{voice_id}' không tồn tại")

    audio = model.generate(
        text=text,
        ref_audio=clone["ref_audio"],
        ref_text=clone["ref_text"],
    )

    torchaudio.save(output_path, audio, sample_rate=24000)
    return output_path
```

---

#### [NEW] `backend/services/capcut_service.py`

Service chèn audio vào CapCut draft — **đây là phần quan trọng nhất**:

```python
# backend/services/capcut_service.py
"""
Inject TTS audio files vào CapCut project draft_content.json.

Workflow:
1. Tìm thư mục draft CapCut theo project name
2. Backup draft_content.json → draft_content.json.backup
3. Đọc + parse JSON
4. Tạo thư mục textReading/ và copy audio files vào
5. Inject material entries vào materials.text_to_audio_materials[]
6. Tạo audio track mới (hoặc dùng track có sẵn) + add segments
7. Xử lý chồng audio: xóa các segment cũ trùng time range
8. Lưu JSON đã chỉnh sửa
"""
import json
import shutil
import uuid
import os
from pathlib import Path
from datetime import datetime

import torchaudio  # để đọc duration audio

# CapCut lưu draft ở đây (Windows)
DEFAULT_CAPCUT_DRAFTS_DIR = Path(os.environ.get(
    "CAPCUT_DRAFTS_DIR",
    Path.home() / "AppData" / "Local" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
))

# Placeholder path pattern mà CapCut dùng trong JSON
DRAFT_PATH_PLACEHOLDER = "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"


def find_draft_folder(project_name: str) -> Path | None:
    """
    Tìm thư mục draft CapCut theo tên project.
    CapCut đặt tên thư mục dạng: {timestamp}_{random}
    Bên trong có draft_meta_info.json chứa tên project.
    """
    drafts_dir = DEFAULT_CAPCUT_DRAFTS_DIR
    if not drafts_dir.exists():
        return None

    for folder in drafts_dir.iterdir():
        if not folder.is_dir():
            continue
        meta_file = folder / "draft_meta_info.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("draft_name", "") == project_name:
                    return folder
            except (json.JSONDecodeError, KeyError):
                continue

        # Fallback: so sánh tên thư mục
        if project_name.lower() in folder.name.lower():
            return folder

    return None


def backup_draft(draft_folder: Path) -> Path:
    """
    Tạo backup draft_content.json trước khi chỉnh sửa.
    Tên backup: draft_content.json.backup_{timestamp}
    """
    draft_json = draft_folder / "draft_content.json"
    if not draft_json.exists():
        raise FileNotFoundError(f"Không tìm thấy draft_content.json trong {draft_folder}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = draft_folder / f"draft_content.json.backup_{timestamp}"
    shutil.copy2(draft_json, backup_path)
    return backup_path


def _generate_uuid() -> str:
    """Sinh UUID uppercase có dấu gạch ngang (CapCut format)"""
    return str(uuid.uuid4()).upper()


def _get_audio_duration_us(audio_path: str) -> int:
    """Đọc duration file audio, trả về microseconds"""
    info = torchaudio.info(audio_path)
    duration_s = info.num_frames / info.sample_rate
    return int(duration_s * 1_000_000)  # → microseconds


def _build_material_entry(
    material_id: str,
    text_id: str,
    text: str,
    audio_filename: str,
    duration_us: int,
) -> dict:
    """Tạo 1 entry cho materials.text_to_audio_materials[]"""
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
        "name": text[:50],  # Tên hiển thị = nội dung subtitle (cắt ngắn)
        "path": f"{DRAFT_PATH_PLACEHOLDER}/textReading/{audio_filename}",
        "pgc_id": "",
        "pgc_name": "",
        "query": "",
        "request_id": "",
        "resource_id": "",
        "search_id": "",
        "similiar_music_info": {
            "original_song_id": "",
            "original_song_name": ""
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
            "benefit_type": "none"
        },
        "tts_generate_scene": "audio_panel",
        "tts_task_id": "",
        "type": "text_to_audio",
        "unique_id": "",
        "video_id": "",
        "wave_points": []
    }


def _build_track_segment(
    segment_id: str,
    material_id: str,
    duration_us: int,
    start_time_us: int,
) -> dict:
    """Tạo 1 segment cho audio track trên timeline"""
    return {
        "attribute": 0,
        "id": segment_id,
        "material_id": material_id,
        "render_index": 0,
        "source_timerange": {
            "duration": duration_us,
            "start": 0
        },
        "target_timerange": {
            "duration": duration_us,
            "start": start_time_us
        },
        "type": "audio",
        "visible": True,
        "volume": 1.0
    }


def _remove_overlapping_segments(
    existing_segments: list[dict],
    new_segments: list[dict],
) -> list[dict]:
    """
    Xóa các segment cũ trùng time range với segment mới.
    Giải quyết vấn đề chồng âm thanh khi inject nhiều lần.
    """
    new_ranges = []
    for seg in new_segments:
        tr = seg["target_timerange"]
        new_ranges.append((tr["start"], tr["start"] + tr["duration"]))

    cleaned = []
    for seg in existing_segments:
        tr = seg.get("target_timerange", {})
        seg_start = tr.get("start", 0)
        seg_end = seg_start + tr.get("duration", 0)

        # Kiểm tra có bị overlap với bất kỳ segment mới nào không
        overlaps = False
        for new_start, new_end in new_ranges:
            if seg_start < new_end and seg_end > new_start:
                overlaps = True
                break

        if not overlaps:
            cleaned.append(seg)

    return cleaned


def inject_audio_to_capcut(
    draft_folder: Path,
    audio_entries: list[dict],
) -> str:
    """
    Inject audio entries vào draft_content.json.

    Args:
        draft_folder: Path tới thư mục draft CapCut
        audio_entries: list of {
            "audio_path": str,        # path tới file .wav đã sinh
            "audio_filename": str,    # tên file (e.g. "line_001.wav")
            "text": str,              # nội dung subtitle
            "start_time_us": int,     # vị trí trên timeline (μs)
            "duration_us": int,       # duration audio (μs)
        }

    Returns:
        str: path tới backup file
    """
    draft_json_path = draft_folder / "draft_content.json"

    # 1. Backup
    backup_path = backup_draft(draft_folder)

    # 2. Đọc JSON
    draft = json.loads(draft_json_path.read_text(encoding="utf-8"))

    # 3. Tạo thư mục textReading/ và copy audio files
    text_reading_dir = draft_folder / "textReading"
    text_reading_dir.mkdir(exist_ok=True)

    for entry in audio_entries:
        src = Path(entry["audio_path"])
        dst = text_reading_dir / entry["audio_filename"]
        shutil.copy2(src, dst)

    # 4. Đảm bảo materials.text_to_audio_materials tồn tại
    materials = draft.setdefault("materials", {})
    tts_materials = materials.setdefault("text_to_audio_materials", [])

    # 5. Build material entries + track segments
    new_materials = []
    new_segments = []

    for entry in audio_entries:
        material_id = _generate_uuid()
        text_id = _generate_uuid()
        segment_id = _generate_uuid()

        mat = _build_material_entry(
            material_id=material_id,
            text_id=text_id,
            text=entry["text"],
            audio_filename=entry["audio_filename"],
            duration_us=entry["duration_us"],
        )
        new_materials.append(mat)

        seg = _build_track_segment(
            segment_id=segment_id,
            material_id=material_id,
            duration_us=entry["duration_us"],
            start_time_us=entry["start_time_us"],
        )
        new_segments.append(seg)

    # 6. Append materials
    tts_materials.extend(new_materials)

    # 7. Tìm hoặc tạo audio track cho TTS
    tracks = draft.setdefault("tracks", [])

    # Tìm track audio TTS đã có (dựa trên flag custom)
    tts_track = None
    for track in tracks:
        if track.get("type") == "audio" and track.get("flag", 0) == 0:
            # Kiểm tra nếu track này chứa segments type text_to_audio
            # CapCut thường dùng track riêng cho text reading
            tts_track = track
            break

    if tts_track is None:
        # Tạo track mới cho TTS audio
        tts_track = {
            "attribute": 0,
            "flag": 0,
            "id": _generate_uuid(),
            "is_default_name": True,
            "name": "",
            "segments": [],
            "type": "audio"
        }
        tracks.append(tts_track)

    # 8. Xóa segments cũ bị overlap → tránh chồng âm thanh
    existing_segments = tts_track.get("segments", [])
    cleaned_segments = _remove_overlapping_segments(existing_segments, new_segments)

    # 9. Thêm segments mới
    cleaned_segments.extend(new_segments)

    # Sắp xếp theo thời gian
    cleaned_segments.sort(key=lambda s: s["target_timerange"]["start"])
    tts_track["segments"] = cleaned_segments

    # 10. Lưu JSON
    draft_json_path.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return str(backup_path)
```

---

#### [NEW] `backend/services/dubbing_service.py`

Pipeline dubbing hoàn chỉnh — kết hợp TTS + CapCut injection:

```python
# backend/services/dubbing_service.py
"""
Pipeline dubbing:
1. Đọc SRT → danh sách subtitle entries
2. OmniVoice: sinh audio cho từng line → lưu vào temp/
3. Tìm CapCut draft folder theo project name
4. Copy audio files vào textReading/
5. Inject entries vào draft_content.json
"""
import pysrt
import os
from pathlib import Path
from core.task_manager import Task, TaskStatus
from core.config import TEMP_DIR
from services.tts_service import synthesize_line, unload_tts_model
from services.capcut_service import (
    find_draft_folder,
    inject_audio_to_capcut,
    _get_audio_duration_us,
)


async def run_dubbing_pipeline(
    srt_path: str,
    voice_id: str,
    capcut_project_name: str,
    task: Task,
):
    """Pipeline: SRT → TTS → CapCut injection"""

    # Step 1: Đọc SRT
    await task.update(5, "Đang đọc file SRT...")
    subs = pysrt.open(srt_path, encoding="utf-8")
    total = len(subs)
    await task.update(10, f"Đọc được {total} dòng subtitle")

    if task.is_cancelled():
        return

    # Step 2: Tìm CapCut draft folder
    await task.update(12, f"Đang tìm project CapCut: {capcut_project_name}...")
    draft_folder = find_draft_folder(capcut_project_name)
    if draft_folder is None:
        await task.fail(
            f"Không tìm thấy project CapCut '{capcut_project_name}'. "
            f"Kiểm tra tên project trong CapCut hoặc đường dẫn thư mục draft."
        )
        return
    await task.update(15, f"Tìm thấy draft: {draft_folder.name}")

    # Step 3: Sinh audio cho từng dòng subtitle
    audio_entries = []
    tts_output_dir = TEMP_DIR / "tts_output"
    tts_output_dir.mkdir(exist_ok=True)

    for i, sub in enumerate(subs):
        if task.is_cancelled():
            return

        text = sub.text.strip()
        if not text:
            continue

        progress = 15 + int((i / total) * 70)  # 15% → 85%
        await task.update(progress, f"Đang tạo audio {i+1}/{total}: {text[:30]}...")

        # Tên file audio: line_{index:03d}.wav
        audio_filename = f"line_{i+1:03d}.wav"
        audio_path = str(tts_output_dir / audio_filename)

        try:
            await synthesize_line(text, voice_id, audio_path)
        except Exception as e:
            await task.update(progress, f"⚠️ Lỗi TTS dòng {i+1}: {e}")
            continue

        # Tính duration audio thực tế
        duration_us = _get_audio_duration_us(audio_path)

        # SRT time → microseconds cho CapCut
        start_ms = (sub.start.hours * 3600 + sub.start.minutes * 60 +
                    sub.start.seconds) * 1000 + sub.start.milliseconds
        start_us = start_ms * 1000  # ms → μs

        audio_entries.append({
            "audio_path": audio_path,
            "audio_filename": audio_filename,
            "text": text,
            "start_time_us": start_us,
            "duration_us": duration_us,
        })

    if task.is_cancelled():
        return

    # Step 4: Inject vào CapCut
    await task.update(88, f"Đang chèn {len(audio_entries)} audio vào CapCut project...")
    try:
        backup_path = inject_audio_to_capcut(draft_folder, audio_entries)
        await task.update(95, f"Backup đã tạo: {backup_path}")
    except Exception as e:
        await task.fail(f"Lỗi khi chèn vào CapCut: {e}")
        return

    # Step 5: Unload TTS model
    unload_tts_model()

    await task.complete(result={
        "total_lines": len(audio_entries),
        "draft_folder": str(draft_folder),
        "backup_path": backup_path,
        "message": f"Đã chèn {len(audio_entries)} audio vào CapCut project '{capcut_project_name}'"
    })
```

---

#### [NEW] `backend/api/v1/tts.py`

```python
# backend/api/v1/tts.py
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from core.task_manager import task_manager, TaskStatus
from services.tts_service import list_voice_clones
from services.dubbing_service import run_dubbing_pipeline

router = APIRouter(tags=["TTS"])


@router.get("/tts/voices")
async def get_voices():
    """Liệt kê danh sách voice clones có sẵn"""
    return {"voices": list_voice_clones()}


class DubbingRequest(BaseModel):
    srt_path: str
    voice_id: str
    capcut_project_name: str  # Tên project CapCut để tìm draft folder


@router.post("/dubbing")
async def start_dubbing(req: DubbingRequest, bg: BackgroundTasks):
    """Chạy pipeline dubbing: TTS → inject CapCut"""
    task = task_manager.create_task("dubbing")

    async def _run():
        try:
            task.status = TaskStatus.RUNNING
            await run_dubbing_pipeline(
                srt_path=req.srt_path,
                voice_id=req.voice_id,
                capcut_project_name=req.capcut_project_name,
                task=task,
            )
        except Exception as e:
            await task.fail(str(e))

    bg.add_task(_run)
    return {"task_id": task.task_id}
```

---

#### [MODIFY] `backend/core/config.py`

```diff
+# Thư mục chứa voice clone files
+VOICE_CLONES_DIR = BASE_DIR / "voice_clones"
+VOICE_CLONES_DIR.mkdir(exist_ok=True)
```

#### [MODIFY] `backend/main.py`

```diff
+from api.v1 import tts
+app.include_router(tts.router, prefix="/api/v1")
```

#### [MODIFY] `backend/requirements.txt`

```diff
+omnivoice
+torch>=2.1.0
+torchaudio>=2.1.0
```

---

### Frontend (WPF)

---

#### [NEW] `src/VideoLocalizer.App/Models/VoiceClone.cs`

```csharp
namespace VideoLocalizer.Models;

public class VoiceClone
{
    public string Id { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string RefAudio { get; set; } = string.Empty;
    public string RefText { get; set; } = string.Empty;
    public bool HasTranscript { get; set; }
}
```

---

#### [MODIFY] `src/VideoLocalizer.App/Services/ApiService.cs`

Thêm methods:

```csharp
/// <summary>GET /api/v1/tts/voices — lấy danh sách voice clones</summary>
public async Task<List<VoiceClone>> GetVoiceClonesAsync()
{
    var resp = await _http.GetAsync("/api/v1/tts/voices");
    resp.EnsureSuccessStatusCode();
    var json = await resp.Content.ReadAsStringAsync();
    var result = JsonSerializer.Deserialize<VoicesResponse>(json, _jsonOpts);
    return result?.Voices ?? new();
}

/// <summary>POST /api/v1/dubbing — chạy TTS + inject CapCut</summary>
public async Task<TaskResponse?> StartDubbingAsync(
    string srtPath,
    string voiceId,
    string capcutProjectName)
{
    var body = new {
        srt_path = srtPath,
        voice_id = voiceId,
        capcut_project_name = capcutProjectName,
    };
    var resp = await _http.PostAsJsonAsync("/api/v1/dubbing", body);
    resp.EnsureSuccessStatusCode();
    return await resp.Content.ReadFromJsonAsync<TaskResponse>(_jsonOpts);
}
```

---

#### [MODIFY] `src/VideoLocalizer.App/ViewModels/MainViewModel.cs`

Thêm properties và commands:

```csharp
// ── Voice Clone / Dubbing ──

/// <summary>Danh sách voice clones từ backend</summary>
public ObservableCollection<VoiceClone> VoiceClones { get; } = new();

/// <summary>Voice đang chọn</summary>
[ObservableProperty]
private VoiceClone? _selectedVoice;

/// <summary>Tên project CapCut (để tìm draft folder)</summary>
[ObservableProperty]
private string _capcutProjectName = string.Empty;

/// <summary>Refresh voice list từ backend</summary>
[RelayCommand]
private async Task RefreshVoices()
{
    try
    {
        var voices = await Api.GetVoiceClonesAsync();
        VoiceClones.Clear();
        foreach (var v in voices)
            VoiceClones.Add(v);
        StatusMessage = $"Tìm thấy {voices.Count} voice clones";
    }
    catch (Exception ex)
    {
        StatusMessage = $"Lỗi load voices: {ex.Message}";
    }
}

/// <summary>Chạy dubbing: TTS → inject CapCut</summary>
[RelayCommand(CanExecute = nameof(CanRunTask))]
private async Task RunDubbing()
{
    if (string.IsNullOrEmpty(CurrentSrtPath))
    {
        StatusMessage = "Vui lòng load SRT trước.";
        return;
    }
    if (SelectedVoice == null)
    {
        StatusMessage = "Vui lòng chọn voice clone.";
        return;
    }
    if (string.IsNullOrEmpty(CapcutProjectName))
    {
        StatusMessage = "Vui lòng nhập tên project CapCut.";
        return;
    }

    var task = await Api.StartDubbingAsync(
        CurrentSrtPath, SelectedVoice.Id, CapcutProjectName);
    if (task == null)
    {
        StatusMessage = "Lỗi: Không thể bắt đầu dubbing.";
        return;
    }

    await StreamTaskProgress(task.TaskId, onComplete: _ =>
    {
        StatusMessage = $"✅ Đã chèn audio vào CapCut project '{CapcutProjectName}'";
    });
}
```

---

#### [MODIFY] `src/VideoLocalizer.App/Views/MainWindow.xaml`

Thêm vào panel phải — **Section Dubbing** (sau DataGrid hoặc trong GroupBox riêng):

```xml
<!-- ── Dubbing / TTS Section ── -->
<GroupBox Header="Dubbing (OmniVoice → CapCut)" Margin="6,4,6,6" Padding="6,4">
    <StackPanel>
        <!-- Voice Clone dropdown -->
        <DockPanel Margin="0,0,0,4">
            <TextBlock Text="Voice:" VerticalAlignment="Center"
                       Width="60" Margin="0,0,4,0"/>
            <ui:Button DockPanel.Dock="Right"
                       Icon="{ui:SymbolIcon ArrowSync24}"
                       Command="{Binding RefreshVoicesCommand}"
                       ToolTip="Refresh danh sách voice"
                       Margin="4,0,0,0"/>
            <ComboBox ItemsSource="{Binding VoiceClones}"
                      SelectedItem="{Binding SelectedVoice}"
                      DisplayMemberPath="Name"/>
        </DockPanel>

        <!-- CapCut Project Name -->
        <DockPanel Margin="0,0,0,4">
            <TextBlock Text="CapCut:" VerticalAlignment="Center"
                       Width="60" Margin="0,0,4,0"/>
            <TextBox Text="{Binding CapcutProjectName,
                         UpdateSourceTrigger=PropertyChanged}"
                     ToolTip="Tên project trong CapCut (để tìm thư mục draft)"/>
        </DockPanel>

        <!-- Nút chạy Dubbing -->
        <ui:Button Content="🎙 Tạo Audio → CapCut"
                   Command="{Binding RunDubbingCommand}"
                   Icon="{ui:SymbolIcon Mic24}"
                   HorizontalAlignment="Stretch"
                   Appearance="Primary"
                   ToolTip="OmniVoice TTS + inject vào CapCut project"/>
    </StackPanel>
</GroupBox>
```

Cập nhật menu Tools:

```diff
-<MenuItem Header="Dubbing (Phase 2)" IsEnabled="False"/>
+<MenuItem Header="Dubbing (OmniVoice → CapCut)..." Click="MenuDubbing_Click"/>
```

---

## Xử lý vấn đề chồng âm thanh
Khi inject audio vào CapCut, có thể xảy ra chồng audio nếu:
1. **Overlap tự nhiên**: Audio TTS dài hơn khoảng cách giữa 2 subtitle

### Giải pháp

1. **Atempo control**: Nếu audio TTS dài hơn khoảng thời gian subtitle:
   Option C (Khuyên dùng): Đẩy lùi Timeline (Ripple Shift trong JSON)
Cách hoạt động: Thay vì cắt bóp âm thanh, bạn dùng code C# thay đổi trực tiếp thuộc tính start của các Subtitle và Audio phía sau trong file draft_content.json. Nếu Audio 1 lố mất 1 giây, bạn cộng thêm 1 giây (1,000,000 micro-giây) vào thời điểm bắt đầu của Câu số 2.

Ưu điểm: Giữ 100% nội dung, giữ 100% chất giọng tự nhiên của AI. Đây là cách các phần mềm dựng phim chuyên nghiệp (Premiere, Resolve) xử lý.

3. **Backup bắt buộc**: Mỗi lần inject đều tạo backup với timestamp → user có thể rollback

---

## Lưu ý quan trọng

> [!WARNING]
> **Backup**: Mỗi lần inject sẽ tạo `draft_content.json.backup_{timestamp}`. File JSON gốc CỰC DÀI nên không nên load vào memory nhiều lần. Chỉ đọc 1 lần, modify, rồi ghi lại.

> [!IMPORTANT]
> **CapCut phải đóng**: Trước khi inject, CapCut PHẢI ĐÓNG project đó. Nếu CapCut đang mở project, các thay đổi trong JSON sẽ bị CapCut ghi đè khi save.

> [!NOTE]
> **Đơn vị thời gian**: CapCut dùng **microseconds** (1s = 1,000,000). SRT dùng milliseconds. Cần nhân ×1000 khi chuyển đổi.

---

## Verification Plan

1. **Voice Clones**: Đặt `.wav` + `.txt` vào `voice_clones/` → GET `/api/v1/tts/voices` trả về list
2. **TTS**: POST `/api/v1/dubbing` với SRT 5 dòng → sinh 5 file `.wav` trong temp
3. **CapCut Backup**: Kiểm tra file backup được tạo trước khi modify
4. **CapCut Inject**:
   - Mở CapCut → tạo project test
   - Chạy dubbing → kiểm tra CapCut mở lại project → thấy audio trên timeline
   - Audio phát đúng timestamp SRT
5. **Overlap**: Chạy dubbing 2 lần → kiểm tra không bị chồng audio
6. **VRAM**: Sau khi dubbing xong → `unload_tts_model()` → VRAM giải phóng