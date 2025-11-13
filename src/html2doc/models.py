"""ドメイン共通のデータモデル。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass(slots=True)
class DocumentMetadata:
    """1 つの HTML 変換対象を表すメタデータ。"""

    input_path: Path
    output_path: Path
    title: Optional[str] = None
    context: Optional[str] = None

    @property
    def stem(self) -> str:
        return self.input_path.stem


@dataclass(slots=True)
class SectionChunk:
    """HTML の一部を表す論理セクション。"""

    identifier: str
    heading: Optional[str]
    level: int
    body: str
    order: int

    def to_prompt_fragment(self) -> str:
        heading = self.heading or "(見出しなし)"
        return f"[{self.identifier}] {heading} (level={self.level})\n{self.body.strip()}".strip()

    def to_dict(self) -> dict:
        return {
            "id": self.identifier,
            "heading": self.heading,
            "level": self.level,
            "body": self.body,
            "order": self.order,
        }


@dataclass(slots=True)
class Asset:
    """HTML 内の画像などのアセット。"""

    identifier: str
    src: str
    alt: Optional[str]

    def to_dict(self) -> dict:
        return {
            "id": self.identifier,
            "src": self.src,
            "alt": self.alt,
        }


@dataclass(slots=True)
class KnowledgeUnit:
    """抽出済みナレッジ。"""

    identifier: str
    title: str
    summary: str
    steps: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    related_queries: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    source_section: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeUnit":
        identifier = data.get("id") or data.get("identifier") or data.get("title")
        if not identifier:
            raise ValueError("KnowledgeUnit には `id` もしくは `title` が必要です。")
        return cls(
            identifier=str(identifier),
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            steps=[str(item) for item in data.get("steps", []) if item],
            prerequisites=[str(item) for item in data.get("prerequisites", []) if item],
            related_queries=[str(item) for item in data.get("related_queries", []) if item],
            tags=[str(item) for item in data.get("tags", []) if item],
            source_section=str(data.get("source_section")) if data.get("source_section") else None,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.identifier,
            "title": self.title,
            "summary": self.summary,
            "steps": self.steps,
            "prerequisites": self.prerequisites,
            "related_queries": self.related_queries,
            "tags": self.tags,
            "source_section": self.source_section,
        }


@dataclass(slots=True)
class RelationEdge:
    """ナレッジ間の関係。"""

    source_id: str
    target_id: str
    relation: str
    reason: str

    @classmethod
    def from_dict(cls, data: dict) -> "RelationEdge":
        if not data.get("source_id") or not data.get("target_id"):
            raise ValueError("RelationEdge には `source_id` と `target_id` が必要です。")
        return cls(
            source_id=str(data.get("source_id")),
            target_id=str(data.get("target_id")),
            relation=str(data.get("relation")),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "reason": self.reason,
        }


@dataclass(slots=True)
class ValidationReport:
    """Markdown 出力の検証結果。"""

    valid: bool
    issues: List[str] = field(default_factory=list)


@dataclass(slots=True)
class HallucinationReport:
    """LLM 生成物のハルシネーション検出結果。"""

    safe: bool
    risk_score: float
    reasons: List[str] = field(default_factory=list)
    unsupported_passages: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "safe": self.safe,
            "risk_score": self.risk_score,
            "reasons": self.reasons,
            "unsupported_passages": self.unsupported_passages,
        }


__all__ = [
    "Asset",
    "DocumentMetadata",
    "HallucinationReport",
    "KnowledgeUnit",
    "RelationEdge",
    "SectionChunk",
    "ValidationReport",
]
