"""LLM 呼び出し周りの処理。"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, Iterable, List

from openai import OpenAI

from .config import ModelConfig
from .models import DocumentMetadata, KnowledgeUnit, RelationEdge, SectionChunk


class MarkdownGenerator:
    """OpenAI モデルを使って HTML から Markdown を生成する。"""

    def __init__(self, model_config: ModelConfig) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY が未設定です。環境変数に API キーを設定してから再実行してください。"
            )
        self._client = OpenAI(api_key=api_key)
        self._model_config = model_config

    def convert(self, metadata: DocumentMetadata, html: str) -> str:
        """（後方互換用）HTML 全文を Markdown 化する。"""

        messages = self._messages_for_markdown(metadata, html)
        text = self._run_request(messages)
        return text.strip()

    def extract_knowledge(self, section: SectionChunk) -> List[KnowledgeUnit]:
        """セクションからナレッジ単位を抽出する。"""

        instructions = (
            "あなたはコールセンター向けマニュアル編集者です。"
            " 以下のセクションを読んで、ユーザー対応に使える知識を JSON 配列で返してください。"
            " 各要素は {id,title,summary,steps,prerequisites,related_queries,tags,source_section} を含めます。"
            " JSON 以外の文字は含めないでください。"
        )
        section_text = section.to_prompt_fragment()
        messages = [
            {"role": "system", "content": [{"type": "text", "text": instructions}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"セクション {section.identifier}:\n{section_text}",
                    }
                ],
            },
        ]
        text = self._run_request(messages)
        data = self._parse_json(text)
        units: List[KnowledgeUnit] = []
        for idx, item in enumerate(data, start=1):
            if not item:
                continue
            if not item.get("id") and not item.get("identifier"):
                item["id"] = f"{section.identifier}-ku-{idx}"
            units.append(
                KnowledgeUnit.from_dict({**item, "source_section": section.identifier})
            )
        return units

    def link_relations(self, knowledge: List[KnowledgeUnit]) -> List[RelationEdge]:
        """ナレッジ同士の関係を抽出する。"""

        instructions = (
            "あなたはナレッジグラフの専門家です。"
            " 以下のナレッジを読み、前提・派生・代替など意味のある関係を JSON 配列で返してください。"
            " 各要素は {source_id,target_id,relation,reason} を含みます。"
        )
        if not knowledge:
            return []
        summary = json.dumps([item.to_dict() for item in knowledge], ensure_ascii=False)
        messages = [
            {"role": "system", "content": [{"type": "text", "text": instructions}]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"ナレッジ一覧: {summary}"},
                ],
            },
        ]
        text = self._run_request(messages)
        data = self._parse_json(text)
        return [RelationEdge.from_dict(item) for item in data if item]

    def compose_markdown(
        self,
        metadata: DocumentMetadata,
        knowledge: List[KnowledgeUnit],
        relations: List[RelationEdge],
    ) -> str:
        """ナレッジと関係グラフから最終 Markdown を生成する。"""

        instructions = (
            "あなたは Markdown ドキュメント生成の専門家です。"
            " 提供されたナレッジを章立てして、わかりやすい応対マニュアルを作成してください。"
            " # タイトル で始め、要約、詳細手順、関連リンクセクションを含めます。"
            " 関係情報をもとに関連する手順同士を参照で結び付けてください。"
        )
        payload = json.dumps(
            {
                "metadata": {
                    "title": metadata.title or metadata.stem,
                    "context": metadata.context,
                },
                "knowledge": [item.to_dict() for item in knowledge],
                "relations": [edge.to_dict() for edge in relations],
            },
            ensure_ascii=False,
        )
        messages = [
            {"role": "system", "content": [{"type": "text", "text": instructions}]},
            {"role": "user", "content": [{"type": "text", "text": payload}]},
        ]
        text = self._run_request(messages)
        return text.strip()

    def _messages_for_markdown(self, metadata: DocumentMetadata, html: str) -> List[Dict[str, object]]:
        instructions = (
            "あなたはカスタマーサポート向けの応対マニュアルを Markdown に整理する専門家です。"
            " HTML の構造を保持しつつ、日本語で丁寧にまとめてください。"
        )
        header_lines = [
            f"入力ファイル: {metadata.input_path}",
            f"出力ファイル: {metadata.output_path}",
        ]
        if metadata.title:
            header_lines.append(f"タイトル指定: {metadata.title}")
        if metadata.context:
            header_lines.append(f"補足文脈: {metadata.context}")
        header_lines.append("以下の HTML を Markdown に変換してください。")
        user_prompt = "\n".join(header_lines) + "\n" + html
        return [
            {"role": "system", "content": [{"type": "text", "text": instructions}]},
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
        ]

    def _run_request(self, messages: List[Dict[str, object]], **overrides: object) -> str:
        kwargs = {**self._build_request_kwargs(), **overrides}
        response = self._client.responses.create(
            model=self._model_config.name,
            temperature=self._model_config.temperature,
            input=messages,
            **kwargs,
        )
        return (response.output_text or "").strip()

    def _parse_json(self, text: str) -> List[dict]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, count=1).strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        if not cleaned:
            return []
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        raise ValueError("LLM からの JSON 応答が不正です。")

    def _build_request_kwargs(self) -> Dict[str, object]:
        kwargs: Dict[str, object] = {}
        if self._model_config.top_p is not None:
            kwargs["top_p"] = self._model_config.top_p
        if self._model_config.max_output_tokens is not None:
            kwargs["max_output_tokens"] = self._model_config.max_output_tokens
        return kwargs


__all__ = ["MarkdownGenerator"]
