# backend/tests/test_srt_merge_service.py
"""
Unit tests cho srt_merge_service.py

Tests bao gồm:
 - parse_srt: đọc file SRT → dict {index: SrtEntry}
 - parse_plain_subtitle: đọc file plain → list[PlainEntry]
 - merge_plain_to_srt: ghép timestamp vào bản dịch
 - Các edge case: index lệch, plain nhiều hơn/ít hơn SRT, file trống...
"""
import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from services.srt_merge_service import (
    MergeResult,
    PlainEntry,
    SrtEntry,
    _default_output_path,
    _find_ocr_srt,
    merge_plain_to_srt,
    parse_plain_subtitle,
    parse_srt,
)


# ─────────────────────────────────────────────────────────────
# Fixtures helpers
# ─────────────────────────────────────────────────────────────

def _write(path: str, content: str) -> str:
    """Ghi nội dung vào file và trả về path."""
    Path(path).write_text(textwrap.dedent(content), encoding="utf-8")
    return path


# ─────────────────────────────────────────────────────────────
# parse_srt
# ─────────────────────────────────────────────────────────────

class TestParseSrt:
    def test_basic(self, tmp_path):
        """Parse SRT cơ bản: 2 entry, đúng index/timestamp/text."""
        srt = _write(str(tmp_path / "ocr.srt"), """\
            1
            00:00:01,000 --> 00:00:03,500
            邦哥喝饮料

            2
            00:00:04,000 --> 00:00:06,000
            摔了个狗吃屎
        """)

        result = parse_srt(srt)

        assert set(result.keys()) == {1, 2}
        assert result[1].start == "00:00:01,000"
        assert result[1].end == "00:00:03,500"
        assert result[1].text == "邦哥喝饮料"
        assert result[2].text == "摔了个狗吃屎"

    def test_multiline_text(self, tmp_path):
        """Text nhiều dòng được giữ nguyên."""
        srt = _write(str(tmp_path / "ocr.srt"), """\
            1
            00:00:01,000 --> 00:00:03,000
            Dòng 1
            Dòng 2
        """)
        result = parse_srt(srt)
        assert "Dòng 1\nDòng 2" == result[1].text

    def test_dot_separator_timestamp(self, tmp_path):
        """Timestamp dùng dấu chấm (.) thay vì dấu phẩy (,) vẫn parse được."""
        srt = _write(str(tmp_path / "ocr.srt"), """\
            1
            00:00:01.000 --> 00:00:03.500
            Text đây
        """)
        result = parse_srt(srt)
        # Phải normalize thành dấu phẩy
        assert result[1].start == "00:00:01,000"

    def test_empty_file(self, tmp_path):
        """File rỗng → trả về dict rỗng."""
        srt = _write(str(tmp_path / "ocr.srt"), "")
        result = parse_srt(srt)
        assert result == {}

    def test_large_index(self, tmp_path):
        """Index lớn vẫn parse đúng."""
        srt = _write(str(tmp_path / "ocr.srt"), """\
            999
            01:30:00,000 --> 01:30:02,000
            Cuối phim
        """)
        result = parse_srt(srt)
        assert 999 in result
        assert result[999].text == "Cuối phim"

    def test_windows_crlf(self, tmp_path):
        """File với line ending CRLF (Windows) vẫn parse đúng."""
        content = "1\r\n00:00:01,000 --> 00:00:03,000\r\nHello\r\n\r\n"
        srt_path = str(tmp_path / "ocr.srt")
        Path(srt_path).write_bytes(content.encode("utf-8"))
        result = parse_srt(srt_path)
        assert 1 in result
        assert result[1].text == "Hello"

    def test_utf8_bom_does_not_skip_index_1(self, tmp_path):
        """
        Regression: file SRT lưu với UTF-8 BOM (\\ufeff) không được làm mất index 1.
        Windows Notepad và nhiều editor mặc định lưu BOM → int('\\ufeff1') sẽ fail
        nếu dùng encoding='utf-8'. Phải dùng 'utf-8-sig' để strip BOM.
        """
        srt_path = str(tmp_path / "ocr.srt")
        # Viết file có BOM thủ công bằng write_bytes
        content_with_bom = (
            "\ufeff"
            "1\n00:00:01,000 --> 00:00:03,000\n邦哥喝饮料\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\n摔了个狗吃屎\n"
        )
        Path(srt_path).write_bytes(content_with_bom.encode("utf-8"))

        result = parse_srt(srt_path)

        # Index 1 KHÔNG được bị skip do BOM
        assert 1 in result, "Index 1 bị mất do BOM bug!"
        assert 2 in result
        assert result[1].text == "邦哥喝饮料"
        assert result[2].text == "摔了个狗吃屎"


# ─────────────────────────────────────────────────────────────
# parse_plain_subtitle
# ─────────────────────────────────────────────────────────────

class TestParsePlainSubtitle:
    def test_basic(self, tmp_path):
        """Parse plain cơ bản: 2 entry đúng index/text."""
        plain = _write(str(tmp_path / "plain.txt"), """\
            1
            Anh Bang uống nước đi.

            2
            Ngã một cú sấp mặt luôn.
        """)
        result = parse_plain_subtitle(plain)
        assert len(result) == 2
        assert result[0].index == 1
        assert result[0].text == "Anh Bang uống nước đi."
        assert result[1].index == 2
        assert result[1].text == "Ngã một cú sấp mặt luôn."

    def test_multiline_text(self, tmp_path):
        """Text nhiều dòng được giữ nguyên."""
        plain = _write(str(tmp_path / "plain.txt"), """\
            1
            Dòng đầu
            Dòng hai
        """)
        result = parse_plain_subtitle(plain)
        assert result[0].text == "Dòng đầu\nDòng hai"

    def test_empty_file(self, tmp_path):
        """File rỗng → list rỗng."""
        plain = _write(str(tmp_path / "plain.txt"), "")
        result = parse_plain_subtitle(plain)
        assert result == []

    def test_non_sequential_indices(self, tmp_path):
        """Chỉ số không liên tiếp (AI có thể bỏ qua dòng) vẫn parse đúng."""
        plain = _write(str(tmp_path / "plain.txt"), """\
            1
            Câu một

            3
            Câu ba
        """)
        result = parse_plain_subtitle(plain)
        assert len(result) == 2
        assert result[0].index == 1
        assert result[1].index == 3

    def test_skips_blocks_without_integer_index(self, tmp_path):
        """Block không có chỉ số nguyên bị bỏ qua, không raise lỗi."""
        plain = _write(str(tmp_path / "plain.txt"), """\
            abc
            Không phải index

            1
            Câu hợp lệ
        """)
        result = parse_plain_subtitle(plain)
        assert len(result) == 1
        assert result[0].index == 1

    def test_utf8_bom_does_not_skip_index_1(self, tmp_path):
        """
        Regression: file plain lưu với UTF-8 BOM không được làm mất index 1.
        Dấu hiệu bug: merged_count=810 nhưng luôn báo skip index 1.
        """
        plain_path = str(tmp_path / "plain.txt")
        content_with_bom = (
            "\ufeff"
            "1\nAnh Bang, uống nước này.\n\n"
            "2\nNgã sấp mặt luôn.\n"
        )
        Path(plain_path).write_bytes(content_with_bom.encode("utf-8"))

        result = parse_plain_subtitle(plain_path)

        assert len(result) == 2, f"Thiếu entry, chỉ parse được: {result}"
        assert result[0].index == 1, "Index 1 bị mất do BOM bug!"
        assert result[0].text == "Anh Bang, uống nước này."
        assert result[1].index == 2


# ─────────────────────────────────────────────────────────────
# merge_plain_to_srt
# ─────────────────────────────────────────────────────────────

class TestMergePlainToSrt:
    def _setup_files(self, tmp_path, srt_content: str, plain_content: str):
        """Tạo ocr.srt và file plain trong cùng folder, trả về path của plain."""
        _write(str(tmp_path / "ocr.srt"), srt_content)
        plain_path = str(tmp_path / "translated_plain.txt")
        _write(plain_path, plain_content)
        return plain_path

    def test_basic_merge(self, tmp_path):
        """Ghép cơ bản: 2 dòng plain đúng index → SRT hoàn chỉnh."""
        plain_path = self._setup_files(
            tmp_path,
            srt_content="""\
                1
                00:00:01,000 --> 00:00:03,500
                邦哥喝饮料

                2
                00:00:04,000 --> 00:00:06,000
                摔了个狗吃屎
            """,
            plain_content="""\
                1
                Anh Bang uống nước đi.

                2
                Ngã một cú sấp mặt luôn.
            """,
        )
        result = merge_plain_to_srt(plain_path)

        assert result.merged_count == 2
        assert result.skipped_count == 0
        assert result.skipped_indices == []

        # Kiểm tra nội dung SRT output
        output = Path(result.output_path).read_text(encoding="utf-8")
        assert "00:00:01,000 --> 00:00:03,500" in output
        assert "Anh Bang uống nước đi." in output
        assert "00:00:04,000 --> 00:00:06,000" in output
        assert "Ngã một cú sấp mặt luôn." in output

    def test_output_path_auto_named(self, tmp_path):
        """Tên output tự động: <stem>_vietsub.srt cạnh file plain."""
        plain_path = self._setup_files(
            tmp_path,
            srt_content="""\
                1
                00:00:01,000 --> 00:00:02,000
                原文
            """,
            plain_content="""\
                1
                Bản dịch
            """,
        )
        result = merge_plain_to_srt(plain_path)
        expected = str(tmp_path / "translated_plain_vietsub.srt")
        assert result.output_path == expected
        assert Path(result.output_path).exists()

    def test_output_path_custom(self, tmp_path):
        """output_srt_path tùy chỉnh được dùng đúng."""
        plain_path = self._setup_files(
            tmp_path,
            srt_content="""\
                1
                00:00:01,000 --> 00:00:02,000
                Text
            """,
            plain_content="""\
                1
                Bản dịch
            """,
        )
        custom_out = str(tmp_path / "my_output.srt")
        result = merge_plain_to_srt(plain_path, output_srt_path=custom_out)
        assert result.output_path == custom_out
        assert Path(custom_out).exists()

    def test_skips_extra_plain_indices(self, tmp_path):
        """Plain có index không có trong SRT → bỏ qua, không crash."""
        plain_path = self._setup_files(
            tmp_path,
            srt_content="""\
                1
                00:00:01,000 --> 00:00:02,000
                Text
            """,
            plain_content="""\
                1
                Câu 1

                2
                Câu 2 không có trong SRT
            """,
        )
        result = merge_plain_to_srt(plain_path)
        assert result.merged_count == 1
        assert result.skipped_count == 1
        assert 2 in result.skipped_indices

    def test_plain_fewer_lines_than_srt(self, tmp_path):
        """Plain có ít dòng hơn SRT → chỉ ghép những dòng có trong plain."""
        plain_path = self._setup_files(
            tmp_path,
            srt_content="""\
                1
                00:00:01,000 --> 00:00:02,000
                Câu 1

                2
                00:00:03,000 --> 00:00:04,000
                Câu 2

                3
                00:00:05,000 --> 00:00:06,000
                Câu 3
            """,
            plain_content="""\
                1
                Bản dịch 1

                2
                Bản dịch 2
            """,
        )
        result = merge_plain_to_srt(plain_path)
        assert result.merged_count == 2
        assert result.skipped_count == 0

    def test_reindexes_output_sequentially(self, tmp_path):
        """SRT output phải đánh số thứ tự liên tiếp (1, 2, 3…) dù input lệch."""
        plain_path = self._setup_files(
            tmp_path,
            srt_content="""\
                1
                00:00:01,000 --> 00:00:02,000
                Câu 1

                3
                00:00:05,000 --> 00:00:06,000
                Câu 3
            """,
            plain_content="""\
                1
                Bản dịch 1

                3
                Bản dịch 3
            """,
        )
        result = merge_plain_to_srt(plain_path)
        output = Path(result.output_path).read_text(encoding="utf-8")
        lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
        # Dòng đầu block 1 phải là "1", dòng đầu block 2 phải là "2"
        assert lines[0] == "1"
        # Tìm index thứ hai (sau block đầu tiên)
        second_block_start = next(
            i for i, l in enumerate(lines) if i > 0 and l.isdigit() and int(l) >= 1
        )
        assert lines[second_block_start] == "2"

    def test_empty_plain_raises(self, tmp_path):
        """File plain rỗng → raise ValueError."""
        plain_path = self._setup_files(
            tmp_path,
            srt_content="""\
                1
                00:00:01,000 --> 00:00:02,000
                Text
            """,
            plain_content="",
        )
        with pytest.raises(ValueError, match="trống"):
            merge_plain_to_srt(plain_path)

    def test_all_indices_mismatch_raises(self, tmp_path):
        """Không ghép được dòng nào (toàn bộ index lệch) → raise ValueError."""
        plain_path = self._setup_files(
            tmp_path,
            srt_content="""\
                1
                00:00:01,000 --> 00:00:02,000
                Text
            """,
            plain_content="""\
                99
                Index không khớp
            """,
        )
        with pytest.raises(ValueError, match="Không ghép được"):
            merge_plain_to_srt(plain_path)

    def test_missing_ocr_srt_raises(self, tmp_path):
        """Không tìm thấy ocr.srt cùng folder → raise FileNotFoundError."""
        plain_path = str(tmp_path / "translated_plain.txt")
        _write(plain_path, "1\nBản dịch\n")
        # Không tạo ocr.srt
        with pytest.raises(FileNotFoundError, match="ocr.srt"):
            merge_plain_to_srt(plain_path)

    def test_explicit_ocr_srt_path(self, tmp_path):
        """Cung cấp ocr_srt_path rõ ràng thay vì tự tìm."""
        srt_path = str(tmp_path / "my_ocr.srt")
        _write(srt_path, """\
            1
            00:00:01,000 --> 00:00:02,000
            Text
        """)
        plain_path = str(tmp_path / "translated.txt")
        _write(plain_path, "1\nBản dịch\n")

        result = merge_plain_to_srt(plain_path, ocr_srt_path=srt_path)
        assert result.merged_count == 1

    def test_timestamp_preserved_in_output(self, tmp_path):
        """Timestamp từ ocr.srt phải giữ nguyên trong SRT output."""
        plain_path = self._setup_files(
            tmp_path,
            srt_content="""\
                1
                01:23:45,678 --> 01:23:47,890
                Original
            """,
            plain_content="""\
                1
                Bản dịch tiếng Việt
            """,
        )
        result = merge_plain_to_srt(plain_path)
        output = Path(result.output_path).read_text(encoding="utf-8")
        assert "01:23:45,678 --> 01:23:47,890" in output
        assert "Bản dịch tiếng Việt" in output

    def test_merge_with_bom_files_does_not_skip_index_1(self, tmp_path):
        """
        Regression: end-to-end merge khi cả ocr.srt và file plain đều có BOM.
        Index 1 không được bị báo là 'không tìm thấy'.
        """
        srt_path = str(tmp_path / "ocr.srt")
        srt_with_bom = (
            "\ufeff"
            "1\n00:00:00,000 --> 00:00:02,000\n邦哥喝饮料\n\n"
            "2\n00:00:04,000 --> 00:00:06,250\n摔了个狗吃屎\n"
        )
        Path(srt_path).write_bytes(srt_with_bom.encode("utf-8"))

        plain_path = str(tmp_path / "translated.txt")
        plain_with_bom = (
            "\ufeff"
            "1\nAnh Bang, uống nước này.\n\n"
            "2\nNgã sấp mặt luôn.\n"
        )
        Path(plain_path).write_bytes(plain_with_bom.encode("utf-8"))

        result = merge_plain_to_srt(plain_path, ocr_srt_path=srt_path)

        assert result.merged_count == 2, (
            f"Chỉ ghép được {result.merged_count} dòng, "
            f"bỏ qua index: {result.skipped_indices}"
        )
        assert result.skipped_count == 0
        output = Path(result.output_path).read_text(encoding="utf-8")
        assert "Anh Bang, uống nước này." in output
        assert "Ngã sấp mặt luôn." in output


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

class TestHelpers:
    def test_default_output_path(self, tmp_path):
        """_default_output_path tạo tên đúng."""
        plain = str(tmp_path / "viet_plain.txt")
        out = _default_output_path(plain)
        assert out == str(tmp_path / "viet_plain_vietsub.srt")

    def test_find_ocr_srt_found(self, tmp_path):
        """_find_ocr_srt tìm thấy khi file tồn tại."""
        srt = tmp_path / "ocr.srt"
        srt.write_text("", encoding="utf-8")
        plain = str(tmp_path / "plain.txt")
        found = _find_ocr_srt(plain)
        assert found == str(srt)

    def test_find_ocr_srt_not_found(self, tmp_path):
        """_find_ocr_srt raise FileNotFoundError khi không có ocr.srt."""
        plain = str(tmp_path / "plain.txt")
        with pytest.raises(FileNotFoundError):
            _find_ocr_srt(plain)
