# Plan: AI Video Localizer

## TL;DR
Xây dựng ứng dụng desktop bản địa hóa video tự động gồm WPF (.NET 10) frontend + Python FastAPI backend. App tách audio → STT → dịch → TTS → mix audio, hỗ trợ cả OCR hardsub. Chia 3 phase: MVP (STT + Dịch + UI), Phase 2 (OCR + TTS/Dubbing), Phase 3 (polish).

## Quyết định từ User
- **Deployment**: Python backend chạy tách riêng (manual)
- **Progress**: SSE (Server-Sent Events) stream progress realtime
- **TTS overflow**: Dùng FFmpeg atempo tăng tốc đọc cho vừa segment
- **Audio ducking**: Dynamic (chỉ giảm volume lúc TTS phát)
- **Cancel**: Bắt buộc có nút hủy tác vụ
- **TTS language**: Chỉ tiếng Việt (phase 1)
- **Project state**: Lưu file JSON
- **LLM Translation**: Dùng `gemma:8b` chạy local (qua Ollama) thay vì Gemini API key
- **Layout**: Left-Right (video trái, DataGrid phải)
- **MVVM**: Dùng CommunityToolkit.Mvvm (đơn giản nhất cho người có WPF cơ bản)
- **Video input**: File local + URL online (yt-dlp: Douyin, Bilibili, YouTube...)
- **UI Theme**: UI Library bên thứ 3 (đề xuất: WPF-UI hoặc HandyControl)
- **Framework**: .NET 10, Python 3.10+

## Architecture Overview
```
[WPF App (.NET 10)] ←── HTTP REST + SSE ──→ [FastAPI (Python)]
     │                                            │
     ├── LibVLCSharp (video)                      ├── demucs (vocal separation)
     ├── CommunityToolkit.Mvvm                    ├── whisperX (STT)
     ├── WPF-UI (theme)                           ├── PaddleOCR (hardsub)
     └── Project JSON                             ├── Ollama local (gemma:8b)
                                                  ├── edge-tts (TTS)
                                                  ├── ffmpeg-python (media)
                                                  ├── pysrt (subtitle)
                                                  └── yt-dlp (download)
```

---

## PHASE 1: MVP — OCR + Translation + UI cơ bản

### Step 1: Khởi tạo Solution & Project Structure
- Tạo solution `AI-Video_Localizer.sln`
- Project C#: `VideoLocalizer.App` (WPF, .NET 10)
- Project Python: `backend/` folder với FastAPI

**C# Project structure:**
```
src/
  VideoLocalizer.App/
    App.xaml
    Models/           — SubtitleEntry, ProjectFile, ApiResponse...
    ViewModels/       — MainViewModel, SettingsViewModel
    Views/            — MainWindow.xaml, SettingsWindow.xaml
    Services/         — ApiService, ProjectService, SubtitleService
    Converters/       — TimeSpanConverter, BoolToVisibilityConverter
```

**Python project structure:**
```
backend/
  main.py             — FastAPI app + Uvicorn entry
  api/
    v1/
      stt.py          — /api/v1/stt endpoint
      ocr.py          — /api/v1/ocr endpoint
      translate.py    — /api/v1/translate endpoint
      dubbing.py      — /api/v1/dubbing endpoint
      tasks.py        — /api/v1/tasks/{id}/status, cancel
      download.py     — /api/v1/download (yt-dlp)
  services/
    stt_service.py
    ocr_service.py
    translate_service.py
    dubbing_service.py
    download_service.py
  core/
    task_manager.py   — Task tracking, cancel support, SSE streaming
    config.py         — Settings, paths
  requirements.txt
```

### Step 2: Python Backend — Task Manager + SSE Infrastructure
- Tạo `TaskManager` class: quản lý task_id, status (pending/running/completed/failed/cancelled), progress %, log messages
- Implement SSE endpoint: `GET /api/v1/tasks/{task_id}/stream` — stream EventSource messages (progress, log, error, complete)
- Implement cancel endpoint: `POST /api/v1/tasks/{task_id}/cancel` — set cancellation flag, subprocess sẽ check flag
- Mỗi endpoint dài (STT, OCR, Translate, Dubbing) sẽ:
  1. Nhận request → tạo task_id → trả về task_id ngay (HTTP 202)
  2. Chạy xử lý trong background (asyncio / threading)
  3. Stream progress qua SSE

### Step 3: Python Backend — STT Pipeline (`/api/v1/stt`)
- Input: `{ "video_path": "...", "language": "auto" }`
- Pipeline:
  1. FFmpeg: Extract audio.wav từ video
  2. Demucs (htdemucs): Tách vocals.wav
  3. WhisperX: vocals.wav → SRT (condition_on_previous_text=False, word_timestamps=True)
  4. Lưu file `original.srt` cạnh video
- Return: task_id (SSE stream progress)
- **Cancel check**: Sau mỗi sub-step, check cancellation flag

### Step 4: Python Backend — Translation (`/api/v1/translate`)
- Input: `{ "srt_path": "...", "target_language": "vi", "style": "cổ trang", "glossary": { "大师姐": "Đại sư tỷ" } }`
- Pipeline:
  1. pysrt đọc SRT → trích xuất text array
  2. Chia batch nhỏ 15-20 dòng / lần dịch (Tối ưu để chạy trên RTX 3060 6GB tránh lỗi OOM / sinh ảo giác)
  3. Xây dựng System Prompt động dựa theo Style (Review phim, Phim cổ trang, Đời sống thường)
  4. Inject TỪ ĐIỂN BẮT BUỘC (Glossary) vào prompt
  5. Gọi Ollama API local (gemma:8b) để dịch
  6. Ráp text dịch vào pysrt object (giữ timestamp)
  7. Lưu `translated.srt`
- **Prompt design**: Bắt buộc tuân thủ format dịch 100%, thay đổi văn phong theo Style yêu cầu và chèn đúng từ khóa Glossary.

### Step 5: C# WPF — Main Window Layout
- Install NuGet: LibVLCSharp.WPF, CommunityToolkit.Mvvm, WPF-UI (hoặc HandyControl), System.Text.Json
- MainWindow layout:
  - Left panel (60%): LibVLCSharp VideoView + transport controls (Play/Pause, seekbar, volume)
  - Right panel (40%): 
    - Trên cùng: Radio buttons chọn Style dịch (Review phim, Phim cổ trang, Đời sống bình thường)
    - Nhỏ ở giữa: TextBox đa dòng (Multiline) nhập "Từ điển bắt buộc" theo cú pháp mỗi dòng 1 cặp, VD `大师姐 = Đại sư tỷ`.
    - Dưới: DataGrid (ID, Start, End, Text) + toolbar (Load SRT, Save, Export)
  - Bottom bar: Status bar + progress info
  - Top menu: File, Tools (STT, Translate, OCR, Dubbing), Settings

### Step 6: C# — ApiService + SSE Client
- `ApiService` class: HTTP client gọi Python backend
  - POST request → nhận task_id
  - Subscribe SSE `/api/v1/tasks/{task_id}/stream` → parse events → update ViewModel progress
  - Cancel: POST `/api/v1/tasks/{task_id}/cancel`
- Tất cả API calls dùng async/await
- Health check: `GET /api/v1/health` — kiểm tra Python backend đã sẵn sàng

### Step 7: C# — Video Player Integration
- LibVLCSharp: Load video, play/pause, seek
- Timer (DispatcherTimer, 100ms): Quét video position → highlight dòng sub tương ứng trên DataGrid
- Load SRT: Parse file SRT → List<SubtitleEntry> → bind DataGrid
- Đồng bộ: Click dòng sub → seek video đến timestamp đó

### Step 8: C# — Subtitle Editing
- DataGrid: Cho phép inline edit cột Text
- Khi edit xong → cập nhật SubtitleEntry → lưu lại file .srt
- LibVLCSharp: Reload subtitle track sau khi save

### Step 9: C# — Project Management
- ProjectFile model: { VideoPath, SrtFiles[], Settings, Glossary, LastPosition } (Từ điển bắt buộc lưu riêng theo từng project file)
- Save/Load project: JSON file (.avlproj)
- Recent projects list
- Auto-save khi thay đổi

### Step 10: C# — Settings Window
- Cấu hình Ollama URL (default: http://localhost:11434)
- Python backend URL (default: http://localhost:8000)
- Default target language & Translation Style mặc định
- edge-tts voice selection

---

## PHASE 2: STT + TTS/Dubbing

### Step 11: Python Backend — OCR Pipeline (`/api/v1/ocr`)
- Input: `{ "video_path": "...", "crop_region": [X, Y, W, H], "fps": 2 }`
- Pipeline:
  1. FFmpeg: Trích xuất frames (2 FPS)
  2. Crop frames theo tọa độ
  3. **Frame deduplication**: So sánh perceptual hash giữa frames liên tiếp, chỉ OCR khi text thay đổi (tiết kiệm 70%+ thời gian)
  4. PaddleOCR: Nhận diện text
  5. Tính timestamp từ frame number
  6. Merge các frame liên tiếp cùng text → 1 subtitle entry
  7. Lưu `ocr.srt`

### Step 12: C# — OCR Region Selection UI
- Hiển thị frame đầu tiên của video trong Image control
- Cho phép user vẽ rectangle (Mouse drag) → lấy tọa độ [X, Y, W, H]
- Preview: Hiển thị vùng crop để user xác nhận
- Gửi request OCR

### Step 13: Python Backend — TTS + Dubbing (`/api/v1/dubbing`)
- Input: `{ "video_path": "...", "srt_path": "...", "voice_id": "vi-VN-HoaiMyNeural", "original_volume": 0.2 }`
- Pipeline:
  1. Đọc SRT → duyệt từng entry
  2. edge-tts: Sinh audio cho mỗi line → line_N.mp3
  3. **TTS timing fix**: So sánh duration TTS vs segment duration
     - Nếu TTS dài hơn → FFmpeg atempo (tối đa 2.0x, vượt quá thì crop cuối)
     - Nếu TTS ngắn hơn → pad silence
  4. FFmpeg: Tạo TTS audio track (đặt mỗi clip đúng timestamp)
  5. **Dynamic ducking**: Giảm original volume xuống 20% CHỈ trong khoảng có TTS, giữ nguyên khoảng không có TTS
     - Dùng FFmpeg `volume` filter với timeline enable: `volume=0.2:enable='between(t,start,end)'`
  6. Mix 2 tracks → final audio
  7. Merge final audio + original video → `final_video.mp4`

### Step 14: C# — Dubbing UI
- Chọn file SRT đã dịch
- Dropdown: Chọn giọng đọc (edge-tts voices: vi-VN-HoaiMyNeural, vi-VN-NamMinhNeural)
- Slider: Âm lượng gốc (0-100%, default 20%)
- Button: "Xuất Video"
- Progress bar + log realtime qua SSE

---

## PHASE 3: Polish & URL Download

### Step 15: Python Backend — Video Download (`/api/v1/download`)
- Input: `{ "url": "https://...", "output_dir": "..." }`
- Dùng yt-dlp: Hỗ trợ YouTube, Bilibili, Douyin, TikTok, 1000+ sites
- Stream progress (download %)
- Return: downloaded video path

### Step 16: C# — Download UI
- TextField: Paste URL
- Button: Download
- Progress bar
- Sau khi download xong → tự động load video vào player

### Step 17: Error Handling & Polish
- Connection check: Cảnh báo khi Python backend chưa chạy
- Retry logic cho network errors
- Graceful error messages (không hiển thị stack trace cho user)
- Keyboard shortcuts (Space = play/pause, Ctrl+S = save SRT)
- Drag & drop video file vào app

---

## Relevant Files (sẽ tạo)

### C# (.NET 10 WPF)
- `src/VideoLocalizer.App/VideoLocalizer.App.csproj` — .NET 10, NuGet refs
- `src/VideoLocalizer.App/App.xaml` — Application entry, theme setup
- `src/VideoLocalizer.App/Views/MainWindow.xaml` — Main layout (video + datagrid)
- `src/VideoLocalizer.App/Views/SettingsWindow.xaml` — Settings UI
- `src/VideoLocalizer.App/ViewModels/MainViewModel.cs` — Main logic (CommunityToolkit.Mvvm)
- `src/VideoLocalizer.App/Models/SubtitleEntry.cs` — Subtitle data model
- `src/VideoLocalizer.App/Models/ProjectFile.cs` — Project serialization
- `src/VideoLocalizer.App/Services/ApiService.cs` — HTTP + SSE client to Python
- `src/VideoLocalizer.App/Services/SubtitleService.cs` — SRT parsing/saving
- `src/VideoLocalizer.App/Services/ProjectService.cs` — Project load/save

### Python (FastAPI)
- `backend/main.py` — FastAPI app, CORS, Uvicorn
- `backend/api/v1/stt.py` — STT endpoint
- `backend/api/v1/translate.py` — Translation endpoint
- `backend/api/v1/ocr.py` — OCR endpoint
- `backend/api/v1/dubbing.py` — Dubbing endpoint
- `backend/api/v1/tasks.py` — Task status + SSE + cancel
- `backend/api/v1/download.py` — yt-dlp download
- `backend/services/stt_service.py` — Demucs + WhisperX logic
- `backend/services/translate_service.py` — Ollama local LLM translation (với style & glossary injection)
- `backend/services/ocr_service.py` — PaddleOCR + frame dedup
- `backend/services/dubbing_service.py` — edge-tts + FFmpeg mix
- `backend/core/task_manager.py` — Task lifecycle + SSE
- `backend/requirements.txt` — All Python dependencies

---

## Verification

### Phase 1
1. Chạy `backend/main.py` → `GET /api/v1/health` trả 200
2. POST `/api/v1/stt` với video mẫu (30s) → nhận task_id → SSE stream progress → file `original.srt` được tạo
3. POST `/api/v1/translate` với SRT → file `translated.srt` đúng format, timestamp giữ nguyên
4. WPF app: Load video + SRT → video phát, sub hiển thị trên DataGrid, highlight đồng bộ
5. Edit text trên DataGrid → save → LibVLCSharp reload sub đúng
6. Save/Load project file hoạt động
7. Cancel task đang chạy → task dừng, không crash

### Phase 2
8. OCR: Vẽ rectangle → chạy OCR → nhận file SRT chính xác
9. Dubbing: Chạy TTS → audio TTS vừa khít segment (atempo hoạt động) → dynamic ducking đúng → final video xuất ra
10. Kiểm tra VRAM: Demucs → unload → WhisperX → unload (không OOM)

### Phase 3
11. Paste URL Bilibili/Douyin → download thành công → load video
12. App handle mượt khi Python backend chưa chạy (hiện cảnh báo, không crash)

---

## Decisions & Scope
- **In scope**: STT, OCR, Translation, TTS Dubbing, Video download, Project management
- **Out of scope**: Speaker diarization (phân biệt người nói), video editing, batch processing nhiều video
- **MVVM**: Dùng CommunityToolkit.Mvvm — đơn giản nhất, có source generators, phù hợp cho người có kinh nghiệm web API chuyển sang WPF
- **UI Library**: Đề xuất WPF-UI (Fluent Design, hỗ trợ .NET 8+) hoặc HandyControl
- **yt-dlp**: Hỗ trợ Douyin, Bilibili, YouTube — confirmed
- **LLM**: Local-first qua Ollama (gemma:8b) để tối ưu chi phí và tăng tính riêng tư.



# Plan: AI Video Localizer

## TL;DR
WPF (.NET 10) frontend + Python FastAPI backend. OCR hardsub → dịch → TTS → mix audio. Chia 3 phase: MVP (OCR + Dịch + UI), Phase 2 (STT + TTS/Dubbing), Phase 3 (polish + download).
**OCR là Phase 1** vì dễ test bằng mắt và chất lượng subtitle tốt hơn STT.

## User Decisions
- Deployment: Python backend chạy tách riêng (manual)
- Progress: SSE stream realtime
- TTS overflow: FFmpeg atempo
- Audio ducking: Dynamic
- Cancel: Bắt buộc
- TTS language: Chỉ tiếng Việt
- Project state: JSON file
- Local LLM: Dùng gemma:8b chạy local qua Ollama thay cho API Key
- Layout: Left-Right
- MVVM: CommunityToolkit.Mvvm
- Video input: File local + URL (yt-dlp)
- UI Theme: UI Library bên thứ 3
- Framework: .NET 10, Python 3.10+

## Architecture
```
[WPF (.NET 10)] ←── REST + SSE ──→ [FastAPI (Python)]
  ├── LibVLCSharp            ├── PaddleOCR (hardsub)
  ├── CommunityToolkit.Mvvm  ├── demucs + whisperX (STT)
  ├── WPF-UI (theme)         ├── Ollama (gemma:8b local)
  └── Project JSON           ├── edge-tts + FFmpeg (dubbing)
                             └── yt-dlp (download)
```

---

## PHASE 1: MVP — OCR + Translation + UI

### Step 1: Khởi tạo Solution & Project Structure
- Solution `AI-Video_Localizer.sln`
- C#: `src/VideoLocalizer.App/` (.NET 10 WPF)
- Python: `backend/`

C# structure:
```
src/VideoLocalizer.App/
  App.xaml
  Models/        — SubtitleEntry, ProjectFile, ApiResponse
  ViewModels/    — MainViewModel, SettingsViewModel
  Views/         — MainWindow.xaml, SettingsWindow.xaml
  Services/      — ApiService, ProjectService, SubtitleService
  Converters/    — TimeSpanConverter, BoolToVisibilityConverter
```

Python structure:
```
backend/
  main.py
  api/v1/        — stt.py, ocr.py, translate.py, dubbing.py, tasks.py, download.py
  services/      — stt_service.py, ocr_service.py, translate_service.py, dubbing_service.py, download_service.py
  core/          — task_manager.py, config.py
  requirements.txt
```

### Step 2: Python — Task Manager + SSE (parallel with Step 5)
- TaskManager: task_id, status, progress %, log messages
- SSE: `GET /api/v1/tasks/{id}/stream`
- Cancel: `POST /api/v1/tasks/{id}/cancel`
- Pattern: POST → 202 + task_id → background processing → SSE progress

### Step 3: Python — OCR Pipeline `/api/v1/ocr` (depends on 2)
- Input: `{ "video_path": "...", "crop_region": [X,Y,W,H], "fps": 2 }`
- Pipeline:
  1. FFmpeg trích frames (2 FPS)
  2. Crop theo tọa độ
  3. Frame dedup: perceptual hash → chỉ OCR khi text đổi (~70% thời gian saved)
  4. PaddleOCR nhận diện text
  5. Tính timestamp từ frame number
  6. Merge consecutive frames cùng text → 1 subtitle entry
  7. Lưu `ocr.srt`
- Cancel check sau mỗi batch frames

### Step 4: Python — Translation `/api/v1/translate` (depends on 2)
- Input: `{ "srt_path": "...", "target_language": "vi", "style": "cổ trang", "glossary": {...} }`
- Pipeline:
  1. pysrt đọc SRT → text array
  2. Chia batch 15-20 dòng để tránh nhồi quá nhiều Context vào gemma:8b (Tối ưu cho card 6GB VRAM)
  3. Build System Prompt động theo Style (Review/Cổ trang/Livestream) + chèn Glossary
  4. Gọi Ollama local API để sinh văn bản dịch
  5. Ráp text dịch vào pysrt (giữ timestamp)
  6. Lưu `translated.srt`

### Step 5: C# — Main Window Layout (parallel with 2-4)
- NuGet: LibVLCSharp.WPF, CommunityToolkit.Mvvm, WPF-UI, System.Text.Json
- Left 60%: VideoView + transport controls
- Right 40%: 
  - Radio chọn Style (Review phim, Phim cổ trang, Đời sống/Livestream)
  - TextBox đa dòng để nhập Từ khóa bắt buộc (cú pháp: `Từ gốc = Từ dịch`)
  - DataGrid (ID, Start, End, Text) biên dịch + toolbar
- Bottom: Status bar + progress
- Top menu: File, Tools (OCR, Translate, STT, Dubbing), Settings

### Step 6: C# — ApiService + SSE Client (depends on 2)
- HTTP client async → POST → task_id → subscribe SSE → update progress
- Cancel: POST `/api/v1/tasks/{id}/cancel`
- Health check: `GET /api/v1/health`

### Step 7: C# — OCR Region Selection UI (depends on 3, 6)
- Hiển thị frame đầu tiên trong Image control
- Mouse drag vẽ rectangle → [X,Y,W,H]
- Preview vùng crop → confirm → gọi `/api/v1/ocr`

### Step 8: C# — Video Player (depends on 5)
- LibVLCSharp: Play/Pause/Seek
- DispatcherTimer 100ms: highlight dòng sub tương ứng
- Click sub → seek video
- Load SRT → List<SubtitleEntry> → bind DataGrid

### Step 9: C# — Subtitle Editing (depends on 8)
- Inline edit Text trên DataGrid
- Save → .srt file → LibVLCSharp reload sub

### Step 10: C# — Project & Settings (depends on 5)
- ProjectFile: { VideoPath, SrtFiles[], Settings, Glossary, LastPosition }
- JSON file (.avlproj), recent projects, auto-save
- Settings: Gemini API key (DPAPI encrypted), backend URL, target language, voice

---

## PHASE 2: STT + TTS/Dubbing

### Step 11: Python — STT Pipeline `/api/v1/stt` (depends on 2)
- Input: `{ "video_path": "...", "language": "auto" }`
- Pipeline: FFmpeg extract audio → Demucs htdemucs tách vocals → WhisperX (condition_on_previous_text=False, word_timestamps=True) → `original.srt`
- Cancel check sau mỗi sub-step
- VRAM: Demucs unload → WhisperX unload

### Step 12: C# — STT UI (depends on 11)
- Nút "Tạo SRT từ Audio" → gọi `/api/v1/stt` → SSE progress → load SRT

### Step 13: Python — Dubbing `/api/v1/dubbing` (depends on 2)
- Input: `{ "video_path": "...", "srt_path": "...", "voice_id": "vi-VN-HoaiMyNeural", "original_volume": 0.2 }`
- Pipeline:
  1. edge-tts: sinh audio mỗi line → line_N.mp3
  2. Atempo fix: TTS dài hơn → speed up (max 2.0x, vượt thì crop)
  3. FFmpeg: tạo TTS track đặt clips đúng timestamp
  4. Dynamic ducking: `volume=0.2:enable='between(t,start,end)'`
  5. Mix 2 tracks → final_video.mp4

### Step 14: C# — Dubbing UI (depends on 13)
- Chọn SRT, giọng đọc, slider volume gốc, "Xuất Video"

---

## PHASE 3: Polish & Download

### Step 15: Python — Download `/api/v1/download`
- yt-dlp: YouTube, Bilibili, Douyin, TikTok, 1000+ sites
- Stream progress

### Step 16: C# — Download UI
- Paste URL → Download → auto load video

### Step 17: Error Handling & Polish
- Connection check, retry, graceful errors
- Keyboard shortcuts, drag & drop

---

## Relevant Files

**C#:** `src/VideoLocalizer.App/` — .csproj, App.xaml, Views/MainWindow.xaml, Views/SettingsWindow.xaml, ViewModels/MainViewModel.cs, Models/SubtitleEntry.cs, Models/ProjectFile.cs, Services/ApiService.cs, Services/SubtitleService.cs, Services/ProjectService.cs

**Python:** `backend/` — main.py, api/v1/{ocr,stt,translate,dubbing,tasks,download}.py, services/{ocr,stt,translate,dubbing,download}_service.py, core/task_manager.py, core/config.py, requirements.txt

---

## Verification

### Phase 1
1. `GET /api/v1/health` → 200
2. OCR: Vẽ rectangle trên video có hardsub → nhận `ocr.srt` chính xác, timestamp đúng
3. Translate: POST SRT → `translated.srt` giữ timestamp, text tiếng Việt
4. WPF: Video + SRT → phát, highlight đồng bộ DataGrid
5. Edit text → save → reload sub
6. Save/Load .avlproj
7. Cancel task → dừng, không crash

### Phase 2
8. STT video 30s → `original.srt` đúng
9. VRAM check: Demucs → unload → WhisperX → unload (no OOM)
10. Dubbing: atempo hoạt động, dynamic ducking đúng, final video OK

### Phase 3
11. Download Bilibili/Douyin → load video
12. Backend chưa chạy → cảnh báo, không crash

---

## Scope
- **In**: OCR, STT, Translation, TTS Dubbing, Download, Project management, Cancel
- **Out**: Speaker diarization, video editing, batch processing
