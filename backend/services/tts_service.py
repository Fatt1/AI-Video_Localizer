from __future__ import annotations

import math
import os
import subprocess
from pathlib import Path

from core.config import FFMPEG_PATH, VOICE_CLONES_DIR


_model = None

DEFAULT_OMNIVOICE_MODEL = os.getenv("OMNIVOICE_MODEL", "k2-fsa/OmniVoice")
DEFAULT_OMNIVOICE_DTYPE = os.getenv("OMNIVOICE_DTYPE", "float16").lower()


def _import_omnivoice_class():
	try:
		from omnivoice import OmniVoice

		return OmniVoice
	except Exception as exc:
		raise RuntimeError(
			"Không thể import omnivoice. Hãy kiểm tra lại torch/torchaudio và package omnivoice."
		) from exc


def get_tts_model():
	"""Lazy-load OmniVoice model to avoid occupying VRAM until needed."""
	global _model
	if _model is None:
		try:
			import torch

			OmniVoice = _import_omnivoice_class()
			device_map = "cuda" if torch.cuda.is_available() else "cpu"
			dtype = torch.float16 if DEFAULT_OMNIVOICE_DTYPE == "float16" else torch.float32

			_model = OmniVoice.from_pretrained(
				DEFAULT_OMNIVOICE_MODEL,
				device_map=device_map,
				dtype=dtype,
				load_asr=False,
			)
		except Exception as exc:
			raise RuntimeError(
				f"Không thể load OmniVoice model '{DEFAULT_OMNIVOICE_MODEL}': {exc}"
			) from exc
	return _model


def unload_tts_model() -> None:
	"""Release OmniVoice model and clear CUDA cache when available."""
	global _model
	if _model is None:
		return

	del _model
	_model = None

	try:
		import torch

		if torch.cuda.is_available():
			torch.cuda.empty_cache()
	except Exception:
		pass


def list_voice_clones() -> list[dict]:
	"""List available voice clones from voice_clones/*.wav files."""
	clones: list[dict] = []
	for wav_file in sorted(VOICE_CLONES_DIR.glob("*.wav")):
		txt_file = wav_file.with_suffix(".txt")
		ref_text = ""
		if txt_file.exists():
			ref_text = txt_file.read_text(encoding="utf-8").strip()

		clones.append(
			{
				"id": wav_file.stem,
				"name": wav_file.stem.replace("_", " ").title(),
				"ref_audio": str(wav_file),
				"ref_text": ref_text,
				"has_transcript": txt_file.exists(),
			}
		)

	return clones


def get_clone_by_id(voice_id: str) -> dict | None:
	"""Find a voice clone by its ID."""
	for clone in list_voice_clones():
		if clone["id"] == voice_id:
			return clone
	return None


def _validate_speed(speed: float) -> float:
	if not math.isfinite(speed):
		raise ValueError("speech_rate phải là số hữu hạn")
	if speed < 0.5 or speed > 2.0:
		raise ValueError("speech_rate phải nằm trong khoảng 0.5 đến 2.0")
	return float(speed)


def _validate_atempo_rate(speed: float) -> float:
	if not math.isfinite(speed):
		raise ValueError("atempo rate phải là số hữu hạn")
	if speed <= 0.0:
		raise ValueError("atempo rate phải lớn hơn 0")
	return float(speed)


def _build_atempo_filter_chain(speed: float) -> str:
	"""Build ffmpeg atempo chain (supports only 0.5..2.0 per stage)."""
	parts: list[str] = []
	remaining = speed

	while remaining > 2.0:
		parts.append("atempo=2.0")
		remaining /= 2.0

	while remaining < 0.5:
		parts.append("atempo=0.5")
		remaining /= 0.5

	parts.append(f"atempo={remaining:.6f}")
	return ",".join(parts)


def _apply_speed_to_wav(wav_path: Path, speed: float) -> None:
	"""Apply speech rate while preserving pitch using ffmpeg atempo."""
	speed = _validate_atempo_rate(speed)
	if abs(speed - 1.0) < 1e-6:
		return

	wav_tmp = wav_path.with_name(f"{wav_path.stem}.speed_tmp{wav_path.suffix}")
	filter_chain = _build_atempo_filter_chain(speed)

	cmd = [
		FFMPEG_PATH,
		"-y",
		"-i",
		str(wav_path),
		"-filter:a",
		filter_chain,
		"-c:a",
		"pcm_s16le",
		str(wav_tmp),
	]

	proc = subprocess.run(cmd, capture_output=True, text=True)
	if proc.returncode != 0:
		raise RuntimeError(
			f"Không thể chỉnh tốc độ audio (speech_rate={speed}). "
			f"FFmpeg error: {proc.stderr.strip()[-500:]}"
		)

	wav_tmp.replace(wav_path)


def _save_audio(output: Path, audio, sample_rate: int) -> None:
	"""Write WAV using soundfile to avoid torchaudio/torchcodec save issues."""
	try:
		import numpy as np
		import soundfile as sf
		import torch

		if isinstance(audio, (list, tuple)):
			audio = audio[0]
		if not isinstance(audio, torch.Tensor):
			audio = torch.tensor(audio)
		if audio.dim() == 1:
			audio = audio.unsqueeze(0)

		wav = audio.detach().cpu().float().numpy()
		if wav.ndim != 2:
			raise RuntimeError(f"Dữ liệu audio không hợp lệ, shape={wav.shape}")

		# soundfile expects shape [num_frames, channels]
		wav = np.transpose(wav, (1, 0))
		sf.write(str(output), wav, samplerate=sample_rate, format="WAV", subtype="PCM_16")
	except Exception as exc:
		raise RuntimeError(f"Không thể lưu audio OmniVoice: {exc}") from exc


async def synthesize_line(
	text: str,
	voice_id: str,
	output_path: str,
	speech_rate: float = 1.0,
) -> str:
	"""Generate one subtitle line with OmniVoice and optional speech rate."""
	if not text or not text.strip():
		raise ValueError("text không được rỗng")

	speech_rate = _validate_speed(speech_rate)
	clone = get_clone_by_id(voice_id)
	if clone is None:
		raise ValueError(f"Voice clone '{voice_id}' không tồn tại")

	model = get_tts_model()
	audio = model.generate(
		text=text,
		ref_audio=clone["ref_audio"],
		ref_text=clone["ref_text"],
	)

	sample_rate = int(
		getattr(model, "sampling_rate", getattr(model, "sample_rate", 24000))
	)
	output = Path(output_path)
	output.parent.mkdir(parents=True, exist_ok=True)

	_save_audio(output, audio, sample_rate)
	_apply_speed_to_wav(output, speech_rate)
	return str(output)


def apply_speed_to_existing_audio(audio_path: str | Path, speed: float) -> None:
	"""
	Apply atempo directly on an existing wav file.

	This is used by dubbing pipeline for per-line adaptive overlap fitting:
	- speed > 1.0: faster (shorter audio)
	- speed < 1.0: slower (longer audio)
	"""
	_apply_speed_to_wav(Path(audio_path), speed)
