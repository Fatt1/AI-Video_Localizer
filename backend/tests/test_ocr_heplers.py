# backend/tests/test_ocr_helpers.py
import numpy as np
import pytest
from services.ocr_service import (
    crop_frame,
    frames_are_same,
    compute_hash,
    frames_to_srt,
    _should_reuse_ocr_result,
    _texts_are_same,
    post_process_ocr_entries,
)
import tempfile, os


def make_blank_image(h=200, w=400, color=(0, 0, 0)):
    """Tạo ảnh giả để test"""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


def test_crop_frame_correct_size():
    img = make_blank_image(200, 400)
    cropped = crop_frame(img, [50, 100, 300, 80])  # x=50,y=100,w=300,h=80
    assert cropped.shape == (80, 300, 3)


def test_crop_frame_full():
    img = make_blank_image(200, 400)
    cropped = crop_frame(img, [0, 0, 400, 200])
    assert cropped.shape == (200, 400, 3)


def test_frames_same_identical():
    """2 ảnh giống nhau → hash khớp"""
    img = make_blank_image(100, 200, color=(128, 128, 128))
    h1 = compute_hash(img)
    h2 = compute_hash(img.copy())
    assert frames_are_same(h1, h2, threshold=5) == True


def test_frames_different():
    """2 ảnh hoàn toàn khác nhau → hash string phải khác nhau"""
    # Ảnh hoàn toàn ngẫu nhiên với seed cố định → reproducible
    rng = np.random.default_rng(seed=42)
    img_noise_1 = rng.integers(0, 256, (100, 200, 3), dtype=np.uint8)
    img_noise_2 = rng.integers(0, 256, (100, 200, 3), dtype=np.uint8)

    h1 = compute_hash(img_noise_1)
    h2 = compute_hash(img_noise_2)
    # 2 ảnh random khác nhau phải tạo ra hash string khác nhau
    assert h1 != h2


def test_frames_to_srt_format():
    """Kiểm tra output SRT đúng format"""
    entries = [
        {"start": 0.0, "end": 2.5, "text": "Xin chào"},
        {"start": 3.0, "end": 5.0, "text": "Tạm biệt"},
    ]
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.srt', delete=False, encoding='utf-8'
    ) as f:
        out_path = f.name

    try:
        frames_to_srt(entries, out_path)
        content = open(out_path, encoding='utf-8').read()
        assert "1\n" in content
        assert "00:00:00,000 --> 00:00:02,500" in content
        assert "Xin chào" in content
        assert "2\n" in content
        assert "Tạm biệt" in content
    finally:
        os.unlink(out_path)


def test_should_reuse_ocr_result_within_time_window():
    """Chỉ reuse khi hash giống và còn trong cửa sổ thời gian ngắn."""
    img = make_blank_image(120, 240, color=(90, 90, 90))
    h = compute_hash(img)
    assert _should_reuse_ocr_result(
        prev_hash=h,
        curr_hash=h,
        prev_text="xin chao",
        current_time=1.20,
        last_ocr_time=0.90,
        max_reuse_window=0.5,
    ) is True


def test_should_not_reuse_ocr_result_outside_time_window():
    """Nếu quá thời gian thì phải OCR lại để tránh giữ text cũ."""
    img = make_blank_image(120, 240, color=(90, 90, 90))
    h = compute_hash(img)
    assert _should_reuse_ocr_result(
        prev_hash=h,
        curr_hash=h,
        prev_text="xin chao",
        current_time=2.00,
        last_ocr_time=0.90,
        max_reuse_window=0.5,
    ) is False


def test_post_process_typing_merge_has_duration_cap():
    """Typing effect chỉ được gộp ngắn hạn, không nuốt cả đoạn dài."""
    entries = [
        {"start": 0.00, "end": 0.25, "text": "abc"},
        {"start": 0.25, "end": 0.50, "text": "abcd"},
        {"start": 0.50, "end": 0.75, "text": "abcde"},
        {"start": 0.75, "end": 1.00, "text": "abcdef"},
        {"start": 1.00, "end": 1.25, "text": "abcdefg"},
        {"start": 1.25, "end": 1.50, "text": "abcdefgh"},
        {"start": 1.50, "end": 1.75, "text": "abcdefghi"},
    ]

    processed = post_process_ocr_entries(
        entries,
        min_duration=0.0,
        max_gap=0.45,
        typing_merge_max_duration=1.0,
    )

    # Nếu không có cap, toàn bộ 7 frame sẽ bị gộp thành 1 block.
    assert len(processed) >= 2


def test_texts_are_same_when_only_punctuation_differs():
    """Khác nhau dấu ngoặc/quote nhưng cùng nội dung thì vẫn coi là 1 câu."""
    a = "因为她这次要请的是「将军神」"
    b = "因为她这次要请的是[将军神]"
    assert _texts_are_same(a, b) is True


def test_post_process_keeps_single_frame_subtitle_if_over_min_duration():
    """Subtitle ngắn 0.25s (fps=4) không bị lọc mất khi min_duration=0.20s."""
    entries = [
        {"start": 4.225, "end": 4.475, "text": "要是没动了那种地方"},
    ]

    processed = post_process_ocr_entries(entries, min_duration=0.20)
    assert len(processed) == 1


def test_post_process_absorbs_short_near_duplicate_tail_blip():
    """Case thực tế: dòng sau chỉ 1 frame và gần giống dòng trước thì coi là nhiễu."""
    entries = [
        {"start": 301.75, "end": 303.00, "text": "杀死动物献给神的巫术"},
        {"start": 303.00, "end": 303.25, "text": "杀死动物献给神的术"},
    ]

    processed = post_process_ocr_entries(entries, min_duration=0.20)

    assert len(processed) == 1
    assert processed[0]["text"] == "杀死动物献给神的巫术"
    assert processed[0]["start"] == 301.75
    assert processed[0]["end"] == 303.25


def test_post_process_majority_vote_picks_most_common_variant():
    """Nếu cùng một subtitle lặp nhiều frame, chọn biến thể xuất hiện nhiều nhất."""
    entries = [
        {"start": 0.00, "end": 0.25, "text": "帝女凤那丫头", "confidence": 0.98},
        {"start": 0.25, "end": 0.50, "text": "帝女凤那丫头", "confidence": 0.97},
        {"start": 0.50, "end": 0.75, "text": "帝女风那丫头", "confidence": 0.75},
        {"start": 0.75, "end": 1.00, "text": "帝女凤那丫头", "confidence": 0.96},
    ]

    processed = post_process_ocr_entries(entries, min_duration=0.0)

    assert len(processed) == 1
    assert processed[0]["text"] == "帝女凤那丫头"


def test_post_process_tie_break_uses_higher_confidence():
    """Nếu hòa 1-1 giữa 2 biến thể gần giống, chọn frame có confidence cao hơn."""
    entries = [
        {"start": 0.00, "end": 0.25, "text": "帝女风那丫头", "confidence": 0.75},
        {"start": 0.25, "end": 0.50, "text": "帝女凤那丫头", "confidence": 0.96},
    ]

    processed = post_process_ocr_entries(entries, min_duration=0.0)

    assert len(processed) == 1
    assert processed[0]["text"] == "帝女凤那丫头"


def test_post_process_keeps_block_when_middle_frame_is_noisy_variant():
    """Frame ở giữa bị OCR lệch do vật thể che chữ không được làm tách cả block."""
    entries = [
        {"start": 38.25, "end": 38.50, "text": "今日是黑水铜调主的寿诞", "confidence": 0.897},
        {"start": 38.50, "end": 38.75, "text": "今日是黑水调调主的寿诞", "confidence": 0.889},
        {"start": 38.75, "end": 39.00, "text": "今日是黑水调调主的寿诞", "confidence": 0.884},
        {"start": 39.00, "end": 39.25, "text": "今日是黑水铜调主的寿诞", "confidence": 0.909},
        {"start": 39.25, "end": 39.50, "text": "今日是黑水铜铜主的寿诞", "confidence": 0.899},
        {"start": 39.50, "end": 39.75, "text": "今日是黑水调主的寿诞", "confidence": 0.931},
        {"start": 39.75, "end": 40.00, "text": "今日是黑水调调主的寿诞", "confidence": 0.903},
        {"start": 40.00, "end": 40.25, "text": "今日是黑水调调主的寿诞", "confidence": 0.872},
        {"start": 40.25, "end": 40.50, "text": "今日是黑水调明主的寿诞", "confidence": 0.883},
        {"start": 40.50, "end": 40.75, "text": "今日是黑水调调主的寿诞", "confidence": 0.880},
    ]

    processed = post_process_ocr_entries(entries, min_duration=0.0)

    assert len(processed) == 1
    assert processed[0]["start"] == 38.25
    assert processed[0]["end"] == 40.75
    assert processed[0]["text"] == "今日是黑水调调主的寿诞"


def test_post_process_merges_when_one_frame_drops_one_character():
    """OCR thiếu/thừa đúng 1 ký tự vẫn phải được coi là cùng subtitle."""
    entries = [
        {"start": 0.00, "end": 0.25, "text": "今日是黑水调调主的寿诞", "confidence": 0.88},
        {"start": 0.25, "end": 0.50, "text": "今日是黑水调主的寿诞", "confidence": 0.93},
        {"start": 0.50, "end": 0.75, "text": "今日是黑水调调主的寿诞", "confidence": 0.90},
    ]

    processed = post_process_ocr_entries(entries, min_duration=0.0)

    assert len(processed) == 1
    assert processed[0]["start"] == 0.00
    assert processed[0]["end"] == 0.75
