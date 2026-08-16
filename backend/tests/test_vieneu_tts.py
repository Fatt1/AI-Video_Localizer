"""
Test VieNeu-TTS v2 Standard GPU -- voice cloning synthesis.

Run:
    cd e:/AI-Video_Localizer/backend
    python -m tests.test_vieneu_tts
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.tts_service import (
    get_vieneu_model,
    list_vieneu_voice_clones,
    get_vieneu_clone_by_id,
    synthesize_line_vieneu,
    unload_vieneu_model,
    get_active_engine,
)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "temp" / "test_vieneu"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def test_list_voices():
    """Test 1: Liệt kê voice clones VieNeu."""
    print("\n" + "=" * 60)
    print("TEST 1: list_vieneu_voice_clones()")
    print("=" * 60)

    clones = list_vieneu_voice_clones()
    print(f"  Tìm thấy {len(clones)} voice clone(s):")
    for c in clones:
        print(f"    - {c['id']}")
        print(f"      name: {c['name']}")
        print(f"      ref_audio: {c['ref_audio']}")
        print(f"      ref_text: {c['ref_text'][:80]}..." if len(c.get('ref_text', '')) > 80 else f"      ref_text: {c.get('ref_text', '')}")
        print(f"      has_transcript: {c['has_transcript']}")

    assert len(clones) > 0, "Không tìm thấy voice clone nào trong voice_clones_vieneu/"
    print("  ✅ PASSED")
    return clones


def test_get_clone_by_id():
    """Test 2: Tìm voice clone theo ID."""
    print("\n" + "=" * 60)
    print("TEST 2: get_vieneu_clone_by_id('review-truyen-nam-voice')")
    print("=" * 60)

    clone = get_vieneu_clone_by_id("review-truyen-nam-voice")
    assert clone is not None, "Không tìm thấy clone 'review-truyen-nam-voice'"
    assert clone["has_transcript"], "Clone thiếu file .txt transcript"
    assert clone["ref_text"], "Transcript rỗng"

    print(f"  id: {clone['id']}")
    print(f"  ref_audio: {clone['ref_audio']}")
    print(f"  ref_text: {clone['ref_text']}")
    print("  ✅ PASSED")
    return clone


def test_load_model():
    """Test 3: Lazy load VieNeu model."""
    print("\n" + "=" * 60)
    print("TEST 3: get_vieneu_model() — lazy loading")
    print("=" * 60)

    print("  Active engine trước khi load:", get_active_engine())

    t0 = time.time()
    model = get_vieneu_model()
    elapsed = time.time() - t0

    assert model is not None, "Model load thất bại"
    assert get_active_engine() == "vieneu", f"Active engine sai: {get_active_engine()}"

    sr = getattr(model, "sample_rate", "?")
    print(f"  Model loaded trong {elapsed:.1f}s")
    print(f"  Sample rate: {sr}")
    print(f"  Active engine: {get_active_engine()}")
    print("  ✅ PASSED")


async def test_synthesize():
    """Test 4: Tổng hợp giọng nói với VieNeu clone."""
    print("\n" + "=" * 60)
    print("TEST 4: synthesize_line_vieneu() — voice cloning")
    print("=" * 60)

    text = "xin chào các bạn hôm nay mình sẽ review một bộ phim mới ra mắt"
    voice_id = "review-truyen-nam-voice"
    output_path = OUTPUT_DIR / "test_vieneu_output.wav"

    print(f"  Text: {text}")
    print(f"  Voice: {voice_id}")
    print(f"  Output: {output_path}")

    t0 = time.time()
    result = await synthesize_line_vieneu(
        text=text,
        voice_id=voice_id,
        output_path=str(output_path),
        speech_rate=1.0,
        temperature=1.0,
        max_chars=256,
    )
    elapsed = time.time() - t0

    assert output_path.exists(), f"File output không tồn tại: {output_path}"
    file_size = output_path.stat().st_size
    assert file_size > 44, f"File output quá nhỏ ({file_size} bytes)"

    print(f"  ✅ Tạo thành công!")
    print(f"  File: {result}")
    print(f"  Size: {file_size:,} bytes")
    print(f"  Thời gian: {elapsed:.2f}s")

    # Kiểm tra duration
    try:
        import soundfile as sf
        data, sr = sf.read(str(output_path))
        duration = len(data) / sr
        print(f"  Duration: {duration:.2f}s @ {sr} Hz")
    except Exception:
        pass

    print("  ✅ PASSED")


def test_unload():
    """Test 5: Unload model."""
    print("\n" + "=" * 60)
    print("TEST 5: unload_vieneu_model()")
    print("=" * 60)

    unload_vieneu_model()
    assert get_active_engine() is None, f"Engine vẫn active: {get_active_engine()}"
    print(f"  Active engine: {get_active_engine()}")
    print("  ✅ PASSED")


async def main():
    print("🧪 VieNeu-TTS v2 Integration Test")
    print("=" * 60)

    try:
        # Test 1-2: Voice listing (no model needed)
        test_list_voices()
        test_get_clone_by_id()

        # Test 3: Model loading
        test_load_model()

        # Test 4: Synthesis
        await test_synthesize()

        # Test 5: Cleanup
        test_unload()

        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print(f"📂 Output files: {OUTPUT_DIR}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        test_unload()  # cleanup even on failure
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
