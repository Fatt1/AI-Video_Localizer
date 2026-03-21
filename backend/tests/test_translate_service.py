# backend/tests/test_translate_service.py
"""
Test suite cho translate_service.py
Kiểm tra:
  - build_prompt         : nội dung prompt, sliding window, glossary
  - translate_batch      : parse output, pad/truncate, context token, sliding window
  - run_translate_pipeline: context được thread qua các batch, cancel, output SRT
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from services.translate_service import build_prompt, STYLE_PROMPTS, CONTEXT_WINDOW


# ══════════════════════════════════════════════════════════════════════════════
# Helper — tạo mock Ollama response
# ══════════════════════════════════════════════════════════════════════════════

def _make_ollama_response(response_text: str, context: list[int] | None = None) -> MagicMock:
    """Tạo mock httpx.Response với dữ liệu Ollama."""
    payload = {"response": response_text}
    if context is not None:
        payload["context"] = context
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _patch_httpx(response: MagicMock):
    """Context manager patch httpx.AsyncClient.post."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    patcher = patch("httpx.AsyncClient")
    mock_cls = patcher.start()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return patcher, mock_client


class FakeSubs(list):
    """List-subclass giả lập pysrt.SubRipFile — có method .save() để pipeline không lỗi."""
    def save(self, path, encoding="utf-8"):
        pass


# ══════════════════════════════════════════════════════════════════════════════
# 1. build_prompt
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildPrompt:
    def test_contains_numbered_texts(self):
        texts = ["你好", "再见", "谢谢"]
        prompt = build_prompt(texts, "lifestyle", {})
        assert "1. 你好" in prompt
        assert "2. 再见" in prompt
        assert "3. 谢谢" in prompt

    def test_style_review_injected(self):
        prompt = build_prompt(["test"], "review", {})
        assert STYLE_PROMPTS["review"][:20] in prompt

    def test_style_ancient_drama_injected(self):
        prompt = build_prompt(["test"], "ancient_drama", {})
        assert STYLE_PROMPTS["ancient_drama"][:20] in prompt

    def test_unknown_style_falls_back_to_lifestyle(self):
        prompt = build_prompt(["test"], "nonexistent_style", {})
        assert STYLE_PROMPTS["lifestyle"][:20] in prompt

    def test_glossary_injected_when_provided(self):
        glossary = {"大师姐": "Đại sư tỷ", "师父": "Sư phụ"}
        prompt = build_prompt(["test"], "lifestyle", glossary)
        assert "大师姐 = Đại sư tỷ" in prompt
        assert "师父 = Sư phụ" in prompt
        assert "TỪ ĐIỂN BẮT BUỘC" in prompt

    def test_glossary_block_absent_when_empty(self):
        prompt = build_prompt(["test"], "lifestyle", {})
        assert "TỪ ĐIỂN BẮT BUỘC" not in prompt

    # ── Sliding Window ─────────────────────────────────────────────────────

    def test_sliding_window_block_injected_when_provided(self):
        prev_src = ["早上好", "你吃了吗"]
        prev_tgt = ["Chào buổi sáng", "Bạn ăn chưa"]
        prompt = build_prompt(["test"], "lifestyle", {}, prev_src=prev_src, prev_tgt=prev_tgt)
        assert "NGỮ CẢNH TRƯỚC ĐÓ" in prompt
        assert "[早上好] → [Chào buổi sáng]" in prompt
        assert "[你吃了吗] → [Bạn ăn chưa]" in prompt

    def test_sliding_window_absent_when_none(self):
        prompt = build_prompt(["test"], "lifestyle", {}, prev_src=None, prev_tgt=None)
        assert "NGỮ CẢNH TRƯỚC ĐÓ" not in prompt

    def test_sliding_window_absent_when_empty_lists(self):
        prompt = build_prompt(["test"], "lifestyle", {}, prev_src=[], prev_tgt=[])
        assert "NGỮ CẢNH TRƯỚC ĐÓ" not in prompt

    def test_sliding_window_does_not_appear_in_input_section(self):
        """Context block phải nằm trước INPUT block, không bị lẫn vào danh sách cần dịch."""
        prev_src = ["旧句"]
        prev_tgt = ["Câu cũ"]
        prompt = build_prompt(["新句"], "lifestyle", {}, prev_src=prev_src, prev_tgt=prev_tgt)
        context_pos = prompt.index("NGỮ CẢNH TRƯỚC ĐÓ")
        input_pos = prompt.index("INPUT:")
        assert context_pos < input_pos, "Context block phải xuất hiện trước INPUT:"

    def test_output_marker_present(self):
        prompt = build_prompt(["test"], "lifestyle", {})
        assert "OUTPUT (chỉ các dòng đã dịch):" in prompt


# ══════════════════════════════════════════════════════════════════════════════
# 2. translate_batch
# ══════════════════════════════════════════════════════════════════════════════

class TestTranslateBatch:
    """translate_batch trả về (list[str], list[int] | None)"""

    @pytest.mark.asyncio
    async def test_returns_tuple(self):
        patcher, _ = _patch_httpx(_make_ollama_response("1. Xin chào\n2. Tạm biệt", context=[1, 2, 3]))
        try:
            from services.translate_service import translate_batch
            result = await translate_batch(["你好", "再见"], "lifestyle", {})
        finally:
            patcher.stop()

        assert isinstance(result, tuple) and len(result) == 2
        translations, ctx = result
        assert isinstance(translations, list)
        assert ctx == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_basic_translation(self):
        patcher, _ = _patch_httpx(_make_ollama_response("1. Xin chào\n2. Tạm biệt"))
        try:
            from services.translate_service import translate_batch
            translations, _ = await translate_batch(["你好", "再见"], "lifestyle", {})
        finally:
            patcher.stop()

        assert translations == ["Xin chào", "Tạm biệt"]

    @pytest.mark.asyncio
    async def test_strips_numbering(self):
        patcher, _ = _patch_httpx(_make_ollama_response("1. Dòng một\n2. Dòng hai\n3. Dòng ba"))
        try:
            from services.translate_service import translate_batch
            translations, _ = await translate_batch(["A", "B", "C"], "lifestyle", {})
        finally:
            patcher.stop()

        assert translations == ["Dòng một", "Dòng hai", "Dòng ba"]

    @pytest.mark.asyncio
    async def test_pads_missing_lines_with_empty_string(self):
        """Ollama trả ít dòng hơn → tự pad ""."""
        patcher, _ = _patch_httpx(_make_ollama_response("1. Xin chào"))
        try:
            from services.translate_service import translate_batch
            translations, _ = await translate_batch(["A", "B", "C"], "lifestyle", {})
        finally:
            patcher.stop()

        assert len(translations) == 3
        assert translations[0] == "Xin chào"
        assert translations[1] == ""
        assert translations[2] == ""

    @pytest.mark.asyncio
    async def test_truncates_extra_lines(self):
        """Ollama trả nhiều dòng hơn → cắt bớt đúng số lượng input."""
        patcher, _ = _patch_httpx(_make_ollama_response("1. A\n2. B\n3. C\n4. D\n5. E"))
        try:
            from services.translate_service import translate_batch
            translations, _ = await translate_batch(["X", "Y"], "lifestyle", {})
        finally:
            patcher.stop()

        assert len(translations) == 2

    @pytest.mark.asyncio
    async def test_context_token_none_when_absent(self):
        """Nếu Ollama không trả context token → trả về None."""
        patcher, _ = _patch_httpx(_make_ollama_response("1. OK", context=None))
        try:
            from services.translate_service import translate_batch
            _, ctx = await translate_batch(["test"], "lifestyle", {})
        finally:
            patcher.stop()

        assert ctx is None

    @pytest.mark.asyncio
    async def test_ollama_context_token_forwarded_in_body(self):
        """Khi truyền ollama_context → request body phải chứa key 'context'."""
        mock_resp = _make_ollama_response("1. OK", context=[9, 8, 7])
        patcher, mock_client = _patch_httpx(mock_resp)
        try:
            from services.translate_service import translate_batch
            await translate_batch(["test"], "lifestyle", {}, ollama_context=[9, 8, 7])
        finally:
            patcher.stop()

        called_json = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args.args[1]
        assert "context" in called_json
        assert called_json["context"] == [9, 8, 7]

    @pytest.mark.asyncio
    async def test_no_context_token_in_body_when_not_provided(self):
        """Không truyền ollama_context → request body KHÔNG có key 'context'."""
        mock_resp = _make_ollama_response("1. OK")
        patcher, mock_client = _patch_httpx(mock_resp)
        try:
            from services.translate_service import translate_batch
            await translate_batch(["test"], "lifestyle", {})
        finally:
            patcher.stop()

        called_json = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args.args[1]
        assert "context" not in called_json

    @pytest.mark.asyncio
    async def test_sliding_window_params_reach_prompt(self):
        """prev_src/prev_tgt phải xuất hiện trong prompt gửi đi."""
        mock_resp = _make_ollama_response("1. OK")
        patcher, mock_client = _patch_httpx(mock_resp)
        try:
            from services.translate_service import translate_batch
            await translate_batch(
                ["新句"],
                "lifestyle",
                {},
                prev_src=["旧句"],
                prev_tgt=["Câu cũ"],
            )
        finally:
            patcher.stop()

        sent_prompt = (mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args.args[1])["prompt"]
        assert "旧句" in sent_prompt
        assert "Câu cũ" in sent_prompt


# ══════════════════════════════════════════════════════════════════════════════
# 3. run_translate_pipeline — context threading qua các batch
# ══════════════════════════════════════════════════════════════════════════════

class TestRunTranslatePipeline:
    """
    Dùng mock pysrt và mock translate_batch để kiểm tra pipeline logic
    mà không cần file SRT thật hay Ollama thật.
    """

    def _make_task(self, cancelled_after: int = 9999) -> MagicMock:
        """Tạo mock Task; is_cancelled() trả True sau N lần gọi."""
        task = MagicMock()
        task.update = AsyncMock()
        task.complete = AsyncMock()
        counter = {"n": 0}

        def _is_cancelled():
            counter["n"] += 1
            return counter["n"] > cancelled_after

        task.is_cancelled.side_effect = _is_cancelled
        return task

    @pytest.mark.asyncio
    async def test_context_threaded_between_batches(self, tmp_path):
        """
        Sau batch 0, pipeline phải truyền:
        - ollama_context từ batch 0 → translate_batch lần 2
        - prev_src / prev_tgt (CONTEXT_WINDOW câu cuối batch 0) → batch 1
        """
        # Chuẩn bị mock subs (30 câu → 2 batch với batch_size=15)
        n_subs = 30
        mock_subs = FakeSubs(MagicMock(text=f"src_{i}") for i in range(n_subs))

        fake_ctx_0 = [10, 20, 30]
        fake_ctx_1 = [40, 50, 60]

        call_num = {"n": 0}

        async def _fake_translate_batch(texts, style, glossary, prev_src=None, prev_tgt=None, ollama_context=None):
            idx = call_num["n"]
            call_num["n"] += 1
            if idx == 0:
                translated = [f"tgt_{i}" for i in range(len(texts))]
                return translated, fake_ctx_0
            else:
                translated = [f"tgt_{i+15}" for i in range(len(texts))]
                return translated, fake_ctx_1

        output_srt = str(tmp_path / "out.srt")
        task = self._make_task()

        with patch("pysrt.open", return_value=mock_subs), \
             patch("services.translate_service.translate_batch", side_effect=_fake_translate_batch) as mock_tb:
            from services.translate_service import run_translate_pipeline
            await run_translate_pipeline(
                srt_path="dummy.srt",
                target_language="vi",
                style="lifestyle",
                glossary={},
                output_srt=output_srt,
                task=task,
                batch_size=15,
            )

        assert mock_tb.call_count == 2

        # Batch 1: ollama_context phải là giá trị trả về từ batch 0
        _, kw1 = mock_tb.call_args_list[1]
        assert kw1["ollama_context"] == fake_ctx_0, "KV-cache phải được thread sang batch tiếp theo"

        # Batch 1: prev_src phải là CONTEXT_WINDOW câu cuối batch 0
        expected_prev_src = [f"src_{i}" for i in range(15 - CONTEXT_WINDOW, 15)]
        assert kw1["prev_src"] == expected_prev_src
        expected_prev_tgt = [f"tgt_{i}" for i in range(15 - CONTEXT_WINDOW, 15)]
        assert kw1["prev_tgt"] == expected_prev_tgt

    @pytest.mark.asyncio
    async def test_first_batch_has_no_context(self, tmp_path):
        """Batch đầu tiên: prev_src, prev_tgt, ollama_context đều là None."""
        mock_subs = FakeSubs(MagicMock(text=f"src_{i}") for i in range(5))
        task = self._make_task()

        async def _fake_tb(texts, style, glossary, prev_src=None, prev_tgt=None, ollama_context=None):
            return [f"tgt_{i}" for i in range(len(texts))], None

        with patch("pysrt.open", return_value=mock_subs), \
             patch("services.translate_service.translate_batch", side_effect=_fake_tb) as mock_tb:
            from services.translate_service import run_translate_pipeline
            await run_translate_pipeline("dummy.srt", "vi", "lifestyle", {}, str(tmp_path / "o.srt"), task, batch_size=15)

        _, kw0 = mock_tb.call_args_list[0]
        assert kw0["prev_src"] is None
        assert kw0["prev_tgt"] is None
        assert kw0["ollama_context"] is None

    @pytest.mark.asyncio
    async def test_pipeline_cancels_mid_batch(self, tmp_path):
        """Nếu is_cancelled() → True trước batch 2 thì translate_batch chỉ gọi 1 lần."""
        mock_subs = [MagicMock(text=f"src_{i}") for i in range(30)]
        task = self._make_task(cancelled_after=1)  # cancel sớm

        async def _fake_tb(texts, style, glossary, **kw):
            return [f"tgt_{i}" for i in range(len(texts))], None

        with patch("pysrt.open", return_value=mock_subs), \
             patch("services.translate_service.translate_batch", side_effect=_fake_tb) as mock_tb:
            from services.translate_service import run_translate_pipeline
            await run_translate_pipeline("dummy.srt", "vi", "lifestyle", {}, str(tmp_path / "o.srt"), task, batch_size=15)

        # Pipeline dừng lại, không dịch hết tất cả batch
        assert mock_tb.call_count < 2

    @pytest.mark.asyncio
    async def test_translated_texts_assigned_to_subs(self, tmp_path):
        """Text đã dịch phải được gán vào sub.text đúng thứ tự."""
        mock_subs = [MagicMock(text=f"src_{i}") for i in range(3)]
        task = self._make_task()
        expected = ["Câu một", "Câu hai", "Câu ba"]

        async def _fake_tb(texts, style, glossary, **kw):
            return expected[:len(texts)], None

        with patch("pysrt.open", return_value=mock_subs), \
             patch("services.translate_service.translate_batch", side_effect=_fake_tb):
            from services.translate_service import run_translate_pipeline
            # Patch subs.save để không cần ghi file thật
            mock_subs_obj = MagicMock()
            mock_subs_obj.__len__ = MagicMock(return_value=3)
            mock_subs_obj.__iter__ = MagicMock(return_value=iter(mock_subs))
            mock_subs_obj.__getitem__ = lambda s, i: mock_subs[i]
            mock_subs_obj.save = MagicMock()
            with patch("pysrt.open", return_value=mock_subs_obj):
                await run_translate_pipeline("dummy.srt", "vi", "lifestyle", {}, str(tmp_path / "o.srt"), task)

        for i, sub in enumerate(mock_subs_obj):
            assert sub.text == expected[i], f"sub[{i}].text sai: {sub.text!r}"

    @pytest.mark.asyncio
    async def test_task_complete_called_with_result(self, tmp_path):
        """Pipeline phải gọi task.complete() với srt_path và total_lines đúng."""
        mock_subs = [MagicMock(text=f"src_{i}") for i in range(5)]
        mock_subs_save = MagicMock()

        class FakeSubs(list):
            save = mock_subs_save

        fake_subs = FakeSubs(mock_subs)
        task = self._make_task()

        async def _fake_tb(texts, style, glossary, **kw):
            return [f"tgt" for _ in texts], None

        out = str(tmp_path / "result.srt")
        with patch("pysrt.open", return_value=fake_subs), \
             patch("services.translate_service.translate_batch", side_effect=_fake_tb):
            from services.translate_service import run_translate_pipeline
            await run_translate_pipeline("dummy.srt", "vi", "lifestyle", {}, out, task)

        task.complete.assert_called_once()
        result_arg = task.complete.call_args.kwargs.get("result") or task.complete.call_args.args[0]
        assert result_arg["srt_path"] == out
        assert result_arg["total_lines"] == 5
