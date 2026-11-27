import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.capcut_service import (
    DRAFT_PATH_PLACEHOLDER,
    extract_capcut_tts_items,
    get_audio_duration_us,
    update_capcut_audio_durations,
)
from services.dubbing_service import compute_target_speed_rate


def _write_dummy_wav(path: Path, duration_s: float = 2.0, sample_rate: int = 24000) -> None:
    num_frames = int(duration_s * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_frames)


class TestCapCutSpeedup(unittest.TestCase):
    def test_compute_target_speed_rate_fits_within_base(self):
        # 2.0s audio at 1.34x -> ~1.49s <= 1.8s slot -> stays at 1.34x
        rate, adjusted = compute_target_speed_rate(2_000_000, 1_800_000, base_rate=1.34, max_rate=1.56)
        self.assertAlmostEqual(rate, 1.34, places=4)
        self.assertFalse(adjusted)

    def test_compute_target_speed_rate_auto_adjusts_up_to_cap(self):
        # 2.2s audio in 1.5s slot -> needed ~1.474x (between 1.34x and 1.56x)
        rate, adjusted = compute_target_speed_rate(2_200_000, 1_500_000, base_rate=1.34, max_rate=1.56)
        self.assertTrue(adjusted)
        self.assertGreater(rate, 1.34)
        self.assertLessEqual(rate, 1.56)

    def test_compute_target_speed_rate_clamps_at_max_156(self):
        # 3.0s audio in 1.0s slot -> needed > 3.0x, must clamp at 1.56x
        rate, adjusted = compute_target_speed_rate(3_000_000, 1_000_000, base_rate=1.34, max_rate=1.56)
        self.assertAlmostEqual(rate, 1.56, places=4)
        self.assertTrue(adjusted)

    def test_compute_target_speed_rate_no_slot(self):
        rate, adjusted = compute_target_speed_rate(2_000_000, None, base_rate=1.34, max_rate=1.56)
        self.assertAlmostEqual(rate, 1.34, places=4)
        self.assertFalse(adjusted)

    def test_extract_and_update_capcut_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft_dir = Path(tmp) / "TestProject"
            text_reading = draft_dir / "textReading"
            text_reading.mkdir(parents=True)
            wav_file = text_reading / "line_001.wav"
            _write_dummy_wav(wav_file, duration_s=2.0)

            draft = {
                "materials": {
                    "audios": [
                        {
                            "id": "AUD-1",
                            "type": "text_to_audio",
                            "name": "Xin chao",
                            "path": f"{DRAFT_PATH_PLACEHOLDER}/textReading/line_001.wav",
                            "duration": 2_000_000,
                            "text_id": "TXT-MAT-1",
                            "tone_speaker": "BV421_vivn_streaming",
                            "resource_id": "7252594014782755330",
                            "check_flag": 62978047,
                        }
                    ],
                    "texts": [{"id": "TXT-MAT-1", "content": "Xin chao"}],
                },
                "tracks": [
                    {
                        "type": "text",
                        "segments": [
                            {
                                "id": "SEG-TXT-1",
                                "material_id": "TXT-MAT-1",
                                "target_timerange": {"start": 1_000_000, "duration": 1_500_000},
                            }
                        ],
                    },
                    {
                        "type": "audio",
                        "segments": [
                            {
                                "id": "SEG-AUD-1",
                                "material_id": "AUD-1",
                                "speed": 1.0,
                                "source_timerange": {"start": 0, "duration": 2_000_000},
                                "target_timerange": {"start": 1_000_000, "duration": 2_000_000},
                                "render_timerange": {"start": 1_000_000, "duration": 2_000_000},
                            }
                        ],
                    },
                ],
            }
            (draft_dir / "draft_content.json").write_text(json.dumps(draft), encoding="utf-8")
            (draft_dir / "key_value.json").write_text(
                json.dumps({"7252594014782755330": {"materialCategory": "tone", "is_vip": "1"}}),
                encoding="utf-8",
            )

            items = extract_capcut_tts_items(draft_dir)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["slot_duration_us"], 1_500_000)

            update_capcut_audio_durations(draft_dir, {"AUD-1": 1_400_000}, clean_pro=True)
            updated = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
            aud_mat = updated["materials"]["audios"][0]
            self.assertEqual(aud_mat["duration"], 1_400_000)
            self.assertEqual(aud_mat["tone_speaker"], "omnivoice_clone")
            self.assertEqual(aud_mat["resource_id"], "")
            self.assertEqual(updated["tracks"][1]["segments"][0]["target_timerange"]["duration"], 1_400_000)

            kv = json.loads((draft_dir / "key_value.json").read_text(encoding="utf-8"))
            self.assertNotIn("7252594014782755330", kv)


if __name__ == "__main__":
    unittest.main()
