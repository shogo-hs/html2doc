"""LLM モジュールのフォーマット変換テスト。"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

from html2doc.config import ModelConfig
from html2doc.llm import MarkdownGenerator, _normalize_messages


class NormalizeMessagesTest(unittest.TestCase):
    """_normalize_messages の振る舞いを確認する。"""

    def test_converts_plain_strings_into_text_objects(self) -> None:
        messages = [
            {"role": "system", "content": ["hello"]},
            {"role": "user", "content": [{"type": "text", "text": "world"}]},
        ]

        normalized = _normalize_messages(messages)

        self.assertEqual(normalized[0]["content"][0]["type"], "input_text")
        self.assertEqual(normalized[0]["content"][0]["text"], "hello")
        self.assertEqual(normalized[1]["content"][0]["type"], "input_text")
        self.assertEqual(normalized[1]["content"][0]["text"], "world")


class RunRequestTest(unittest.TestCase):
    """_run_request の I/O 形式を検証する。"""

    def setUp(self) -> None:
        os.environ.setdefault("OPENAI_API_KEY", "dummy-key")

    def tearDown(self) -> None:
        os.environ.pop("OPENAI_API_KEY", None)

    def test_run_request_passes_normalized_messages(self) -> None:
        responses_stub = _ResponsesStub()
        generator = MarkdownGenerator(ModelConfig(name="fake-model"))
        generator._client = SimpleNamespace(responses=responses_stub)

        generator._run_request(
            [
                {"role": "system", "content": [{"type": "text", "text": "test"}]},
            ]
        )

        sent_messages = responses_stub.last_kwargs["input"]
        self.assertEqual(sent_messages[0]["content"][0]["type"], "input_text")


class _ResponsesStub:
    """OpenAI クライアントの `responses` エンドポイントを模倣するスタブ。"""

    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):  # type: ignore[override]
        self.last_kwargs = kwargs

        class _Result:
            output_text = ""

        return _Result()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
