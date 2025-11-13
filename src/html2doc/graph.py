"""LangGraph を使った変換パイプライン定義。"""
from __future__ import annotations

import json
from typing import List, Tuple, TypedDict

from bs4 import BeautifulSoup
from bs4.element import Tag
from langgraph.graph import END, START, StateGraph

from .llm import MarkdownGenerator
from .models import (
    Asset,
    DocumentMetadata,
    KnowledgeUnit,
    RelationEdge,
    SectionChunk,
    ValidationReport,
)


class DocumentState(TypedDict, total=False):
    """LangGraph で共有する状態。"""

    metadata: DocumentMetadata
    html: str
    sections: List[SectionChunk]
    assets: List[Asset]
    outline: str
    knowledge_items: List[KnowledgeUnit]
    relationships: List[RelationEdge]
    markdown: str
    report: ValidationReport
    output_path: str
    graph_path: str


def _load_html(state: DocumentState) -> DocumentState:
    metadata = state["metadata"]
    content = metadata.input_path.read_text(encoding="utf-8")
    return {"html": content}


def _parse_html(state: DocumentState) -> DocumentState:
    html = state["html"]
    sections, assets = _extract_sections_and_assets(html)
    return {"sections": sections, "assets": assets}


def _summarize_structure_node(state: DocumentState) -> DocumentState:
    sections = state.get("sections", [])
    outline = _build_outline(sections)
    return {"outline": outline}


def _extract_knowledge_node(state: DocumentState, llm: MarkdownGenerator) -> DocumentState:
    sections = state.get("sections", [])
    outline = state.get("outline") or None
    knowledge = _extract_all_knowledge(llm, sections, outline)
    return {"knowledge_items": knowledge}


def _link_relations_node(state: DocumentState, llm: MarkdownGenerator) -> DocumentState:
    knowledge = state.get("knowledge_items", [])
    relations = llm.link_relations(knowledge)
    return {"relationships": relations}


def _compose_markdown_node(state: DocumentState, llm: MarkdownGenerator) -> DocumentState:
    metadata = state["metadata"]
    knowledge = state.get("knowledge_items", [])
    relations = state.get("relationships", [])
    sections = state.get("sections", [])
    outline = state.get("outline") or None
    assets = state.get("assets", [])
    markdown = llm.compose_markdown(
        metadata,
        knowledge,
        relations,
        sections=sections,
        outline=outline,
        assets=assets,
    )
    return {"markdown": markdown}


def _persist_markdown(state: DocumentState) -> DocumentState:
    metadata = state["metadata"]
    markdown = state["markdown"]
    metadata.output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata.output_path.write_text(markdown, encoding="utf-8")
    graph_path = metadata.output_path.with_suffix(".json")
    report = state.get("report")
    payload = {
        "metadata": {
            "input_path": str(metadata.input_path),
            "output_path": str(metadata.output_path),
            "title": metadata.title,
            "context": metadata.context,
        },
        "sections": [section.to_dict() for section in state.get("sections", [])],
        "assets": [asset.to_dict() for asset in state.get("assets", [])],
        "outline": state.get("outline"),
        "knowledge": [item.to_dict() for item in state.get("knowledge_items", [])],
        "relationships": [edge.to_dict() for edge in state.get("relationships", [])],
        "validation": {
            "valid": report.valid if report else True,
            "issues": report.issues if report else [],
        },
    }
    graph_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_path": str(metadata.output_path), "graph_path": str(graph_path)}


def _validate_output(state: DocumentState) -> DocumentState:
    markdown = state["markdown"]
    report = _validate_markdown(markdown, state.get("knowledge_items", []))
    if not report.valid:
        issues = " / ".join(report.issues)
        raise ValueError(f"Markdown 検証に失敗しました: {issues}")
    return {"report": report}


def _extract_all_knowledge(
    llm: MarkdownGenerator,
    sections: List[SectionChunk],
    outline: str | None,
) -> List[KnowledgeUnit]:
    knowledge: List[KnowledgeUnit] = []
    for section in sections:
        knowledge.extend(llm.extract_knowledge(section, outline=outline))
    return knowledge


def _extract_sections_and_assets(html: str) -> Tuple[List[SectionChunk], List[Asset]]:
    soup = BeautifulSoup(html, "html.parser")
    assets: List[Asset] = []
    for idx, img in enumerate(soup.find_all("img"), start=1):
        assets.append(
            Asset(
                identifier=f"asset-{idx}",
                src=img.get("src", ""),
                alt=img.get("alt"),
            )
        )

    sections: List[SectionChunk] = []
    current_heading = None
    current_level = 1
    buffer: List[str] = []

    def flush(order: int) -> int:
        text = "\n".join(line for line in buffer if line.strip()).strip()
        buffer.clear()
        if text:
            sections.append(
                SectionChunk(
                    identifier=f"sec-{order}",
                    heading=current_heading,
                    level=current_level,
                    body=text,
                    order=order,
                )
            )
            return order + 1
        return order

    order = 1
    for element in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "table", "pre", "code"]
    ):
        if element.name and element.name.startswith("h"):
            order = flush(order)
            current_heading = element.get_text(" ", strip=True)
            try:
                current_level = int(element.name[1])
            except (ValueError, IndexError):
                current_level = 1
            continue
        text = _element_text(element)
        if text:
            buffer.append(text)
    flush(order)

    if not sections:
        text = soup.get_text(" ", strip=True)
        if text:
            sections.append(
                SectionChunk(
                    identifier="sec-1",
                    heading="全文",
                    level=1,
                    body=text,
                    order=1,
                )
            )

    return sections, assets


def _element_text(element: Tag) -> str:
    if element.name == "table":
        return _table_to_markdown(element)
    if element.name in {"pre", "code"}:
        return f"```\n{element.get_text()}\n```"
    return element.get_text(" ", strip=True)


def _build_outline(sections: List[SectionChunk]) -> str:
    if not sections:
        return ""
    lines: List[str] = []
    for section in sections:
        heading = section.heading or "(無題セクション)"
        indent = "  " * max(section.level - 1, 0)
        preview = section.body.strip().splitlines()
        first_line = preview[0][:80] if preview else ""
        suffix = f" - {first_line}" if first_line else ""
        lines.append(f"{indent}- {heading}{suffix}")
    return "\n".join(lines)


def _table_to_markdown(table: Tag) -> str:
    rows = []
    for row in table.find_all("tr"):
        cols = [col.get_text(" ", strip=True) for col in row.find_all(["th", "td"])]
        if cols:
            rows.append(cols)
    if not rows:
        return ""
    header = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    widths = [max(len(col), 3) for col in header]
    fmt_row = lambda items: "| " + " | ".join(item.ljust(widths[idx]) for idx, item in enumerate(items)) + " |"
    lines = [fmt_row(header), "| " + " | ".join("-" * widths[idx] for idx in range(len(header))) + " |"]
    for row in body:
        padded = row + [""] * (len(header) - len(row))
        lines.append(fmt_row(padded[: len(header)]))
    return "\n".join(lines)


def _validate_markdown(markdown: str, knowledge: List[KnowledgeUnit]) -> ValidationReport:
    issues: List[str] = []
    stripped = markdown.strip()
    if not stripped:
        issues.append("出力が空です。")
    if stripped and not stripped.lstrip().startswith("#"):
        issues.append("先頭にタイトル見出し (# ...) がありません。")
    missing_titles = [item.title for item in knowledge[:10] if item.title and item.title not in markdown]
    if len(missing_titles) >= max(3, len(knowledge[:10]) // 2 + 1):
        issues.append("抽出されたナレッジの多くが Markdown に反映されていません。")
    return ValidationReport(valid=not issues, issues=issues)


def build_pipeline(llm: MarkdownGenerator):
    """LangGraph パイプラインを構築して返す。"""

    graph = StateGraph(DocumentState)
    graph.add_node("load_html", _load_html)
    graph.add_node("parse_html", _parse_html)
    graph.add_node("summarize_structure", _summarize_structure_node)
    graph.add_node("extract_knowledge", lambda state: _extract_knowledge_node(state, llm))
    graph.add_node("link_relations", lambda state: _link_relations_node(state, llm))
    graph.add_node("compose_markdown", lambda state: _compose_markdown_node(state, llm))
    graph.add_node("validate_output", _validate_output)
    graph.add_node("persist_markdown", _persist_markdown)

    graph.add_edge(START, "load_html")
    graph.add_edge("load_html", "parse_html")
    graph.add_edge("parse_html", "summarize_structure")
    graph.add_edge("summarize_structure", "extract_knowledge")
    graph.add_edge("extract_knowledge", "link_relations")
    graph.add_edge("link_relations", "compose_markdown")
    graph.add_edge("compose_markdown", "validate_output")
    graph.add_edge("validate_output", "persist_markdown")
    graph.add_edge("persist_markdown", END)

    return graph.compile()


__all__ = ["DocumentState", "build_pipeline"]
