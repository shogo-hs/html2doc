"""LLM 呼び出し周りの処理。"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from openai import OpenAI

from .config import ModelConfig
from .models import Asset, DocumentMetadata, KnowledgeUnit, RelationEdge, SectionChunk


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

    def extract_knowledge(self, section: SectionChunk, *, outline: Optional[str] = None) -> List[KnowledgeUnit]:
        """セクションからナレッジ単位を抽出する。"""

        instructions = (
            "あなたはコールセンター向けマニュアル編集者です。"
            " 以下のセクションを読んで、ユーザー対応に使える知識を JSON 配列で返してください。"
            " 各要素は {id,title,summary,steps,prerequisites,related_queries,tags,source_section} を含めます。"
            " JSON 以外の文字は含めないでください。"
        )
        section_text = section.to_prompt_fragment()
        context_snippets = []
        if outline:
            context_snippets.append(f"ドキュメント全体の構成:\n{outline}")
        messages = [
            {"role": "system", "content": [{"type": "text", "text": instructions}]},
            {
                "role": "user",
                "content": [
                    *(
                        {"type": "text", "text": snippet}
                        for snippet in context_snippets
                    ),
                    {
                        "type": "text",
                        "text": f"セクション {section.identifier}:\n{section_text}",
                    },
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
        *,
        sections: Optional[List[SectionChunk]] = None,
        outline: Optional[str] = None,
        assets: Optional[List[Asset]] = None,
    ) -> str:
        """ナレッジと関係グラフから最終 Markdown を生成する。"""

        instructions = (
            "あなたは Markdown ドキュメント生成の専門家です。"
            " 提供されたナレッジを章立てして、わかりやすい応対マニュアルを作成してください。"
            " # タイトル で始め、要約、詳細手順、関連リンクセクションを含めます。"
            " 関係情報をもとに関連する手順同士を参照で結び付けてください。"
            " 文書全体のアウトラインや付属アセット（画像など）があれば適宜参照し、操作手順を詳述してください。"
        )
        payload = json.dumps(
            {
                "metadata": {
                    "title": metadata.title or metadata.stem,
                    "context": metadata.context,
                },
                "knowledge": [item.to_dict() for item in knowledge],
                "relations": [edge.to_dict() for edge in relations],
                "sections": [section.to_dict() for section in sections or []],
                "outline": outline,
                "assets": [asset.to_dict() for asset in assets or []],
            },
            ensure_ascii=False,
        )
        messages = [
            {"role": "system", "content": [{"type": "text", "text": instructions}]},
            {"role": "user", "content": [{"type": "text", "text": payload}]},
        ]
        text = self._run_request(messages)
        return text.strip()

    def check_factual_consistency(
        self, markdown: str, sections: Optional[List[SectionChunk]]
    ) -> List[str]:
        """生成結果が HTML ソースと矛盾していないかを検査する。"""

        if not markdown.strip():
            return []
        section_fragments = [section.to_prompt_fragment() for section in sections or []]
        if not section_fragments:
            return []
        reference_text = "\n\n".join(section_fragments[:30])
        instructions = (
            "あなたはコールセンターマニュアルの品質検査官です。"
            " 参照セクションと生成済み Markdown を比較し、ソースに存在しない記述や矛盾を JSON 配列で返してください。"
            " 各要素は {statement, reason} を含み、不要であれば空配列 [] を返します。"
        )
        user_prompt = (
            "### 参照セクション\n"
            f"{reference_text}\n\n"
            "### 生成された Markdown\n"
            f"{markdown}"
        )
        messages = [
            {"role": "system", "content": [{"type": "text", "text": instructions}]},
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
        ]
        text = self._run_request(messages, max_output_tokens=600)
        data = self._parse_json(text)
        issues: List[str] = []
        for item in data:
            if isinstance(item, str):
                normalized = item.strip()
                if normalized:
                    issues.append(normalized)
                continue
            statement = str(item.get("statement", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if statement and reason:
                issues.append(f"{statement} (理由: {reason})")
            elif statement:
                issues.append(statement)
            elif reason:
                issues.append(reason)
        return issues

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
