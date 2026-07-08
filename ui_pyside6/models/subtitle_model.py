# ui_pyside6/models/subtitle_model.py
"""
SubtitleEntry model + SRT parse/save utilities.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


_TIMESTAMP_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})"
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _time_str_to_ms(time_str: str) -> int:
    """'HH:MM:SS,mmm' → milliseconds (int)."""
    time_str = time_str.replace(".", ",")
    parts = time_str.split(",")
    ms_part = int(parts[1]) if len(parts) == 2 else 0
    h, m, s = parts[0].split(":")
    return int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + ms_part


def ms_to_srt_time(ms: int) -> str:
    """milliseconds → 'HH:MM:SS,mmm'."""
    ms = max(0, int(ms))
    h   = ms // 3_600_000;  ms -= h * 3_600_000
    m   = ms // 60_000;     ms -= m * 60_000
    s   = ms // 1_000;      ms -= s * 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ─── Data model ──────────────────────────────────────────────────────────────

@dataclass
class SubtitleEntry:
    index:    int
    start_ms: int   # milliseconds
    end_ms:   int   # milliseconds
    text:     str

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    @property
    def start_str(self) -> str:
        return ms_to_srt_time(self.start_ms)

    @property
    def end_str(self) -> str:
        return ms_to_srt_time(self.end_ms)

    def is_short_duration(self, threshold_ms: int = 1000) -> bool:
        return self.duration_ms < threshold_ms

    def to_srt_block(self, new_index: int | None = None) -> str:
        idx = new_index if new_index is not None else self.index
        return f"{idx}\n{self.start_str} --> {self.end_str}\n{self.text}\n\n"


# ─── Parse SRT ───────────────────────────────────────────────────────────────

def parse_srt(srt_path: str) -> list[SubtitleEntry]:
    """Read a .srt file → list[SubtitleEntry] sorted by start_ms."""
    content = Path(srt_path).read_text(encoding="utf-8-sig")
    blocks  = re.split(r"\r?\n\r?\n", content.strip())
    entries: list[SubtitleEntry] = []

    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0])
        except ValueError:
            continue
        m = _TIMESTAMP_RE.match(lines[1])
        if not m:
            continue
        start_ms = _time_str_to_ms(m.group(1))
        end_ms   = _time_str_to_ms(m.group(2))
        text     = "\n".join(lines[2:])
        entries.append(SubtitleEntry(index=idx, start_ms=start_ms, end_ms=end_ms, text=text))

    entries.sort(key=lambda e: e.start_ms)
    return entries


# ─── Save SRT ────────────────────────────────────────────────────────────────

def save_srt(entries: list[SubtitleEntry], srt_path: str) -> None:
    """Write list[SubtitleEntry] → .srt file (re-index from 1)."""
    content = "".join(e.to_srt_block(new_index=i + 1) for i, e in enumerate(entries))
    Path(srt_path).write_text(content, encoding="utf-8")


# ─── Utilities ───────────────────────────────────────────────────────────────

def reindex(entries: list[SubtitleEntry]) -> list[SubtitleEntry]:
    """Re-assign sequential index values starting from 1."""
    for i, e in enumerate(entries):
        e.index = i + 1
    return entries


def get_short_duration_warnings(
    entries: list[SubtitleEntry],
    threshold_ms: int = 1000,
) -> list[SubtitleEntry]:
    """Return entries whose duration < threshold_ms."""
    return [e for e in entries if e.is_short_duration(threshold_ms)]


def filter_duplicate_subtitles(entries: list[SubtitleEntry]) -> list[SubtitleEntry]:
    """
    Merge consecutive entries with identical (or nearly identical) text.
    Keeps the start of the first and the end of the last in each group.
    """
    if not entries:
        return []

    def _normalize(t: str) -> str:
        return " ".join(t.split()).lower()

    result: list[SubtitleEntry] = []
    current = entries[0]

    for nxt in entries[1:]:
        if _normalize(nxt.text) == _normalize(current.text):
            # Extend end time to cover duplicate
            current = SubtitleEntry(
                index=current.index,
                start_ms=current.start_ms,
                end_ms=nxt.end_ms,
                text=current.text,
            )
        else:
            result.append(current)
            current = nxt
    result.append(current)
    return reindex(result)
