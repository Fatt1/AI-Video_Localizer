

##### [MODIFY] [requirements.txt](file:///e:/AI-Video_Localizer/backend/requirements.txt)

```diff
+omnivoice
+torch>=2.1.0
+torchaudio>=2.1.0
```

##### [MODIFY] [main.py](file:///e:/AI-Video_Localizer/backend/main.py)

```diff
+from api.v1 import tts
+app.include_router(tts.router, prefix="/api/v1")
```

---

#### Frontend (WPF)

##### [MODIFY] [ApiService.cs](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/Services/ApiService.cs)

Thêm methods:
- `GetVoiceClonesAsync()` — GET `/api/v1/tts/voices`
- `StartDubbingAsync(videoPath, srtPath, voiceId, originalVolume)` — POST `/api/v1/dubbing`

##### [MODIFY] [MainViewModel.cs](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/ViewModels/MainViewModel.cs)

Thêm properties:
- `ObservableCollection<VoiceClone> VoiceClones` — danh sách voice clone
- `VoiceClone SelectedVoice` — voice đang chọn
- `int OriginalVolume` — slider volume gốc (0-100%, default 20)
- `RelayCommand RunDubbingCommand` — chạy dubbing
- `RelayCommand RefreshVoicesCommand` — refresh danh sách voices

##### [MODIFY] [MainWindow.xaml](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/Views/MainWindow.xaml)

Thêm vào panel phải (hoặc trong menu Tools):
- **ComboBox** dropdown chọn voice clone (bind `VoiceClones`, `SelectedVoice`)
- **Slider** volume gốc (0-100%)
- **Button** "Xuất Video" (bind `RunDubbingCommand`)

##### [NEW] `src/VideoLocalizer.App/Models/VoiceClone.cs`

```csharp
public class VoiceClone
{
    public string Id { get; set; }
    public string Name { get; set; }
    public bool HasTranscript { get; set; }
}
```

---

## Task 4: Thay WhisperX bằng Qwen3-ASR + ForcedAligner

### Tổng quan

Chuyển STT pipeline từ **Demucs + WhisperX** sang **Qwen3-ASR-1.7B** (transcription) + **Qwen3-ForcedAligner-0.6B** (timestamp alignment).

### Lợi ích
- Hỗ trợ 52+ ngôn ngữ (bao gồm **tiếng Trung**, **tiếng Việt**, Nhật, Hàn...)
- Word/character-level timestamp chính xác hơn
- Model nhỹ (1.7B + 0.6B) phù hợp RTX 3060 6GB

### Pipeline mới

```
Video → FFmpeg extract audio.wav 
      → (optional) Demucs tách vocals 
      → Qwen3-ASR: audio → raw transcript
      → Qwen3-ForcedAligner: audio + transcript → word timestamps
      → Group words → subtitle segments (.srt)
```

> [!IMPORTANT]
> **Qwen3-ForcedAligner** hỗ trợ 11 ngôn ngữ cho timestamp. Cần verify Chinese và Vietnamese có trong list. Nếu không, fallback dùng Qwen3-ASR trực tiếp (auto-segment bằng silence detection).

### Proposed Changes

---

#### Backend

##### [NEW] `backend/services/stt_service.py`

```python
# backend/services/stt_service.py
import torch
from qwen_asr import Qwen3ASRModel, Qwen3ForcedAligner
from core.task_manager import Task, TaskStatus
from core.config import FFMPEG_PATH
import subprocess
import tempfile

_asr_model = None
_aligner_model = None

def get_asr_model():
    global _asr_model
    if _asr_model is None:
        _asr_model = Qwen3ASRModel.from_pretrained(
            "Qwen/Qwen3-ASR-1.7B",
            dtype=torch.bfloat16,
            device_map="cuda:0"
        )
    return _asr_model

def get_aligner_model():
    global _aligner_model
    if _aligner_model is None:
        _aligner_model = Qwen3ForcedAligner.from_pretrained(
            "Qwen/Qwen3-ForcedAligner-0.6B",
            dtype=torch.bfloat16,
            device_map="cuda:0"
        )
    return _aligner_model

def unload_models():
    """Giải phóng VRAM sau khi xử lý xong"""
    global _asr_model, _aligner_model
    del _asr_model, _aligner_model
    _asr_model = None
    _aligner_model = None
    torch.cuda.empty_cache()

async def run_stt_pipeline(
    video_path: str,
    language: str | None,  # None = auto-detect
    output_srt: str,
    task: Task,
    use_demucs: bool = True,
):
    """Pipeline: video → audio → ASR → alignment → SRT"""
    
    # Step 1: Extract audio
    await task.update(5, "Đang trích xuất audio từ video...")
    audio_path = extract_audio(video_path)
    
    # Step 2: (Optional) Demucs tách vocals
    if use_demucs:
        await task.update(15, "Đang tách vocal bằng Demucs...")
        audio_path = run_demucs(audio_path)
    
    # Step 3: ASR — speech to text
    await task.update(30, "Đang nhận diện giọng nói (Qwen3-ASR)...")
    asr_model = get_asr_model()
    result = asr_model.transcribe(
        audio=audio_path,
        language=language  # None = auto-detect
    )
    transcript = result  # raw text
    
    # Step 4: Forced alignment — lấy word timestamps
    await task.update(60, "Đang căn chỉnh timestamp (ForcedAligner)...")
    aligner = get_aligner_model()
    alignment = aligner.align(
        audio=audio_path,
        text=transcript,
        language=language or "Chinese"
    )
    
    # Step 5: Group words → subtitle segments
    await task.update(80, "Đang tạo file SRT...")
    entries = group_words_to_subtitles(alignment)
    write_srt(entries, output_srt)
    
    # Step 6: Unload models để giải phóng VRAM
    unload_models()
    
    await task.complete(result={
        "srt_path": output_srt, 
        "subtitle_count": len(entries)
    })
```

##### [NEW] `backend/api/v1/stt.py`

```python
# POST /api/v1/stt
# Input: { "video_path": "...", "language": "Chinese" | null }
# Return: { "task_id": "..." }
```

##### [MODIFY] [requirements.txt](file:///e:/AI-Video_Localizer/backend/requirements.txt)

```diff
+qwen-asr
+torch>=2.1.0
+torchaudio>=2.1.0
+demucs>=4.0.0
```

##### [MODIFY] [main.py](file:///e:/AI-Video_Localizer/backend/main.py)

```diff
+from api.v1 import stt
+app.include_router(stt.router, prefix="/api/v1")
```

---

#### Frontend (WPF)

##### [MODIFY] [ApiService.cs](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/Services/ApiService.cs)

Thêm method:
- `StartSttAsync(videoPath, language)` — POST `/api/v1/stt`

##### [MODIFY] [MainViewModel.cs](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/ViewModels/MainViewModel.cs)

Thêm:
- `string SelectedLanguage` — ngôn ngữ (null = auto-detect)
- `RelayCommand RunSttCommand` — chạy STT

##### [MODIFY] [MainWindow.xaml](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/Views/MainWindow.xaml)

Cập nhật menu Tools:
```diff
-<MenuItem Header="STT (Phase 2)" IsEnabled="False"/>
+<MenuItem Header="STT (Qwen3-ASR)..." Click="MenuStt_Click"/>
```

Thêm ComboBox chọn ngôn ngữ hoặc Dialog trước khi chạy STT.

---

## User Review Required

> [!IMPORTANT]
> **Task 3 (OmniVoice)**: OmniVoice yêu cầu GPU có VRAM đáng kể. Trên RTX 3060 6GB, chạy song song OmniVoice + Qwen3-ASR có thể gây OOM. Nên dùng model unloading giữa các task: unload ASR trước khi load TTS và ngược lại.

> [!IMPORTANT]
> **Task 4 (Qwen3-ForcedAligner)**: ForcedAligner chỉ hỗ trợ **11 ngôn ngữ** cho timestamp. Nếu Vietnamese/Chinese không nằm trong list, cần fallback strategy:
> - **Option A**: Dùng silence-based segmentation (pydub/webrtcvad) + ASR text
> - **Option B**: Dùng Qwen3-ASR trực tiếp nếu nó trả về timestamps trong output
> 
> Bạn muốn chọn option nào?

> [!WARNING]
> **Task 3 (Voice clone files)**: Mỗi voice clone cần có cả file `.wav` và `.txt` (transcript). User cần chuẩn bị files này thủ công. Có muốn tôi thêm chức năng **record trực tiếp** từ microphone trên UI không?

## Open Questions

1. **Task 3**: Bạn muốn đặt thư mục `voice_clones/` ở đâu? Đề xuất: `voice_clones/` trong root project hoặc trong thư mục cấu hình user.

2. **Task 4**: Khi chạy STT, bạn muốn auto-detect ngôn ngữ hay luôn chỉ định (ví dụ luôn Chinese)?

3. **Task 3 + 4**: Về VRAM management — bạn muốn:
   - (A) Tự động unload model không dùng trước khi load model mới
   - (B) Giữ tất cả models trong VRAM (cần GPU lớn hơn)

4. **Task 1**: LibVLC `TakeSnapshot` có thể mất ~50-100ms. Bạn OK với delay nhỏ này không?

---

## Verification Plan

### Task 3
- Đặt file `.wav` + `.txt` vào `voice_clones/`
- GET `/api/v1/tts/voices` → trả về danh sách voices
- POST dubbing → file video cuối cùng có giọng clone

### Task 4
- POST `/api/v1/stt` với video 30s tiếng Trung → nhận file SRT có timestamp chính xác
- Kiểm tra VRAM: ASR load → process → unload → VRAM giải phóng
