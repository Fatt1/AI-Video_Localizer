# backend/services/ocr_service.py
import subprocess
import cv2
import imagehash
from PIL import Image
import numpy as np
import tempfile
import os
import sys
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher

def _text_similarity(a: str, b: str) -> float:
    """Trả về tỉ lệ giống nhau giữa 2 chuỗi (0.0 → 1.0)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _normalize_text(text: str) -> str:
    """Chuẩn hóa text trước khi so sánh để giảm nhiễu do ký tự fullwidth/spacing."""
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", text)
    return " ".join(normalized.split()).strip()


def _text_core(text: str) -> str:
    """Lấy lõi ký tự (loại bỏ punctuation/space) để so sánh câu gần giống."""
    normalized = _normalize_text(text)
    chars = []
    for ch in normalized:
        cat = unicodedata.category(ch)
        # P*: punctuation, Z*: separators (space)
        if cat.startswith("P") or cat.startswith("Z"):
            continue
        chars.append(ch)
    return "".join(chars)

def _texts_are_same(a: str | None, b: str | None, threshold: float = 0.84) -> bool:
    """So sánh fuzzy: 2 câu giống >= 80% → coi là cùng một câu thoại."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False

    a_core = _text_core(a)
    b_core = _text_core(b)
    if not a_core or not b_core:
        return False

    if a_core == b_core:
        return True

    # Typing effect (câu sau là phần mở rộng câu trước) không coi là "same".
    if a_core in b_core or b_core in a_core:
        return False

    # OCR nhiễu ký tự: ưu tiên trường hợp cùng độ dài (thay nhầm 1-2 ký tự),
    # tránh gộp nhầm với câu đang dần dài ra.
    if len(a_core) == len(b_core) and _text_similarity(a_core, b_core) >= threshold:
        return True

    return False


def _texts_are_near_variants(a: str | None, b: str | None, threshold: float = 0.90) -> bool:
    """
    So sánh "gần giống" cho mục đích khử nhiễu ngắn (1 frame).
    Dùng ngưỡng cao để tránh gộp sai 2 câu khác nhau.
    """
    if a is None or b is None:
        return False

    a_core = _text_core(a)
    b_core = _text_core(b)
    if not a_core or not b_core:
        return False

    if a_core == b_core:
        return True

    sim = _text_similarity(a_core, b_core)
    if sim < threshold:
        return False

    # Nếu là containment nhưng chênh lệch quá lớn thì có thể là typing/dòng khác.
    if a_core in b_core or b_core in a_core:
        shorter = min(len(a_core), len(b_core))
        longer = max(len(a_core), len(b_core))
        if longer == 0:
            return False
        if (shorter / longer) < 0.80:
            return False

    return True

from core.task_manager import Task, TaskStatus
from core.config import FFMPEG_PATH   # dùng path đã detect sẵn

# Khởi tạo PaddleOCR một lần (load model tốn ~5s lần đầu)
# Dùng PaddleOCR 2.7.x — API ổn định, không dùng PaddleX pipeline
_ocr_engine = None
_paddle_cuda_paths_initialized = False


def _iter_nvidia_bin_dirs() -> list[Path]:
    import site

    bin_dirs: list[Path] = []
    for sp in site.getsitepackages():
        nvidia_dir = Path(sp) / "nvidia"
        if not nvidia_dir.exists():
            continue
        for sub_dir in nvidia_dir.iterdir():
            dll_bin_path = sub_dir / "bin"
            if dll_bin_path.exists():
                bin_dirs.append(dll_bin_path)
    return bin_dirs


def _ensure_paddle_cuda_dll_paths() -> None:
    """
    Register NVIDIA DLL directories for Paddle on Windows.

    Important: Do not mutate os.environ['PATH'] globally here because that can
    shadow PyTorch's own CUDA DLLs and break OmniVoice with WinError 127.
    """
    global _paddle_cuda_paths_initialized
    if _paddle_cuda_paths_initialized:
        return

    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        _paddle_cuda_paths_initialized = True
        return

    for dll_bin_path in _iter_nvidia_bin_dirs():
        try:
            os.add_dll_directory(str(dll_bin_path))
        except Exception:
            # Ignore non-critical registration errors and let Paddle raise later if needed.
            continue

    _paddle_cuda_paths_initialized = True


def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        # Preload torch before registering Paddle CUDA paths to avoid DLL conflicts
        # when both OCR (Paddle) and dubbing (OmniVoice/Torch) run in one process.
        if "torch" not in sys.modules:
            try:
                import torch  # noqa: F401
            except Exception:
                pass

        _ensure_paddle_cuda_dll_paths()

        from paddleocr import PaddleOCR

        # use_angle_cls=True: xoay ảnh để detect text nghiêng
        # use_gpu=True: Dùng card đồ họa NVIDIA (đã cài paddlepaddle-gpu)
        _ocr_engine = PaddleOCR(
            use_angle_cls=True,
            use_gpu=True,
            lang='ch',
            show_log=False,
        )
    return _ocr_engine


def extract_frames(video_path: str, fps: float, output_dir: str) -> list[str]:
    """Trích xuất frames từ video dùng FFmpeg"""
    frame_pattern = os.path.join(output_dir, "frame_%06d.jpg")
    cmd = [
        FFMPEG_PATH,          # đường dẫn đầy đủ thay vì "ffmpeg"
        "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        frame_pattern,
        "-y"
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    frames = sorted(Path(output_dir).glob("frame_*.jpg"))
    return [str(f) for f in frames]


def crop_frame(image: np.ndarray, crop_region: list) -> np.ndarray:
    """Crop ảnh theo [X, Y, W, H]"""
    x, y, w, h = crop_region
    return image[y:y+h, x:x+w]


def compute_hash(image: np.ndarray) -> str:
    """Tính perceptual hash để dedup frame"""
    pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    return str(imagehash.phash(pil_img))


def frames_are_same(hash1: str, hash2: str, threshold: int = 5) -> bool:
    """So sánh 2 hash — threshold=5 là hợp lý cho subtitle"""
    h1 = imagehash.hex_to_hash(hash1)
    h2 = imagehash.hex_to_hash(hash2)
    return (h1 - h2) <= threshold


def _should_reuse_ocr_result(
    prev_hash: str | None,
    curr_hash: str,
    prev_text: str | None,
    current_time: float,
    last_ocr_time: float | None,
    max_reuse_window: float = 0.25,
    max_hash_distance: int = 2,
) -> bool:
    """
    Chỉ tái sử dụng kết quả OCR trong cửa sổ thời gian ngắn.
    Mục tiêu: tránh giữ text cũ quá lâu khi subtitle thay đổi nhưng frame hash vẫn gần giống.
    """
    if prev_hash is None or not prev_text:
        return False
    # Reuse chỉ khi hash THỰC SỰ gần nhau, tránh giữ text cũ lúc subtitle vừa đổi.
    if not frames_are_same(prev_hash, curr_hash, threshold=max_hash_distance):
        return False
    if last_ocr_time is None:
        return False
    return (current_time - last_ocr_time) <= max_reuse_window


def ocr_image(image: np.ndarray) -> str:
    """
    Nhận diện text từ ảnh dùng PaddleOCR 2.7.x.
    Output format: [[[box_coords], (text, confidence)], ...]
    """
    engine = get_ocr_engine()
    # cls=True: dùng angle classifier (cần use_angle_cls=True khi init)
    result = engine.ocr(image, cls=True)
    if not result or not result[0]:
        return ""
    # Lọc theo confidence > 60%
    texts = [
        line[1][0]
        for line in result[0]
        if line and line[1][1] > 0.6
    ]
    return " ".join(texts).strip()


def frames_to_srt(entries: list[dict], output_path: str):
    """Chuyển list entries sang file .srt"""
    def to_srt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(output_path, "w", encoding="utf-8") as f:
        for i, entry in enumerate(entries, 1):
            f.write(f"{i}\n")
            f.write(f"{to_srt_time(entry['start'])} --> {to_srt_time(entry['end'])}\n")
            f.write(f"{entry['text']}\n\n")
from difflib import SequenceMatcher

def post_process_ocr_entries(
    entries: list[dict],
    min_duration: float = 0.20,
    max_gap: float = 0.45,
    typing_merge_max_duration: float = 1.2,
    short_glitch_max_duration: float = 0.28,
) -> list[dict]:
    """
    1. Gộp các block liên tiếp giống nhau hoặc bị gõ chữ (typing effect).

    2. Lọc bỏ các block quá ngắn (do OCR nhận diện sai chớp nhoáng).

    """
    if not entries:
        return []

    # Hàm kiểm tra giống nhau hoặc typing

    def normalize_text(s: str) -> str:
        return " ".join(s.split())

    def compare_text_relation(a: str, b: str) -> str:
        """Trả về: exact | typing | different"""
        if not a or not b:
            return "different"

        a_n = normalize_text(a)
        b_n = normalize_text(b)
        a_core = _text_core(a_n)
        b_core = _text_core(b_n)

        if a_n == b_n:
            return "exact"

        # Cùng nội dung nhưng khác dấu ngoặc/quote/punctuation.
        if a_core and b_core and a_core == b_core:
            return "exact"

        # OCR đôi khi lệch nhẹ 1-2 ký tự do nhòe/viền subtitle.
        if _texts_are_same(a_n, b_n):
            return "exact"

        # Hiệu ứng typing thường là câu sau chứa câu trước với phần đuôi mở rộng.
        if (a_core in b_core or b_core in a_core) and abs(len(a_core) - len(b_core)) <= 12:
            return "typing"

        # Vẫn cho phép fuzzy nhưng threshold cao để tránh gộp sai.
        if _text_similarity(a_core, b_core) >= 0.90:
            return "typing"

        return "different"
    # 1. Gộp (Merging)
    merged = []
    curr = entries[0].copy()
    for nxt in entries[1:]:

        gap = nxt["start"] - curr["end"]
        relation = compare_text_relation(curr["text"], nxt["text"])

        # exact: cho merge bình thường
        # typing: chỉ merge trong khoảng ngắn để tránh nuốt mất subtitle ở giữa
        can_merge_typing = (
            relation == "typing"
            and (curr["end"] - curr["start"]) <= typing_merge_max_duration
        )
        can_merge_exact = relation == "exact"

        if gap <= max_gap and (can_merge_exact or can_merge_typing):
            curr["end"] = nxt["end"]

            # Với typing effect, giữ text dài hơn để lấy câu hoàn chỉnh cuối cùng.
            if relation == "typing" and len(nxt["text"]) >= len(curr["text"]):
                curr["text"] = nxt["text"]

        else:

            merged.append(curr)

            curr = nxt.copy()
    merged.append(curr)
    # 2. Lọc nhiễu (Filtering)
    final_entries = []

    for e in merged:
        duration = e["end"] - e["start"]

        # Khử "đuôi nhiễu" rất ngắn: ví dụ dòng 166 chỉ 1 frame và gần giống hệt dòng 165.
        # Khi gặp trường hợp này, nối thời gian vào dòng trước và giữ text dòng trước.
        if final_entries:
            prev = final_entries[-1]
            prev_duration = prev["end"] - prev["start"]
            gap = e["start"] - prev["end"]

            if (
                duration <= short_glitch_max_duration
                and prev_duration >= (2.0 * duration)
                and gap <= max_gap
                and _texts_are_near_variants(prev["text"], e["text"])
            ):
                prev["end"] = e["end"]
                continue

        if duration >= (min_duration - 1e-6):
            final_entries.append(e)

    return final_entries
    


async def run_ocr_pipeline(
    video_path: str,
    crop_region: list,
    fps: float,
    output_srt: str,
    task: Task
):
    """Pipeline chính: video → frames → dedup → OCR → SRT"""
    print(f"\n[OCR Task {task.task_id}] Bắt đầu xử lý video: {video_path}")
    print(f"[OCR Task {task.task_id}] Thông số - Vùng chọn: {crop_region}, FPS: {fps}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Bước 1: Trích frames
        print(f"[OCR Task {task.task_id}] Đang dùng FFMPEG cắt video thành từng frames...")
        await task.update(5, "Đang trích xuất frames từ video...")
        frame_paths = extract_frames(video_path, fps, tmp_dir)
        total_frames = len(frame_paths)
        print(f"[OCR Task {task.task_id}] Trích xuất thành công {total_frames} frames ảnh.")
        await task.update(15, f"Đã trích xuất {total_frames} frames")

        if task.is_cancelled():
            print(f"[OCR Task {task.task_id}] Task đã bị người dùng hủy!")
            return

        # Bước 2: Xử lý từng frame (dedup + OCR)
        print(f"[OCR Task {task.task_id}] Bắt đầu phân tích OCR ({total_frames} ảnh)...")
        raw_entries = []
        prev_hash = None
        prev_text = None
        last_ocr_time = None

        for i, frame_path in enumerate(frame_paths):
            if task.is_cancelled():
                print(f"[OCR Task {task.task_id}] Task đã bị người dùng hủy!")
                return

            if i % 10 == 0 or i == total_frames - 1:
                progress = 15 + int(80 * (i / total_frames))
                print(f"[OCR Progress] Đang quét ảnh {i}/{total_frames} ({progress}%)")
                await task.update(progress, f"Đang nhận diện chữ... ({i}/{total_frames})", TaskStatus.RUNNING)

            image = cv2.imread(frame_path)
            if image is None:
                continue

            cropped = crop_frame(image, crop_region)
            curr_hash = compute_hash(cropped)
            frame_time = i / fps  # Thời gian theo giây

            # Chỉ reuse OCR trong cửa sổ rất ngắn để tránh giữ text cũ quá lâu.
            if _should_reuse_ocr_result(
                prev_hash=prev_hash,
                curr_hash=curr_hash,
                prev_text=prev_text,
                current_time=frame_time,
                last_ocr_time=last_ocr_time,
            ):
                text = prev_text
            else:
                text = ocr_image(cropped) or None
                last_ocr_time = frame_time

            if text:
                raw_entries.append({
                    "start": frame_time,
                    "end": frame_time + (1.0 / fps),
                    "text": text
                })

            prev_text = text
            prev_hash = curr_hash

            # Update progress (15% → 90%) — mỗi 20 frames để tránh spam
            if i % 20 == 0:
                progress = 15 + int((i / total_frames) * 75)
                await task.update(progress, f"Đang xử lý frame {i}/{total_frames}...")

        await task.update(90, f"Đã nhận diện {len(raw_entries)} frame có chữ. Đang gộp và lọc nhiễu...")

        # Bước 3: Thuật toán Gộp & Lọc nhiễu
        # Giữ được subtitle ngắn: min_duration phụ thuộc FPS (không dùng hằng số cứng 0.35s).
        min_duration = max(0.12, min(0.22, 0.8 / max(fps, 0.1)))
        entries = post_process_ocr_entries(raw_entries, min_duration=min_duration)
        
        # Lọc rỗng lặp lại cho chắc chắn
        entries = [e for e in entries if e["text"].strip()]

        # Bước 3: Lưu SRT
        frames_to_srt(entries, output_srt)
        await task.complete(result={"srt_path": output_srt, "subtitle_count": len(entries)})