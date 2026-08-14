from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services.dubbing_service import (
    _fit_audio_to_slot,
    _normalize_tts_text,
    run_dubbing_pipeline,
)


@dataclass
class _FakeSubRipTime:
    ordinal: int


@dataclass
class _FakeSub:
    text: str
    start: _FakeSubRipTime
    end: _FakeSubRipTime


class _FakeTask:
    def __init__(self, task_id: str = "task-1"):
        self.task_id = task_id
        self.fail = AsyncMock()
        self.update = AsyncMock()
        self.complete = AsyncMock()

    def is_cancelled(self) -> bool:
        return False


def test_normalize_tts_text_collapses_newlines_and_spaces():
    assert _normalize_tts_text("  cay \n nhung   con\tkha dai  ") == "cay nhung con kha dai"


def test_fit_audio_to_slot_caps_extra_atempo():
    fake_path = Path("dummy.wav")
    observed_speeds = []
    durations = iter([3_000_000, 2_650_000, 2_540_000])

    def fake_get_audio_duration_us(_):
        return next(durations)

    def fake_apply_speed_to_existing_audio(_, speed):
        observed_speeds.append(speed)

    with patch("services.dubbing_service.get_audio_duration_us", side_effect=fake_get_audio_duration_us), patch(
        "services.dubbing_service.apply_speed_to_existing_audio",
        side_effect=fake_apply_speed_to_existing_audio,
    ):
        duration_us, effective_rate, adjusted = _fit_audio_to_slot(
            audio_path=fake_path,
            slot_us=2_500_000,
            base_speech_rate=1.3,
        )

    assert adjusted is True
    assert duration_us == 2_650_000
    assert len(observed_speeds) == 1
    assert observed_speeds[0] <= 1.18
    assert effective_rate > 1.3


@pytest.mark.asyncio
async def test_dubbing_fails_with_detailed_error_when_all_lines_tts_fail(tmp_path: Path):
    srt_path = tmp_path / "input.srt"
    srt_path.write_text("dummy", encoding="utf-8")

    task = _FakeTask("task-detail")
    subs = [
        _FakeSub("Xin chao", _FakeSubRipTime(0), _FakeSubRipTime(1000)),
        _FakeSub("Ban khoe khong", _FakeSubRipTime(1500), _FakeSubRipTime(3000)),
    ]

    with patch("services.dubbing_service.pysrt.open", return_value=subs), patch(
        "services.dubbing_service.get_clone_by_id",
        return_value={"id": "voice-a", "ref_text": "sample transcript"},
    ), patch("services.dubbing_service.find_draft_folder", return_value=tmp_path), patch(
        "services.dubbing_service.synthesize_line",
        side_effect=RuntimeError("model load failed"),
    ), patch("services.dubbing_service.unload_tts_model"):
        await run_dubbing_pipeline(
            srt_path=str(srt_path),
            voice_id="voice-a",
            capcut_project_name="demo",
            task=task,
        )

    task.fail.assert_awaited_once()
    failure_message = task.fail.await_args.args[0]


@pytest.mark.asyncio
async def test_dubbing_fails_with_detailed_error_when_all_lines_tts_fail(tmp_path: Path):
    srt_path = tmp_path / "input.srt"
    srt_path.write_text("dummy", encoding="utf-8")

    task = _FakeTask("task-detail")
    subs = [
        _FakeSub("Xin chao", _FakeSubRipTime(0), _FakeSubRipTime(1000)),
        _FakeSub("Ban khoe khong", _FakeSubRipTime(1500), _FakeSubRipTime(3000)),
    ]

    with patch("services.dubbing_service.pysrt.open", return_value=subs), patch(
        "services.dubbing_service.get_clone_by_id",
        return_value={"id": "voice-a", "ref_text": "sample transcript"},
    ), patch("services.dubbing_service.find_draft_folder", return_value=tmp_path), patch(
        "services.dubbing_service.synthesize_line",
        side_effect=RuntimeError("model load failed"),
    ), patch("services.dubbing_service.unload_tts_model"):
        await run_dubbing_pipeline(
            srt_path=str(srt_path),
            voice_id="voice-a",
            capcut_project_name="demo",
            task=task,
        )

    task.fail.assert_awaited_once()
    failure_message = task.fail.await_args.args[0]
    assert "Lỗi mẫu" in failure_message
    assert "model load failed" in failure_message
    assert "2/2 dòng lỗi" in failure_message
    task.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_dubbing_fails_early_when_voice_clone_is_missing(tmp_path: Path):
    srt_path = tmp_path / "input.srt"
    srt_path.write_text("dummy", encoding="utf-8")

    task = _FakeTask("task-missing-voice")
    subs = [_FakeSub("Xin chao", _FakeSubRipTime(0), _FakeSubRipTime(1000))]

    with patch("services.dubbing_service.pysrt.open", return_value=subs), patch(
        "services.dubbing_service.get_clone_by_id", return_value=None
    ), patch(
        "services.dubbing_service.list_voice_clones",
        return_value=[{"id": "voice-a"}, {"id": "voice-b"}],
    ), patch("services.dubbing_service.unload_tts_model"):
        await run_dubbing_pipeline(
            srt_path=str(srt_path),
            voice_id="missing-voice",
            capcut_project_name="demo",
            task=task,
        )

    task.fail.assert_awaited_once()
    failure_message = task.fail.await_args.args[0]
    assert "missing-voice" in failure_message
    assert "voice-a" in failure_message
    task.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_dubbing_integration_quyt_nho_voice(tmp_path: Path):
    """
    Integration test to actually generate voice using quyt-nho-voice.WAV.
    This tests the TTS model with real text: "Xin chào các bạn hôm này mình sẽ review"
    """
    from services.tts_service import synthesize_line
    
    text = "Xin chào các bạn hôm này mình sẽ review"
    voice_id = "quyt-nho-voice"
    output_path = tmp_path / "output_test_quyt_nho.wav"
    
    # Synthesize the line
    result_path = await synthesize_line(
        text=text,
        voice_id=voice_id,
        output_path=str(output_path)
    )
    
    # Verify file is created and not empty
    assert Path(result_path).exists()
    assert Path(result_path).stat().st_size > 44  # basic wav header is 44 bytes
