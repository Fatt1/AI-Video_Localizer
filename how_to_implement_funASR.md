Dưới đây là toàn bộ nội dung tài liệu hướng dẫn sử dụng **FunASR** được chuyển đổi và tổ chức lại thành một file Markdown (`.md`) chuẩn chỉnh, rõ ràng, dễ đọc và tối ưu nhất cho bạn.

---

```markdown
# Hướng dẫn sử dụng FunASR (Full Documentation)

Chỉ với một đối tượng Model duy nhất, bạn có thể xử lý toàn bộ quy trình: tải âm thanh, phân đoạn VAD (Voice Activity Detection), nhận dạng giọng nói (ASR) và thêm dấu câu.

```bash
pip install funasr

python -c "
from funasr import AutoModel
model = AutoModel(model='paraformer-zh', vad_model='fsmn-vad', punc_model='ct-punc')
res = model.generate(input='[https://isv-data.oss-cn-hangzhou.aliyuncs.com/ics/MaaS/ASR/test_audio/asr_example_zh.wav](https://isv-data.oss-cn-hangzhou.aliyuncs.com/ics/MaaS/ASR/test_audio/asr_example_zh.wav)')
print(res[0]['text'])
"
# Output: 欢迎大家来体验达摩院推出的语音识别模型。

```

---

## 1. Cài đặt (Install)

* **Bản ổn định (Stable release):**
```bash
pip install funasr

```


* **Bản mới nhất (Recommended — cập nhật model mới và sửa lỗi):**
```bash
pip install git+[https://github.com/modelscope/FunASR.git](https://github.com/modelscope/FunASR.git)

```



> **Lưu ý về Hub:** Đối với người dùng tại Trung Quốc, các model sẽ được tải mặc định từ **ModelScope** (tốc độ nhanh). Đối với người dùng quốc tế, hãy thêm tham số `hub="hf"` để tải từ **HuggingFace**.

---

## 2. Lựa chọn Model (Which Model Should I Use?)

### Bảng so sánh các Model

| Model | Phù hợp nhất cho | Ngôn ngữ | Tốc độ | Dấu câu (Punctuation) |
| --- | --- | --- | --- | --- |
| **Paraformer** | Hệ thống ASR thương mại (Chinese) | Tiếng Trung, Tiếng Anh | Nhanh | Cần thêm `punc_model` |
| **Fun-ASR-Nano** | Đa ngôn ngữ, phương ngôn, lời bài hát | 31 ngôn ngữ | Trung bình | Tích hợp sẵn ✓ |
| **SenseVoice** | Nhận diện cảm xúc + sự kiện âm thanh + ASR | 5 ngôn ngữ | Cực nhanh (70ms/10s) | Tích hợp sẵn ✓ |
| **Qwen3-ASR** | Độ chính xác cao nhất, hiểu ngữ cảnh | 52 ngôn ngữ | Chậm (LLM) | Tích hợp sẵn ✓ |
| **Paraformer-Streaming** | Transcription thời gian thực (Real-time) | Tiếng Trung | Thời gian thực | Cần thêm `punc_model` |

### Gợi ý nhanh theo nhu cầu (Quick Recommendation)

* **Họp hành/Cuộc gọi tiếng Trung:** `paraformer-zh` + `fsmn-vad` + `ct-punc` + `cam++`
* **Xử lý đa ngôn ngữ:** `Fun-ASR-Nano`
* **Cần nhận diện cảm xúc / tiếng động môi trường:** `SenseVoice`
* **Làm phụ đề thời gian thực (Live stream):** `paraformer-zh-streaming`
* **Cần chất lượng cao nhất, không quan tâm độ trễ (latency):** `Qwen3-ASR`

---

## 3. Kịch bản sử dụng (Usage Scenarios)

* 🎤 **"Tôi có file ghi âm cuộc họp và muốn xuất văn bản + xác định ai nói gì"**
* -> Sử dụng: *Paraformer + VAD + Punctuation + Speaker Diarization*


* 📺 **"Tôi muốn làm phụ đề thời gian thực cho live stream"**
* -> Sử dụng: *Paraformer-Streaming* (gửi các đoạn audio chunk mỗi 600ms)


* 😊 **"Tôi muốn nhận diện cảm xúc của người nói qua giọng điệu"**
* -> Sử dụng: *SenseVoice* (trả về các tag cảm xúc: happy, sad, angry, neutral)


* 🌍 **"Tôi có file âm thanh tiếng Nhật/Hàn/Ả Rập/v.v."**
* -> Sử dụng: *Fun-ASR-Nano* (31 ngôn ngữ) hoặc *Qwen3-ASR* (52 ngôn ngữ)


* ✂️ **"Tôi muốn cắt video dựa trên nội dung lời nói"**
* -> Sử dụng: *FunClip* (công cụ tích hợp FunASR để edit video thông minh)



---

## 4. Nhận dạng ngoại tuyến (Offline ASR)

### Paraformer (Tiếng Trung)

```python
from funasr import AutoModel

model = AutoModel(
    model="paraformer-zh",          # Chinese ASR
    vad_model="fsmn-vad",           # Xử lý mọi độ dài file audio
    vad_kwargs={"max_single_segment_time": 60000},
    punc_model="ct-punc",           # Thêm dấu câu
)
res = model.generate(input="meeting.wav", batch_size_s=300, hotword='达摩院 语音识别')
print(res[0]["text"])       # "欢迎大家来体验达摩院推出的语音识别模型。"
print(res[0]["timestamp"])  # [[880,1120],[1120,1360],...] (ms mỗi ký tự)

```

### Fun-ASR-Nano (31 Ngôn ngữ)

*Mô hình này tự động xuất dấu câu bản xứ — không cần cấu hình `punc_model`.*

```python
from funasr import AutoModel

model = AutoModel(
    model="FunAudioLLM/Fun-ASR-Nano-2512",
    trust_remote_code=True,
    remote_code="./model.py",
    vad_model="fsmn-vad",
    vad_kwargs={"max_single_segment_time": 30000},
    device="cuda:0",
    hub="hf",
)
res = model.generate(input=["audio.wav"], cache={}, batch_size=1,
                     hotwords=["keyword"], language="中文")
print(res[0]["text"])        # Văn bản đã nhận diện kèm dấu câu
print(res[0]["timestamps"])  # [{"token":"开","start_time":0.42,"end_time":0.48}, ...]

```

### SenseVoice (ASR + Cảm xúc + Sự kiện âm thanh)

```python
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

model = AutoModel(
    model="iic/SenseVoiceSmall",
    vad_model="fsmn-vad",
    vad_kwargs={"max_single_segment_time": 30000},
    device="cuda:0",
)
res = model.generate(input="audio.wav", cache={}, language="auto",
                     use_itn=True, batch_size_s=60, merge_vad=True, merge_length_s=15)

# Output gốc chứa các tag cảm xúc/sự kiện: <|zh|><|HAPPY|><|Speech|>你好
text = rich_transcription_postprocess(res[0]["text"])
print(text)  # "你好" (Văn bản sạch sau khi filter)

```

### Qwen3-ASR (52 Ngôn ngữ - Độ chính xác cao nhất)

```bash
pip install qwen-asr

```

```python
from funasr import AutoModel

model = AutoModel(model="Qwen/Qwen3-ASR-1.7B", hub="hf", device="cuda:0")
res = model.generate(input="audio.wav")
print(res[0]["text"])             # Văn bản nhận diện
print(res[0].get("language"))    # Ngôn ngữ tự động nhận diện

```

---

## 5. Nhận dạng thời gian thực (Streaming ASR)

Xử lý âm thanh theo từng block (chunk) để chuyển ngữ theo thời gian thực. Mỗi block sẽ lập tức trả về văn bản thành phần.

```python
from funasr import AutoModel
import soundfile

model = AutoModel(model="paraformer-zh-streaming")

speech, sr = soundfile.read("audio.wav")
chunk_size = [0, 10, 5]          # 600ms hiển thị, 300ms nhìn trước (lookahead)
chunk_stride = chunk_size[1] * 960  # 9600 samples mỗi chunk

cache = {}
total_chunks = int((len(speech) - 1) / chunk_stride + 1)
for i in range(total_chunks):
    chunk = speech[i * chunk_stride:(i + 1) * chunk_stride]
    is_final = (i == total_chunks - 1)

    res = model.generate(input=chunk, cache=cache, is_final=is_final,
                         chunk_size=chunk_size,
                         encoder_chunk_look_back=4,
                         decoder_chunk_look_back=1)
    if res[0]["text"]:
        print(res[0]["text"], end="", flush=True)  # Output tăng dần

```

**Kết quả in ra (Tăng dần):**

```text
欢迎大 | 家来 | 体验达 | 摩院推 | 出的语 | 音识 | 别模型

```

> 📌 **Điểm mấu chốt:**
> * Biến `cache={}` phải được giữ nguyên qua tất cả các khối chunk (không khởi tạo lại giữa chừng).
> * `is_final=True` ở chunk cuối cùng để ép model giải phóng (flush) toàn bộ văn bản còn trong hàng đợi bộ đệm.
> * Cấu hình `chunk_size=[0,10,5]`: số đầu tiên không dùng, số thứ 2 là độ mịn hiển thị ($\times 60\text{ms}$), số thứ 3 là lookahead ($\times 60\text{ms}$).
> 
> 

---

## 6. Phân tách người nói (Speaker Diarization - "Ai nói gì")

Hỗ trợ tốt trên cả 3 model lớn: Paraformer, Fun-ASR-Nano, và SenseVoice bằng cách thêm tham số `spk_model="cam++"` để lấy nhãn speaker cho từng câu.

### Paraformer + Speaker

```python
from funasr import AutoModel

model = AutoModel(
    model="paraformer-zh",
    vad_model="fsmn-vad",
    punc_model="ct-punc",      # Paraformer cần cái này để phân tách câu
    spk_model="cam++",
)
res = model.generate(input="meeting.wav", batch_size_s=300)

for sent in res[0]["sentence_info"]:
    print(f"[Speaker {sent['spk']}] [{sent['start']}-{sent['end']}ms] {sent['text']}")
# Output mẫu: [Speaker 0] [880-5195ms] 欢迎大家来体验达摩院推出的语音识别模型。

```

### Fun-ASR-Nano + Speaker (Không cần punc_model)

```python
model = AutoModel(
    model="FunAudioLLM/Fun-ASR-Nano-2512",
    trust_remote_code=True, remote_code="./model.py",
    vad_model="fsmn-vad", vad_kwargs={"max_single_segment_time": 30000},
    spk_model="cam++",     # Không cần punc_model!
    device="cuda:0", hub="hf",
)
res = model.generate(input=["meeting.wav"], cache={}, batch_size=1, language="中文")
for sent in res[0]["sentence_info"]:
    print(f"Speaker {sent['spk']}: {sent.get('text', sent.get('sentence', ''))}")

```

### SenseVoice + Speaker (Không cần punc_model)

```python
model = AutoModel(
    model="iic/SenseVoiceSmall",
    vad_model="fsmn-vad", vad_kwargs={"max_single_segment_time": 30000},
    spk_model="cam++",    # Không cần punc_model!
    device="cuda:0",
)
res = model.generate(input="meeting.wav", cache={}, language="auto",
                     use_itn=True, batch_size_s=60, merge_vad=True, merge_length_s=15)
for sent in res[0]["sentence_info"]:
    print(f"Speaker {sent['spk']}: {rich_transcription_postprocess(sent['text'])}")

```

---

## 7. Nhận diện cảm xúc (Emotion Detection)

### Model chuyên dụng (emotion2vec)

```python
from funasr import AutoModel

model = AutoModel(model="iic/emotion2vec_plus_large", device="cuda:0")
res = model.generate(input="audio.wav", granularity="utterance")

print(res[0]["labels"])  # ['angry', 'happy', 'neutral', 'sad', ...]
print(res[0]["scores"])  # [0.01,   0.03,   0.89,      0.05, ...]
# -> Audio này mang sắc thái "neutral" (bình thường) với độ tự tin 89%

```

### SenseVoice (ASR + Cảm xúc tích hợp sẵn)

SenseVoice nhúng trực tiếp các tag cảm xúc vào chuỗi văn bản trả về:

* *Output thô:* `"<|zh|><|HAPPY|><|Speech|><|withitn|>今天真是太开心了。"`
* Thẻ `<|HAPPY|>` biểu thị cảm xúc của đoạn thoại.
* Sử dụng hàm `rich_transcription_postprocess()` để lọc lấy văn bản sạch.

---

## 8. Nhận diện phân đoạn hội thoại (Voice Activity Detection - VAD)

### Ngoại tuyến (Xử lý toàn bộ file âm thanh)

```python
from funasr import AutoModel

model = AutoModel(model="fsmn-vad")
res = model.generate(input="audio.wav")
print(res[0]["value"])  # [[610, 5530], [7200, 12400], ...]
                         # Mỗi cặp: [start_ms, end_ms] của tiếng nói

```

### Thời gian thực (Streaming chunk-by-chunk)

```python
import soundfile
from funasr import AutoModel

model = AutoModel(model="fsmn-vad")
speech, sr = soundfile.read("audio.wav")
chunk_stride = int(200 * sr / 1000)  # Khối chunk 200ms

cache = {}
for i in range(int((len(speech)-1)/chunk_stride+1)):
    chunk = speech[i*chunk_stride:(i+1)*chunk_stride]
    is_final = i == int((len(speech)-1)/chunk_stride)
    res = model.generate(input=chunk, cache=cache, is_final=is_final, chunk_size=200)
    if res[0]["value"]:
        print(res[0]["value"])
        # [[610, -1]]   → Tiếng nói bắt đầu tại 610ms
        # [[-1, 5530]]  → Tiếng nói kết thúc tại 5530ms
        # [[610, 5530]] → Hoàn thành một phân đoạn

```

---

## 9. Tự động thêm dấu câu (Punctuation Restoration)

```python
from funasr import AutoModel

model = AutoModel(model="ct-punc")
res = model.generate(input="那今天的会就到这里吧 happy new year 明年见")
print(res[0]["text"])  # "那今天的会就到这里吧，happy new year，明年见。"

```

> ⚠️ **Khi nào cần dùng?** Chỉ thực sự cần thiết khi dùng với model **Paraformer** (mặc định xuất text thô không dấu câu). Các model khác như *Fun-ASR-Nano*, *SenseVoice*, và *Qwen3-ASR* đều hỗ trợ dấu câu tự động.

---

## 10. Triển khai & Tích hợp Agent (Deploy & Agent Integration)

Sử dụng `funasr-server` khi bạn cần tạo một endpoint cục bộ (local endpoint) tương thích với chuẩn OpenAI dành cho ứng dụng hoặc AI Agent của bạn.

```bash
pip install funasr fastapi uvicorn python-multipart
funasr-server --device cuda --port 8000

```

Gọi API thông qua thư viện `openai` trong Python:

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="x")
result = client.audio.transcriptions.create(
    model="sensevoice",
    file=open("meeting.wav", "rb"),
    response_format="verbose_json",
)

```

> Đối với Claude Code, Cursor, và các MCP client khác, bạn hãy cấu hình file `examples/mcp_server/funasr_mcp.py`. Xem chi tiết tại *Agent integration guide*.

---

## 11. Tạo phụ đề (Subtitle Generation)

Hỗ trợ tạo định dạng phụ đề `.srt` hoặc `.vtt` từ file audio/video, có tùy chọn gán nhãn người nói.

```bash
cd examples/subtitle
python generate_subtitle.py video.mp4
python generate_subtitle.py meeting.wav --spk
python generate_subtitle.py podcast.mp3 --format vtt

```

---

## 12. Xuất định dạng ONNX (ONNX Export)

```python
# 1. Xuất model sang định dạng ONNX
from funasr import AutoModel
model = AutoModel(model="paraformer", device="cpu")
model.export(quantize=False)   # Lưu vào thư mục cache của model

# 2. Sử dụng model ONNX (Tốc độ nhanh hơn, không cần PyTorch)
# pip install funasr-onnx
from funasr_onnx import Paraformer
model = Paraformer("damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                   batch_size=1, quantize=True)
result = model(["audio.wav"])
print(result)

```

---

## 13. Câu hỏi thường gặp & Sửa lỗi (FAQ & Troubleshooting)

### Tốc độ tải model quá chậm?

Hãy set thuộc tính `hub="hf"` để chuyển hướng tải từ HuggingFace (nhanh hơn khi ở ngoài Trung Quốc), hoặc tải thủ công một lần và truyền đường dẫn thư mục local:

```python
model = AutoModel(model="/path/to/local/model", disable_update=True)

```

### Lỗi tràn bộ nhớ (Out of Memory - OOM)?

Hãy tinh chỉnh 3 tham số sau để giảm thiểu lượng RAM/VRAM tiêu thụ:

1. Giảm `batch_size_s` (Ví dụ: từ `300` xuống `60`).
2. Giảm `max_single_segment_time` trong cấu hình `vad_kwargs` (Ví dụ: `30000` $\rightarrow$ `15000`).
3. Thêm tham số `batch_size_threshold_s=30` để ép hệ thống dùng `batch=1` đối với các phân đoạn quá dài.

### Mỗi lần khởi chạy đều hiện "Downloading Model..."?

Hệ thống không thực sự tải lại mà chỉ đang check/verify tính toàn vẹn của cache. Để tắt hoàn toàn tính năng này:

```python
model = AutoModel(model="/local/path/to/model", disable_update=True)

```

### Gặp lỗi `"ModelName is not registered"`?

Thường do phiên bản thư viện trên pypi (`pip install funasr`) bị cũ so với repo gốc. Hãy cài đặt trực tiếp từ mã nguồn GitHub:

```bash
pip install git+[https://github.com/modelscope/FunASR.git](https://github.com/modelscope/FunASR.git)

```

### Muốn ẩn toàn bộ tiến trình (progress bar) và log thông báo?

```python
model = AutoModel(model="...", disable_update=True, disable_pbar=True, log_level="ERROR")

```

### Làm thế nào để truyền trực tiếp mảng Numpy Audio đã load sẵn?

```python
import soundfile as sf
audio, sr = sf.read("audio.wav")  # Mảng numpy array, tần số 16kHz
res = model.generate(input=audio)  # Truyền trực tiếp mảng array mà không cần qua file mẫu

```

### GPU không hoạt động / không được sử dụng?

Kiểm tra xem PyTorch đã nhận CUDA chính xác chưa:

```python
import torch
print(torch.cuda.is_available())  # Kết quả phải trả về True

```

Sau đó chỉ định GPU tường minh khi khởi tạo model:

```python
model = AutoModel(model="...", device="cuda:0")

```

```

```